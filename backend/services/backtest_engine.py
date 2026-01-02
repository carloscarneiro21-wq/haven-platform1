"""Lightweight Backtesting & Replay Tool for HAVEN.

Provides:
- Historical data replay from saved candles
- Paper trading simulation with realistic fills
- Performance metrics (return, Sharpe, drawdown, etc.)
- Strategy evaluation capabilities

Usage:
    engine = BacktestEngine(db)
    result = await engine.run(
        symbol="BTC/USDT",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        strategy="momentum",
        initial_capital=10000,
    )
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
import logging
import numpy as np

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class BacktestStatus(str, Enum):
    """Backtest execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SignalType(str, Enum):
    """Trading signal types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class BacktestCandle:
    """Historical candle for backtest."""
    timestamp: int  # ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc)


@dataclass
class BacktestTrade:
    """Executed trade in backtest."""
    id: str
    timestamp: int
    symbol: str
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    value: float
    fee: float
    pnl: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc).isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "value": self.value,
            "fee": self.fee,
            "pnl": self.pnl,
        }


@dataclass
class BacktestPosition:
    """Current position in backtest."""
    symbol: str
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def update_unrealized(self, current_price: float):
        """Update unrealized PnL."""
        if self.quantity != 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.quantity


@dataclass
class BacktestMetrics:
    """Performance metrics from backtest."""
    total_return: float = 0.0
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_trade_duration_hours: float = 0.0
    volatility: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_return": round(self.total_return, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate": round(self.win_rate, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_trade_duration_hours": round(self.avg_trade_duration_hours, 2),
            "volatility": round(self.volatility, 4),
        }


@dataclass
class BacktestResult:
    """Complete backtest result."""
    id: str
    status: BacktestStatus
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    metrics: BacktestMetrics
    trades: List[BacktestTrade]
    equity_curve: List[Dict[str, Any]]  # [{timestamp, equity}]
    candles_processed: int
    execution_time_ms: float
    error: Optional[str] = None
    created_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "metrics": self.metrics.to_dict(),
            "trades": [t.to_dict() for t in self.trades[-100:]],  # Last 100 trades
            "equity_curve": self.equity_curve[-500:],  # Last 500 points
            "candles_processed": self.candles_processed,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
            "created_at": self.created_at,
        }


# ============================================================
# BUILT-IN STRATEGIES
# ============================================================

def strategy_momentum(
    candles: List[BacktestCandle],
    position: BacktestPosition,
    params: Dict[str, Any]
) -> SignalType:
    """
    Momentum strategy based on RSI.
    
    Buy when RSI < oversold (30)
    Sell when RSI > overbought (70)
    """
    if len(candles) < 14:
        return SignalType.HOLD
    
    # Calculate RSI
    closes = [c.close for c in candles[-15:]]
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    oversold = params.get("oversold", 30)
    overbought = params.get("overbought", 70)
    
    if position.quantity == 0 and rsi < oversold:
        return SignalType.BUY
    elif position.quantity > 0 and rsi > overbought:
        return SignalType.SELL
    
    return SignalType.HOLD


def strategy_sma_crossover(
    candles: List[BacktestCandle],
    position: BacktestPosition,
    params: Dict[str, Any]
) -> SignalType:
    """
    Simple Moving Average crossover strategy.
    
    Buy when short SMA crosses above long SMA
    Sell when short SMA crosses below long SMA
    """
    short_period = params.get("short_period", 10)
    long_period = params.get("long_period", 30)
    
    if len(candles) < long_period + 1:
        return SignalType.HOLD
    
    closes = [c.close for c in candles[-(long_period + 1):]]
    
    # Current SMAs
    short_sma = np.mean(closes[-short_period:])
    long_sma = np.mean(closes[-long_period:])
    
    # Previous SMAs
    prev_short_sma = np.mean(closes[-(short_period + 1):-1])
    prev_long_sma = np.mean(closes[-(long_period + 1):-1])
    
    # Crossover detection
    if position.quantity == 0:
        if prev_short_sma <= prev_long_sma and short_sma > long_sma:
            return SignalType.BUY
    else:
        if prev_short_sma >= prev_long_sma and short_sma < long_sma:
            return SignalType.SELL
    
    return SignalType.HOLD


def strategy_mean_reversion(
    candles: List[BacktestCandle],
    position: BacktestPosition,
    params: Dict[str, Any]
) -> SignalType:
    """
    Mean reversion strategy using Bollinger Bands.
    
    Buy when price below lower band
    Sell when price above upper band or crosses middle
    """
    period = params.get("period", 20)
    std_mult = params.get("std_mult", 2.0)
    
    if len(candles) < period:
        return SignalType.HOLD
    
    closes = [c.close for c in candles[-period:]]
    current_price = candles[-1].close
    
    sma = np.mean(closes)
    std = np.std(closes)
    
    upper_band = sma + std_mult * std
    lower_band = sma - std_mult * std
    
    if position.quantity == 0 and current_price < lower_band:
        return SignalType.BUY
    elif position.quantity > 0 and (current_price > upper_band or current_price > sma):
        return SignalType.SELL
    
    return SignalType.HOLD


def strategy_breakout(
    candles: List[BacktestCandle],
    position: BacktestPosition,
    params: Dict[str, Any]
) -> SignalType:
    """
    Breakout strategy using Donchian channels.
    
    Buy on upper channel breakout
    Sell on lower channel breakdown or trailing stop
    """
    period = params.get("period", 20)
    trailing_stop_pct = params.get("trailing_stop", 0.03)  # 3%
    
    if len(candles) < period:
        return SignalType.HOLD
    
    highs = [c.high for c in candles[-period:-1]]  # Exclude current
    lows = [c.low for c in candles[-period:-1]]
    
    upper_channel = max(highs)
    lower_channel = min(lows)
    current_price = candles[-1].close
    
    if position.quantity == 0 and current_price > upper_channel:
        return SignalType.BUY
    elif position.quantity > 0:
        # Trailing stop check
        if current_price < position.avg_entry_price * (1 - trailing_stop_pct):
            return SignalType.SELL
        if current_price < lower_channel:
            return SignalType.SELL
    
    return SignalType.HOLD


# Strategy registry
STRATEGIES: Dict[str, Callable] = {
    "momentum": strategy_momentum,
    "sma_crossover": strategy_sma_crossover,
    "mean_reversion": strategy_mean_reversion,
    "breakout": strategy_breakout,
}

STRATEGY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "momentum": {"oversold": 30, "overbought": 70},
    "sma_crossover": {"short_period": 10, "long_period": 30},
    "mean_reversion": {"period": 20, "std_mult": 2.0},
    "breakout": {"period": 20, "trailing_stop": 0.03},
}


# ============================================================
# BACKTEST ENGINE
# ============================================================

class BacktestEngine:
    """Lightweight backtesting engine."""
    
    # Execution settings
    FEE_RATE = 0.001  # 0.1% per trade
    SLIPPAGE = 0.0005  # 0.05% slippage
    MIN_TRADE_INTERVAL_MS = 3600000  # 1 hour between trades
    
    def __init__(self, db: AsyncIOMotorDatabase = None):
        self.db = db
        self._running_backtests: Dict[str, bool] = {}
    
    async def run(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy: str = "momentum",
        strategy_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.95,  # 95% of capital per trade
    ) -> BacktestResult:
        """
        Run a backtest simulation.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            start_date: Backtest start date
            end_date: Backtest end date
            strategy: Strategy name (from STRATEGIES)
            strategy_params: Optional strategy parameters
            initial_capital: Starting capital in quote currency
            position_size_pct: Fraction of capital to use per trade
        
        Returns:
            BacktestResult with performance metrics
        """
        backtest_id = str(uuid4())
        start_time = datetime.now(timezone.utc)
        
        logger.info(f"Starting backtest {backtest_id}: {symbol} {strategy} from {start_date} to {end_date}")
        
        # Validate strategy
        if strategy not in STRATEGIES:
            return BacktestResult(
                id=backtest_id,
                status=BacktestStatus.FAILED,
                symbol=symbol,
                strategy=strategy,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                initial_capital=initial_capital,
                final_capital=initial_capital,
                metrics=BacktestMetrics(),
                trades=[],
                equity_curve=[],
                candles_processed=0,
                execution_time_ms=0,
                error=f"Unknown strategy: {strategy}. Available: {list(STRATEGIES.keys())}",
                created_at=start_time.isoformat(),
            )
        
        strategy_fn = STRATEGIES[strategy]
        params = {**STRATEGY_DEFAULTS.get(strategy, {}), **(strategy_params or {})}
        
        try:
            # Load historical data
            candles = await self._load_candles(symbol, start_date, end_date)
            
            if len(candles) < 50:
                return BacktestResult(
                    id=backtest_id,
                    status=BacktestStatus.FAILED,
                    symbol=symbol,
                    strategy=strategy,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    initial_capital=initial_capital,
                    final_capital=initial_capital,
                    metrics=BacktestMetrics(),
                    trades=[],
                    equity_curve=[],
                    candles_processed=len(candles),
                    execution_time_ms=0,
                    error=f"Insufficient data: {len(candles)} candles (minimum 50)",
                    created_at=start_time.isoformat(),
                )
            
            # Run simulation
            result = await self._simulate(
                backtest_id=backtest_id,
                symbol=symbol,
                strategy=strategy,
                strategy_fn=strategy_fn,
                params=params,
                candles=candles,
                initial_capital=initial_capital,
                position_size_pct=position_size_pct,
                start_date=start_date,
                end_date=end_date,
            )
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            result.created_at = start_time.isoformat()
            
            # Save result to database
            if self.db is not None:
                await self._save_result(result)
            
            logger.info(f"Backtest {backtest_id} completed: {result.metrics.total_return_pct:.2f}% return")
            return result
            
        except Exception as e:
            logger.error(f"Backtest {backtest_id} failed: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return BacktestResult(
                id=backtest_id,
                status=BacktestStatus.FAILED,
                symbol=symbol,
                strategy=strategy,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                initial_capital=initial_capital,
                final_capital=initial_capital,
                metrics=BacktestMetrics(),
                trades=[],
                equity_curve=[],
                candles_processed=0,
                execution_time_ms=execution_time,
                error=str(e),
                created_at=start_time.isoformat(),
            )
    
    async def _load_candles(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[BacktestCandle]:
        """Load historical candles from database or generate synthetic data."""
        candles = []
        
        # Try to load from database
        if self.db is not None:
            start_ms = int(start_date.timestamp() * 1000)
            end_ms = int(end_date.timestamp() * 1000)
            
            cursor = self.db.candles.find({
                "symbol": symbol,
                "timestamp": {"$gte": start_ms, "$lte": end_ms}
            }, {"_id": 0}).sort("timestamp", 1)
            
            docs = await cursor.to_list(10000)
            candles = [
                BacktestCandle(
                    timestamp=doc["timestamp"],
                    open=doc["open"],
                    high=doc["high"],
                    low=doc["low"],
                    close=doc["close"],
                    volume=doc.get("volume", 0),
                )
                for doc in docs
            ]
        
        # If no data, generate synthetic (for demo purposes)
        if len(candles) < 50:
            logger.info(f"Generating synthetic data for {symbol}")
            candles = self._generate_synthetic_candles(symbol, start_date, end_date)
        
        return candles
    
    def _generate_synthetic_candles(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[BacktestCandle]:
        """Generate synthetic price data for backtesting."""
        # Base prices by symbol
        base_prices = {
            "BTC/USDT": 45000, "BTC/USD": 45000,
            "ETH/USDT": 2500, "ETH/USD": 2500,
            "SOL/USDT": 100, "SOL/USD": 100,
        }
        base_price = base_prices.get(symbol, 100)
        
        candles = []
        current_time = start_date
        price = base_price
        
        # Parameters for realistic price movement
        drift = 0.0001  # Slight upward drift
        volatility = 0.02  # 2% hourly volatility
        
        while current_time <= end_date:
            timestamp_ms = int(current_time.timestamp() * 1000)
            
            # Random walk with drift
            returns = np.random.normal(drift, volatility)
            price = price * (1 + returns)
            
            # Generate OHLC
            intra_vol = abs(np.random.normal(0, price * 0.005))
            high = price + intra_vol
            low = price - intra_vol
            open_price = price * (1 + np.random.normal(0, 0.002))
            close_price = price
            
            candles.append(BacktestCandle(
                timestamp=timestamp_ms,
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_price, 2),
                volume=round(np.random.uniform(100, 1000), 2),
            ))
            
            current_time += timedelta(hours=1)
        
        return candles
    
    async def _simulate(
        self,
        backtest_id: str,
        symbol: str,
        strategy: str,
        strategy_fn: Callable,
        params: Dict[str, Any],
        candles: List[BacktestCandle],
        initial_capital: float,
        position_size_pct: float,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestResult:
        """Run the backtest simulation."""
        # State
        capital = initial_capital
        position = BacktestPosition(symbol=symbol)
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict[str, Any]] = []
        
        # Tracking
        last_trade_time = 0
        peak_equity = initial_capital
        max_drawdown = 0
        returns_list: List[float] = []
        prev_equity = initial_capital
        
        # Lookback window for strategy
        lookback_start = 50  # Start after enough data for indicators
        
        for i in range(lookback_start, len(candles)):
            candle = candles[i]
            lookback = candles[max(0, i - 100):i + 1]  # Last 100 candles + current
            
            # Update position unrealized PnL
            position.update_unrealized(candle.close)
            
            # Calculate current equity
            equity = capital + (position.quantity * candle.close if position.quantity > 0 else 0)
            
            # Track returns for Sharpe calculation
            if prev_equity > 0:
                period_return = (equity - prev_equity) / prev_equity
                returns_list.append(period_return)
            prev_equity = equity
            
            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            drawdown = peak_equity - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # Record equity curve (every 4 hours to reduce data)
            if i % 4 == 0 or i == len(candles) - 1:
                equity_curve.append({
                    "timestamp": candle.timestamp,
                    "equity": round(equity, 2),
                    "position": round(position.quantity, 6),
                    "price": candle.close,
                })
            
            # Check for trade signal
            if candle.timestamp - last_trade_time >= self.MIN_TRADE_INTERVAL_MS:
                signal = strategy_fn(lookback, position, params)
                
                if signal == SignalType.BUY and position.quantity == 0:
                    # Execute buy
                    trade_capital = capital * position_size_pct
                    slippage_price = candle.close * (1 + self.SLIPPAGE)
                    quantity = trade_capital / slippage_price
                    fee = trade_capital * self.FEE_RATE
                    
                    trade = BacktestTrade(
                        id=str(uuid4()),
                        timestamp=candle.timestamp,
                        symbol=symbol,
                        side="buy",
                        price=slippage_price,
                        quantity=quantity,
                        value=trade_capital,
                        fee=fee,
                    )
                    trades.append(trade)
                    
                    position.quantity = quantity
                    position.avg_entry_price = slippage_price
                    capital -= (trade_capital + fee)
                    last_trade_time = candle.timestamp
                    
                elif signal == SignalType.SELL and position.quantity > 0:
                    # Execute sell
                    slippage_price = candle.close * (1 - self.SLIPPAGE)
                    sale_value = position.quantity * slippage_price
                    fee = sale_value * self.FEE_RATE
                    pnl = sale_value - (position.quantity * position.avg_entry_price) - fee
                    
                    trade = BacktestTrade(
                        id=str(uuid4()),
                        timestamp=candle.timestamp,
                        symbol=symbol,
                        side="sell",
                        price=slippage_price,
                        quantity=position.quantity,
                        value=sale_value,
                        fee=fee,
                        pnl=pnl,
                    )
                    trades.append(trade)
                    
                    capital += (sale_value - fee)
                    position.realized_pnl += pnl
                    position.quantity = 0
                    position.avg_entry_price = 0
                    last_trade_time = candle.timestamp
        
        # Close any remaining position at end
        if position.quantity > 0:
            final_candle = candles[-1]
            slippage_price = final_candle.close * (1 - self.SLIPPAGE)
            sale_value = position.quantity * slippage_price
            fee = sale_value * self.FEE_RATE
            pnl = sale_value - (position.quantity * position.avg_entry_price) - fee
            
            trade = BacktestTrade(
                id=str(uuid4()),
                timestamp=final_candle.timestamp,
                symbol=symbol,
                side="sell",
                price=slippage_price,
                quantity=position.quantity,
                value=sale_value,
                fee=fee,
                pnl=pnl,
            )
            trades.append(trade)
            capital += (sale_value - fee)
        
        # Calculate final equity and metrics
        final_equity = capital
        
        # Compute metrics
        metrics = self._calculate_metrics(
            trades=trades,
            returns_list=returns_list,
            initial_capital=initial_capital,
            final_capital=final_equity,
            max_drawdown=max_drawdown,
        )
        
        return BacktestResult(
            id=backtest_id,
            status=BacktestStatus.COMPLETED,
            symbol=symbol,
            strategy=strategy,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            initial_capital=initial_capital,
            final_capital=final_equity,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            candles_processed=len(candles),
            execution_time_ms=0,
        )
    
    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        returns_list: List[float],
        initial_capital: float,
        final_capital: float,
        max_drawdown: float,
    ) -> BacktestMetrics:
        """Calculate performance metrics."""
        # Basic return
        total_return = final_capital - initial_capital
        total_return_pct = (total_return / initial_capital) * 100 if initial_capital > 0 else 0
        
        # Filter sell trades (completed trades)
        sell_trades = [t for t in trades if t.side == "sell"]
        winning = [t for t in sell_trades if t.pnl > 0]
        losing = [t for t in sell_trades if t.pnl <= 0]
        
        # Win rate
        win_rate = (len(winning) / len(sell_trades) * 100) if sell_trades else 0
        
        # Average win/loss
        avg_win = np.mean([t.pnl for t in winning]) if winning else 0
        avg_loss = abs(np.mean([t.pnl for t in losing])) if losing else 0
        
        # Profit factor
        total_wins = sum(t.pnl for t in winning) if winning else 0
        total_losses = abs(sum(t.pnl for t in losing)) if losing else 1
        profit_factor = total_wins / total_losses if total_losses > 0 else total_wins
        
        # Sharpe ratio (annualized from hourly returns)
        if len(returns_list) > 1:
            returns_arr = np.array(returns_list)
            mean_return = np.mean(returns_arr)
            std_return = np.std(returns_arr)
            # Annualize: hourly data * sqrt(8760 hours/year)
            sharpe = (mean_return / std_return * np.sqrt(8760)) if std_return > 0 else 0
            volatility = std_return * np.sqrt(8760)
        else:
            sharpe = 0
            volatility = 0
        
        # Max drawdown percentage
        max_dd_pct = (max_drawdown / initial_capital) * 100 if initial_capital > 0 else 0
        
        # Average trade duration
        if len(trades) >= 2:
            buy_times = [t.timestamp for t in trades if t.side == "buy"]
            sell_times = [t.timestamp for t in trades if t.side == "sell"]
            if buy_times and sell_times:
                durations = []
                for i, sell_time in enumerate(sell_times):
                    if i < len(buy_times):
                        durations.append((sell_time - buy_times[i]) / 3600000)  # hours
                avg_duration = np.mean(durations) if durations else 0
            else:
                avg_duration = 0
        else:
            avg_duration = 0
        
        return BacktestMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_dd_pct,
            win_rate=win_rate,
            total_trades=len(sell_trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            avg_trade_duration_hours=avg_duration,
            volatility=volatility,
        )
    
    async def _save_result(self, result: BacktestResult):
        """Save backtest result to database."""
        if self.db is None:
            return
        
        try:
            await self.db.backtest_results.insert_one({
                **result.to_dict(),
                "trades_count": len(result.trades),
                "equity_points": len(result.equity_curve),
            })
        except Exception as e:
            logger.warning(f"Failed to save backtest result: {e}")
    
    async def get_history(
        self,
        limit: int = 20,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get historical backtest results."""
        if self.db is None:
            return []
        
        query = {}
        if symbol:
            query["symbol"] = symbol
        if strategy:
            query["strategy"] = strategy
        
        cursor = self.db.backtest_results.find(
            query,
            {"_id": 0, "trades": 0, "equity_curve": 0}  # Exclude large fields
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_result(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific backtest result."""
        if self.db is None:
            return None
        
        result = await self.db.backtest_results.find_one(
            {"id": backtest_id},
            {"_id": 0}
        )
        return result


# Module-level instance
_backtest_engine: Optional[BacktestEngine] = None


def get_backtest_engine() -> Optional[BacktestEngine]:
    """Get global backtest engine instance."""
    return _backtest_engine


def set_backtest_engine(engine: BacktestEngine):
    """Set global backtest engine instance."""
    global _backtest_engine
    _backtest_engine = engine
