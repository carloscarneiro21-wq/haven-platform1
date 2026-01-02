"""Grid Trading Agent."""
from datetime import datetime, timezone
from typing import Optional, List, Dict
from motor.motor_asyncio import AsyncIOMotorDatabase
import numpy as np
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentType, OrderSide, OrderType, GridConfig, MarketRegime
)
from services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class GridAgent(BaseAgent):
    """
    Grid Trading Agent - Range Trading Strategy
    
    Features:
    - Arithmetic or geometric grid spacing
    - Auto-adjustment based on volatility
    - Maintains buy orders below current price
    - Maintains sell orders above current price
    - Profit from oscillation in ranging markets
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        super().__init__(db, config)
        self.grid_config: GridConfig = config.grid or GridConfig()
        self._grid_orders: Dict[float, Optional[str]] = {}  # level -> order_id
        self._last_grid_update: Optional[datetime] = None
        
    @property
    def symbol(self) -> str:
        return self.grid_config.symbol
    
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market for grid trading opportunities."""
        if features.symbol != self.symbol:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                symbol=self.symbol,
                action="hold",
                reason="Wrong symbol"
            )
        
        current_price = features.last_price
        
        # Check if grid needs initialization or update
        if not self.grid_config.grid_levels:
            # Initialize grid around current price
            await self._initialize_grid(current_price, features)
            
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                symbol=self.symbol,
                action="buy",  # Will create grid orders
                strength=0.3,
                reason=f"Grid initialized around {current_price:.2f}",
                target_price=current_price
            )
        
        # Check if grid needs adjustment (price moved outside range)
        if self.grid_config.auto_adjust:
            if current_price > self.grid_config.upper_price * 1.05:
                await self._adjust_grid_up(current_price, features)
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.GRID,
                    symbol=self.symbol,
                    action="buy",
                    strength=0.5,
                    reason=f"Grid adjusted up: price {current_price:.2f} above upper bound",
                    target_price=current_price
                )
            elif current_price < self.grid_config.lower_price * 0.95:
                await self._adjust_grid_down(current_price, features)
                return Signal(
                    agent_id=self.agent_id,
                    agent_type=AgentType.GRID,
                    symbol=self.symbol,
                    action="buy",
                    strength=0.5,
                    reason=f"Grid adjusted down: price {current_price:.2f} below lower bound",
                    target_price=current_price
                )
        
        # Check which grid levels need orders
        levels_needing_orders = self._find_levels_needing_orders(current_price)
        
        if levels_needing_orders:
            return Signal(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                symbol=self.symbol,
                action="buy",  # Will create both buy and sell orders
                strength=0.4,
                reason=f"Grid maintenance: {len(levels_needing_orders)} levels need orders",
                target_price=current_price
            )
        
        return Signal(
            agent_id=self.agent_id,
            agent_type=AgentType.GRID,
            symbol=self.symbol,
            action="hold",
            reason="Grid operating normally"
        )
    
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Generate grid orders."""
        orders = []
        current_price = features.last_price
        
        if signal.action == "hold":
            return OrderPlan(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                orders=[],
                reason="No grid action needed"
            )
        
        # Get levels that need orders
        buy_levels = [l for l in self.grid_config.grid_levels if l < current_price and l not in self._grid_orders]
        sell_levels = [l for l in self.grid_config.grid_levels if l > current_price and l not in self._grid_orders]
        
        # Create buy orders below current price
        for level in buy_levels[-3:]:  # Limit to 3 closest levels
            amount = self.grid_config.amount_per_grid / level
            
            order = Order(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                symbol=self.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=level,
                reason=f"Grid buy at level {level:.2f}"
            )
            orders.append(order)
            self._grid_orders[level] = order.id
        
        # Create sell orders above current price
        for level in sell_levels[:3]:  # Limit to 3 closest levels
            amount = self.grid_config.amount_per_grid / level
            
            order = Order(
                agent_id=self.agent_id,
                agent_type=AgentType.GRID,
                symbol=self.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=level,
                reason=f"Grid sell at level {level:.2f}"
            )
            orders.append(order)
            self._grid_orders[level] = order.id
        
        self.grid_config.active_buy_orders = len([o for o in orders if o.side == OrderSide.BUY])
        self.grid_config.active_sell_orders = len([o for o in orders if o.side == OrderSide.SELL])
        
        await self.update_config({
            "active_buy_orders": self.grid_config.active_buy_orders,
            "active_sell_orders": self.grid_config.active_sell_orders,
        })
        
        return OrderPlan(
            agent_id=self.agent_id,
            agent_type=AgentType.GRID,
            orders=orders,
            reason=signal.reason,
            priority=0
        )
    
    async def _initialize_grid(self, current_price: float, features: MarketFeatures):
        """Initialize grid levels around current price."""
        num_grids = self.grid_config.num_grids
        
        # Calculate range based on volatility
        volatility = features.volatility_pct / 100
        range_pct = max(0.05, min(0.20, volatility * self.grid_config.volatility_multiplier))
        
        upper = current_price * (1 + range_pct)
        lower = current_price * (1 - range_pct)
        
        self.grid_config.upper_price = upper
        self.grid_config.lower_price = lower
        
        # Generate grid levels
        if self.grid_config.grid_type == "arithmetic":
            step = (upper - lower) / num_grids
            levels = [lower + step * i for i in range(num_grids + 1)]
        else:  # geometric
            ratio = (upper / lower) ** (1 / num_grids)
            levels = [lower * (ratio ** i) for i in range(num_grids + 1)]
        
        self.grid_config.grid_levels = [round(l, 2) for l in levels]
        
        await self.update_config({
            "upper_price": self.grid_config.upper_price,
            "lower_price": self.grid_config.lower_price,
            "grid_levels": self.grid_config.grid_levels,
        })
        
        logger.info(f"Grid initialized: {lower:.2f} - {upper:.2f}, {num_grids} levels")
    
    async def _adjust_grid_up(self, current_price: float, features: MarketFeatures):
        """Adjust grid upward when price breaks above."""
        old_upper = self.grid_config.upper_price
        new_upper = current_price * 1.05
        new_lower = self.grid_config.upper_price * 0.95
        
        self.grid_config.upper_price = new_upper
        self.grid_config.lower_price = new_lower
        
        # Regenerate levels
        num_grids = self.grid_config.num_grids
        step = (new_upper - new_lower) / num_grids
        self.grid_config.grid_levels = [round(new_lower + step * i, 2) for i in range(num_grids + 1)]
        
        # Clear old order tracking
        self._grid_orders = {}
        
        await self.update_config({
            "upper_price": self.grid_config.upper_price,
            "lower_price": self.grid_config.lower_price,
            "grid_levels": self.grid_config.grid_levels,
        })
        
        logger.info(f"Grid adjusted up: {new_lower:.2f} - {new_upper:.2f}")
    
    async def _adjust_grid_down(self, current_price: float, features: MarketFeatures):
        """Adjust grid downward when price breaks below."""
        new_lower = current_price * 0.95
        new_upper = self.grid_config.lower_price * 1.05
        
        self.grid_config.upper_price = new_upper
        self.grid_config.lower_price = new_lower
        
        # Regenerate levels
        num_grids = self.grid_config.num_grids
        step = (new_upper - new_lower) / num_grids
        self.grid_config.grid_levels = [round(new_lower + step * i, 2) for i in range(num_grids + 1)]
        
        # Clear old order tracking
        self._grid_orders = {}
        
        await self.update_config({
            "upper_price": self.grid_config.upper_price,
            "lower_price": self.grid_config.lower_price,
            "grid_levels": self.grid_config.grid_levels,
        })
        
        logger.info(f"Grid adjusted down: {new_lower:.2f} - {new_upper:.2f}")
    
    def _find_levels_needing_orders(self, current_price: float) -> List[float]:
        """Find grid levels that need new orders."""
        levels_needing_orders = []
        
        for level in self.grid_config.grid_levels:
            if level not in self._grid_orders:
                levels_needing_orders.append(level)
        
        return levels_needing_orders
    
    async def on_order_filled(self, order: Order, value: float):
        """Handle filled order - create opposite order at next level."""
        # Find the level this order was at
        filled_level = order.price
        
        # Remove from tracking
        if filled_level in self._grid_orders:
            del self._grid_orders[filled_level]
        
        logger.info(f"Grid: Order filled at level {filled_level:.2f}")
    
    def get_status(self):
        """Get grid agent status."""
        status = super().get_status()
        status.update({
            "symbol": self.symbol,
            "grid_type": self.grid_config.grid_type,
            "num_grids": self.grid_config.num_grids,
            "upper_price": self.grid_config.upper_price,
            "lower_price": self.grid_config.lower_price,
            "active_buy_orders": self.grid_config.active_buy_orders,
            "active_sell_orders": self.grid_config.active_sell_orders,
            "amount_per_grid": self.grid_config.amount_per_grid,
            "auto_adjust": self.grid_config.auto_adjust,
        })
        return status
