"""
Unit Tests for Real-Time Broadcaster (P3.1)
============================================

Tests for:
- Event broadcasting
- State change detection
- History management
- Audit logging
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest_plugins = ('pytest_asyncio',)


class TestRealTimeEvent:
    """Tests for RealTimeEvent."""
    
    def test_event_creation(self):
        """Test creating a real-time event."""
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        event = RealTimeEvent(
            event_type=EventType.GUARDIAN_ALERT,
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="This is a test alert",
            data={"key": "value"},
        )
        
        assert event.event_type == EventType.GUARDIAN_ALERT
        assert event.severity == AlertSeverity.WARNING
        assert event.title == "Test Alert"
        assert event.data["key"] == "value"
    
    def test_to_ws_message(self):
        """Test converting event to WebSocket message."""
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        event = RealTimeEvent(
            event_type=EventType.KILL_SWITCH,
            severity=AlertSeverity.CRITICAL,
            title="Kill Switch",
            message="Activated",
        )
        
        msg = event.to_ws_message()
        
        assert msg["type"] == "event"
        assert msg["event_type"] == "kill_switch"
        assert msg["severity"] == "critical"
        assert msg["title"] == "Kill Switch"
        assert "timestamp" in msg


class TestRealTimeBroadcaster:
    """Tests for RealTimeBroadcaster."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        db.realtime_events = MagicMock()
        db.realtime_events.insert_one = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_ws_manager(self):
        """Create mock WebSocket manager."""
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        ws.get_connection_count = MagicMock(return_value=2)
        return ws
    
    @pytest.fixture
    def broadcaster(self, mock_db, mock_ws_manager):
        """Create broadcaster with mocks."""
        from services.realtime_broadcaster import RealTimeBroadcaster
        
        b = RealTimeBroadcaster(db=mock_db, ws_manager=mock_ws_manager)
        return b
    
    @pytest.mark.asyncio
    async def test_broadcast_event(self, broadcaster, mock_ws_manager, mock_db):
        """Test broadcasting an event."""
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        event = RealTimeEvent(
            event_type=EventType.EXECUTION_COMPLETE,
            severity=AlertSeverity.INFO,
            title="Test",
            message="Test message",
        )
        
        await broadcaster.broadcast_event(event)
        
        # Event should be in history
        assert len(broadcaster._event_history) == 1
        
        # WebSocket should have been called
        mock_ws_manager.broadcast.assert_called_once()
        
        # DB should have logged event
        mock_db.realtime_events.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_event_history_limit(self, broadcaster):
        """Test event history is limited."""
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        # Add more events than the limit
        for i in range(60):
            await broadcaster.broadcast_event(RealTimeEvent(
                event_type=EventType.EXECUTION_COMPLETE,
                severity=AlertSeverity.INFO,
                title=f"Event {i}",
                message="Test",
            ))
        
        # Should be capped at max_history (50)
        assert len(broadcaster._event_history) == 50
        
        # Should keep most recent
        assert broadcaster._event_history[-1].title == "Event 59"
    
    @pytest.mark.asyncio
    async def test_get_recent_events(self, broadcaster):
        """Test getting recent events."""
        from services.realtime_broadcaster import RealTimeEvent, EventType, AlertSeverity
        
        # Add some events
        for i in range(10):
            await broadcaster.broadcast_event(RealTimeEvent(
                event_type=EventType.ORDER_CREATED,
                severity=AlertSeverity.INFO,
                title=f"Order {i}",
                message="Created",
            ))
        
        # Get last 5
        recent = broadcaster.get_recent_events(count=5)
        assert len(recent) == 5
        assert recent[-1]["title"] == "Order 9"  # Most recent
    
    @pytest.mark.asyncio
    async def test_broadcast_execution_start(self, broadcaster, mock_ws_manager):
        """Test broadcasting execution start."""
        await broadcaster.broadcast_execution_start(
            execution_id="exec123",
            mode="paper",
            symbol="BTC/USDT"
        )
        
        mock_ws_manager.broadcast.assert_called_once()
        
        # Check event in history
        event = broadcaster._event_history[-1]
        assert event.event_type.value == "execution_start"
        assert "exec123" in event.data["execution_id"]
    
    @pytest.mark.asyncio
    async def test_broadcast_execution_blocked(self, broadcaster, mock_ws_manager):
        """Test broadcasting execution blocked."""
        await broadcaster.broadcast_execution_blocked(
            reason="Daily cap exceeded",
            user_id="user123"
        )
        
        event = broadcaster._event_history[-1]
        assert event.event_type.value == "execution_blocked"
        assert event.severity.value == "warning"
        assert "Daily cap exceeded" in event.message
    
    @pytest.mark.asyncio
    async def test_broadcast_mode_change_to_live(self, broadcaster):
        """Test broadcasting mode change to LIVE is CRITICAL."""
        from services.realtime_broadcaster import AlertSeverity
        
        await broadcaster.broadcast_mode_change(
            old_mode="paper",
            new_mode="live",
            user_id="user123"
        )
        
        event = broadcaster._event_history[-1]
        assert event.severity == AlertSeverity.CRITICAL
    
    @pytest.mark.asyncio
    async def test_broadcast_circuit_breaker_trip(self, broadcaster):
        """Test broadcasting circuit breaker trip."""
        await broadcaster.broadcast_circuit_breaker(
            tripped=True,
            reason="Too many failures"
        )
        
        event = broadcaster._event_history[-1]
        assert event.event_type.value == "circuit_breaker"
        assert event.severity.value == "critical"
        assert "Too many failures" in event.message
    
    def test_get_status(self, broadcaster, mock_ws_manager):
        """Test getting broadcaster status."""
        status = broadcaster.get_status()
        
        assert "running" in status
        assert "events_in_history" in status
        assert status["ws_connections"] == 2
        assert "services_connected" in status


class TestGuardianStateDetection:
    """Tests for Guardian state change detection."""
    
    @pytest.fixture
    def mock_guardian(self):
        """Create mock guardian service."""
        guardian = MagicMock()
        guardian.get_status = MagicMock(return_value={
            "kill_switch_active": False,
            "weekly_drawdown_pct": -2.5,
            "weekly_drawdown_limit_pct": -5.0,
            "daily_loss_eur": -10,
        })
        return guardian
    
    @pytest.mark.asyncio
    async def test_detects_kill_switch_activation(self, mock_guardian):
        """Test detection of kill switch activation."""
        from services.realtime_broadcaster import RealTimeBroadcaster, EventType
        
        broadcaster = RealTimeBroadcaster()
        broadcaster.guardian_service = mock_guardian
        broadcaster._last_guardian_state = {
            "kill_switch_active": False,
            "weekly_drawdown_pct": -2.0,
        }
        
        # Now kill switch is active
        mock_guardian.get_status.return_value = {
            "kill_switch_active": True,
            "weekly_drawdown_pct": -5.5,
            "block_reason": "Weekly loss limit exceeded",
        }
        
        await broadcaster._check_guardian_changes()
        
        # Should have kill switch event
        kill_events = [
            e for e in broadcaster._event_history 
            if e.event_type == EventType.KILL_SWITCH
        ]
        assert len(kill_events) == 1
        assert "ACTIVATED" in kill_events[0].title


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
