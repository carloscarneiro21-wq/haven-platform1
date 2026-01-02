"""Kraken venue adapter - Primary execution-grade data source."""

import httpx
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import VenueAdapter, TickerData, CandleData, OrderBookData
from ..symbol_mapper import get_symbol_mapper, get_timeframe_mapper, Venue

logger = logging.getLogger(__name__)


class KrakenAdapter(VenueAdapter):
    """Kraken API adapter for market data."""
    
    API_BASE = "https://api.kraken.com/0/public"
    
    def __init__(self):
        super().__init__("kraken")
        self._client: Optional[httpx.AsyncClient] = None
        self._symbol_mapper = get_symbol_mapper()
        self._timeframe_mapper = get_timeframe_mapper()
    
    async def initialize(self):
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"Accept": "application/json"}
        )
        logger.info("KrakenAdapter initialized")
    
    async def cleanup(self):
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def fetch_ticker(self, internal_symbol: str) -> Optional[TickerData]:
        """Fetch ticker from Kraken."""
        if not self._client:
            await self.initialize()
        
        kraken_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.KRAKEN)
        if not kraken_symbol:
            logger.warning(f"Unknown symbol for Kraken: {internal_symbol}")
            return None
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/Ticker",
                params={"pair": kraken_symbol}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Kraken error: {data['error']}")
            
            result = data.get("result", {})
            ticker_data = None
            for key in result:
                ticker_data = result[key]
                break
            
            if not ticker_data:
                return None
            
            self.record_success()
            
            return TickerData(
                symbol=internal_symbol,
                source="kraken",
                last=float(ticker_data["c"][0]),
                bid=float(ticker_data["b"][0]),
                ask=float(ticker_data["a"][0]),
                high_24h=float(ticker_data["h"][1]),
                low_24h=float(ticker_data["l"][1]),
                volume_24h=float(ticker_data["v"][1]),
                vwap_24h=float(ticker_data["p"][1]),
                trades_24h=int(ticker_data["t"][1]),
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Kraken ticker fetch failed for {internal_symbol}: {e}")
            return None
    
    async def fetch_candles(
        self, 
        internal_symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[CandleData]:
        """Fetch OHLCV candles from Kraken."""
        if not self._client:
            await self.initialize()
        
        kraken_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.KRAKEN)
        if not kraken_symbol:
            logger.warning(f"Unknown symbol for Kraken: {internal_symbol}")
            return []
        
        kraken_interval = self._timeframe_mapper.to_venue(timeframe, Venue.KRAKEN)
        if not kraken_interval:
            kraken_interval = 60  # Default 1h
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/OHLC",
                params={"pair": kraken_symbol, "interval": kraken_interval}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Kraken error: {data['error']}")
            
            result = data.get("result", {})
            ohlc_data = None
            for key in result:
                if key != "last":
                    ohlc_data = result[key]
                    break
            
            if not ohlc_data:
                return []
            
            self.record_success()
            
            candles = []
            for item in ohlc_data[-limit:]:
                # Kraken format: [time, open, high, low, close, vwap, volume, count]
                candles.append(CandleData(
                    timestamp=int(item[0]) * 1000,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[6]),
                ))
            
            return candles
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Kraken candles fetch failed for {internal_symbol}: {e}")
            return []
    
    async def fetch_orderbook(
        self, 
        internal_symbol: str, 
        limit: int = 20
    ) -> Optional[OrderBookData]:
        """Fetch order book from Kraken."""
        if not self._client:
            await self.initialize()
        
        kraken_symbol = self._symbol_mapper.to_venue(internal_symbol, Venue.KRAKEN)
        if not kraken_symbol:
            return None
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/Depth",
                params={"pair": kraken_symbol, "count": limit}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Kraken error: {data['error']}")
            
            result = data.get("result", {})
            book = None
            for key in result:
                book = result[key]
                break
            
            if not book:
                return None
            
            self.record_success()
            
            return OrderBookData(
                symbol=internal_symbol,
                source="kraken",
                bids=[[float(p), float(v)] for p, v, _ in book.get("bids", [])[:limit]],
                asks=[[float(p), float(v)] for p, v, _ in book.get("asks", [])[:limit]],
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"Kraken orderbook fetch failed for {internal_symbol}: {e}")
            return None
