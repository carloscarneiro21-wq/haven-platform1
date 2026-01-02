"""
Unit Tests for Enhanced Data Feed Module (P2.2)
===============================================

Tests:
- Symbol mapping between internal format and venue-specific formats
- Fallback behavior when primary source fails
- Staleness detection and safe mode
- Invalid data handling and validation
- Cache behavior
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest_plugins = ('pytest_asyncio',)


# ============ Symbol Mapper Tests ============

class TestSymbolMapper:
    """Tests for SymbolMapper."""
    
    def test_get_info_valid_symbol(self):
        """Test getting info for a valid symbol."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        info = mapper.get_info("BTC/USDT")
        assert info is not None
        assert info.internal == "BTC/USDT"
        assert info.base == "BTC"
        assert info.quote == "USDT"
        assert info.kraken == "XBTUSDT"
        assert info.binance == "BTCUSDT"
        assert info.coingecko == "bitcoin"
    
    def test_get_info_invalid_symbol(self):
        """Test getting info for an invalid symbol."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        info = mapper.get_info("INVALID/SYMBOL")
        assert info is None
    
    def test_to_venue_kraken(self):
        """Test converting internal symbol to Kraken format."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        assert mapper.to_venue("BTC/USDT", Venue.KRAKEN) == "XBTUSDT"
        assert mapper.to_venue("ETH/USDT", Venue.KRAKEN) == "ETHUSDT"
        assert mapper.to_venue("BTC/USD", Venue.KRAKEN) == "XXBTZUSD"
    
    def test_to_venue_binance(self):
        """Test converting internal symbol to Binance format."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        assert mapper.to_venue("BTC/USDT", Venue.BINANCE) == "BTCUSDT"
        assert mapper.to_venue("ETH/USDT", Venue.BINANCE) == "ETHUSDT"
    
    def test_to_venue_coingecko(self):
        """Test converting internal symbol to CoinGecko ID."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        assert mapper.to_venue("BTC/USDT", Venue.COINGECKO) == "bitcoin"
        assert mapper.to_venue("ETH/USDT", Venue.COINGECKO) == "ethereum"
        assert mapper.to_venue("SOL/USDT", Venue.COINGECKO) == "solana"
    
    def test_from_venue_kraken(self):
        """Test converting Kraken symbol to internal format."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        assert mapper.from_venue("XBTUSDT", Venue.KRAKEN) == "BTC/USDT"
        assert mapper.from_venue("ETHUSDT", Venue.KRAKEN) == "ETH/USDT"
        assert mapper.from_venue("XXBTZUSD", Venue.KRAKEN) == "BTC/USD"
    
    def test_from_venue_binance(self):
        """Test converting Binance symbol to internal format."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        assert mapper.from_venue("BTCUSDT", Venue.BINANCE) == "BTC/USDT"
        assert mapper.from_venue("ETHUSDT", Venue.BINANCE) == "ETH/USDT"
    
    def test_from_venue_coingecko(self):
        """Test converting CoinGecko ID to internal format."""
        from services.data_feed import get_symbol_mapper, Venue
        mapper = get_symbol_mapper()
        
        # Note: CoinGecko IDs map to the first matching internal symbol
        # since the same coin ID is used for both USDT and USD pairs
        result = mapper.from_venue("bitcoin", Venue.COINGECKO)
        assert result in ["BTC/USDT", "BTC/USD", "BTC/EUR"]
        
        result = mapper.from_venue("ethereum", Venue.COINGECKO)
        assert result in ["ETH/USDT", "ETH/USD", "ETH/EUR"]
    
    def test_normalize_internal_no_slash(self):
        """Test normalizing symbol without slash."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        # BTCUSDT -> BTC/USDT
        info = mapper.get_info("BTCUSDT")
        assert info is not None
        assert info.internal == "BTC/USDT"
    
    def test_is_valid(self):
        """Test symbol validation."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        assert mapper.is_valid("BTC/USDT") is True
        assert mapper.is_valid("ETH/USDT") is True
        assert mapper.is_valid("INVALID/PAIR") is False
    
    def test_list_symbols(self):
        """Test listing all symbols."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        symbols = mapper.list_symbols()
        assert len(symbols) > 0
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
    
    def test_list_symbols_by_quote(self):
        """Test listing symbols filtered by quote currency."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        usdt_symbols = mapper.list_symbols(quote="USDT")
        assert all("/USDT" in s for s in usdt_symbols)
        
        usd_symbols = mapper.list_symbols(quote="USD")
        assert all("/USD" in s for s in usd_symbols)
    
    def test_get_precision(self):
        """Test getting price/size precision."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        price_dec, size_dec = mapper.get_precision("BTC/USDT")
        assert price_dec == 1  # BTC price to 1 decimal
        assert size_dec == 5  # BTC size to 5 decimals
    
    def test_round_price(self):
        """Test price rounding."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        rounded = mapper.round_price("BTC/USDT", 95123.456789)
        assert rounded == 95123.5  # 1 decimal for BTC
    
    def test_round_size(self):
        """Test size rounding."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        rounded = mapper.round_size("BTC/USDT", 0.123456789)
        assert rounded == 0.12346  # 5 decimals for BTC
    
    def test_validate_order_size(self):
        """Test order size validation."""
        from services.data_feed import get_symbol_mapper
        mapper = get_symbol_mapper()
        
        # Valid size
        valid, error = mapper.validate_order_size("BTC/USDT", 0.001)
        assert valid is True
        assert error == ""
        
        # Size below minimum
        valid, error = mapper.validate_order_size("BTC/USDT", 0.00001)
        assert valid is False
        assert "below minimum" in error


# ============ Timeframe Mapper Tests ============

class TestTimeframeMapper:
    """Tests for TimeframeMapper."""
    
    def test_get_info(self):
        """Test getting timeframe info."""
        from services.data_feed import get_timeframe_mapper
        mapper = get_timeframe_mapper()
        
        info = mapper.get_info("1h")
        assert info is not None
        assert info.seconds == 3600
        assert info.kraken == 60
        assert info.binance == "1h"
    
    def test_to_venue_kraken(self):
        """Test converting timeframe to Kraken format."""
        from services.data_feed import get_timeframe_mapper, Venue
        mapper = get_timeframe_mapper()
        
        assert mapper.to_venue("1h", Venue.KRAKEN) == 60
        assert mapper.to_venue("4h", Venue.KRAKEN) == 240
        assert mapper.to_venue("1d", Venue.KRAKEN) == 1440
    
    def test_to_venue_binance(self):
        """Test converting timeframe to Binance format."""
        from services.data_feed import get_timeframe_mapper, Venue
        mapper = get_timeframe_mapper()
        
        assert mapper.to_venue("1h", Venue.BINANCE) == "1h"
        assert mapper.to_venue("4h", Venue.BINANCE) == "4h"
        assert mapper.to_venue("1d", Venue.BINANCE) == "1d"
    
    def test_get_seconds(self):
        """Test getting timeframe duration in seconds."""
        from services.data_feed import get_timeframe_mapper
        mapper = get_timeframe_mapper()
        
        assert mapper.get_seconds("1m") == 60
        assert mapper.get_seconds("5m") == 300
        assert mapper.get_seconds("1h") == 3600
        assert mapper.get_seconds("1d") == 86400


# ============ Data Types Tests ============

class TestTickerData:
    """Tests for TickerData."""
    
    def test_spread_calculation(self):
        """Test spread calculation."""
        from services.data_feed import TickerData
        
        ticker = TickerData(
            symbol="BTC/USDT",
            source="kraken",
            last=95000,
            bid=94990,
            ask=95010,
        )
        
        assert ticker.spread == 20
        assert abs(ticker.spread_pct - 0.021) < 0.001  # ~0.021%
        assert ticker.mid_price == 95000
    
    def test_is_valid(self):
        """Test ticker validity check."""
        from services.data_feed import TickerData
        
        # Valid ticker
        valid = TickerData(symbol="BTC/USDT", source="kraken", last=95000, bid=94990, ask=95010)
        assert valid.is_valid is True
        
        # Invalid - no price
        invalid = TickerData(symbol="BTC/USDT", source="kraken", last=0, bid=0, ask=0)
        assert invalid.is_valid is False
    
    def test_age_seconds(self):
        """Test data age calculation."""
        from services.data_feed import TickerData
        
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # Fresh data
        fresh = TickerData(symbol="BTC/USDT", source="kraken", timestamp=now_ms)
        assert fresh.age_seconds < 1
        
        # Old data
        old_ms = now_ms - 60000  # 60 seconds ago
        old = TickerData(symbol="BTC/USDT", source="kraken", timestamp=old_ms)
        assert old.age_seconds >= 59


class TestCandleData:
    """Tests for CandleData."""
    
    def test_is_valid(self):
        """Test candle validity check."""
        from services.data_feed import CandleData
        
        # Valid candle
        valid = CandleData(
            timestamp=1000,
            open=100, high=105, low=95, close=102, volume=1000
        )
        assert valid.is_valid is True
        
        # Invalid - high < low
        invalid = CandleData(
            timestamp=1000,
            open=100, high=95, low=105, close=102, volume=1000
        )
        assert invalid.is_valid is False
        
        # Invalid - close > high
        invalid2 = CandleData(
            timestamp=1000,
            open=100, high=105, low=95, close=110, volume=1000
        )
        assert invalid2.is_valid is False
        
        # Invalid - negative price
        invalid3 = CandleData(
            timestamp=1000,
            open=-100, high=105, low=95, close=102, volume=1000
        )
        assert invalid3.is_valid is False


# ============ Data Feed Manager Tests ============

class TestDataFeedManager:
    """Tests for DataFeedManager."""
    
    @pytest.fixture
    def mock_kraken_adapter(self):
        """Create mock Kraken adapter."""
        from services.data_feed import TickerData, CandleData
        
        adapter = MagicMock()
        adapter.name = "kraken"
        adapter.enabled = True
        adapter.is_healthy = True
        adapter._last_success = datetime.now(timezone.utc)
        
        adapter.initialize = AsyncMock()
        adapter.cleanup = AsyncMock()
        adapter.fetch_ticker = AsyncMock(return_value=TickerData(
            symbol="BTC/USDT",
            source="kraken",
            last=95000,
            bid=94990,
            ask=95010,
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000)
        ))
        adapter.fetch_candles = AsyncMock(return_value=[
            CandleData(timestamp=(i+1)*3600000, open=95000+i, high=95100+i, low=94900+i, close=95050+i, volume=100)
            for i in range(10)
        ])
        adapter.get_status = MagicMock(return_value={"name": "kraken", "healthy": True})
        
        return adapter
    
    @pytest.fixture
    def mock_binance_adapter(self):
        """Create mock Binance adapter."""
        from services.data_feed import TickerData, CandleData
        
        adapter = MagicMock()
        adapter.name = "binance"
        adapter.enabled = True
        adapter.is_healthy = True
        adapter._last_success = datetime.now(timezone.utc)
        
        adapter.initialize = AsyncMock()
        adapter.cleanup = AsyncMock()
        adapter.fetch_ticker = AsyncMock(return_value=TickerData(
            symbol="BTC/USDT",
            source="binance",
            last=95001,
            bid=94991,
            ask=95011,
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000)
        ))
        adapter.fetch_candles = AsyncMock(return_value=[
            CandleData(timestamp=(i+1)*3600000, open=95000+i, high=95100+i, low=94900+i, close=95050+i, volume=100)
            for i in range(10)
        ])
        adapter.get_status = MagicMock(return_value={"name": "binance", "healthy": True})
        
        return adapter
    
    @pytest.fixture
    def manager(self, mock_kraken_adapter, mock_binance_adapter):
        """Create manager with mock adapters."""
        from services.data_feed import DataFeedManager, DataFeedConfig
        
        config = DataFeedConfig(
            ticker_cache_seconds=0,  # Disable cache for tests
            candle_cache_seconds=0,
            failover_cooldown_seconds=0,  # No cooldown for tests
        )
        mgr = DataFeedManager(config=config)
        mgr._initialized = True
        mgr._adapters = {
            "kraken": mock_kraken_adapter,
            "binance": mock_binance_adapter,
            "coingecko": MagicMock(enabled=False, is_healthy=False),
        }
        return mgr
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_success(self, manager):
        """Test successful ticker fetch from primary."""
        ticker = await manager.fetch_ticker("BTC/USDT")
        
        assert ticker is not None
        assert ticker.symbol == "BTC/USDT"
        assert ticker.source == "kraken"
        assert ticker.last == 95000
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_fallback(self, manager, mock_kraken_adapter):
        """Test ticker fetch falls back when primary fails."""
        # Make Kraken fail
        mock_kraken_adapter.fetch_ticker = AsyncMock(return_value=None)
        mock_kraken_adapter.is_healthy = False
        
        ticker = await manager.fetch_ticker("BTC/USDT")
        
        assert ticker is not None
        assert ticker.source == "binance"
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_invalid_symbol(self, manager):
        """Test ticker fetch with invalid symbol."""
        ticker = await manager.fetch_ticker("INVALID/PAIR")
        
        assert ticker is None
    
    @pytest.mark.asyncio
    async def test_fetch_candles_success(self, manager):
        """Test successful candles fetch."""
        candles = await manager.fetch_candles("BTC/USDT", "1h", 10)
        
        assert len(candles) == 10
        assert all(c.is_valid for c in candles)
    
    @pytest.mark.asyncio
    async def test_fetch_candles_fallback(self, manager, mock_kraken_adapter):
        """Test candles fetch falls back when primary fails."""
        mock_kraken_adapter.fetch_candles = AsyncMock(return_value=[])
        mock_kraken_adapter.is_healthy = False
        
        candles = await manager.fetch_candles("BTC/USDT", "1h", 10)
        
        assert len(candles) == 10
    
    @pytest.mark.asyncio
    async def test_candle_validation(self, manager, mock_kraken_adapter):
        """Test invalid candles are filtered out."""
        from services.data_feed import CandleData
        
        # Include some invalid candles
        mock_kraken_adapter.fetch_candles = AsyncMock(return_value=[
            CandleData(timestamp=1000, open=100, high=105, low=95, close=102, volume=100),  # Valid
            CandleData(timestamp=2000, open=100, high=90, low=110, close=102, volume=100),  # Invalid - h < l
            CandleData(timestamp=3000, open=100, high=105, low=95, close=102, volume=100),  # Valid
        ])
        
        candles = await manager.fetch_candles("BTC/USDT", "1h", 10)
        
        # Invalid candle should be filtered
        assert len(candles) == 2
    
    @pytest.mark.asyncio
    async def test_staleness_detection(self, manager, mock_kraken_adapter, mock_binance_adapter):
        """Test safe mode when all sources are stale."""
        # Make all adapters return stale data
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_kraken_adapter._last_success = old_time
        mock_kraken_adapter.is_healthy = False
        mock_binance_adapter._last_success = old_time
        mock_binance_adapter.is_healthy = False
        
        manager._adapters["coingecko"]._last_success = old_time
        
        await manager._update_safe_mode()
        
        assert manager.is_safe_mode is True
    
    @pytest.mark.asyncio
    async def test_symbol_normalization(self, manager):
        """Test symbol normalization."""
        # Test various input formats
        assert manager._normalize_symbol("btc/usdt") == "BTC/USDT"
        assert manager._normalize_symbol("BTCUSDT") == "BTC/USDT"
        assert manager._normalize_symbol("  ETH/USD  ") == "ETH/USD"
    
    def test_list_supported_symbols(self, manager):
        """Test listing supported symbols."""
        symbols = manager.list_supported_symbols()
        
        assert len(symbols) > 0
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
    
    def test_is_symbol_supported(self, manager):
        """Test symbol support check."""
        assert manager.is_symbol_supported("BTC/USDT") is True
        assert manager.is_symbol_supported("BTCUSDT") is True  # Normalized
        assert manager.is_symbol_supported("INVALID/PAIR") is False
    
    def test_get_status(self, manager):
        """Test getting manager status."""
        status = manager.get_status()
        
        assert "initialized" in status
        assert "active_source" in status
        assert "safe_mode" in status
        assert "adapters" in status
        assert "cache_stats" in status


# ============ Venue Adapter Tests ============

class TestKrakenAdapter:
    """Tests for KrakenAdapter."""
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_parses_response(self):
        """Test Kraken ticker response parsing."""
        from services.data_feed.venues.kraken import KrakenAdapter
        
        adapter = KrakenAdapter()
        
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "error": [],
            "result": {
                "XBTUSDT": {
                    "c": ["95000.0", "1"],  # last
                    "b": ["94990.0", "10", "1"],  # bid
                    "a": ["95010.0", "5", "1"],  # ask
                    "h": ["96000.0", "95500.0"],  # high
                    "l": ["94000.0", "94500.0"],  # low
                    "v": ["1000.0", "500.0"],  # volume
                    "p": ["95100.0", "95050.0"],  # vwap
                    "t": [100, 50],  # trades
                }
            }
        })
        
        # Patch HTTP client
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(return_value=mock_response)
        
        ticker = await adapter.fetch_ticker("BTC/USDT")
        
        assert ticker is not None
        assert ticker.source == "kraken"
        assert ticker.last == 95000.0
        assert ticker.bid == 94990.0
        assert ticker.ask == 95010.0


class TestBinanceAdapter:
    """Tests for BinanceAdapter."""
    
    @pytest.mark.asyncio
    async def test_fetch_ticker_parses_response(self):
        """Test Binance ticker response parsing."""
        from services.data_feed.venues.binance import BinanceAdapter
        
        adapter = BinanceAdapter()
        
        # Mock 24hr ticker response
        mock_ticker = MagicMock()
        mock_ticker.raise_for_status = MagicMock()
        mock_ticker.json = MagicMock(return_value={
            "lastPrice": "95000.0",
            "highPrice": "96000.0",
            "lowPrice": "94000.0",
            "volume": "1000.0",
            "weightedAvgPrice": "95100.0",
            "count": 100,
            "closeTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        })
        
        # Mock book ticker response
        mock_book = MagicMock()
        mock_book.raise_for_status = MagicMock()
        mock_book.json = MagicMock(return_value={
            "bidPrice": "94990.0",
            "askPrice": "95010.0",
        })
        
        # Patch HTTP client
        adapter._client = MagicMock()
        adapter._client.get = AsyncMock(side_effect=[mock_ticker, mock_book])
        
        ticker = await adapter.fetch_ticker("BTC/USDT")
        
        assert ticker is not None
        assert ticker.source == "binance"
        assert ticker.last == 95000.0
        assert ticker.bid == 94990.0
        assert ticker.ask == 95010.0


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
