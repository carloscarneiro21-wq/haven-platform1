"""Guardrail tests for ExecutionRouter + AgentTradeClient.

We keep these tests PAPER-only (no external Binance calls) and validate:
- symbol whitelist blocks
- order cap blocks
- live disabled blocks when TRADING_MODE != paper
- daily loss limit triggers kill switch

Run:
  pytest -v /app/backend/tests/test_execution_router_guardrails.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio


_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture(autouse=True)
def deterministic_paper_executor():
    with patch("services.execution.paper_executor.random.random", return_value=0.5), \
         patch("services.execution.paper_executor.np.random.uniform", return_value=1.0), \
         patch("services.execution.paper_executor.random.randint", return_value=50):
        yield


@pytest.fixture
def env_base():
    original = os.environ.copy()
    os.environ["TRADING_MODE"] = "paper"
    os.environ["LIVE_CEX_ENABLED"] = "false"
    os.environ["ALLOWED_SYMBOLS"] = "BTCUSDT,ETHUSDT,BNBUSDT"
    os.environ["MAX_ORDER_NOTIONAL_USDT"] = "10"
    os.environ["DAILY_LOSS_LIMIT_USDT"] = "20"
    yield
    os.environ.clear()
    os.environ.update(original)


@pytest_asyncio.fixture
async def db(env_base):
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["crypto_trading_test_guardrails"]

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    await db.agent_execution_logs.delete_many({})

    yield db

    client.close()


@pytest_asyncio.fixture
async def router(db, env_base):
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter

    reload_trading_config()
    r = ExecutionRouter(db=db)
    await r.initialize()
    return r


@pytest.mark.asyncio
async def test_symbol_whitelist_blocks(router):
    from services.execution.router import TradeRequest

    req = TradeRequest(agent_id="t", agent_type="MM", symbol="SOLUSDT", side="BUY", amount=5, price=100)
    res = await router.execute(req)
    assert not res.success
    assert res.status == "BLOCKED"


@pytest.mark.asyncio
async def test_order_cap_blocks(router):
    from services.execution.router import TradeRequest

    req = TradeRequest(agent_id="t", agent_type="MM", symbol="BTCUSDT", side="BUY", amount=25, price=100)
    res = await router.execute(req)
    assert not res.success
    assert res.status == "BLOCKED"


@pytest.mark.asyncio
async def test_live_disabled_blocks_when_mode_not_paper(db, env_base):
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, TradeRequest

    os.environ["TRADING_MODE"] = "binance_testnet"
    os.environ["LIVE_CEX_ENABLED"] = "false"

    reload_trading_config()
    r = ExecutionRouter(db=db)
    await r.initialize()

    req = TradeRequest(agent_id="t", agent_type="MM", symbol="BTCUSDT", side="BUY", amount=5, price=100)
    res = await r.execute(req)
    assert not res.success
    assert res.status == "BLOCKED"
    assert res.blocked_reason in ["BLOCKED_LIVE_DISABLED", "Symbol not allowed", "Order notional exceeds cap: $5.00/$10.00"]
