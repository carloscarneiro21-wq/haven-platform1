"""Unified Symbol Mapper for Multi-Venue Data Feed.

Provides:
- Internal canonical symbol format (e.g., "BTC/USDT")
- Per-venue symbol mapping (Kraken, Binance, CoinGecko)
- Validation and normalization
- Support for common trading pairs
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class Venue(str, Enum):
    """Supported trading venues."""
    KRAKEN = "kraken"
    BINANCE = "binance"
    COINGECKO = "coingecko"  # Reference/fallback only


class QuoteCurrency(str, Enum):
    """Supported quote currencies."""
    USDT = "USDT"
    USD = "USD"
    EUR = "EUR"
    BTC = "BTC"


@dataclass
class SymbolInfo:
    """Metadata about a trading symbol."""
    internal: str           # Canonical format: "BTC/USDT"
    base: str               # Base currency: "BTC"
    quote: str              # Quote currency: "USDT"
    kraken: str             # Kraken format: "XBTUSDT"
    binance: str            # Binance format: "BTCUSDT"
    coingecko: str          # CoinGecko ID: "bitcoin"
    min_order_size: float   # Minimum order size (in base)
    price_decimals: int     # Price precision
    size_decimals: int      # Size precision
    enabled: bool = True    # Whether symbol is enabled for trading


# ============ SYMBOL REGISTRY ============

# Master symbol registry - single source of truth
SYMBOL_REGISTRY: Dict[str, SymbolInfo] = {
    # Major Crypto vs USDT
    "BTC/USDT": SymbolInfo(
        internal="BTC/USDT", base="BTC", quote="USDT",
        kraken="XBTUSDT", binance="BTCUSDT", coingecko="bitcoin",
        min_order_size=0.0001, price_decimals=1, size_decimals=5
    ),
    "ETH/USDT": SymbolInfo(
        internal="ETH/USDT", base="ETH", quote="USDT",
        kraken="ETHUSDT", binance="ETHUSDT", coingecko="ethereum",
        min_order_size=0.001, price_decimals=2, size_decimals=4
    ),
    "SOL/USDT": SymbolInfo(
        internal="SOL/USDT", base="SOL", quote="USDT",
        kraken="SOLUSDT", binance="SOLUSDT", coingecko="solana",
        min_order_size=0.01, price_decimals=2, size_decimals=3
    ),
    "XRP/USDT": SymbolInfo(
        internal="XRP/USDT", base="XRP", quote="USDT",
        kraken="XRPUSDT", binance="XRPUSDT", coingecko="ripple",
        min_order_size=1.0, price_decimals=4, size_decimals=1
    ),
    "DOGE/USDT": SymbolInfo(
        internal="DOGE/USDT", base="DOGE", quote="USDT",
        kraken="DOGEUSDT", binance="DOGEUSDT", coingecko="dogecoin",
        min_order_size=10.0, price_decimals=5, size_decimals=0
    ),
    "ADA/USDT": SymbolInfo(
        internal="ADA/USDT", base="ADA", quote="USDT",
        kraken="ADAUSDT", binance="ADAUSDT", coingecko="cardano",
        min_order_size=1.0, price_decimals=4, size_decimals=1
    ),
    "AVAX/USDT": SymbolInfo(
        internal="AVAX/USDT", base="AVAX", quote="USDT",
        kraken="AVAXUSDT", binance="AVAXUSDT", coingecko="avalanche-2",
        min_order_size=0.1, price_decimals=2, size_decimals=2
    ),
    "LINK/USDT": SymbolInfo(
        internal="LINK/USDT", base="LINK", quote="USDT",
        kraken="LINKUSDT", binance="LINKUSDT", coingecko="chainlink",
        min_order_size=0.1, price_decimals=3, size_decimals=2
    ),
    "DOT/USDT": SymbolInfo(
        internal="DOT/USDT", base="DOT", quote="USDT",
        kraken="DOTUSDT", binance="DOTUSDT", coingecko="polkadot",
        min_order_size=0.1, price_decimals=3, size_decimals=2
    ),
    "MATIC/USDT": SymbolInfo(
        internal="MATIC/USDT", base="MATIC", quote="USDT",
        kraken="MATICUSDT", binance="MATICUSDT", coingecko="matic-network",
        min_order_size=1.0, price_decimals=4, size_decimals=1
    ),
    
    # Major Crypto vs USD (Kraken native)
    "BTC/USD": SymbolInfo(
        internal="BTC/USD", base="BTC", quote="USD",
        kraken="XXBTZUSD", binance="BTCUSD", coingecko="bitcoin",
        min_order_size=0.0001, price_decimals=1, size_decimals=5
    ),
    "ETH/USD": SymbolInfo(
        internal="ETH/USD", base="ETH", quote="USD",
        kraken="XETHZUSD", binance="ETHUSD", coingecko="ethereum",
        min_order_size=0.001, price_decimals=2, size_decimals=4
    ),
    "SOL/USD": SymbolInfo(
        internal="SOL/USD", base="SOL", quote="USD",
        kraken="SOLUSD", binance="SOLUSD", coingecko="solana",
        min_order_size=0.01, price_decimals=2, size_decimals=3
    ),
    
    # EUR pairs (Kraken strong suit)
    "BTC/EUR": SymbolInfo(
        internal="BTC/EUR", base="BTC", quote="EUR",
        kraken="XXBTZEUR", binance="BTCEUR", coingecko="bitcoin",
        min_order_size=0.0001, price_decimals=1, size_decimals=5
    ),
    "ETH/EUR": SymbolInfo(
        internal="ETH/EUR", base="ETH", quote="EUR",
        kraken="XETHZEUR", binance="ETHEUR", coingecko="ethereum",
        min_order_size=0.001, price_decimals=2, size_decimals=4
    ),
}


class SymbolMapper:
    """Maps between internal canonical format and venue-specific formats."""
    
    def __init__(self):
        self._internal_to_info: Dict[str, SymbolInfo] = SYMBOL_REGISTRY.copy()
        
        # Build reverse lookup maps for each venue
        self._kraken_to_internal: Dict[str, str] = {}
        self._binance_to_internal: Dict[str, str] = {}
        self._coingecko_to_internal: Dict[str, str] = {}
        
        self._rebuild_reverse_maps()
        
    def _rebuild_reverse_maps(self):
        """Rebuild reverse lookup maps."""
        self._kraken_to_internal.clear()
        self._binance_to_internal.clear()
        self._coingecko_to_internal.clear()
        
        for internal, info in self._internal_to_info.items():
            self._kraken_to_internal[info.kraken] = internal
            self._kraken_to_internal[info.kraken.upper()] = internal
            self._kraken_to_internal[info.kraken.lower()] = internal
            
            self._binance_to_internal[info.binance] = internal
            self._binance_to_internal[info.binance.upper()] = internal
            self._binance_to_internal[info.binance.lower()] = internal
            
            self._coingecko_to_internal[info.coingecko] = internal
            self._coingecko_to_internal[info.coingecko.lower()] = internal
    
    def get_info(self, internal: str) -> Optional[SymbolInfo]:
        """Get symbol info by internal format."""
        # Normalize input
        normalized = self._normalize_internal(internal)
        return self._internal_to_info.get(normalized)
    
    def _normalize_internal(self, symbol: str) -> str:
        """Normalize an internal symbol format."""
        # Handle common variations
        symbol = symbol.upper().strip()
        
        # Handle no-slash formats (BTCUSDT -> BTC/USDT)
        if "/" not in symbol:
            for quote in ["USDT", "USD", "EUR", "BTC"]:
                if symbol.endswith(quote):
                    base = symbol[:-len(quote)]
                    return f"{base}/{quote}"
        
        return symbol
    
    def to_venue(self, internal: str, venue: Venue) -> Optional[str]:
        """Convert internal symbol to venue-specific format."""
        info = self.get_info(internal)
        if not info:
            logger.warning(f"Unknown symbol: {internal}")
            return None
            
        if venue == Venue.KRAKEN:
            return info.kraken
        elif venue == Venue.BINANCE:
            return info.binance
        elif venue == Venue.COINGECKO:
            return info.coingecko
        else:
            return None
    
    def from_venue(self, venue_symbol: str, venue: Venue) -> Optional[str]:
        """Convert venue-specific symbol to internal format."""
        venue_symbol = venue_symbol.strip()
        
        if venue == Venue.KRAKEN:
            return self._kraken_to_internal.get(venue_symbol) or \
                   self._kraken_to_internal.get(venue_symbol.upper())
        elif venue == Venue.BINANCE:
            return self._binance_to_internal.get(venue_symbol) or \
                   self._binance_to_internal.get(venue_symbol.upper())
        elif venue == Venue.COINGECKO:
            return self._coingecko_to_internal.get(venue_symbol) or \
                   self._coingecko_to_internal.get(venue_symbol.lower())
        
        return None
    
    def is_valid(self, internal: str) -> bool:
        """Check if symbol is valid and supported."""
        info = self.get_info(internal)
        return info is not None and info.enabled
    
    def list_symbols(self, quote: Optional[str] = None, enabled_only: bool = True) -> List[str]:
        """List all supported internal symbols."""
        symbols = []
        for internal, info in self._internal_to_info.items():
            if enabled_only and not info.enabled:
                continue
            if quote and info.quote != quote:
                continue
            symbols.append(internal)
        return sorted(symbols)
    
    def list_for_venue(self, venue: Venue, enabled_only: bool = True) -> List[str]:
        """List all venue-specific symbols."""
        result = []
        for internal, info in self._internal_to_info.items():
            if enabled_only and not info.enabled:
                continue
            venue_symbol = self.to_venue(internal, venue)
            if venue_symbol:
                result.append(venue_symbol)
        return result
    
    def get_precision(self, internal: str) -> Tuple[int, int]:
        """Get (price_decimals, size_decimals) for a symbol."""
        info = self.get_info(internal)
        if info:
            return (info.price_decimals, info.size_decimals)
        return (2, 4)  # Default
    
    def round_price(self, internal: str, price: float) -> float:
        """Round price to correct precision for symbol."""
        info = self.get_info(internal)
        decimals = info.price_decimals if info else 2
        return round(price, decimals)
    
    def round_size(self, internal: str, size: float) -> float:
        """Round size to correct precision for symbol."""
        info = self.get_info(internal)
        decimals = info.size_decimals if info else 4
        return round(size, decimals)
    
    def validate_order_size(self, internal: str, size: float) -> Tuple[bool, str]:
        """Validate order size against minimum."""
        info = self.get_info(internal)
        if not info:
            return False, f"Unknown symbol: {internal}"
        
        if size < info.min_order_size:
            return False, f"Size {size} below minimum {info.min_order_size}"
        
        return True, ""
    
    def add_symbol(self, info: SymbolInfo):
        """Add a new symbol to the registry."""
        self._internal_to_info[info.internal] = info
        self._rebuild_reverse_maps()
        logger.info(f"Added symbol: {info.internal}")
    
    def disable_symbol(self, internal: str):
        """Disable a symbol (soft delete)."""
        info = self.get_info(internal)
        if info:
            info.enabled = False
            logger.info(f"Disabled symbol: {internal}")
    
    def enable_symbol(self, internal: str):
        """Enable a previously disabled symbol."""
        info = self.get_info(internal)
        if info:
            info.enabled = True
            logger.info(f"Enabled symbol: {internal}")


# ============ TIMEFRAME MAPPING ============

@dataclass
class TimeframeInfo:
    """Metadata about a timeframe."""
    internal: str       # Canonical: "1h"
    seconds: int        # Duration in seconds
    kraken: int         # Kraken interval parameter
    binance: str        # Binance interval string


TIMEFRAME_REGISTRY: Dict[str, TimeframeInfo] = {
    "1m": TimeframeInfo(internal="1m", seconds=60, kraken=1, binance="1m"),
    "5m": TimeframeInfo(internal="5m", seconds=300, kraken=5, binance="5m"),
    "15m": TimeframeInfo(internal="15m", seconds=900, kraken=15, binance="15m"),
    "30m": TimeframeInfo(internal="30m", seconds=1800, kraken=30, binance="30m"),
    "1h": TimeframeInfo(internal="1h", seconds=3600, kraken=60, binance="1h"),
    "4h": TimeframeInfo(internal="4h", seconds=14400, kraken=240, binance="4h"),
    "1d": TimeframeInfo(internal="1d", seconds=86400, kraken=1440, binance="1d"),
}


class TimeframeMapper:
    """Maps between internal timeframe format and venue-specific formats."""
    
    def __init__(self):
        self._registry = TIMEFRAME_REGISTRY.copy()
    
    def get_info(self, internal: str) -> Optional[TimeframeInfo]:
        """Get timeframe info by internal format."""
        return self._registry.get(internal.lower())
    
    def to_venue(self, internal: str, venue: Venue) -> Optional[int | str]:
        """Convert internal timeframe to venue-specific format."""
        info = self.get_info(internal)
        if not info:
            return None
            
        if venue == Venue.KRAKEN:
            return info.kraken
        elif venue == Venue.BINANCE:
            return info.binance
        
        return None
    
    def get_seconds(self, internal: str) -> int:
        """Get timeframe duration in seconds."""
        info = self.get_info(internal)
        return info.seconds if info else 3600  # Default 1h
    
    def list_timeframes(self) -> List[str]:
        """List all supported timeframes."""
        return list(self._registry.keys())


# ============ GLOBAL INSTANCES ============

# Singleton instances
_symbol_mapper: Optional[SymbolMapper] = None
_timeframe_mapper: Optional[TimeframeMapper] = None


def get_symbol_mapper() -> SymbolMapper:
    """Get singleton symbol mapper."""
    global _symbol_mapper
    if _symbol_mapper is None:
        _symbol_mapper = SymbolMapper()
    return _symbol_mapper


def get_timeframe_mapper() -> TimeframeMapper:
    """Get singleton timeframe mapper."""
    global _timeframe_mapper
    if _timeframe_mapper is None:
        _timeframe_mapper = TimeframeMapper()
    return _timeframe_mapper
