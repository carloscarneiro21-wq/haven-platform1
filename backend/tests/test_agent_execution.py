"""Agent Execution Bridge Tests.

Tests:
1. Agent creates OPEN trade -> trade appears in DB with WS event
2. Agent closes trade -> PnL computed correctly
3. Kill switch ON -> agent signals ignored (no trade created)

Run:
    pytest -v /app/backend/tests/test_agent_execution.py
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so imports like `from services...` work
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))




@pytest.fixture
def mock_db():
    """Mock MongoDB database."""
    db = MagicMock()
    
    # Mock collections
    db.agent_trades = MagicMock()
    db.agent_trades.create_index = AsyncMock()
    db.agent_trades.insert_one = AsyncMock()
    db.agent_trades.find_one = AsyncMock(return_value=None)
    db.agent_trades.find_one_and_update = AsyncMock()
    db.agent_trades.count_documents = AsyncMock(return_value=0)
    
    # Mock find cursor
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    db.agent_trades.find = MagicMock(return_value=mock_cursor)
    
    db.agent_trades.aggregate = MagicMock()
    mock_agg = MagicMock()
    mock_agg.to_list = AsyncMock(return_value=[])
    db.agent_trades.aggregate.return_value = mock_agg
    
    db.execution_history = MagicMock()
    db.execution_history.insert_one = AsyncMock()
    
    db.paper_trades = MagicMock()
    db.paper_trades.insert_one = AsyncMock()
    
    return db


@pytest.fixture
def paper_mode_env():
    """Set up paper mode environment."""
    original = os.environ.copy()
    os.environ["TRADING_MODE"] = "paper"
    os.environ["LIVE_CEX_ENABLED"] = "false"
    os.environ["LIVE_DEX_ENABLED"] = "false"
    os.environ["MAX_POSITION_SIZE_EUR"] = "10000"
    os.environ["DAILY_LOSS_LIMIT_EUR"] = "1000"
    os.environ["MAX_DAILY_TRADES"] = "100"
    yield
    os.environ.clear()
    os.environ.update(original)


@pytest.fixture(autouse=True)
def deterministic_paper_executor():
    """Make paper execution deterministic for tests.

    PaperTradeExecutor simulates random rejections / partial fills / variable slippage.
    In tests we want stable behavior, so we patch randomness:
    - random.random() -> 0.5 (no rejection, no partial fill)
    - np.random.uniform() -> 1.0 (stable slippage variation)
    - random.randint() -> MIN latency
    """
    with patch("services.execution.paper_executor.random.random", return_value=0.5), \
         patch("services.execution.paper_executor.np.random.uniform", return_value=1.0), \
         patch("services.execution.paper_executor.random.randint", return_value=50):
        yield


# ============================================================
# Test 1: Agent Creates OPEN Trade
# ============================================================

@pytest.mark.asyncio
async def test_agent_opens_position(mock_db, paper_mode_env):
    """Agent creates an OPEN trade that appears in DB."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    # Setup
    config = reload_trading_config()
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    # Execute
    result = await bridge.open_position(
        agent_id="test_mm_agent",
        agent_name="Test Market Maker",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.1,
        price=65000.0,
        reason="Test signal",
    )
    
    # Verify
    assert result["success"] == True
    assert result["trade_id"] is not None
    assert result["entry_price"] > 0
    assert result["qty"] > 0
    assert result.get("fees", 0) >= 0
    
    # Verify DB insert was called
    mock_db.agent_trades.insert_one.assert_called()


@pytest.mark.asyncio
async def test_agent_opens_sell_position(mock_db, paper_mode_env):
    """Agent creates a SELL position."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    result = await bridge.open_position(
        agent_id="test_sniper",
        agent_name="Sniper Bot",
        strategy="SNIPER",
        symbol="ETH/USDT",
        side="SELL",
        qty=1.0,
        price=3500.0,
    )
    
    assert result["success"] == True
    assert result["trade_id"] is not None


# ============================================================
# Test 2: Agent Closes Trade with PnL
# ============================================================

@pytest.mark.asyncio
async def test_agent_closes_position_with_profit(mock_db, paper_mode_env):
    """Agent closes trade and PnL is computed correctly (profit)."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    # Open position
    open_result = await bridge.open_position(
        agent_id="test_mm",
        agent_name="Market Maker",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.1,
        price=65000.0,
    )
    
    assert open_result["success"] == True
    trade_id = open_result["trade_id"]
    entry_price = open_result["entry_price"]
    
    # Mock the trade exists in DB for close operation
    mock_db.agent_trades.find_one.return_value = {
        "id": trade_id,
        "entry_price": entry_price,
        "qty": 0.1,
        "side": "BUY",
        "fees": open_result.get("fees", 0),
        "status": "OPEN",
    }
    
    mock_db.agent_trades.find_one_and_update.return_value = {
        "id": trade_id,
        "entry_price": entry_price,
        "exit_price": 67000.0,
        "qty": 0.1,
        "side": "BUY",
        "status": "CLOSED",
        "pnl": (67000.0 - entry_price) * 0.1,  # Profit
        "pnl_pct": ((67000.0 - entry_price) / entry_price) * 100,
    }
    
    # Close position with profit
    close_result = await bridge.close_position(
        trade_id=trade_id,
        exit_price=67000.0,
    )
    
    assert close_result["success"] == True
    assert close_result["status"] == "CLOSED"
    assert close_result["pnl"] > 0  # Profit


@pytest.mark.asyncio
async def test_agent_closes_position_with_loss(mock_db, paper_mode_env):
    """Agent closes trade and PnL is computed correctly (loss)."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    # Open position
    open_result = await bridge.open_position(
        agent_id="test_mom",
        agent_name="Momentum Bot",
        strategy="MOM",
        symbol="ETH/USDT",
        side="BUY",
        qty=1.0,
        price=3500.0,
    )
    
    trade_id = open_result["trade_id"]
    entry_price = open_result["entry_price"]
    
    # Mock the trade for close
    mock_db.agent_trades.find_one.return_value = {
        "id": trade_id,
        "entry_price": entry_price,
        "qty": 1.0,
        "side": "BUY",
        "fees": 0,
        "status": "OPEN",
    }
    
    loss_pnl = (3400.0 - entry_price) * 1.0  # Loss
    mock_db.agent_trades.find_one_and_update.return_value = {
        "id": trade_id,
        "exit_price": 3400.0,
        "pnl": loss_pnl,
        "pnl_pct": (loss_pnl / (entry_price * 1.0)) * 100,
        "status": "CLOSED",
    }
    
    # Close with loss
    close_result = await bridge.close_position(
        trade_id=trade_id,
        exit_price=3400.0,
    )
    
    assert close_result["success"] == True
    assert close_result["pnl"] < 0  # Loss


# ============================================================
# Test 3: Kill Switch Blocks Execution
# ============================================================

@pytest.mark.asyncio
async def test_kill_switch_blocks_agent_execution(mock_db, paper_mode_env):
    """Kill switch ON -> agent signals are ignored."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    
    # Activate kill switch
    config.activate_kill_switch("Test emergency stop")
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    # Try to open position
    result = await bridge.open_position(
        agent_id="test_agent",
        agent_name="Test Agent",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.1,
        price=65000.0,
    )
    
    # Should be blocked
    assert result["success"] == False
    assert result["blocked"] == True
    assert "kill switch" in result["reason"].lower()
    assert result["trade_id"] is None
    
    # DB should NOT have been called for insert
    mock_db.agent_trades.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_kill_switch_blocks_close(mock_db, paper_mode_env):
    """Kill switch also blocks close operations."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    config.activate_kill_switch("Emergency")
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    result = await bridge.close_position(
        trade_id="some-trade-id",
        exit_price=65000.0,
    )
    
    assert result["success"] == False
    assert result["blocked"] == True


# ============================================================
# Test 4: Position Tracking
# ============================================================

@pytest.mark.asyncio
async def test_agent_position_tracking(mock_db, paper_mode_env):
    """Bridge tracks open positions by agent/strategy/symbol."""
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution.agent_bridge import AgentExecutionBridge
    
    config = reload_trading_config()
    
    router = ExecutionRouter(db=mock_db, config=config)
    await router.initialize()
    set_execution_router(router)
    
    trades_service = TradesService(mock_db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    bridge = AgentExecutionBridge()
    await bridge.initialize()
    
    # Open position
    result = await bridge.open_position(
        agent_id="tracker_test",
        agent_name="Tracker",
        strategy="MM",
        symbol="BTC/USDT",
        side="BUY",
        qty=0.1,
        price=65000.0,
    )
    
    trade_id = result["trade_id"]
    
    # Verify position is tracked
    position_key = bridge._get_position_key("tracker_test", "MM", "BTC/USDT")
    assert position_key in bridge._open_positions
    assert bridge._open_positions[position_key] == trade_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
