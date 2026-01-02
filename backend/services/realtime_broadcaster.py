"""
Real-Time Data Broadcaster for HAVEN (P3.1)
============================================

🔔 PUSH-BASED real-time updates for:
- Guardian state changes
- Execution events
- PnL updates
- Order state changes
- Risk alerts
- System status

⚡ Design:
- Zero impact on executor latency (async, non-blocking)
- Side-channel only (read from services, never write)
- Full audit trail (all events logged)

Usage:
    broadcaster = RealTimeBroadcaster(db, ws_manager)
    await broadcaster.start()
    
    # Events are automatically pushed when services update
    # Or manually trigger:
    await broadcaster.broadcast_risk_alert(...)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of real-time events."""
    # Guardian
    GUARDIAN_STATE = "guardian_state"
    GUARDIAN_ALERT = "guardian_alert"
    KILL_SWITCH = "kill_switch"
    
    # Execution
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_BLOCKED = "execution_blocked"
    
    # Orders
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    
    # PnL
    PNL_UPDATE = "pnl_update"
    DRAWDOWN_ALERT = "drawdown_alert"
    
    # System
    MODE_CHANGE = "mode_change"
    DATA_SOURCE_CHANGE = "data_source_change"
    CIRCUIT_BREAKER = "circuit_breaker"
    
    # GO-LIVE Gate
    GATE_STATUS_CHANGE = "gate_status_change"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class RealTimeEvent:
    """Real-time event structure."""
    event_type: EventType
    severity: AlertSeverity
    title: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_ws_message(self) -> Dict[str, Any]:
        """Convert to WebSocket message format."""
        return {
            "type": "event",
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class RealTimeBroadcaster:
    """
    Broadcasts real-time events to connected WebSocket clients.
    
    Features:
    - Non-blocking async broadcast
    - Event batching for efficiency
    - Event history for late joiners
    - Audit logging
    """
    
    def __init__(self, db=None, ws_manager=None):
        self.db = db
        self.ws_manager = ws_manager
        
        # Event history (last N events for late joiners)
        self._event_history: List[RealTimeEvent] = []
        self._max_history = 50
        
        # Background task
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        
        # State tracking for change detection
        self._last_guardian_state: Optional[Dict] = None
        self._last_pnl: Optional[Dict] = None
        self._last_gate_status: Optional[str] = None
        
        # Services (set externally)
        self.guardian_service = None
        self.go_live_gate = None
        self.live_executor = None
        self.paper_adapter = None
        
        # Callbacks for custom event sources
        self._event_callbacks: List[Callable] = []
        
        logger.info("RealTimeBroadcaster initialized")
    
    async def start(self, poll_interval: float = 2.0):
        """Start background polling for state changes."""
        if self._running:
            return
        
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(poll_interval))
        logger.info(f"RealTimeBroadcaster started (poll interval: {poll_interval}s)")
    
    async def stop(self):
        """Stop the broadcaster."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("RealTimeBroadcaster stopped")
    
    async def _poll_loop(self, interval: float):
        """Background loop to check for state changes."""
        while self._running:
            try:
                await self._check_guardian_changes()
                await self._check_pnl_changes()
                await self._check_gate_changes()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(interval)
    
    # ============================================================
    # 📊 STATE CHANGE DETECTION
    # ============================================================
    
    async def _check_guardian_changes(self):
        """Check for Guardian state changes and broadcast."""
        if not self.guardian_service:
            return
        
        try:
            state = self.guardian_service.get_status()
            
            if self._last_guardian_state is None:
                self._last_guardian_state = state
                await self._broadcast_guardian_state(state)
                return
            
            # Check for significant changes
            changes = []
            
            # Kill switch change
            old_kill = self._last_guardian_state.get("kill_switch_active", False)
            new_kill = state.get("kill_switch_active", False)
            if old_kill != new_kill:
                changes.append("kill_switch")
                if new_kill:
                    await self.broadcast_event(RealTimeEvent(
                        event_type=EventType.KILL_SWITCH,
                        severity=AlertSeverity.CRITICAL,
                        title="⛔ KILL SWITCH ACTIVATED",
                        message="All trading has been halted to protect capital.",
                        data={"reason": state.get("block_reason", "Risk limit exceeded")},
                    ))
            
            # Drawdown approaching limit
            old_dd = self._last_guardian_state.get("weekly_drawdown_pct", 0)
            new_dd = state.get("weekly_drawdown_pct", 0)
            limit = state.get("weekly_drawdown_limit_pct", -5)
            
            if new_dd < limit * 0.7 and old_dd >= limit * 0.7:
                await self.broadcast_event(RealTimeEvent(
                    event_type=EventType.DRAWDOWN_ALERT,
                    severity=AlertSeverity.WARNING,
                    title="⚠️ Drawdown Alert",
                    message=f"Weekly drawdown at {new_dd:.1f}% (limit: {limit}%)",
                    data={"drawdown_pct": new_dd, "limit_pct": limit},
                ))
            
            # Any change triggers state update
            if state != self._last_guardian_state:
                await self._broadcast_guardian_state(state)
            
            self._last_guardian_state = state
            
        except Exception as e:
            logger.warning(f"Guardian state check failed: {e}")
    
    async def _check_pnl_changes(self):
        """Check for PnL changes and broadcast."""
        if not self.paper_adapter:
            return
        
        try:
            pnl = self.paper_adapter.get_pnl_summary() if hasattr(self.paper_adapter, 'get_pnl_summary') else None
            
            if pnl and pnl != self._last_pnl:
                await self._broadcast_pnl(pnl)
                self._last_pnl = pnl
                
        except Exception as e:
            logger.warning(f"PnL check failed: {e}")
    
    async def _check_gate_changes(self):
        """Check for GO-LIVE gate status changes."""
        if not self.go_live_gate:
            return
        
        try:
            status = await self.go_live_gate.get_current_status()
            decision = status.get("decision", "NO_GO")
            
            if self._last_gate_status and decision != self._last_gate_status:
                await self.broadcast_event(RealTimeEvent(
                    event_type=EventType.GATE_STATUS_CHANGE,
                    severity=AlertSeverity.WARNING if decision == "NO_GO" else AlertSeverity.INFO,
                    title=f"GO-LIVE Gate: {decision}",
                    message=f"Gate status changed from {self._last_gate_status} to {decision}",
                    data=status,
                ))
            
            self._last_gate_status = decision
            
        except Exception as e:
            logger.warning(f"Gate status check failed: {e}")
    
    # ============================================================
    # 📤 BROADCAST METHODS
    # ============================================================
    
    async def _broadcast_guardian_state(self, state: Dict[str, Any]):
        """Broadcast Guardian state update."""
        if self.ws_manager:
            from services.growth.websocket_manager import notify_guardian_change
            await notify_guardian_change(state)
    
    async def _broadcast_pnl(self, pnl: Dict[str, Any]):
        """Broadcast PnL update."""
        if self.ws_manager:
            from services.growth.websocket_manager import notify_pnl_change
            await notify_pnl_change(pnl)
    
    async def broadcast_event(self, event: RealTimeEvent):
        """Broadcast a real-time event to all clients."""
        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Broadcast via WebSocket
        if self.ws_manager:
            from services.growth.websocket_manager import GrowthWSMessage
            message = GrowthWSMessage(
                type="event",
                data=event.to_ws_message(),
            )
            await self.ws_manager.broadcast(message)
        
        # Log to audit
        if self.db:
            try:
                await self.db.realtime_events.insert_one({
                    "event_type": event.event_type.value,
                    "severity": event.severity.value,
                    "title": event.title,
                    "message": event.message,
                    "data": event.data,
                    "timestamp": datetime.now(timezone.utc),
                })
            except Exception as e:
                logger.warning(f"Failed to log event to DB: {e}")
        
        logger.info(f"[{event.severity.value.upper()}] {event.title}: {event.message}")
    
    # ============================================================
    # 🎯 PUBLIC EVENT METHODS
    # ============================================================
    
    async def broadcast_execution_start(self, execution_id: str, mode: str, symbol: str):
        """Broadcast execution start event."""
        await self.broadcast_event(RealTimeEvent(
            event_type=EventType.EXECUTION_START,
            severity=AlertSeverity.INFO,
            title="⚡ Execution Started",
            message=f"Running {mode} execution on {symbol}",
            data={"execution_id": execution_id, "mode": mode, "symbol": symbol},
        ))
    
    async def broadcast_execution_complete(
        self, 
        execution_id: str, 
        success: bool, 
        orders_created: int,
        pnl_delta: float
    ):
        """Broadcast execution complete event."""
        await self.broadcast_event(RealTimeEvent(
            event_type=EventType.EXECUTION_COMPLETE,
            severity=AlertSeverity.INFO if success else AlertSeverity.WARNING,
            title="✅ Execution Complete" if success else "⚠️ Execution Failed",
            message=f"{orders_created} orders created, PnL: {pnl_delta:+.2f} EUR",
            data={
                "execution_id": execution_id, 
                "success": success, 
                "orders_created": orders_created,
                "pnl_delta": pnl_delta,
            },
        ))
    
    async def broadcast_execution_blocked(self, reason: str, user_id: str):
        """Broadcast execution blocked event."""
        await self.broadcast_event(RealTimeEvent(
            event_type=EventType.EXECUTION_BLOCKED,
            severity=AlertSeverity.WARNING,
            title="🛑 Execution Blocked",
            message=reason,
            data={"reason": reason, "user_id": user_id},
        ))
    
    async def broadcast_mode_change(self, old_mode: str, new_mode: str, user_id: str):
        """Broadcast execution mode change."""
        severity = AlertSeverity.CRITICAL if new_mode == "live" else AlertSeverity.INFO
        await self.broadcast_event(RealTimeEvent(
            event_type=EventType.MODE_CHANGE,
            severity=severity,
            title=f"🔄 Mode Changed to {new_mode.upper()}",
            message=f"Execution mode changed from {old_mode} to {new_mode} by {user_id}",
            data={"old_mode": old_mode, "new_mode": new_mode, "user_id": user_id},
        ))
    
    async def broadcast_circuit_breaker(self, tripped: bool, reason: str = ""):
        """Broadcast circuit breaker event."""
        if tripped:
            await self.broadcast_event(RealTimeEvent(
                event_type=EventType.CIRCUIT_BREAKER,
                severity=AlertSeverity.CRITICAL,
                title="🔴 Circuit Breaker Tripped",
                message=f"Execution halted: {reason}",
                data={"tripped": True, "reason": reason},
            ))
        else:
            await self.broadcast_event(RealTimeEvent(
                event_type=EventType.CIRCUIT_BREAKER,
                severity=AlertSeverity.INFO,
                title="🟢 Circuit Breaker Reset",
                message="Circuit breaker has reset, execution can resume",
                data={"tripped": False},
            ))
    
    async def broadcast_risk_alert(
        self, 
        alert_type: str, 
        message: str, 
        severity: AlertSeverity = AlertSeverity.WARNING,
        data: Dict[str, Any] = None
    ):
        """Broadcast a generic risk alert."""
        await self.broadcast_event(RealTimeEvent(
            event_type=EventType.GUARDIAN_ALERT,
            severity=severity,
            title=f"⚠️ Risk Alert: {alert_type}",
            message=message,
            data=data or {},
        ))
    
    # ============================================================
    # 📜 HISTORY
    # ============================================================
    
    def get_recent_events(self, count: int = 20, event_type: Optional[EventType] = None) -> List[Dict]:
        """Get recent events for late-joining clients."""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_ws_message() for e in events[-count:]]
    
    def get_status(self) -> Dict[str, Any]:
        """Get broadcaster status."""
        return {
            "running": self._running,
            "events_in_history": len(self._event_history),
            "ws_connections": self.ws_manager.get_connection_count() if self.ws_manager else 0,
            "services_connected": {
                "guardian": self.guardian_service is not None,
                "go_live_gate": self.go_live_gate is not None,
                "live_executor": self.live_executor is not None,
                "paper_adapter": self.paper_adapter is not None,
            },
        }


# ============================================================
# 🏭 FACTORY
# ============================================================

_broadcaster: Optional[RealTimeBroadcaster] = None


def get_broadcaster() -> Optional[RealTimeBroadcaster]:
    """Get global broadcaster instance."""
    return _broadcaster


def set_broadcaster(broadcaster: RealTimeBroadcaster):
    """Set global broadcaster instance."""
    global _broadcaster
    _broadcaster = broadcaster


async def init_broadcaster(db=None, ws_manager=None, **services) -> RealTimeBroadcaster:
    """Initialize and start the global broadcaster."""
    global _broadcaster
    
    _broadcaster = RealTimeBroadcaster(db=db, ws_manager=ws_manager)
    
    # Attach services
    _broadcaster.guardian_service = services.get("guardian_service")
    _broadcaster.go_live_gate = services.get("go_live_gate")
    _broadcaster.live_executor = services.get("live_executor")
    _broadcaster.paper_adapter = services.get("paper_adapter")
    
    await _broadcaster.start()
    return _broadcaster
