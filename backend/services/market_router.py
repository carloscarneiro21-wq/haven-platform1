"""
Market Router Service for Capital Growth Module
===============================================

Non-trading service that:
1. Detects market regime (RANGE, TREND, HIGH_VOL, CHOP)
2. Recommends which agent to activate (MM or MOM)
3. Selects the appropriate preset set
4. Provides deterministic reason codes

Uses data from ccxt (Kraken + Binance).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
from pydantic import BaseModel, Field
import numpy as np

logger = logging.getLogger(__name__)


# ============ Symbol Whitelist ============

GROWTH_SYMBOL_WHITELIST = [
    "BTC/USDT",
    "ETH/USDT", 
    "BNB/USDT",
    "BTC/EUR",
    "ETH/EUR",
]

SUPPORTED_VENUES = ["binance", "kraken"]


# Import event enums lazily
def _get_event_enums():
    """Get event enums, importing lazily."""
    try:
        from services.event_logger import EventSeverity, EventCategory
        return EventSeverity, EventCategory
    except ImportError:
        return None, None


# ============ Enums ============

class MarketRegime(str, Enum):
    """Detected market regime."""
    RANGE = "RANGE"          # Sideways - good for MM
    TREND = "TREND"          # Strong direction - good for MOM
    HIGH_VOL = "HIGH_VOL"    # High volatility - careful/aggressive MOM
    CHOP = "CHOP"            # Choppy/unpredictable - avoid or defensive


class RecommendedAgent(str, Enum):
    """Agent recommendation from router."""
    MM = "MM"
    MOM = "MOM"
    PAUSE = "PAUSE"


class Confidence(str, Enum):
    """Confidence level in recommendation."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ============ Reason Codes ============

REASON_CODES = {
    # Regime detection
    "REGIME_RANGE_LOW_ADX": "ADX baixo ({adx:.1f}) indica mercado lateral - favorável para MM",
    "REGIME_RANGE_TIGHT_BB": "Bandas de Bollinger apertadas - range definido",
    "REGIME_TREND_HIGH_ADX": "ADX alto ({adx:.1f}) indica tendência forte - favorável para MOM",
    "REGIME_TREND_MA_ALIGNED": "Médias móveis alinhadas na direção da tendência",
    "REGIME_HIGH_VOL_ATR": "ATR% elevado ({atr_pct:.2f}%) - alta volatilidade",
    "REGIME_CHOP_MIXED_SIGNALS": "Sinais mistos - mercado incerto",
    "REGIME_CHOP_WHIPSAW": "Detecção de whipsaw - evitar trades",
    
    # Agent selection
    "SELECT_MM_RANGE_FAVORABLE": "Mercado lateral favorece Market Making",
    "SELECT_MM_LOW_SPREAD": "Spread baixo ({spread_pct:.3f}%) adequado para MM",
    "SELECT_MOM_TREND_STRONG": "Tendência forte justifica Momentum",
    "SELECT_MOM_VOL_OPPORTUNITY": "Volatilidade cria oportunidade para MOM agressivo",
    "SELECT_PAUSE_CHOP": "Mercado muito incerto - pausar trading",
    "SELECT_PAUSE_SPREAD_WIDE": "Spread muito largo ({spread_pct:.3f}%) - pausar",
    "SELECT_PAUSE_DATA_QUALITY": "Qualidade de dados insuficiente",
    
    # Preset selection
    "PRESET_MM_TIGHT_LOW_VOL": "Volatilidade baixa -> MM Tight Range",
    "PRESET_MM_NORMAL": "Condições normais -> MM Normal Range",
    "PRESET_MM_WIDE_HIGH_VOL": "Volatilidade alta mas ranging -> MM Wide Vol",
    "PRESET_MM_DEFENSIVE": "Sinais de cautela -> MM Defensive",
    "PRESET_MM_TREND_AVOID": "Tendência detectada -> MM pausado",
    "PRESET_MOM_CONSERVATIVE": "Breakout setup mas cautela -> MOM Conservative",
    "PRESET_MOM_STANDARD": "Breakout setup normal -> MOM Standard",
    "PRESET_MOM_AGGRESSIVE": "Alta volatilidade + volume -> MOM Aggressive",
    "PRESET_MOM_DEFENSIVE": "Recuperação pós-drawdown -> MOM Defensive",
    
    # Viability
    "VIABILITY_OK": "Viabilidade confirmada: edge > cost * {multiplier:.1f}",
    "VIABILITY_FAILED": "Viabilidade falhou: edge ({edge:.4f}) <= cost ({cost:.4f}) * {multiplier:.1f}",
    
    # Data quality
    "DATA_OK": "Dados de mercado atualizados e consistentes",
    "DATA_STALE": "Dados desatualizados há {minutes:.0f} minutos",
    "DATA_INCONSISTENT": "Inconsistência entre exchanges",
}


def format_reason(code: str, **kwargs) -> str:
    """Format a reason code with parameters."""
    template = REASON_CODES.get(code, code)
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# ============ Market Metrics ============

class MarketMetrics(BaseModel):
    """Collected market metrics for regime detection."""
    symbol: str
    venue: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Price data
    last_price: float
    bid: float
    ask: float
    spread_pct: float
    
    # Volatility
    atr_pct: float = Field(description="ATR as % of price")
    atr_14: float = Field(description="14-period ATR absolute")
    bollinger_width_pct: float = Field(default=0, description="BB width as % of price")
    
    # Trend
    adx: float = Field(default=0, description="ADX value 0-100")
    ma_slope_pct: float = Field(default=0, description="MA slope as % change")
    trend_direction: int = Field(default=0, description="-1, 0, or 1")
    
    # Volume
    volume_24h: float = Field(default=0)
    volume_ratio: float = Field(default=1.0, description="Current vs average volume")
    
    # Quality
    data_age_seconds: float = Field(default=0)
    data_quality: float = Field(default=1.0, ge=0, le=1)


# ============ Router Output ============

class RouterDecision(BaseModel):
    """Output from Market Router."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    venue: str
    
    # Regime
    regime: MarketRegime
    regime_confidence: Confidence
    regime_reasons: List[str] = []
    
    # Recommendation
    recommended_agent: RecommendedAgent
    recommended_preset_id: str
    agent_confidence: Confidence
    agent_reasons: List[str] = []
    
    # Raw metrics (for debugging)
    metrics: Optional[MarketMetrics] = None
    
    # Viability check
    viability_passed: bool = True
    viability_reasons: List[str] = []
    
    # All reason codes combined
    all_reason_codes: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API/logging."""
        return self.model_dump()


# ============ Market Router Service ============

class MarketRouter:
    """
    Non-trading service that detects market regime and recommends agents.
    
    Features:
    - Regime detection (RANGE, TREND, HIGH_VOL, CHOP)
    - Agent recommendation (MM, MOM, PAUSE)
    - Preset selection based on conditions
    - Deterministic reason codes
    - Audit trail
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        system_config_service=None,
        event_logger=None,
        pair_advisor=None,
    ):
        self.db = db
        self.system_config_service = system_config_service
        self.event_logger = event_logger
        self.pair_advisor = pair_advisor
        self._last_decisions: Dict[str, RouterDecision] = {}  # symbol -> last decision
    
    def is_symbol_whitelisted(self, symbol: str) -> bool:
        """Check if symbol is in the Growth Module whitelist."""
        return symbol.upper() in [s.upper() for s in GROWTH_SYMBOL_WHITELIST]
    
    def get_whitelisted_symbols(self) -> List[str]:
        """Get list of whitelisted symbols."""
        return GROWTH_SYMBOL_WHITELIST.copy()
    
    async def select_best_venue(self, symbol: str) -> Tuple[str, str]:
        """
        Select best venue for a symbol using Pair Advisor.
        
        Returns:
            (venue, reason) tuple
        """
        if not self.is_symbol_whitelisted(symbol):
            return "binance", f"Symbol {symbol} not whitelisted - default to Binance"
        
        # If Pair Advisor is available, use it
        if self.pair_advisor:
            try:
                from services.pair_advisor import AgentStrategy
                rec = await self.pair_advisor.get_recommendation_for_pair(
                    symbol, 
                    AgentStrategy.GRID  # Use GRID as proxy for MM
                )
                if rec and "grid" in rec:
                    venue = rec["grid"].get("venue", "binance").lower()
                    reason = rec["grid"].get("venue_selection_reason", "Pair Advisor selection")
                    return venue, reason
            except Exception as e:
                logger.warning(f"Pair Advisor failed for {symbol}: {e}")
        
        # Default venue selection based on symbol
        if symbol.endswith("/EUR"):
            return "kraken", "EUR pairs have better liquidity on Kraken"
        else:
            return "binance", "USDT pairs have better liquidity on Binance"
    
    async def analyze(
        self,
        metrics: MarketMetrics,
        current_capital_eur: float = 100.0,
        recent_pnl_pct: float = 0.0,
    ) -> RouterDecision:
        """
        Analyze market and produce routing decision.
        
        Args:
            metrics: Current market metrics
            current_capital_eur: User's current capital
            recent_pnl_pct: Recent P&L % (for defensive mode detection)
        
        Returns:
            RouterDecision with regime, agent, and preset recommendation
        """
        decision = RouterDecision(
            symbol=metrics.symbol,
            venue=metrics.venue,
            regime=MarketRegime.CHOP,  # Default
            regime_confidence=Confidence.LOW,
            recommended_agent=RecommendedAgent.PAUSE,
            recommended_preset_id="",
            agent_confidence=Confidence.LOW,
            metrics=metrics,
        )
        
        # Get config thresholds
        thresholds = await self._get_thresholds()
        
        # Step 1: Check data quality
        if not self._check_data_quality(metrics, decision, thresholds):
            return decision
        
        # Step 2: Detect regime
        self._detect_regime(metrics, decision, thresholds)
        
        # Step 3: Select agent
        self._select_agent(metrics, decision, thresholds, recent_pnl_pct)
        
        # Step 4: Select preset
        self._select_preset(metrics, decision, thresholds, recent_pnl_pct)
        
        # Step 5: Check viability (basic, detailed in ViabilityService)
        self._basic_viability_check(metrics, decision, thresholds)
        
        # Combine all reasons
        decision.all_reason_codes = (
            decision.regime_reasons +
            decision.agent_reasons +
            decision.viability_reasons
        )
        
        # Cache decision
        self._last_decisions[metrics.symbol] = decision
        
        # Log decision
        await self._log_decision(decision)
        
        return decision
    
    async def _get_thresholds(self) -> Dict[str, Any]:
        """Get regime thresholds from config."""
        if self.system_config_service:
            config = await self.system_config_service.get_config()
            return config.regime_thresholds.model_dump()
        
        # Defaults
        return {
            "atr_low_pct": 0.5,
            "atr_high_pct": 2.0,
            "adx_trend_threshold": 25.0,
            "adx_strong_trend": 35.0,
            "volume_spike_multiplier": 2.0,
            "volume_dry_threshold": 0.5,
            "spread_tight_pct": 0.05,
            "spread_wide_pct": 0.15,
        }
    
    def _check_data_quality(
        self,
        metrics: MarketMetrics,
        decision: RouterDecision,
        thresholds: Dict[str, Any],
    ) -> bool:
        """Check if data quality is sufficient."""
        # Check data age
        if metrics.data_age_seconds > 60:
            decision.agent_reasons.append(
                format_reason("DATA_STALE", minutes=metrics.data_age_seconds / 60)
            )
            decision.recommended_agent = RecommendedAgent.PAUSE
            decision.agent_confidence = Confidence.HIGH
            decision.recommended_preset_id = ""
            return False
        
        # Check data quality score
        if metrics.data_quality < 0.8:
            decision.agent_reasons.append(format_reason("SELECT_PAUSE_DATA_QUALITY"))
            decision.recommended_agent = RecommendedAgent.PAUSE
            decision.agent_confidence = Confidence.HIGH
            return False
        
        decision.agent_reasons.append(format_reason("DATA_OK"))
        return True
    
    def _detect_regime(
        self,
        metrics: MarketMetrics,
        decision: RouterDecision,
        thresholds: Dict[str, Any],
    ) -> None:
        """Detect market regime from metrics."""
        atr_pct = metrics.atr_pct
        adx = metrics.adx
        volume_ratio = metrics.volume_ratio
        spread_pct = metrics.spread_pct
        
        # === High Volatility Detection ===
        if atr_pct >= thresholds["atr_high_pct"]:
            decision.regime = MarketRegime.HIGH_VOL
            decision.regime_confidence = Confidence.HIGH
            decision.regime_reasons.append(
                format_reason("REGIME_HIGH_VOL_ATR", atr_pct=atr_pct)
            )
            return
        
        # === Trend Detection ===
        if adx >= thresholds["adx_strong_trend"]:
            decision.regime = MarketRegime.TREND
            decision.regime_confidence = Confidence.HIGH
            decision.regime_reasons.append(
                format_reason("REGIME_TREND_HIGH_ADX", adx=adx)
            )
            if metrics.trend_direction != 0:
                decision.regime_reasons.append(
                    format_reason("REGIME_TREND_MA_ALIGNED")
                )
            return
        
        if adx >= thresholds["adx_trend_threshold"]:
            decision.regime = MarketRegime.TREND
            decision.regime_confidence = Confidence.MEDIUM
            decision.regime_reasons.append(
                format_reason("REGIME_TREND_HIGH_ADX", adx=adx)
            )
            return
        
        # === Range Detection ===
        if adx < thresholds["adx_trend_threshold"]:
            if atr_pct <= thresholds["atr_low_pct"]:
                decision.regime = MarketRegime.RANGE
                decision.regime_confidence = Confidence.HIGH
                decision.regime_reasons.append(
                    format_reason("REGIME_RANGE_LOW_ADX", adx=adx)
                )
                decision.regime_reasons.append(
                    format_reason("REGIME_RANGE_TIGHT_BB")
                )
                return
            elif atr_pct < thresholds["atr_high_pct"]:
                decision.regime = MarketRegime.RANGE
                decision.regime_confidence = Confidence.MEDIUM
                decision.regime_reasons.append(
                    format_reason("REGIME_RANGE_LOW_ADX", adx=adx)
                )
                return
        
        # === Chop Detection (default) ===
        decision.regime = MarketRegime.CHOP
        decision.regime_confidence = Confidence.LOW
        decision.regime_reasons.append(
            format_reason("REGIME_CHOP_MIXED_SIGNALS")
        )
    
    def _select_agent(
        self,
        metrics: MarketMetrics,
        decision: RouterDecision,
        thresholds: Dict[str, Any],
        recent_pnl_pct: float,
    ) -> None:
        """Select which agent to activate based on regime."""
        spread_pct = metrics.spread_pct
        
        # Check spread first
        if spread_pct > thresholds["spread_wide_pct"]:
            decision.recommended_agent = RecommendedAgent.PAUSE
            decision.agent_confidence = Confidence.HIGH
            decision.agent_reasons.append(
                format_reason("SELECT_PAUSE_SPREAD_WIDE", spread_pct=spread_pct)
            )
            return
        
        # Based on regime
        if decision.regime == MarketRegime.RANGE:
            decision.recommended_agent = RecommendedAgent.MM
            decision.agent_confidence = decision.regime_confidence
            decision.agent_reasons.append(
                format_reason("SELECT_MM_RANGE_FAVORABLE")
            )
            if spread_pct <= thresholds["spread_tight_pct"]:
                decision.agent_reasons.append(
                    format_reason("SELECT_MM_LOW_SPREAD", spread_pct=spread_pct)
                )
        
        elif decision.regime == MarketRegime.TREND:
            decision.recommended_agent = RecommendedAgent.MOM
            decision.agent_confidence = decision.regime_confidence
            decision.agent_reasons.append(
                format_reason("SELECT_MOM_TREND_STRONG")
            )
        
        elif decision.regime == MarketRegime.HIGH_VOL:
            # High vol can favor MOM aggressive if conditions are right
            if metrics.volume_ratio >= thresholds["volume_spike_multiplier"]:
                decision.recommended_agent = RecommendedAgent.MOM
                decision.agent_confidence = Confidence.MEDIUM
                decision.agent_reasons.append(
                    format_reason("SELECT_MOM_VOL_OPPORTUNITY")
                )
            else:
                # High vol without volume confirmation = be careful
                decision.recommended_agent = RecommendedAgent.PAUSE
                decision.agent_confidence = Confidence.MEDIUM
                decision.agent_reasons.append(
                    format_reason("SELECT_PAUSE_CHOP")
                )
        
        else:  # CHOP
            decision.recommended_agent = RecommendedAgent.PAUSE
            decision.agent_confidence = Confidence.HIGH
            decision.agent_reasons.append(
                format_reason("SELECT_PAUSE_CHOP")
            )
    
    def _select_preset(
        self,
        metrics: MarketMetrics,
        decision: RouterDecision,
        thresholds: Dict[str, Any],
        recent_pnl_pct: float,
    ) -> None:
        """Select specific preset based on conditions."""
        atr_pct = metrics.atr_pct
        adx = metrics.adx
        volume_ratio = metrics.volume_ratio
        
        # Check if in recovery mode (recent losses)
        in_recovery = recent_pnl_pct < -3.0
        
        if decision.recommended_agent == RecommendedAgent.MM:
            if decision.regime == MarketRegime.TREND:
                # Trend detected, pause MM
                decision.recommended_preset_id = "MM_5_TREND_AVOID"
                decision.agent_reasons.append(format_reason("PRESET_MM_TREND_AVOID"))
            elif in_recovery:
                decision.recommended_preset_id = "MM_4_DEFENSIVE"
                decision.agent_reasons.append(format_reason("PRESET_MM_DEFENSIVE"))
            elif atr_pct <= thresholds["atr_low_pct"]:
                decision.recommended_preset_id = "MM_1_TIGHT_RANGE"
                decision.agent_reasons.append(format_reason("PRESET_MM_TIGHT_LOW_VOL"))
            elif atr_pct >= thresholds["atr_high_pct"] * 0.7:  # 70% of high threshold
                decision.recommended_preset_id = "MM_3_WIDE_VOL"
                decision.agent_reasons.append(format_reason("PRESET_MM_WIDE_HIGH_VOL"))
            else:
                decision.recommended_preset_id = "MM_2_NORMAL_RANGE"
                decision.agent_reasons.append(format_reason("PRESET_MM_NORMAL"))
        
        elif decision.recommended_agent == RecommendedAgent.MOM:
            if in_recovery:
                decision.recommended_preset_id = "MOM_4_DEFENSIVE_RECOVERY"
                decision.agent_reasons.append(format_reason("PRESET_MOM_DEFENSIVE"))
            elif (decision.regime == MarketRegime.HIGH_VOL and 
                  volume_ratio >= thresholds["volume_spike_multiplier"]):
                decision.recommended_preset_id = "MOM_3_HIGH_VOL_AGGRESSIVE"
                decision.agent_reasons.append(format_reason("PRESET_MOM_AGGRESSIVE"))
            elif adx >= thresholds["adx_strong_trend"]:
                decision.recommended_preset_id = "MOM_2_BREAKOUT_STANDARD"
                decision.agent_reasons.append(format_reason("PRESET_MOM_STANDARD"))
            else:
                decision.recommended_preset_id = "MOM_1_BREAKOUT_CONSERVATIVE"
                decision.agent_reasons.append(format_reason("PRESET_MOM_CONSERVATIVE"))
    
    def _basic_viability_check(
        self,
        metrics: MarketMetrics,
        decision: RouterDecision,
        thresholds: Dict[str, Any],
    ) -> None:
        """Basic viability check (spread-based)."""
        spread_pct = metrics.spread_pct
        
        # Estimate cost (spread + approximate fees)
        estimated_cost_pct = spread_pct + 0.10  # spread + ~0.1% fees
        
        # Get multiplier based on agent
        if decision.recommended_agent == RecommendedAgent.MM:
            multiplier = 2.0
        elif decision.recommended_agent == RecommendedAgent.MOM:
            if "DEFENSIVE" in decision.recommended_preset_id:
                multiplier = 3.0
            elif "CONSERVATIVE" in decision.recommended_preset_id:
                multiplier = 2.5
            elif "AGGRESSIVE" in decision.recommended_preset_id:
                multiplier = 2.0
            else:
                multiplier = 2.2
        else:
            multiplier = 2.0
        
        # Estimate edge based on ATR
        estimated_edge_pct = metrics.atr_pct * 0.3  # Capture ~30% of daily range
        
        if estimated_edge_pct > estimated_cost_pct * multiplier:
            decision.viability_passed = True
            decision.viability_reasons.append(
                format_reason("VIABILITY_OK", multiplier=multiplier)
            )
        else:
            decision.viability_passed = False
            decision.viability_reasons.append(
                format_reason(
                    "VIABILITY_FAILED",
                    edge=estimated_edge_pct,
                    cost=estimated_cost_pct,
                    multiplier=multiplier
                )
            )
            # Downgrade to PAUSE if viability fails
            decision.recommended_agent = RecommendedAgent.PAUSE
            decision.recommended_preset_id = ""
    
    async def _log_decision(self, decision: RouterDecision) -> None:
        """Log routing decision for audit."""
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if EventSeverity and EventCategory:
                await self.event_logger.emit(
                    type="ROUTER_DECISION",
                    category=EventCategory.SYSTEM,
                    severity=EventSeverity.INFO,
                    message=f"Router: {decision.symbol} -> {decision.recommended_agent.value} ({decision.recommended_preset_id})",
                    context={
                        "symbol": decision.symbol,
                        "venue": decision.venue,
                        "regime": decision.regime.value,
                        "regime_confidence": decision.regime_confidence.value,
                        "recommended_agent": decision.recommended_agent.value,
                        "recommended_preset": decision.recommended_preset_id,
                        "agent_confidence": decision.agent_confidence.value,
                        "viability_passed": decision.viability_passed,
                        "all_reasons": decision.all_reason_codes,
                    },
                    tags=["router", "growth"]
                )
    
    def get_last_decision(self, symbol: str) -> Optional[RouterDecision]:
        """Get last routing decision for a symbol."""
        return self._last_decisions.get(symbol)
    
    def get_all_decisions(self) -> Dict[str, RouterDecision]:
        """Get all cached routing decisions."""
        return self._last_decisions.copy()


# ============ Helper: Calculate Metrics from OHLCV ============

def calculate_metrics_from_ohlcv(
    symbol: str,
    venue: str,
    ohlcv: List[List],  # [[timestamp, open, high, low, close, volume], ...]
    bid: float,
    ask: float,
    last_data_timestamp: datetime,
) -> MarketMetrics:
    """
    Calculate market metrics from OHLCV data.
    
    Args:
        symbol: Trading pair
        venue: Exchange name
        ohlcv: List of OHLCV candles (newest last)
        bid: Current bid price
        ask: Current ask price
        last_data_timestamp: When data was received
    
    Returns:
        MarketMetrics object
    """
    if len(ohlcv) < 20:
        raise ValueError("Need at least 20 candles for metrics")
    
    # Convert to numpy arrays
    closes = np.array([c[4] for c in ohlcv])
    highs = np.array([c[2] for c in ohlcv])
    lows = np.array([c[3] for c in ohlcv])
    volumes = np.array([c[5] for c in ohlcv])
    
    last_price = closes[-1]
    spread_pct = ((ask - bid) / last_price) * 100
    
    # ATR (14-period)
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    atr_14 = np.mean(tr[-14:])
    atr_pct = (atr_14 / last_price) * 100
    
    # ADX (simplified - using directional movement)
    plus_dm = np.maximum(highs[1:] - highs[:-1], 0)
    minus_dm = np.maximum(lows[:-1] - lows[1:], 0)
    
    # Where plus_dm < minus_dm, set plus_dm to 0 (and vice versa)
    plus_dm = np.where(plus_dm > minus_dm, plus_dm, 0)
    minus_dm = np.where(minus_dm > plus_dm, minus_dm, 0)
    
    # Smoothed values
    atr_smooth = np.mean(tr[-14:])
    plus_di = 100 * np.mean(plus_dm[-14:]) / (atr_smooth if atr_smooth > 0 else 1)
    minus_di = 100 * np.mean(minus_dm[-14:]) / (atr_smooth if atr_smooth > 0 else 1)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di if plus_di + minus_di > 0 else 1)
    adx = dx  # Simplified - would normally smooth over 14 periods
    
    # MA slope (20-period)
    ma_20 = np.mean(closes[-20:])
    ma_20_prev = np.mean(closes[-21:-1])
    ma_slope_pct = ((ma_20 - ma_20_prev) / ma_20_prev) * 100 if ma_20_prev > 0 else 0
    
    # Trend direction
    if ma_slope_pct > 0.1:
        trend_direction = 1
    elif ma_slope_pct < -0.1:
        trend_direction = -1
    else:
        trend_direction = 0
    
    # Volume ratio
    avg_volume = np.mean(volumes[-20:])
    current_volume = volumes[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    
    # Bollinger width
    std_20 = np.std(closes[-20:])
    bb_width_pct = (4 * std_20 / ma_20) * 100 if ma_20 > 0 else 0
    
    # Data age
    now = datetime.now(timezone.utc)
    data_age = (now - last_data_timestamp).total_seconds()
    
    return MarketMetrics(
        symbol=symbol,
        venue=venue,
        last_price=last_price,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        atr_pct=atr_pct,
        atr_14=atr_14,
        bollinger_width_pct=bb_width_pct,
        adx=adx,
        ma_slope_pct=ma_slope_pct,
        trend_direction=trend_direction,
        volume_24h=float(np.sum(volumes[-24:])) if len(volumes) >= 24 else float(np.sum(volumes)),
        volume_ratio=volume_ratio,
        data_age_seconds=data_age,
        data_quality=1.0 if data_age < 60 else max(0, 1 - (data_age - 60) / 300),
    )
