"""Tests: AgentTradeClient guardrails + end-to-end persistence in agent_trades.

Covers:
1) MM open -> creates trade with strategy=MM and agent_id; visible via TradesService summary
2) close -> status CLOSED and pnl updates
3) kill switch ON -> open blocked and no trade created
4) rate limit -> 3rd open in 60s blocked
5) duplicate protection -> open while open exists blocked

Run:
  pytest -v /app/backend/tests/test_agent_trade_client.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio


# Ensure backend/ is on sys.path so imports like `from services...` work
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture(autouse=True)
def deterministic_paper_executor():
    # Make paper execution deterministic
    with patch("services.execution.paper_executor.random.random", return_value=0.5), \
         patch("services.execution.paper_executor.np.random.uniform", return_value=1.0), \
         patch("services.execution.paper_executor.random.randint", return_value=50):
        yield


@pytest.fixture
def paper_env():
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


@pytest_asyncio.fixture
async def db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["crypto_trading_test_agent_client"]

    # clean
    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})

    yield db

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    client.close()


@pytest_asyncio.fixture
async def services(db, paper_env):
    # Set global services (router, trades_service, bridge, agent_trade_client)
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution import agent_bridge as agent_bridge_module
    from services.execution.agent_bridge import init_agent_bridge
    from services.agent_trade_client import AgentTradeClient, set_agent_trade_client

    # Reset global singletons that may reference a previous event loop
    agent_bridge_module._agent_bridge = None

    cfg = reload_trading_config()
    # Ensure kill switch is OFF for tests unless explicitly enabled
    cfg.kill_switch_active = False
    cfg.kill_switch_reason = None
    cfg.kill_switch_activated_at = None

    router = ExecutionRouter(db=db)
    await router.initialize()
    set_execution_router(router)

    trades = TradesService(db=db)
    await trades.initialize()
    set_trades_service(trades)

    bridge = await init_agent_bridge()

    client = AgentTradeClient(db=db)
    await client.initialize()
    set_agent_trade_client(client)

    return {"router": router, "trades": trades, "bridge": bridge, "client": client}


@pytest.mark.asyncio
async def test_mm_open_and_close_updates_summary(services):
    from services.agent_trade_client import AgentOpenPayload, AgentClosePayload

    client = services["client"]

    open_res = await client.open_trade(
        AgentOpenPayload(
            symbol="BTC/USDT",
            side="BUY",
            qty=0.01,
            entry_price=65000,
            strategy="MM",
            agent_id="mm_agent_1",
            meta={"signal_reason": "test_open"},
        )
    )

    assert open_res["status"] == "ok"
    trade_id = open_res["trade_id"]
    assert trade_id

    # Validate trade record
    trade = await services["trades"].db.agent_trades.find_one({"id": trade_id}, {"_id": 0})
    assert trade["agent_id"] == "mm_agent_1"
    assert trade["strategy"] == "MM"
    assert trade["status"] == "OPEN"

    # Close with profit
    close_res = await client.close_trade(
        agent_id="mm_agent_1",
        symbol="BTC/USDT",
        strategy="MM",
        payload=AgentClosePayload(exit_price=66000, reason="manual", meta={}),
    )
    assert close_res["status"] == "ok"

    trade2 = await services["trades"].db.agent_trades.find_one({"id": trade_id}, {"_id": 0})
    assert trade2["status"] == "CLOSED"
    assert trade2["pnl"] > 0

    summary = await services["trades"].get_summary(window="24h", group_by="agent", mode="paper")
    assert summary["overall"]["total_trades"] >= 1
    assert summary["overall"]["cumulative_pnl"] > 0


@pytest.mark.asyncio
async def test_kill_switch_blocks_open_and_creates_no_trade(services):
    from services.agent_trade_client import AgentOpenPayload
    from services.execution.config import get_trading_config

    cfg = get_trading_config()
    cfg.activate_kill_switch("test")

    client = services["client"]
    res = await client.open_trade(
        AgentOpenPayload(
            symbol="BTC/USDT",
            side="BUY",
            qty=0.01,
            entry_price=65000,
            strategy="MM",
            agent_id="mm_agent_2",
            meta={},
        )
    )

    assert res["status"] == "blocked"
    assert res["code"] == "BLOCKED_KILL_SWITCH"

    count = await services["trades"].db.agent_trades.count_documents({"agent_id": "mm_agent_2"})
    assert count == 0


@pytest.mark.asyncio
async def test_rate_limit_blocks_third_open_in_60s(services):
    from services.agent_trade_client import AgentOpenPayload

    client = services["client"]

    p = AgentOpenPayload(
        symbol="ETH/USDT",
        side="BUY",
        qty=0.1,
        entry_price=3500,
        strategy="MOM",
        agent_id="mom_agent_1",
        meta={},
    )

    r1 = await client.open_trade(p)
    assert r1["status"] == "ok"

    # Close immediately so we can try again without max-open conflict
    from services.agent_trade_client import AgentClosePayload

    await client.close_trade(
        agent_id="mom_agent_1",
        symbol="ETH/USDT",
        strategy="MOM",
        payload=AgentClosePayload(exit_price=3550, reason="manual", meta={}),
    )

    r2 = await client.open_trade(p)
    assert r2["status"] == "ok"

    await client.close_trade(
        agent_id="mom_agent_1",
        symbol="ETH/USDT",
        strategy="MOM",
        payload=AgentClosePayload(exit_price=3560, reason="manual", meta={}),
    )

    r3 = await client.open_trade(p)
    assert r3["status"] == "blocked"
    assert r3["code"] == "BLOCKED_RATE_LIMIT"


@pytest.mark.asyncio
async def test_duplicate_protection_blocks_when_open_exists(services):
    from services.agent_trade_client import AgentOpenPayload

    client = services["client"]

    p = AgentOpenPayload(
        symbol="SOL/USDT",
        side="BUY",
        qty=1.0,
        entry_price=150,
        strategy="SNIPER",
        agent_id="sniper_agent_1",
        meta={},
    )

    r1 = await client.open_trade(p)
    assert r1["status"] == "ok"

    r2 = await client.open_trade(p)
    assert r2["status"] == "blocked"
    assert r2["code"] == "BLOCKED_ALREADY_OPEN"
