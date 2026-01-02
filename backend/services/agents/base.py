"""Base agent class for trading agents."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    Signal, OrderPlan, Order, MarketFeatures, AgentConfig,
    AgentStatus, AgentType, TradeLog
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all trading agents."""
    
    def __init__(self, db: AsyncIOMotorDatabase, config: AgentConfig):
        self.db = db
        self.config = config
        self.agent_id = config.id
        self.agent_type = config.agent_type
        self._last_signal: Optional[Signal] = None
        
    @property
    def is_active(self) -> bool:
        """Check if agent is running."""
        return self.config.status == AgentStatus.RUNNING
    
    @abstractmethod
    async def analyze(self, features: MarketFeatures) -> Signal:
        """Analyze market and generate trading signal."""
        pass
    
    @abstractmethod
    async def generate_orders(self, signal: Signal, features: MarketFeatures) -> OrderPlan:
        """Convert signal into executable orders."""
        pass
    
    async def run_cycle(self, features: MarketFeatures) -> Optional[OrderPlan]:
        """Run one analysis and order generation cycle."""
        if not self.is_active:
            return None
        
        try:
            # Generate signal
            signal = await self.analyze(features)
            self._last_signal = signal
            
            if signal.action == "hold":
                return None
            
            # Log the signal
            await self._log_signal(signal, features)
            
            # Generate orders
            order_plan = await self.generate_orders(signal, features)
            
            if order_plan.orders:
                return order_plan
            
            return None
            
        except Exception as e:
            logger.error(f"Agent {self.agent_id} error: {e}")
            await self._log_error(str(e))
            return None
    
    async def start(self):
        """Start the agent."""
        self.config.status = AgentStatus.RUNNING
        self.config.updated_at = datetime.now(timezone.utc)
        await self._save_config()
        logger.info(f"Agent {self.agent_id} ({self.agent_type.value}) started")
    
    async def stop(self):
        """Stop the agent."""
        self.config.status = AgentStatus.STOPPED
        self.config.updated_at = datetime.now(timezone.utc)
        await self._save_config()
        logger.info(f"Agent {self.agent_id} ({self.agent_type.value}) stopped")
    
    async def pause(self):
        """Pause the agent."""
        self.config.status = AgentStatus.PAUSED
        self.config.updated_at = datetime.now(timezone.utc)
        await self._save_config()
    
    async def update_config(self, updates: Dict[str, Any]):
        """Update agent configuration."""
        config_field = self.agent_type.value  # 'dca', 'grid', or 'trend'
        sub_config = getattr(self.config, config_field)
        
        if sub_config:
            for key, value in updates.items():
                if hasattr(sub_config, key):
                    setattr(sub_config, key, value)
        
        self.config.updated_at = datetime.now(timezone.utc)
        await self._save_config()
    
    async def update_performance(self, pnl: float, is_win: bool):
        """Update agent performance metrics."""
        self.config.total_trades += 1
        self.config.total_pnl += pnl
        if is_win:
            self.config.winning_trades += 1
        await self._save_config()
    
    async def _save_config(self):
        """Save agent config to database."""
        doc = self.config.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        
        await self.db.agent_configs.update_one(
            {"id": self.config.id},
            {"$set": doc},
            upsert=True
        )
    
    async def _log_signal(self, signal: Signal, features: MarketFeatures):
        """Log trading signal."""
        log = TradeLog(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            symbol=signal.symbol,
            action=signal.action,
            reason=signal.reason,
            market_conditions={
                "price": features.last_price,
                "rsi": features.rsi_14,
                "ema_9": features.ema_9,
                "ema_21": features.ema_21,
                "adx": features.adx,
                "regime": features.regime.value,
            },
            signal_strength=signal.strength
        )
        
        doc = log.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        
        await self.db.trade_logs.insert_one(doc)
    
    async def _log_error(self, error: str):
        """Log agent error."""
        from models.trading import SystemLog
        
        log = SystemLog(
            level="error",
            component=f"agent_{self.agent_type.value}",
            message=error,
            details={"agent_id": self.agent_id}
        )
        
        doc = log.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        
        await self.db.system_logs.insert_one(doc)
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status summary."""
        win_rate = 0
        if self.config.total_trades > 0:
            win_rate = (self.config.winning_trades / self.config.total_trades) * 100
        
        return {
            "id": self.agent_id,
            "type": self.agent_type.value,
            "status": self.config.status.value,
            "allocated_capital": self.config.allocated_capital,
            "used_capital": self.config.used_capital,
            "total_trades": self.config.total_trades,
            "winning_trades": self.config.winning_trades,
            "win_rate": win_rate,
            "total_pnl": self.config.total_pnl,
            "last_signal": self._last_signal.model_dump() if self._last_signal else None,
        }
