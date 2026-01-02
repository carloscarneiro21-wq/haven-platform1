"""Data Feed Module - Unified market data with multi-venue support.

Exports:
- DataFeedManager: New modular data feed manager (recommended)
- DataFeed: Legacy-compatible interface (use for existing code)
- SymbolMapper, TimeframeMapper: Symbol/timeframe conversion utilities
- Venue adapters: KrakenAdapter, BinanceAdapter, CoinGeckoAdapter
"""

from .symbol_mapper import (
    SymbolMapper,
    TimeframeMapper,
    SymbolInfo,
    TimeframeInfo,
    Venue,
    QuoteCurrency,
    get_symbol_mapper,
    get_timeframe_mapper,
    SYMBOL_REGISTRY,
    TIMEFRAME_REGISTRY,
)

from .manager import (
    DataFeedManager,
    DataFeedConfig,
    get_data_feed_manager,
    set_data_feed_manager,
)

from .venues.base import (
    VenueAdapter,
    TickerData,
    CandleData,
    OrderBookData,
)

from .venues.kraken import KrakenAdapter
from .venues.binance import BinanceAdapter
from .venues.coingecko import CoinGeckoAdapter

# Legacy compatibility
from .compat import (
    DataFeed,
    Candle,
    get_data_feed,
    set_data_feed,
    create_data_feed,
)

__all__ = [
    # Core classes
    "DataFeedManager",
    "DataFeedConfig",
    "get_data_feed_manager",
    "set_data_feed_manager",
    
    # Symbol mapping
    "SymbolMapper",
    "TimeframeMapper",
    "SymbolInfo",
    "TimeframeInfo",
    "Venue",
    "QuoteCurrency",
    "get_symbol_mapper",
    "get_timeframe_mapper",
    "SYMBOL_REGISTRY",
    "TIMEFRAME_REGISTRY",
    
    # Data types
    "VenueAdapter",
    "TickerData",
    "CandleData",
    "OrderBookData",
    
    # Venue adapters
    "KrakenAdapter",
    "BinanceAdapter",
    "CoinGeckoAdapter",
    
    # Legacy compatibility
    "DataFeed",
    "Candle",
    "get_data_feed",
    "set_data_feed",
    "create_data_feed",
]
