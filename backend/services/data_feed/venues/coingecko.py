"""CoinGecko venue adapter - Reference/fallback data source."""

import httpx
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import VenueAdapter, TickerData, CandleData, OrderBookData
from ..symbol_mapper import get_symbol_mapper, Venue

logger = logging.getLogger(__name__)


class CoinGeckoAdapter(VenueAdapter):
    """CoinGecko API adapter - fallback for reference pricing."""
    
    API_BASE = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        super().__init__("coingecko")
        self._client: Optional[httpx.AsyncClient] = None
        self._symbol_mapper = get_symbol_mapper()
    
    async def initialize(self):
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"Accept": "application/json"}
        )
        logger.info("CoinGeckoAdapter initialized")
    
    async def cleanup(self):
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def fetch_ticker(self, internal_symbol: str) -> Optional[TickerData]:
        """Fetch ticker from CoinGecko."""
        if not self._client:
            await self.initialize()
        
        coin_id = self._symbol_mapper.to_venue(internal_symbol, Venue.COINGECKO)
        if not coin_id:
            logger.warning(f"Unknown symbol for CoinGecko: {internal_symbol}")
            return None
        
        # Determine quote currency from symbol
        info = self._symbol_mapper.get_info(internal_symbol)
        vs_currency = info.quote.lower() if info else "usd"
        if vs_currency == "usdt":
            vs_currency = "usd"  # CoinGecko uses USD
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": vs_currency,
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_last_updated_at": "true",
                }
            )
            response.raise_for_status()
            data = response.json().get(coin_id, {})
            
            if not data:
                return None
            
            price = float(data.get(vs_currency, 0))
            
            self.record_success()
            
            # CoinGecko doesn't provide bid/ask, estimate from price
            return TickerData(
                symbol=internal_symbol,
                source="coingecko",
                last=price,
                bid=price * 0.9999,  # Estimated
                ask=price * 1.0001,  # Estimated
                high_24h=price * 1.02,  # Estimated
                low_24h=price * 0.98,  # Estimated
                volume_24h=float(data.get(f"{vs_currency}_24h_vol", 0)),
                vwap_24h=price,
                trades_24h=0,  # Not available
                timestamp=int(data.get("last_updated_at", datetime.now(timezone.utc).timestamp()) * 1000),
            )
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"CoinGecko ticker fetch failed for {internal_symbol}: {e}")
            return None
    
    async def fetch_candles(
        self, 
        internal_symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[CandleData]:
        """Fetch price history from CoinGecko (hourly granularity max)."""
        if not self._client:
            await self.initialize()
        
        coin_id = self._symbol_mapper.to_venue(internal_symbol, Venue.COINGECKO)
        if not coin_id:
            return []
        
        # Determine days to fetch
        days = min(30, max(1, limit // 24))
        
        try:
            response = await self._client.get(
                f"{self.API_BASE}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": days}
            )
            response.raise_for_status()
            data = response.json()
            
            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])
            
            self.record_success()
            
            candles = []
            for i, (timestamp, price) in enumerate(prices[-limit:]):
                # CoinGecko doesn't have OHLC, estimate
                vol = volumes[i][1] if i < len(volumes) else 0
                volatility = price * 0.001
                
                candles.append(CandleData(
                    timestamp=int(timestamp),
                    open=price,
                    high=price + volatility,
                    low=price - volatility,
                    close=price,
                    volume=vol / price if price > 0 else 0,
                ))
            
            return candles
            
        except Exception as e:
            self.record_error(str(e))
            logger.warning(f"CoinGecko candles fetch failed for {internal_symbol}: {e}")
            return []
    
    async def fetch_orderbook(
        self, 
        internal_symbol: str, 
        limit: int = 20
    ) -> Optional[OrderBookData]:
        """CoinGecko doesn't provide order book - return None."""
        logger.debug(f"CoinGecko doesn't support orderbook for {internal_symbol}")
        return None
