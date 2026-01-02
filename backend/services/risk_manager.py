"""Global Risk Manager with pre/post trade checks and circuit breakers."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    RiskSettings, RiskCheckResult, Order, Position, Trade,
    OrderSide, AgentType, SystemLog
)

logger = logging.getLogger(__name__)


class RiskManager:
    """Global risk manager controlling all trading agents."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.settings: RiskSettings = RiskSettings()
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Load risk settings from database."""
        doc = await self.db.risk_settings.find_one({}, {"_id": 0})
        if doc:
            self.settings = RiskSettings(**doc)
        else:
            # Save default settings
            await self.save_settings()
        
        # Reset daily PnL if new day
        await self._check_daily_reset()
        
        logger.info("RiskManager initialized")
        
    async def save_settings(self):
        """Persist risk settings to database."""
        self.settings.last_updated = datetime.now(timezone.utc)
        await self.db.risk_settings.replace_one(
            {},
            self.settings.model_dump(),
            upsert=True
        )
        
    async def _check_daily_reset(self):
        """Reset daily metrics at start of new day."""
        now = datetime.now(timezone.utc)
        last_update = self.settings.last_updated
        
        if last_update.date() < now.date():
            self.settings.current_daily_pnl = 0.0
            self.settings.consecutive_losses = 0
            await self.save_settings()
            logger.info("Daily risk metrics reset")
            
    async def pre_trade_check(self, order: Order, current_exposure: float = 0.0) -> RiskCheckResult:
        """Pre-trade risk check before order execution."""
        async with self._lock:
            warnings = []
            
            # Check kill switch
            if self.settings.kill_switch_active:
                return RiskCheckResult(
                    allowed=False,
                    reason="Kill switch is active - all trading halted"
                )
            
            # Check cooldown
            if self.settings.cooldown_until:
                if datetime.now(timezone.utc) < self.settings.cooldown_until:
                    return RiskCheckResult(
                        allowed=False,
                        reason=f"Cooldown active until {self.settings.cooldown_until.isoformat()}"
                    )
                else:
                    self.settings.cooldown_until = None
                    
            # Check daily loss limit
            daily_loss_limit = min(
                self.settings.max_daily_loss,
                self.settings.peak_equity * self.settings.max_daily_loss_pct / 100
            )
            
            if self.settings.current_daily_pnl < -daily_loss_limit:
                await self._activate_cooldown(hours=4)
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Daily loss limit exceeded: ${abs(self.settings.current_daily_pnl):.2f}"
                )
            
            # Check drawdown limit
            if self.settings.current_drawdown_pct >= self.settings.max_drawdown_pct:
                await self._activate_cooldown(hours=24)
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Max drawdown exceeded: {self.settings.current_drawdown_pct:.2f}%"
                )
            
            # Check consecutive losses
            if self.settings.consecutive_losses >= self.settings.max_consecutive_losses:
                await self._activate_cooldown(hours=2)
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Max consecutive losses reached: {self.settings.consecutive_losses}"
                )
            
            # Check position size limit
            order_value = order.amount * (order.price or 0)
            if order_value > self.settings.max_position_size:
                # Adjust amount instead of rejecting
                adjusted_amount = self.settings.max_position_size / (order.price or 1)
                warnings.append(f"Order size reduced from {order.amount} to {adjusted_amount:.6f}")
                
                return RiskCheckResult(
                    allowed=True,
                    adjusted_amount=adjusted_amount,
                    warnings=warnings
                )
            
            # Check total exposure limit
            new_exposure = current_exposure + order_value
            if new_exposure > self.settings.max_total_exposure:
                remaining_capacity = self.settings.max_total_exposure - current_exposure
                if remaining_capacity <= 0:
                    return RiskCheckResult(
                        allowed=False,
                        reason="Max total exposure reached"
                    )
                
                adjusted_amount = remaining_capacity / (order.price or 1)
                warnings.append(f"Order size adjusted to fit exposure limit: {adjusted_amount:.6f}")
                
                return RiskCheckResult(
                    allowed=True,
                    adjusted_amount=adjusted_amount,
                    warnings=warnings
                )
            
            return RiskCheckResult(allowed=True, warnings=warnings)
    
    async def post_trade_update(self, trade: Trade):
        """Update risk metrics after trade execution."""
        async with self._lock:
            # Update daily PnL
            self.settings.current_daily_pnl += trade.pnl
            
            # Update consecutive losses
            if trade.pnl < 0:
                self.settings.consecutive_losses += 1
            else:
                self.settings.consecutive_losses = 0
            
            # Update total exposure
            if trade.side == OrderSide.BUY:
                self.settings.current_total_exposure += trade.value
            else:
                self.settings.current_total_exposure -= trade.value
            
            self.settings.current_total_exposure = max(0, self.settings.current_total_exposure)
            
            await self.save_settings()
            
            # Log critical events
            if self.settings.consecutive_losses >= 3:
                await self._log_warning(
                    f"Consecutive losses: {self.settings.consecutive_losses}",
                    {"trade_id": trade.id}
                )
    
    async def update_equity(self, total_equity: float, unrealized_pnl: float):
        """Update equity and drawdown tracking."""
        async with self._lock:
            # Update peak equity
            if total_equity > self.settings.peak_equity:
                self.settings.peak_equity = total_equity
            
            # Calculate drawdown
            if self.settings.peak_equity > 0:
                self.settings.current_drawdown_pct = (
                    (self.settings.peak_equity - total_equity) / self.settings.peak_equity
                ) * 100
            
            await self.save_settings()
    
    async def activate_kill_switch(self, reason: str = "Manual activation"):
        """Activate emergency kill switch to halt all trading."""
        async with self._lock:
            self.settings.kill_switch_active = True
            await self.save_settings()
            
            await self._log_critical(f"Kill switch activated: {reason}")
            
            logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
    
    async def deactivate_kill_switch(self):
        """Deactivate kill switch."""
        async with self._lock:
            self.settings.kill_switch_active = False
            await self.save_settings()
            
            await self._log_info("Kill switch deactivated")
            
            logger.info("Kill switch deactivated")
    
    async def _activate_cooldown(self, hours: int):
        """Activate trading cooldown."""
        self.settings.cooldown_until = datetime.now(timezone.utc) + timedelta(hours=hours)
        await self.save_settings()
        
        await self._log_warning(f"Cooldown activated for {hours} hours")
        
        logger.warning(f"Trading cooldown activated for {hours} hours")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current risk status."""
        return {
            "kill_switch_active": self.settings.kill_switch_active,
            "cooldown_until": self.settings.cooldown_until.isoformat() if self.settings.cooldown_until else None,
            "current_daily_pnl": self.settings.current_daily_pnl,
            "max_daily_loss": self.settings.max_daily_loss,
            "current_drawdown_pct": self.settings.current_drawdown_pct,
            "max_drawdown_pct": self.settings.max_drawdown_pct,
            "consecutive_losses": self.settings.consecutive_losses,
            "current_total_exposure": self.settings.current_total_exposure,
            "max_total_exposure": self.settings.max_total_exposure,
            "trading_allowed": not self.settings.kill_switch_active and (
                self.settings.cooldown_until is None or 
                (self.settings.cooldown_until.tzinfo is not None and datetime.now(timezone.utc) >= self.settings.cooldown_until) or
                (self.settings.cooldown_until.tzinfo is None and datetime.now(timezone.utc) >= self.settings.cooldown_until.replace(tzinfo=timezone.utc))
            )
        }
    
    async def update_settings(self, updates: Dict[str, Any]):
        """Update risk settings."""
        async with self._lock:
            for key, value in updates.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)
            await self.save_settings()
    
    async def _log_info(self, message: str, details: Dict = None):
        """Log info event."""
        log = SystemLog(
            level="info",
            component="risk_manager",
            message=message,
            details=details or {}
        )
        await self.db.system_logs.insert_one(log.model_dump())
    
    async def _log_warning(self, message: str, details: Dict = None):
        """Log warning event."""
        log = SystemLog(
            level="warning",
            component="risk_manager",
            message=message,
            details=details or {}
        )
        await self.db.system_logs.insert_one(log.model_dump())
    
    async def _log_critical(self, message: str, details: Dict = None):
        """Log critical event."""
        log = SystemLog(
            level="critical",
            component="risk_manager",
            message=message,
            details=details or {}
        )
        await self.db.system_logs.insert_one(log.model_dump())
