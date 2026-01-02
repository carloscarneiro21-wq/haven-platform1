# Market Data Service - Binance OHLCV Data Pipeline
import asyncio
import aiohttp
import hmac
import hashlib
import time
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Literal
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)

BINANCE_API = "https://api.binance.com/api/v3"

# Timeframe mappings (Binance format)
TIMEFRAMES = {
    "1m": {"ms": 60000, "limit": 1000},
    "5m": {"ms": 300000, "limit": 1000},
    "15m": {"ms": 900000, "limit": 1000},
    "1h": {"ms": 3600000, "limit": 1000},
}

class BinanceDataService:
    """Fetches and caches OHLCV data from Binance API"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = os.environ.get("BINANCE_API_KEY", "")
        self.api_secret = os.environ.get("BINANCE_API_SECRET", "")
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {}
            if self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _symbol_to_binance(self, symbol: str) -> str:
        """Convert BTC/USDT to BTCUSDT"""
        return symbol.replace("/", "")
    
    def _sign_request(self, params: Dict) -> Dict:
        """Sign request with HMAC SHA256"""
        if not self.api_secret:
            return params
        
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params
    
    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[Dict]:
        """Fetch klines/candlestick data from Binance"""
        session = await self._get_session()
        binance_symbol = self._symbol_to_binance(symbol)
        
        params = {
            "symbol": binance_symbol,
            "interval": timeframe,
            "limit": min(limit, 1000)
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        try:
            async with session.get(f"{BINANCE_API}/klines", params=params) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"Binance API error: {resp.status} - {error}")
                    return []
                
                data = await resp.json()
                
                # Parse Binance kline format
                candles = []
                for k in data:
                    candles.append({
                        "timestamp": k[0],  # Open time
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                        "close_time": k[6],
                        "quote_volume": float(k[7]),
                        "trades": k[8],
                        "taker_buy_base": float(k[9]),
                        "taker_buy_quote": float(k[10]),
                        "symbol": symbol,
                        "timeframe": timeframe
                    })
                
                return candles
                
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []
    
    async def fetch_and_store_historical(
        self,
        symbol: str,
        timeframe: str = "1h",
        days_back: int = 30
    ) -> int:
        """Fetch historical data and store in MongoDB"""
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = end_time - (days_back * 24 * 60 * 60 * 1000)
        
        all_candles = []
        current_start = start_time
        
        while current_start < end_time:
            candles = await self.fetch_klines(
                symbol=symbol,
                timeframe=timeframe,
                start_time=current_start,
                end_time=end_time,
                limit=1000
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            # Move to next batch
            current_start = candles[-1]["timestamp"] + TIMEFRAMES[timeframe]["ms"]
            
            # Rate limit
            await asyncio.sleep(0.1)
        
        if all_candles:
            # Upsert candles to avoid duplicates
            collection = self.db[f"candles_{timeframe}"]
            
            for candle in all_candles:
                await collection.update_one(
                    {"symbol": symbol, "timestamp": candle["timestamp"]},
                    {"$set": candle},
                    upsert=True
                )
            
            # Create index for efficient queries
            await collection.create_index([("symbol", 1), ("timestamp", -1)])
            
            logger.info(f"Stored {len(all_candles)} candles for {symbol} ({timeframe})")
        
        return len(all_candles)
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[Dict]:
        """Get candles from cache or fetch from Binance"""
        collection = self.db[f"candles_{timeframe}"]
        
        query = {"symbol": symbol}
        if start_time:
            query["timestamp"] = {"$gte": start_time}
        if end_time:
            if "timestamp" in query:
                query["timestamp"]["$lte"] = end_time
            else:
                query["timestamp"] = {"$lte": end_time}
        
        # Try cache first
        candles = await collection.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
        
        if candles:
            return list(reversed(candles))
        
        # Fallback to API
        return await self.fetch_klines(symbol, timeframe, start_time, end_time, limit)
    
    async def get_latest_price(self, symbol: str) -> Optional[Dict]:
        """Get latest price from Binance ticker"""
        session = await self._get_session()
        binance_symbol = self._symbol_to_binance(symbol)
        
        try:
            async with session.get(f"{BINANCE_API}/ticker/24hr", params={"symbol": binance_symbol}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "symbol": symbol,
                        "last": float(data["lastPrice"]),
                        "bid": float(data["bidPrice"]),
                        "ask": float(data["askPrice"]),
                        "high_24h": float(data["highPrice"]),
                        "low_24h": float(data["lowPrice"]),
                        "volume_24h": float(data["quoteVolume"]),
                        "change_24h": float(data["priceChange"]),
                        "change_24h_percent": float(data["priceChangePercent"]),
                        "timestamp": datetime.now(timezone.utc),
                        "source": "binance_live"
                    }
                elif resp.status == 451:
                    # Geo-blocked, try Kraken
                    return await self._get_kraken_price(symbol)
                else:
                    logger.warning(f"Binance ticker error: {resp.status}")
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
        
        return None
    
    async def _get_kraken_price(self, symbol: str) -> Optional[Dict]:
        """Fallback to Kraken API when Binance is geo-blocked"""
        session = await self._get_session()
        
        # Convert symbol format (BTC/USDT -> XBTUSDT for Kraken)
        kraken_map = {
            "BTC/USDT": "XBTUSDT",
            "ETH/USDT": "ETHUSDT", 
            "SOL/USDT": "SOLUSDT",
            "XRP/USDT": "XRPUSDT",
            "BNB/USDT": None,  # Not on Kraken
        }
        
        kraken_symbol = kraken_map.get(symbol)
        if not kraken_symbol:
            return None
        
        try:
            async with session.get(f"https://api.kraken.com/0/public/Ticker?pair={kraken_symbol}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("result"):
                        ticker = list(data["result"].values())[0]
                        last = float(ticker["c"][0])
                        return {
                            "symbol": symbol,
                            "last": last,
                            "bid": float(ticker["b"][0]),
                            "ask": float(ticker["a"][0]),
                            "high_24h": float(ticker["h"][1]),
                            "low_24h": float(ticker["l"][1]),
                            "volume_24h": float(ticker["v"][1]) * last,
                            "change_24h": last - float(ticker["o"]),
                            "change_24h_percent": ((last - float(ticker["o"])) / float(ticker["o"])) * 100,
                            "timestamp": datetime.now(timezone.utc),
                            "source": "kraken_live"
                        }
        except Exception as e:
            logger.error(f"Kraken API error: {e}")
        
        return None
    
    async def fetch_kraken_klines(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None
    ) -> List[Dict]:
        """Fetch OHLCV data from Kraken"""
        session = await self._get_session()
        
        kraken_map = {
            "BTC/USDT": "XBTUSDT",
            "ETH/USDT": "ETHUSDT",
            "SOL/USDT": "SOLUSDT", 
            "XRP/USDT": "XRPUSDT",
        }
        
        interval_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
        
        kraken_symbol = kraken_map.get(symbol)
        if not kraken_symbol:
            return []
        
        params = {
            "pair": kraken_symbol,
            "interval": interval_map.get(timeframe, 60)
        }
        
        if since:
            params["since"] = since // 1000  # Kraken uses seconds
        
        try:
            async with session.get("https://api.kraken.com/0/public/OHLC", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("result"):
                        result_key = [k for k in data["result"].keys() if k != "last"][0]
                        candles = []
                        for k in data["result"][result_key]:
                            candles.append({
                                "timestamp": int(k[0]) * 1000,
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[6]),
                                "symbol": symbol,
                                "timeframe": timeframe
                            })
                        return candles
        except Exception as e:
            logger.error(f"Kraken OHLC error: {e}")
        
        return []


class MarketRegimeDetector:
    """Detects market regime: trend, range, high volatility"""
    
    @staticmethod
    def calculate_atr(candles: List[Dict], period: int = 14) -> float:
        """Calculate Average True Range"""
        if len(candles) < period + 1:
            return 0.0
        
        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i-1]["close"]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        return sum(tr_values[-period:]) / period
    
    @staticmethod
    def calculate_adx(candles: List[Dict], period: int = 14) -> float:
        """Calculate ADX (trend strength indicator)"""
        if len(candles) < period * 2:
            return 0.0
        
        plus_dm = []
        minus_dm = []
        tr_values = []
        
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_high = candles[i-1]["high"]
            prev_low = candles[i-1]["low"]
            prev_close = candles[i-1]["close"]
            
            # True Range
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
            
            # Directional Movement
            up_move = high - prev_high
            down_move = prev_low - low
            
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)
            
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)
        
        # Smoothed values
        atr = sum(tr_values[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        
        # DX and ADX
        if plus_di + minus_di > 0:
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        else:
            dx = 0
        
        return dx
    
    @staticmethod
    def detect_regime(candles: List[Dict]) -> Dict:
        """Detect current market regime"""
        if len(candles) < 50:
            return {"regime": "unknown", "confidence": 0.0, "details": {}}
        
        # Calculate indicators
        adx = MarketRegimeDetector.calculate_adx(candles)
        atr = MarketRegimeDetector.calculate_atr(candles)
        
        # Recent price range
        recent = candles[-20:]
        price_range = max(c["high"] for c in recent) - min(c["low"] for c in recent)
        avg_price = sum(c["close"] for c in recent) / len(recent)
        volatility_pct = (atr / avg_price) * 100 if avg_price > 0 else 0
        
        # EMA trend direction
        ema_12 = MarketRegimeDetector._ema([c["close"] for c in candles], 12)
        ema_26 = MarketRegimeDetector._ema([c["close"] for c in candles], 26)
        trend_direction = "bullish" if ema_12 > ema_26 else "bearish"
        
        # Determine regime
        if adx > 25:
            regime = "trending"
            confidence = min(adx / 50, 1.0)
        elif volatility_pct > 3:
            regime = "volatile"
            confidence = min(volatility_pct / 5, 1.0)
        else:
            regime = "ranging"
            confidence = 1.0 - (adx / 25)
        
        return {
            "regime": regime,
            "confidence": confidence,
            "trend_direction": trend_direction,
            "details": {
                "adx": round(adx, 2),
                "atr": round(atr, 4),
                "volatility_pct": round(volatility_pct, 2),
                "ema_12": round(ema_12, 2),
                "ema_26": round(ema_26, 2)
            }
        }
    
    @staticmethod
    def _ema(prices: List[float], period: int) -> float:
        """Calculate EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
