"""Binance venue adapter - Secondary execution-grade data source."""

import httpx
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import VenueAdapter, TickerData, CandleData, OrderBookData
from ..symbol_mapper import get_symbol_mapper, get_timeframe_mapper, Venue

logger = logging.getLogger(__name__)


class BinanceAdapter(VenueAdapter):
    """Binance API adapter for market data."""
    
    API_BASE = "https://api.binance.com/api/v3"
    
    def __init__(self):
        super().__init__("binance")
        self._client: Optional[httpx.AsyncClient] = None
        self._symbol_mapper = get_symbol_mapper()
        self._timeframe_mapper = get_timeframe_mapper()
    
    async def initialize(self):
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"Accept": "application/json"}
        )
        logger.info("BinanceAdapter initialized")
    
    async def cleanup(self):
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def fetch_ticker(self, internal_symbol: str) -> Optional[TickerData]:
        """Fetch ticker from Binance."""
        if not self._client:
            await self.initialize()
        
        binance_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.BINANCE)
        if not binance_symbol:
            logger.warning(f"Unknown symbol for Binance: {internal_symbol}")
            return None
        
        try:
            # Get 24h ticker stats
            response = await self._client.get(
                f"{self.API_BASE}/ticker/24hr",
                params={"symbol": binance_symbol}
            )
            response.raise_for_status()
            data = response.json()
            
            # Also get book ticker for best bid/ask
            book_response = await self._client.get(
                f"{self.API_BASE}/ticker/bookTicker",
                params={"symbol": binance_symbol}
            )
            book_response.raise_for_status()
            book_data = book_response.json()
            
            self.record_success()
            
            return TickerData(
                symbol=internal_symbol,
                source="binance",
                last=float(data.get("lastPrice", 0)),
                bid=float(book_data.get("bidPrice", 0)),
                ask=float(book_data.get("askPrice", 0)),
                high_24h=float(data.get("highPrice", 0)),
                low_24h=float(data.get("lowPrice", 0)),
                volume_24h=float(data.get("volume", 0)),
                vwap_24h=float(data.get("weightedAvgPrice", 0)),
                trades_24h=int(data.get("count", 0)),
                timestamp=int(data.get("closeTime", datetime.now(timezone.utc).timestamp() * 1000)),
            )
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Binance ticker fetch failed for {internal_symbol}: {e}")
            return None
    
    async def fetch_candles(
        self, 
        internal_symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[CandleData]:
        """Fetch OHLCV candles from Binance."""
        if not self._client:
            await self.initialize()
        
        binance_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.BINANCE)
        if not binance_symbol:
            logger.warning(f"Unknown symbol for Binance: {internal_symbol}")
            return []
        
        binance_interval = self._timeframe_mapper.to_venue(timeframe, Venue.BINANCE)
        if not binance_interval:
            binance_interval = "1h"  # Default
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/klines",
                params={
                    "symbol": binance_symbol,
                    "interval": binance_interval,
                    "limit": limit
                }
            )
            response.raise_for_status()
            data = response.json()
            
            self.record_success()
            
            candles = []
            for item in data:
                # Binance format: [open_time, open, high, low, close, volume, close_time, ...]
                candles.append(CandleData(
                    timestamp=int(item[0]),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                ))
            
            return candles
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Binance candles fetch failed for {internal_symbol}: {e}")
            return []
    
    async def fetch_orderbook(
        self, 
        internal_symbol: str, 
        limit: int = 20
    ) -> Optional[OrderBookData]:
        """Fetch order book from Binance."""
        if not self._client:
            await self.initialize()
        
        binance_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.BINANCE)
        if not binance_symbol:
            return None
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/depth",
                params={"symbol": binance_symbol, "limit": limit}
            )
            response.raise_for_status()
            data = response.json()
            
            self.record_success()
            
            return OrderBookData(
                symbol=internal_symbol,
                source="binance",
                bids=[[float(p), float(v)] for p, v in data.get("bids", [])[:limit]],
                asks=[[float(p), float(v)] for p, v in data.get("asks", [])[:limit]],
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Binance orderbook fetch failed for {internal_symbol}: {e}")
            return None
