"""Tests for Optimization Engine and Strategy-Agent Mapper."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.optimization_engine import (
    OptimizationEngine,
    OptimizationConfig,
    OptimizationResult,
    OptimizationJob,
    OptimizationStatus,
    ParameterRange,
    STRATEGY_PARAM_RANGES,
)
from services.strategy_agent_mapper import (
    StrategyAgentMapper,
    AgentType,
    StrategyMapping,
    AgentSuggestion,
    STRATEGY_AGENT_MAP,
    get_strategy_mapper,
)


class TestStrategyAgentMapper:
    """Test Strategy to Agent mapping service."""
    
    @pytest.fixture
    def mapper(self):
        return StrategyAgentMapper()
    
    def test_get_all_mappings(self, mapper):
        """Test getting all strategy mappings."""
        mappings = mapper.get_all_mappings()
        
        # Should have momentum, sma_crossover, mean_reversion, breakout + DCA
        assert len(mappings) >= 5
        
        strategy_names = [m["strategy"] for m in mappings]
        assert "momentum" in strategy_names
        assert "mean_reversion" in strategy_names
        assert "breakout" in strategy_names
        assert "dca" in strategy_names
    
    def test_mean_reversion_maps_to_grid(self, mapper):
        """Test mean_reversion maps to GRID agent."""
        mapping = mapper.get_mapping("mean_reversion")
        assert mapping is not None
        assert mapping.agent == AgentType.GRID
        assert mapping.confidence >= 80
    
    def test_breakout_maps_to_trend(self, mapper):
        """Test breakout maps to TREND agent."""
        mapping = mapper.get_mapping("breakout")
        assert mapping is not None
        assert mapping.agent == AgentType.TREND
    
    def test_momentum_maps_to_trend(self, mapper):
        """Test momentum maps to TREND agent."""
        mapping = mapper.get_mapping("momentum")
        assert mapping is not None
        assert mapping.agent == AgentType.TREND
    
    def test_sma_crossover_maps_to_trend(self, mapper):
        """Test sma_crossover maps to TREND agent."""
        mapping = mapper.get_mapping("sma_crossover")
        assert mapping is not None
        assert mapping.agent == AgentType.TREND
    
    def test_suggest_agent_positive_metrics(self, mapper):
        """Test agent suggestion with positive metrics."""
        metrics = {
            "total_return_pct": 25.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 15.0,
            "win_rate": 55.0,
            "profit_factor": 1.8,
            "total_trades": 30,
        }
        
        suggestion = mapper.suggest_agent_from_backtest("momentum", metrics, "BTC/USDT")
        
        assert suggestion.primary_agent == AgentType.TREND
        assert suggestion.confidence > 70
        assert len(suggestion.reasons) > 0
        assert len(suggestion.metrics_analysis) > 0
        assert "return" in suggestion.metrics_analysis
        assert "sharpe" in suggestion.metrics_analysis
    
    def test_suggest_agent_negative_metrics(self, mapper):
        """Test agent suggestion with negative metrics."""
        metrics = {
            "total_return_pct": -10.0,
            "sharpe_ratio": -0.5,
            "max_drawdown_pct": 35.0,
            "win_rate": 40.0,
            "profit_factor": 0.8,
            "total_trades": 20,
        }
        
        suggestion = mapper.suggest_agent_from_backtest("momentum", metrics, "BTC/USDT")
        
        assert suggestion.confidence < 80  # Lower confidence due to poor metrics
        assert len(suggestion.warnings) > 0
    
    def test_suggest_agent_unknown_strategy(self, mapper):
        """Test agent suggestion with unknown strategy."""
        suggestion = mapper.suggest_agent_from_backtest("unknown_strategy", {}, "BTC/USDT")
        
        assert suggestion.primary_agent == AgentType.DCA  # Safe fallback
        assert "Unknown strategy" in suggestion.warnings[0] or "no direct agent mapping" in suggestion.reasons[0]
    
    def test_suggested_params_included(self, mapper):
        """Test that recommended params are included in suggestion."""
        metrics = {
            "total_return_pct": 20.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 18.0,
            "win_rate": 52.0,
            "total_trades": 25,
        }
        
        suggestion = mapper.suggest_agent_from_backtest("mean_reversion", metrics, "ETH/USDT")
        
        assert "recommended_params" in suggestion.to_dict()
        assert "symbol" in suggestion.recommended_params
        assert suggestion.recommended_params["symbol"] == "ETH/USDT"


class TestOptimizationEngine:
    """Test Optimization Engine."""
    
    @pytest.fixture
    def engine(self):
        return OptimizationEngine(db=None)
    
    def test_generate_variations_momentum(self, engine):
        """Test parameter variation generation for momentum."""
        variations = engine._generate_variations("momentum", 10)
        
        assert len(variations) == 10
        # Check first variation is base params
        assert "oversold" in variations[0]
        assert "overbought" in variations[0]
    
    def test_generate_variations_sma_crossover(self, engine):
        """Test parameter variation generation for SMA crossover."""
        variations = engine._generate_variations("sma_crossover", 5)
        
        assert len(variations) == 5
        # Check constraint: short_period < long_period
        for v in variations:
            assert v.get("short_period", 10) < v.get("long_period", 30)
    
    def test_calculate_overfit_risk_no_overfit(self, engine):
        """Test overfit risk calculation with good consistency."""
        risk, reasons = engine._calculate_overfit_risk(
            train_return=20.0,
            test_return=18.0,
            train_sharpe=1.5,
            test_sharpe=1.3,
            train_trades=25,
            test_trades=12,
        )
        
        assert risk < 30  # Low risk
        assert "No significant overfitting signals" in reasons[0] or len(reasons) <= 2
    
    def test_calculate_overfit_risk_high_overfit(self, engine):
        """Test overfit risk calculation with clear overfitting."""
        risk, reasons = engine._calculate_overfit_risk(
            train_return=50.0,
            test_return=-5.0,
            train_sharpe=2.5,
            test_sharpe=0.2,
            train_trades=8,
            test_trades=3,
        )
        
        assert risk > 50  # High risk
        assert len(reasons) > 1
    
    def test_calculate_score(self, engine):
        """Test composite score calculation."""
        config = OptimizationConfig(
            strategy="momentum",
            symbol="BTC/USDT",
            start_date=datetime.now(timezone.utc) - timedelta(days=90),
            end_date=datetime.now(timezone.utc),
        )
        
        result = OptimizationResult(
            variation_id="test",
            params={"oversold": 30, "overbought": 70},
            train_return_pct=25.0,
            train_sharpe=1.5,
            train_max_drawdown_pct=12.0,
            train_win_rate=55.0,
            train_trades=20,
            test_return_pct=20.0,
            test_sharpe=1.2,
            test_max_drawdown_pct=15.0,
            test_win_rate=52.0,
            test_trades=10,
            overfit_risk=25.0,
            overfit_reasons=["Minor degradation"],
        )
        
        score = engine._calculate_score(result, config)
        
        assert score > 0  # Positive score for good results
    
    @pytest.mark.asyncio
    async def test_run_optimization_invalid_strategy(self, engine):
        """Test optimization with invalid strategy."""
        job = await engine.run_optimization(
            strategy="invalid_strategy",
            symbol="BTC/USDT",
            start_date=datetime.now(timezone.utc) - timedelta(days=60),
            end_date=datetime.now(timezone.utc),
            num_variations=5,
        )
        
        assert job.status == OptimizationStatus.FAILED
        assert "Unknown strategy" in job.error
    
    @pytest.mark.asyncio
    async def test_run_optimization_momentum(self, engine):
        """Test full optimization run with momentum strategy."""
        # Use longer date range to ensure enough trades
        job = await engine.run_optimization(
            strategy="momentum",
            symbol="BTC/USDT",
            start_date=datetime.now(timezone.utc) - timedelta(days=120),
            end_date=datetime.now(timezone.utc),
            initial_capital=10000.0,
            num_variations=10,  # More variations for better coverage
            train_ratio=0.7,
        )
        
        assert job.status == OptimizationStatus.COMPLETED
        # Results may be filtered by constraints, so just check it ran
        assert job.progress == 10
        
        # If we have results, verify they're ranked
        if len(job.results) > 0:
            for i, r in enumerate(job.results):
                assert r.rank == i + 1
            
            # Check overfit risk is calculated
            assert job.best_result is not None
            assert job.best_result.overfit_risk >= 0
            assert job.best_result.overfit_risk <= 100


class TestParameterRanges:
    """Test parameter ranges configuration."""
    
    def test_all_strategies_have_ranges(self):
        """Test all strategies have parameter ranges defined."""
        expected = ["momentum", "sma_crossover", "mean_reversion", "breakout"]
        
        for strategy in expected:
            assert strategy in STRATEGY_PARAM_RANGES
            assert len(STRATEGY_PARAM_RANGES[strategy]) > 0
    
    def test_parameter_range_validity(self):
        """Test parameter ranges have valid min/max/step."""
        for strategy, ranges in STRATEGY_PARAM_RANGES.items():
            for r in ranges:
                assert r.min_val < r.max_val, f"{strategy}.{r.name}: min >= max"
                assert r.step > 0, f"{strategy}.{r.name}: step <= 0"


class TestOptimizationResult:
    """Test OptimizationResult serialization."""
    
    def test_to_dict(self):
        """Test result serialization."""
        result = OptimizationResult(
            variation_id="test-123",
            params={"oversold": 25, "overbought": 75},
            train_return_pct=15.5,
            train_sharpe=1.2,
            train_max_drawdown_pct=10.5,
            train_win_rate=55.0,
            train_trades=20,
            test_return_pct=12.0,
            test_sharpe=1.0,
            test_max_drawdown_pct=12.0,
            test_win_rate=50.0,
            test_trades=8,
            overfit_risk=30.0,
            overfit_reasons=["Moderate degradation"],
            score=45.5,
            rank=1,
        )
        
        data = result.to_dict()
        
        assert data["variation_id"] == "test-123"
        assert data["params"]["oversold"] == 25
        assert data["train"]["return_pct"] == 15.5
        assert data["test"]["return_pct"] == 12.0
        assert data["overfit_risk"] == 30.0
        assert data["rank"] == 1
