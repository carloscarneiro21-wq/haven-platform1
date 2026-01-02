"""Tests: Growth orchestrator uses AgentTradeClient -> creates agent_trades.

We verify that a single /growth/run/once creates at least one trade in the
agent_trades collection with strategy MM or MOM and an agent_id.

Run:
  pytest -v /app/backend/tests/test_growth_agents_trade_integration.py
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
    yield
    os.environ.clear()
    os.environ.update(original)


@pytest_asyncio.fixture
async def db(paper_env):
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["crypto_trading_test_growth_agents"]

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    await db.growth_runs.delete_many({})

    yield db

    await db.agent_trades.delete_many({})
    await db.agent_trade_state.delete_many({})
    await db.growth_runs.delete_many({})
    client.close()


@pytest_asyncio.fixture
async def growth_orchestrator(db):
    # Build minimal GrowthOrchestrator with services it needs.
    from services.growth_orchestrator import GrowthOrchestrator, set_growth_orchestrator
    from services.growth.paper_adapter import GrowthPaperAdapter
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

    paper_adapter = GrowthPaperAdapter(db=db, paper_executor=None, event_logger=None)
    await paper_adapter.initialize()

    orchestrator = GrowthOrchestrator(
        db=db,
        market_router=None,
        guardian_service=None,
        viability_service=None,
        risk_budget_service=None,
        growth_presets_service=None,
        paper_adapter=paper_adapter,
        event_logger=None,
        data_feed=None,
    )
    await orchestrator.initialize()
    set_growth_orchestrator(orchestrator)

    return orchestrator


@pytest.mark.asyncio
async def test_growth_run_once_creates_trade(growth_orchestrator, db):
    from services.growth import RunMode

    # Force deterministic routing + order generation so we actually execute an agent path
    with patch.object(growth_orchestrator, "_run_router", return_value={
        "regime": "RANGE",
        "regime_confidence": "HIGH",
        "recommended_agent": "MM",
        "recommended_preset_id": "MM_DEFAULT",
        "all_reason_codes": ["TEST_FORCED_MM"],
        "venue": "binance",
        "regime_reasons": [],
        "agent_reasons": [],
        "viability_reasons": [],
    }), patch.object(growth_orchestrator, "_generate_mm_orders", return_value=[
        {
            "client_order_id": "test_bid_0",
            "side": "buy",
            "order_type": "limit_maker",
            "price": 65000.0,
            "size_eur": 10.0,
            "size_asset": 10.0 / 65000.0,
            "post_only": True,
            "rationale": "test",
        }
    ]):
        res = await growth_orchestrator.run(mode=RunMode.RUN_ONCE, symbol="BTC/USDT", venue="auto")

    assert res.status.value in ["success", "blocked", "error", "replayed", "paused"]

    # Expect at least one trade (unless blocked by guardrails; in this test kill switch is off)
    count = await db.agent_trades.count_documents({})
    assert count >= 1

    t = await db.agent_trades.find_one({}, {"_id": 0})
    assert t.get("strategy") in ["MM", "MOM"]
    assert t.get("agent_id")
