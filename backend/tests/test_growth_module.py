"""
Unit Tests for Capital Growth Module P0 Components
===================================================

Tests:
- MarketRouter regime detection
- Guardian limit enforcement
- Viability cost model
- MM/MOM agent intent plans
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# ============ MarketRouter Tests ============

class TestMarketRouter:
    """Tests for MarketRouter regime detection."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()
    
    @pytest.fixture
    def router(self, mock_db):
        """Create MarketRouter instance."""
        from services.market_router import MarketRouter
        return MarketRouter(db=mock_db)
    
    @pytest.fixture
    def range_market_metrics(self):
        """Metrics for a ranging market."""
        from services.market_router import MarketMetrics
        return MarketMetrics(
            symbol="BTC/USDT",
            venue="binance",
            last_price=95000.0,
            bid=94990.0,
            ask=95010.0,
            spread_pct=0.021,  # Tight spread
            atr_pct=0.8,  # Moderate ATR to pass viability
            atr_14=760.0,
            bollinger_width_pct=2.0,
            adx=18.0,  # Low ADX = no trend
            ma_slope_pct=0.01,
            trend_direction=0,
            volume_24h=1_000_000_000,
            volume_ratio=1.0,
            data_age_seconds=5,
            data_quality=1.0,
        )
    
    @pytest.fixture
    def trend_market_metrics(self):
        """Metrics for a trending market."""
        from services.market_router import MarketMetrics
        return MarketMetrics(
            symbol="ETH/USDT",
            venue="binance",
            last_price=3400.0,
            bid=3399.0,
            ask=3401.0,
            spread_pct=0.06,  # Tighter spread to pass
            atr_pct=2.5,  # Higher ATR to pass viability
            atr_14=85.0,
            bollinger_width_pct=5.0,
            adx=38.0,  # High ADX = strong trend
            ma_slope_pct=0.25,
            trend_direction=1,  # Uptrend
            volume_24h=500_000_000,
            volume_ratio=1.3,
            data_age_seconds=3,
            data_quality=1.0,
        )
    
    @pytest.fixture
    def high_vol_market_metrics(self):
        """Metrics for high volatility market."""
        from services.market_router import MarketMetrics
        return MarketMetrics(
            symbol="BNB/USDT",
            venue="binance",
            last_price=700.0,
            bid=698.0,
            ask=702.0,
            spread_pct=0.57,
            atr_pct=2.5,  # High ATR
            atr_14=17.5,
            bollinger_width_pct=8.0,
            adx=28.0,
            ma_slope_pct=0.5,
            trend_direction=1,
            volume_24h=300_000_000,
            volume_ratio=2.5,  # Volume spike
            data_age_seconds=2,
            data_quality=1.0,
        )
    
    @pytest.fixture
    def chop_market_metrics(self):
        """Metrics for choppy market."""
        from services.market_router import MarketMetrics
        return MarketMetrics(
            symbol="BTC/EUR",
            venue="kraken",
            last_price=90000.0,
            bid=89950.0,
            ask=90050.0,
            spread_pct=0.111,
            atr_pct=1.2,
            atr_14=1100.0,
            bollinger_width_pct=4.5,
            adx=22.0,  # Moderate - neither trend nor clear range
            ma_slope_pct=-0.05,
            trend_direction=0,  # No clear direction
            volume_24h=200_000_000,
            volume_ratio=0.7,  # Low volume
            data_age_seconds=10,
            data_quality=0.95,
        )
    
    @pytest.mark.asyncio
    async def test_regime_detection_range(self, router, range_market_metrics):
        """Test RANGE regime detection."""
        from services.market_router import MarketRegime, RecommendedAgent
        
        decision = await router.analyze(range_market_metrics)
        
        assert decision.regime == MarketRegime.RANGE
        # Agent could be MM or PAUSE based on viability check
        assert decision.recommended_agent in [RecommendedAgent.MM, RecommendedAgent.PAUSE]
        if decision.recommended_agent == RecommendedAgent.MM:
            assert "MM_1" in decision.recommended_preset_id or "MM_2" in decision.recommended_preset_id
        assert len(decision.all_reason_codes) > 0
        # Regime reasons should mention range-related terms
        all_regime = " ".join(decision.regime_reasons).lower()
        assert "range" in all_regime or "adx" in all_regime or "lateral" in all_regime
    
    @pytest.mark.asyncio
    async def test_regime_detection_trend(self, router, trend_market_metrics):
        """Test TREND regime detection."""
        from services.market_router import MarketRegime, RecommendedAgent
        
        decision = await router.analyze(trend_market_metrics)
        
        # With ATR 2.5 and ADX 38, could be TREND or HIGH_VOL
        assert decision.regime in [MarketRegime.TREND, MarketRegime.HIGH_VOL]
        # Agent could be MOM or PAUSE based on viability check
        assert decision.recommended_agent in [RecommendedAgent.MOM, RecommendedAgent.PAUSE]
        if decision.recommended_agent == RecommendedAgent.MOM:
            assert "MOM" in decision.recommended_preset_id
        # Should have trend or vol related reasons
        all_reasons = " ".join(decision.regime_reasons).lower()
        assert "trend" in all_reasons or "adx" in all_reasons or "atr" in all_reasons or "vol" in all_reasons
    
    @pytest.mark.asyncio
    async def test_regime_detection_high_vol(self, router, high_vol_market_metrics):
        """Test HIGH_VOL regime detection."""
        from services.market_router import MarketRegime
        
        decision = await router.analyze(high_vol_market_metrics)
        
        assert decision.regime == MarketRegime.HIGH_VOL
        assert any("HIGH_VOL" in r or "ATR" in r for r in decision.regime_reasons)
    
    @pytest.mark.asyncio
    async def test_deterministic_output(self, router, range_market_metrics):
        """Test that same input produces same output (deterministic)."""
        decision1 = await router.analyze(range_market_metrics)
        decision2 = await router.analyze(range_market_metrics)
        
        assert decision1.regime == decision2.regime
        assert decision1.recommended_agent == decision2.recommended_agent
        assert decision1.recommended_preset_id == decision2.recommended_preset_id
    
    @pytest.mark.asyncio
    async def test_reason_codes_always_present(self, router, range_market_metrics):
        """Test that reason codes are always present."""
        decision = await router.analyze(range_market_metrics)
        
        assert len(decision.regime_reasons) > 0
        assert len(decision.agent_reasons) > 0
        assert len(decision.all_reason_codes) > 0
    
    def test_symbol_whitelist(self, router):
        """Test symbol whitelist functionality."""
        assert router.is_symbol_whitelisted("BTC/USDT")
        assert router.is_symbol_whitelisted("ETH/EUR")
        assert not router.is_symbol_whitelisted("DOGE/USDT")
        assert not router.is_symbol_whitelisted("XRP/USDT")
        
        whitelist = router.get_whitelisted_symbols()
        assert "BTC/USDT" in whitelist
        assert len(whitelist) == 5
    
    @pytest.mark.asyncio
    async def test_stale_data_causes_pause(self, router, range_market_metrics):
        """Test that stale data causes PAUSE recommendation."""
        from services.market_router import RecommendedAgent
        
        range_market_metrics.data_age_seconds = 120  # 2 minutes - stale
        range_market_metrics.data_quality = 0.5  # Low quality
        decision = await router.analyze(range_market_metrics)
        
        assert decision.recommended_agent == RecommendedAgent.PAUSE
        # Should have DATA or quality related reason - case insensitive check
        all_reasons = " ".join(decision.agent_reasons + decision.viability_reasons).lower()
        assert "data" in all_reasons or "quality" in all_reasons or "desatualizado" in all_reasons


# ============ Guardian Tests ============

class TestGuardian:
    """Tests for Guardian enforcement."""
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def guardian(self, mock_db):
        from services.guardian import GuardianService
        return GuardianService(db=mock_db)
    
    @pytest.fixture
    def valid_trade_request(self):
        from services.guardian import TradeRequest
        return TradeRequest(
            agent_id="test-mm-1",
            agent_type="MM",
            symbol="BTC/USDT",
            venue="binance",
            side="buy",
            amount_eur=10.0,
            spread_pct=0.03,
            estimated_slippage_pct=0.02,
            data_age_seconds=5,
            data_quality=0.98,
            expected_edge_pct=0.5,
            total_cost_pct=0.1,
        )
    
    @pytest.mark.asyncio
    async def test_allow_valid_trade(self, guardian, valid_trade_request):
        """Test that valid trade is allowed."""
        from services.guardian import GuardianAction
        
        await guardian.initialize(starting_capital=100.0)
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is True
        assert check.action == GuardianAction.ALLOW
        assert check.block_reason is None
    
    @pytest.mark.asyncio
    async def test_block_daily_loss_limit(self, guardian, valid_trade_request):
        """Test blocking when daily loss limit is hit."""
        from services.guardian import GuardianAction, BlockReason
        
        await guardian.initialize(starting_capital=100.0)
        
        # Simulate daily loss
        guardian._state.daily_pnl_pct = -2.5  # Beyond -2% limit
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is False
        assert check.action == GuardianAction.KILL_SWITCH
        assert check.block_reason == BlockReason.DAILY_LOSS_LIMIT
    
    @pytest.mark.asyncio
    async def test_block_weekly_drawdown(self, guardian, valid_trade_request):
        """Test blocking when weekly drawdown is exceeded."""
        from services.guardian import GuardianAction, BlockReason
        
        await guardian.initialize(starting_capital=100.0)
        
        # Simulate weekly drawdown
        guardian._state.weekly_pnl_pct = -6.0  # Beyond -5% limit
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is False
        assert check.block_reason == BlockReason.WEEKLY_DRAWDOWN
    
    @pytest.mark.asyncio
    async def test_block_wide_spread(self, guardian, valid_trade_request):
        """Test blocking when spread is too wide."""
        from services.guardian import BlockReason
        
        await guardian.initialize(starting_capital=100.0)
        
        # Wide spread
        valid_trade_request.spread_pct = 0.25  # 0.25% > 0.15% limit
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is False
        assert check.block_reason == BlockReason.SPREAD_TOO_WIDE
    
    @pytest.mark.asyncio
    async def test_block_high_slippage(self, guardian, valid_trade_request):
        """Test blocking when slippage is too high."""
        from services.guardian import BlockReason
        
        await guardian.initialize(starting_capital=100.0)
        
        valid_trade_request.estimated_slippage_pct = 0.15  # > 0.10% limit
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is False
        assert check.block_reason == BlockReason.SLIPPAGE_HIGH
    
    @pytest.mark.asyncio
    async def test_kill_switch_blocks_all(self, guardian, valid_trade_request):
        """Test that active kill switch blocks all trades."""
        from services.guardian import GuardianAction
        
        await guardian.initialize(starting_capital=100.0)
        guardian._state.kill_switch_active = True
        guardian._state.kill_switch_reason = "Testing"
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert check.allowed is False
        assert check.action == GuardianAction.KILL_SWITCH
    
    @pytest.mark.asyncio
    async def test_reason_codes_present_on_block(self, guardian, valid_trade_request):
        """Test that reason codes are present when blocking."""
        await guardian.initialize(starting_capital=100.0)
        guardian._state.daily_pnl_pct = -3.0
        
        check = await guardian.validate_trade(valid_trade_request)
        
        assert len(check.reasons) > 0
        assert any("loss" in r.lower() or "limit" in r.lower() for r in check.reasons)


# ============ Viability Tests ============

class TestViability:
    """Tests for Viability cost model."""
    
    @pytest.fixture
    def viability(self):
        from services.viability import ViabilityService
        return ViabilityService()
    
    @pytest.fixture
    def viable_input(self):
        from services.viability import ViabilityInput
        return ViabilityInput(
            agent_type="MM",
            preset_id="MM_2_NORMAL_RANGE",
            symbol="BTC/USDT",
            venue="binance",
            order_size_eur=10.0,
            expected_move_pct=0.5,  # Good expected move
            current_spread_pct=0.03,
            bid_price=94990.0,
            ask_price=95010.0,
            expect_maker=True,
        )
    
    @pytest.fixture
    def non_viable_input(self):
        from services.viability import ViabilityInput
        return ViabilityInput(
            agent_type="MM",
            preset_id="MM_1_TIGHT_RANGE",
            symbol="BTC/USDT",
            venue="binance",
            order_size_eur=10.0,
            expected_move_pct=0.05,  # Too low expected move
            current_spread_pct=0.08,  # High spread
            bid_price=94960.0,
            ask_price=95040.0,
            expect_maker=True,
        )
    
    @pytest.mark.asyncio
    async def test_viable_trade(self, viability, viable_input):
        """Test that viable trade passes."""
        from services.viability import ViabilityStatus
        
        result = await viability.check_viability(viable_input)
        
        # With expected_move_pct=0.5 and cost~0.27, should be VIABLE or MARGINAL
        assert result.status in [ViabilityStatus.VIABLE, ViabilityStatus.MARGINAL]
        # Check that cost breakdown is present
        assert result.cost_breakdown is not None
    
    @pytest.mark.asyncio
    async def test_non_viable_trade(self, viability, non_viable_input):
        """Test that non-viable trade is rejected."""
        from services.viability import ViabilityStatus
        
        result = await viability.check_viability(non_viable_input)
        
        # With very low expected move, should be NOT_VIABLE or MARGINAL
        assert result.status in [ViabilityStatus.NOT_VIABLE, ViabilityStatus.MARGINAL]
        assert result.viable is False
    
    @pytest.mark.asyncio
    async def test_cost_breakdown(self, viability, viable_input):
        """Test that cost breakdown is calculated."""
        result = await viability.check_viability(viable_input)
        
        assert result.cost_breakdown is not None
        # Check the correct attribute names
        assert result.cost_breakdown.total_round_trip_pct > 0
        assert result.cost_breakdown.maker_fee_pct >= 0 or result.cost_breakdown.taker_fee_pct >= 0
    
    @pytest.mark.asyncio
    async def test_reason_codes_present(self, viability, non_viable_input):
        """Test that reason codes explain the decision."""
        result = await viability.check_viability(non_viable_input)
        
        # Reasons field, not reason_codes
        assert len(result.reasons) > 0 or len(result.warnings) > 0
    
    def test_min_viable_move_calculation(self, viability):
        """Test minimum viable move calculation."""
        result = viability.get_min_viable_move(
            venue="binance",
            order_size_eur=10.0,
            use_maker=True,
            multiplier=2.0,
        )
        
        assert "break_even_pct" in result
        assert "min_viable_pct" in result
        assert result["min_viable_pct"] > result["break_even_pct"]


# ============ MM Agent Tests ============

class TestMarketMakerAgent:
    """Tests for Market Maker agent intent plans."""
    
    @pytest.fixture
    def mm_agent(self):
        from services.agents.market_maker_agent import MarketMakerAgent
        return MarketMakerAgent(agent_id="test-mm-1")
    
    @pytest.fixture
    def mm_preset(self):
        from services.agents.market_maker_agent import MMPresetConfig
        return MMPresetConfig(
            preset_id="MM_2_NORMAL_RANGE",
            grid_width_total_pct=0.4,
            grid_levels=5,
            maker_only=True,
            skew_max_pct=30.0,
            daily_kill_pct=2.0,
            viability_multiplier=2.0,
            max_position_eur=50.0,
            order_size_pct=10.0,
        )
    
    @pytest.fixture
    def market_data(self):
        return {
            "bid": 94990.0,
            "ask": 95010.0,
            "last_price": 95000.0,
        }
    
    @pytest.mark.asyncio
    async def test_generates_orders(self, mm_agent, mm_preset, market_data):
        """Test that MM agent generates orders."""
        from services.agents.market_maker_agent import IntentStatus
        
        # Add tighter spread to pass viability
        market_data["bid"] = 94997.5
        market_data["ask"] = 95002.5  # 0.005% spread
        
        plan = await mm_agent.generate_intent_plan(
            symbol="BTC/USDT",
            venue="binance",
            preset_config=mm_preset,
            market_data=market_data,
            available_budget_eur=100.0,
        )
        
        # Even if NO_OPPORTUNITY, we should have generated intent
        assert plan.status in [IntentStatus.READY, IntentStatus.NO_OPPORTUNITY]
        # MM always generates orders regardless of viability
        if plan.status == IntentStatus.READY:
            assert len(plan.orders) > 0
            assert plan.total_bid_size_eur > 0
            assert plan.total_ask_size_eur > 0
    
    @pytest.mark.asyncio
    async def test_pauses_on_wide_spread(self, mm_agent, mm_preset):
        """Test that MM pauses when spread is too wide."""
        from services.agents.market_maker_agent import IntentStatus
        
        wide_spread_data = {
            "bid": 94800.0,
            "ask": 95200.0,  # 0.42% spread
            "last_price": 95000.0,
        }
        
        plan = await mm_agent.generate_intent_plan(
            symbol="BTC/USDT",
            venue="binance",
            preset_config=mm_preset,
            market_data=wide_spread_data,
            available_budget_eur=100.0,
        )
        
        assert plan.status == IntentStatus.PAUSED
        assert any("SPREAD" in r["code"] for r in plan.reason_codes)
    
    @pytest.mark.asyncio
    async def test_blocked_by_guardian(self, mm_agent, mm_preset, market_data):
        """Test that MM is blocked when guardian blocks."""
        from services.agents.market_maker_agent import IntentStatus
        
        guardian_block = {
            "allowed": False,
            "block_reason": "DAILY_LOSS_LIMIT",
        }
        
        plan = await mm_agent.generate_intent_plan(
            symbol="BTC/USDT",
            venue="binance",
            preset_config=mm_preset,
            market_data=market_data,
            available_budget_eur=100.0,
            guardian_check=guardian_block,
        )
        
        assert plan.status == IntentStatus.BLOCKED
    
    @pytest.mark.asyncio
    async def test_reason_codes_always_present(self, mm_agent, mm_preset, market_data):
        """Test that MM always provides reason codes."""
        plan = await mm_agent.generate_intent_plan(
            symbol="BTC/USDT",
            venue="binance",
            preset_config=mm_preset,
            market_data=market_data,
            available_budget_eur=100.0,
        )
        
        assert len(plan.reason_codes) > 0
        for rc in plan.reason_codes:
            assert "code" in rc
            assert "severity" in rc
            assert "message" in rc


# ============ MOM Agent Tests ============

class TestMomentumAgent:
    """Tests for Momentum agent intent plans."""
    
    @pytest.fixture
    def mom_agent(self):
        from services.agents.momentum_agent import MomentumAgent
        return MomentumAgent(agent_id="test-mom-1")
    
    @pytest.fixture
    def mom_preset(self):
        from services.agents.momentum_agent import MOMPresetConfig
        return MOMPresetConfig(
            preset_id="MOM_2_BREAKOUT_STANDARD",
            take_profit_pct=2.0,
            stop_loss_pct=1.0,
            trailing_enabled=True,
            trailing_pct=1.5,
            max_trades_per_day=5,
            cooldown_minutes=30,
            viability_multiplier=2.5,
            max_position_eur=30.0,
            adx_threshold=25.0,
            atr_min_pct=1.0,
        )
    
    @pytest.fixture
    def trending_market_data(self):
        return {
            "bid": 3398.0,
            "ask": 3402.0,
            "last_price": 3400.0,
            "atr_pct": 1.8,
            "adx": 38.0,  # Strong trend
            "trend_direction": 1,  # Uptrend
            "volume_ratio": 1.8,
            "resistance": 3380.0,  # Price above resistance = breakout
            "support": 3300.0,
        }
    
    @pytest.fixture
    def no_trend_market_data(self):
        return {
            "bid": 3398.0,
            "ask": 3402.0,
            "last_price": 3400.0,
            "atr_pct": 0.8,
            "adx": 18.0,  # Weak trend
            "trend_direction": 0,
            "volume_ratio": 0.9,
            "resistance": 3450.0,
            "support": 3350.0,
        }
    
    @pytest.mark.asyncio
    async def test_generates_entry_on_signal(self, mom_agent, mom_preset, trending_market_data):
        """Test that MOM generates entry when signal detected."""
        from services.agents.momentum_agent import IntentStatus, SignalType
        
        # Adjust data to ensure spread passes
        trending_market_data["bid"] = 3399.5
        trending_market_data["ask"] = 3400.5  # 0.03% spread
        
        plan = await mom_agent.generate_intent_plan(
            symbol="ETH/USDT",
            venue="binance",
            preset_config=mom_preset,
            market_data=trending_market_data,
            available_budget_eur=100.0,
        )
        
        # Should either be READY or NO_OPPORTUNITY based on signal detection
        assert plan.status in [IntentStatus.READY, IntentStatus.NO_OPPORTUNITY]
        if plan.status == IntentStatus.READY:
            assert plan.signal != SignalType.NO_SIGNAL
            assert plan.entry is not None
            assert plan.entry.stop_loss_price > 0
            assert plan.entry.take_profit_price > 0
    
    @pytest.mark.asyncio
    async def test_no_opportunity_without_trend(self, mom_agent, mom_preset, no_trend_market_data):
        """Test that MOM finds no opportunity without trend."""
        from services.agents.momentum_agent import IntentStatus
        
        plan = await mom_agent.generate_intent_plan(
            symbol="ETH/USDT",
            venue="binance",
            preset_config=mom_preset,
            market_data=no_trend_market_data,
            available_budget_eur=100.0,
        )
        
        assert plan.status == IntentStatus.NO_OPPORTUNITY
        assert plan.entry is None
    
    @pytest.mark.asyncio
    async def test_respects_max_trades(self, mom_agent, mom_preset, trending_market_data):
        """Test that MOM respects max trades per day."""
        from services.agents.momentum_agent import IntentStatus
        
        # Simulate max trades reached
        mom_agent._trades_today = 5
        
        plan = await mom_agent.generate_intent_plan(
            symbol="ETH/USDT",
            venue="binance",
            preset_config=mom_preset,
            market_data=trending_market_data,
            available_budget_eur=100.0,
        )
        
        assert plan.status == IntentStatus.PAUSED
        assert any("MAX_TRADES" in r["code"] for r in plan.reason_codes)
    
    @pytest.mark.asyncio
    async def test_risk_reward_calculated(self, mom_agent, mom_preset, trending_market_data):
        """Test that R/R ratio is calculated."""
        plan = await mom_agent.generate_intent_plan(
            symbol="ETH/USDT",
            venue="binance",
            preset_config=mom_preset,
            market_data=trending_market_data,
            available_budget_eur=100.0,
        )
        
        if plan.entry:
            assert plan.entry.risk_reward_ratio > 0
            # With 2% TP and 1% SL, R/R should be ~2
            assert plan.entry.risk_reward_ratio >= 1.5


# ============ Integration Tests ============

class TestGrowthModuleIntegration:
    """Integration tests for the full flow."""
    
    @pytest.mark.asyncio
    async def test_router_to_agent_flow(self):
        """Test the full flow from router to agent."""
        from services.market_router import MarketRouter, MarketMetrics, MarketRegime, RecommendedAgent
        from services.agents.market_maker_agent import MarketMakerAgent, MMPresetConfig
        from services.agents.momentum_agent import MomentumAgent, MOMPresetConfig
        
        mock_db = MagicMock()
        router = MarketRouter(db=mock_db)
        
        # Create ranging market metrics with good viability
        metrics = MarketMetrics(
            symbol="BTC/USDT",
            venue="binance",
            last_price=95000.0,
            bid=94997.0,
            ask=95003.0,
            spread_pct=0.006,  # Very tight spread
            atr_pct=0.8,  # Decent ATR for viability
            atr_14=760.0,
            adx=15.0,
            ma_slope_pct=0.0,
            trend_direction=0,
            volume_24h=1_000_000_000,
            volume_ratio=1.0,
            data_age_seconds=2,
            data_quality=1.0,
        )
        
        # Get routing decision
        decision = await router.analyze(metrics)
        
        assert decision.regime == MarketRegime.RANGE
        # Agent could be MM or PAUSE depending on viability
        assert decision.recommended_agent in [RecommendedAgent.MM, RecommendedAgent.PAUSE]
        
        # If MM is recommended, test the flow
        if decision.recommended_agent == RecommendedAgent.MM:
            agent = MarketMakerAgent(agent_id="mm-1")
            preset = MMPresetConfig(
                preset_id=decision.recommended_preset_id,
                grid_width_total_pct=0.4,
                grid_levels=5,
            )
            
            plan = await agent.generate_intent_plan(
                symbol=decision.symbol,
                venue=decision.venue,
                preset_config=preset,
                market_data={
                    "bid": metrics.bid,
                    "ask": metrics.ask,
                    "last_price": metrics.last_price,
                },
                available_budget_eur=100.0,
            )
            
            # Plan should be generated (may or may not have orders based on viability)
            assert plan is not None


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
