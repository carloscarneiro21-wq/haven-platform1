"""
Stress Sandbox - Fault Injector
===============================
Coordinates infrastructure fault injection during sandbox runs.

Handles:
- WebSocket drops and reconnections
- API latency injection
- Rate limit simulation
- Stale data conditions
- Order acknowledgment delays
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
from pydantic import BaseModel, Field
from enum import Enum
import logging

from services.sandbox.scenario_engine import ScenarioEvent, ScenarioEventType

logger = logging.getLogger(__name__)


# ============ Models ============

class FaultState(BaseModel):
    """Current fault injection state."""
    ws_connected: bool = True
    ws_drop_count: int = 0
    ws_total_downtime_sec: float = 0
    
    api_latency_ms: int = 0
    api_latency_active: bool = False
    
    rate_limited: bool = False
    rate_limit_429_count: int = 0
    
    stale_data: bool = False
    stale_lag_sec: int = 0
    
    order_ack_delay_ms: int = 0
    order_ack_delay_active: bool = False


class FaultEvent(BaseModel):
    """Record of a fault event."""
    timestamp: datetime
    fault_type: str
    params: Dict[str, Any]
    duration_sec: int
    

# ============ Fault Injector ============

class FaultInjector:
    """
    Manages infrastructure fault injection during sandbox runs.
    
    Coordinates timing of faults and tracks statistics.
    """
    
    def __init__(self, seed: int):
        import random
        self._rng = random.Random(seed)
        
        # Current state
        self._state = FaultState()
        
        # Active faults with end times
        self._active_faults: Dict[str, datetime] = {}
        
        # Event history
        self._fault_history: List[FaultEvent] = []
        
        # Callbacks
        self._on_ws_drop: Optional[Callable] = None
        self._on_ws_reconnect: Optional[Callable] = None
        
        # Simulation time reference
        self._sim_time: Optional[datetime] = None
        
    def set_sim_time(self, sim_time: datetime):
        """Update simulation time reference."""
        self._sim_time = sim_time
        self._cleanup_expired_faults()
        
    def _cleanup_expired_faults(self):
        """Clean up expired faults."""
        if not self._sim_time:
            return
            
        expired = []
        for fault_key, end_time in self._active_faults.items():
            if self._sim_time >= end_time:
                expired.append(fault_key)
        
        for fault_key in expired:
            self._end_fault(fault_key)
            del self._active_faults[fault_key]
            
    def _end_fault(self, fault_key: str):
        """End a specific fault and reset state."""
        if fault_key == "ws_drop":
            if not self._state.ws_connected:
                self._state.ws_connected = True
                logger.debug("WS reconnected")
                if self._on_ws_reconnect:
                    self._on_ws_reconnect()
                    
        elif fault_key == "api_latency":
            self._state.api_latency_active = False
            self._state.api_latency_ms = 0
            
        elif fault_key == "rate_limit":
            self._state.rate_limited = False
            
        elif fault_key == "stale_data":
            self._state.stale_data = False
            self._state.stale_lag_sec = 0
            
        elif fault_key == "order_ack_delay":
            self._state.order_ack_delay_active = False
            self._state.order_ack_delay_ms = 0
    
    def inject_event(self, event: ScenarioEvent, start_time: datetime):
        """Inject a fault event from the scenario timeline."""
        end_time = start_time + timedelta(seconds=event.duration_sec)
        
        if event.event_type == ScenarioEventType.WS_DROP:
            self._inject_ws_drop(event, end_time)
            
        elif event.event_type == ScenarioEventType.API_LATENCY:
            self._inject_api_latency(event, end_time)
            
        elif event.event_type == ScenarioEventType.RATE_LIMIT_429:
            self._inject_rate_limit(event, end_time)
            
        elif event.event_type == ScenarioEventType.STALE_DATA:
            self._inject_stale_data(event, end_time)
            
        elif event.event_type == ScenarioEventType.ORDER_ACK_DELAY:
            self._inject_order_ack_delay(event, end_time)
            
        # Record event
        self._fault_history.append(FaultEvent(
            timestamp=start_time,
            fault_type=event.event_type.value,
            params=event.params,
            duration_sec=event.duration_sec,
        ))
    
    def _inject_ws_drop(self, event: ScenarioEvent, end_time: datetime):
        """Inject WebSocket drop."""
        self._state.ws_connected = False
        self._state.ws_drop_count += 1
        self._state.ws_total_downtime_sec += event.params.get("drop_duration_sec", 30)
        self._active_faults["ws_drop"] = end_time
        
        logger.debug(f"WS drop injected for {event.params.get('drop_duration_sec', 30)}s")
        
        if self._on_ws_drop:
            self._on_ws_drop()
    
    def _inject_api_latency(self, event: ScenarioEvent, end_time: datetime):
        """Inject API latency."""
        self._state.api_latency_active = True
        self._state.api_latency_ms = event.params.get("latency_ms", 500)
        self._active_faults["api_latency"] = end_time
        
        logger.debug(f"API latency injected: {self._state.api_latency_ms}ms")
    
    def _inject_rate_limit(self, event: ScenarioEvent, end_time: datetime):
        """Inject rate limiting."""
        self._state.rate_limited = True
        self._state.rate_limit_429_count += 1
        self._active_faults["rate_limit"] = end_time
        
        logger.debug("Rate limit (429) injected")
    
    def _inject_stale_data(self, event: ScenarioEvent, end_time: datetime):
        """Inject stale data condition."""
        self._state.stale_data = True
        self._state.stale_lag_sec = event.params.get("stale_lag_sec", 10)
        self._active_faults["stale_data"] = end_time
        
        logger.debug(f"Stale data injected: {self._state.stale_lag_sec}s lag")
    
    def _inject_order_ack_delay(self, event: ScenarioEvent, end_time: datetime):
        """Inject order acknowledgment delay."""
        self._state.order_ack_delay_active = True
        self._state.order_ack_delay_ms = event.params.get("ack_delay_ms", 1000)
        self._active_faults["order_ack_delay"] = end_time
        
        logger.debug(f"Order ACK delay injected: {self._state.order_ack_delay_ms}ms")
    
    def get_state(self) -> FaultState:
        """Get current fault state."""
        return self._state.model_copy()
    
    def is_ws_connected(self) -> bool:
        """Check if WS is connected."""
        return self._state.ws_connected
    
    def get_api_latency(self) -> int:
        """Get current API latency in ms."""
        return self._state.api_latency_ms if self._state.api_latency_active else 0
    
    def is_rate_limited(self) -> bool:
        """Check if currently rate limited."""
        return self._state.rate_limited
    
    def is_data_stale(self) -> bool:
        """Check if data is stale."""
        return self._state.stale_data
    
    def get_order_ack_delay(self) -> int:
        """Get order acknowledgment delay in ms."""
        return self._state.order_ack_delay_ms if self._state.order_ack_delay_active else 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fault injection statistics."""
        return {
            "ws_drop_count": self._state.ws_drop_count,
            "ws_total_downtime_sec": self._state.ws_total_downtime_sec,
            "rate_limit_429_count": self._state.rate_limit_429_count,
            "total_faults": len(self._fault_history),
            "active_faults": list(self._active_faults.keys()),
        }
    
    def get_fault_history(self) -> List[FaultEvent]:
        """Get all fault events."""
        return self._fault_history.copy()
    
    def reset(self):
        """Reset fault injector state."""
        self._state = FaultState()
        self._active_faults.clear()
        self._fault_history.clear()
