"""Backtest Optimization Service for HAVEN.

Provides:
- Parameter variation generation from base presets
- Walk-forward (train/test split) backtesting
- Overfitting risk assessment
- Top results ranking with metrics
- Hard cap and constraint enforcement

No live execution - results are suggestions only.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from uuid import uuid4
import logging
import numpy as np
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase

from services.backtest_engine import (
    BacktestEngine, BacktestResult, BacktestStatus, 
    STRATEGIES, STRATEGY_DEFAULTS
)

logger = logging.getLogger(__name__)


class OptimizationStatus(str, Enum):
    """Optimization job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParameterRange:
    """Parameter variation range."""
    name: str
    min_val: float
    max_val: float
    step: float
    param_type: str = "float"  # float, int, bool


@dataclass
class OptimizationConfig:
    """Configuration for optimization run."""
    strategy: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0
    
    # Walk-forward settings
    train_ratio: float = 0.7  # 70% train, 30% test
    
    # Variation settings
    num_variations: int = 20
    
    # Constraints
    max_drawdown_pct: float = 30.0
    min_sharpe: float = 0.5
    min_trades: int = 5


@dataclass
class OptimizationResult:
    """Single optimization variation result."""
    variation_id: str
    params: Dict[str, Any]
    
    # Train metrics
    train_return_pct: float
    train_sharpe: float
    train_max_drawdown_pct: float
    train_win_rate: float
    train_trades: int
    
    # Test metrics (out-of-sample)
    test_return_pct: float
    test_sharpe: float
    test_max_drawdown_pct: float
    test_win_rate: float
    test_trades: int
    
    # Risk assessment
    overfit_risk: float  # 0-100, higher = more likely overfit
    overfit_reasons: List[str]
    
    # Ranking
    score: float = 0.0
    rank: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "variation_id": self.variation_id,
            "params": self.params,
            "train": {
                "return_pct": round(self.train_return_pct, 2),
                "sharpe": round(self.train_sharpe, 2),
                "max_drawdown_pct": round(self.train_max_drawdown_pct, 2),
                "win_rate": round(self.train_win_rate, 2),
                "trades": self.train_trades,
            },
            "test": {
                "return_pct": round(self.test_return_pct, 2),
                "sharpe": round(self.test_sharpe, 2),
                "max_drawdown_pct": round(self.test_max_drawdown_pct, 2),
                "win_rate": round(self.test_win_rate, 2),
                "trades": self.test_trades,
            },
            "overfit_risk": round(self.overfit_risk, 1),
            "overfit_reasons": self.overfit_reasons,
            "score": round(self.score, 2),
            "rank": self.rank,
        }


@dataclass
class OptimizationJob:
    """Complete optimization job."""
    id: str
    status: OptimizationStatus
    config: OptimizationConfig
    results: List[OptimizationResult]
    best_result: Optional[OptimizationResult]
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    progress: int = 0
    total_variations: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "config": {
                "strategy": self.config.strategy,
                "symbol": self.config.symbol,
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_capital": self.config.initial_capital,
                "train_ratio": self.config.train_ratio,
                "num_variations": self.config.num_variations,
            },
            "results": [r.to_dict() for r in self.results[:10]],  # Top 10
            "best_result": self.best_result.to_dict() if self.best_result else None,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "progress": self.progress,
            "total_variations": self.total_variations,
        }


# ============================================================
# PARAMETER RANGES BY STRATEGY
# ============================================================

STRATEGY_PARAM_RANGES: Dict[str, List[ParameterRange]] = {
    "momentum": [
        ParameterRange("oversold", 15, 40, 5, "int"),
        ParameterRange("overbought", 60, 85, 5, "int"),
    ],
    "sma_crossover": [
        ParameterRange("short_period", 5, 20, 5, "int"),
        ParameterRange("long_period", 20, 60, 10, "int"),
    ],
    "mean_reversion": [
        ParameterRange("period", 10, 30, 5, "int"),
        ParameterRange("std_mult", 1.5, 3.0, 0.5, "float"),
    ],
    "breakout": [
        ParameterRange("period", 10, 30, 5, "int"),
        ParameterRange("trailing_stop", 0.02, 0.06, 0.01, "float"),
    ],
}

# Hard caps - cannot exceed these values
HARD_CAPS = {
    "max_position_pct": 0.95,
    "max_drawdown_pct": 50.0,
    "min_sharpe": -2.0,
}


# ============================================================
# OPTIMIZATION ENGINE
# ============================================================

class OptimizationEngine:
    """Backtest-assisted preset optimization engine."""
    
    def __init__(self, db: AsyncIOMotorDatabase = None, backtest_engine: BacktestEngine = None):
        self.db = db
        self.backtest_engine = backtest_engine or BacktestEngine(db=db)
        self._running_jobs: Dict[str, bool] = {}
    
    def _generate_variations(
        self, 
        strategy: str, 
        num_variations: int,
        base_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate parameter variations for a strategy."""
        ranges = STRATEGY_PARAM_RANGES.get(strategy, [])
        if not ranges:
            return [STRATEGY_DEFAULTS.get(strategy, {})]
        
        variations = []
        base = base_params or STRATEGY_DEFAULTS.get(strategy, {})
        
        # Add base params as first variation
        variations.append(base.copy())
        
        # Generate random variations
        for _ in range(num_variations - 1):
            params = {}
            for r in ranges:
                if r.param_type == "int":
                    val = int(np.random.choice(np.arange(r.min_val, r.max_val + r.step, r.step)))
                else:
                    val = round(np.random.uniform(r.min_val, r.max_val), 2)
                params[r.name] = val
            
            # Validate constraints (e.g., short_period < long_period)
            if strategy == "sma_crossover":
                if params.get("short_period", 10) >= params.get("long_period", 30):
                    params["short_period"] = max(5, params["long_period"] - 10)
            
            variations.append(params)
        
        return variations
    
    def _calculate_overfit_risk(
        self,
        train_return: float,
        test_return: float,
        train_sharpe: float,
        test_sharpe: float,
        train_trades: int,
        test_trades: int,
    ) -> Tuple[float, List[str]]:
        """
        Calculate overfitting risk score (0-100).
        
        Signs of overfitting:
        - Train >> Test performance
        - Very high train returns but low test
        - Very few trades
        - Sharpe degradation
        """
        risk = 0.0
        reasons = []
        
        # Return degradation
        if train_return > 0 and test_return < train_return:
            degradation = (train_return - test_return) / max(abs(train_return), 1)
            if degradation > 0.5:
                risk += 30
                reasons.append(f"Return dropped {degradation*100:.0f}% from train to test")
            elif degradation > 0.3:
                risk += 15
                reasons.append(f"Moderate return degradation ({degradation*100:.0f}%)")
        
        # Sharpe degradation
        if train_sharpe > 0 and test_sharpe < train_sharpe:
            sharpe_drop = train_sharpe - test_sharpe
            if sharpe_drop > 1.0:
                risk += 25
                reasons.append(f"Sharpe dropped by {sharpe_drop:.2f}")
            elif sharpe_drop > 0.5:
                risk += 10
                reasons.append(f"Sharpe degraded by {sharpe_drop:.2f}")
        
        # Too few trades
        if train_trades < 10:
            risk += 20
            reasons.append(f"Only {train_trades} trades in train period (too few)")
        if test_trades < 5:
            risk += 15
            reasons.append(f"Only {test_trades} trades in test period")
        
        # Unrealistic train performance
        if train_return > 100:
            risk += 20
            reasons.append(f"Suspicious train return ({train_return:.0f}%)")
        
        # Negative test but positive train
        if train_return > 20 and test_return < 0:
            risk += 25
            reasons.append("Positive train but negative test return")
        
        # Cap at 100
        risk = min(100, risk)
        
        if not reasons:
            reasons.append("No significant overfitting signals detected")
        
        return risk, reasons
    
    def _calculate_score(self, result: OptimizationResult, config: OptimizationConfig) -> float:
        """
        Calculate composite score for ranking.
        
        Weights:
        - Test performance (primary)
        - Overfit risk (penalty)
        - Consistency (train vs test similarity)
        """
        # Test-weighted score
        test_score = (
            result.test_return_pct * 0.3 +
            result.test_sharpe * 10 * 0.3 +
            result.test_win_rate * 0.2 +
            (100 - result.test_max_drawdown_pct) * 0.2
        )
        
        # Overfit penalty
        overfit_penalty = result.overfit_risk * 0.5
        
        # Consistency bonus
        if result.train_return_pct > 0 and result.test_return_pct > 0:
            consistency = min(result.test_return_pct / result.train_return_pct, 1.0) * 10
        else:
            consistency = 0
        
        return test_score - overfit_penalty + consistency
    
    async def run_optimization(
        self,
        strategy: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        num_variations: int = 20,
        train_ratio: float = 0.7,
        base_params: Optional[Dict[str, Any]] = None,
    ) -> OptimizationJob:
        """
        Run optimization with walk-forward validation.
        """
        job_id = str(uuid4())
        start_time = datetime.now(timezone.utc)
        
        config = OptimizationConfig(
            strategy=strategy,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            train_ratio=train_ratio,
            num_variations=num_variations,
        )
        
        job = OptimizationJob(
            id=job_id,
            status=OptimizationStatus.RUNNING,
            config=config,
            results=[],
            best_result=None,
            created_at=start_time.isoformat(),
            total_variations=num_variations,
        )
        
        self._running_jobs[job_id] = True
        
        try:
            # Validate strategy
            if strategy not in STRATEGIES:
                raise ValueError(f"Unknown strategy: {strategy}")
            
            # Calculate train/test split dates
            total_days = (end_date - start_date).days
            train_days = int(total_days * train_ratio)
            
            train_end = start_date + timedelta(days=train_days)
            test_start = train_end
            
            logger.info(f"Optimization {job_id}: Train {start_date.date()} to {train_end.date()}, Test {test_start.date()} to {end_date.date()}")
            
            # Generate variations
            variations = self._generate_variations(strategy, num_variations, base_params)
            
            results = []
            
            for i, params in enumerate(variations):
                if not self._running_jobs.get(job_id, False):
                    break  # Job cancelled
                
                job.progress = i + 1
                variation_id = f"{job_id}_{i}"
                
                try:
                    # Run train backtest
                    train_result = await self.backtest_engine.run(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=train_end,
                        strategy=strategy,
                        strategy_params=params,
                        initial_capital=initial_capital,
                    )
                    
                    # Run test backtest
                    test_result = await self.backtest_engine.run(
                        symbol=symbol,
                        start_date=test_start,
                        end_date=end_date,
                        strategy=strategy,
                        strategy_params=params,
                        initial_capital=initial_capital,
                    )
                    
                    # Skip if failed
                    if train_result.status != BacktestStatus.COMPLETED or test_result.status != BacktestStatus.COMPLETED:
                        continue
                    
                    # Apply hard cap constraints
                    if train_result.metrics.max_drawdown_pct > config.max_drawdown_pct:
                        continue
                    if test_result.metrics.max_drawdown_pct > config.max_drawdown_pct:
                        continue
                    if train_result.metrics.total_trades < config.min_trades:
                        continue
                    
                    # Calculate overfit risk
                    overfit_risk, overfit_reasons = self._calculate_overfit_risk(
                        train_result.metrics.total_return_pct,
                        test_result.metrics.total_return_pct,
                        train_result.metrics.sharpe_ratio,
                        test_result.metrics.sharpe_ratio,
                        train_result.metrics.total_trades,
                        test_result.metrics.total_trades,
                    )
                    
                    opt_result = OptimizationResult(
                        variation_id=variation_id,
                        params=params,
                        train_return_pct=train_result.metrics.total_return_pct,
                        train_sharpe=train_result.metrics.sharpe_ratio,
                        train_max_drawdown_pct=train_result.metrics.max_drawdown_pct,
                        train_win_rate=train_result.metrics.win_rate,
                        train_trades=train_result.metrics.total_trades,
                        test_return_pct=test_result.metrics.total_return_pct,
                        test_sharpe=test_result.metrics.sharpe_ratio,
                        test_max_drawdown_pct=test_result.metrics.max_drawdown_pct,
                        test_win_rate=test_result.metrics.win_rate,
                        test_trades=test_result.metrics.total_trades,
                        overfit_risk=overfit_risk,
                        overfit_reasons=overfit_reasons,
                    )
                    
                    opt_result.score = self._calculate_score(opt_result, config)
                    results.append(opt_result)
                    
                except Exception as e:
                    logger.warning(f"Variation {i} failed: {e}")
                    continue
            
            # Rank results
            results.sort(key=lambda r: r.score, reverse=True)
            for i, r in enumerate(results):
                r.rank = i + 1
            
            job.results = results
            job.best_result = results[0] if results else None
            job.status = OptimizationStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc).isoformat()
            
            # Save to database
            if self.db is not None:
                await self._save_job(job)
            
            logger.info(f"Optimization {job_id} completed: {len(results)} valid variations")
            return job
            
        except Exception as e:
            logger.error(f"Optimization {job_id} failed: {e}")
            job.status = OptimizationStatus.FAILED
            job.error = str(e)
            return job
        finally:
            self._running_jobs.pop(job_id, None)
    
    async def _save_job(self, job: OptimizationJob):
        """Save optimization job to database."""
        if self.db is None:
            return
        
        try:
            await self.db.optimization_jobs.insert_one({
                **job.to_dict(),
                "all_results_count": len(job.results),
            })
        except Exception as e:
            logger.warning(f"Failed to save optimization job: {e}")
    
    async def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get optimization history."""
        if self.db is None:
            return []
        
        cursor = self.db.optimization_jobs.find(
            {},
            {"_id": 0, "results": {"$slice": 3}}  # Only top 3 results
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get specific optimization job."""
        if self.db is None:
            return None
        
        return await self.db.optimization_jobs.find_one(
            {"id": job_id},
            {"_id": 0}
        )


# Module-level instance
_optimization_engine: Optional[OptimizationEngine] = None


def get_optimization_engine() -> Optional[OptimizationEngine]:
    return _optimization_engine


def set_optimization_engine(engine: OptimizationEngine):
    global _optimization_engine
    _optimization_engine = engine
