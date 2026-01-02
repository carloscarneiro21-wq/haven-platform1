"""Strategy to Agent Mapping Service for HAVEN.

Provides:
- Mapping from backtest strategies to trading agents
- Explainable reasoning for agent suggestions
- Backtest result-based agent recommendations

Mappings:
- mean_reversion -> GRID (range-bound market maker)
- breakout/sma_crossover/momentum -> TREND (directional follower)
- DCA as baseline conservative strategy

No live execution - suggestions only.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Trading agent types."""
    GRID = "GRID"
    TREND = "TREND"
    DCA = "DCA"
    MM = "MM"  # Market Maker


@dataclass
class StrategyMapping:
    """Mapping from strategy to agent."""
    strategy: str
    agent: AgentType
    confidence: float  # 0-100
    reasons: List[str]
    market_conditions: List[str]
    risk_profile: str  # conservative, moderate, aggressive
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "agent": self.agent.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "market_conditions": self.market_conditions,
            "risk_profile": self.risk_profile,
        }


@dataclass
class AgentSuggestion:
    """Agent suggestion based on backtest results."""
    primary_agent: AgentType
    secondary_agent: Optional[AgentType]
    confidence: float
    reasons: List[str]
    metrics_analysis: Dict[str, str]
    recommended_params: Dict[str, Any]
    warnings: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_agent": self.primary_agent.value,
            "secondary_agent": self.secondary_agent.value if self.secondary_agent else None,
            "confidence": round(self.confidence, 1),
            "reasons": self.reasons,
            "metrics_analysis": self.metrics_analysis,
            "recommended_params": self.recommended_params,
            "warnings": self.warnings,
        }


# ============================================================
# STRATEGY -> AGENT MAPPINGS
# ============================================================

STRATEGY_AGENT_MAP: Dict[str, StrategyMapping] = {
    "mean_reversion": StrategyMapping(
        strategy="mean_reversion",
        agent=AgentType.GRID,
        confidence=85,
        reasons=[
            "Mean reversion strategies exploit price oscillations around a fair value",
            "GRID agents place orders at regular intervals, capturing range-bound moves",
            "Both strategies profit from prices returning to mean",
            "Bollinger Band signals align with grid level triggers",
        ],
        market_conditions=[
            "Range-bound/sideways markets",
            "Low to moderate volatility",
            "Clear support/resistance levels",
            "High liquidity pairs",
        ],
        risk_profile="moderate",
    ),
    
    "breakout": StrategyMapping(
        strategy="breakout",
        agent=AgentType.TREND,
        confidence=90,
        reasons=[
            "Breakout strategies identify trend initiation points",
            "TREND agents follow directional momentum",
            "Donchian channel breakouts signal strong trend continuation",
            "Trailing stops preserve profits during trend extensions",
        ],
        market_conditions=[
            "Trending markets with clear direction",
            "Post-consolidation breakouts",
            "High momentum environments",
            "News-driven price movements",
        ],
        risk_profile="aggressive",
    ),
    
    "sma_crossover": StrategyMapping(
        strategy="sma_crossover",
        agent=AgentType.TREND,
        confidence=85,
        reasons=[
            "SMA crossovers signal trend direction changes",
            "TREND agents capitalize on sustained directional moves",
            "Golden/death crosses provide clear entry signals",
            "Works best in extended trending markets",
        ],
        market_conditions=[
            "Medium to long-term trends",
            "Markets with clear directional bias",
            "Lower frequency trading environments",
            "Macro-driven price action",
        ],
        risk_profile="moderate",
    ),
    
    "momentum": StrategyMapping(
        strategy="momentum",
        agent=AgentType.TREND,
        confidence=80,
        reasons=[
            "RSI-based momentum identifies overbought/oversold conditions",
            "TREND agents can ride momentum waves",
            "Works for both reversals and continuations",
            "Flexible for different market regimes",
        ],
        market_conditions=[
            "Volatile markets with clear swings",
            "Momentum-driven rallies/selloffs",
            "Markets with institutional flow",
            "Event-driven volatility",
        ],
        risk_profile="moderate",
    ),
}

# DCA as baseline
DCA_MAPPING = StrategyMapping(
    strategy="dca",
    agent=AgentType.DCA,
    confidence=95,
    reasons=[
        "Dollar Cost Averaging is the safest baseline strategy",
        "Removes timing risk through regular investments",
        "Suitable for all market conditions",
        "Lowest cognitive and emotional burden",
    ],
    market_conditions=[
        "All market conditions (universal)",
        "Best for long-term accumulation",
        "Ideal when direction is uncertain",
        "Works in both bull and bear markets",
    ],
    risk_profile="conservative",
)


# ============================================================
# MAPPING SERVICE
# ============================================================

class StrategyAgentMapper:
    """Maps backtest strategies to trading agents with explanations."""
    
    def __init__(self):
        self.mappings = STRATEGY_AGENT_MAP
        self.dca_baseline = DCA_MAPPING
    
    def get_all_mappings(self) -> List[Dict[str, Any]]:
        """Get all strategy-agent mappings."""
        result = []
        
        for mapping in self.mappings.values():
            result.append(mapping.to_dict())
        
        # Add DCA baseline
        result.append(self.dca_baseline.to_dict())
        
        return result
    
    def get_mapping(self, strategy: str) -> Optional[StrategyMapping]:
        """Get mapping for a specific strategy."""
        return self.mappings.get(strategy)
    
    def suggest_agent_from_backtest(
        self,
        strategy: str,
        metrics: Dict[str, Any],
        symbol: str,
    ) -> AgentSuggestion:
        """
        Suggest an agent based on backtest results.
        
        Args:
            strategy: Strategy used in backtest
            metrics: Backtest metrics (return_pct, sharpe, drawdown, win_rate, etc.)
            symbol: Trading symbol
        
        Returns:
            AgentSuggestion with reasoning
        """
        mapping = self.mappings.get(strategy)
        if not mapping:
            # Unknown strategy - suggest DCA as safe default
            return AgentSuggestion(
                primary_agent=AgentType.DCA,
                secondary_agent=None,
                confidence=70,
                reasons=[
                    f"Strategy '{strategy}' has no direct agent mapping",
                    "DCA recommended as safe baseline",
                ],
                metrics_analysis={},
                recommended_params={},
                warnings=["Unknown strategy - manual review recommended"],
            )
        
        # Analyze metrics
        total_return = metrics.get("total_return_pct", 0)
        sharpe = metrics.get("sharpe_ratio", 0)
        max_drawdown = metrics.get("max_drawdown_pct", 0)
        win_rate = metrics.get("win_rate", 0)
        profit_factor = metrics.get("profit_factor", 0)
        total_trades = metrics.get("total_trades", 0)
        
        reasons = list(mapping.reasons)
        warnings = []
        metrics_analysis = {}
        confidence = mapping.confidence
        
        # Analyze return
        if total_return > 50:
            metrics_analysis["return"] = f"Excellent return ({total_return:.1f}%) supports aggressive allocation"
            confidence += 5
        elif total_return > 20:
            metrics_analysis["return"] = f"Good return ({total_return:.1f}%) validates strategy"
        elif total_return > 0:
            metrics_analysis["return"] = f"Modest positive return ({total_return:.1f}%)"
        else:
            metrics_analysis["return"] = f"Negative return ({total_return:.1f}%) - use with caution"
            confidence -= 15
            warnings.append("Backtest showed negative returns")
        
        # Analyze Sharpe
        if sharpe > 2:
            metrics_analysis["sharpe"] = f"Excellent risk-adjusted return (Sharpe: {sharpe:.2f})"
            confidence += 5
        elif sharpe > 1:
            metrics_analysis["sharpe"] = f"Good risk-adjusted return (Sharpe: {sharpe:.2f})"
        elif sharpe > 0:
            metrics_analysis["sharpe"] = f"Acceptable risk-adjusted return (Sharpe: {sharpe:.2f})"
        else:
            metrics_analysis["sharpe"] = f"Poor risk-adjusted return (Sharpe: {sharpe:.2f})"
            confidence -= 10
            warnings.append("Low Sharpe ratio indicates high risk")
        
        # Analyze drawdown
        if max_drawdown < 10:
            metrics_analysis["drawdown"] = f"Low drawdown ({max_drawdown:.1f}%) - conservative risk"
        elif max_drawdown < 20:
            metrics_analysis["drawdown"] = f"Moderate drawdown ({max_drawdown:.1f}%)"
        elif max_drawdown < 30:
            metrics_analysis["drawdown"] = f"High drawdown ({max_drawdown:.1f}%) - aggressive risk"
            warnings.append("Consider tighter risk controls")
        else:
            metrics_analysis["drawdown"] = f"Very high drawdown ({max_drawdown:.1f}%) - reduce position size"
            confidence -= 15
            warnings.append("Excessive drawdown risk")
        
        # Analyze win rate
        if win_rate > 60:
            metrics_analysis["win_rate"] = f"High win rate ({win_rate:.1f}%) supports strategy"
        elif win_rate > 45:
            metrics_analysis["win_rate"] = f"Moderate win rate ({win_rate:.1f}%)"
        else:
            metrics_analysis["win_rate"] = f"Low win rate ({win_rate:.1f}%) - requires large winners"
            if profit_factor < 1.5:
                warnings.append("Low win rate with low profit factor is risky")
        
        # Trade count analysis
        if total_trades < 10:
            warnings.append(f"Low trade count ({total_trades}) - results may not be statistically significant")
            confidence -= 10
        
        # Determine secondary agent
        secondary_agent = None
        if mapping.agent == AgentType.TREND and max_drawdown > 20:
            secondary_agent = AgentType.DCA
            reasons.append("DCA suggested as hedge due to high drawdown risk")
        elif mapping.agent == AgentType.GRID and total_return > 30:
            secondary_agent = AgentType.TREND
            reasons.append("Strong returns suggest partial TREND allocation")
        
        # Generate recommended params based on agent type
        recommended_params = self._generate_agent_params(
            mapping.agent, metrics, symbol
        )
        
        # Clamp confidence
        confidence = max(30, min(95, confidence))
        
        return AgentSuggestion(
            primary_agent=mapping.agent,
            secondary_agent=secondary_agent,
            confidence=confidence,
            reasons=reasons,
            metrics_analysis=metrics_analysis,
            recommended_params=recommended_params,
            warnings=warnings,
        )
    
    def _generate_agent_params(
        self,
        agent: AgentType,
        metrics: Dict[str, Any],
        symbol: str,
    ) -> Dict[str, Any]:
        """Generate suggested agent parameters based on metrics."""
        max_drawdown = metrics.get("max_drawdown_pct", 20)
        sharpe = metrics.get("sharpe_ratio", 1)
        
        # Adjust position size based on drawdown
        if max_drawdown < 15:
            position_size = 0.15  # 15% of portfolio
        elif max_drawdown < 25:
            position_size = 0.10
        else:
            position_size = 0.05
        
        base_params = {
            "symbol": symbol,
            "position_size_pct": position_size,
            "max_drawdown_limit": min(max_drawdown * 1.2, 30),  # 20% buffer, max 30%
        }
        
        if agent == AgentType.GRID:
            base_params.update({
                "grid_levels": 10,
                "grid_spacing_pct": 1.0,
                "rebalance_threshold": 0.5,
            })
        elif agent == AgentType.TREND:
            base_params.update({
                "trend_lookback_periods": 20,
                "entry_threshold": 0.02,
                "trailing_stop_pct": 0.03,
            })
        elif agent == AgentType.DCA:
            base_params.update({
                "interval_hours": 24,
                "amount_per_interval": 100,
            })
        
        return base_params


# Module-level instance
_strategy_mapper: Optional[StrategyAgentMapper] = None


def get_strategy_mapper() -> StrategyAgentMapper:
    global _strategy_mapper
    if _strategy_mapper is None:
        _strategy_mapper = StrategyAgentMapper()
    return _strategy_mapper
