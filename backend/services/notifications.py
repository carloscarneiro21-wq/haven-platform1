"""Telegram notification service for critical alerts."""
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class NotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    TRADE = "trade"


class NotificationConfig(BaseModel):
    enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    # Notification preferences
    notify_on_trade: bool = True
    notify_on_stop_loss: bool = True
    notify_on_take_profit: bool = True
    notify_on_kill_switch: bool = True
    notify_on_agent_error: bool = True
    notify_on_risk_warning: bool = True
    notify_on_daily_summary: bool = True
    
    # Rate limiting
    min_interval_seconds: int = 10  # Minimum time between notifications
    max_per_hour: int = 60


class NotificationService:
    """Telegram notification service with rate limiting."""
    
    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.config: NotificationConfig = NotificationConfig()
        self.http_client: Optional[httpx.AsyncClient] = None
        self._last_sent: Dict[str, datetime] = {}
        self._hourly_count = 0
        self._hour_start = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize notification service."""
        self.http_client = httpx.AsyncClient(timeout=10.0)
        await self._load_config()
        logger.info(f"NotificationService initialized (enabled: {self.config.enabled})")
        
    async def cleanup(self):
        """Cleanup resources."""
        if self.http_client:
            await self.http_client.aclose()
            
    async def _load_config(self):
        """Load notification config from database."""
        doc = await self.db.notification_config.find_one({}, {"_id": 0})
        if doc:
            self.config = NotificationConfig(**doc)
        else:
            await self._save_config()
            
    async def _save_config(self):
        """Save notification config to database."""
        await self.db.notification_config.replace_one(
            {},
            self.config.model_dump(),
            upsert=True
        )
        
    async def update_config(self, updates: Dict[str, Any]) -> NotificationConfig:
        """Update notification configuration."""
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        await self._save_config()
        return self.config
    
    async def test_connection(self) -> Tuple[bool, str]:
        """Test Telegram connection."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return False, "Bot token or chat ID not configured"
        
        try:
            success = await self._send_telegram(
                "🔔 *Test Notification*\n\nYour Crypto Trading Bot is connected!",
                parse_mode="Markdown"
            )
            if success:
                return True, "Connection successful"
            return False, "Failed to send message"
        except Exception as e:
            return False, str(e)
    
    async def send(
        self,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        category: str = "general"
    ) -> bool:
        """Send notification with rate limiting."""
        if not self.config.enabled:
            return False
            
        # Check notification preferences
        if level == NotificationLevel.TRADE and not self.config.notify_on_trade:
            return False
        if level == NotificationLevel.CRITICAL and not self.config.notify_on_kill_switch:
            return False
        if level == NotificationLevel.WARNING and not self.config.notify_on_risk_warning:
            return False
            
        # Rate limiting
        async with self._lock:
            now = datetime.now(timezone.utc)
            
            # Reset hourly counter
            if (now - self._hour_start).total_seconds() > 3600:
                self._hourly_count = 0
                self._hour_start = now
                
            # Check hourly limit
            if self._hourly_count >= self.config.max_per_hour:
                logger.warning("Notification rate limit reached")
                return False
                
            # Check minimum interval for same category
            last_sent = self._last_sent.get(category)
            if last_sent:
                elapsed = (now - last_sent).total_seconds()
                if elapsed < self.config.min_interval_seconds:
                    return False
            
            # Send notification
            emoji = self._get_emoji(level)
            formatted_message = f"{emoji} *{level.value.upper()}*\n\n{message}"
            
            success = await self._send_telegram(formatted_message, parse_mode="Markdown")
            
            if success:
                self._last_sent[category] = now
                self._hourly_count += 1
                
                # Log to database
                await self._log_notification(message, level, category, success)
                
            return success
    
    def _get_emoji(self, level: NotificationLevel) -> str:
        """Get emoji for notification level."""
        emojis = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.CRITICAL: "🚨",
            NotificationLevel.TRADE: "💰",
        }
        return emojis.get(level, "📢")
    
    async def _send_telegram(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message via Telegram Bot API."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return False
            
        try:
            url = self.TELEGRAM_API_URL.format(token=self.config.telegram_bot_token)
            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            
            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data.get("ok", False)
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
    async def _log_notification(
        self,
        message: str,
        level: NotificationLevel,
        category: str,
        success: bool
    ):
        """Log notification to database."""
        doc = {
            "message": message,
            "level": level.value,
            "category": category,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.notification_logs.insert_one(doc)
    
    # Convenience methods for common notifications
    async def notify_trade_executed(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        agent: str,
        pnl: Optional[float] = None
    ):
        """Notify about trade execution."""
        pnl_text = f"\nPnL: ${pnl:.2f}" if pnl is not None else ""
        message = (
            f"*Trade Executed*\n\n"
            f"Symbol: `{symbol}`\n"
            f"Side: {side.upper()}\n"
            f"Amount: {amount:.6f}\n"
            f"Price: ${price:.2f}\n"
            f"Agent: {agent}{pnl_text}"
        )
        await self.send(message, NotificationLevel.TRADE, "trade")
    
    async def notify_stop_loss_triggered(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        loss_pct: float,
        agent: str
    ):
        """Notify about stop loss trigger."""
        message = (
            f"*Stop Loss Triggered*\n\n"
            f"Symbol: `{symbol}`\n"
            f"Entry: ${entry_price:.2f}\n"
            f"Exit: ${exit_price:.2f}\n"
            f"Loss: {loss_pct:.2f}%\n"
            f"Agent: {agent}"
        )
        await self.send(message, NotificationLevel.WARNING, "stop_loss")
    
    async def notify_take_profit_triggered(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        profit_pct: float,
        agent: str
    ):
        """Notify about take profit trigger."""
        message = (
            f"*Take Profit Triggered* 🎉\n\n"
            f"Symbol: `{symbol}`\n"
            f"Entry: ${entry_price:.2f}\n"
            f"Exit: ${exit_price:.2f}\n"
            f"Profit: +{profit_pct:.2f}%\n"
            f"Agent: {agent}"
        )
        await self.send(message, NotificationLevel.TRADE, "take_profit")
    
    async def notify_kill_switch_activated(self, reason: str):
        """Notify about kill switch activation."""
        message = (
            f"*KILL SWITCH ACTIVATED*\n\n"
            f"All trading has been halted.\n\n"
            f"Reason: {reason}\n\n"
            f"Manual intervention required."
        )
        await self.send(message, NotificationLevel.CRITICAL, "kill_switch")
    
    async def notify_risk_warning(self, warning: str, current_value: float, limit: float):
        """Notify about risk limit approaching."""
        message = (
            f"*Risk Warning*\n\n"
            f"{warning}\n\n"
            f"Current: {current_value:.2f}\n"
            f"Limit: {limit:.2f}"
        )
        await self.send(message, NotificationLevel.WARNING, "risk")
    
    async def notify_agent_error(self, agent: str, error: str):
        """Notify about agent error."""
        message = (
            f"*Agent Error*\n\n"
            f"Agent: {agent}\n"
            f"Error: {error}"
        )
        await self.send(message, NotificationLevel.WARNING, "agent_error")
    
    async def send_daily_summary(
        self,
        total_equity: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        trades_count: int,
        win_rate: float
    ):
        """Send daily trading summary."""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        message = (
            f"*Daily Summary* {pnl_emoji}\n\n"
            f"Total Equity: ${total_equity:,.2f}\n"
            f"Daily P&L: ${daily_pnl:+,.2f} ({daily_pnl_pct:+.2f}%)\n"
            f"Trades: {trades_count}\n"
            f"Win Rate: {win_rate:.1f}%"
        )
        await self.send(message, NotificationLevel.INFO, "daily_summary")
    
    async def notify_data_source_issue(self, source: str, status: str):
        """Notify about data source issues."""
        message = (
            f"*Data Source Issue*\n\n"
            f"Source: {source}\n"
            f"Status: {status}\n\n"
            f"System may switch to fallback source."
        )
        await self.send(message, NotificationLevel.WARNING, "data_source")
    
    async def notify_safe_mode_entered(self, reason: str):
        """Notify about safe mode activation."""
        message = (
            f"*Safe Mode Activated*\n\n"
            f"New entries paused. Exits only.\n\n"
            f"Reason: {reason}"
        )
        await self.send(message, NotificationLevel.WARNING, "safe_mode")
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration (without sensitive data)."""
        config = self.config.model_dump()
        if config.get('telegram_bot_token'):
            config['telegram_bot_token'] = '***configured***'
        return config
    
    async def get_recent_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent notification logs."""
        docs = await self.db.notification_logs.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return docs
