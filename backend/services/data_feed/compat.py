"""DataFeed Compatibility Adapter.

This module provides backward compatibility for services that use the older DataFeed API
while internally using the new modular DataFeedManager.

Usage:
1. Import from data_feed.compat for backward-compatible interface
2. Use the same interface - all methods are compatible
3. For new code, use DataFeedManager directly
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import numpy as np

from .manager import DataFeedManager, DataFeedConfig
from .venues.base import TickerData, CandleData, OrderBookData
from models.trading import MarketFeatures

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """Candle format for backward compatibility."""
    timestamp: int  # ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class HealthAdapter:
    """Adapter for DataFeedHealth interface."""
    
    def __init__(self, manager: DataFeedManager):
        self._manager = manager
        self._event_logger = None
        
    def set_event_logger(self, event_logger):
        """Set event logger for events."""
        self._event_logger = event_logger
        self._manager.event_logger = event_logger
        
    def get_active_source(self) -> str:
        """Get currently active data source."""
        return self._manager.active_source
    
    def is_data_stale(self) -> bool:
        """Check if data is stale."""
        return self._manager.is_safe_mode
    
    def get_status(self) -> Dict[str, Any]:
        """Get health status in backward-compatible format."""
        manager_status = self._manager.get_status()
        return {
            "ok": not manager_status.get("safe_mode", False),
            "using_fallback": manager_status.get("active_source") != "kraken",
            "fallback_reason": manager_status.get("safe_mode_reason", ""),
            "active_source": manager_status.get("active_source"),
            "adapters": manager_status.get("adapters", {}),
        }
    
    async def emit_pending_events(self):
        """Emit pending events (for compatibility)."""
        pass  # New manager handles this internally


class DataFeed:
    """
    Legacy-compatible DataFeed using the new modular DataFeedManager.
    
    This is a drop-in replacement that provides the same interface
    while leveraging the improved multi-venue data feed system.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase = None):
        self.db = db
        self._manager = DataFeedManager(db=db)
        self.health = HealthAdapter(self._manager)
        
        # Feature cache
        self.feature_cache: Dict[str, MarketFeatures] = {}
        self._feature_cache_time: Dict[str, datetime] = {}
        self._feature_cache_duration = timedelta(seconds=30)
        
        # Safe mode proxies to manager
        self.event_logger = None
        
        # Stress mode (for testing)
        self.stress_mode = False
        
    @property
    def safe_mode(self) -> bool:
        """Check if in safe mode."""
        return self._manager.is_safe_mode
    
    @property
    def safe_mode_reason(self) -> str:
        """Get safe mode reason."""
        status = self._manager.get_status()
        return status.get("safe_mode_reason", "")
    
    async def initialize(self):
        """Initialize the data feed."""
        await self._manager.initialize()
        
        # Set event logger if provided
        if self.event_logger:
            self._manager.event_logger = self.event_logger
            self.health.set_event_logger(self.event_logger)
            
        logger.info("DataFeed (compat adapter) initialized")
        
    async def cleanup(self):
        """Cleanup resources."""
        await self._manager.cleanup()
        
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch ticker data for a symbol.
        
        Returns dict with: symbol, source, last, bid, ask, high, low, volume, timestamp
        """
        ticker: Optional[TickerData] = await self._manager.fetch_ticker(symbol)
        
        if not ticker:
            return {}
        
        return {
            "symbol": symbol,
            "source": ticker.source,
            "last": ticker.last,
            "bid": ticker.bid,
            "ask": ticker.ask,
            "high": ticker.high_24h or ticker.last,
            "low": ticker.low_24h or ticker.last,
            "volume": ticker.volume_24h or 0,
            "vwap": ticker.vwap_24h or ticker.last,
            "timestamp": ticker.timestamp,
        }
    
    async def fetch_candles(
        self, 
        symbol: str, 
        timeframe: str = "1h", 
        limit: int = 100
    ) -> List[Candle]:
        """
        Fetch OHLCV candles for a symbol.
        
        Returns list of Candle objects.
        """
        candle_data: List[CandleData] = await self._manager.fetch_candles(
            symbol, timeframe, limit
        )
        
        return [
            Candle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in candle_data
        ]
    
    async def get_orderbook(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        """
        Fetch orderbook for a symbol.
        
        Returns dict with: bids, asks (as [price, size] arrays)
        """
        orderbook: Optional[OrderBookData] = await self._manager.fetch_orderbook(
            symbol, depth
        )
        
        if not orderbook:
            return {"bids": [], "asks": []}
        
        return {
            "bids": orderbook.bids[:depth],
            "asks": orderbook.asks[:depth],
            "source": orderbook.source,
            "timestamp": orderbook.timestamp,
        }
    
    async def calculate_features(self, symbol: str) -> Optional[MarketFeatures]:
        """
        Calculate market features from candle data.
        
        Returns MarketFeatures object with regime, volatility, momentum, etc.
        """
        # Check cache
        cache_key = symbol
        if cache_key in self.feature_cache:
            cache_time = self._feature_cache_time.get(cache_key)
            if cache_time and (datetime.now(timezone.utc) - cache_time) < self._feature_cache_duration:
                return self.feature_cache[cache_key]
        
        # Fetch candles
        candles = await self.fetch_candles(symbol, "1h", 100)
        
        if len(candles) < 20:
            logger.warning(f"Insufficient candles for features: {len(candles)}")
            return None
        
        # Calculate features
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        volumes = np.array([c.volume for c in candles])
        
        # Returns
        returns = np.diff(closes) / closes[:-1]
        
        # Volatility (annualized from hourly)
        volatility = float(np.std(returns) * np.sqrt(24 * 365))
        
        # Momentum (RSI-like)
        gains = np.maximum(returns, 0)
        losses = np.abs(np.minimum(returns, 0))
        avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains)
        avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses)
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        momentum = (rsi - 50) / 50  # Normalized to [-1, 1]
        
        # Trend detection
        sma_20 = np.mean(closes[-20:])
        sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma_20
        current_price = closes[-1]
        
        if current_price > sma_20 > sma_50:
            trend = "up"
        elif current_price < sma_20 < sma_50:
            trend = "down"
        else:
            trend = "sideways"
        
        # Regime detection
        atr = np.mean(highs[-14:] - lows[-14:]) / current_price
        
        if volatility > 0.8 and abs(momentum) > 0.5:
            regime = "BREAKOUT"
        elif volatility < 0.3 and abs(momentum) < 0.3:
            regime = "RANGE"
        elif trend in ["up", "down"] and abs(momentum) > 0.3:
            regime = "TREND"
        else:
            regime = "RANGE"
        
        # Spread estimate
        spread = atr * 0.1  # Rough estimate
        
        # Liquidity score (based on volume)
        avg_volume = np.mean(volumes[-24:]) if len(volumes) >= 24 else np.mean(volumes)
        liquidity_score = min(1.0, avg_volume / 10000)  # Normalize
        
        features = MarketFeatures(
            symbol=symbol,
            regime=regime,
            volatility=round(volatility, 4),
            momentum=round(float(momentum), 4),
            spread=round(spread, 6),
            liquidity_score=round(liquidity_score, 4),
            trend=trend,
            atr=round(float(atr * current_price), 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        # Cache
        self.feature_cache[cache_key] = features
        self._feature_cache_time[cache_key] = datetime.now(timezone.utc)
        
        return features
    
    def get_status(self) -> Dict[str, Any]:
        """Get data feed status."""
        manager_status = self._manager.get_status()
        
        return {
            "initialized": manager_status.get("initialized", False),
            "active_source": manager_status.get("active_source"),
            "safe_mode": manager_status.get("safe_mode", False),
            "safe_mode_reason": manager_status.get("safe_mode_reason", ""),
            "adapters": manager_status.get("adapters", {}),
            "cache_stats": manager_status.get("cache_stats", {}),
        }


# Module-level singleton management (for backward compatibility)
_data_feed_instance: Optional[DataFeed] = None


def get_data_feed() -> Optional[DataFeed]:
    """Get the global DataFeed instance."""
    return _data_feed_instance


def set_data_feed(instance: DataFeed):
    """Set the global DataFeed instance."""
    global _data_feed_instance
    _data_feed_instance = instance


async def create_data_feed(db: AsyncIOMotorDatabase = None) -> DataFeed:
    """Create and initialize a new DataFeed instance."""
    feed = DataFeed(db=db)
    await feed.initialize()
    return feed
