"""
Advanced Monitoring & Alerting Service (P3.2)
==============================================

🔔 Notification channels:
- In-app alerts (via WebSocket/broadcaster)
- Email notifications (configurable)
- Telegram notifications (configurable)

⚡ Alert types:
- Risk alerts (drawdown, kill switch)
- Execution alerts (blocked, mode change)
- System alerts (circuit breaker, data source)
- Daily summaries

🎯 Design:
- Async, non-blocking
- Rate limiting to prevent spam
- User preferences for notification types
- Full audit trail
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    WEBAPP = "webapp"       # In-app via WebSocket
    EMAIL = "email"         # Email
    TELEGRAM = "telegram"   # Telegram bot


class AlertCategory(str, Enum):
    """Categories of alerts."""
    RISK = "risk"               # Guardian, kill switch, drawdown
    EXECUTION = "execution"     # Orders, mode changes
    SYSTEM = "system"          # Circuit breaker, data source
    PERFORMANCE = "performance" # PnL, metrics
    SECURITY = "security"       # Auth, permissions


class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"           # Informational
    MEDIUM = "medium"     # Requires attention
    HIGH = "high"         # Urgent action needed
    CRITICAL = "critical" # Immediate action required


@dataclass
class AlertConfig:
    """User alert preferences."""
    user_id: str
    
    # Enabled channels per category
    channels: Dict[AlertCategory, List[NotificationChannel]] = field(default_factory=dict)
    
    # Minimum priority to notify
    min_priority: AlertPriority = AlertPriority.MEDIUM
    
    # Rate limiting
    max_alerts_per_hour: int = 20
    quiet_hours_start: Optional[int] = None  # Hour (0-23)
    quiet_hours_end: Optional[int] = None
    
    # Email
    email: Optional[str] = None
    
    # Telegram
    telegram_chat_id: Optional[str] = None
    
    def get_channels(self, category: AlertCategory) -> List[NotificationChannel]:
        """Get enabled channels for a category."""
        return self.channels.get(category, [NotificationChannel.WEBAPP])
    
    def should_notify(self, priority: AlertPriority) -> bool:
        """Check if priority meets threshold."""
        priority_order = [AlertPriority.LOW, AlertPriority.MEDIUM, AlertPriority.HIGH, AlertPriority.CRITICAL]
        return priority_order.index(priority) >= priority_order.index(self.min_priority)


@dataclass
class Alert:
    """Alert instance."""
    id: str
    category: AlertCategory
    priority: AlertPriority
    title: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Delivery tracking
    delivered_to: List[NotificationChannel] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "category": self.category.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "delivered_to": [c.value for c in self.delivered_to],
            "acknowledged": self.acknowledged,
        }


class RateLimiter:
    """Rate limiter for alerts."""
    
    def __init__(self, max_per_hour: int = 20):
        self.max_per_hour = max_per_hour
        self._alerts: Dict[str, List[datetime]] = {}  # user_id -> timestamps
    
    def can_send(self, user_id: str) -> bool:
        """Check if user can receive another alert."""
        self._cleanup_old(user_id)
        return len(self._alerts.get(user_id, [])) < self.max_per_hour
    
    def record(self, user_id: str):
        """Record an alert sent."""
        if user_id not in self._alerts:
            self._alerts[user_id] = []
        self._alerts[user_id].append(datetime.now(timezone.utc))
    
    def _cleanup_old(self, user_id: str):
        """Remove alerts older than 1 hour."""
        if user_id not in self._alerts:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self._alerts[user_id] = [t for t in self._alerts[user_id] if t > cutoff]
    
    def get_remaining(self, user_id: str) -> int:
        """Get remaining alerts allowed this hour."""
        self._cleanup_old(user_id)
        return max(0, self.max_per_hour - len(self._alerts.get(user_id, [])))


class AlertingService:
    """
    Advanced alerting service with multi-channel support.
    
    Features:
    - Multiple notification channels (webapp, email, telegram)
    - User preferences
    - Rate limiting
    - Deduplication
    - Audit logging
    """
    
    def __init__(self, db=None, broadcaster=None):
        self.db = db
        self.broadcaster = broadcaster
        
        # User configs (cached)
        self._user_configs: Dict[str, AlertConfig] = {}
        
        # Rate limiter
        self._rate_limiter = RateLimiter()
        
        # Deduplication (alert hash -> last sent time)
        self._recent_alerts: Dict[str, datetime] = {}
        self._dedup_window_seconds = 300  # 5 minutes
        
        # Alert history (in memory, recent only)
        self._alert_history: List[Alert] = []
        self._max_history = 100
        
        # Stats
        self._alerts_sent = 0
        self._alerts_blocked = 0
        
        logger.info("AlertingService initialized")
    
    async def initialize(self):
        """Load user configs from database."""
        if self.db:
            try:
                configs = await self.db.alert_configs.find().to_list(1000)
                for config in configs:
                    self._user_configs[config["user_id"]] = AlertConfig(
                        user_id=config["user_id"],
                        channels=config.get("channels", {}),
                        min_priority=AlertPriority(config.get("min_priority", "medium")),
                        max_alerts_per_hour=config.get("max_alerts_per_hour", 20),
                        email=config.get("email"),
                        telegram_chat_id=config.get("telegram_chat_id"),
                    )
                logger.info(f"Loaded {len(self._user_configs)} alert configs")
            except Exception as e:
                logger.warning(f"Failed to load alert configs: {e}")
    
    async def send_alert(
        self,
        category: AlertCategory,
        priority: AlertPriority,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        user_ids: List[str] = None,
        broadcast: bool = False,
    ) -> Alert:
        """
        Send an alert to specified users or broadcast.
        
        Args:
            category: Alert category
            priority: Alert priority
            title: Alert title
            message: Alert message
            data: Additional data
            user_ids: Specific users to notify (None = all with relevant prefs)
            broadcast: If True, send to all users via webapp
        
        Returns:
            The created Alert
        """
        # Create alert
        alert_id = hashlib.sha256(
            f"{category.value}:{title}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]
        
        alert = Alert(
            id=alert_id,
            category=category,
            priority=priority,
            title=title,
            message=message,
            data=data or {},
        )
        
        # Check deduplication
        alert_hash = self._hash_alert(alert)
        if self._is_duplicate(alert_hash):
            logger.debug(f"Duplicate alert suppressed: {title}")
            self._alerts_blocked += 1
            return alert
        
        self._record_alert_hash(alert_hash)
        
        # Broadcast via webapp if enabled
        if broadcast and self.broadcaster:
            await self._send_webapp(alert)
            alert.delivered_to.append(NotificationChannel.WEBAPP)
        
        # Send to specific users
        if user_ids:
            for user_id in user_ids:
                await self._send_to_user(alert, user_id)
        
        # Add to history
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history:
            self._alert_history.pop(0)
        
        # Log to DB
        await self._log_alert(alert)
        
        self._alerts_sent += 1
        logger.info(f"Alert sent: [{priority.value}] {title}")
        
        return alert
    
    async def _send_to_user(self, alert: Alert, user_id: str):
        """Send alert to a specific user based on their preferences."""
        config = self._user_configs.get(user_id)
        if not config:
            # Default config
            config = AlertConfig(user_id=user_id)
        
        # Check priority threshold
        if not config.should_notify(alert.priority):
            return
        
        # Check rate limit
        if not self._rate_limiter.can_send(user_id):
            logger.debug(f"Rate limited alert for user {user_id}")
            return
        
        # Get channels for this category
        channels = config.get_channels(alert.category)
        
        for channel in channels:
            try:
                if channel == NotificationChannel.WEBAPP:
                    await self._send_webapp(alert)
                elif channel == NotificationChannel.EMAIL and config.email:
                    await self._send_email(alert, config.email)
                elif channel == NotificationChannel.TELEGRAM and config.telegram_chat_id:
                    await self._send_telegram(alert, config.telegram_chat_id)
                
                if channel not in alert.delivered_to:
                    alert.delivered_to.append(channel)
            except Exception as e:
                logger.warning(f"Failed to send alert via {channel.value}: {e}")
        
        self._rate_limiter.record(user_id)
    
    async def _send_webapp(self, alert: Alert):
        """Send alert via webapp (WebSocket broadcast)."""
        if not self.broadcaster:
            return
        
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        # Map priority to severity
        severity_map = {
            AlertPriority.LOW: AlertSeverity.INFO,
            AlertPriority.MEDIUM: AlertSeverity.WARNING,
            AlertPriority.HIGH: AlertSeverity.WARNING,
            AlertPriority.CRITICAL: AlertSeverity.CRITICAL,
        }
        
        # Map category to event type
        event_type_map = {
            AlertCategory.RISK: EventType.GUARDIAN_ALERT,
            AlertCategory.EXECUTION: EventType.EXECUTION_BLOCKED,
            AlertCategory.SYSTEM: EventType.CIRCUIT_BREAKER,
            AlertCategory.PERFORMANCE: EventType.PNL_UPDATE,
            AlertCategory.SECURITY: EventType.GUARDIAN_ALERT,
        }
        
        event = RealTimeEvent(
            event_type=event_type_map.get(alert.category, EventType.GUARDIAN_ALERT),
            severity=severity_map.get(alert.priority, AlertSeverity.INFO),
            title=alert.title,
            message=alert.message,
            data=alert.data,
        )
        
        await self.broadcaster.broadcast_event(event)
    
    async def _send_email(self, alert: Alert, email: str):
        """Send alert via email (placeholder - requires email service integration)."""
        # TODO: Integrate with email service (SendGrid, etc.)
        logger.info(f"[EMAIL] Would send to {email}: {alert.title}")
        
        # Log the attempt
        if self.db:
            await self.db.notification_log.insert_one({
                "channel": "email",
                "recipient": email,
                "alert_id": alert.id,
                "title": alert.title,
                "timestamp": datetime.now(timezone.utc),
                "status": "simulated",  # Change to "sent" when integrated
            })
    
    async def _send_telegram(self, alert: Alert, chat_id: str):
        """Send alert via Telegram (placeholder - requires Telegram bot integration)."""
        # TODO: Integrate with Telegram bot
        logger.info(f"[TELEGRAM] Would send to {chat_id}: {alert.title}")
        
        # Log the attempt
        if self.db:
            await self.db.notification_log.insert_one({
                "channel": "telegram",
                "recipient": chat_id,
                "alert_id": alert.id,
                "title": alert.title,
                "timestamp": datetime.now(timezone.utc),
                "status": "simulated",  # Change to "sent" when integrated
            })
    
    def _hash_alert(self, alert: Alert) -> str:
        """Generate hash for deduplication."""
        return hashlib.sha256(
            f"{alert.category.value}:{alert.title}:{alert.message}".encode()
        ).hexdigest()[:16]
    
    def _is_duplicate(self, alert_hash: str) -> bool:
        """Check if alert is a duplicate."""
        if alert_hash not in self._recent_alerts:
            return False
        
        last_sent = self._recent_alerts[alert_hash]
        elapsed = (datetime.now(timezone.utc) - last_sent).total_seconds()
        return elapsed < self._dedup_window_seconds
    
    def _record_alert_hash(self, alert_hash: str):
        """Record alert hash for deduplication."""
        self._recent_alerts[alert_hash] = datetime.now(timezone.utc)
        
        # Cleanup old hashes
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._dedup_window_seconds)
        self._recent_alerts = {
            k: v for k, v in self._recent_alerts.items() if v > cutoff
        }
    
    async def _log_alert(self, alert: Alert):
        """Log alert to database."""
        if not self.db:
            return
        
        await self.db.alerts.insert_one({
            "id": alert.id,
            "category": alert.category.value,
            "priority": alert.priority.value,
            "title": alert.title,
            "message": alert.message,
            "data": alert.data,
            "timestamp": alert.timestamp,
            "delivered_to": [c.value for c in alert.delivered_to],
        })
    
    # ============================================================
    # 🎯 CONVENIENCE METHODS
    # ============================================================
    
    async def alert_kill_switch(self, reason: str, user_ids: List[str] = None):
        """Send kill switch activation alert."""
        await self.send_alert(
            category=AlertCategory.RISK,
            priority=AlertPriority.CRITICAL,
            title="⛔ KILL SWITCH ACTIVATED",
            message=f"All trading halted: {reason}",
            data={"reason": reason, "requires_manual_reset": True},
            user_ids=user_ids,
            broadcast=True,
        )
    
    async def alert_drawdown_warning(self, current_pct: float, limit_pct: float, user_ids: List[str] = None):
        """Send drawdown warning alert."""
        await self.send_alert(
            category=AlertCategory.RISK,
            priority=AlertPriority.HIGH,
            title="⚠️ Drawdown Warning",
            message=f"Weekly drawdown at {current_pct:.1f}% (limit: {limit_pct}%)",
            data={"current_pct": current_pct, "limit_pct": limit_pct},
            user_ids=user_ids,
            broadcast=True,
        )
    
    async def alert_execution_blocked(self, reason: str, user_id: str):
        """Send execution blocked alert."""
        await self.send_alert(
            category=AlertCategory.EXECUTION,
            priority=AlertPriority.MEDIUM,
            title="🛑 Execution Blocked",
            message=reason,
            data={"reason": reason},
            user_ids=[user_id],
        )
    
    async def alert_mode_change(self, old_mode: str, new_mode: str, user_id: str):
        """Send mode change alert."""
        priority = AlertPriority.CRITICAL if new_mode == "live" else AlertPriority.MEDIUM
        await self.send_alert(
            category=AlertCategory.EXECUTION,
            priority=priority,
            title=f"🔄 Mode Changed to {new_mode.upper()}",
            message=f"Execution mode changed from {old_mode} to {new_mode}",
            data={"old_mode": old_mode, "new_mode": new_mode, "changed_by": user_id},
            broadcast=True,
        )
    
    async def alert_circuit_breaker(self, tripped: bool, reason: str = ""):
        """Send circuit breaker alert."""
        if tripped:
            await self.send_alert(
                category=AlertCategory.SYSTEM,
                priority=AlertPriority.HIGH,
                title="🔴 Circuit Breaker Tripped",
                message=f"Execution halted: {reason}",
                data={"tripped": True, "reason": reason},
                broadcast=True,
            )
        else:
            await self.send_alert(
                category=AlertCategory.SYSTEM,
                priority=AlertPriority.LOW,
                title="🟢 Circuit Breaker Reset",
                message="Circuit breaker has reset, execution can resume",
                data={"tripped": False},
                broadcast=True,
            )
    
    async def send_daily_summary(self, user_id: str, summary: Dict[str, Any]):
        """Send daily performance summary."""
        pnl = summary.get("pnl_eur", 0)
        emoji = "📈" if pnl >= 0 else "📉"
        
        await self.send_alert(
            category=AlertCategory.PERFORMANCE,
            priority=AlertPriority.LOW,
            title=f"{emoji} Daily Summary",
            message=f"PnL: {pnl:+.2f} EUR | Orders: {summary.get('orders', 0)} | Win Rate: {summary.get('win_rate', 0):.0f}%",
            data=summary,
            user_ids=[user_id],
        )
    
    # ============================================================
    # 📊 STATUS & HISTORY
    # ============================================================
    
    def get_recent_alerts(self, count: int = 20, category: AlertCategory = None) -> List[Dict]:
        """Get recent alerts."""
        alerts = self._alert_history
        if category:
            alerts = [a for a in alerts if a.category == category]
        return [a.to_dict() for a in alerts[-count:]]
    
    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alert_history:
            if alert.id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now(timezone.utc)
                alert.acknowledged_by = user_id
                
                # Update in DB
                if self.db:
                    await self.db.alerts.update_one(
                        {"id": alert_id},
                        {"$set": {
                            "acknowledged": True,
                            "acknowledged_at": alert.acknowledged_at,
                            "acknowledged_by": user_id,
                        }}
                    )
                
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alerting stats."""
        return {
            "alerts_sent": self._alerts_sent,
            "alerts_blocked": self._alerts_blocked,
            "recent_alerts": len(self._alert_history),
            "user_configs": len(self._user_configs),
            "dedup_window_seconds": self._dedup_window_seconds,
        }
    
    async def update_user_config(self, user_id: str, config: Dict[str, Any]):
        """Update user alert preferences."""
        alert_config = AlertConfig(
            user_id=user_id,
            channels={
                AlertCategory(k): [NotificationChannel(c) for c in v]
                for k, v in config.get("channels", {}).items()
            },
            min_priority=AlertPriority(config.get("min_priority", "medium")),
            max_alerts_per_hour=config.get("max_alerts_per_hour", 20),
            email=config.get("email"),
            telegram_chat_id=config.get("telegram_chat_id"),
        )
        
        self._user_configs[user_id] = alert_config
        
        # Save to DB
        if self.db:
            await self.db.alert_configs.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "channels": config.get("channels", {}),
                    "min_priority": config.get("min_priority", "medium"),
                    "max_alerts_per_hour": config.get("max_alerts_per_hour", 20),
                    "email": config.get("email"),
                    "telegram_chat_id": config.get("telegram_chat_id"),
                    "updated_at": datetime.now(timezone.utc),
                }},
                upsert=True
            )
        
        logger.info(f"Updated alert config for user {user_id}")


# ============================================================
# 🏭 FACTORY
# ============================================================

_alerting_service: Optional[AlertingService] = None


def get_alerting_service() -> Optional[AlertingService]:
    """Get global alerting service instance."""
    return _alerting_service


def set_alerting_service(service: AlertingService):
    """Set global alerting service instance."""
    global _alerting_service
    _alerting_service = service


async def init_alerting_service(db=None, broadcaster=None) -> AlertingService:
    """Initialize and return the alerting service."""
    global _alerting_service
    
    _alerting_service = AlertingService(db=db, broadcaster=broadcaster)
    await _alerting_service.initialize()
    
    return _alerting_service
