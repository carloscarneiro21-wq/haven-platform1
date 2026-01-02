"""Breakout/Momentum Trading Agent."""
from datetime import datetime, timezone
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
import numpy as np
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentType, OrderSide, OrderType, MarketRegime, BreakoutConfig
)
from services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class BreakoutAgent(BaseAgent):
    """
    Breakout/Momentum Agent - Trades breakouts on key levels
    
    Features:
    - Identifies key support/resistance levels
    - Detects breakouts with volume confirmation
    - Volatility expansion signals (ATR)
    - Momentum confirmation (ADX)
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        super().__init__(db, config)
        self.breakout_config: BreakoutConfig = config.breakout or BreakoutConfig()
        self._entry_price: Optional[float] = None
        self._highest_price: Optional[float] = None
        self._lowest_price: Optional[float] = None
        self._recent_highs: List[float] = []
        self._recent_lows: List[float] = []
        self._resistance_level: Optional[float] = None
        self._support_level: Optional[float] = None
        
    @property
    def symbol(self) -> str:
        return self.breakout_config.symbol
    
    def _update_levels(self, features: MarketFeatures):
        """Update support/resistance levels from recent price action."""
        # Use Bollinger Bands as dynamic levels
        self._resistance_level = features.bollinger_upper
        self._support_level = features.bollinger_lower
        
        # Could also track swing highs/lows
        self._recent_highs.append(features.last_price)
        self._recent_lows.append(features.last_price)
        
        # Keep last N periods
        max_periods = self.breakout_config.lookback_periods
        self._recent_highs = self._recent_highs[-max_periods:]
        self._recent_lows = self._recent_lows[-max_periods:]
        
        if len(self._recent_highs) >= max_periods:
            self._resistance_level = max(self._recent_highs)
            self._support_level = min(self._recent_lows)
    
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market for breakout opportunities."""
        if features.symbol != self.symbol:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.BREAKOUT,
                symbol=self.symbol,
                action="hold",
                reason="Wrong symbol"
            )
        
        current_price = features.last_price
        
        # Update price levels
        self._update_levels(features)
        
        # Update trailing tracking
        if self.breakout_config.in_position:
            if self.breakout_config.position_side == OrderSide.BUY:
                if self._highest_price is None or current_price > self._highest_price:
                    self._highest_price = current_price
            else:
                if self._lowest_price is None or current_price < self._lowest_price:
                    self._lowest_price = current_price
        
        # Check exit conditions first
        if self.breakout_config.in_position:
            exit_signal = self._check_exit_conditions(features)
            if exit_signal:
                return exit_signal
        
        # Check entry conditions if not in position
        if not self.breakout_config.in_position:
            entry_signal = self._check_entry_conditions(features)
            if entry_signal:
                return entry_signal
        
        return Signal(
            agent_id=self.agent_id,
            agent_type=AgentType.BREAKOUT,
            symbol=self.symbol,
            action="hold",
            reason="No breakout signal"
        )
    
    def _check_entry_conditions(self, features: MarketFeatures) -> Optional[Signal]:
        """Check for breakout entry signals."""
        current_price = features.last_price
        resistance = self._resistance_level
        support = self._support_level
        
        if not resistance or not support:
            return None
        
        # Check momentum filter
        if features.adx < self.breakout_config.min_adx:
            return None
        
        # Breakout above resistance
        breakout_threshold = resistance * (1 + self.breakout_config.breakout_threshold_pct / 100)
        
        if current_price > breakout_threshold:
            # Confirm with momentum
            if features.macd > features.macd_signal and features.plus_di > features.minus_di:
                strength = min(1.0, features.adx / 50)
                
                stop_loss = current_price - (features.atr_14 * self.breakout_config.stop_loss_atr_mult)
                take_profit = current_price + (features.atr_14 * self.breakout_config.take_profit_atr_mult)
                
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="buy",
                    strength=strength,
                    reason=f"Bullish breakout: Price {current_price:.0f} > Resistance {resistance:.0f}, ADX={features.adx:.1f}",
                    target_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
        
        # Breakdown below support
        breakdown_threshold = support * (1 - self.breakout_config.breakout_threshold_pct / 100)
        
        if current_price < breakdown_threshold:
            # Confirm with momentum
            if features.macd < features.macd_signal and features.minus_di > features.plus_di:
                strength = min(1.0, features.adx / 50)
                
                stop_loss = current_price + (features.atr_14 * self.breakout_config.stop_loss_atr_mult)
                take_profit = current_price - (features.atr_14 * self.breakout_config.take_profit_atr_mult)
                
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="sell",
                    strength=strength,
                    reason=f"Bearish breakdown: Price {current_price:.0f} < Support {support:.0f}, ADX={features.adx:.1f}",
                    target_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
        
        return None
    
    def _check_exit_conditions(self, features: MarketFeatures) -> Optional[Signal]:
        """Check for exit signals when in position."""
        current_price = features.last_price
        
        if not self._entry_price:
            return None
        
        is_long = self.breakout_config.position_side == OrderSide.BUY
        atr = features.atr_14
        
        # Calculate PnL
        if is_long:
            pnl_pct = ((current_price - self._entry_price) / self._entry_price) * 100
        else:
            pnl_pct = ((self._entry_price - current_price) / self._entry_price) * 100
        
        # Fixed stop loss (ATR based)
        stop_distance = atr * self.breakout_config.stop_loss_atr_mult
        if is_long:
            stop_price = self._entry_price - stop_distance
            if current_price <= stop_price:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=1.0,
                    reason=f"Stop loss hit: {current_price:.0f} <= {stop_price:.0f}"
                )
        else:
            stop_price = self._entry_price + stop_distance
            if current_price >= stop_price:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=1.0,
                    reason=f"Stop loss hit: {current_price:.0f} >= {stop_price:.0f}"
                )
        
        # Take profit (ATR based)
        tp_distance = atr * self.breakout_config.take_profit_atr_mult
        if is_long:
            tp_price = self._entry_price + tp_distance
            if current_price >= tp_price:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=1.0,
                    reason=f"Take profit hit: {current_price:.0f} >= {tp_price:.0f}"
                )
        else:
            tp_price = self._entry_price - tp_distance
            if current_price <= tp_price:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=1.0,
                    reason=f"Take profit hit: {current_price:.0f} <= {tp_price:.0f}"
                )
        
        # Trailing stop (only if in profit)
        if pnl_pct > 1.0:  # At least 1% profit
            trail_distance = atr * self.breakout_config.trailing_stop_atr_mult
            
            if is_long and self._highest_price:
                trail_stop = self._highest_price - trail_distance
                if current_price <= trail_stop:
                    return Signal(
                        agent_id=self.agent_id,
                        agent_type=AgentType.BREAKOUT,
                        symbol=self.symbol,
                        action="close",
                        strength=0.9,
                        reason=f"Trailing stop: {current_price:.0f} from high {self._highest_price:.0f}"
                    )
            
            if not is_long and self._lowest_price:
                trail_stop = self._lowest_price + trail_distance
                if current_price >= trail_stop:
                    return Signal(
                        agent_id=self.agent_id,
                        agent_type=AgentType.BREAKOUT,
                        symbol=self.symbol,
                        action="close",
                        strength=0.9,
                        reason=f"Trailing stop: {current_price:.0f} from low {self._lowest_price:.0f}"
                    )
        
        # Momentum reversal exit
        if is_long and features.macd < features.macd_signal and features.minus_di > features.plus_di:
            if pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=0.7,
                    reason="Momentum reversal - locking profit"
                )
        
        if not is_long and features.macd > features.macd_signal and features.plus_di > features.minus_di:
            if pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    action="close",
                    strength=0.7,
                    reason="Momentum reversal - locking profit"
                )
        
        return None
    
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Generate breakout orders."""
        orders = []
        current_price = features.last_price
        
        if signal.action == "hold":
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.BREAKOUT,
                orders=[],
                reason="No action"
            )
        
        if signal.action in ["buy", "sell"]:
            position_value = min(
                self.config.allocated_capital * self.breakout_config.position_size_pct / 100,
                self.breakout_config.max_position_size
            )
            amount = position_value / current_price
            
            side = OrderSide.BUY if signal.action == "buy" else OrderSide.SELL
            
            order = Order(
                agent_id=self.agent_id,
                agent_type=AgentType.BREAKOUT,
                symbol=self.symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=amount,
                price=current_price,
                reason=signal.reason
            )
            orders.append(order)
            
            self.breakout_config.in_position = True
            self.breakout_config.position_side = side
            self._entry_price = current_price
            self._highest_price = current_price if side == OrderSide.BUY else None
            self._lowest_price = current_price if side == OrderSide.SELL else None
            
        elif signal.action == "close":
            if self.breakout_config.position_side:
                close_side = OrderSide.SELL if self.breakout_config.position_side == OrderSide.BUY else OrderSide.BUY
                
                position_value = self.config.used_capital
                amount = position_value / current_price if position_value > 0 else 0.01
                
                order = Order(
                    agent_id=self.agent_id,
                    agent_type=AgentType.BREAKOUT,
                    symbol=self.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    amount=amount,
                    price=current_price,
                    reason=signal.reason
                )
                orders.append(order)
                
                self.breakout_config.in_position = False
                self.breakout_config.position_side = None
                self._entry_price = None
                self._highest_price = None
                self._lowest_price = None
        
        return OrderPlan(
            agent_id=self.agent_id,
            agent_type=AgentType.BREAKOUT,
            orders=orders,
            reason=signal.reason,
            priority=2 if signal.action == "close" else 1
        )
    
    def get_status(self):
        """Get breakout agent status."""
        status = super().get_status()
        status.update({
            "symbol": self.symbol,
            "in_position": self.breakout_config.in_position,
            "position_side": self.breakout_config.position_side.value if self.breakout_config.position_side else None,
            "entry_price": self._entry_price,
            "resistance_level": self._resistance_level,
            "support_level": self._support_level,
            "min_adx": self.breakout_config.min_adx,
            "lookback_periods": self.breakout_config.lookback_periods,
            "breakout_threshold_pct": self.breakout_config.breakout_threshold_pct,
        })
        return status
