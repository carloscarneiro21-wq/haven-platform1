"""Binance Spot REST client (market data + signed trading).

- Supports Spot LIVE and Spot TESTNET via BINANCE_ENV
- MARKET orders only (quoteOrderQty for BUY, quantity for SELL)
- Signed requests for private endpoints
- Small TTL caches for public endpoints to avoid rate limits

Env vars (backend/.env):
- BINANCE_ENV: testnet|live
- BINANCE_API_KEY
- BINANCE_API_SECRET

Base URLs:
- live: https://api.binance.com
- testnet: https://testnet.binance.vision

Docs: Binance Spot REST API /api/v3/...
"""

from __future__ import annotations

import os
import time
import hmac
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)


@dataclass
class FeedStatus:
    status: str  # LIVE|OFFLINE
    last_update_ts: str


class BinanceSpotClient:
    def __init__(self):
        env = (os.environ.get("BINANCE_ENV") or "testnet").lower()
        self.env = env

        # Allow explicit base URLs (for geo-restricted environments / deployments)
        self.base_url_live = os.environ.get("BINANCE_BASE_URL_LIVE") or "https://api.binance.com"
        self.base_url_testnet = os.environ.get("BINANCE_BASE_URL_TESTNET") or "https://testnet.binance.vision"
        self.base_url = self.base_url_live if env == "live" else self.base_url_testnet

        # Optional fallback market-data base URL (e.g. Binance.US) for restricted envs
        self.market_data_base_url = os.environ.get("BINANCE_MARKET_DATA_BASE_URL")

        self.api_key = os.environ.get("BINANCE_API_KEY")
        self.api_secret = os.environ.get("BINANCE_API_SECRET")

        self._client = httpx.AsyncClient(timeout=20)

        # TTL caches
        self._exchange_info_cache = TTLCache(maxsize=10, ttl=60 * 60)  # 1h
        self._price_cache = TTLCache(maxsize=200, ttl=2)  # 2s
        self._klines_cache = TTLCache(maxsize=200, ttl=5)  # 5s

        self._feed_status: FeedStatus = FeedStatus(status="OFFLINE", last_update_ts="")

    async def close(self):
        await self._client.aclose()

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, query_string: str) -> str:
        if not self.api_secret:
            raise RuntimeError("BINANCE_API_SECRET missing")
        return hmac.new(self.api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("BINANCE_API_KEY missing")
        return {"X-MBX-APIKEY": self.api_key}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        # Market data may use a fallback base URL in restricted environments
        base = self.market_data_base_url or self.base_url
        url = f"{base}{path}"
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        self._feed_status = FeedStatus(status="LIVE", last_update_ts=str(self._now_ms()))
        return r.json()

    async def _post_signed(self, path: str, params: Dict[str, Any]) -> Any:
        # Signed endpoints require timestamp + signature
        params = {**params}
        params.setdefault("recvWindow", 5000)
        params["timestamp"] = self._now_ms()

        # Construct query string (order doesn't matter for REST)
        query_parts = []
        for k, v in params.items():
            query_parts.append(f"{k}={v}")
        query_string = "&".join(query_parts)
        signature = self._sign(query_string)

        url = f"{self.base_url}{path}?{query_string}&signature={signature}"
        r = await self._client.post(url, headers=self._headers())
        r.raise_for_status()
        return r.json()

    # ---------------------------
    # Public endpoints
    # ---------------------------

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        key = symbol or "ALL"
        if key in self._exchange_info_cache:
            return self._exchange_info_cache[key]

        data = await self._get("/api/v3/exchangeInfo", params={"symbol": symbol} if symbol else None)
        self._exchange_info_cache[key] = data
        return data

    async def get_price(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper()
        if symbol in self._price_cache:
            return self._price_cache[symbol]
        data = await self._get("/api/v3/ticker/price", params={"symbol": symbol})
        self._price_cache[symbol] = data
        return data

    async def get_klines(self, symbol: str, interval: str, limit: int) -> List[list]:
        symbol = symbol.upper()
        cache_key = f"{symbol}:{interval}:{limit}"
        if cache_key in self._klines_cache:
            return self._klines_cache[cache_key]
        data = await self._get("/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})
        self._klines_cache[cache_key] = data
        return data

    def get_feed_status(self) -> FeedStatus:
        # Never return UNKNOWN
        if self._feed_status.status not in ["LIVE", "OFFLINE"]:
            return FeedStatus(status="OFFLINE", last_update_ts=self._feed_status.last_update_ts)
        return self._feed_status

    # ---------------------------
    # Trading (MARKET orders)
    # ---------------------------

    async def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quote_order_qty: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        side = side.upper()

        if quote_order_qty is None and quantity is None:
            raise ValueError("Provide quote_order_qty or quantity")
        if quote_order_qty is not None and quantity is not None:
            raise ValueError("Provide only one of quote_order_qty or quantity")

        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "newOrderRespType": "FULL",
        }

        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        else:
            params["quantity"] = quantity

        return await self._post_signed("/api/v3/order", params)


_binance_client: Optional[BinanceSpotClient] = None


def get_binance_client() -> BinanceSpotClient:
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceSpotClient()
    return _binance_client
