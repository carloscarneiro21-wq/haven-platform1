"""Acceptance tests for /api/trades/report.

Requirements:
- 3 trades (1 win, 1 loss, 1 open)
- 2 blocked opens (rate limit or already open)
- Report returns correct counts + failed codes + recommendations

Run:
  pytest -v /app/backend/tests/test_trades_report.py
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
async def db(paper_env):
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["crypto_trading_test_trades_report"]

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    await db.agent_execution_logs.delete_many({})

    yield db

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    await db.agent_execution_logs.delete_many({})
    client.close()


@pytest_asyncio.fixture
async def services(db):
    from services.execution.config import reload_trading_config
    from services.execution.router import ExecutionRouter, set_execution_router
    from services.trades_service import TradesService, set_trades_service
    from services.execution import agent_bridge as agent_bridge_module
    from services.execution.agent_bridge import init_agent_bridge
    from services.agent_trade_client import AgentTradeClient, set_agent_trade_client

    agent_bridge_module._agent_bridge = None

    cfg = reload_trading_config()
    cfg.kill_switch_active = False
    cfg.kill_switch_reason = None
    cfg.kill_switch_activated_at = None

    router = ExecutionRouter(db=db)
    await router.initialize()
    set_execution_router(router)

    trades = TradesService(db=db)
    await trades.initialize()
    set_trades_service(trades)

    await init_agent_bridge()

    client = AgentTradeClient(db=db)
    await client.initialize()
    set_agent_trade_client(client)

    return {"db": db, "trades": trades, "client": client}


@pytest.mark.asyncio
async def test_report_counts_failed_and_recommendations(services):
    from services.agent_trade_client import AgentOpenPayload, AgentClosePayload
    from services.trades_report import TradesReportService

    client = services["client"]
    db = services["db"]

    # Trade 1: win
    r1 = await client.open_trade(AgentOpenPayload(symbol="BTC/USDT", side="BUY", qty=0.01, entry_price=65000, strategy="MM", agent_id="mm_1", meta={}))
    assert r1["status"] == "ok"
    await client.close_trade(agent_id="mm_1", symbol="BTC/USDT", strategy="MM", payload=AgentClosePayload(exit_price=66000, reason="manual", meta={}))

    # Trade 2: loss
    r2 = await client.open_trade(AgentOpenPayload(symbol="ETH/USDT", side="BUY", qty=0.1, entry_price=3500, strategy="MOM", agent_id="mom_1", meta={}))
    assert r2["status"] == "ok"
    await client.close_trade(agent_id="mom_1", symbol="ETH/USDT", strategy="MOM", payload=AgentClosePayload(exit_price=3400, reason="manual", meta={}))

    # Trade 3: open
    r3 = await client.open_trade(AgentOpenPayload(symbol="SOL/USDT", side="BUY", qty=1.0, entry_price=150, strategy="SNIPER", agent_id="sn_1", meta={}))
    assert r3["status"] == "ok"

    # Blocked 1: already open (same symbol/agent/strategy)
    b1 = await client.open_trade(AgentOpenPayload(symbol="SOL/USDT", side="BUY", qty=1.0, entry_price=150, strategy="SNIPER", agent_id="sn_1", meta={}))
    assert b1["status"] == "blocked"
    assert b1["code"] == "BLOCKED_ALREADY_OPEN"

    # Blocked 2: rate limit (make 2 opens within 60s for same agent_id then 3rd)
    # We close immediately to avoid max-open conflict.
    a = AgentOpenPayload(symbol="XRP/USDT", side="BUY", qty=10.0, entry_price=0.5, strategy="MM", agent_id="rate_1", meta={})
    o1 = await client.open_trade(a)
    assert o1["status"] == "ok"
    await client.close_trade(agent_id="rate_1", symbol="XRP/USDT", strategy="MM", payload=AgentClosePayload(exit_price=0.51, reason="manual", meta={}))

    o2 = await client.open_trade(a)
    assert o2["status"] == "ok"
    await client.close_trade(agent_id="rate_1", symbol="XRP/USDT", strategy="MM", payload=AgentClosePayload(exit_price=0.49, reason="manual", meta={}))

    o3 = await client.open_trade(a)
    assert o3["status"] == "blocked"
    assert o3["code"] == "BLOCKED_RATE_LIMIT"

    report_service = TradesReportService(db=db)
    report = await report_service.get_report(mode="paper", window="24h", strategy="ALL", agent_id="ALL")

    assert report["counts"]["total"] >= 3
    assert report["counts"]["wins"] >= 1
    assert report["counts"]["losses"] >= 1
    assert report["counts"]["open"] >= 1

    failed_by_code = {f["reason_code"]: f for f in report["failed"]}
    assert failed_by_code.get("BLOCKED_ALREADY_OPEN", {}).get("count", 0) >= 1
    assert failed_by_code.get("BLOCKED_RATE_LIMIT", {}).get("count", 0) >= 1

    # Examples preview present (up to 3) with required fields
    ex = failed_by_code["BLOCKED_ALREADY_OPEN"].get("examples")
    assert ex and len(ex) <= 3
    assert {"ts", "agent_id", "strategy", "symbol", "action", "code", "message", "details"}.issubset(ex[0].keys())

    # At least one worked_well item
    assert len(report["worked_well"]) >= 1

    # At least one P0 recommendation based on failures
    assert any(r["priority"] == "P0" for r in report["recommendations"])
