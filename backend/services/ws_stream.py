"""WebSocket Stream Manager for Real-Time Trading Updates.

Provides:
- JWT-authenticated WebSocket connections
- Subscription-based event filtering
- Heartbeat ping/pong
- Auto-disconnect stale connections

Events:
- trade.created: New trade executed
- trade.updated: Trade status/PnL updated
- metrics.updated: Periodic metrics broadcast
"""

import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set, List
from fastapi import WebSocket, WebSocketDisconnect
import jwt
import os

logger = logging.getLogger(__name__)


class WSConnection:
    """WebSocket connection wrapper."""
    
    def __init__(self, websocket: WebSocket, user_id: str, user_info: Dict[str, Any]):
        self.websocket = websocket
        self.user_id = user_id
        self.user_info = user_info
        self.subscriptions: Set[str] = set()  # topics subscribed to
        self.filters: Dict[str, Any] = {}  # filter criteria
        self.connected_at = datetime.now(timezone.utc)
        self.last_pong = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)
    
    def update_activity(self):
        self.last_activity = datetime.now(timezone.utc)
    
    def is_stale(self, timeout_seconds: int = 120) -> bool:
        """Check if connection is stale (no pong/activity for timeout_seconds)."""
        return (datetime.now(timezone.utc) - self.last_pong).total_seconds() > timeout_seconds


class WSStreamManager:
    """WebSocket stream manager for real-time updates."""
    
    HEARTBEAT_INTERVAL = 30  # seconds
    STALE_TIMEOUT = 120  # seconds without pong -> consider dead
    METRICS_INTERVAL = 5  # seconds
    
    def __init__(self):
        self.connections: Dict[str, WSConnection] = {}
        self._jwt_secret = os.environ.get("JWT_SECRET_KEY", "")
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        self._trades_service = None
    
    def set_trades_service(self, service):
        """Set trades service for metrics broadcasting."""
        self._trades_service = service
        # Register callback for trade events
        service.register_event_callback(self._on_trade_event)
    
    async def _on_trade_event(self, event_type: str, payload: Dict[str, Any]):
        """Handle trade events from TradesService."""
        await self.broadcast(event_type, payload)
    
    async def start(self):
        """Start background tasks."""
        if self._running:
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._metrics_task = asyncio.create_task(self._metrics_loop())
        logger.info("WSStreamManager started")
    
    async def stop(self):
        """Stop background tasks."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
        
        # Close all connections
        for conn_id in list(self.connections.keys()):
            await self.disconnect(conn_id)
        
        logger.info("WSStreamManager stopped")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats and cleanup stale connections."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                # Check for stale connections (no pong)
                stale_ids = [
                    conn_id for conn_id, conn in self.connections.items()
                    if conn.is_stale(self.STALE_TIMEOUT)
                ]

                for conn_id in stale_ids:
                    logger.info(f"[WS] Closing stale connection (no pong): {conn_id}")
                    await self.disconnect(conn_id, reason="stale_no_pong")

                # Send ping to all connections (keepalive)
                await self.broadcast("ping", {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "connections": len(self.connections),
                })
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _metrics_loop(self):
        """Broadcast metrics periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.METRICS_INTERVAL)
                
                if self._trades_service and self.connections:
                    metrics = await self._trades_service.get_metrics()
                    await self.broadcast("metrics.updated", metrics, topic="metrics")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics broadcast error: {e}")
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return user info."""
        if not token:
            logger.warning("[WS] Auth failed: No token provided")
            return None
        
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]
            
            # Log token prefix for debugging (first 20 chars only)
            logger.debug(f"[WS] Verifying token: {token[:20]}...")
            
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"]
            )
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                logger.warning(f"[WS] Auth failed: Token expired for user {payload.get('username')}")
                return None
            
            user_info = {
                "user_id": payload.get("user_id") or payload.get("sub"),
                "username": payload.get("username"),
                "role": payload.get("role"),
            }
            logger.info(f"[WS] Token verified for user: {user_info.get('username')}")
            return user_info
            
        except jwt.InvalidTokenError as e:
            logger.warning(f"[WS] Auth failed - Invalid JWT: {e}")
            return None
        except Exception as e:
            logger.error(f"[WS] Auth failed - Token verification error: {e}")
            return None
    
    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> Optional[str]:
        """Authenticate and connect a WebSocket client.
        
        Returns connection ID if successful, None if auth failed.
        """
        client_ip = websocket.client.host if websocket.client else "unknown"
        logger.info(f"[WS] Connection attempt from {client_ip}")
        
        # Verify token
        user_info = self.verify_token(token)
        if not user_info:
            # Must accept before closing in some WebSocket implementations
            try:
                await websocket.accept()
                await websocket.close(code=4401, reason="Unauthorized: Invalid or missing JWT")
            except Exception as e:
                logger.warning(f"[WS] Error closing unauthorized connection: {e}")
            logger.warning(f"[WS] Connection rejected from {client_ip}: Auth failed")
            return None
        
        # Accept connection
        await websocket.accept()
        
        # Create connection
        conn_id = f"{user_info['user_id']}_{id(websocket)}"
        conn = WSConnection(websocket, user_info["user_id"], user_info)
        self.connections[conn_id] = conn
        
        logger.info(f"[WS] Connected: {conn_id} (user: {user_info.get('username')}, ip: {client_ip})")
        
        # Send welcome message
        await self._send(conn_id, {
            "type": "connected",
            "connection_id": conn_id,
            "user": user_info,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        
        return conn_id
    
    async def disconnect(self, conn_id: str, reason: str = "normal", code: int = 1000):
        """Disconnect a WebSocket client."""
        conn = self.connections.pop(conn_id, None)
        if conn:
            try:
                await conn.websocket.close(code=code, reason=reason)
            except Exception:
                pass
            duration = (datetime.now(timezone.utc) - conn.connected_at).total_seconds()
            logger.info(f"[WS] Disconnected: {conn_id} (code: {code}, reason: {reason}, duration: {duration:.1f}s)")
    
    async def handle_message(self, conn_id: str, data: Dict[str, Any]):
        """Handle incoming message from client."""
        conn = self.connections.get(conn_id)
        if not conn:
            return
        
        conn.update_activity()
        msg_type = data.get("type")

        # Treat any message as liveness
        conn.last_pong = datetime.now(timezone.utc)
        
        if msg_type == "subscribe":
            # Handle subscription
            topics = data.get("topics", [])
            filters = data.get("filters", {})
            
            conn.subscriptions = set(topics)
            conn.filters = filters
            
            await self._send(conn_id, {
                "type": "subscribed",
                "topics": list(conn.subscriptions),
                "filters": conn.filters,
            })
            
            logger.debug(f"Client {conn_id} subscribed to: {topics}")
        
        elif msg_type == "unsubscribe":
            topics = data.get("topics", [])
            conn.subscriptions -= set(topics)
            
            await self._send(conn_id, {
                "type": "unsubscribed",
                "topics": topics,
            })
        
        elif msg_type == "ping":
            # Client ping -> respond pong
            conn.last_pong = datetime.now(timezone.utc)
            await self._send(conn_id, {
                "type": "pong",
                "ts": datetime.now(timezone.utc).isoformat(),
            })

        elif msg_type == "pong":
            # Client pong (response to server ping)
            conn.last_pong = datetime.now(timezone.utc)
            await self._send(conn_id, {
                "type": "pong.ack",
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    
    async def _send(self, conn_id: str, message: Dict[str, Any]):
        """Send message to a specific connection."""
        conn = self.connections.get(conn_id)
        if not conn:
            return
        
        try:
            await conn.websocket.send_json(message)
            # Any successful send is a sign the socket is alive
            conn.last_activity = datetime.now(timezone.utc)
        except Exception as e:
            logger.warning(f"Send error to {conn_id}: {e}")
            await self.disconnect(conn_id, reason="send_error")
    
    async def broadcast(
        self,
        event_type: str,
        payload: Dict[str, Any],
        topic: Optional[str] = None,
    ):
        """Broadcast message to all subscribed connections."""
        message = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        }
        
        # Determine topic from event type if not specified
        if topic is None:
            if event_type.startswith("trade."):
                topic = "trades"
            elif event_type.startswith("metrics."):
                topic = "metrics"
        
        sent_count = 0
        for conn_id, conn in list(self.connections.items()):
            try:
                # Check if subscribed to topic
                if topic and topic not in conn.subscriptions:
                    continue
                
                # Apply filters (for trades)
                if topic == "trades" and conn.filters:
                    if not self._matches_filters(payload, conn.filters):
                        continue
                
                await conn.websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Broadcast error to {conn_id}: {e}")
                await self.disconnect(conn_id, "broadcast_error")
        
        if event_type.startswith("trade."):
            logger.info(f"[WS] Broadcast {event_type} to {sent_count}/{len(self.connections)} connections")
    
    def _matches_filters(self, payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if payload matches client filters."""
        for key, value in filters.items():
            if key in payload:
                if isinstance(value, list):
                    if payload[key] not in value:
                        return False
                elif payload[key] != value:
                    return False
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get manager status."""
        return {
            "running": self._running,
            "connections": len(self.connections),
            "connection_details": [
                {
                    "id": conn_id,
                    "user_id": conn.user_id,
                    "subscriptions": list(conn.subscriptions),
                    "connected_at": conn.connected_at.isoformat(),
                    "last_activity": conn.last_activity.isoformat(),
                }
                for conn_id, conn in self.connections.items()
            ],
        }


# Global instance
_ws_manager: Optional[WSStreamManager] = None


def get_ws_manager() -> WSStreamManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WSStreamManager()
    return _ws_manager


def set_ws_manager(manager: WSStreamManager):
    global _ws_manager
    _ws_manager = manager
