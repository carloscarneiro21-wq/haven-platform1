"""Monitoring Panel - Real-time system health monitoring."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HealthState(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    HALTED = "HALTED"
    SAFE = "SAFE"
    WARN = "WARN"
    HALT = "HALT"
    # Never return UNKNOWN - use OFFLINE instead
    OFFLINE = "OFFLINE"


class MonitoringStatus(BaseModel):
    """Complete monitoring status."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Engine status
    engine_running: bool = False
    engine_last_tick_at: Optional[datetime] = None
    engine_tick_age_seconds: float = 0.0
    engine_healthy: bool = True
    
    # Data status
    data_source: str = "unknown"
    data_freshness_seconds: float = 0.0
    data_stale: bool = False
    
    # Positions
    open_positions_count: int = 0
    total_exposure: float = 0.0
    
    # P&L
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    daily_drawdown: float = 0.0
    daily_drawdown_pct: float = 0.0
    
    # Risk
    risk_state: HealthState = HealthState.OK
    kill_switch_active: bool = False
    safe_mode: bool = False
    safe_mode_reason: str = ""
    consecutive_losses: int = 0
    
    # Agents
    agents_total: int = 0
    agents_running: int = 0
    agents_in_error: int = 0
    
    # Alerts
    alerts_last_sent_at: Optional[datetime] = None
    alerts_sent_today: int = 0
    
    # Data Feed Health (detailed)
    data_feed_health: Dict[str, Any] = {}
    
    # Cycles
    cycle_count: int = 0
    error_count: int = 0
    recovery_attempts: int = 0
    
    # Watchdog
    watchdog_status: str = "healthy"
    watchdog_warnings: List[str] = []


class MonitoringPanel:
    """Real-time monitoring panel for 24/7 operation."""
    
    # Thresholds
    TICK_STALE_MULTIPLIER = 2.0  # Mark unhealthy if tick > 2x cycle interval
    DATA_STALE_THRESHOLD = 180  # 3 minutes
    MAX_CONSECUTIVE_ERRORS = 5
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.runtime = None
        self._last_status: Optional[MonitoringStatus] = None
        
    def set_runtime(self, runtime):
        """Set runtime reference."""
        self.runtime = runtime
    
    async def get_status(self) -> MonitoringStatus:
        """Get complete monitoring status."""
        status = MonitoringStatus()
        
        now = datetime.now(timezone.utc)
        
        try:
            # Engine status
            if self.runtime:
                status.engine_running = self.runtime._running
                status.engine_last_tick_at = self.runtime._last_cycle
                status.cycle_count = self.runtime._cycle_count
                status.error_count = self.runtime._error_count
                status.recovery_attempts = self.runtime._recovery_attempts
                status.safe_mode = self.runtime._safe_mode
                status.safe_mode_reason = self.runtime._safe_mode_reason
                
                if status.engine_last_tick_at:
                    status.engine_tick_age_seconds = (now - status.engine_last_tick_at).total_seconds()
                    
                    # Check if engine tick is stale
                    expected_interval = self.runtime._interval * self.TICK_STALE_MULTIPLIER
                    status.engine_healthy = status.engine_tick_age_seconds < expected_interval
                
                # Data feed status
                if self.runtime.data_feed:
                    try:
                        df_status = self.runtime.data_feed.get_status()
                        status.data_source = df_status.get("active_source", "unknown")
                        status.data_stale = df_status.get("safe_mode", False)
                        
                        # Include full health status with anti-flapping info
                        if hasattr(self.runtime.data_feed, 'health'):
                            status.data_feed_health = self.runtime.data_feed.health.get_status()
                        
                        # Calculate data freshness - use cache stats as fallback
                        cache_stats = df_status.get("cache_stats", {})
                        if cache_stats.get("tickers", 0) > 0:
                            status.data_freshness_seconds = 0  # Data is fresh
                        else:
                            status.data_freshness_seconds = 999  # No recent data
                    except Exception as df_err:
                        logger.debug(f"Data feed status error: {df_err}")
                        status.data_source = "offline"
                        status.data_stale = True
            
            # Positions
            positions = await self.db.positions.find({"is_open": True}, {"_id": 0}).to_list(100)
            status.open_positions_count = len(positions)
            status.total_exposure = sum(p.get("amount", 0) * p.get("current_price", 0) for p in positions)
            
            # Risk settings
            risk = await self.db.risk_settings.find_one({}, {"_id": 0})
            if risk:
                status.daily_pnl = risk.get("current_daily_pnl", 0)
                status.kill_switch_active = risk.get("kill_switch_active", False)
                status.consecutive_losses = risk.get("consecutive_losses", 0)
                status.daily_drawdown_pct = risk.get("current_drawdown_pct", 0)
                
                peak_equity = risk.get("peak_equity", 10000)
                if peak_equity > 0:
                    status.daily_pnl_pct = (status.daily_pnl / peak_equity) * 100
                    status.daily_drawdown = status.daily_drawdown_pct * peak_equity / 100
            
            # Determine risk state
            status.risk_state = self._determine_risk_state(status)
            
            # Agents
            if self.runtime and self.runtime.orchestrator:
                agents = self.runtime.orchestrator.get_all_agent_statuses()
                status.agents_total = len(agents)
                status.agents_running = len([a for a in agents if a.get("status") == "running"])
                status.agents_in_error = len([a for a in agents if a.get("status") == "error"])
            
            # Alerts
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            alerts_today = await self.db.notification_logs.count_documents({
                "timestamp": {"$gte": today_start.isoformat()}
            })
            status.alerts_sent_today = alerts_today
            
            last_alert = await self.db.notification_logs.find_one(
                {}, {"_id": 0, "timestamp": 1}
            , sort=[("timestamp", -1)])
            if last_alert and last_alert.get("timestamp"):
                status.alerts_last_sent_at = datetime.fromisoformat(last_alert["timestamp"])
            
            # Run watchdog checks
            status.watchdog_status, status.watchdog_warnings = await self._run_watchdog_checks(status)
            
            # Cache status
            self._last_status = status
            
            # Save to DB for external monitoring
            await self._save_status(status)
            
        except Exception as e:
            logger.error(f"Failed to get monitoring status: {e}")
            status.watchdog_warnings.append(f"Monitoring error: {str(e)}")
        
        return status
    
    def _determine_risk_state(self, status: MonitoringStatus) -> HealthState:
        """Determine overall risk state."""
        if status.kill_switch_active:
            return HealthState.HALTED
        
        if status.safe_mode or status.data_stale:
            return HealthState.WARNING
        
        if not status.engine_healthy:
            return HealthState.WARNING
        
        if status.consecutive_losses >= 3:
            return HealthState.WARNING
        
        if status.agents_in_error > 0:
            return HealthState.WARNING
        
        return HealthState.OK
    
    async def _run_watchdog_checks(self, status: MonitoringStatus) -> tuple[str, List[str]]:
        """Run watchdog checks and return status + warnings."""
        warnings = []
        overall_status = "healthy"
        
        # Check engine tick freshness
        if status.engine_running and status.engine_last_tick_at:
            if status.engine_tick_age_seconds > (self.runtime._interval * self.TICK_STALE_MULTIPLIER if self.runtime else 120):
                warnings.append(f"Engine tick stale: {status.engine_tick_age_seconds:.0f}s since last cycle")
                overall_status = "degraded"
        
        # Check data freshness
        if status.data_freshness_seconds > self.DATA_STALE_THRESHOLD:
            warnings.append(f"Data stale: {status.data_freshness_seconds:.0f}s since last update")
            overall_status = "degraded"
            
            # Trigger safe mode if not already
            if self.runtime and not self.runtime._safe_mode:
                self.runtime._safe_mode = True
                self.runtime._safe_mode_reason = "Watchdog: data stale"
                warnings.append("SAFE MODE activated by watchdog")
        
        # Check error count
        if status.error_count >= self.MAX_CONSECUTIVE_ERRORS:
            warnings.append(f"High error count: {status.error_count} consecutive errors")
            overall_status = "unhealthy"
        
        # Check recovery attempts
        if status.recovery_attempts > 0:
            warnings.append(f"Recovery in progress: attempt {status.recovery_attempts}")
            overall_status = "recovering"
        
        # Check kill switch
        if status.kill_switch_active:
            warnings.append("Kill switch is ACTIVE - all trading halted")
            overall_status = "halted"
        
        # Check agents
        if status.agents_in_error > 0:
            warnings.append(f"{status.agents_in_error} agent(s) in error state")
        
        return overall_status, warnings
    
    async def _save_status(self, status: MonitoringStatus):
        """Save monitoring status to database."""
        doc = status.model_dump()
        doc["timestamp"] = doc["timestamp"].isoformat()
        if doc.get("engine_last_tick_at"):
            doc["engine_last_tick_at"] = doc["engine_last_tick_at"].isoformat()
        if doc.get("alerts_last_sent_at"):
            doc["alerts_last_sent_at"] = doc["alerts_last_sent_at"].isoformat()
        
        await self.db.monitoring_status.replace_one({}, doc, upsert=True)
    
    async def get_status_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical monitoring data."""
        docs = await self.db.monitoring_history.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return docs
    
    async def trigger_safe_mode(self, reason: str):
        """Manually trigger safe mode."""
        if self.runtime:
            self.runtime._safe_mode = True
            self.runtime._safe_mode_reason = reason
            logger.warning(f"Safe mode triggered: {reason}")
            
            # Send notification
            if self.runtime.notifications and self.runtime.notifications.config.enabled:
                await self.runtime.notifications.notify_safe_mode_entered(reason)
    
    async def exit_safe_mode(self):
        """Exit safe mode."""
        if self.runtime:
            self.runtime._safe_mode = False
            self.runtime._safe_mode_reason = ""
            
            if self.runtime.data_feed:
                self.runtime.data_feed.safe_mode = False
                self.runtime.data_feed.safe_mode_reason = ""
            
            logger.info("Safe mode exited")
