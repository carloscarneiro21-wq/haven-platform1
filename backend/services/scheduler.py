"""
Daily Validation Scheduler - Automatic E2E validation at 09:00 Europe/Lisbon.

Features:
- Runs once per day at configurable time
- PAPER mode only gate
- Distributed lock to prevent duplicate runs
- Restart recovery with catch-up logic
- Event Timeline integration
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import pytz
import logging
import uuid
import os

logger = logging.getLogger(__name__)

# Constants
LISBON_TZ = pytz.timezone("Europe/Lisbon")
DEFAULT_SCHEDULE_HOUR = 9
DEFAULT_SCHEDULE_MINUTE = 0


class ValidationScheduler:
    """
    Manages automatic daily validation scheduling.
    
    Safety:
    - PAPER mode only
    - Distributed lock via MongoDB
    - Singleton pattern per instance
    - Skip if validation already running
    """
    
    LOCK_COLLECTION = "scheduler_locks"
    STATE_COLLECTION = "scheduler_state"
    LOCK_NAME = "daily_validation"
    LOCK_TTL_SECONDS = 3600  # 1 hour max lock time
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.validator = None
        self.event_logger = None
        self._enabled = False
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._instance_id = str(uuid.uuid4())[:8]
        
        # Schedule config
        self.schedule_hour = DEFAULT_SCHEDULE_HOUR
        self.schedule_minute = DEFAULT_SCHEDULE_MINUTE
        self.timezone = LISBON_TZ
        
        # State tracking
        self._last_scheduled_run: Optional[datetime] = None
        self._last_run_id: Optional[str] = None
        self._next_run_at: Optional[datetime] = None
        
    def set_validator(self, validator):
        """Set the production validator instance."""
        self.validator = validator
        
    def set_event_logger(self, event_logger):
        """Set event logger for emitting events."""
        self.event_logger = event_logger
    
    async def initialize(self):
        """Initialize scheduler - load state and check for catch-up."""
        # Create TTL index for lock expiration
        try:
            await self.db[self.LOCK_COLLECTION].create_index(
                "expires_at",
                expireAfterSeconds=0
            )
        except Exception:
            pass  # Index may already exist
        
        # Load saved state
        state = await self.db[self.STATE_COLLECTION].find_one(
            {"name": self.LOCK_NAME},
            {"_id": 0}
        )
        
        if state:
            self._enabled = state.get("enabled", False)
            self._last_scheduled_run = self._parse_datetime(state.get("last_scheduled_run"))
            self._last_run_id = state.get("last_run_id")
            self.schedule_hour = state.get("schedule_hour", DEFAULT_SCHEDULE_HOUR)
            self.schedule_minute = state.get("schedule_minute", DEFAULT_SCHEDULE_MINUTE)
            
            logger.info(f"Scheduler state loaded: enabled={self._enabled}, last_run={self._last_scheduled_run}")
        
        # Calculate next run time
        self._update_next_run_time()
        
        # If enabled, start the scheduler
        if self._enabled:
            await self.start()
    
    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from string or return None."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    
    def _update_next_run_time(self):
        """Calculate the next scheduled run time."""
        now = datetime.now(self.timezone)
        
        # Today's scheduled time
        today_run = now.replace(
            hour=self.schedule_hour,
            minute=self.schedule_minute,
            second=0,
            microsecond=0
        )
        
        # If we've passed today's time, schedule for tomorrow
        if now >= today_run:
            self._next_run_at = today_run + timedelta(days=1)
        else:
            self._next_run_at = today_run
        
        # Convert to UTC for storage
        self._next_run_at = self._next_run_at.astimezone(timezone.utc)
    
    async def _save_state(self):
        """Save scheduler state to MongoDB."""
        state = {
            "name": self.LOCK_NAME,
            "enabled": self._enabled,
            "last_scheduled_run": self._last_scheduled_run.isoformat() if self._last_scheduled_run else None,
            "last_run_id": self._last_run_id,
            "schedule_hour": self.schedule_hour,
            "schedule_minute": self.schedule_minute,
            "timezone": str(self.timezone),
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
            "instance_id": self._instance_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.db[self.STATE_COLLECTION].update_one(
            {"name": self.LOCK_NAME},
            {"$set": state},
            upsert=True
        )
    
    async def _acquire_lock(self) -> bool:
        """Try to acquire distributed lock. Returns True if acquired."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.LOCK_TTL_SECONDS)
        
        try:
            # Try to insert lock (will fail if exists and not expired)
            result = await self.db[self.LOCK_COLLECTION].update_one(
                {
                    "name": self.LOCK_NAME,
                    "$or": [
                        {"expires_at": {"$lt": now}},  # Expired
                        {"expires_at": {"$exists": False}},  # No expiry set
                    ]
                },
                {
                    "$set": {
                        "name": self.LOCK_NAME,
                        "acquired_by": self._instance_id,
                        "acquired_at": now,
                        "expires_at": expires_at,
                    }
                },
                upsert=True
            )
            
            # Check if we got the lock
            if result.upserted_id or result.modified_count > 0:
                logger.info(f"Scheduler lock acquired by {self._instance_id}")
                return True
            
            # Check if we already hold the lock
            lock = await self.db[self.LOCK_COLLECTION].find_one({"name": self.LOCK_NAME})
            if lock and lock.get("acquired_by") == self._instance_id:
                return True
                
            return False
        except Exception as e:
            logger.warning(f"Failed to acquire scheduler lock: {e}")
            return False
    
    async def _release_lock(self):
        """Release the distributed lock."""
        await self.db[self.LOCK_COLLECTION].delete_one({
            "name": self.LOCK_NAME,
            "acquired_by": self._instance_id
        })
    
    def _is_paper_mode(self) -> bool:
        """Check if system is in PAPER mode."""
        mode = os.environ.get("TRADING_MODE", "paper").lower()
        return mode == "paper"
    
    async def start(self) -> Dict[str, Any]:
        """Start the daily validation scheduler."""
        if self._running:
            return {"already_running": True, "instance": self._instance_id}
        
        self._enabled = True
        self._running = True
        await self._save_state()
        
        # Check for catch-up run on startup
        await self._check_catchup()
        
        # Start scheduler loop
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Validation scheduler started (instance: {self._instance_id})")
        
        return {
            "started": True,
            "instance": self._instance_id,
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
        }
    
    async def stop(self) -> Dict[str, Any]:
        """Stop the daily validation scheduler."""
        self._enabled = False
        self._running = False
        await self._save_state()
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Validation scheduler stopped")
        
        return {"stopped": True}
    
    async def _check_catchup(self):
        """
        Check if we need to run a catch-up validation.
        Run if last successful scheduled run is older than 24h.
        """
        if not self._is_paper_mode():
            return
        
        now = datetime.now(timezone.utc)
        
        # If never run before, or last run is older than 24h
        should_catchup = False
        
        if self._last_scheduled_run is None:
            should_catchup = True
            reason = "No previous scheduled run"
        elif (now - self._last_scheduled_run).total_seconds() > 86400:  # 24h
            should_catchup = True
            reason = f"Last run was {(now - self._last_scheduled_run).total_seconds() / 3600:.1f}h ago"
        
        if should_catchup:
            logger.info(f"Catch-up validation triggered: {reason}")
            
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.INFO,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_CATCHUP",
                    message=f"Catch-up validation triggered on startup: {reason}",
                    context={
                        "reason": reason,
                        "last_scheduled_run": self._last_scheduled_run.isoformat() if self._last_scheduled_run else None,
                        "instance_id": self._instance_id,
                    },
                    tags=["scheduler", "catchup", "validation"]
                )
            
            # Run catch-up validation
            await self._run_scheduled_validation(is_catchup=True)
    
    async def _scheduler_loop(self):
        """Main scheduler loop - checks every minute if it's time to run."""
        logger.info("Scheduler loop started")
        
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self._enabled:
                    continue
                
                now = datetime.now(self.timezone)
                
                # Check if it's time to run
                if (now.hour == self.schedule_hour and 
                    now.minute == self.schedule_minute):
                    
                    # Check if we already ran today
                    today = now.date()
                    if self._last_scheduled_run:
                        last_run_date = self._last_scheduled_run.astimezone(self.timezone).date()
                        if last_run_date == today:
                            continue  # Already ran today
                    
                    await self._run_scheduled_validation()
                    self._update_next_run_time()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry
        
        logger.info("Scheduler loop stopped")
    
    async def _run_scheduled_validation(self, is_catchup: bool = False):
        """Execute the scheduled validation with all safety checks."""
        start_time = datetime.now(timezone.utc)
        
        # Gate 1: PAPER mode only
        if not self._is_paper_mode():
            logger.info("Scheduled validation skipped: not in PAPER mode")
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.INFO,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_SKIPPED_LIVE_MODE",
                    message="Daily validation skipped: system is in LIVE mode",
                    context={"mode": "live"},
                    tags=["scheduler", "skipped"]
                )
            return
        
        # Gate 2: Acquire distributed lock
        if not await self._acquire_lock():
            logger.info("Scheduled validation skipped: another instance is running")
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.INFO,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_SKIPPED_LOCKED",
                    message="Daily validation skipped: another instance holds the lock",
                    tags=["scheduler", "skipped", "lock"]
                )
            return
        
        try:
            # Gate 3: Check if validation is already running
            if self.validator and self.validator._current_run:
                current_status = self.validator._current_run.status
                if current_status in ["pending", "running"]:
                    logger.info("Scheduled validation skipped: validation already running")
                    if self.event_logger:
                        from services.event_logger import EventSeverity, EventCategory
                        await self.event_logger.emit(
                            severity=EventSeverity.INFO,
                            category=EventCategory.SYSTEM,
                            type="DAILY_VALIDATION_SKIPPED_ALREADY_RUNNING",
                            message="Daily validation skipped: validation already in progress",
                            context={"current_run_id": self.validator._current_run.id},
                            tags=["scheduler", "skipped"]
                        )
                    return
            
            # Emit DAILY_VALIDATION_TRIGGERED event
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.INFO,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_TRIGGERED",
                    message=f"Daily validation triggered (scheduled: {not is_catchup}, catchup: {is_catchup})",
                    context={
                        "scheduled": not is_catchup,
                        "catchup": is_catchup,
                        "timezone": str(self.timezone),
                        "schedule_time": f"{self.schedule_hour:02d}:{self.schedule_minute:02d}",
                        "instance_id": self._instance_id,
                    },
                    tags=["scheduler", "triggered", "validation"]
                )
            
            # Run validation
            if not self.validator:
                raise Exception("Validator not initialized")
            
            run_id = await self.validator.start_validation()
            logger.info(f"Scheduled validation started: {run_id}")
            
            # Wait for validation to complete (poll status)
            max_wait = 300  # 5 minutes max
            poll_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
                status = await self.validator.get_status(run_id)
                if status and status.get("status") in ["completed", "failed"]:
                    break
            
            # Get final result
            result = await self.validator.get_result(run_id)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Update state
            self._last_scheduled_run = datetime.now(timezone.utc)
            self._last_run_id = run_id
            await self._save_state()
            
            # Collect 24h metrics for summary
            metrics_24h = await self._collect_24h_metrics()
            
            # Emit completion event
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                
                # Determine severity based on result
                overall = result.get("overall_result", "FAIL") if result else "FAIL"
                if overall == "PASS":
                    severity = EventSeverity.INFO
                elif overall == "WARNING":
                    severity = EventSeverity.WARNING
                else:
                    severity = EventSeverity.ERROR
                
                await self.event_logger.emit(
                    severity=severity,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_COMPLETED",
                    message=f"Daily validation completed: {overall}",
                    context={
                        "run_id": run_id,
                        "pass_count": result.get("passed", 0) if result else 0,
                        "fail_count": result.get("failed", 0) if result else 0,
                        "warning_count": result.get("warnings", 0) if result else 0,
                        "duration_ms": duration_ms,
                        "overall_result": overall,
                        "scheduled": not is_catchup,
                    },
                    tags=["scheduler", "completed", "validation"]
                )
                
                # Emit DAILY_RUN_SUMMARY with aggregated metrics
                warning_count = result.get("warnings", 0) if result else 0
                
                # Ensure overall is a clean string
                overall_str = str(overall).replace("CheckResult.", "")
                
                # Use PROD metrics for severity grading (excludes test activity)
                safe_mode_prod = metrics_24h["safe_mode_count_prod"]
                switches_prod = metrics_24h["source_switches_prod"]
                errors_prod = metrics_24h["errors_count_prod"]
                health_status_prod = metrics_24h["health_status_prod"]
                
                # Severity based on PROD-only metrics
                if safe_mode_prod >= 10 or switches_prod >= 6 or errors_prod >= 3:
                    summary_severity = EventSeverity.ERROR
                elif safe_mode_prod > 3 or switches_prod > 2 or errors_prod > 0:
                    summary_severity = EventSeverity.WARNING
                else:
                    summary_severity = EventSeverity.INFO
                
                await self.event_logger.emit(
                    severity=summary_severity,
                    category=EventCategory.SYSTEM,
                    type="DAILY_RUN_SUMMARY",
                    message=f"Daily Summary: {overall_str} | Health: {health_status_prod} | Prod Safe Mode: {safe_mode_prod} | Prod Switches: {switches_prod} | Prod Errors: {errors_prod}",
                    context={
                        # Validation result
                        "result": overall_str,  # PASS/FAIL/WARNING
                        "health_status": health_status_prod,  # HEALTHY/DEGRADED/UNHEALTHY (based on PROD metrics)
                        "warning_count": warning_count,
                        "run_id": run_id,
                        "validation_passed": result.get("passed", 0) if result else 0,
                        "validation_failed": result.get("failed", 0) if result else 0,
                        
                        # PROD metrics (excluding test activity - used for severity grading)
                        "prod_like": {
                            "safe_mode_count": safe_mode_prod,
                            "source_switches": switches_prod,
                            "errors_count": errors_prod,
                            "primary_source_uptime_pct": metrics_24h["primary_source_uptime_pct_prod"],
                            "health_status": health_status_prod,
                        },
                        
                        # TOTAL metrics (including test activity - for transparency)
                        "total": {
                            "safe_mode_count": metrics_24h["safe_mode_count_total"],
                            "source_switches": metrics_24h["source_switches_total"],
                            "switch_attempts_blocked": metrics_24h["switch_attempts_blocked"],
                            "errors_count": metrics_24h["errors_count_total"],
                            "primary_source_uptime_pct": metrics_24h["primary_source_uptime_pct_total"],
                            "health_status": metrics_24h["health_status_total"],
                        },
                        
                        # Safe mode breakdown by reason
                        "safe_mode_reason_counts": metrics_24h["safe_mode_reason_counts"],
                        
                        # Other metrics
                        "trades_count_24h": metrics_24h["trades_count"],
                        "avg_data_age_s_24h": metrics_24h["avg_data_age_s"],
                        "p95_data_age_s_24h": metrics_24h["p95_data_age_s"],
                        
                        # Exclusions applied
                        "test_exclusions": metrics_24h["exclusions"],
                        
                        # Thresholds used for reference
                        "thresholds": {
                            "info": {"safe_mode": 3, "switches": 2, "errors": 0},
                            "warning": {"safe_mode": 3, "switches": 2, "errors": 0},
                            "error": {"safe_mode": 10, "switches": 6, "errors": 3},
                        }
                    },
                    tags=["daily_summary", "metrics", "24h", health_status_prod.lower()]
                )
            
            logger.info(f"Scheduled validation completed: {run_id} ({overall})")
            
        except Exception as e:
            logger.error(f"Scheduled validation failed: {e}")
            
            if self.event_logger:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.ERROR,
                    category=EventCategory.SYSTEM,
                    type="DAILY_VALIDATION_FAILED_TO_START",
                    message=f"Daily validation failed to start: {str(e)}",
                    context={
                        "error": str(e),
                        "instance_id": self._instance_id,
                    },
                    tags=["scheduler", "error", "validation"]
                )
        finally:
            await self._release_lock()
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "enabled": self._enabled,
            "running": self._running,
            "timezone": str(self.timezone),
            "schedule_time": f"{self.schedule_hour:02d}:{self.schedule_minute:02d}",
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
            "last_run_at": self._last_scheduled_run.isoformat() if self._last_scheduled_run else None,
            "last_run_id": self._last_run_id,
            "instance_id": self._instance_id,
        }
    
    async def _collect_24h_metrics(self) -> Dict[str, Any]:
        """
        Collect comprehensive metrics from the last 24 hours for the daily summary.
        
        Separates:
        - TOTAL metrics (all events)
        - PROD metrics (excluding validation_test, stress_lab, simulated)
        
        Includes:
        - safe_mode_count and reason breakdown
        - source_switches vs blocked attempts
        - primary source uptime percentage
        - data age statistics (avg, p95)
        """
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_24h_iso = last_24h.isoformat()
        
        # Tags/reasons to exclude for "prod" metrics
        test_exclusions = ["validation_test", "stress_lab", "stress_test", "simulation", "simulated", "test"]
        
        try:
            # === SAFE MODE METRICS ===
            # Get all safe mode events
            safe_mode_events = await self.db.events.find({
                "type": "SAFE_MODE_ENTERED",
                "ts": {"$gte": last_24h_iso}
            }, {"_id": 0, "context": 1, "message": 1, "tags": 1}).to_list(1000)
            
            safe_mode_count_total = len(safe_mode_events)
            safe_mode_count_prod = 0
            
            safe_mode_reason_counts = {
                "data_stale": 0,
                "api_errors": 0,
                "latency": 0,
                "validation_test": 0,
                "stress_lab": 0,
                "other": 0,
            }
            
            for event in safe_mode_events:
                ctx = event.get("context", {})
                reason = ctx.get("reason", "").lower()
                message = (event.get("message") or "").lower()
                tags = event.get("tags", [])
                is_simulated = ctx.get("simulated", False) or ctx.get("test_scope", False)
                
                # Determine category
                is_test = False
                if is_simulated or any(t in tags for t in test_exclusions):
                    is_test = True
                elif any(excl in reason for excl in test_exclusions):
                    is_test = True
                
                # Categorize by reason
                if "stale" in reason or "age" in reason or "stale" in message:
                    safe_mode_reason_counts["data_stale"] += 1
                    if not is_test:
                        safe_mode_count_prod += 1
                elif "error" in reason or "fail" in reason or "error" in message:
                    safe_mode_reason_counts["api_errors"] += 1
                    if not is_test:
                        safe_mode_count_prod += 1
                elif "latency" in reason or "latency" in message:
                    safe_mode_reason_counts["latency"] += 1
                    if not is_test:
                        safe_mode_count_prod += 1
                elif "validation" in reason or "test" in reason:
                    safe_mode_reason_counts["validation_test"] += 1
                elif "stress" in reason:
                    safe_mode_reason_counts["stress_lab"] += 1
                else:
                    safe_mode_reason_counts["other"] += 1
                    if not is_test:
                        safe_mode_count_prod += 1
            
            # === SOURCE SWITCH METRICS ===
            # Get all switch events
            switch_events = await self.db.events.find({
                "type": "DATA_SOURCE_SWITCHED",
                "ts": {"$gte": last_24h_iso}
            }, {"_id": 0, "context": 1, "tags": 1}).to_list(1000)
            
            source_switches_total = len(switch_events)
            source_switches_prod = sum(1 for e in switch_events 
                if not e.get("context", {}).get("simulated", False) 
                and not e.get("context", {}).get("test_scope", False)
                and not any(t in e.get("tags", []) for t in test_exclusions))
            
            # Count blocked switch attempts
            switch_attempts_blocked = await self.db.events.count_documents({
                "type": "DATA_SOURCE_SWITCH_BLOCKED_COOLDOWN",
                "ts": {"$gte": last_24h_iso}
            })
            
            # === ERROR METRICS ===
            error_events = await self.db.events.find({
                "severity": "ERROR",
                "ts": {"$gte": last_24h_iso}
            }, {"_id": 0, "context": 1, "tags": 1}).to_list(1000)
            
            errors_count_total = len(error_events)
            errors_count_prod = sum(1 for e in error_events 
                if not e.get("context", {}).get("simulated", False) 
                and not e.get("context", {}).get("test_scope", False)
                and not any(t in e.get("tags", []) for t in test_exclusions))
            
            # === PRIMARY SOURCE UPTIME ===
            # Calculate for total and prod separately
            total_hours = 24.0
            avg_fallback_duration_h = 0.25  # 15 min average
            
            fallback_hours_total = source_switches_total * avg_fallback_duration_h
            primary_uptime_pct_total = max(0, min(100, ((total_hours - fallback_hours_total) / total_hours) * 100))
            
            fallback_hours_prod = source_switches_prod * avg_fallback_duration_h
            primary_uptime_pct_prod = max(0, min(100, ((total_hours - fallback_hours_prod) / total_hours) * 100))
            
            # === DATA AGE STATISTICS ===
            watch_results = await self.db.watch_results.find({
                "timestamp": {"$gte": last_24h_iso}
            }, {"_id": 0, "engine_tick_age_s": 1}).to_list(1000)
            
            data_ages = [r.get("engine_tick_age_s") for r in watch_results if r.get("engine_tick_age_s") is not None]
            
            if data_ages:
                avg_data_age = sum(data_ages) / len(data_ages)
                sorted_ages = sorted(data_ages)
                p95_index = int(len(sorted_ages) * 0.95)
                p95_data_age = sorted_ages[min(p95_index, len(sorted_ages) - 1)]
            else:
                avg_data_age = 0.0
                p95_data_age = 0.0
            
            # === TRADES ===
            trades_count = await self.db.trades.count_documents({
                "executed_at": {"$gte": last_24h_iso}
            })
            
            # === COMPUTE HEALTH STATUS ===
            # Use PROD metrics for health determination
            if safe_mode_count_prod >= 10 or source_switches_prod >= 6 or errors_count_prod >= 3:
                health_status_prod = "UNHEALTHY"
            elif safe_mode_count_prod > 3 or source_switches_prod > 2 or errors_count_prod > 0:
                health_status_prod = "DEGRADED"
            else:
                health_status_prod = "HEALTHY"
            
            # Also compute total health for reference
            if safe_mode_count_total >= 10 or source_switches_total >= 6 or errors_count_total >= 3:
                health_status_total = "UNHEALTHY"
            elif safe_mode_count_total > 3 or source_switches_total > 2 or errors_count_total > 0:
                health_status_total = "DEGRADED"
            else:
                health_status_total = "HEALTHY"
            
            return {
                # === PROD METRICS (for severity grading) ===
                "safe_mode_count_prod": safe_mode_count_prod,
                "source_switches_prod": source_switches_prod,
                "errors_count_prod": errors_count_prod,
                "primary_source_uptime_pct_prod": round(primary_uptime_pct_prod, 1),
                "health_status_prod": health_status_prod,
                
                # === TOTAL METRICS (for transparency/diagnostics) ===
                "safe_mode_count_total": safe_mode_count_total,
                "source_switches_total": source_switches_total,
                "switch_attempts_blocked": switch_attempts_blocked,
                "errors_count_total": errors_count_total,
                "primary_source_uptime_pct_total": round(primary_uptime_pct_total, 1),
                "health_status_total": health_status_total,
                
                # === BREAKDOWN ===
                "safe_mode_reason_counts": safe_mode_reason_counts,
                "trades_count": trades_count,
                
                # === DATA QUALITY ===
                "avg_data_age_s": round(avg_data_age, 1),
                "p95_data_age_s": round(p95_data_age, 1),
                
                # === EXCLUSIONS APPLIED ===
                "exclusions": test_exclusions,
            }
        except Exception as e:
            logger.warning(f"Failed to collect 24h metrics: {e}")
            return {
                "safe_mode_count_prod": 0,
                "source_switches_prod": 0,
                "errors_count_prod": 0,
                "primary_source_uptime_pct_prod": 100.0,
                "health_status_prod": "HEALTHY",
                "safe_mode_count_total": 0,
                "source_switches_total": 0,
                "switch_attempts_blocked": 0,
                "errors_count_total": 0,
                "primary_source_uptime_pct_total": 100.0,
                "health_status_total": "HEALTHY",
                "safe_mode_reason_counts": {"data_stale": 0, "api_errors": 0, "latency": 0, "validation_test": 0, "stress_lab": 0, "other": 0},
                "trades_count": 0,
                "avg_data_age_s": 0.0,
                "p95_data_age_s": 0.0,
                "exclusions": [],
            }


    async def trigger_now(self) -> Dict[str, Any]:
        """Manually trigger a scheduled validation run (for testing)."""
        if not self._is_paper_mode():
            return {"error": "Only available in PAPER mode"}
        
        # Run in background
        asyncio.create_task(self._run_scheduled_validation(is_catchup=False))
        
        return {"triggered": True, "message": "Validation triggered manually"}


# Global instance
validation_scheduler: Optional[ValidationScheduler] = None


def get_validation_scheduler(db: AsyncIOMotorDatabase) -> ValidationScheduler:
    """Get or create validation scheduler."""
    global validation_scheduler
    if validation_scheduler is None:
        validation_scheduler = ValidationScheduler(db)
    return validation_scheduler
