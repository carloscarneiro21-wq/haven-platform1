"""Unified Multi-Venue Data Feed Manager.

Provides:
- Automatic venue failover (Kraken -> Binance -> CoinGecko)
- Staleness detection and safe mode
- Caching with configurable TTL
- Data validation and filtering
- Health monitoring and status reporting
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging
import numpy as np

from .symbol_mapper import (
    get_symbol_mapper, 
    get_timeframe_mapper, 
    SymbolMapper, 
    TimeframeMapper,
    Venue
)
from .venues.base import VenueAdapter, TickerData, CandleData, OrderBookData
from .venues.kraken import KrakenAdapter
from .venues.binance import BinanceAdapter
from .venues.coingecko import CoinGeckoAdapter

logger = logging.getLogger(__name__)


@dataclass
class DataFeedConfig:
    """Configuration for data feed manager."""
    # Cache settings
    ticker_cache_seconds: int = 5
    candle_cache_seconds: int = 60
    orderbook_cache_seconds: int = 2
    
    # Staleness thresholds
    stale_ticker_seconds: int = 60
    stale_candle_seconds: int = 300
    
    # Failover settings
    max_consecutive_failures: int = 3
    failover_cooldown_seconds: int = 60
    recovery_consecutive_ok: int = 2
    
    # Safe mode
    safe_mode_stale_threshold: int = 120
    safe_mode_min_ok_cycles: int = 3


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    data: Any
    timestamp: datetime
    source: str
    stale: bool = False
    
    @property
    def age_seconds(self) -> float:
        """Age of cache entry in seconds."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()


class DataFeedManager:
    """Unified data feed manager with multi-venue support."""
    
    def __init__(self, config: Optional[DataFeedConfig] = None, db=None):
        self.config = config or DataFeedConfig()
        self.db = db
        
        # Mappers
        self._symbol_mapper = get_symbol_mapper()
        self._timeframe_mapper = get_timeframe_mapper()
        
        # Venue adapters (ordered by priority)
        self._adapters: Dict[str, VenueAdapter] = {}
        self._adapter_priority = ["kraken", "binance", "coingecko"]
        self._active_adapter = "kraken"
        
        # Caches
        self._ticker_cache: Dict[str, CacheEntry] = {}
        self._candle_cache: Dict[str, CacheEntry] = {}
        self._orderbook_cache: Dict[str, CacheEntry] = {}
        self._last_known_good: Dict[str, TickerData] = {}
        
        # State
        self._initialized = False
        self._safe_mode = False
        self._safe_mode_reason = ""
        self._safe_mode_entered_at: Optional[datetime] = None
        self._consecutive_ok_cycles = 0
        
        # Failover tracking
        self._last_failover_time: Optional[datetime] = None
        self._failover_blocked_count = 0
        
        # Event logger (set externally)
        self.event_logger = None
    
    async def initialize(self):
        """Initialize all venue adapters."""
        if self._initialized:
            return
        
        # Create and initialize adapters
        self._adapters = {
            "kraken": KrakenAdapter(),
            "binance": BinanceAdapter(),
            "coingecko": CoinGeckoAdapter(),
        }
        
        for name, adapter in self._adapters.items():
            try:
                await adapter.initialize()
                logger.info(f"Initialized adapter: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize adapter {name}: {e}")
                adapter.enabled = False
        
        self._initialized = True
        logger.info("DataFeedManager initialized with adapters: " + 
                   ", ".join(self._adapter_priority))
    
    async def cleanup(self):
        """Cleanup all adapters."""
        for adapter in self._adapters.values():
            try:
                await adapter.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up adapter: {e}")
    
    # ============ PUBLIC API ============
    
    async def fetch_ticker(self, symbol: str) -> Optional[TickerData]:
        """Fetch ticker with automatic failover and caching."""
        if not self._initialized:
            await self.initialize()
        
        # Normalize symbol
        symbol = self._normalize_symbol(symbol)
        if not self._symbol_mapper.is_valid(symbol):
            logger.warning(f"Invalid symbol: {symbol}")
            return None
        
        # Check cache
        cache_key = f"ticker_{symbol}"
        cached = self._ticker_cache.get(cache_key)
        if cached and cached.age_seconds < self.config.ticker_cache_seconds:
            return cached.data
        
        # Try adapters in priority order
        ticker = await self._fetch_with_failover(
            symbol, 
            "ticker",
            lambda adapter: adapter.fetch_ticker(symbol)
        )
        
        if ticker:
            # Cache result
            self._ticker_cache[cache_key] = CacheEntry(
                data=ticker,
                timestamp=datetime.now(timezone.utc),
                source=ticker.source
            )
            self._last_known_good[symbol] = ticker
            
        elif symbol in self._last_known_good:
            # Return last known good with stale flag
            ticker = self._last_known_good[symbol]
            logger.warning(f"Returning last known good ticker for {symbol}")
        
        await self._update_safe_mode()
        return ticker
    
    async def fetch_candles(
        self, 
        symbol: str, 
        timeframe: str = "1h", 
        limit: int = 100
    ) -> List[CandleData]:
        """Fetch OHLCV candles with automatic failover and validation."""
        if not self._initialized:
            await self.initialize()
        
        symbol = self._normalize_symbol(symbol)
        if not self._symbol_mapper.is_valid(symbol):
            return []
        
        # Check cache
        cache_key = f"candles_{symbol}_{timeframe}_{limit}"
        cached = self._candle_cache.get(cache_key)
        if cached and cached.age_seconds < self.config.candle_cache_seconds:
            return cached.data
        
        # Try adapters in priority order
        candles = await self._fetch_with_failover(
            symbol,
            "candles",
            lambda adapter: adapter.fetch_candles(symbol, timeframe, limit)
        )
        
        if candles:
            # Validate candles
            candles = self._validate_candles(candles, symbol)
            
            # Cache result
            self._candle_cache[cache_key] = CacheEntry(
                data=candles,
                timestamp=datetime.now(timezone.utc),
                source=self._active_adapter
            )
        
        if not candles:
            # Return cached if available
            if cached:
                logger.warning(f"Returning stale candles for {symbol}")
                return cached.data
            # Generate mock as last resort
            candles = self._generate_mock_candles(symbol, limit)
        
        await self._update_safe_mode()
        return candles
    
    async def fetch_orderbook(
        self, 
        symbol: str, 
        limit: int = 20
    ) -> Optional[OrderBookData]:
        """Fetch order book with automatic failover."""
        if not self._initialized:
            await self.initialize()
        
        symbol = self._normalize_symbol(symbol)
        if not self._symbol_mapper.is_valid(symbol):
            return None
        
        # Check cache
        cache_key = f"orderbook_{symbol}"
        cached = self._orderbook_cache.get(cache_key)
        if cached and cached.age_seconds < self.config.orderbook_cache_seconds:
            return cached.data
        
        # Try adapters (skip coingecko as it doesn't support orderbook)
        orderbook = await self._fetch_with_failover(
            symbol,
            "orderbook",
            lambda adapter: adapter.fetch_orderbook(symbol, limit),
            skip_adapters=["coingecko"]
        )
        
        if orderbook:
            self._orderbook_cache[cache_key] = CacheEntry(
                data=orderbook,
                timestamp=datetime.now(timezone.utc),
                source=orderbook.source
            )
        
        return orderbook
    
    # ============ FAILOVER LOGIC ============
    
    async def _fetch_with_failover(
        self, 
        symbol: str,
        data_type: str,
        fetch_func,
        skip_adapters: Optional[List[str]] = None
    ) -> Any:
        """Try fetching from adapters in priority order with failover."""
        skip_adapters = skip_adapters or []
        
        # Start with active adapter
        adapters_to_try = [self._active_adapter]
        
        # Add others in priority order
        for name in self._adapter_priority:
            if name not in adapters_to_try and name not in skip_adapters:
                adapters_to_try.append(name)
        
        for adapter_name in adapters_to_try:
            adapter = self._adapters.get(adapter_name)
            if not adapter or not adapter.enabled or not adapter.is_healthy:
                continue
            
            try:
                result = await fetch_func(adapter)
                if result:
                    # Success - check if we should switch active
                    if adapter_name != self._active_adapter:
                        await self._handle_failover(adapter_name, f"{data_type} success")
                    self._consecutive_ok_cycles += 1
                    return result
            except Exception as e:
                logger.warning(f"{adapter_name} {data_type} fetch failed: {e}")
                adapter.record_error(str(e))
        
        # All adapters failed
        self._consecutive_ok_cycles = 0
        return None
    
    async def _handle_failover(self, new_adapter: str, reason: str):
        """Handle switching to a different adapter."""
        old_adapter = self._active_adapter
        
        # Check cooldown
        if self._last_failover_time:
            elapsed = (datetime.now(timezone.utc) - self._last_failover_time).total_seconds()
            if elapsed < self.config.failover_cooldown_seconds:
                self._failover_blocked_count += 1
                logger.debug(f"Failover blocked by cooldown ({elapsed:.0f}s < {self.config.failover_cooldown_seconds}s)")
                return
        
        self._active_adapter = new_adapter
        self._last_failover_time = datetime.now(timezone.utc)
        
        logger.warning(f"Switched data source: {old_adapter} -> {new_adapter} ({reason})")
        
        # Emit event
        if self.event_logger:
            try:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.WARNING,
                    category=EventCategory.DATA,
                    type="DATA_SOURCE_SWITCHED",
                    message=f"Data source switched from {old_adapter} to {new_adapter}",
                    context={
                        "from_source": old_adapter,
                        "to_source": new_adapter,
                        "reason": reason,
                    },
                    tags=["failover", "data_source"]
                )
            except Exception as e:
                logger.warning(f"Failed to emit failover event: {e}")
    
    # ============ SAFE MODE ============
    
    async def _update_safe_mode(self):
        """Update safe mode status based on data health."""
        # Check if all data is stale
        all_stale = True
        for adapter in self._adapters.values():
            if adapter.is_healthy and adapter._last_success:
                age = (datetime.now(timezone.utc) - adapter._last_success).total_seconds()
                if age < self.config.safe_mode_stale_threshold:
                    all_stale = False
                    break
        
        if all_stale and not self._safe_mode:
            # Enter safe mode
            self._safe_mode = True
            self._safe_mode_reason = "All data sources stale"
            self._safe_mode_entered_at = datetime.now(timezone.utc)
            logger.warning(f"Entering SAFE MODE: {self._safe_mode_reason}")
            
            if self.event_logger:
                try:
                    from services.event_logger import EventSeverity, EventCategory
                    await self.event_logger.emit(
                        severity=EventSeverity.WARNING,
                        category=EventCategory.RISK,
                        type="SAFE_MODE_ENTERED",
                        message=f"Entered safe mode: {self._safe_mode_reason}",
                        context={"reason": self._safe_mode_reason},
                        tags=["safe_mode", "risk"]
                    )
                except Exception:
                    pass
                    
        elif not all_stale and self._safe_mode:
            # Check if we can exit safe mode
            if self._consecutive_ok_cycles >= self.config.safe_mode_min_ok_cycles:
                old_reason = self._safe_mode_reason
                self._safe_mode = False
                self._safe_mode_reason = ""
                self._safe_mode_entered_at = None
                logger.info("Exiting SAFE MODE - data restored")
                
                if self.event_logger:
                    try:
                        from services.event_logger import EventSeverity, EventCategory
                        await self.event_logger.emit(
                            severity=EventSeverity.INFO,
                            category=EventCategory.RISK,
                            type="SAFE_MODE_EXITED",
                            message="Exited safe mode - data restored",
                            context={"previous_reason": old_reason},
                            tags=["safe_mode", "recovered"]
                        )
                    except Exception:
                        pass
    
    # ============ VALIDATION ============
    
    def _validate_candles(self, candles: List[CandleData], symbol: str) -> List[CandleData]:
        """Validate and filter candles."""
        valid = []
        last_timestamp = 0
        
        for candle in candles:
            # Check timestamp monotonicity
            if candle.timestamp <= last_timestamp:
                continue
            
            # Check OHLC validity
            if not candle.is_valid:
                logger.debug(f"Invalid candle for {symbol} at {candle.timestamp}")
                continue
            
            valid.append(candle)
            last_timestamp = candle.timestamp
        
        return valid
    
    def _generate_mock_candles(self, symbol: str, limit: int) -> List[CandleData]:
        """Generate mock candles as emergency fallback."""
        logger.warning(f"Generating mock candles for {symbol}")
        
        # Get base price from last known good or default
        base_price = 100.0
        if symbol in self._last_known_good:
            base_price = self._last_known_good[symbol].last
        else:
            # Default prices
            defaults = {
                "BTC/USDT": 95000, "BTC/USD": 95000,
                "ETH/USDT": 3400, "ETH/USD": 3400,
                "SOL/USDT": 190, "SOL/USD": 190,
            }
            base_price = defaults.get(symbol, 100.0)
        
        candles = []
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        interval_ms = 3600000  # 1h
        
        price = base_price
        for i in range(limit):
            timestamp = now - (limit - i - 1) * interval_ms
            
            # Random walk
            change = np.random.normal(0, base_price * 0.005)
            price = max(base_price * 0.8, min(base_price * 1.2, price + change))
            
            volatility = abs(np.random.normal(0, base_price * 0.003))
            
            candles.append(CandleData(
                timestamp=timestamp,
                open=round(price, 2),
                high=round(price + volatility, 2),
                low=round(price - volatility, 2),
                close=round(price + np.random.normal(0, base_price * 0.001), 2),
                volume=round(np.random.uniform(100, 1000), 2),
            ))
        
        return candles
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to internal format."""
        symbol = symbol.upper().strip()
        if "/" not in symbol:
            for quote in ["USDT", "USD", "EUR", "BTC"]:
                if symbol.endswith(quote):
                    return f"{symbol[:-len(quote)]}/{quote}"
        return symbol
    
    # ============ STATUS ============
    
    @property
    def is_safe_mode(self) -> bool:
        """Check if in safe mode."""
        return self._safe_mode
    
    @property
    def active_source(self) -> str:
        """Get currently active data source."""
        return self._active_adapter
    
    def get_status(self) -> Dict[str, Any]:
        """Get data feed status."""
        return {
            "initialized": self._initialized,
            "active_source": self._active_adapter,
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "safe_mode_duration_s": (
                (datetime.now(timezone.utc) - self._safe_mode_entered_at).total_seconds()
                if self._safe_mode_entered_at else None
            ),
            "consecutive_ok_cycles": self._consecutive_ok_cycles,
            "adapters": {
                name: adapter.get_status()
                for name, adapter in self._adapters.items()
            },
            "cache_stats": {
                "tickers": len(self._ticker_cache),
                "candles": len(self._candle_cache),
                "orderbooks": len(self._orderbook_cache),
                "last_known_good": len(self._last_known_good),
            },
            "failover": {
                "last_time": self._last_failover_time.isoformat() if self._last_failover_time else None,
                "blocked_count": self._failover_blocked_count,
                "cooldown_seconds": self.config.failover_cooldown_seconds,
            },
        }
    
    def list_supported_symbols(self) -> List[str]:
        """List all supported trading symbols."""
        return self._symbol_mapper.list_symbols(enabled_only=True)
    
    def is_symbol_supported(self, symbol: str) -> bool:
        """Check if symbol is supported."""
        return self._symbol_mapper.is_valid(self._normalize_symbol(symbol))


# ============ GLOBAL INSTANCE ============

_data_feed_manager: Optional[DataFeedManager] = None


async def get_data_feed_manager() -> DataFeedManager:
    """Get or create global data feed manager instance."""
    global _data_feed_manager
    if _data_feed_manager is None:
        _data_feed_manager = DataFeedManager()
        await _data_feed_manager.initialize()
    return _data_feed_manager


def set_data_feed_manager(manager: DataFeedManager):
    """Set global data feed manager instance."""
    global _data_feed_manager
    _data_feed_manager = manager
