"""Event Logger - Centralized event tracking for the trading system."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)


class EventSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventCategory(str, Enum):
    ENGINE = "ENGINE"
    DATA = "DATA"
    RISK = "RISK"
    AGENT = "AGENT"
    ORDER = "ORDER"
    SYSTEM = "SYSTEM"
    NOTIFY = "NOTIFY"
    SECURITY = "SECURITY"
    GROWTH = "GROWTH"


# Standard event types for consistency
class EventType:
    # ENGINE
    ENGINE_STARTED = "ENGINE_STARTED"
    ENGINE_STOPPED = "ENGINE_STOPPED"
    ENGINE_TICK_OK = "ENGINE_TICK_OK"
    ENGINE_TICK_MISSED = "ENGINE_TICK_MISSED"
    ENGINE_RESTARTED = "ENGINE_RESTARTED"
    RECONCILE_STARTED = "RECONCILE_STARTED"
    RECONCILE_OK = "RECONCILE_OK"
    RECONCILE_FAILED = "RECONCILE_FAILED"
    
    # DATA
    DATA_SOURCE_SWITCHED = "DATA_SOURCE_SWITCHED"
    DATA_STALE_DETECTED = "DATA_STALE_DETECTED"
    DATA_RECOVERED = "DATA_RECOVERED"
    CANDLE_VALIDATION_FAILED = "CANDLE_VALIDATION_FAILED"
    RATE_LIMIT_HIT = "RATE_LIMIT_HIT"
    DATA_FETCH_ERROR = "DATA_FETCH_ERROR"
    
    # RISK
    SAFE_MODE_ENTERED = "SAFE_MODE_ENTERED"
    SAFE_MODE_EXITED = "SAFE_MODE_EXITED"
    KILL_SWITCH_ENABLED = "KILL_SWITCH_ENABLED"
    KILL_SWITCH_DISABLED = "KILL_SWITCH_DISABLED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    DAILY_LOSS_LIMIT_HIT = "DAILY_LOSS_LIMIT_HIT"
    DRAWDOWN_LIMIT_HIT = "DRAWDOWN_LIMIT_HIT"
    EXPOSURE_LIMIT_HIT = "EXPOSURE_LIMIT_HIT"
    
    # AGENT
    AGENT_ENABLED = "AGENT_ENABLED"
    AGENT_DISABLED = "AGENT_DISABLED"
    AGENT_COOLDOWN_STARTED = "AGENT_COOLDOWN_STARTED"
    AGENT_COOLDOWN_ENDED = "AGENT_COOLDOWN_ENDED"
    AGENT_SIGNAL_GENERATED = "AGENT_SIGNAL_GENERATED"
    AGENT_SIGNAL_SKIPPED = "AGENT_SIGNAL_SKIPPED"
    
    # ORDER / EXECUTION
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_CANCELED = "ORDER_CANCELED"
    IDEMPOTENCY_DUPLICATE_BLOCKED = "IDEMPOTENCY_DUPLICATE_BLOCKED"
    
    # NOTIFY
    TELEGRAM_SENT = "TELEGRAM_SENT"
    TELEGRAM_FAILED = "TELEGRAM_FAILED"
    
    # STRESS TEST
    STRESS_TEST_STARTED = "STRESS_TEST_STARTED"
    STRESS_TEST_COMPLETED = "STRESS_TEST_COMPLETED"
    STRESS_TEST_FAILED = "STRESS_TEST_FAILED"
    
    # TEST SCOPE - For filtering test vs production activity
    TEST_SCOPE_ACTIVE = "TEST_SCOPE_ACTIVE"
    TEST_SCOPE_ENDED = "TEST_SCOPE_ENDED"
    
    # DAILY OPERATIONS
    DAILY_SNAPSHOT_CREATED = "DAILY_SNAPSHOT_CREATED"
    DAILY_RESET_COMPLETED = "DAILY_RESET_COMPLETED"


class Event(BaseModel):
    """Event model for the timeline."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: EventSeverity
    category: EventCategory
    type: str
    message: str
    context: Dict[str, Any] = {}
    
    # Runtime tracking
    run_id: Optional[str] = None
    cycle_id: Optional[int] = None
    
    # Optional identifiers
    agent_id: Optional[str] = None
    symbol: Optional[str] = None
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    
    # Test scope tracking
    test_scope: Optional[str] = None  # Active test scope ID when event was emitted
    test_scope_type: Optional[str] = None  # Type: "validation", "stress_lab", etc.
    
    # Tags for filtering
    tags: List[str] = []


# Test scope types for categorization
class TestScopeType(str, Enum):
    VALIDATION = "validation"
    STRESS_LAB = "stress_lab"
    MANUAL_TEST = "manual_test"


class EventLogger:
    """
    Centralized event logging service.
    
    Usage:
        await event_logger.emit(
            severity=EventSeverity.WARNING,
            category=EventCategory.RISK,
            type=EventType.SAFE_MODE_ENTERED,
            message="Entered safe mode due to stale data",
            context={"reason": "data_stale", "data_age_s": 180}
        )
    """
    
    # Retention settings (days) by severity
    RETENTION_DEBUG_INFO = 30
    RETENTION_WARNING_ERROR = 60
    RETENTION_CRITICAL = 90
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._run_id: Optional[str] = None
        self._cycle_id: int = 0
        self._initialized = False
        self._current_correlation_id: Optional[str] = None
        
        # Test scope tracking
        self._active_test_scope: Optional[str] = None  # Scope ID
        self._active_test_scope_type: Optional[str] = None  # Type (validation, stress_lab)
        self._test_scope_started_at: Optional[datetime] = None
        
    async def initialize(self):
        """Initialize event logger and create indexes."""
        # Generate run_id for this runtime session
        self._run_id = str(uuid.uuid4())[:8]
        
        # Create indexes for fast queries
        try:
            await self.db.events.create_index([("severity", 1), ("ts", -1)])
            await self.db.events.create_index([("category", 1), ("ts", -1)])
            await self.db.events.create_index([("type", 1), ("ts", -1)])
            await self.db.events.create_index([("agent_id", 1), ("ts", -1)])
            await self.db.events.create_index([("symbol", 1), ("ts", -1)])
            await self.db.events.create_index("run_id")
            await self.db.events.create_index("correlation_id")
            await self.db.events.create_index("ts")
            await self.db.events.create_index("test_scope")  # For filtering test events
        except Exception as e:
            logger.warning(f"Failed to create event indexes: {e}")
        
        self._initialized = True
        logger.info(f"EventLogger initialized with run_id: {self._run_id}")
        
        # Log startup event
        await self.emit(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            type="SYSTEM_STARTED",
            message="Event logging system initialized",
            context={"run_id": self._run_id}
        )
    
    def set_cycle(self, cycle_id: int):
        """Update current cycle ID."""
        self._cycle_id = cycle_id
    
    def get_run_id(self) -> str:
        """Get current run ID."""
        return self._run_id or "unknown"
    
    # ============ Test Scope Management ============
    
    async def start_test_scope(
        self, 
        scope_type: str,
        scope_id: str = None,
        description: str = "",
        context: Dict[str, Any] = None
    ) -> str:
        """
        Start a test scope. All events emitted during this scope will be tagged.
        
        Args:
            scope_type: Type of test (validation, stress_lab, manual_test)
            scope_id: Optional custom ID, auto-generated if not provided
            description: Human-readable description of the test
            context: Additional context data
            
        Returns:
            The scope ID
        """
        scope_id = scope_id or str(uuid.uuid4())[:8]
        self._active_test_scope = scope_id
        self._active_test_scope_type = scope_type
        self._test_scope_started_at = datetime.now(timezone.utc)
        
        # Emit TEST_SCOPE_ACTIVE event
        await self.emit(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            type=EventType.TEST_SCOPE_ACTIVE,
            message=f"Test scope started: {scope_type} ({description or scope_id})",
            context={
                "scope_id": scope_id,
                "scope_type": scope_type,
                "description": description,
                "started_at": self._test_scope_started_at.isoformat(),
                **(context or {})
            },
            tags=["test_scope", scope_type, "test_start"]
        )
        
        logger.info(f"Test scope started: {scope_type} (id: {scope_id})")
        return scope_id
    
    async def end_test_scope(
        self, 
        result: str = "completed",
        summary: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        End the current test scope.
        
        Args:
            result: Outcome of the test (completed, failed, cancelled)
            summary: Summary data from the test
            
        Returns:
            Summary of the test scope
        """
        if not self._active_test_scope:
            logger.warning("end_test_scope called but no active scope")
            return {"error": "No active test scope"}
        
        scope_id = self._active_test_scope
        scope_type = self._active_test_scope_type
        started_at = self._test_scope_started_at
        ended_at = datetime.now(timezone.utc)
        duration_s = (ended_at - started_at).total_seconds() if started_at else 0
        
        # Emit TEST_SCOPE_ENDED event
        await self.emit(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            type=EventType.TEST_SCOPE_ENDED,
            message=f"Test scope ended: {scope_type} ({scope_id}) - {result}",
            context={
                "scope_id": scope_id,
                "scope_type": scope_type,
                "result": result,
                "duration_s": round(duration_s, 2),
                "started_at": started_at.isoformat() if started_at else None,
                "ended_at": ended_at.isoformat(),
                **(summary or {})
            },
            tags=["test_scope", scope_type, "test_end", result]
        )
        
        # Clear active scope
        scope_summary = {
            "scope_id": scope_id,
            "scope_type": scope_type,
            "result": result,
            "duration_s": round(duration_s, 2),
            "started_at": started_at.isoformat() if started_at else None,
            "ended_at": ended_at.isoformat(),
        }
        
        self._active_test_scope = None
        self._active_test_scope_type = None
        self._test_scope_started_at = None
        
        logger.info(f"Test scope ended: {scope_type} (id: {scope_id}, duration: {duration_s:.1f}s)")
        return scope_summary
    
    def is_test_scope_active(self) -> bool:
        """Check if a test scope is currently active."""
        return self._active_test_scope is not None
    
    def get_active_test_scope(self) -> Optional[Dict[str, Any]]:
        """Get current active test scope info."""
        if not self._active_test_scope:
            return None
        return {
            "scope_id": self._active_test_scope,
            "scope_type": self._active_test_scope_type,
            "started_at": self._test_scope_started_at.isoformat() if self._test_scope_started_at else None,
            "duration_s": (datetime.now(timezone.utc) - self._test_scope_started_at).total_seconds() if self._test_scope_started_at else 0,
        }
    
    # ============ Event Emission ============

    async def emit(
        self,
        severity: EventSeverity,
        category: EventCategory,
        type: str,
        message: str,
        context: Dict[str, Any] = None,
        agent_id: str = None,
        symbol: str = None,
        source: str = None,
        correlation_id: str = None,
        tags: List[str] = None,
    ) -> Event:
        """Emit an event to the timeline."""
        # Prepare context with test scope info if active
        ctx = context.copy() if context else {}
        event_tags = list(tags) if tags else []
        
        # Auto-tag events emitted during test scope
        test_scope_id = None
        test_scope_type = None
        if self._active_test_scope:
            test_scope_id = self._active_test_scope
            test_scope_type = self._active_test_scope_type
            # Add test_scope flag to context
            ctx["test_scope"] = True
            ctx["test_scope_id"] = test_scope_id
            ctx["test_scope_type"] = test_scope_type
            # Add tags for filtering
            if "test" not in event_tags:
                event_tags.append("test")
            if test_scope_type and test_scope_type not in event_tags:
                event_tags.append(test_scope_type)
        
        event = Event(
            severity=severity,
            category=category,
            type=type,
            message=message,
            context=ctx,
            run_id=self._run_id,
            cycle_id=self._cycle_id,
            agent_id=agent_id,
            symbol=symbol,
            source=source,
            correlation_id=correlation_id,
            test_scope=test_scope_id,
            test_scope_type=test_scope_type,
            tags=event_tags,
        )
        
        # Add severity tag automatically
        if severity in [EventSeverity.WARNING, EventSeverity.ERROR, EventSeverity.CRITICAL]:
            event.tags.append(severity.value.lower())
        
        # Log to Python logger as well
        log_level = {
            EventSeverity.DEBUG: logging.DEBUG,
            EventSeverity.INFO: logging.INFO,
            EventSeverity.WARNING: logging.WARNING,
            EventSeverity.ERROR: logging.ERROR,
            EventSeverity.CRITICAL: logging.CRITICAL,
        }.get(severity, logging.INFO)
        
        logger.log(log_level, f"[{category.value}] {type}: {message}")
        
        # Store in MongoDB
        try:
            doc = event.model_dump()
            doc["ts"] = doc["ts"].isoformat()
            await self.db.events.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to store event: {e}")
        
        return event
    
    # ============ Convenience Methods ============
    
    async def debug(self, category: EventCategory, type: str, message: str, **kwargs):
        """Emit DEBUG event."""
        return await self.emit(EventSeverity.DEBUG, category, type, message, **kwargs)
    
    async def info(self, category: EventCategory, type: str, message: str, **kwargs):
        """Emit INFO event."""
        return await self.emit(EventSeverity.INFO, category, type, message, **kwargs)
    
    async def warning(self, category: EventCategory, type: str, message: str, **kwargs):
        """Emit WARNING event."""
        return await self.emit(EventSeverity.WARNING, category, type, message, **kwargs)
    
    async def error(self, category: EventCategory, type: str, message: str, **kwargs):
        """Emit ERROR event."""
        return await self.emit(EventSeverity.ERROR, category, type, message, **kwargs)
    
    async def critical(self, category: EventCategory, type: str, message: str, **kwargs):
        """Emit CRITICAL event."""
        return await self.emit(EventSeverity.CRITICAL, category, type, message, **kwargs)
    
    # ============ Query Methods ============
    
    async def get_events(
        self,
        limit: int = 50,
        severity: str = None,
        category: str = None,
        type: str = None,
        from_ts: datetime = None,
        to_ts: datetime = None,
        agent_id: str = None,
        symbol: str = None,
        run_id: str = None,
    ) -> List[Dict[str, Any]]:
        """Query events with filters."""
        query = {}
        
        if severity:
            query["severity"] = severity
        if category:
            query["category"] = category
        if type:
            query["type"] = type
        if agent_id:
            query["agent_id"] = agent_id
        if symbol:
            query["symbol"] = symbol
        if run_id:
            query["run_id"] = run_id
        
        if from_ts or to_ts:
            query["ts"] = {}
            if from_ts:
                query["ts"]["$gte"] = from_ts.isoformat()
            if to_ts:
                query["ts"]["$lte"] = to_ts.isoformat()
        
        events = await self.db.events.find(
            query, {"_id": 0}
        ).sort("ts", -1).limit(limit).to_list(limit)
        
        return events
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get event summary with counts by severity."""
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_1h = now - timedelta(hours=1)
        
        # Count by severity (last 24h)
        pipeline = [
            {"$match": {"ts": {"$gte": last_24h.isoformat()}}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        severity_counts = {}
        async for doc in self.db.events.aggregate(pipeline):
            severity_counts[doc["_id"]] = doc["count"]
        
        # Count by category (last 24h)
        pipeline = [
            {"$match": {"ts": {"$gte": last_24h.isoformat()}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        ]
        category_counts = {}
        async for doc in self.db.events.aggregate(pipeline):
            category_counts[doc["_id"]] = doc["count"]
        
        # Recent critical events
        # Note: We intentionally hide default-credential events here because auth/login
        # is currently bypassed in this deployment.
        critical_events = await self.db.events.find(
            {
                "severity": "CRITICAL",
                "ts": {"$gte": last_24h.isoformat()},
                "type": {
                    "$nin": [
                        "SECURITY_DEFAULT_CREDENTIALS_DETECTED",
                        "SECURITY_DEFAULT_CREDENTIALS_REVOKED",
                    ]
                },
            },
            {"_id": 0}
        ).sort("ts", -1).limit(10).to_list(10)
        
        # Recent warnings (last hour)
        warnings_1h = await self.db.events.count_documents({
            "severity": "WARNING",
            "ts": {"$gte": last_1h.isoformat()}
        })
        
        # Total events
        total_24h = await self.db.events.count_documents({
            "ts": {"$gte": last_24h.isoformat()}
        })
        
        return {
            "total_24h": total_24h,
            "warnings_1h": warnings_1h,
            "by_severity": severity_counts,
            "by_category": category_counts,
            "recent_critical": critical_events,
            "current_run_id": self._run_id,
            "current_cycle": self._cycle_id,
        }
    
    async def get_event_types(self) -> List[str]:
        """Get all unique event types."""
        types = await self.db.events.distinct("type")
        return sorted(types)
    
    async def cleanup_old_events(self):
        """Manual cleanup of old events based on severity-based retention."""
        now = datetime.now(timezone.utc)
        
        # Delete DEBUG/INFO older than 30 days
        cutoff_debug_info = now - timedelta(days=self.RETENTION_DEBUG_INFO)
        result1 = await self.db.events.delete_many({
            "ts": {"$lt": cutoff_debug_info.isoformat()},
            "severity": {"$in": ["DEBUG", "INFO"]}
        })
        
        # Delete WARNING/ERROR older than 60 days
        cutoff_warn_error = now - timedelta(days=self.RETENTION_WARNING_ERROR)
        result2 = await self.db.events.delete_many({
            "ts": {"$lt": cutoff_warn_error.isoformat()},
            "severity": {"$in": ["WARNING", "ERROR"]}
        })
        
        # Delete CRITICAL older than 90 days
        cutoff_critical = now - timedelta(days=self.RETENTION_CRITICAL)
        result3 = await self.db.events.delete_many({
            "ts": {"$lt": cutoff_critical.isoformat()},
            "severity": "CRITICAL"
        })
        
        total_deleted = result1.deleted_count + result2.deleted_count + result3.deleted_count
        logger.info(f"Cleaned up {total_deleted} old events (DEBUG/INFO: {result1.deleted_count}, WARN/ERROR: {result2.deleted_count}, CRITICAL: {result3.deleted_count})")
        return total_deleted
    
    # ============ Correlation Chain Methods ============
    
    def start_correlation_chain(self, chain_id: str = None) -> str:
        """Start a new correlation chain for related events."""
        self._current_correlation_id = chain_id or str(uuid.uuid4())[:12]
        return self._current_correlation_id
    
    def end_correlation_chain(self):
        """End the current correlation chain."""
        self._current_correlation_id = None
    
    async def get_correlation_chain(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Get all events in a correlation chain."""
        events = await self.db.events.find(
            {"correlation_id": correlation_id},
            {"_id": 0}
        ).sort("ts", 1).to_list(1000)
        return events
    
    async def emit_chained(
        self,
        severity: EventSeverity,
        category: EventCategory,
        type: str,
        message: str,
        **kwargs
    ) -> Event:
        """Emit an event with automatic correlation_id from current chain."""
        if self._current_correlation_id and "correlation_id" not in kwargs:
            kwargs["correlation_id"] = self._current_correlation_id
        return await self.emit(severity, category, type, message, **kwargs)
    
    # ============ Daily Snapshot ============
    
    async def create_daily_snapshot(
        self,
        equity: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        daily_drawdown: float,
        daily_drawdown_pct: float,
        trades_count: int,
        positions_count: int,
        safe_mode_count: int = 0,
    ) -> Event:
        """Create a daily snapshot event for operational history."""
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        
        # Count WARNING and CRITICAL events in last 24h
        warnings_count = await self.db.events.count_documents({
            "severity": "WARNING",
            "ts": {"$gte": last_24h.isoformat()}
        })
        
        critical_count = await self.db.events.count_documents({
            "severity": "CRITICAL",
            "ts": {"$gte": last_24h.isoformat()}
        })
        
        errors_count = await self.db.events.count_documents({
            "severity": "ERROR",
            "ts": {"$gte": last_24h.isoformat()}
        })
        
        return await self.emit(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            type=EventType.DAILY_SNAPSHOT_CREATED,
            message=f"Daily snapshot: Equity ${equity:.2f}, PnL ${daily_pnl:.2f} ({daily_pnl_pct:.2f}%)",
            context={
                "equity": equity,
                "daily_pnl": daily_pnl,
                "daily_pnl_pct": daily_pnl_pct,
                "daily_drawdown": daily_drawdown,
                "daily_drawdown_pct": daily_drawdown_pct,
                "trades_count": trades_count,
                "positions_count": positions_count,
                "warnings_24h": warnings_count,
                "errors_24h": errors_count,
                "critical_24h": critical_count,
                "safe_mode_count": safe_mode_count,
                "snapshot_date": now.strftime("%Y-%m-%d"),
            },
            tags=["daily", "snapshot", "operational"]
        )
    
    async def get_daily_snapshots(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get daily snapshot events."""
        return await self.get_events(
            limit=limit,
            type=EventType.DAILY_SNAPSHOT_CREATED
        )


# Global event logger instance
event_logger: Optional[EventLogger] = None


async def get_event_logger(db: AsyncIOMotorDatabase = None) -> EventLogger:
    """Get or create event logger instance."""
    global event_logger
    if event_logger is None and db is not None:
        event_logger = EventLogger(db)
        await event_logger.initialize()
    return event_logger
