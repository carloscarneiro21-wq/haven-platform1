"""Pair Advisor Engine - Recommends optimal trading pairs per agent type."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class AgentStrategy(str, Enum):
    DCA = "dca"
    GRID = "grid"
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"


class Venue(str, Enum):
    KRAKEN = "kraken"
    BINANCE = "binance"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# Reason codes with explanations
REASON_CODES = {
    # Positive
    "LOW_SPREAD": "Spread baixo permite entradas/saídas eficientes",
    "HIGH_LIQUIDITY": "Alta liquidez reduz slippage em ordens pequenas",
    "GOOD_RANGE_BEHAVIOR": "Par oscila bem dentro de ranges previsíveis",
    "LOW_COST_FOR_MICRO_CAPITAL": "Custos totais adequados para capital €5-€50",
    "STRONG_TREND": "Tendência clara favorece estratégias direcionais",
    "HIGH_VOLATILITY": "Volatilidade cria oportunidades de lucro",
    "STABLE_VOLUME": "Volume consistente ao longo do dia",
    "GOOD_ATR_RANGE": "ATR adequado para definir grids/stops",
    "FAVORABLE_FEES": "Taxas da exchange competitivas",
    "DEEP_ORDER_BOOK": "Order book profundo absorve ordens sem impacto",
    
    # Negative
    "HIGH_SPREAD": "Spread alto come lucros em micro-trades",
    "LOW_LIQUIDITY": "Baixa liquidez causa slippage excessivo",
    "ERRATIC_BEHAVIOR": "Movimentos imprevisíveis dificultam estratégia",
    "HIGH_COST": "Custos totais > 0.15% por trade",
    "INSUFFICIENT_VOLUME": "Volume insuficiente para execução fiável",
    "SPREAD_GATE_FAILED": "Spread > 0.10% (gate micro-capital)",
    "SLIPPAGE_GATE_FAILED": "Slippage > 0.05% para €5-€10 (gate micro-capital)",
}

# Strategy-specific scoring weights
STRATEGY_WEIGHTS = {
    AgentStrategy.DCA: {
        "spread": 0.25,
        "slippage": 0.20,
        "volume": 0.15,
        "atr": 0.10,
        "trend_strength": 0.15,
        "fees": 0.15,
    },
    AgentStrategy.GRID: {
        "spread": 0.30,
        "slippage": 0.25,
        "volume": 0.10,
        "atr": 0.20,  # Grid needs good ATR for range
        "trend_strength": 0.05,  # Grid prefers ranging
        "fees": 0.10,
    },
    AgentStrategy.TREND: {
        "spread": 0.15,
        "slippage": 0.15,
        "volume": 0.15,
        "atr": 0.15,
        "trend_strength": 0.30,  # Trend needs strong trends
        "fees": 0.10,
    },
    AgentStrategy.MEAN_REVERSION: {
        "spread": 0.25,
        "slippage": 0.20,
        "volume": 0.15,
        "atr": 0.15,
        "trend_strength": 0.10,  # Prefers low trend (ranging)
        "fees": 0.15,
    },
    AgentStrategy.BREAKOUT: {
        "spread": 0.20,
        "slippage": 0.20,
        "volume": 0.20,  # Volume confirms breakouts
        "atr": 0.20,
        "trend_strength": 0.10,
        "fees": 0.10,
    },
}

# Supported pairs per venue
SUPPORTED_PAIRS = {
    Venue.KRAKEN: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
        "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT", "AVAX/USDT",
        "BTC/EUR", "ETH/EUR", "SOL/EUR"
    ],
    Venue.BINANCE: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
        "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT", "AVAX/USDT",
        "BNB/USDT", "ARB/USDT", "OP/USDT", "PEPE/USDT", "SHIB/USDT"
    ],
}

# Venue fee structures (maker/taker)
VENUE_FEES = {
    Venue.KRAKEN: {"maker": 0.0016, "taker": 0.0026},  # 0.16% / 0.26%
    Venue.BINANCE: {"maker": 0.001, "taker": 0.001},   # 0.10% / 0.10%
}


class PairMetrics:
    """Metrics for a trading pair on a specific venue."""
    
    def __init__(
        self,
        pair: str,
        venue: Venue,
        spread_pct: float,
        slippage_5eur: float,
        slippage_10eur: float,
        atr_7d_pct: float,
        volume_24h_usd: float,
        trend_strength: float,  # ADX or similar, 0-100
        last_price: float,
        bid: float,
        ask: float,
    ):
        self.pair = pair
        self.venue = venue
        self.spread_pct = spread_pct
        self.slippage_5eur = slippage_5eur
        self.slippage_10eur = slippage_10eur
        self.atr_7d_pct = atr_7d_pct
        self.volume_24h_usd = volume_24h_usd
        self.trend_strength = trend_strength
        self.last_price = last_price
        self.bid = bid
        self.ask = ask
        self.fees = VENUE_FEES[venue]
        self.timestamp = datetime.now(timezone.utc)
    
    @property
    def estimated_cost_per_trade(self) -> float:
        """Estimate total cost per trade (spread + fees + avg slippage)."""
        avg_slippage = (self.slippage_5eur + self.slippage_10eur) / 2
        return self.spread_pct + self.fees["taker"] * 100 + avg_slippage
    
    def to_dict(self) -> Dict:
        return {
            "pair": self.pair,
            "venue": self.venue.value,
            "spread_pct": round(self.spread_pct, 4),
            "slippage_5eur": round(self.slippage_5eur, 4),
            "slippage_10eur": round(self.slippage_10eur, 4),
            "atr_7d_pct": round(self.atr_7d_pct, 2),
            "volume_24h_usd": self.volume_24h_usd,
            "volume_24h_label": self._volume_label(),
            "trend_strength": round(self.trend_strength, 1),
            "last_price": self.last_price,
            "estimated_cost_per_trade": round(self.estimated_cost_per_trade, 4),
            "fees": {
                "maker": f"{self.fees['maker']*100:.2f}%",
                "taker": f"{self.fees['taker']*100:.2f}%",
            },
            "timestamp": self.timestamp.isoformat(),
        }
    
    def _volume_label(self) -> str:
        if self.volume_24h_usd >= 1_000_000_000:
            return "very_high"
        elif self.volume_24h_usd >= 100_000_000:
            return "high"
        elif self.volume_24h_usd >= 10_000_000:
            return "medium"
        else:
            return "low"


class PairRecommendation:
    """Recommendation for a trading pair."""
    
    def __init__(
        self,
        agent: AgentStrategy,
        pair: str,
        venue: Venue,
        score: int,
        metrics: PairMetrics,
        reason_codes: List[str],
        confidence: ConfidenceLevel,
        venue_selection_reason: str,
    ):
        self.agent = agent
        self.pair = pair
        self.venue = venue
        self.score = score
        self.metrics = metrics
        self.reason_codes = reason_codes
        self.confidence = confidence
        self.venue_selection_reason = venue_selection_reason
        self.timestamp = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict:
        return {
            "agent": self.agent.value.upper(),
            "pair": self.pair,
            "venue": self.venue.value.upper(),
            "score": self.score,
            "confidence": self.confidence.value,
            "metrics": self.metrics.to_dict(),
            "reason_codes": self.reason_codes,
            "reasons_explained": [
                {"code": code, "explanation": REASON_CODES.get(code, code)}
                for code in self.reason_codes
            ],
            "venue_selection_reason": self.venue_selection_reason,
            "timestamp": self.timestamp.isoformat(),
        }


class PairAdvisorEngine:
    """Engine for recommending optimal trading pairs per agent strategy."""
    
    # Cache settings
    CACHE_TTL_SECONDS = 300  # 5 minutes
    ANTI_FLAP_COOLDOWN_SECONDS = 60  # 1 minute cooldown for venue switches
    
    # Micro-capital gates
    MAX_SPREAD_PCT = 0.10  # 0.10%
    MAX_SLIPPAGE_PCT = 0.05  # 0.05% for €5-€10
    
    def __init__(self, db: AsyncIOMotorDatabase, data_feed=None, event_logger=None):
        self.db = db
        self.data_feed = data_feed
        self.event_logger = event_logger
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._venue_history: Dict[str, List[Tuple[Venue, datetime]]] = {}
        
    async def initialize(self):
        """Initialize the engine."""
        # Create indexes for audit collection
        await self.db.pair_advisor_audit.create_index("timestamp")
        await self.db.pair_advisor_audit.create_index([("pair", 1), ("agent", 1)])
        logger.info("PairAdvisorEngine initialized")
    
    def _cache_key(self, agent: AgentStrategy) -> str:
        """Generate cache key for recommendations."""
        return f"recommendations_{agent.value}"
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache:
            return False
        _, cached_at = self._cache[key]
        return (datetime.now(timezone.utc) - cached_at).total_seconds() < self.CACHE_TTL_SECONDS
    
    def _check_anti_flap(self, pair: str, new_venue: Venue) -> Tuple[bool, Optional[str]]:
        """Check anti-flapping rules for venue selection."""
        history = self._venue_history.get(pair, [])
        if not history:
            return True, None
        
        # Check last venue and time
        last_venue, last_time = history[-1]
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
        
        if last_venue != new_venue and elapsed < self.ANTI_FLAP_COOLDOWN_SECONDS:
            return False, f"Cooldown ativo: {last_venue.value} → {new_venue.value} requer {self.ANTI_FLAP_COOLDOWN_SECONDS - elapsed:.0f}s"
        
        return True, None
    
    def _record_venue_selection(self, pair: str, venue: Venue):
        """Record venue selection for anti-flap tracking."""
        if pair not in self._venue_history:
            self._venue_history[pair] = []
        self._venue_history[pair].append((venue, datetime.now(timezone.utc)))
        # Keep only last 10 entries
        self._venue_history[pair] = self._venue_history[pair][-10:]
    
    async def _fetch_pair_metrics(self, pair: str, venue: Venue) -> Optional[PairMetrics]:
        """Fetch metrics for a pair from the venue."""
        try:
            # Try to get real data from data feed
            if self.data_feed:
                ticker = await self.data_feed.get_ticker(pair)
                orderbook = await self.data_feed.get_order_book(pair)
                
                if ticker and orderbook:
                    spread_pct = ((ticker.get("ask", 0) - ticker.get("bid", 0)) / ticker.get("last", 1)) * 100
                    
                    # Calculate slippage from orderbook depth
                    slippage_5eur = self._calculate_slippage(orderbook, 5, ticker.get("last", 1))
                    slippage_10eur = self._calculate_slippage(orderbook, 10, ticker.get("last", 1))
                    
                    # Get ATR from stored data or calculate
                    atr = await self._get_atr(pair)
                    
                    return PairMetrics(
                        pair=pair,
                        venue=venue,
                        spread_pct=spread_pct,
                        slippage_5eur=slippage_5eur,
                        slippage_10eur=slippage_10eur,
                        atr_7d_pct=atr,
                        volume_24h_usd=ticker.get("quoteVolume", 0),
                        trend_strength=await self._get_trend_strength(pair),
                        last_price=ticker.get("last", 0),
                        bid=ticker.get("bid", 0),
                        ask=ticker.get("ask", 0),
                    )
            
            # Fallback to simulated/cached data for paper trading
            return await self._get_simulated_metrics(pair, venue)
            
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {pair} on {venue}: {e}")
            return await self._get_simulated_metrics(pair, venue)
    
    def _calculate_slippage(self, orderbook: Dict, amount_eur: float, price: float) -> float:
        """Calculate expected slippage for a given order size."""
        if not orderbook or "asks" not in orderbook:
            return 0.05  # Default estimate
        
        amount_base = amount_eur / price
        cumulative = 0
        weighted_price = 0
        
        for ask_price, ask_size in orderbook.get("asks", [])[:10]:
            if cumulative >= amount_base:
                break
            take = min(ask_size, amount_base - cumulative)
            weighted_price += take * ask_price
            cumulative += take
        
        if cumulative == 0:
            return 0.05
        
        avg_price = weighted_price / cumulative
        slippage = ((avg_price - price) / price) * 100
        return max(0, slippage)
    
    async def _get_atr(self, pair: str) -> float:
        """Get ATR percentage for pair (7-day average)."""
        # Try to get from stored market features
        features = await self.db.market_features.find_one(
            {"symbol": pair},
            sort=[("timestamp", -1)]
        )
        if features and "atr" in features and "last_price" in features:
            return (features["atr"] / features["last_price"]) * 100
        
        # Default estimates based on asset type
        base = pair.split("/")[0]
        defaults = {
            "BTC": 2.5, "ETH": 3.5, "SOL": 5.0, "XRP": 4.0,
            "ADA": 4.5, "DOGE": 6.0, "DOT": 4.5, "MATIC": 5.0,
            "LINK": 4.0, "AVAX": 5.0, "BNB": 3.0, "ARB": 5.5,
            "OP": 5.5, "PEPE": 8.0, "SHIB": 7.0,
        }
        return defaults.get(base, 4.0)
    
    async def _get_trend_strength(self, pair: str) -> float:
        """Get trend strength (ADX-like, 0-100) for pair."""
        features = await self.db.market_features.find_one(
            {"symbol": pair},
            sort=[("timestamp", -1)]
        )
        if features and "adx" in features:
            return features["adx"]
        
        # Default moderate trend
        return 25.0
    
    async def _get_simulated_metrics(self, pair: str, venue: Venue) -> PairMetrics:
        """Get simulated metrics for paper trading."""
        # Simulated data based on typical market conditions
        base = pair.split("/")[0]
        
        # Base spreads by asset tier
        tier1 = ["BTC", "ETH"]
        tier2 = ["SOL", "XRP", "BNB", "DOGE"]
        tier3 = ["ADA", "DOT", "MATIC", "LINK", "AVAX", "ARB", "OP"]
        
        if base in tier1:
            spread = 0.02 if venue == Venue.BINANCE else 0.03
            volume = 2_000_000_000 if venue == Venue.BINANCE else 500_000_000
            slippage_5 = 0.01
            slippage_10 = 0.015
        elif base in tier2:
            spread = 0.03 if venue == Venue.BINANCE else 0.05
            volume = 500_000_000 if venue == Venue.BINANCE else 100_000_000
            slippage_5 = 0.02
            slippage_10 = 0.025
        elif base in tier3:
            spread = 0.05 if venue == Venue.BINANCE else 0.08
            volume = 100_000_000 if venue == Venue.BINANCE else 20_000_000
            slippage_5 = 0.03
            slippage_10 = 0.04
        else:
            spread = 0.08 if venue == Venue.BINANCE else 0.12
            volume = 20_000_000 if venue == Venue.BINANCE else 5_000_000
            slippage_5 = 0.05
            slippage_10 = 0.07
        
        # Simulated prices
        prices = {
            "BTC": 95000, "ETH": 3400, "SOL": 190, "XRP": 2.2,
            "ADA": 0.95, "DOGE": 0.32, "DOT": 7.5, "MATIC": 0.50,
            "LINK": 23, "AVAX": 40, "BNB": 700, "ARB": 0.80,
            "OP": 1.80, "PEPE": 0.00002, "SHIB": 0.000023,
        }
        price = prices.get(base, 100)
        
        return PairMetrics(
            pair=pair,
            venue=venue,
            spread_pct=spread,
            slippage_5eur=slippage_5,
            slippage_10eur=slippage_10,
            atr_7d_pct=await self._get_atr(pair),
            volume_24h_usd=volume,
            trend_strength=await self._get_trend_strength(pair),
            last_price=price,
            bid=price * (1 - spread/200),
            ask=price * (1 + spread/200),
        )
    
    def _score_pair(self, metrics: PairMetrics, strategy: AgentStrategy) -> Tuple[int, List[str]]:
        """Score a pair for a given strategy."""
        weights = STRATEGY_WEIGHTS[strategy]
        reason_codes = []
        
        # Initialize scores (0-100 scale)
        scores = {}
        
        # Spread score (lower is better)
        if metrics.spread_pct <= 0.03:
            scores["spread"] = 100
            reason_codes.append("LOW_SPREAD")
        elif metrics.spread_pct <= 0.05:
            scores["spread"] = 80
        elif metrics.spread_pct <= 0.08:
            scores["spread"] = 60
        elif metrics.spread_pct <= 0.10:
            scores["spread"] = 40
        else:
            scores["spread"] = 20
            reason_codes.append("HIGH_SPREAD")
        
        # Slippage score (lower is better) - using €10 as reference
        avg_slippage = (metrics.slippage_5eur + metrics.slippage_10eur) / 2
        if avg_slippage <= 0.02:
            scores["slippage"] = 100
            reason_codes.append("HIGH_LIQUIDITY")
        elif avg_slippage <= 0.03:
            scores["slippage"] = 80
        elif avg_slippage <= 0.05:
            scores["slippage"] = 60
        else:
            scores["slippage"] = 30
            reason_codes.append("LOW_LIQUIDITY")
        
        # Volume score
        vol_label = metrics._volume_label()
        if vol_label == "very_high":
            scores["volume"] = 100
            reason_codes.append("STABLE_VOLUME")
        elif vol_label == "high":
            scores["volume"] = 85
        elif vol_label == "medium":
            scores["volume"] = 60
        else:
            scores["volume"] = 30
            reason_codes.append("INSUFFICIENT_VOLUME")
        
        # ATR score (depends on strategy)
        atr = metrics.atr_7d_pct
        if strategy == AgentStrategy.GRID:
            # Grid prefers moderate ATR (2-5%)
            if 2.0 <= atr <= 5.0:
                scores["atr"] = 100
                reason_codes.append("GOOD_ATR_RANGE")
            elif 1.5 <= atr <= 6.0:
                scores["atr"] = 70
            else:
                scores["atr"] = 40
        elif strategy in [AgentStrategy.TREND, AgentStrategy.BREAKOUT]:
            # Trend/Breakout prefer higher ATR
            if atr >= 4.0:
                scores["atr"] = 100
                reason_codes.append("HIGH_VOLATILITY")
            elif atr >= 2.5:
                scores["atr"] = 70
            else:
                scores["atr"] = 40
        else:
            # DCA/Mean Reversion - moderate is fine
            if 2.0 <= atr <= 5.0:
                scores["atr"] = 90
            else:
                scores["atr"] = 60
        
        # Trend strength score (depends on strategy)
        trend = metrics.trend_strength
        if strategy == AgentStrategy.TREND:
            # Trend needs strong trends (ADX > 25)
            if trend >= 35:
                scores["trend_strength"] = 100
                reason_codes.append("STRONG_TREND")
            elif trend >= 25:
                scores["trend_strength"] = 80
            else:
                scores["trend_strength"] = 40
        elif strategy in [AgentStrategy.GRID, AgentStrategy.MEAN_REVERSION]:
            # Grid/MR prefer ranging (ADX < 25)
            if trend < 20:
                scores["trend_strength"] = 100
                reason_codes.append("GOOD_RANGE_BEHAVIOR")
            elif trend < 30:
                scores["trend_strength"] = 70
            else:
                scores["trend_strength"] = 40
        else:
            scores["trend_strength"] = 70  # Neutral for others
        
        # Fees score
        taker_fee = metrics.fees["taker"]
        if taker_fee <= 0.001:
            scores["fees"] = 100
            reason_codes.append("FAVORABLE_FEES")
        elif taker_fee <= 0.002:
            scores["fees"] = 70
        else:
            scores["fees"] = 50
        
        # Calculate weighted score
        total_score = sum(scores[k] * weights[k] for k in weights.keys())
        
        # Micro-capital gates
        passed_gates = True
        if metrics.spread_pct > self.MAX_SPREAD_PCT:
            reason_codes.append("SPREAD_GATE_FAILED")
            total_score *= 0.5  # Penalty
            passed_gates = False
        if avg_slippage > self.MAX_SLIPPAGE_PCT:
            reason_codes.append("SLIPPAGE_GATE_FAILED")
            total_score *= 0.5  # Penalty
            passed_gates = False
        
        # Bonus for micro-capital suitability
        if passed_gates and metrics.estimated_cost_per_trade <= 0.12:
            reason_codes.append("LOW_COST_FOR_MICRO_CAPITAL")
            total_score = min(100, total_score * 1.05)
        elif metrics.estimated_cost_per_trade > 0.15:
            reason_codes.append("HIGH_COST")
        
        return int(total_score), reason_codes
    
    def _select_best_venue(
        self, 
        pair: str, 
        metrics_by_venue: Dict[Venue, PairMetrics],
        strategy: AgentStrategy
    ) -> Tuple[Venue, str]:
        """Select the best venue for a pair."""
        best_venue = None
        best_score = -1
        best_reason = ""
        
        for venue, metrics in metrics_by_venue.items():
            score, _ = self._score_pair(metrics, strategy)
            
            if score > best_score:
                best_score = score
                best_venue = venue
        
        if len(metrics_by_venue) == 1:
            best_reason = f"Único venue disponível para {pair}"
        else:
            # Compare venues
            venues = list(metrics_by_venue.keys())
            m1, m2 = metrics_by_venue[venues[0]], metrics_by_venue[venues[1]]
            
            reasons = []
            if m1.spread_pct != m2.spread_pct:
                better = venues[0] if m1.spread_pct < m2.spread_pct else venues[1]
                reasons.append(f"spread {better.value} ({min(m1.spread_pct, m2.spread_pct):.3f}%)")
            
            if m1.estimated_cost_per_trade != m2.estimated_cost_per_trade:
                better = venues[0] if m1.estimated_cost_per_trade < m2.estimated_cost_per_trade else venues[1]
                reasons.append(f"custo total menor em {better.value}")
            
            if m1.volume_24h_usd != m2.volume_24h_usd:
                better = venues[0] if m1.volume_24h_usd > m2.volume_24h_usd else venues[1]
                reasons.append(f"maior liquidez em {better.value}")
            
            best_reason = f"Escolhido {best_venue.value.upper()}: " + ", ".join(reasons[:2])
        
        return best_venue, best_reason
    
    def _determine_confidence(self, score: int, reason_codes: List[str]) -> ConfidenceLevel:
        """Determine confidence level based on score and reasons."""
        negative_codes = ["HIGH_SPREAD", "LOW_LIQUIDITY", "SPREAD_GATE_FAILED", 
                        "SLIPPAGE_GATE_FAILED", "HIGH_COST", "INSUFFICIENT_VOLUME"]
        
        negative_count = sum(1 for code in reason_codes if code in negative_codes)
        
        if score >= 80 and negative_count == 0:
            return ConfidenceLevel.HIGH
        elif score >= 60 and negative_count <= 1:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    async def get_recommendations(
        self, 
        strategy: AgentStrategy, 
        top_n: int = 5,
        force_refresh: bool = False
    ) -> List[PairRecommendation]:
        """Get top N pair recommendations for a strategy."""
        cache_key = self._cache_key(strategy)
        
        # Check cache
        if not force_refresh and self._is_cache_valid(cache_key):
            cached_data, _ = self._cache[cache_key]
            logger.debug(f"Returning cached recommendations for {strategy.value}")
            return cached_data
        
        logger.info(f"Generating recommendations for {strategy.value}")
        recommendations = []
        
        # Get all unique pairs across venues
        all_pairs = set()
        for pairs in SUPPORTED_PAIRS.values():
            all_pairs.update(pairs)
        
        # Fetch metrics and score each pair
        for pair in all_pairs:
            metrics_by_venue: Dict[Venue, PairMetrics] = {}
            
            # Get metrics from each venue that supports this pair
            for venue in Venue:
                if pair in SUPPORTED_PAIRS[venue]:
                    metrics = await self._fetch_pair_metrics(pair, venue)
                    if metrics:
                        metrics_by_venue[venue] = metrics
            
            if not metrics_by_venue:
                continue
            
            # Select best venue
            best_venue, venue_reason = self._select_best_venue(pair, metrics_by_venue, strategy)
            
            # Check anti-flap
            can_switch, flap_reason = self._check_anti_flap(pair, best_venue)
            if not can_switch:
                # Use previous venue
                prev_venue = self._venue_history[pair][-1][0]
                if prev_venue in metrics_by_venue:
                    best_venue = prev_venue
                    venue_reason = f"Anti-flap: {flap_reason}"
            
            # Record venue selection
            self._record_venue_selection(pair, best_venue)
            
            # Score the pair
            metrics = metrics_by_venue[best_venue]
            score, reason_codes = self._score_pair(metrics, strategy)
            confidence = self._determine_confidence(score, reason_codes)
            
            recommendation = PairRecommendation(
                agent=strategy,
                pair=pair,
                venue=best_venue,
                score=score,
                metrics=metrics,
                reason_codes=reason_codes,
                confidence=confidence,
                venue_selection_reason=venue_reason,
            )
            recommendations.append(recommendation)
        
        # Sort by score and take top N
        recommendations.sort(key=lambda r: r.score, reverse=True)
        top_recommendations = recommendations[:top_n]
        
        # Cache results
        self._cache[cache_key] = (top_recommendations, datetime.now(timezone.utc))
        
        # Audit log
        await self._audit_recommendations(strategy, top_recommendations)
        
        return top_recommendations
    
    async def get_all_recommendations(self, top_n: int = 5) -> Dict[str, List[Dict]]:
        """Get recommendations for all strategies."""
        results = {}
        
        for strategy in [AgentStrategy.DCA, AgentStrategy.GRID, AgentStrategy.TREND, AgentStrategy.MEAN_REVERSION, AgentStrategy.BREAKOUT]:
            recs = await self.get_recommendations(strategy, top_n)
            results[strategy.value] = [r.to_dict() for r in recs]
        
        return results
    
    async def _audit_recommendations(self, strategy: AgentStrategy, recommendations: List[PairRecommendation]):
        """Audit log the recommendations."""
        audit_doc = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": strategy.value,
            "recommendations": [
                {
                    "pair": r.pair,
                    "venue": r.venue.value,
                    "score": r.score,
                    "confidence": r.confidence.value,
                    "reason_codes": r.reason_codes,
                    "venue_selection_reason": r.venue_selection_reason,
                    "metrics_summary": {
                        "spread_pct": r.metrics.spread_pct,
                        "estimated_cost": r.metrics.estimated_cost_per_trade,
                        "volume_label": r.metrics._volume_label(),
                    }
                }
                for r in recommendations
            ]
        }
        
        await self.db.pair_advisor_audit.insert_one(audit_doc)
        
        # Emit event
        if self.event_logger:
            from services.event_logger import EventCategory, EventSeverity
            await self.event_logger.emit(
                type="PAIR_ADVISOR_RECOMMENDATION",
                category=EventCategory.SYSTEM,
                severity=EventSeverity.INFO,
                message=f"Pair Advisor: Top {len(recommendations)} recommendations for {strategy.value.upper()}",
                context={
                    "strategy": strategy.value,
                    "top_pair": recommendations[0].pair if recommendations else None,
                    "top_venue": recommendations[0].venue.value if recommendations else None,
                    "top_score": recommendations[0].score if recommendations else None,
                }
            )
        
        logger.info(f"Audited {len(recommendations)} recommendations for {strategy.value}")
    
    async def get_recommendation_for_pair(
        self, 
        pair: str, 
        strategy: Optional[AgentStrategy] = None
    ) -> Dict[str, Any]:
        """Get detailed recommendation for a specific pair."""
        results = {}
        
        strategies = [strategy] if strategy else [AgentStrategy.DCA, AgentStrategy.GRID, AgentStrategy.TREND]
        
        for strat in strategies:
            metrics_by_venue: Dict[Venue, PairMetrics] = {}
            
            for venue in Venue:
                if pair in SUPPORTED_PAIRS.get(venue, []):
                    metrics = await self._fetch_pair_metrics(pair, venue)
                    if metrics:
                        metrics_by_venue[venue] = metrics
            
            if not metrics_by_venue:
                results[strat.value] = {"error": f"Pair {pair} not available on any venue"}
                continue
            
            best_venue, venue_reason = self._select_best_venue(pair, metrics_by_venue, strat)
            metrics = metrics_by_venue[best_venue]
            score, reason_codes = self._score_pair(metrics, strat)
            confidence = self._determine_confidence(score, reason_codes)
            
            rec = PairRecommendation(
                agent=strat,
                pair=pair,
                venue=best_venue,
                score=score,
                metrics=metrics,
                reason_codes=reason_codes,
                confidence=confidence,
                venue_selection_reason=venue_reason,
            )
            
            results[strat.value] = rec.to_dict()
            
            # Add comparison with other venue if available
            if len(metrics_by_venue) > 1:
                other_venue = [v for v in metrics_by_venue.keys() if v != best_venue][0]
                other_metrics = metrics_by_venue[other_venue]
                results[strat.value]["venue_comparison"] = {
                    best_venue.value: {
                        "spread": f"{metrics.spread_pct:.3f}%",
                        "cost": f"{metrics.estimated_cost_per_trade:.3f}%",
                    },
                    other_venue.value: {
                        "spread": f"{other_metrics.spread_pct:.3f}%",
                        "cost": f"{other_metrics.estimated_cost_per_trade:.3f}%",
                    }
                }
        
        return results
