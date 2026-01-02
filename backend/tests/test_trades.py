"""Trades API and WebSocket Tests.

These tests validate:
1. /api/trades returns correct schema
2. WS rejects missing/invalid JWT
3. WS accepts valid JWT and can emit events

Run:
    pytest -v /app/backend/tests/test_trades.py
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import jwt


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def mock_db():
    """Mock MongoDB database."""
    db = MagicMock()
    
    # Mock agent_trades collection
    db.agent_trades = MagicMock()
    db.agent_trades.create_index = AsyncMock()
    db.agent_trades.insert_one = AsyncMock()
    db.agent_trades.find = MagicMock()
    db.agent_trades.find_one = AsyncMock()
    db.agent_trades.find_one_and_update = AsyncMock()
    db.agent_trades.count_documents = AsyncMock(return_value=10)
    db.agent_trades.aggregate = MagicMock()
    
    # Setup find to return a mock cursor
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "trade-1",
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent_id": "agent-1",
            "agent_name": "Test Agent",
            "strategy": "MM",
            "mode": "paper",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "qty": 0.01,
            "entry_price": 65000.0,
            "exit_price": None,
            "status": "FILLED",
            "fees": 0.65,
            "slippage": 0.01,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "meta": {"latency_ms": 150},
        }
    ])
    db.agent_trades.find.return_value = mock_cursor
    
    # Setup aggregate
    mock_agg = MagicMock()
    mock_agg.to_list = AsyncMock(return_value=[
        {
            "_id": "agent-1",
            "name": "Test Agent",
            "total_trades": 10,
            "total_pnl": 150.0,
            "wins": 7,
            "losses": 3,
            "total_volume": 5000.0,
            "avg_pnl": 15.0,
            "max_pnl": 50.0,
            "min_pnl": -20.0,
        }
    ])
    db.agent_trades.aggregate.return_value = mock_agg
    
    return db


@pytest.fixture
def jwt_secret():
    """JWT secret for testing."""
    return "test-secret-key-12345"


@pytest.fixture
def valid_token(jwt_secret):
    """Generate a valid JWT token."""
    payload = {
        "user_id": "test-user-123",
        "username": "testuser",
        "role": "user",
        "exp": datetime.now(timezone.utc).timestamp() + 3600,
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest.fixture
def expired_token(jwt_secret):
    """Generate an expired JWT token."""
    payload = {
        "user_id": "test-user-123",
        "username": "testuser",
        "role": "user",
        "exp": datetime.now(timezone.utc).timestamp() - 3600,  # Expired
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


# ============================================================
# Test 1: TradesService
# ============================================================

@pytest.mark.asyncio
async def test_trades_service_initialization(mock_db):
    """TradesService initializes and creates indexes."""
    from services.trades_service import TradesService
    
    service = TradesService(mock_db)
    await service.initialize()
    
    # Should create indexes
    assert mock_db.agent_trades.create_index.call_count >= 4


@pytest.mark.asyncio
async def test_trades_service_get_trades(mock_db):
    """TradesService.get_trades returns correct data."""
    from services.trades_service import TradesService
    
    service = TradesService(mock_db)
    await service.initialize()
    
    trades = await service.get_trades(limit=50)
    
    assert len(trades) == 1
    assert trades[0]["id"] == "trade-1"
    assert trades[0]["symbol"] == "BTC/USDT"
    assert trades[0]["mode"] == "paper"


@pytest.mark.asyncio
async def test_trades_service_create_trade(mock_db):
    """TradesService.create_trade stores trade correctly."""
    from services.trades_service import TradesService, AgentTrade
    
    service = TradesService(mock_db)
    await service.initialize()
    
    trade = AgentTrade(
        agent_id="agent-1",
        agent_name="Test Agent",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.01,
        entry_price=65000.0,
    )
    
    result = await service.create_trade(trade)
    
    assert result.id == trade.id
    mock_db.agent_trades.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_trades_service_get_summary(mock_db):
    """TradesService.get_summary returns aggregated stats."""
    from services.trades_service import TradesService
    
    service = TradesService(mock_db)
    await service.initialize()
    
    summary = await service.get_summary(window="24h", group_by="agent")
    
    assert "overall" in summary
    assert "by_agent" in summary
    assert summary["overall"]["total_trades"] == 10


# ============================================================
# Test 2: WebSocket Manager - Token Validation
# ============================================================

def test_ws_manager_rejects_missing_token(jwt_secret):
    """WSStreamManager rejects connections without token."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        result = manager.verify_token("")
        
        assert result is None


def test_ws_manager_rejects_invalid_token(jwt_secret):
    """WSStreamManager rejects invalid JWT tokens."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        result = manager.verify_token("invalid-token-123")
        
        assert result is None


def test_ws_manager_rejects_expired_token(jwt_secret, expired_token):
    """WSStreamManager rejects expired JWT tokens."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        result = manager.verify_token(expired_token)
        
        assert result is None


def test_ws_manager_accepts_valid_token(jwt_secret, valid_token):
    """WSStreamManager accepts valid JWT tokens."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        result = manager.verify_token(valid_token)
        
        assert result is not None
        assert result["user_id"] == "test-user-123"
        assert result["username"] == "testuser"


# ============================================================
# Test 3: WebSocket Manager - Connection Management
# ============================================================

@pytest.mark.asyncio
async def test_ws_manager_connection_lifecycle(jwt_secret, valid_token):
    """WSStreamManager handles connection lifecycle correctly."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        
        # Mock WebSocket
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        
        # Connect
        conn_id = await manager.connect(mock_ws, valid_token)
        
        assert conn_id is not None
        assert conn_id in manager.connections
        mock_ws.accept.assert_called_once()
        
        # Disconnect
        await manager.disconnect(conn_id)
        
        assert conn_id not in manager.connections


@pytest.mark.asyncio
async def test_ws_manager_subscription(jwt_secret, valid_token):
    """WSStreamManager handles subscriptions correctly."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        
        # Mock WebSocket
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        
        # Connect
        conn_id = await manager.connect(mock_ws, valid_token)
        
        # Subscribe
        await manager.handle_message(conn_id, {
            "type": "subscribe",
            "topics": ["trades", "metrics"],
            "filters": {"symbol": "BTC/USDT"},
        })
        
        conn = manager.connections[conn_id]
        assert "trades" in conn.subscriptions
        assert "metrics" in conn.subscriptions
        assert conn.filters["symbol"] == "BTC/USDT"
        
        # Cleanup
        await manager.disconnect(conn_id)


@pytest.mark.asyncio
async def test_ws_manager_broadcast(jwt_secret, valid_token):
    """WSStreamManager broadcasts to subscribed connections."""
    with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
        from services.ws_stream import WSStreamManager
        
        manager = WSStreamManager()
        
        # Mock WebSocket
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        
        # Connect and subscribe
        conn_id = await manager.connect(mock_ws, valid_token)
        await manager.handle_message(conn_id, {
            "type": "subscribe",
            "topics": ["trades"],
        })
        
        # Broadcast
        await manager.broadcast("trade.created", {
            "id": "trade-1",
            "symbol": "BTC/USDT",
        }, topic="trades")
        
        # Check send was called (welcome + subscribed + broadcast)
        assert mock_ws.send_json.call_count >= 3
        
        # Cleanup
        await manager.disconnect(conn_id)


# ============================================================
# Test 4: Trades API Schema
# ============================================================

def test_trade_response_schema():
    """AgentTrade model has required fields."""
    from services.trades_service import AgentTrade
    
    trade = AgentTrade(
        agent_id="agent-1",
        agent_name="Test Agent",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.01,
        entry_price=65000.0,
    )
    
    data = trade.model_dump()
    
    # Check required fields
    assert "id" in data
    assert "ts" in data
    assert "agent_id" in data
    assert "agent_name" in data
    assert "strategy" in data
    assert "mode" in data
    assert "symbol" in data
    assert "side" in data
    assert "qty" in data
    assert "entry_price" in data
    assert "status" in data
    assert "fees" in data
    assert "slippage" in data
    assert "pnl" in data
    assert "pnl_pct" in data
    assert "meta" in data
    
    # Check defaults
    assert data["mode"] == "paper"
    assert data["status"] == "OPEN"


# ============================================================
# Test 5: Event Emission
# ============================================================

@pytest.mark.asyncio
async def test_trades_service_emits_events(mock_db):
    """TradesService emits events when trades are created/updated."""
    from services.trades_service import TradesService, AgentTrade
    
    service = TradesService(mock_db)
    await service.initialize()
    
    # Track emitted events
    events = []
    
    async def callback(event_type, payload):
        events.append((event_type, payload))
    
    service.register_event_callback(callback)
    
    # Create trade
    trade = AgentTrade(
        agent_id="agent-1",
        agent_name="Test Agent",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.01,
        entry_price=65000.0,
    )
    
    await service.create_trade(trade)
    
    # Check event was emitted
    assert len(events) == 1
    assert events[0][0] == "trade.created"
    assert events[0][1]["symbol"] == "BTC/USDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
