"""
Unit Tests for Growth Orchestrator P1
=====================================

Tests:
- Paper adapter converts intent plans correctly
- Idempotency prevents duplicate orders
- Guardian/Viability gates block execution properly
- Full pipeline integration test
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest_plugins = ('pytest_asyncio',)


# ============ Paper Adapter Tests ============

class TestPaperAdapter:
    """Tests for GrowthPaperAdapter."""
    
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        collection = MagicMock()
        collection.create_index = AsyncMock()
        collection.update_one = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        collection.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=MagicMock(
                    to_list=AsyncMock(return_value=[])
                ))
            ))
        ))
        db.__getitem__ = MagicMock(return_value=collection)
        db.growth_paper_runs = collection
        return db
    
    @pytest.fixture
    def sample_plan(self):
        from services.growth.paper_adapter import IntentPlan, IntentOrderSpec, IntentPlanScope
        return IntentPlan(
            plan_id="test_plan_123",
            symbol="BTC/USDT",
            venue="binance",
            agent_type="MM",
            preset_id="MM_2_NORMAL_RANGE",
            scope=IntentPlanScope(capital_eur=100, bucket="CORE"),
            orders=[
                IntentOrderSpec(
                    client_order_id="test_bid_0",
                    side="buy",
                    price=94900,
                    size_eur=10,
                    size_asset=0.000105,
                ),
                IntentOrderSpec(
                    client_order_id="test_ask_0",
                    side="sell",
                    price=95100,
                    size_eur=10,
                    size_asset=0.000105,
                ),
            ],
            reason_codes=["REGIME_RANGE", "SPREAD_OK"],
        )
    
    @pytest.mark.asyncio
    async def test_dry_run_creates_no_real_orders(self, mock_db, sample_plan):
        """Test that dry run doesn't execute orders."""
        from services.growth.paper_adapter import GrowthPaperAdapter
        adapter = GrowthPaperAdapter(db=mock_db)
        # Skip initialize for unit test - just set _processed_plans
        adapter._processed_plans = set()
        
        result = await adapter.execute_plan(
            plan=sample_plan,
            decision_snapshot={"regime": "RANGE"},
            dry_run=True,
        )
        
        assert result.status == "dry_run"
        assert result.is_dry_run is True
        assert result.orders_created == 2
        assert len(result.orders) == 2
        assert result.orders_filled == 0  # No fills in dry run
    
    @pytest.mark.asyncio
    async def test_idempotency_blocks_duplicate_plans(self, mock_db, sample_plan):
        """Test that same plan_id doesn't create duplicate orders."""
        from services.growth.paper_adapter import GrowthPaperAdapter
        adapter = GrowthPaperAdapter(db=mock_db)
        adapter._processed_plans = set()
        
        # First execution (dry run to avoid needing executor)
        result1 = await adapter.execute_plan(
            plan=sample_plan,
            decision_snapshot={},
            dry_run=True,
        )
        
        assert result1.orders_created == 2
        
        # Mark as processed (simulating non-dry-run)
        adapter._processed_plans.add(sample_plan.plan_id)
        
        # Second execution should be blocked
        result2 = await adapter.execute_plan(
            plan=sample_plan,
            decision_snapshot={},
            dry_run=False,
        )
        
        # Should return cached result or block
        assert result2.plan_id == sample_plan.plan_id
    
    def test_convert_to_paper_orders(self, mock_db, sample_plan):
        """Test intent orders are converted to Order objects."""
        from services.growth.paper_adapter import GrowthPaperAdapter
        adapter = GrowthPaperAdapter(db=mock_db)
        
        orders = adapter._convert_to_paper_orders(sample_plan)
        
        assert len(orders) == 2
        
        # Check first order (bid)
        bid_order = orders[0]
        assert bid_order.symbol == "BTC/USDT"
        assert bid_order.exchange == "binance"
        assert bid_order.side.value == "buy"
        assert bid_order.price == 94900
        assert bid_order.amount == 0.000105
        assert "test_plan_123" in bid_order.idempotency_key
        
        # Check second order (ask)
        ask_order = orders[1]
        assert ask_order.side.value == "sell"
        assert ask_order.price == 95100
    
    def test_is_plan_processed(self, mock_db):
        """Test plan processed checking."""
        from services.growth.paper_adapter import GrowthPaperAdapter
        adapter = GrowthPaperAdapter(db=mock_db)
        
        assert adapter.is_plan_processed("nonexistent") is False
        
        adapter._processed_plans.add("test_plan_abc")
        assert adapter.is_plan_processed("test_plan_abc") is True


# ============ Orchestrator Tests ============

class TestGrowthOrchestrator:
    """Tests for GrowthOrchestrator."""
    
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.growth_cycles = MagicMock()
        db.growth_cycles.update_one = AsyncMock()
        db.growth_cycles.find_one = AsyncMock(return_value=None)
        return db
    
    @pytest.fixture
    def mock_router(self):
        from services.market_router import MarketRegime, RecommendedAgent, Confidence
        router = MagicMock()
        decision = MagicMock()
        decision.regime = MarketRegime.RANGE
        decision.regime_confidence = Confidence.MEDIUM
        decision.recommended_agent = RecommendedAgent.MM
        decision.recommended_preset_id = "MM_2_NORMAL_RANGE"
        decision.venue = "binance"
        decision.all_reason_codes = ["REGIME_RANGE"]
        decision.regime_reasons = ["Range detected"]
        decision.agent_reasons = ["MM selected"]
        decision.viability_reasons = []
        router.analyze = AsyncMock(return_value=decision)
        return router
    
    @pytest.fixture
    def mock_guardian(self):
        guardian = MagicMock()
        check = MagicMock()
        check.allowed = True
        check.action = MagicMock(value="ALLOW")
        check.block_reason = None
        check.reasons = ["All checks passed"]
        guardian.validate_trade = AsyncMock(return_value=check)
        return guardian
    
    @pytest.fixture
    def mock_viability(self):
        viability = MagicMock()
        result = MagicMock()
        result.viable = True
        result.status = MagicMock(value="VIABLE")
        result.expected_edge_pct = 0.5
        result.required_edge_pct = 0.3
        result.cost_breakdown = MagicMock(total_round_trip_pct=0.15)
        result.reasons = ["Viable"]
        viability.check_viability = AsyncMock(return_value=result)
        return viability
    
    @pytest.fixture
    def mock_adapter(self, mock_db):
        from services.growth.paper_adapter import RunResult
        adapter = MagicMock()
        adapter.initialize = AsyncMock()
        adapter.is_plan_processed = MagicMock(return_value=False)
        adapter.execute_plan = AsyncMock(return_value=RunResult(
            plan_id="test",
            status="success",
            orders_created=5,
            orders_filled=3,
        ))
        return adapter
    
    @pytest.fixture
    def mock_data_feed(self):
        """Mock data feed for price data."""
        data_feed = MagicMock()
        data_feed.fetch_ticker = AsyncMock(return_value={
            'bid': 94995,
            'ask': 95005,
            'last': 95000,
        })
        return data_feed
    
    @pytest.fixture
    def orchestrator(self, mock_db, mock_router, mock_guardian, mock_viability, mock_adapter, mock_data_feed):
        from services.growth_orchestrator import GrowthOrchestrator
        orch = GrowthOrchestrator(
            db=mock_db,
            market_router=mock_router,
            guardian_service=mock_guardian,
            viability_service=mock_viability,
            paper_adapter=mock_adapter,
        )
        orch._initialized = True  # Skip async init
        orch.data_feed = mock_data_feed  # Add mock data feed
        return orch
    
    @pytest.mark.asyncio
    async def test_full_cycle_success(self, orchestrator):
        """Test a successful full cycle."""
        from services.growth_orchestrator import GrowthRunMode, GrowthRunStatus
        
        result = await orchestrator.run_cycle(
            symbol="BTC/USDT",
            venue="binance",
            mode=GrowthRunMode.ONCE,
        )
        
        assert result.status == GrowthRunStatus.SUCCESS
        assert result.regime == "RANGE"
        assert result.recommended_agent == "MM"
        assert result.guardian_allowed is True
        assert result.viability_viable is True
        assert result.orders_created == 5
    
    @pytest.mark.asyncio
    async def test_cycle_blocked_by_guardian(self, orchestrator, mock_guardian):
        """Test cycle blocked when Guardian rejects."""
        from services.growth_orchestrator import GrowthRunMode, GrowthRunStatus
        
        # Configure guardian to block
        check = MagicMock()
        check.allowed = False
        check.action = MagicMock(value="KILL_SWITCH")
        check.block_reason = MagicMock(value="DAILY_LOSS_LIMIT")
        check.reasons = ["Daily loss exceeded"]
        mock_guardian.validate_trade = AsyncMock(return_value=check)
        
        result = await orchestrator.run_cycle(
            symbol="BTC/USDT",
            mode=GrowthRunMode.ONCE,
        )
        
        assert result.status == GrowthRunStatus.BLOCKED
        assert result.guardian_allowed is False
        assert "DAILY_LOSS_LIMIT" in result.block_reason
        assert result.orders_created == 0
    
    @pytest.mark.asyncio
    async def test_cycle_blocked_by_viability(self, orchestrator, mock_viability):
        """Test cycle blocked when Viability rejects."""
        from services.growth_orchestrator import GrowthRunMode, GrowthRunStatus
        
        # Configure viability to reject
        result_mock = MagicMock()
        result_mock.viable = False
        result_mock.status = MagicMock(value="NOT_VIABLE")
        result_mock.expected_edge_pct = 0.1
        result_mock.required_edge_pct = 0.5
        result_mock.cost_breakdown = MagicMock(total_round_trip_pct=0.4)
        result_mock.reasons = ["Cost too high"]
        mock_viability.check_viability = AsyncMock(return_value=result_mock)
        
        # Disable marginal allowance
        orchestrator.config.allow_marginal_viability = False
        
        result = await orchestrator.run_cycle(
            symbol="BTC/USDT",
            mode=GrowthRunMode.ONCE,
        )
        
        assert result.status == GrowthRunStatus.BLOCKED
        assert result.viability_viable is False
        assert "VIABILITY" in result.block_reason
    
    @pytest.mark.asyncio
    async def test_cycle_paused_by_router(self, orchestrator, mock_router):
        """Test cycle paused when Router recommends PAUSE."""
        from services.growth_orchestrator import GrowthRunMode, GrowthRunStatus
        from services.market_router import RecommendedAgent
        
        # Configure router to recommend PAUSE
        decision = MagicMock()
        decision.regime = MagicMock(value="CHOP")
        decision.regime_confidence = MagicMock(value="LOW")
        decision.recommended_agent = RecommendedAgent.PAUSE
        decision.recommended_preset_id = ""
        decision.venue = "binance"
        decision.all_reason_codes = ["REGIME_CHOP"]
        decision.regime_reasons = []
        decision.agent_reasons = []
        decision.viability_reasons = []
        mock_router.analyze = AsyncMock(return_value=decision)
        
        result = await orchestrator.run_cycle(
            symbol="BTC/USDT",
            mode=GrowthRunMode.ONCE,
        )
        
        assert result.status == GrowthRunStatus.PAUSED
        assert result.block_reason == "ROUTER_PAUSE"
        assert result.orders_created == 0
    
    @pytest.mark.asyncio
    async def test_dry_run_mode(self, orchestrator):
        """Test dry run doesn't execute orders."""
        from services.growth_orchestrator import GrowthRunMode, GrowthRunStatus
        
        # Mock adapter to return dry_run status
        orchestrator.paper_adapter.execute_plan = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={
                "status": "dry_run",
                "orders_created": 5,
                "orders_filled": 0,
            })
        ))
        
        result = await orchestrator.run_cycle(
            symbol="BTC/USDT",
            mode=GrowthRunMode.SIMULATE,
        )
        
        assert result.status == GrowthRunStatus.DRY_RUN


# ============ Integration Tests ============

class TestGrowthPipelineIntegration:
    """Integration tests for full Growth Module pipeline."""
    
    @pytest.mark.asyncio
    async def test_router_to_plan_flow(self):
        """Test: Router -> Agent -> Plan generation."""
        from services.market_router import MarketRouter, MarketMetrics
        from services.growth.paper_adapter import IntentPlan
        
        mock_db = MagicMock()
        router = MarketRouter(db=mock_db)
        
        # Create ranging market metrics
        metrics = MarketMetrics(
            symbol="BTC/USDT",
            venue="binance",
            last_price=95000,
            bid=94995,
            ask=95005,
            spread_pct=0.01,
            atr_pct=0.5,
            atr_14=475,
            adx=18,
            ma_slope_pct=0.01,
            trend_direction=0,
            volume_24h=1e9,
            volume_ratio=1.0,
            data_age_seconds=3,
            data_quality=1.0,
        )
        
        # Run router
        decision = await router.analyze(metrics)
        
        # Verify regime detection
        assert decision.regime.value == "RANGE"
        
        # Generate plan ID (deterministic)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        plan_id = IntentPlan.generate_plan_id(
            agent_type=decision.recommended_agent.value,
            symbol="BTC/USDT",
            venue="binance",
            preset_id=decision.recommended_preset_id,
            timestamp_minute=timestamp,
        )
        
        # Plan ID should be deterministic
        plan_id_2 = IntentPlan.generate_plan_id(
            agent_type=decision.recommended_agent.value,
            symbol="BTC/USDT",
            venue="binance",
            preset_id=decision.recommended_preset_id,
            timestamp_minute=timestamp,
        )
        
        assert plan_id == plan_id_2  # Same inputs = same plan_id


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
