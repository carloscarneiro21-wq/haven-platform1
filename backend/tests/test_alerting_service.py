"""
Unit Tests for Alerting Service (P3.2)
======================================

Tests for:
- Alert creation and delivery
- Rate limiting
- Deduplication
- User preferences
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest_plugins = ('pytest_asyncio',)


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    def test_allows_within_limit(self):
        """Test rate limiter allows alerts within limit."""
        from services.alerting_service import RateLimiter
        
        limiter = RateLimiter(max_per_hour=5)
        
        for _ in range(5):
            assert limiter.can_send("user1") is True
            limiter.record("user1")
        
        # 6th should be blocked
        assert limiter.can_send("user1") is False
    
    def test_different_users_independent(self):
        """Test different users have independent limits."""
        from services.alerting_service import RateLimiter
        
        limiter = RateLimiter(max_per_hour=2)
        
        limiter.record("user1")
        limiter.record("user1")
        
        # user1 is blocked
        assert limiter.can_send("user1") is False
        
        # user2 can still send
        assert limiter.can_send("user2") is True
    
    def test_get_remaining(self):
        """Test getting remaining alerts."""
        from services.alerting_service import RateLimiter
        
        limiter = RateLimiter(max_per_hour=10)
        
        assert limiter.get_remaining("user1") == 10
        
        limiter.record("user1")
        limiter.record("user1")
        
        assert limiter.get_remaining("user1") == 8


class TestAlertConfig:
    """Tests for AlertConfig."""
    
    def test_should_notify_priority(self):
        """Test priority filtering."""
        from services.alerting_service import AlertConfig, AlertPriority
        
        config = AlertConfig(user_id="user1", min_priority=AlertPriority.MEDIUM)
        
        assert config.should_notify(AlertPriority.LOW) is False
        assert config.should_notify(AlertPriority.MEDIUM) is True
        assert config.should_notify(AlertPriority.HIGH) is True
        assert config.should_notify(AlertPriority.CRITICAL) is True
    
    def test_get_channels_default(self):
        """Test default channel is WEBAPP."""
        from services.alerting_service import AlertConfig, AlertCategory, NotificationChannel
        
        config = AlertConfig(user_id="user1")
        
        channels = config.get_channels(AlertCategory.RISK)
        assert NotificationChannel.WEBAPP in channels


class TestAlert:
    """Tests for Alert."""
    
    def test_to_dict(self):
        """Test converting alert to dictionary."""
        from services.alerting_service import Alert, AlertCategory, AlertPriority
        
        alert = Alert(
            id="test123",
            category=AlertCategory.RISK,
            priority=AlertPriority.HIGH,
            title="Test Alert",
            message="Test message",
            data={"key": "value"},
        )
        
        d = alert.to_dict()
        
        assert d["id"] == "test123"
        assert d["category"] == "risk"
        assert d["priority"] == "high"
        assert d["title"] == "Test Alert"
        assert d["data"]["key"] == "value"


class TestAlertingService:
    """Tests for AlertingService."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        db.alerts = MagicMock()
        db.alerts.insert_one = AsyncMock()
        db.alert_configs = MagicMock()
        db.alert_configs.find = MagicMock()
        db.alert_configs.find.return_value.to_list = AsyncMock(return_value=[])
        db.notification_log = MagicMock()
        db.notification_log.insert_one = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_broadcaster(self):
        """Create mock broadcaster."""
        from services.realtime_broadcaster import RealTimeBroadcaster
        
        broadcaster = MagicMock(spec=RealTimeBroadcaster)
        broadcaster.broadcast_event = AsyncMock()
        return broadcaster
    
    @pytest.fixture
    def alerting_service(self, mock_db, mock_broadcaster):
        """Create alerting service."""
        from services.alerting_service import AlertingService
        
        service = AlertingService(db=mock_db, broadcaster=mock_broadcaster)
        return service
    
    @pytest.mark.asyncio
    async def test_send_alert_basic(self, alerting_service, mock_db):
        """Test basic alert sending."""
        from services.alerting_service import AlertCategory, AlertPriority
        
        alert = await alerting_service.send_alert(
            category=AlertCategory.RISK,
            priority=AlertPriority.HIGH,
            title="Test Alert",
            message="Test message",
            broadcast=True,
        )
        
        assert alert is not None
        assert alert.title == "Test Alert"
        assert alert.category == AlertCategory.RISK
        
        # Should be logged to DB
        mock_db.alerts.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_alert_with_broadcast(self, alerting_service, mock_broadcaster):
        """Test alert broadcasts via WebSocket."""
        from services.alerting_service import AlertCategory, AlertPriority
        
        await alerting_service.send_alert(
            category=AlertCategory.SYSTEM,
            priority=AlertPriority.CRITICAL,
            title="System Alert",
            message="Critical issue",
            broadcast=True,
        )
        
        mock_broadcaster.broadcast_event.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_deduplication(self, alerting_service):
        """Test duplicate alerts are suppressed."""
        from services.alerting_service import AlertCategory, AlertPriority
        
        # Send same alert twice
        alert1 = await alerting_service.send_alert(
            category=AlertCategory.RISK,
            priority=AlertPriority.HIGH,
            title="Duplicate Alert",
            message="Same message",
        )
        
        alert2 = await alerting_service.send_alert(
            category=AlertCategory.RISK,
            priority=AlertPriority.HIGH,
            title="Duplicate Alert",
            message="Same message",
        )
        
        # Should only count as one sent
        assert alerting_service._alerts_sent == 1
        assert alerting_service._alerts_blocked == 1
    
    @pytest.mark.asyncio
    async def test_convenience_kill_switch(self, alerting_service, mock_broadcaster):
        """Test kill switch alert convenience method."""
        await alerting_service.alert_kill_switch(reason="Weekly loss limit")
        
        # Should have broadcast
        mock_broadcaster.broadcast_event.assert_called_once()
        
        # Check alert in history
        assert len(alerting_service._alert_history) == 1
        alert = alerting_service._alert_history[0]
        assert "KILL SWITCH" in alert.title
    
    @pytest.mark.asyncio
    async def test_convenience_drawdown_warning(self, alerting_service):
        """Test drawdown warning convenience method."""
        await alerting_service.alert_drawdown_warning(
            current_pct=-4.5,
            limit_pct=-5.0
        )
        
        alert = alerting_service._alert_history[-1]
        assert "Drawdown" in alert.title
        assert alert.data["current_pct"] == -4.5
    
    def test_get_recent_alerts(self, alerting_service):
        """Test getting recent alerts."""
        from services.alerting_service import Alert, AlertCategory, AlertPriority
        
        # Add some alerts
        for i in range(5):
            alerting_service._alert_history.append(Alert(
                id=f"alert{i}",
                category=AlertCategory.RISK,
                priority=AlertPriority.MEDIUM,
                title=f"Alert {i}",
                message="Test",
            ))
        
        recent = alerting_service.get_recent_alerts(count=3)
        
        assert len(recent) == 3
        assert recent[-1]["title"] == "Alert 4"
    
    def test_get_stats(self, alerting_service):
        """Test getting stats."""
        stats = alerting_service.get_stats()
        
        assert "alerts_sent" in stats
        assert "alerts_blocked" in stats
        assert "recent_alerts" in stats


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
