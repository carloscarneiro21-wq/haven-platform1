"""
Growth Module WebSocket Manager
===============================

Real-time push updates for:
- PnL (total and per position)
- Active paper orders
- Guardian state (kill switch, limits)
- Last run result

Push imediato quando há mudanças.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GrowthWSMessage(BaseModel):
    """WebSocket message format."""
    type: str  # "pnl" | "orders" | "guardian" | "run" | "scheduler" | "full"
    data: Dict[str, Any]
    timestamp: str = ""
    
    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        super().__init__(**data)


class GrowthWebSocketManager:
    """
    Manages WebSocket connections for Growth Module real-time updates.
    
    Usage:
        manager = GrowthWebSocketManager()
        
        # In WebSocket endpoint:
        await manager.connect(websocket, user_id)
        await manager.broadcast_pnl(pnl_data)
        
        # When changes occur:
        await manager.notify_change("pnl", pnl_data)
    """
    
    def __init__(self):
        # Active connections: user_id -> websocket
        self.active_connections: Dict[str, WebSocket] = {}
        # Subscriptions: user_id -> set of types
        self.subscriptions: Dict[str, Set[str]] = {}
        # Last known state for each type
        self._state: Dict[str, Any] = {
            "pnl": {},
            "orders": [],
            "guardian": {},
            "run": None,
            "scheduler": {},
        }
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: str, subscribe_to: list = None):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections[user_id] = websocket
            self.subscriptions[user_id] = set(subscribe_to or ["pnl", "orders", "guardian", "run", "scheduler"])
        logger.info(f"WebSocket connected: {user_id}")
        
        # Send current state
        await self._send_full_state(websocket)
    
    async def disconnect(self, user_id: str):
        """Remove a connection."""
        async with self._lock:
            if user_id in self.active_connections:
                del self.active_connections[user_id]
            if user_id in self.subscriptions:
                del self.subscriptions[user_id]
        logger.info(f"WebSocket disconnected: {user_id}")
    
    async def _send_full_state(self, websocket: WebSocket):
        """Send full current state to a connection."""
        try:
            message = GrowthWSMessage(
                type="full",
                data=self._state.copy(),
            )
            await websocket.send_json(message.model_dump())
        except Exception as e:
            logger.error(f"Error sending full state: {e}")
    
    async def notify_change(self, change_type: str, data: Any):
        """
        Notify all subscribed connections of a change.
        
        Args:
            change_type: "pnl" | "orders" | "guardian" | "run" | "scheduler"
            data: The new data
        """
        # Update state
        self._state[change_type] = data
        
        # Create message
        message = GrowthWSMessage(
            type=change_type,
            data={change_type: data},
        )
        
        # Broadcast to subscribed connections
        disconnected = []
        async with self._lock:
            for user_id, websocket in self.active_connections.items():
                if change_type in self.subscriptions.get(user_id, set()):
                    try:
                        await websocket.send_json(message.model_dump())
                    except Exception as e:
                        logger.warning(f"Failed to send to {user_id}: {e}")
                        disconnected.append(user_id)
        
        # Clean up disconnected
        for user_id in disconnected:
            await self.disconnect(user_id)
    
    async def broadcast(self, message: GrowthWSMessage):
        """Broadcast a message to all connections."""
        disconnected = []
        async with self._lock:
            for user_id, websocket in self.active_connections.items():
                try:
                    await websocket.send_json(message.model_dump())
                except Exception:
                    disconnected.append(user_id)
        
        for user_id in disconnected:
            await self.disconnect(user_id)
    
    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)
    
    def update_state(self, state_type: str, data: Any):
        """Update internal state without notifying (for batch updates)."""
        self._state[state_type] = data


# Global instance
_growth_ws_manager: Optional[GrowthWebSocketManager] = None


def get_growth_ws_manager() -> GrowthWebSocketManager:
    """Get or create the global WebSocket manager."""
    global _growth_ws_manager
    if _growth_ws_manager is None:
        _growth_ws_manager = GrowthWebSocketManager()
    return _growth_ws_manager


async def notify_pnl_change(pnl_data: Dict[str, Any]):
    """Helper to notify PnL changes."""
    manager = get_growth_ws_manager()
    await manager.notify_change("pnl", pnl_data)


async def notify_orders_change(orders: list):
    """Helper to notify orders changes."""
    manager = get_growth_ws_manager()
    await manager.notify_change("orders", orders)


async def notify_guardian_change(guardian_state: Dict[str, Any]):
    """Helper to notify Guardian state changes."""
    manager = get_growth_ws_manager()
    await manager.notify_change("guardian", guardian_state)


async def notify_run_complete(run_result: Dict[str, Any]):
    """Helper to notify run completion."""
    manager = get_growth_ws_manager()
    await manager.notify_change("run", run_result)


async def notify_scheduler_change(scheduler_state: Dict[str, Any]):
    """Helper to notify scheduler state changes."""
    manager = get_growth_ws_manager()
    await manager.notify_change("scheduler", scheduler_state)
