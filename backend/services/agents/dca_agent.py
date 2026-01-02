"""DCA (Dollar Cost Averaging) Trading Agent."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentType, OrderSide, OrderType, DCAConfig
)
from services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DCAAgent(BaseAgent):
    """
    DCA Agent - Dollar Cost Averaging Strategy
    
    Features:
    - Time-based periodic buying
    - Price dip triggers for additional buys
    - Size scaling based on dip magnitude
    - Max exposure limits
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        super().__init__(db, config)
        self.dca_config: DCAConfig = config.dca or DCAConfig()
        self._last_dip_buy: Optional[datetime] = None
        self._reference_price: Optional[float] = None
        
    @property
    def symbol(self) -> str:
        return self.dca_config.symbol
    
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market for DCA opportunities."""
        if features.symbol != self.symbol:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.DCA,
                symbol=self.symbol,
                action="hold",
                reason="Wrong symbol"
            )
        
        now = datetime.now(timezone.utc)
        current_price = features.last_price
        
        # Update reference price (highest seen price for dip calculation)
        if self._reference_price is None or current_price > self._reference_price:
            self._reference_price = current_price
        
        # Check exposure limit
        if self.dca_config.current_exposure >= self.dca_config.max_exposure:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.DCA,
                symbol=self.symbol,
                action="hold",
                reason=f"Max exposure reached: ${self.dca_config.current_exposure:.2f}"
            )
        
        # Check for time-based DCA
        if self.dca_config.next_execution:
            if now >= self.dca_config.next_execution:
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.DCA,
                    symbol=self.symbol,
                    action="buy",
                    strength=0.5,
                    reason=f"Scheduled DCA buy at {current_price:.2f}",
                    target_price=current_price
                )
        else:
            # First run - schedule next execution
            self.dca_config.next_execution = now + timedelta(hours=self.dca_config.interval_hours)
            await self.update_config({"next_execution": self.dca_config.next_execution})
        
        # Check for dip-triggered buy
        if self._reference_price and self._reference_price > 0:
            dip_pct = ((self._reference_price - current_price) / self._reference_price) * 100
            
            if dip_pct >= self.dca_config.dip_threshold_pct:
                # Check cooldown
                if self._last_dip_buy:
                    cooldown_end = self._last_dip_buy + timedelta(hours=self.dca_config.dip_cooldown_hours)
                    if now < cooldown_end:
                        return Signal(
                            agent_id=self.agent_id,
                            agent_type=AgentType.DCA,
                            symbol=self.symbol,
                            action="hold",
                            reason=f"Dip buy cooldown until {cooldown_end.isoformat()}"
                        )
                
                # Calculate signal strength based on dip magnitude
                strength = min(1.0, dip_pct / 10.0)  # Max strength at 10% dip
                
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.DCA,
                    symbol=self.symbol,
                    action="buy",
                    strength=strength,
                    reason=f"Dip buy triggered: {dip_pct:.1f}% below reference ({self._reference_price:.2f})",
                    target_price=current_price
                )
        
        return Signal(
            agent_id=self.agent_id,
            agent_type=AgentType.DCA,
            symbol=self.symbol,
            action="hold",
            reason="No DCA trigger"
        )
    
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Generate DCA buy order."""
        orders = []
        
        if signal.action != "buy":
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.DCA,
                orders=[],
                reason="No buy signal"
            )
        
        current_price = features.last_price
        
        # Calculate buy amount based on signal strength
        base_amount = self.dca_config.base_amount
        if signal.strength > 0.5:
            # Scale up for stronger dip signals
            scale = 1 + (signal.strength - 0.5) * (self.dca_config.scaling_factor - 1)
            buy_value = min(base_amount * scale, self.dca_config.max_amount)
        else:
            buy_value = base_amount
        
        # Check remaining exposure capacity
        remaining_capacity = self.dca_config.max_exposure - self.dca_config.current_exposure
        buy_value = min(buy_value, remaining_capacity)
        
        if buy_value < 10:  # Minimum order value
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.DCA,
                orders=[],
                reason="Order value too small"
            )
        
        # Calculate amount in base currency
        amount = buy_value / current_price
        
        order = Order(
            agent_id=self.agent_id,
            agent_type=AgentType.DCA,
            symbol=self.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=amount,
            price=current_price,
            reason=signal.reason
        )
        
        orders.append(order)
        
        # Update next scheduled execution
        now = datetime.now(timezone.utc)
        
        if "Scheduled DCA" in signal.reason:
            self.dca_config.next_execution = now + timedelta(hours=self.dca_config.interval_hours)
            await self.update_config({"next_execution": self.dca_config.next_execution})
        
        if "Dip buy" in signal.reason:
            self._last_dip_buy = now
            # Reset reference price after dip buy
            self._reference_price = current_price
        
        return OrderPlan(
            agent_id=self.agent_id,
            agent_type=AgentType.DCA,
            orders=orders,
            reason=signal.reason,
            priority=1 if "Dip" in signal.reason else 0
        )
    
    async def on_order_filled(self, order: Order, value: float):
        """Handle filled order - update exposure tracking."""
        self.dca_config.current_exposure += value
        await self.update_config({"current_exposure": self.dca_config.current_exposure})
        
        logger.info(f"DCA: Filled ${value:.2f}, total exposure: ${self.dca_config.current_exposure:.2f}")
    
    def get_status(self):
        """Get DCA agent status."""
        status = super().get_status()
        status.update({
            "symbol": self.symbol,
            "current_exposure": self.dca_config.current_exposure,
            "max_exposure": self.dca_config.max_exposure,
            "exposure_pct": (self.dca_config.current_exposure / self.dca_config.max_exposure) * 100,
            "next_execution": self.dca_config.next_execution.isoformat() if self.dca_config.next_execution else None,
            "interval_hours": self.dca_config.interval_hours,
            "base_amount": self.dca_config.base_amount,
            "dip_threshold_pct": self.dca_config.dip_threshold_pct,
        })
        return status
