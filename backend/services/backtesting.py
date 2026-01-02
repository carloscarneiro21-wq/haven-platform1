# Backtesting Framework with Comprehensive Metrics
import numpy as np
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import csv
import io


@dataclass
class BacktestTrade:
    """Single trade in backtest"""
    id: str
    agent_id: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    amount: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    fees: float = 0
    slippage: float = 0
    r_multiple: Optional[float] = None  # Risk-adjusted return
    reason_entry: str = ""
    reason_exit: str = ""
    indicators: Dict = field(default_factory=dict)


@dataclass 
class BacktestMetrics:
    """Comprehensive backtest performance metrics"""
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # P&L metrics
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_hours: float = 0.0
    
    # Return metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Trade metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # R-multiple metrics
    expectancy: float = 0.0  # Expected value per trade
    avg_r_multiple: float = 0.0
    
    # Exposure metrics
    avg_exposure_pct: float = 0.0
    max_exposure_pct: float = 0.0
    time_in_market_pct: float = 0.0
    
    # Fee impact
    total_fees: float = 0.0
    total_slippage: float = 0.0
    fees_as_pnl_pct: float = 0.0
    
    # Time metrics
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    duration_days: float = 0.0
    trades_per_day: float = 0.0


class BacktestEngine:
    """Backtesting engine with realistic simulation"""
    
    def __init__(
        self,
        initial_capital: float = 10000,
        risk_per_trade_pct: float = 1.0,  # 1% risk per trade for R calculation
        risk_free_rate: float = 0.04  # 4% annual for Sharpe
    ):
        self.initial_capital = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.risk_free_rate = risk_free_rate
        
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[Dict] = []
        self.positions: Dict[str, Dict] = {}
        self.current_equity = initial_capital
    
    def reset(self):
        """Reset backtest state"""
        self.trades = []
        self.equity_curve = []
        self.positions = {}
        self.current_equity = self.initial_capital
    
    def record_equity(self, timestamp: datetime, price_data: Dict = None):
        """Record equity at a point in time"""
        # Mark-to-market open positions
        unrealized_pnl = 0
        for pos_id, pos in self.positions.items():
            if price_data and pos["symbol"] in price_data:
                current_price = price_data[pos["symbol"]]
                if pos["side"] == "buy":
                    unrealized_pnl += (current_price - pos["entry_price"]) * pos["amount"]
                else:
                    unrealized_pnl += (pos["entry_price"] - current_price) * pos["amount"]
        
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": self.current_equity + unrealized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "open_positions": len(self.positions)
        })
    
    def open_trade(
        self,
        trade_id: str,
        agent_id: str,
        symbol: str,
        side: str,
        amount: float,
        entry_price: float,
        entry_time: datetime,
        fees: float = 0,
        slippage: float = 0,
        reason: str = "",
        indicators: Dict = None
    ):
        """Open a new trade"""
        trade = BacktestTrade(
            id=trade_id,
            agent_id=agent_id,
            symbol=symbol,
            side=side,
            entry_time=entry_time,
            entry_price=entry_price,
            amount=amount,
            fees=fees,
            slippage=slippage,
            reason_entry=reason,
            indicators=indicators or {}
        )
        
        self.positions[trade_id] = {
            "trade": trade,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "entry_price": entry_price
        }
        
        return trade
    
    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime,
        exit_fees: float = 0,
        exit_slippage: float = 0,
        reason: str = ""
    ) -> Optional[BacktestTrade]:
        """Close an existing trade"""
        if trade_id not in self.positions:
            return None
        
        pos = self.positions[trade_id]
        trade = pos["trade"]
        
        # Update trade
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.fees += exit_fees
        trade.slippage += exit_slippage
        trade.reason_exit = reason
        
        # Calculate P&L
        if trade.side == "buy":
            gross_pnl = (exit_price - trade.entry_price) * trade.amount
        else:
            gross_pnl = (trade.entry_price - exit_price) * trade.amount
        
        trade.pnl = gross_pnl - trade.fees
        trade.pnl_pct = (trade.pnl / (trade.entry_price * trade.amount)) * 100
        
        # Calculate R-multiple
        risk_amount = self.initial_capital * (self.risk_per_trade_pct / 100)
        if risk_amount > 0:
            trade.r_multiple = trade.pnl / risk_amount
        
        # Update equity
        self.current_equity += trade.pnl
        
        # Store completed trade
        self.trades.append(trade)
        del self.positions[trade_id]
        
        return trade
    
    def calculate_metrics(self) -> BacktestMetrics:
        """Calculate comprehensive backtest metrics"""
        if not self.trades:
            return BacktestMetrics()
        
        metrics = BacktestMetrics()
        
        # Basic counts
        metrics.total_trades = len(self.trades)
        pnls = [t.pnl for t in self.trades]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p <= 0]
        
        metrics.winning_trades = len(winning)
        metrics.losing_trades = len(losing)
        metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100 if metrics.total_trades > 0 else 0
        
        # P&L metrics
        metrics.total_pnl = sum(pnls)
        metrics.total_pnl_pct = (metrics.total_pnl / self.initial_capital) * 100
        metrics.gross_profit = sum(winning) if winning else 0
        metrics.gross_loss = abs(sum(losing)) if losing else 0
        metrics.profit_factor = metrics.gross_profit / metrics.gross_loss if metrics.gross_loss > 0 else float('inf')
        
        # Trade averages
        metrics.avg_trade = np.mean(pnls) if pnls else 0
        metrics.avg_win = np.mean(winning) if winning else 0
        metrics.avg_loss = abs(np.mean(losing)) if losing else 0
        metrics.largest_win = max(winning) if winning else 0
        metrics.largest_loss = abs(min(losing)) if losing else 0
        
        # Expectancy (expected value per trade)
        if metrics.win_rate > 0:
            win_prob = metrics.win_rate / 100
            loss_prob = 1 - win_prob
            metrics.expectancy = (win_prob * metrics.avg_win) - (loss_prob * metrics.avg_loss)
        
        # R-multiple metrics
        r_multiples = [t.r_multiple for t in self.trades if t.r_multiple is not None]
        if r_multiples:
            metrics.avg_r_multiple = np.mean(r_multiples)
        
        # Drawdown calculation from equity curve
        if self.equity_curve:
            equities = [e["equity"] for e in self.equity_curve]
            peak = equities[0]
            max_dd = 0
            max_dd_pct = 0
            dd_start = None
            max_dd_duration = 0
            
            for i, eq in enumerate(equities):
                if eq > peak:
                    peak = eq
                    dd_start = i
                
                dd = peak - eq
                dd_pct = (dd / peak) * 100 if peak > 0 else 0
                
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = dd_pct
                    if dd_start is not None and i > dd_start:
                        # Calculate duration
                        start_time = self.equity_curve[dd_start]["timestamp"]
                        end_time = self.equity_curve[i]["timestamp"]
                        max_dd_duration = (end_time - start_time).total_seconds() / 3600
            
            metrics.max_drawdown = max_dd
            metrics.max_drawdown_pct = max_dd_pct
            metrics.max_drawdown_duration_hours = max_dd_duration
        
        # Risk-adjusted returns
        if len(pnls) > 1:
            returns = np.array(pnls) / self.initial_capital
            
            # Sharpe Ratio (annualized)
            daily_rf = self.risk_free_rate / 365
            excess_returns = returns - daily_rf
            if np.std(excess_returns) > 0:
                # Assuming daily trades, annualize
                metrics.sharpe_ratio = (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(365)
            
            # Sortino Ratio (only downside deviation)
            negative_returns = returns[returns < 0]
            if len(negative_returns) > 0 and np.std(negative_returns) > 0:
                metrics.sortino_ratio = (np.mean(excess_returns) / np.std(negative_returns)) * np.sqrt(365)
            
            # Calmar Ratio
            if metrics.max_drawdown_pct > 0:
                annual_return = metrics.total_pnl_pct * (365 / metrics.duration_days) if metrics.duration_days > 0 else 0
                metrics.calmar_ratio = annual_return / metrics.max_drawdown_pct
        
        # Time metrics
        if self.trades:
            metrics.start_date = min(t.entry_time for t in self.trades)
            metrics.end_date = max(t.exit_time or t.entry_time for t in self.trades)
            metrics.duration_days = (metrics.end_date - metrics.start_date).total_seconds() / 86400
            metrics.trades_per_day = metrics.total_trades / metrics.duration_days if metrics.duration_days > 0 else 0
        
        # Fee impact
        metrics.total_fees = sum(t.fees for t in self.trades)
        metrics.total_slippage = sum(t.slippage for t in self.trades)
        if metrics.gross_profit + metrics.gross_loss > 0:
            metrics.fees_as_pnl_pct = (metrics.total_fees / (metrics.gross_profit + metrics.gross_loss)) * 100
        
        # Exposure (simplified - would need position sizing data for accuracy)
        metrics.time_in_market_pct = (metrics.total_trades * 24) / (metrics.duration_days * 24) * 100 if metrics.duration_days > 0 else 0
        
        return metrics
    
    def export_trades_csv(self) -> str:
        """Export trades to CSV string"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "id", "agent_id", "symbol", "side", "entry_time", "entry_price",
            "exit_time", "exit_price", "amount", "pnl", "pnl_pct", "fees",
            "slippage", "r_multiple", "reason_entry", "reason_exit"
        ])
        
        for t in self.trades:
            writer.writerow([
                t.id, t.agent_id, t.symbol, t.side,
                t.entry_time.isoformat() if t.entry_time else "",
                t.entry_price,
                t.exit_time.isoformat() if t.exit_time else "",
                t.exit_price or "",
                t.amount, round(t.pnl, 2), round(t.pnl_pct, 2),
                round(t.fees, 2), round(t.slippage, 4),
                round(t.r_multiple, 2) if t.r_multiple else "",
                t.reason_entry, t.reason_exit
            ])
        
        return output.getvalue()
    
    def export_metrics_json(self) -> str:
        """Export metrics to JSON string"""
        metrics = self.calculate_metrics()
        
        # Convert to dict with serializable values
        result = {
            "total_trades": metrics.total_trades,
            "winning_trades": metrics.winning_trades,
            "losing_trades": metrics.losing_trades,
            "win_rate": round(metrics.win_rate, 2),
            "total_pnl": round(metrics.total_pnl, 2),
            "total_pnl_pct": round(metrics.total_pnl_pct, 2),
            "gross_profit": round(metrics.gross_profit, 2),
            "gross_loss": round(metrics.gross_loss, 2),
            "profit_factor": round(metrics.profit_factor, 2) if metrics.profit_factor != float('inf') else "∞",
            "max_drawdown": round(metrics.max_drawdown, 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
            "sortino_ratio": round(metrics.sortino_ratio, 2),
            "calmar_ratio": round(metrics.calmar_ratio, 2),
            "avg_win": round(metrics.avg_win, 2),
            "avg_loss": round(metrics.avg_loss, 2),
            "avg_trade": round(metrics.avg_trade, 2),
            "largest_win": round(metrics.largest_win, 2),
            "largest_loss": round(metrics.largest_loss, 2),
            "expectancy": round(metrics.expectancy, 2),
            "avg_r_multiple": round(metrics.avg_r_multiple, 2),
            "total_fees": round(metrics.total_fees, 2),
            "total_slippage": round(metrics.total_slippage, 4),
            "fees_as_pnl_pct": round(metrics.fees_as_pnl_pct, 2),
            "duration_days": round(metrics.duration_days, 1),
            "trades_per_day": round(metrics.trades_per_day, 2),
            "start_date": metrics.start_date.isoformat() if metrics.start_date else None,
            "end_date": metrics.end_date.isoformat() if metrics.end_date else None
        }
        
        return json.dumps(result, indent=2)
    
    def export_equity_curve_json(self) -> str:
        """Export equity curve to JSON string"""
        data = []
        for e in self.equity_curve:
            data.append({
                "timestamp": e["timestamp"].isoformat(),
                "equity": round(e["equity"], 2),
                "unrealized_pnl": round(e["unrealized_pnl"], 2),
                "open_positions": e["open_positions"]
            })
        return json.dumps(data, indent=2)


class WalkForwardAnalysis:
    """Walk-forward optimization and validation"""
    
    def __init__(
        self,
        in_sample_pct: float = 0.7,  # 70% for optimization
        n_folds: int = 5  # Number of walk-forward periods
    ):
        self.in_sample_pct = in_sample_pct
        self.n_folds = n_folds
        self.results: List[Dict] = []
    
    def run(
        self,
        candles: List[Dict],
        strategy_func: Callable,
        optimize_func: Callable
    ) -> Dict:
        """Run walk-forward analysis"""
        total_candles = len(candles)
        fold_size = total_candles // self.n_folds
        
        all_trades = []
        all_metrics = []
        
        for fold in range(self.n_folds):
            # Define periods
            start_idx = fold * fold_size
            end_idx = min((fold + 1) * fold_size, total_candles)
            
            fold_candles = candles[start_idx:end_idx]
            in_sample_size = int(len(fold_candles) * self.in_sample_pct)
            
            in_sample = fold_candles[:in_sample_size]
            out_sample = fold_candles[in_sample_size:]
            
            # Optimize on in-sample
            optimal_params = optimize_func(in_sample)
            
            # Test on out-of-sample
            fold_trades, fold_metrics = strategy_func(out_sample, optimal_params)
            
            all_trades.extend(fold_trades)
            all_metrics.append({
                "fold": fold + 1,
                "in_sample_start": in_sample[0]["timestamp"] if in_sample else None,
                "out_sample_start": out_sample[0]["timestamp"] if out_sample else None,
                "params": optimal_params,
                "metrics": fold_metrics
            })
        
        # Aggregate results
        return {
            "n_folds": self.n_folds,
            "fold_results": all_metrics,
            "total_out_sample_trades": len(all_trades),
            "aggregated_metrics": self._aggregate_metrics(all_metrics)
        }
    
    def _aggregate_metrics(self, fold_results: List[Dict]) -> Dict:
        """Aggregate metrics across folds"""
        if not fold_results:
            return {}
        
        metrics_keys = ["win_rate", "profit_factor", "sharpe_ratio", "max_drawdown_pct"]
        aggregated = {}
        
        for key in metrics_keys:
            values = [f["metrics"].get(key, 0) for f in fold_results if f["metrics"]]
            if values:
                aggregated[f"avg_{key}"] = np.mean(values)
                aggregated[f"std_{key}"] = np.std(values)
                aggregated[f"min_{key}"] = min(values)
                aggregated[f"max_{key}"] = max(values)
        
        return aggregated
