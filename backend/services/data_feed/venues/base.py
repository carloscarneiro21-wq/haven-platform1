"""Base class for venue-specific data feed adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class TickerData:
    """Normalized ticker data."""
    symbol: str              # Internal format
    source: str              # Venue name
    last: float = 0.0        # Last trade price
    bid: float = 0.0         # Best bid
    ask: float = 0.0         # Best ask
    high_24h: float = 0.0    # 24h high
    low_24h: float = 0.0     # 24h low
    volume_24h: float = 0.0  # 24h volume (in base currency)
    vwap_24h: float = 0.0    # 24h VWAP
    trades_24h: int = 0      # 24h trade count
    timestamp: int = 0       # Unix timestamp (ms)
    
    @property
    def spread(self) -> float:
        """Calculate spread."""
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return 0.0
    
    @property
    def spread_pct(self) -> float:
        """Calculate spread percentage."""
        if self.bid > 0 and self.ask > 0:
            mid = (self.bid + self.ask) / 2
            return (self.spread / mid) * 100
        return 0.0
    
    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last
    
    @property
    def is_valid(self) -> bool:
        """Check if ticker data is valid."""
        return self.last > 0 and (self.bid > 0 or self.ask > 0)
    
    @property
    def age_seconds(self) -> float:
        """Age of data in seconds."""
        if self.timestamp <= 0:
            return float('inf')
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return (now_ms - self.timestamp) / 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "source": self.source,
            "last": self.last,
            "bid": self.bid,
            "ask": self.ask,
            "high": self.high_24h,
            "low": self.low_24h,
            "volume": self.volume_24h,
            "vwap": self.vwap_24h,
            "trades": self.trades_24h,
            "timestamp": self.timestamp,
            "spread_pct": round(self.spread_pct, 4),
            "mid_price": self.mid_price,
        }


@dataclass
class CandleData:
    """Normalized OHLCV candle data."""
    timestamp: int           # Unix timestamp (ms)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    
    @property
    def is_valid(self) -> bool:
        """Check if candle data is valid."""
        return (
            self.high >= self.low and
            self.high >= max(self.open, self.close) and
            self.low <= min(self.open, self.close) and
            all(p > 0 for p in [self.open, self.high, self.low, self.close]) and
            self.volume >= 0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class OrderBookData:
    """Normalized order book data."""
    symbol: str
    source: str
    bids: List[List[float]] = field(default_factory=list)  # [[price, size], ...]
    asks: List[List[float]] = field(default_factory=list)  # [[price, size], ...]
    timestamp: int = 0
    
    @property
    def best_bid(self) -> float:
        """Get best bid price."""
        return self.bids[0][0] if self.bids else 0.0
    
    @property
    def best_ask(self) -> float:
        """Get best ask price."""
        return self.asks[0][0] if self.asks else 0.0
    
    @property
    def spread(self) -> float:
        """Calculate spread."""
        if self.best_bid > 0 and self.best_ask > 0:
            return self.best_ask - self.best_bid
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "source": self.source,
            "bids": self.bids,
            "asks": self.asks,
            "timestamp": self.timestamp,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
        }


class VenueAdapter(ABC):
    """Base class for venue-specific data feed adapters."""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self._last_success: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._consecutive_failures = 0
        self._total_requests = 0
        self._total_errors = 0
    
    @abstractmethod
    async def initialize(self):
        """Initialize the adapter (create HTTP client, etc)."""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup resources."""
        pass
    
    @abstractmethod
    async def fetch_ticker(self, internal_symbol: str) -> Optional[TickerData]:
        """Fetch ticker for a symbol."""
        pass
    
    @abstractmethod
    async def fetch_candles(
        self, 
        internal_symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[CandleData]:
        """Fetch OHLCV candles."""
        pass
    
    @abstractmethod
    async def fetch_orderbook(
        self, 
        internal_symbol: str, 
        limit: int = 20
    ) -> Optional[OrderBookData]:
        """Fetch order book."""
        pass
    
    def record_success(self):
        """Record a successful request."""
        self._last_success = datetime.now(timezone.utc)
        self._last_error = None
        self._consecutive_failures = 0
        self._total_requests += 1
    
    def record_error(self, error: str):
        """Record a failed request."""
        self._last_error = error
        self._consecutive_failures += 1
        self._total_requests += 1
        self._total_errors += 1
    
    @property
    def is_healthy(self) -> bool:
        """Check if adapter is healthy."""
        if not self.enabled:
            return False
        if self._consecutive_failures >= 5:
            return False
        return True
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        if self._total_requests == 0:
            return 0.0
        return self._total_errors / self._total_requests
    
    def get_status(self) -> Dict[str, Any]:
        """Get adapter status."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "healthy": self.is_healthy,
            "last_success": self._last_success.isoformat() if self._last_success else None,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "total_requests": self._total_requests,
            "error_rate": round(self.error_rate, 4),
        }
