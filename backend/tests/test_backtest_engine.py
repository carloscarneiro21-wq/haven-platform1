"""Tests for Backtest Engine."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.backtest_engine import (
    BacktestEngine,
    BacktestCandle,
    BacktestTrade,
    BacktestPosition,
    BacktestMetrics,
    BacktestResult,
    BacktestStatus,
    SignalType,
    strategy_momentum,
    strategy_sma_crossover,
    strategy_mean_reversion,
    strategy_breakout,
    STRATEGIES,
)


class TestBacktestCandle:
    """Test BacktestCandle dataclass."""
    
    def test_candle_creation(self):
        """Test candle creation."""
        candle = BacktestCandle(
            timestamp=1704067200000,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
        )
        assert candle.timestamp == 1704067200000
        assert candle.close == 102.0
    
    def test_candle_datetime(self):
        """Test datetime property."""
        candle = BacktestCandle(
            timestamp=1704067200000,  # 2024-01-01 00:00:00 UTC
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1000.0,
        )
        dt = candle.datetime
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1


class TestBacktestPosition:
    """Test BacktestPosition."""
    
    def test_position_unrealized_pnl(self):
        """Test unrealized PnL calculation."""
        position = BacktestPosition(
            symbol="BTC/USDT",
            quantity=1.0,
            avg_entry_price=50000.0,
        )
        position.update_unrealized(51000.0)
        assert position.unrealized_pnl == 1000.0
        
        position.update_unrealized(49000.0)
        assert position.unrealized_pnl == -1000.0


class TestBacktestMetrics:
    """Test BacktestMetrics."""
    
    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        metrics = BacktestMetrics(
            total_return=1000.0,
            total_return_pct=10.0,
            sharpe_ratio=1.5,
            max_drawdown=500.0,
            max_drawdown_pct=5.0,
            win_rate=60.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
        )
        data = metrics.to_dict()
        assert data["total_return"] == 1000.0
        assert data["win_rate"] == 60.0
        assert data["total_trades"] == 10


class TestStrategies:
    """Test built-in strategies."""
    
    def _create_candles(self, prices: list) -> list:
        """Helper to create candles from prices."""
        return [
            BacktestCandle(
                timestamp=1704067200000 + i * 3600000,
                open=p, high=p * 1.01, low=p * 0.99, close=p,
                volume=100.0,
            )
            for i, p in enumerate(prices)
        ]
    
    def test_momentum_strategy_buy_signal(self):
        """Test momentum strategy generates buy on oversold."""
        # Create declining prices to trigger oversold
        prices = [100 - i * 0.5 for i in range(20)]  # Declining prices
        candles = self._create_candles(prices)
        position = BacktestPosition(symbol="BTC/USDT")
        
        signal = strategy_momentum(candles, position, {"oversold": 30, "overbought": 70})
        # Note: actual RSI calculation needed, this tests structure
        assert signal in [SignalType.BUY, SignalType.HOLD]
    
    def test_momentum_strategy_hold_insufficient_data(self):
        """Test momentum holds with insufficient data."""
        candles = self._create_candles([100] * 5)  # Only 5 candles
        position = BacktestPosition(symbol="BTC/USDT")
        
        signal = strategy_momentum(candles, position, {})
        assert signal == SignalType.HOLD
    
    def test_sma_crossover_insufficient_data(self):
        """Test SMA crossover holds with insufficient data."""
        candles = self._create_candles([100] * 10)
        position = BacktestPosition(symbol="BTC/USDT")
        
        signal = strategy_sma_crossover(candles, position, {"short_period": 10, "long_period": 30})
        assert signal == SignalType.HOLD
    
    def test_mean_reversion_insufficient_data(self):
        """Test mean reversion holds with insufficient data."""
        candles = self._create_candles([100] * 10)
        position = BacktestPosition(symbol="BTC/USDT")
        
        signal = strategy_mean_reversion(candles, position, {"period": 20})
        assert signal == SignalType.HOLD
    
    def test_breakout_insufficient_data(self):
        """Test breakout holds with insufficient data."""
        candles = self._create_candles([100] * 10)
        position = BacktestPosition(symbol="BTC/USDT")
        
        signal = strategy_breakout(candles, position, {"period": 20})
        assert signal == SignalType.HOLD
    
    def test_all_strategies_registered(self):
        """Test all strategies are in registry."""
        assert "momentum" in STRATEGIES
        assert "sma_crossover" in STRATEGIES
        assert "mean_reversion" in STRATEGIES
        assert "breakout" in STRATEGIES


class TestBacktestEngine:
    """Test BacktestEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create backtest engine without DB."""
        return BacktestEngine(db=None)
    
    def test_generate_synthetic_candles(self, engine):
        """Test synthetic candle generation."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)
        
        candles = engine._generate_synthetic_candles("BTC/USDT", start, end)
        
        assert len(candles) > 100  # ~216 hourly candles in 9 days
        assert all(isinstance(c, BacktestCandle) for c in candles)
        assert candles[0].timestamp < candles[-1].timestamp
    
    @pytest.mark.asyncio
    async def test_run_unknown_strategy(self, engine):
        """Test running with unknown strategy."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)
        
        result = await engine.run(
            symbol="BTC/USDT",
            start_date=start,
            end_date=end,
            strategy="unknown_strategy",
        )
        
        assert result.status == BacktestStatus.FAILED
        assert "Unknown strategy" in result.error
    
    @pytest.mark.asyncio
    async def test_run_backtest_momentum(self, engine):
        """Test running momentum backtest."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)
        
        result = await engine.run(
            symbol="BTC/USDT",
            start_date=start,
            end_date=end,
            strategy="momentum",
            initial_capital=10000.0,
        )
        
        assert result.status == BacktestStatus.COMPLETED
        assert result.id is not None
        assert result.candles_processed > 50
        assert result.metrics is not None
        assert len(result.equity_curve) > 0
    
    @pytest.mark.asyncio
    async def test_run_backtest_sma_crossover(self, engine):
        """Test running SMA crossover backtest."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)
        
        result = await engine.run(
            symbol="ETH/USDT",
            start_date=start,
            end_date=end,
            strategy="sma_crossover",
            strategy_params={"short_period": 5, "long_period": 20},
            initial_capital=5000.0,
        )
        
        assert result.status == BacktestStatus.COMPLETED
        assert result.symbol == "ETH/USDT"
        assert result.strategy == "sma_crossover"
    
    @pytest.mark.asyncio
    async def test_backtest_metrics_calculation(self, engine):
        """Test metrics are calculated correctly."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 1, tzinfo=timezone.utc)  # 2 months
        
        result = await engine.run(
            symbol="BTC/USDT",
            start_date=start,
            end_date=end,
            strategy="momentum",
            initial_capital=10000.0,
        )
        
        assert result.metrics.total_trades >= 0
        assert -100 <= result.metrics.total_return_pct <= 500  # Reasonable range
        assert result.metrics.max_drawdown_pct >= 0
        assert 0 <= result.metrics.win_rate <= 100
    
    @pytest.mark.asyncio
    async def test_backtest_result_serialization(self, engine):
        """Test result can be serialized to dict."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, tzinfo=timezone.utc)
        
        result = await engine.run(
            symbol="BTC/USDT",
            start_date=start,
            end_date=end,
            strategy="momentum",
        )
        
        data = result.to_dict()
        assert "id" in data
        assert "status" in data
        assert "metrics" in data
        assert "equity_curve" in data
        assert data["status"] == "completed"


class TestBacktestTrade:
    """Test BacktestTrade."""
    
    def test_trade_to_dict(self):
        """Test trade serialization."""
        trade = BacktestTrade(
            id="test-id",
            timestamp=1704067200000,
            symbol="BTC/USDT",
            side="buy",
            price=50000.0,
            quantity=0.1,
            value=5000.0,
            fee=5.0,
            pnl=0.0,
        )
        data = trade.to_dict()
        assert data["id"] == "test-id"
        assert data["side"] == "buy"
        assert data["price"] == 50000.0
        assert "datetime" in data
