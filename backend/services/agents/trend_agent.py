"""Trend Following Trading Agent."""
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentType, OrderSide, OrderType, TrendConfig, MarketRegime
)
from services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class TrendAgent(BaseAgent):
    """
    Trend Following Agent - Momentum Strategy
    
    Features:
    - EMA crossover signals
    - RSI confirmation
    - ADX trend strength filter
    - Trailing stop-loss
    - Take profit targets
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        super().__init__(db, config)
        self.trend_config: TrendConfig = config.trend or TrendConfig()
        self._entry_price: Optional[float] = None
        self._highest_price: Optional[float] = None
        self._lowest_price: Optional[float] = None
        
    @property
    def symbol(self) -> str:
        return self.trend_config.symbol
    
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market for trend following opportunities."""
        if features.symbol != self.symbol:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                action="hold",
                reason="Wrong symbol"
            )
        
        current_price = features.last_price
        
        # Update price tracking for trailing stop
        if self.trend_config.in_position:
            if self.trend_config.position_side == OrderSide.BUY:
                if self._highest_price is None or current_price > self._highest_price:
                    self._highest_price = current_price
            else:
                if self._lowest_price is None or current_price < self._lowest_price:
                    self._lowest_price = current_price
        
        # Check exit conditions first if in position
        if self.trend_config.in_position:
            exit_signal = self._check_exit_conditions(features)
            if exit_signal:
                return exit_signal
        
        # Check entry conditions if not in position
        if not self.trend_config.in_position:
            entry_signal = self._check_entry_conditions(features)
            if entry_signal:
                return entry_signal
        
        return Signal(
            agent_id=self.agent_id,
            agent_type=AgentType.TREND,
            symbol=self.symbol,
            action="hold",
            reason="No trend signal"
        )
    
    def _check_entry_conditions(self, features: MarketFeatures) -> Optional[Signal]:
        """Check for entry signals."""
        current_price = features.last_price
        
        # Require trending market (ADX > threshold)
        if features.adx < self.trend_config.adx_threshold:
            return None
        
        # Check for bullish setup
        bullish_ema = features.ema_9 > features.ema_21
        bullish_macd = features.macd > features.macd_signal
        rsi_ok = features.rsi_14 < self.trend_config.rsi_overbought
        trending_up = features.regime in [MarketRegime.TRENDING_UP]
        
        if bullish_ema and bullish_macd and rsi_ok:
            strength = min(1.0, features.adx / 50)  # Stronger signal with higher ADX
            
            # Calculate stop loss and take profit
            stop_loss = current_price * (1 - self.trend_config.stop_loss_pct / 100)
            take_profit = current_price * (1 + self.trend_config.take_profit_pct / 100)
            
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                action="buy",
                strength=strength,
                reason=f"Bullish trend: EMA9>{features.ema_9:.0f} > EMA21>{features.ema_21:.0f}, ADX={features.adx:.1f}, RSI={features.rsi_14:.1f}",
                target_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        
        # Check for bearish setup
        bearish_ema = features.ema_9 < features.ema_21
        bearish_macd = features.macd < features.macd_signal
        rsi_ok_short = features.rsi_14 > self.trend_config.rsi_oversold
        trending_down = features.regime in [MarketRegime.TRENDING_DOWN]
        
        if bearish_ema and bearish_macd and rsi_ok_short:
            strength = min(1.0, features.adx / 50)
            
            stop_loss = current_price * (1 + self.trend_config.stop_loss_pct / 100)
            take_profit = current_price * (1 - self.trend_config.take_profit_pct / 100)
            
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                action="sell",
                strength=strength,
                reason=f"Bearish trend: EMA9>{features.ema_9:.0f} < EMA21>{features.ema_21:.0f}, ADX={features.adx:.1f}, RSI={features.rsi_14:.1f}",
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
        
        is_long = self.trend_config.position_side == OrderSide.BUY
        
        # Calculate current PnL percentage
        if is_long:
            pnl_pct = ((current_price - self._entry_price) / self._entry_price) * 100
        else:
            pnl_pct = ((self._entry_price - current_price) / self._entry_price) * 100
        
        # Check stop loss
        if pnl_pct <= -self.trend_config.stop_loss_pct:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                action="close",
                strength=1.0,
                reason=f"Stop loss triggered: {pnl_pct:.2f}% loss"
            )
        
        # Check take profit
        if pnl_pct >= self.trend_config.take_profit_pct:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                action="close",
                strength=1.0,
                reason=f"Take profit triggered: {pnl_pct:.2f}% gain"
            )
        
        # Check trailing stop
        if is_long and self._highest_price:
            drawdown = ((self._highest_price - current_price) / self._highest_price) * 100
            if drawdown >= self.trend_config.trailing_stop_pct and pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.TREND,
                    symbol=self.symbol,
                    action="close",
                    strength=0.9,
                    reason=f"Trailing stop: {drawdown:.2f}% drawdown from high ({self._highest_price:.2f})"
                )
        
        elif not is_long and self._lowest_price:
            runup = ((current_price - self._lowest_price) / self._lowest_price) * 100
            if runup >= self.trend_config.trailing_stop_pct and pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.TREND,
                    symbol=self.symbol,
                    action="close",
                    strength=0.9,
                    reason=f"Trailing stop: {runup:.2f}% runup from low ({self._lowest_price:.2f})"
                )
        
        # Check for trend reversal
        if is_long:
            if features.ema_9 < features.ema_21 and features.macd < features.macd_signal:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.TREND,
                    symbol=self.symbol,
                    action="close",
                    strength=0.7,
                    reason=f"Trend reversal: EMA and MACD turned bearish"
                )
        else:
            if features.ema_9 > features.ema_21 and features.macd > features.macd_signal:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.TREND,
                    symbol=self.symbol,
                    action="close",
                    strength=0.7,
                    reason=f"Trend reversal: EMA and MACD turned bullish"
                )
        
        return None
    
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Generate trend following orders."""
        orders = []
        current_price = features.last_price
        
        if signal.action == "hold":
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                orders=[],
                reason="No trend action"
            )
        
        if signal.action in ["buy", "sell"]:
            # Calculate position size
            position_value = min(
                self.config.allocated_capital * self.trend_config.position_size_pct / 100,
                self.trend_config.max_position_size
            )
            amount = position_value / current_price
            
            side = OrderSide.BUY if signal.action == "buy" else OrderSide.SELL
            
            # Entry order
            entry_order = Order(
                agent_id=self.agent_id,
                agent_type=AgentType.TREND,
                symbol=self.symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=amount,
                price=current_price,
                reason=signal.reason
            )
            orders.append(entry_order)
            
            # Update state
            self.trend_config.in_position = True
            self.trend_config.position_side = side
            self._entry_price = current_price
            self._highest_price = current_price if side == OrderSide.BUY else None
            self._lowest_price = current_price if side == OrderSide.SELL else None
            
            await self.update_config({
                "in_position": True,
                "position_side": side.value,
            })
        
        elif signal.action == "close":
            # Close position
            if self.trend_config.position_side:
                close_side = OrderSide.SELL if self.trend_config.position_side == OrderSide.BUY else OrderSide.BUY
                
                # Get current position size (simplified - should query actual position)
                position_value = self.config.used_capital
                amount = position_value / current_price if position_value > 0 else 0.01
                
                close_order = Order(
                    agent_id=self.agent_id,
                    agent_type=AgentType.TREND,
                    symbol=self.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    amount=amount,
                    price=current_price,
                    reason=signal.reason
                )
                orders.append(close_order)
                
                # Reset state
                self.trend_config.in_position = False
                self.trend_config.position_side = None
                self._entry_price = None
                self._highest_price = None
                self._lowest_price = None
                
                await self.update_config({
                    "in_position": False,
                    "position_side": None,
                })
        
        return OrderPlan(
            agent_id=self.agent_id,
            agent_type=AgentType.TREND,
            orders=orders,
            reason=signal.reason,
            priority=2 if signal.action == "close" else 1  # Exits have higher priority
        )
    
    def get_status(self):
        """Get trend agent status."""
        status = super().get_status()
        # Handle position_side which could be a string or enum
        position_side = self.trend_config.position_side
        if position_side:
            position_side_str = position_side.value if hasattr(position_side, 'value') else str(position_side)
        else:
            position_side_str = None
        
        status.update({
            "symbol": self.symbol,
            "in_position": self.trend_config.in_position,
            "position_side": position_side_str,
            "entry_price": self._entry_price,
            "highest_price": self._highest_price,
            "lowest_price": self._lowest_price,
            "stop_loss_pct": self.trend_config.stop_loss_pct,
            "take_profit_pct": self.trend_config.take_profit_pct,
            "trailing_stop_pct": self.trend_config.trailing_stop_pct,
            "position_size_pct": self.trend_config.position_size_pct,
        })
        return status
