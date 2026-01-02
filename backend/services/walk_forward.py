# Walk-Forward Optimization (WFO) Framework
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import random
import copy


@dataclass
class WFOWindow:
    """Single walk-forward window"""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    optimized_params: Dict = field(default_factory=dict)
    train_metrics: Dict = field(default_factory=dict)
    test_metrics: Dict = field(default_factory=dict)
    test_trades: List = field(default_factory=list)
    test_equity_curve: List = field(default_factory=list)


@dataclass
class WFOResult:
    """Complete WFO analysis result"""
    agent_type: str
    symbol: str
    timeframe: str
    n_windows: int
    train_days: int
    test_days: int
    step_days: int
    windows: List[WFOWindow] = field(default_factory=list)
    
    # Aggregated out-of-sample metrics
    oos_total_pnl: float = 0.0
    oos_total_pnl_pct: float = 0.0
    oos_total_trades: int = 0
    oos_win_rate: float = 0.0
    
    # Distribution metrics (across windows)
    median_sharpe: float = 0.0
    min_sharpe: float = 0.0
    max_sharpe: float = 0.0
    std_sharpe: float = 0.0
    
    median_profit_factor: float = 0.0
    worst_drawdown: float = 0.0
    median_expectancy: float = 0.0
    
    # Stability score (0-100)
    stability_score: float = 0.0
    
    # Overfitting metrics
    train_vs_test_degradation: float = 0.0  # How much worse is OOS vs IS?
    complexity_penalty: float = 0.0
    
    # Monte Carlo results
    monte_carlo_dd_median: float = 0.0
    monte_carlo_dd_95: float = 0.0
    
    # Sensitivity results
    sensitivity_pnl_low: float = 0.0  # P&L with +20% fees
    sensitivity_pnl_high: float = 0.0  # P&L with -20% fees
    is_robust: bool = False
    
    # Go/No-Go decision
    go_live_score: float = 0.0
    go_live_recommendation: str = "NO_GO"
    go_live_reasons: List[str] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ParameterOptimizer:
    """Grid search optimizer with complexity penalty"""
    
    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        
        # Define parameter search spaces by agent type
        self.param_spaces = {
            "dca": {
                "interval_hours": [6, 12, 24, 48],
                "buy_amount_pct": [1, 2, 5, 10],  # % of capital
                "price_drop_trigger": [0, 3, 5, 10],  # % drop to trigger extra buy
            },
            "grid": {
                "grid_levels": [5, 10, 15, 20],
                "grid_spacing_percent": [0.5, 1.0, 1.5, 2.0],
                "mode": ["arithmetic", "geometric"],
            },
            "trend_following": {
                "ema_short": [8, 12, 20],
                "ema_long": [21, 26, 50],
                "rsi_period": [14, 21],
                "rsi_oversold": [25, 30, 35],
                "rsi_overbought": [65, 70, 75],
            },
            "mean_reversion": {
                "bb_period": [14, 20, 30],
                "bb_std": [1.5, 2.0, 2.5],
                "rsi_period": [7, 14],
            },
            "breakout": {
                "lookback_periods": [10, 20, 30],
                "volume_multiplier": [1.2, 1.5, 2.0],
                "atr_multiplier": [1.0, 1.5, 2.0],
            }
        }
        
        # Complexity weights (more params = higher penalty)
        self.complexity_weights = {
            "dca": 0.1,  # Simple strategy
            "grid": 0.15,
            "trend_following": 0.2,
            "mean_reversion": 0.2,
            "breakout": 0.25,
        }
    
    def generate_param_combinations(self) -> List[Dict]:
        """Generate all parameter combinations for grid search"""
        space = self.param_spaces.get(self.agent_type, {})
        if not space:
            return [{}]
        
        # Create all combinations
        keys = list(space.keys())
        values = list(space.values())
        
        combinations = []
        self._recursive_combine(keys, values, 0, {}, combinations)
        
        return combinations
    
    def _recursive_combine(self, keys, values, idx, current, result):
        if idx == len(keys):
            result.append(copy.deepcopy(current))
            return
        
        for val in values[idx]:
            current[keys[idx]] = val
            self._recursive_combine(keys, values, idx + 1, current, result)
    
    def calculate_complexity_penalty(self, params: Dict) -> float:
        """Calculate complexity penalty based on number of active parameters"""
        base_penalty = self.complexity_weights.get(self.agent_type, 0.1)
        n_params = len([v for v in params.values() if v is not None])
        return base_penalty * n_params
    
    def score_params(
        self,
        metrics: Dict,
        complexity_penalty: float
    ) -> float:
        """
        Score parameter set using expectancy + max drawdown (not just Sharpe)
        Lower is better for drawdown, higher is better for expectancy
        """
        expectancy = metrics.get("expectancy", 0)
        max_dd = abs(metrics.get("max_drawdown_pct", 100))
        win_rate = metrics.get("win_rate", 0)
        profit_factor = metrics.get("profit_factor", 0)
        
        # Normalize components
        expectancy_score = min(expectancy / 100, 1.0) if expectancy > 0 else expectancy / 100
        dd_penalty = max_dd / 20  # 20% DD = full penalty
        win_rate_bonus = (win_rate - 50) / 100  # Bonus for >50% WR
        pf_bonus = min((profit_factor - 1) / 2, 0.5) if profit_factor > 1 else 0
        
        # Combined score (higher is better)
        score = (
            expectancy_score * 0.4 +
            (1 - dd_penalty) * 0.3 +
            win_rate_bonus * 0.15 +
            pf_bonus * 0.15 -
            complexity_penalty
        )
        
        return score


class MonteCarloSimulator:
    """Monte Carlo analysis for robustness testing"""
    
    def __init__(self, n_simulations: int = 1000):
        self.n_simulations = n_simulations
    
    def shuffle_trades(self, trades: List[Dict]) -> List[Dict]:
        """Randomly shuffle trade order"""
        shuffled = copy.deepcopy(trades)
        random.shuffle(shuffled)
        return shuffled
    
    def perturb_fills(self, trades: List[Dict], perturbation_pct: float = 0.02) -> List[Dict]:
        """Add random perturbation to fill prices"""
        perturbed = []
        for trade in trades:
            t = copy.deepcopy(trade)
            if "entry_price" in t:
                t["entry_price"] *= (1 + random.uniform(-perturbation_pct, perturbation_pct))
            if "exit_price" in t:
                t["exit_price"] *= (1 + random.uniform(-perturbation_pct, perturbation_pct))
            perturbed.append(t)
        return perturbed
    
    def calculate_equity_curve(self, trades: List[Dict], initial_capital: float = 10000) -> List[float]:
        """Calculate equity curve from trades"""
        equity = [initial_capital]
        current = initial_capital
        
        for trade in trades:
            pnl = trade.get("pnl", 0)
            current += pnl
            equity.append(current)
        
        return equity
    
    def calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown from equity curve"""
        peak = equity_curve[0]
        max_dd = 0
        
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def run_simulation(
        self,
        trades: List[Dict],
        initial_capital: float = 10000
    ) -> Dict:
        """Run Monte Carlo simulation"""
        drawdowns = []
        final_equities = []
        
        for _ in range(self.n_simulations):
            # Randomly choose perturbation type
            if random.random() < 0.5:
                sim_trades = self.shuffle_trades(trades)
            else:
                sim_trades = self.perturb_fills(trades)
            
            equity = self.calculate_equity_curve(sim_trades, initial_capital)
            dd = self.calculate_max_drawdown(equity)
            
            drawdowns.append(dd)
            final_equities.append(equity[-1])
        
        return {
            "dd_median": np.median(drawdowns),
            "dd_mean": np.mean(drawdowns),
            "dd_std": np.std(drawdowns),
            "dd_95_percentile": np.percentile(drawdowns, 95),
            "dd_99_percentile": np.percentile(drawdowns, 99),
            "final_equity_median": np.median(final_equities),
            "final_equity_std": np.std(final_equities),
            "ruin_probability": sum(1 for eq in final_equities if eq < initial_capital * 0.5) / self.n_simulations
        }


class SensitivityAnalyzer:
    """Sensitivity analysis for fees and slippage"""
    
    def analyze_fee_sensitivity(
        self,
        trades: List[Dict],
        base_fee_pct: float = 0.1,
        variation_pct: float = 20
    ) -> Dict:
        """Analyze P&L sensitivity to fee changes"""
        # Calculate base P&L
        base_pnl = sum(t.get("pnl", 0) for t in trades)
        
        # Simulate with +20% fees
        high_fee_pnl = 0
        for trade in trades:
            original_fees = trade.get("fees", 0)
            additional_fees = original_fees * (variation_pct / 100)
            high_fee_pnl += trade.get("pnl", 0) - additional_fees
        
        # Simulate with -20% fees  
        low_fee_pnl = 0
        for trade in trades:
            original_fees = trade.get("fees", 0)
            reduced_fees = original_fees * (variation_pct / 100)
            low_fee_pnl += trade.get("pnl", 0) + reduced_fees
        
        return {
            "base_pnl": base_pnl,
            "high_fee_pnl": high_fee_pnl,
            "low_fee_pnl": low_fee_pnl,
            "fee_sensitivity": (base_pnl - high_fee_pnl) / abs(base_pnl) * 100 if base_pnl != 0 else 0,
            "is_robust": high_fee_pnl > 0  # Still profitable with higher fees?
        }
    
    def analyze_slippage_sensitivity(
        self,
        trades: List[Dict],
        additional_slippage_pct: float = 0.05
    ) -> Dict:
        """Analyze P&L sensitivity to slippage changes"""
        base_pnl = sum(t.get("pnl", 0) for t in trades)
        
        # Simulate with additional slippage
        slippage_pnl = 0
        for trade in trades:
            amount = trade.get("amount", 1)
            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            
            # Additional slippage on entry and exit
            slippage_cost = (entry_price + exit_price) * amount * additional_slippage_pct / 100
            slippage_pnl += trade.get("pnl", 0) - slippage_cost
        
        return {
            "base_pnl": base_pnl,
            "slippage_pnl": slippage_pnl,
            "slippage_sensitivity": (base_pnl - slippage_pnl) / abs(base_pnl) * 100 if base_pnl != 0 else 0,
            "is_robust": slippage_pnl > 0
        }


class WalkForwardOptimizer:
    """Walk-Forward Optimization Engine"""
    
    def __init__(
        self,
        train_days: int = 90,
        test_days: int = 30,
        step_days: int = 30,
        initial_capital: float = 10000
    ):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.initial_capital = initial_capital
        
        self.monte_carlo = MonteCarloSimulator()
        self.sensitivity = SensitivityAnalyzer()
    
    def create_windows(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Tuple[datetime, datetime, datetime, datetime]]:
        """Create train/test windows"""
        windows = []
        current_train_start = start_date
        
        while True:
            train_end = current_train_start + timedelta(days=self.train_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self.test_days)
            
            if test_end > end_date:
                break
            
            windows.append((current_train_start, train_end, test_start, test_end))
            current_train_start += timedelta(days=self.step_days)
        
        return windows
    
    def run_wfo(
        self,
        candles: List[Dict],
        agent_type: str,
        backtest_func: Callable,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h"
    ) -> WFOResult:
        """Run complete Walk-Forward Optimization"""
        if not candles:
            return WFOResult(
                agent_type=agent_type,
                symbol=symbol,
                timeframe=timeframe,
                n_windows=0,
                train_days=self.train_days,
                test_days=self.test_days,
                step_days=self.step_days
            )
        
        # Get date range from candles
        start_date = datetime.fromtimestamp(candles[0]["timestamp"] / 1000, timezone.utc)
        end_date = datetime.fromtimestamp(candles[-1]["timestamp"] / 1000, timezone.utc)
        
        # Create windows
        windows = self.create_windows(start_date, end_date)
        
        if not windows:
            return WFOResult(
                agent_type=agent_type,
                symbol=symbol,
                timeframe=timeframe,
                n_windows=0,
                train_days=self.train_days,
                test_days=self.test_days,
                step_days=self.step_days
            )
        
        optimizer = ParameterOptimizer(agent_type)
        param_combinations = optimizer.generate_param_combinations()
        
        wfo_windows = []
        all_oos_trades = []
        oos_equity_spliced = [self.initial_capital]
        
        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            # Filter candles for train period
            train_candles = [
                c for c in candles
                if train_start.timestamp() * 1000 <= c["timestamp"] < train_end.timestamp() * 1000
            ]
            
            # Filter candles for test period
            test_candles = [
                c for c in candles
                if test_start.timestamp() * 1000 <= c["timestamp"] < test_end.timestamp() * 1000
            ]
            
            if not train_candles or not test_candles:
                continue
            
            # Optimize on train data
            best_params = None
            best_score = float('-inf')
            best_train_metrics = {}
            
            for params in param_combinations:
                try:
                    train_result = backtest_func(train_candles, params, self.initial_capital)
                    metrics = train_result.get("metrics", {})
                    
                    complexity_penalty = optimizer.calculate_complexity_penalty(params)
                    score = optimizer.score_params(metrics, complexity_penalty)
                    
                    if score > best_score:
                        best_score = score
                        best_params = params
                        best_train_metrics = metrics
                except Exception as e:
                    continue
            
            if not best_params:
                best_params = param_combinations[0] if param_combinations else {}
            
            # Test with optimized params (frozen)
            try:
                test_result = backtest_func(test_candles, best_params, self.initial_capital)
                test_metrics = test_result.get("metrics", {})
                test_trades = test_result.get("trades", [])
                test_equity = test_result.get("equity_curve", [])
            except Exception as e:
                test_metrics = {}
                test_trades = []
                test_equity = []
            
            # Create window result
            window = WFOWindow(
                window_id=i + 1,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                optimized_params=best_params,
                train_metrics=best_train_metrics,
                test_metrics=test_metrics,
                test_trades=test_trades,
                test_equity_curve=test_equity
            )
            wfo_windows.append(window)
            
            # Collect OOS trades
            all_oos_trades.extend(test_trades)
            
            # Splice equity curve
            if test_equity:
                for eq in test_equity[1:]:  # Skip first (it's the starting point)
                    pnl_change = eq - test_equity[0]
                    oos_equity_spliced.append(oos_equity_spliced[-1] + pnl_change)
        
        # Calculate aggregated OOS metrics
        result = self._calculate_aggregated_metrics(
            wfo_windows, all_oos_trades, oos_equity_spliced, agent_type, symbol, timeframe
        )
        
        # Run Monte Carlo
        if all_oos_trades:
            mc_result = self.monte_carlo.run_simulation(all_oos_trades, self.initial_capital)
            result.monte_carlo_dd_median = mc_result["dd_median"]
            result.monte_carlo_dd_95 = mc_result["dd_95_percentile"]
        
        # Run sensitivity analysis
        if all_oos_trades:
            fee_sens = self.sensitivity.analyze_fee_sensitivity(all_oos_trades)
            result.sensitivity_pnl_low = fee_sens["high_fee_pnl"]
            result.sensitivity_pnl_high = fee_sens["low_fee_pnl"]
            result.is_robust = fee_sens["is_robust"]
        
        # Calculate go-live score and recommendation
        result = self._calculate_go_live_decision(result)
        
        return result
    
    def _calculate_aggregated_metrics(
        self,
        windows: List[WFOWindow],
        all_trades: List,
        equity_curve: List,
        agent_type: str,
        symbol: str,
        timeframe: str
    ) -> WFOResult:
        """Calculate aggregated out-of-sample metrics"""
        result = WFOResult(
            agent_type=agent_type,
            symbol=symbol,
            timeframe=timeframe,
            n_windows=len(windows),
            train_days=self.train_days,
            test_days=self.test_days,
            step_days=self.step_days,
            windows=windows
        )
        
        if not windows:
            return result
        
        # Collect metrics from each window
        sharpe_values = []
        pf_values = []
        expectancy_values = []
        dd_values = []
        win_rates = []
        
        for w in windows:
            m = w.test_metrics
            if m:
                if "sharpe_ratio" in m:
                    sharpe_values.append(m["sharpe_ratio"])
                if "profit_factor" in m and m["profit_factor"] != float('inf'):
                    pf_values.append(m["profit_factor"])
                if "expectancy" in m:
                    expectancy_values.append(m["expectancy"])
                if "max_drawdown_pct" in m:
                    dd_values.append(m["max_drawdown_pct"])
                if "win_rate" in m:
                    win_rates.append(m["win_rate"])
        
        # Distribution metrics
        if sharpe_values:
            result.median_sharpe = float(np.median(sharpe_values))
            result.min_sharpe = float(min(sharpe_values))
            result.max_sharpe = float(max(sharpe_values))
            result.std_sharpe = float(np.std(sharpe_values))
        
        if pf_values:
            result.median_profit_factor = float(np.median(pf_values))
        
        if expectancy_values:
            result.median_expectancy = float(np.median(expectancy_values))
        
        if dd_values:
            result.worst_drawdown = float(max(dd_values))
        
        # OOS totals
        result.oos_total_trades = len(all_trades)
        result.oos_total_pnl = sum(t.get("pnl", 0) for t in all_trades)
        result.oos_total_pnl_pct = (result.oos_total_pnl / self.initial_capital) * 100
        
        winning = [t for t in all_trades if t.get("pnl", 0) > 0]
        result.oos_win_rate = (len(winning) / len(all_trades) * 100) if all_trades else 0
        
        # Stability score (0-100)
        # Based on consistency of returns across windows
        if sharpe_values and len(sharpe_values) > 1:
            # Lower std = more stable
            cv = abs(np.std(sharpe_values) / np.mean(sharpe_values)) if np.mean(sharpe_values) != 0 else 1
            stability = max(0, 100 - cv * 50)  # cv of 0 = 100 stability, cv of 2 = 0 stability
            
            # Bonus for positive returns in all windows
            positive_windows = sum(1 for w in windows if w.test_metrics.get("total_pnl", 0) > 0)
            consistency_bonus = (positive_windows / len(windows)) * 20
            
            result.stability_score = min(100, stability + consistency_bonus)
        
        # Train vs Test degradation
        train_pnls = [w.train_metrics.get("total_pnl_pct", 0) for w in windows if w.train_metrics]
        test_pnls = [w.test_metrics.get("total_pnl_pct", 0) for w in windows if w.test_metrics]
        
        if train_pnls and test_pnls:
            avg_train = np.mean(train_pnls)
            avg_test = np.mean(test_pnls)
            if avg_train != 0:
                result.train_vs_test_degradation = ((avg_train - avg_test) / abs(avg_train)) * 100
        
        return result
    
    def _calculate_go_live_decision(self, result: WFOResult) -> WFOResult:
        """Calculate go/no-go recommendation"""
        score = 0
        reasons = []
        
        # Check 1: Positive OOS P&L
        if result.oos_total_pnl > 0:
            score += 20
        else:
            reasons.append("❌ Negative out-of-sample P&L")
        
        # Check 2: Median Sharpe > 0.5
        if result.median_sharpe > 0.5:
            score += 15
        elif result.median_sharpe > 0:
            score += 5
        else:
            reasons.append("❌ Sharpe ratio below threshold")
        
        # Check 3: Max DD < 15%
        if result.worst_drawdown < 10:
            score += 15
        elif result.worst_drawdown < 15:
            score += 10
        elif result.worst_drawdown < 20:
            score += 5
        else:
            reasons.append("❌ Max drawdown exceeds 20%")
        
        # Check 4: Stability > 60
        if result.stability_score > 70:
            score += 15
        elif result.stability_score > 50:
            score += 10
        else:
            reasons.append("❌ Low stability score (inconsistent returns)")
        
        # Check 5: Train/Test degradation < 50%
        if result.train_vs_test_degradation < 30:
            score += 15
        elif result.train_vs_test_degradation < 50:
            score += 10
        else:
            reasons.append("❌ High train/test degradation (possible overfitting)")
        
        # Check 6: Robust to fees
        if result.is_robust:
            score += 10
        else:
            reasons.append("❌ Strategy not robust to +20% fees")
        
        # Check 7: Monte Carlo DD acceptable
        if result.monte_carlo_dd_95 < 20:
            score += 10
        elif result.monte_carlo_dd_95 < 30:
            score += 5
        else:
            reasons.append("❌ Monte Carlo 95% DD exceeds 30%")
        
        result.go_live_score = score
        result.go_live_reasons = reasons
        
        if score >= 70:
            result.go_live_recommendation = "GO"
        elif score >= 50:
            result.go_live_recommendation = "CONDITIONAL_GO"
        else:
            result.go_live_recommendation = "NO_GO"
        
        return result
    
    def export_result(self, result: WFOResult) -> Dict:
        """Export WFO result as JSON-serializable dict"""
        windows_data = []
        for w in result.windows:
            windows_data.append({
                "window_id": w.window_id,
                "train_period": f"{w.train_start.strftime('%Y-%m-%d')} to {w.train_end.strftime('%Y-%m-%d')}",
                "test_period": f"{w.test_start.strftime('%Y-%m-%d')} to {w.test_end.strftime('%Y-%m-%d')}",
                "optimized_params": w.optimized_params,
                "train_metrics": w.train_metrics,
                "test_metrics": w.test_metrics,
                "test_trades_count": len(w.test_trades)
            })
        
        return {
            "summary": {
                "agent_type": result.agent_type,
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "n_windows": result.n_windows,
                "train_days": result.train_days,
                "test_days": result.test_days,
                "step_days": result.step_days
            },
            "oos_performance": {
                "total_pnl": round(result.oos_total_pnl, 2),
                "total_pnl_pct": round(result.oos_total_pnl_pct, 2),
                "total_trades": result.oos_total_trades,
                "win_rate": round(result.oos_win_rate, 2)
            },
            "distribution_metrics": {
                "median_sharpe": round(result.median_sharpe, 3),
                "min_sharpe": round(result.min_sharpe, 3),
                "max_sharpe": round(result.max_sharpe, 3),
                "std_sharpe": round(result.std_sharpe, 3),
                "median_profit_factor": round(result.median_profit_factor, 2),
                "median_expectancy": round(result.median_expectancy, 2),
                "worst_drawdown": round(result.worst_drawdown, 2)
            },
            "stability_analysis": {
                "stability_score": round(result.stability_score, 1),
                "train_vs_test_degradation_pct": round(result.train_vs_test_degradation, 1)
            },
            "monte_carlo": {
                "median_max_dd": round(result.monte_carlo_dd_median, 2),
                "95_percentile_dd": round(result.monte_carlo_dd_95, 2)
            },
            "sensitivity": {
                "pnl_with_higher_fees": round(result.sensitivity_pnl_low, 2),
                "pnl_with_lower_fees": round(result.sensitivity_pnl_high, 2),
                "is_robust": result.is_robust
            },
            "go_live_decision": {
                "score": result.go_live_score,
                "recommendation": result.go_live_recommendation,
                "issues": result.go_live_reasons
            },
            "windows": windows_data,
            "created_at": result.created_at.isoformat()
        }
