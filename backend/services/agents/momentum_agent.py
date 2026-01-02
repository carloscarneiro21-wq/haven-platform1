"""
Momentum Agent - Intent Plan Generator
======================================

Produces hypothetical orders for paper trading validation.
Does NOT execute trades - only generates "intent plans".

Core MOM Strategy:
- Identify breakout setups
- Enter with tight stop loss
- Trail profit with take-profit targets
- Risk-adjusted position sizing
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field
import numpy as np

logger = logging.getLogger(__name__)


# ============ Enums ============

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    MOMENTUM_CONTINUATION = "MOMENTUM_CONTINUATION"
    NO_SIGNAL = "NO_SIGNAL"


class IntentStatus(str, Enum):
    READY = "READY"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    NO_OPPORTUNITY = "NO_OPPORTUNITY"
    COOLDOWN = "COOLDOWN"


# ============ Reason Codes ============

MOM_REASON_CODES = {
    # Signal detection
    "SIGNAL_BREAKOUT_UP": "Breakout de alta detectado: preço > resistência {resistance:.2f}",
    "SIGNAL_BREAKOUT_DOWN": "Breakout de baixa detectado: preço < suporte {support:.2f}",
    "SIGNAL_MOMENTUM_STRONG": "Momentum forte: ADX={adx:.1f}, direção={direction}",
    "SIGNAL_VOLUME_CONFIRMED": "Volume confirma movimento: {volume_ratio:.1f}x média",
    "SIGNAL_NONE": "Nenhum sinal de momentum detectado",
    
    # Entry calculation
    "ENTRY_PRICE_SET": "Preço de entrada: {entry_price:.2f} ({distance_pct:.2f}% do mid)",
    "STOP_LOSS_SET": "Stop loss: {stop_price:.2f} ({sl_pct:.2f}% de risco)",
    "TAKE_PROFIT_SET": "Take profit: {tp_price:.2f} ({tp_pct:.2f}% target)",
    "TRAILING_ENABLED": "Trailing stop ativado: {trail_pct:.2f}% de distância",
    
    # Position sizing
    "POSITION_SIZED": "Tamanho da posição: {size_eur:.2f}€ ({risk_pct:.1f}% do budget)",
    "POSITION_CAPPED": "Posição limitada ao máximo: {max_eur:.2f}€",
    "R_R_RATIO": "Risk/Reward ratio: 1:{rr_ratio:.1f}",
    
    # Pause reasons
    "PAUSE_NO_TREND": "Sem tendência: ADX={adx:.1f} < {threshold}",
    "PAUSE_LOW_VOLATILITY": "Volatilidade insuficiente: ATR={atr_pct:.2f}%",
    "PAUSE_SPREAD_WIDE": "Spread muito largo: {spread_pct:.3f}%",
    "PAUSE_COOLDOWN": "Cooldown ativo: próximo trade em {minutes:.0f} min",
    "PAUSE_MAX_TRADES": "Limite diário atingido: {count}/{max} trades",
    "PAUSE_VIABILITY": "Viabilidade falhou: edge < custo * {multiplier:.1f}",
    "PAUSE_GUARDIAN": "Bloqueado pelo Guardian: {reason}",
    "PAUSE_NO_BUDGET": "Budget insuficiente para operar",
    "PAUSE_CHOP_MARKET": "Mercado choppy - evitar entradas",
}


# ============ Models ============

class MOMPresetConfig(BaseModel):
    """Configuration from MOM preset."""
    preset_id: str
    take_profit_pct: float = 2.0
    stop_loss_pct: float = 1.0
    trailing_enabled: bool = True
    trailing_pct: float = 1.5
    max_trades_per_day: int = 5
    cooldown_minutes: int = 30
    viability_multiplier: float = 2.5
    max_position_eur: float = 30.0
    adx_threshold: float = 25.0
    atr_min_pct: float = 1.0


class IntendedEntry(BaseModel):
    """A hypothetical entry in the intent plan."""
    signal_type: SignalType
    side: OrderSide
    entry_price: float
    entry_size_base: float
    entry_size_eur: float
    stop_loss_price: float
    stop_loss_pct: float
    take_profit_price: float
    take_profit_pct: float
    trailing_enabled: bool = False
    trailing_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    max_risk_eur: float = 0.0
    expected_win_rate: float = 0.5
    rationale: str = ""


class MOMIntentPlan(BaseModel):
    """Intent plan from Momentum agent."""
    agent_type: str = "MOM"
    agent_id: str
    preset_id: str
    symbol: str
    venue: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Status
    status: IntentStatus = IntentStatus.READY
    
    # Market context
    current_price: float
    bid: float
    ask: float
    spread_pct: float
    atr_pct: float = 0.0
    adx: float = 0.0
    trend_direction: int = 0  # -1, 0, 1
    volume_ratio: float = 1.0
    
    # Signal
    signal: SignalType = SignalType.NO_SIGNAL
    signal_strength: float = 0.0  # 0-100
    
    # Intended entry
    entry: Optional[IntendedEntry] = None
    
    # Trading stats
    trades_today: int = 0
    cooldown_until: Optional[datetime] = None
    
    # Expected outcomes
    expected_value_eur: float = 0.0
    
    # Reason codes with severity
    reason_codes: List[Dict[str, Any]] = []
    
    def add_reason(self, code: str, severity: str = "info", **kwargs):
        """Add a reason code with formatted message."""
        template = MOM_REASON_CODES.get(code, code)
        try:
            message = template.format(**kwargs)
        except KeyError:
            message = template
        self.reason_codes.append({
            "code": code,
            "severity": severity,
            "message": message,
        })


# ============ Momentum Agent ============

from services.agents.trade_execution_mixin import TradeExecutionMixin


class MomentumAgent(TradeExecutionMixin):
    """
    Momentum agent that produces intent plans.
    
    Does NOT execute trades. Generates hypothetical orders
    for validation before connecting to paper trading engine.
    """
    
    def __init__(
        self,
        agent_id: str,
        db=None,
        viability_service=None,
        risk_budget_service=None,
    ):
        self.agent_id = agent_id
        self.db = db
        self.viability_service = viability_service
        self.risk_budget_service = risk_budget_service
        
        # State
        self._trades_today = 0
        self._last_trade_time: Optional[datetime] = None
        self._last_plan: Optional[MOMIntentPlan] = None
    
    async def generate_intent_plan(
        self,
        symbol: str,
        venue: str,
        preset_config: MOMPresetConfig,
        market_data: Dict[str, Any],
        available_budget_eur: float,
        guardian_check: Optional[Dict[str, Any]] = None,
    ) -> MOMIntentPlan:
        """
        Generate an intent plan for MOM strategy.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            venue: Exchange (e.g., "binance")
            preset_config: MOM preset configuration
            market_data: Current market data with indicators
            available_budget_eur: Available capital in EUR
            guardian_check: Optional guardian validation result
        
        Returns:
            MOMIntentPlan with hypothetical entry
        """
        # Extract market data
        bid = market_data.get("bid", 0)
        ask = market_data.get("ask", 0)
        current_price = (bid + ask) / 2 if bid and ask else market_data.get("last_price", 0)
        spread_pct = ((ask - bid) / current_price * 100) if current_price > 0 else 0
        atr_pct = market_data.get("atr_pct", 1.5)
        adx = market_data.get("adx", 20)
        trend_direction = market_data.get("trend_direction", 0)
        volume_ratio = market_data.get("volume_ratio", 1.0)
        
        # Resistance/Support levels (simplified)
        resistance = market_data.get("resistance", current_price * 1.02)
        support = market_data.get("support", current_price * 0.98)
        
        # Initialize plan
        plan = MOMIntentPlan(
            agent_id=self.agent_id,
            preset_id=preset_config.preset_id,
            symbol=symbol,
            venue=venue,
            current_price=current_price,
            bid=bid,
            ask=ask,
            spread_pct=spread_pct,
            atr_pct=atr_pct,
            adx=adx,
            trend_direction=trend_direction,
            volume_ratio=volume_ratio,
            trades_today=self._trades_today,
        )
        
        # === Pre-checks ===
        
        # Guardian check
        if guardian_check and not guardian_check.get("allowed", True):
            plan.status = IntentStatus.BLOCKED
            plan.add_reason(
                "PAUSE_GUARDIAN",
                severity="error",
                reason=guardian_check.get("block_reason", "unknown")
            )
            return plan
        
        # Budget check
        if available_budget_eur < 5:
            plan.status = IntentStatus.PAUSED
            plan.add_reason("PAUSE_NO_BUDGET", severity="error")
            return plan
        
        # Cooldown check
        if self._last_trade_time:
            cooldown_end = self._last_trade_time.replace(
                second=0, microsecond=0
            )
            from datetime import timedelta
            cooldown_end += timedelta(minutes=preset_config.cooldown_minutes)
            
            if datetime.now(timezone.utc) < cooldown_end:
                plan.status = IntentStatus.COOLDOWN
                plan.cooldown_until = cooldown_end
                remaining = (cooldown_end - datetime.now(timezone.utc)).total_seconds() / 60
                plan.add_reason(
                    "PAUSE_COOLDOWN",
                    severity="info",
                    minutes=remaining
                )
                return plan
        
        # Max trades check
        if self._trades_today >= preset_config.max_trades_per_day:
            plan.status = IntentStatus.PAUSED
            plan.add_reason(
                "PAUSE_MAX_TRADES",
                severity="warn",
                count=self._trades_today,
                max=preset_config.max_trades_per_day
            )
            return plan
        
        # === Market Condition Checks ===
        
        # ADX/Trend check
        if adx < preset_config.adx_threshold:
            plan.status = IntentStatus.NO_OPPORTUNITY
            plan.add_reason(
                "PAUSE_NO_TREND",
                severity="info",
                adx=adx,
                threshold=preset_config.adx_threshold
            )
            return plan
        
        # ATR/Volatility check
        if atr_pct < preset_config.atr_min_pct:
            plan.status = IntentStatus.NO_OPPORTUNITY
            plan.add_reason(
                "PAUSE_LOW_VOLATILITY",
                severity="info",
                atr_pct=atr_pct
            )
            return plan
        
        # Spread check
        max_spread = 0.10  # 0.10%
        if spread_pct > max_spread:
            plan.status = IntentStatus.PAUSED
            plan.add_reason(
                "PAUSE_SPREAD_WIDE",
                severity="warn",
                spread_pct=spread_pct
            )
            return plan
        
        # === Signal Detection ===
        
        signal = SignalType.NO_SIGNAL
        signal_strength = 0.0
        direction = trend_direction
        
        # Breakout detection (simplified)
        if current_price > resistance and trend_direction > 0:
            signal = SignalType.BREAKOUT_UP
            signal_strength = min(100, adx + volume_ratio * 10)
            plan.add_reason(
                "SIGNAL_BREAKOUT_UP",
                severity="info",
                resistance=resistance
            )
        elif current_price < support and trend_direction < 0:
            signal = SignalType.BREAKOUT_DOWN
            signal_strength = min(100, adx + volume_ratio * 10)
            plan.add_reason(
                "SIGNAL_BREAKOUT_DOWN",
                severity="info",
                support=support
            )
        elif adx >= 35 and trend_direction != 0:
            signal = SignalType.MOMENTUM_CONTINUATION
            signal_strength = adx
            plan.add_reason(
                "SIGNAL_MOMENTUM_STRONG",
                severity="info",
                adx=adx,
                direction="UP" if trend_direction > 0 else "DOWN"
            )
        
        plan.signal = signal
        plan.signal_strength = signal_strength
        
        if signal == SignalType.NO_SIGNAL:
            plan.status = IntentStatus.NO_OPPORTUNITY
            plan.add_reason("SIGNAL_NONE", severity="info")
            return plan
        
        # Volume confirmation
        if volume_ratio >= 1.5:
            plan.add_reason(
                "SIGNAL_VOLUME_CONFIRMED",
                severity="info",
                volume_ratio=volume_ratio
            )
        
        # === Generate Entry ===
        
        # Determine side
        if signal in [SignalType.BREAKOUT_UP, SignalType.MOMENTUM_CONTINUATION] and direction > 0:
            side = OrderSide.BUY
            entry_price = ask  # Enter at ask for immediate fill
            stop_loss_price = entry_price * (1 - preset_config.stop_loss_pct / 100)
            take_profit_price = entry_price * (1 + preset_config.take_profit_pct / 100)
        elif signal == SignalType.BREAKOUT_DOWN or direction < 0:
            side = OrderSide.SELL
            entry_price = bid  # Enter at bid for immediate fill
            stop_loss_price = entry_price * (1 + preset_config.stop_loss_pct / 100)
            take_profit_price = entry_price * (1 - preset_config.take_profit_pct / 100)
        else:
            plan.status = IntentStatus.NO_OPPORTUNITY
            plan.add_reason("PAUSE_CHOP_MARKET", severity="info")
            return plan
        
        plan.add_reason(
            "ENTRY_PRICE_SET",
            severity="info",
            entry_price=entry_price,
            distance_pct=0.0
        )
        
        plan.add_reason(
            "STOP_LOSS_SET",
            severity="info",
            stop_price=stop_loss_price,
            sl_pct=preset_config.stop_loss_pct
        )
        
        plan.add_reason(
            "TAKE_PROFIT_SET",
            severity="info",
            tp_price=take_profit_price,
            tp_pct=preset_config.take_profit_pct
        )
        
        if preset_config.trailing_enabled:
            plan.add_reason(
                "TRAILING_ENABLED",
                severity="info",
                trail_pct=preset_config.trailing_pct
            )
        
        # Position sizing based on risk
        risk_per_share = abs(entry_price - stop_loss_price)
        max_risk_eur = available_budget_eur * 0.02  # 2% max risk
        
        if risk_per_share > 0:
            position_size_base = max_risk_eur / risk_per_share
            position_size_eur = position_size_base * entry_price
        else:
            position_size_eur = preset_config.max_position_eur
            position_size_base = position_size_eur / entry_price
        
        # Cap position size
        if position_size_eur > preset_config.max_position_eur:
            position_size_eur = preset_config.max_position_eur
            position_size_base = position_size_eur / entry_price
            plan.add_reason(
                "POSITION_CAPPED",
                severity="info",
                max_eur=preset_config.max_position_eur
            )
        
        plan.add_reason(
            "POSITION_SIZED",
            severity="info",
            size_eur=position_size_eur,
            risk_pct=(position_size_eur / available_budget_eur * 100) if available_budget_eur > 0 else 0
        )
        
        # Calculate R/R ratio
        reward = abs(take_profit_price - entry_price)
        risk = abs(entry_price - stop_loss_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        plan.add_reason(
            "R_R_RATIO",
            severity="info",
            rr_ratio=rr_ratio
        )
        
        # Create entry
        entry = IntendedEntry(
            signal_type=signal,
            side=side,
            entry_price=round(entry_price, 8),
            entry_size_base=round(position_size_base, 8),
            entry_size_eur=round(position_size_eur, 2),
            stop_loss_price=round(stop_loss_price, 8),
            stop_loss_pct=preset_config.stop_loss_pct,
            take_profit_price=round(take_profit_price, 8),
            take_profit_pct=preset_config.take_profit_pct,
            trailing_enabled=preset_config.trailing_enabled,
            trailing_pct=preset_config.trailing_pct if preset_config.trailing_enabled else 0,
            risk_reward_ratio=round(rr_ratio, 2),
            max_risk_eur=round(max_risk_eur, 2),
            expected_win_rate=0.45 if "CONSERVATIVE" in preset_config.preset_id else 0.40,
            rationale=f"{signal.value} entry: {side.value} at {entry_price:.2f}, SL: {stop_loss_price:.2f}, TP: {take_profit_price:.2f}"
        )
        
        plan.entry = entry
        
        # Expected value calculation
        win_rate = entry.expected_win_rate
        avg_win = position_size_eur * (preset_config.take_profit_pct / 100)
        avg_loss = position_size_eur * (preset_config.stop_loss_pct / 100)
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        plan.expected_value_eur = round(expected_value, 4)
        
        # === Finalize ===
        
        plan.status = IntentStatus.READY
        
        self._last_plan = plan
        
        logger.info(
            f"MOM Intent Plan: {symbol}@{venue} - {signal.value} {side.value}, "
            f"size={position_size_eur:.2f}€, status={plan.status.value}"
        )
        
        return plan
    
    def record_trade(self) -> None:
        """Record that a trade was executed (for cooldown/limit tracking)."""
        self._trades_today += 1
        self._last_trade_time = datetime.now(timezone.utc)
    
    def reset_daily_stats(self) -> None:
        """Reset daily trade count (call at start of trading day)."""
        self._trades_today = 0
        logger.info("MOM daily trade count reset")
    
    def get_last_plan(self) -> Optional[MOMIntentPlan]:
        """Get the last generated plan."""
        return self._last_plan
    
    def to_dict(self, plan: MOMIntentPlan) -> Dict[str, Any]:
        """Convert plan to dict for API response."""
        return plan.model_dump(mode='json')
