"""Mean Reversion Trading Agent."""
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentType, OrderSide, OrderType, MarketRegime, MeanReversionConfig
)
from services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class MeanReversionAgent(BaseAgent):
    """
    Mean Reversion Agent - Range Trading Strategy
    
    Features:
    - Trades oversold/overbought conditions
    - Uses RSI, Bollinger Bands for entry signals
    - Filters for ranging markets (low ADX)
    - Mean reversion to moving average
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        super().__init__(db, config)
        self.mr_config: MeanReversionConfig = config.mean_reversion or MeanReversionConfig()
        self._entry_price: Optional[float] = None
        
    @property
    def symbol(self) -> str:
        return self.mr_config.symbol
    
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market for mean reversion opportunities."""
        if features.symbol != self.symbol:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="hold",
                reason="Wrong symbol"
            )
        
        # Check exit conditions first if in position
        if self.mr_config.in_position:
            exit_signal = self._check_exit_conditions(features)
            if exit_signal:
                return exit_signal
        
        # Check regime filter - only trade in ranging markets
        if self.mr_config.require_ranging:
            if features.adx > self.mr_config.max_adx:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.MEAN_REVERSION,
                    symbol=self.symbol,
                    action="hold",
                    reason=f"Market trending (ADX={features.adx:.1f} > {self.mr_config.max_adx})"
                )
            if features.regime not in [MarketRegime.RANGING, MarketRegime.LOW_VOLATILITY]:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.MEAN_REVERSION,
                    symbol=self.symbol,
                    action="hold",
                    reason=f"Not in ranging market: {features.regime.value}"
                )
        
        # Check entry conditions if not in position
        if not self.mr_config.in_position:
            entry_signal = self._check_entry_conditions(features)
            if entry_signal:
                return entry_signal
        
        return Signal(
            agent_id=self.agent_id,
            agent_type=AgentType.MEAN_REVERSION,
            symbol=self.symbol,
            action="hold",
            reason="No mean reversion opportunity"
        )
    
    def _check_entry_conditions(self, features: MarketFeatures) -> Optional[Signal]:
        """Check for mean reversion entry signals."""
        current_price = features.last_price
        
        # Buy signal: Price at lower Bollinger Band + RSI oversold
        at_lower_bb = current_price <= features.bollinger_lower
        rsi_oversold = features.rsi_14 <= self.mr_config.rsi_oversold
        
        if at_lower_bb and rsi_oversold:
            strength = (self.mr_config.rsi_oversold - features.rsi_14) / self.mr_config.rsi_oversold
            
            stop_loss = current_price * (1 - self.mr_config.stop_loss_pct / 100)
            take_profit = features.bollinger_middle  # Target middle band
            
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="buy",
                strength=min(1.0, strength),
                reason=f"Oversold bounce: RSI={features.rsi_14:.1f}, Price at lower BB ({features.bollinger_lower:.0f})",
                target_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        
        # Sell signal: Price at upper Bollinger Band + RSI overbought
        at_upper_bb = current_price >= features.bollinger_upper
        rsi_overbought = features.rsi_14 >= self.mr_config.rsi_overbought
        
        if at_upper_bb and rsi_overbought:
            strength = (features.rsi_14 - self.mr_config.rsi_overbought) / (100 - self.mr_config.rsi_overbought)
            
            stop_loss = current_price * (1 + self.mr_config.stop_loss_pct / 100)
            take_profit = features.bollinger_middle  # Target middle band
            
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="sell",
                strength=min(1.0, strength),
                reason=f"Overbought reversal: RSI={features.rsi_14:.1f}, Price at upper BB ({features.bollinger_upper:.0f})",
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
        
        is_long = self.mr_config.position_side == OrderSide.BUY
        
        # Calculate PnL
        if is_long:
            pnl_pct = ((current_price - self._entry_price) / self._entry_price) * 100
        else:
            pnl_pct = ((self._entry_price - current_price) / self._entry_price) * 100
        
        # Check stop loss
        if pnl_pct <= -self.mr_config.stop_loss_pct:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="close",
                strength=1.0,
                reason=f"Stop loss: {pnl_pct:.2f}%"
            )
        
        # Check take profit (mean reversion target = middle BB)
        if is_long and current_price >= features.bollinger_middle:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="close",
                strength=1.0,
                reason=f"Mean reversion target: price at middle BB ({features.bollinger_middle:.0f})"
            )
        
        if not is_long and current_price <= features.bollinger_middle:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                action="close",
                strength=1.0,
                reason=f"Mean reversion target: price at middle BB ({features.bollinger_middle:.0f})"
            )
        
        # Check RSI reversal (back to neutral)
        if is_long and features.rsi_14 > 50:
            if pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.MEAN_REVERSION,
                    symbol=self.symbol,
                    action="close",
                    strength=0.8,
                    reason=f"RSI normalized: {features.rsi_14:.1f}, locking profit"
                )
        
        if not is_long and features.rsi_14 < 50:
            if pnl_pct > 0:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.MEAN_REVERSION,
                    symbol=self.symbol,
                    action="close",
                    strength=0.8,
                    reason=f"RSI normalized: {features.rsi_14:.1f}, locking profit"
                )
        
        return None
    
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Generate mean reversion orders."""
        orders = []
        current_price = features.last_price
        
        if signal.action == "hold":
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                orders=[],
                reason="No action"
            )
        
        if signal.action in ["buy", "sell"]:
            position_value = min(
                self.config.allocated_capital * self.mr_config.position_size_pct / 100,
                self.mr_config.max_position_size
            )
            amount = position_value / current_price
            
            side = OrderSide.BUY if signal.action == "buy" else OrderSide.SELL
            
            order = Order(
                agent_id=self.agent_id,
                agent_type=AgentType.MEAN_REVERSION,
                symbol=self.symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=amount,
                price=current_price,
                reason=signal.reason
            )
            orders.append(order)
            
            self.mr_config.in_position = True
            self.mr_config.position_side = side
            self._entry_price = current_price
            
        elif signal.action == "close":
            if self.mr_config.position_side:
                close_side = OrderSide.SELL if self.mr_config.position_side == OrderSide.BUY else OrderSide.BUY
                
                position_value = self.config.used_capital
                amount = position_value / current_price if position_value > 0 else 0.01
                
                order = Order(
                    agent_id=self.agent_id,
                    agent_type=AgentType.MEAN_REVERSION,
                    symbol=self.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    amount=amount,
                    price=current_price,
                    reason=signal.reason
                )
                orders.append(order)
                
                self.mr_config.in_position = False
                self.mr_config.position_side = None
                self._entry_price = None
        
        return OrderPlan(
            agent_id=self.agent_id,
            agent_type=AgentType.MEAN_REVERSION,
            orders=orders,
            reason=signal.reason,
            priority=2 if signal.action == "close" else 1
        )
    
    def get_status(self):
        """Get mean reversion agent status."""
        status = super().get_status()
        status.update({
            "symbol": self.symbol,
            "in_position": self.mr_config.in_position,
            "position_side": self.mr_config.position_side.value if self.mr_config.position_side else None,
            "entry_price": self._entry_price,
            "rsi_oversold": self.mr_config.rsi_oversold,
            "rsi_overbought": self.mr_config.rsi_overbought,
            "max_adx": self.mr_config.max_adx,
        })
        return status
