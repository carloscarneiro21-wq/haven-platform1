"""Tests for data_feed compatibility adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from services.data_feed.compat import DataFeed, Candle, HealthAdapter


class TestCandle:
    """Test Candle format for backward compatibility."""
    
    def test_candle_creation(self):
        """Test candle creation."""
        candle = Candle(
            timestamp=1704067200000,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
        )
        assert candle.timestamp == 1704067200000
        assert candle.open == 100.0
        assert candle.high == 105.0
        assert candle.low == 95.0
        assert candle.close == 102.0
        assert candle.volume == 1000.0
    
    def test_candle_to_dict(self):
        """Test candle to dict conversion."""
        candle = Candle(
            timestamp=1704067200000,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
        )
        data = candle.to_dict()
        assert data["timestamp"] == 1704067200000
        assert data["open"] == 100.0
        assert data["close"] == 102.0


class TestDataFeedCompat:
    """Test DataFeed compatibility adapter."""
    
    @pytest.fixture
    def mock_manager(self):
        """Create mock DataFeedManager."""
        manager = MagicMock()
        manager.is_safe_mode = False
        manager.active_source = "kraken"
        manager.event_logger = None
        manager.get_status.return_value = {
            "initialized": True,
            "active_source": "kraken",
            "safe_mode": False,
            "safe_mode_reason": "",
            "adapters": {},
            "cache_stats": {},
        }
        return manager
    
    @pytest.fixture
    def data_feed(self, mock_manager):
        """Create DataFeed with mocked manager."""
        feed = DataFeed(db=None)
        feed._manager = mock_manager
        feed.health = HealthAdapter(mock_manager)
        return feed
    
    def test_safe_mode_property(self, data_feed, mock_manager):
        """Test safe_mode property delegation."""
        mock_manager.is_safe_mode = False
        assert data_feed.safe_mode is False
        
        mock_manager.is_safe_mode = True
        assert data_feed.safe_mode is True
    
    def test_safe_mode_reason_property(self, data_feed, mock_manager):
        """Test safe_mode_reason property."""
        mock_manager.get_status.return_value = {
            "safe_mode_reason": "Test reason"
        }
        assert data_feed.safe_mode_reason == "Test reason"
    
    @pytest.mark.asyncio
    async def test_fetch_ticker(self, data_feed, mock_manager):
        """Test fetch_ticker converts to compatible format."""
        from services.data_feed.venues.base import TickerData
        
        mock_manager.fetch_ticker = AsyncMock(return_value=TickerData(
            symbol="BTC/USDT",
            last=50000.0,
            bid=49990.0,
            ask=50010.0,
            high_24h=51000.0,
            low_24h=49000.0,
            volume_24h=10000.0,
            vwap_24h=50100.0,
            timestamp=1704067200000,
            source="kraken",
        ))
        
        ticker = await data_feed.fetch_ticker("BTC/USDT")
        
        assert ticker["symbol"] == "BTC/USDT"
        assert ticker["last"] == 50000.0
        assert ticker["bid"] == 49990.0
        assert ticker["ask"] == 50010.0
        assert ticker["source"] == "kraken"
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_empty(self, data_feed, mock_manager):
        """Test fetch_ticker returns empty dict when no data."""
        mock_manager.fetch_ticker = AsyncMock(return_value=None)
        
        ticker = await data_feed.fetch_ticker("UNKNOWN/USD")
        
        assert ticker == {}
    
    @pytest.mark.asyncio
    async def test_fetch_candles(self, data_feed, mock_manager):
        """Test fetch_candles converts to Candle objects."""
        from services.data_feed.venues.base import CandleData
        
        mock_manager.fetch_candles = AsyncMock(return_value=[
            CandleData(
                timestamp=1704067200000,
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000.0,
            ),
            CandleData(
                timestamp=1704070800000,
                open=102.0,
                high=108.0,
                low=100.0,
                close=106.0,
                volume=1200.0,
            ),
        ])
        
        candles = await data_feed.fetch_candles("BTC/USDT", "1h", 100)
        
        assert len(candles) == 2
        assert isinstance(candles[0], Candle)
        assert candles[0].open == 100.0
        assert candles[1].close == 106.0
    
    @pytest.mark.asyncio
    async def test_get_orderbook(self, data_feed, mock_manager):
        """Test get_orderbook conversion."""
        from services.data_feed.venues.base import OrderBookData
        
        mock_manager.fetch_orderbook = AsyncMock(return_value=OrderBookData(
            symbol="BTC/USDT",
            bids=[
                [49990.0, 1.0],
                [49980.0, 2.0],
            ],
            asks=[
                [50010.0, 1.5],
                [50020.0, 2.5],
            ],
            timestamp=1704067200000,
            source="kraken",
        ))
        
        orderbook = await data_feed.get_orderbook("BTC/USDT", 10)
        
        assert len(orderbook["bids"]) == 2
        assert orderbook["bids"][0] == [49990.0, 1.0]
        assert len(orderbook["asks"]) == 2
        assert orderbook["asks"][0] == [50010.0, 1.5]
    
    @pytest.mark.asyncio
    async def test_get_orderbook_empty(self, data_feed, mock_manager):
        """Test get_orderbook returns empty when no data."""
        mock_manager.fetch_orderbook = AsyncMock(return_value=None)
        
        orderbook = await data_feed.get_orderbook("UNKNOWN/USD", 10)
        
        assert orderbook == {"bids": [], "asks": []}
    
    def test_get_status(self, data_feed, mock_manager):
        """Test get_status returns expected format."""
        mock_manager.get_status.return_value = {
            "initialized": True,
            "active_source": "kraken",
            "safe_mode": False,
            "safe_mode_reason": "",
            "adapters": {"kraken": {"enabled": True}},
            "cache_stats": {"ticker": 5},
        }
        
        status = data_feed.get_status()
        
        assert status["initialized"] is True
        assert status["active_source"] == "kraken"
        assert status["safe_mode"] is False


class TestHealthAdapter:
    """Test HealthAdapter for backward compatibility."""
    
    def test_get_active_source(self):
        """Test get_active_source delegation."""
        manager = MagicMock()
        manager.active_source = "binance"
        
        health = HealthAdapter(manager)
        
        assert health.get_active_source() == "binance"
    
    def test_is_data_stale(self):
        """Test is_data_stale delegation."""
        manager = MagicMock()
        manager.is_safe_mode = True
        
        health = HealthAdapter(manager)
        
        assert health.is_data_stale() is True
    
    def test_get_status(self):
        """Test get_status returns compatible format."""
        manager = MagicMock()
        manager.get_status.return_value = {
            "safe_mode": False,
            "active_source": "kraken",
            "safe_mode_reason": "",
            "adapters": {"kraken": {"enabled": True}},
        }
        
        health = HealthAdapter(manager)
        status = health.get_status()
        
        assert status["ok"] is True
        assert status["using_fallback"] is False
        assert status["active_source"] == "kraken"
