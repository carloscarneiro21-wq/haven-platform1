"""
Stress Sandbox - Synthetic Price Feed
=====================================
Generates synthetic market data (ticks + candles) for stress testing.

Features:
- Stochastic price model with configurable volatility
- Event-driven price overrides (crashes, gaps, wicks)
- Tick stream for WebSocket simulation
- Candle aggregation for charts
"""

import random
import math
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import logging

from services.sandbox.scenario_engine import (
    ScenarioEvent, ScenarioEventType, Severity, SEVERITY_MULTIPLIERS
)

logger = logging.getLogger(__name__)


# ============ Models ============

class PriceTick(BaseModel):
    """Single price update."""
    symbol: str
    timestamp: datetime
    price: float
    bid: float
    ask: float
    spread_pct: float
    volume: float
    liquidity_factor: float = 1.0  # 1.0 = normal, <1 = reduced
    is_gap: bool = False
    
    
class Candle(BaseModel):
    """OHLCV candle."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int = 0


class MarketSnapshot(BaseModel):
    """Current market state for a symbol."""
    symbol: str
    timestamp: datetime
    mid_price: float
    bid: float
    ask: float
    spread_pct: float
    liquidity_factor: float
    volatility: float
    is_stale: bool = False
    stale_age_sec: int = 0


# ============ Price Model ============

class SyntheticPriceFeed:
    """
    Generates synthetic price data with event-driven chaos injection.
    
    Uses geometric Brownian motion as base, with regime shifts and
    explicit event overrides for crash scenarios.
    """
    
    # Base parameters
    DEFAULT_VOLATILITY = 0.02  # 2% daily vol
    TICK_INTERVAL_MS = 100  # 100ms between ticks
    BASE_SPREAD_BPS = 5  # 0.05% spread
    
    def __init__(self, symbols: List[str], starting_prices: Dict[str, float] = None):
        self.symbols = symbols
        self.starting_prices = starting_prices or {
            "BTCUSDT": 42000.0,
            "ETHUSDT": 2200.0,
            "BNBUSDT": 300.0,
            "SOLUSDT": 100.0,
        }
        
        # Current state per symbol
        self._state: Dict[str, Dict[str, Any]] = {}
        self._tick_history: Dict[str, List[PriceTick]] = {}
        self._candles: Dict[str, List[Candle]] = {}
        
        # Active events
        self._active_events: List[Tuple[ScenarioEvent, datetime]] = []
        
        # RNG for reproducibility
        self._rng: Optional[random.Random] = None
        
        # Callbacks
        self._tick_callbacks: List[Callable] = []
        
        # Control
        self._running = False
        self._sim_time: Optional[datetime] = None
        
    def initialize(self, seed: int, start_time: datetime = None):
        """Initialize the feed with a seed for reproducibility."""
        self._rng = random.Random(seed)
        self._sim_time = start_time or datetime.now(timezone.utc)
        
        for symbol in self.symbols:
            base_price = self.starting_prices.get(symbol, 1000.0)
            spread = base_price * (self.BASE_SPREAD_BPS / 10000)
            
            self._state[symbol] = {
                "price": base_price,
                "bid": base_price - spread / 2,
                "ask": base_price + spread / 2,
                "volatility": self.DEFAULT_VOLATILITY,
                "vol_multiplier": 1.0,
                "spread_multiplier": 1.0,
                "liquidity_factor": 1.0,
                "stale": False,
                "stale_since": None,
                "in_crash": False,
                "crash_target": None,
                "crash_speed": None,
            }
            self._tick_history[symbol] = []
            self._candles[symbol] = []
            
        logger.info(f"SyntheticPriceFeed initialized: {len(self.symbols)} symbols, seed={seed}")
    
    def inject_event(self, event: ScenarioEvent, start_time: datetime):
        """Inject a scenario event into the feed."""
        end_time = start_time + timedelta(seconds=event.duration_sec)
        self._active_events.append((event, end_time))
        
        # Apply immediate effects
        for symbol in event.symbols:
            if symbol not in self._state:
                continue
                
            state = self._state[symbol]
            
            if event.event_type == ScenarioEventType.CAPITULATION_DUMP:
                state["in_crash"] = True
                state["crash_target"] = state["price"] * (1 - event.params["drop_pct"] / 100)
                state["crash_speed"] = event.params["drop_pct"] / event.duration_sec
                state["spread_multiplier"] = event.params["spread_multiplier"]
                state["liquidity_factor"] = event.params["liquidity_factor"]
                
            elif event.event_type == ScenarioEventType.FLASH_CRASH_WICK:
                # Immediate wick down
                state["in_crash"] = True
                state["crash_target"] = state["price"] * (1 - event.params["wick_pct"] / 100)
                state["crash_speed"] = event.params["wick_pct"] / event.params["wick_duration_sec"]
                state["spread_multiplier"] = 5.0
                state["liquidity_factor"] = 0.1
                
            elif event.event_type == ScenarioEventType.GAP_MOVE:
                # Instant gap
                gap_mult = 1 + (event.params["gap_pct"] / 100)
                if event.params["direction"] == "down":
                    gap_mult = 1 - (event.params["gap_pct"] / 100)
                state["price"] *= gap_mult
                
            elif event.event_type == ScenarioEventType.VOL_REGIME_SHIFT:
                state["vol_multiplier"] = event.params["vol_multiplier"]
                
            elif event.event_type == ScenarioEventType.LIQUIDITY_DRY_UP:
                state["liquidity_factor"] = 1 - (event.params["reserve_reduction_pct"] / 100)
                state["spread_multiplier"] = 1 / state["liquidity_factor"]
                
            elif event.event_type == ScenarioEventType.STALE_DATA:
                state["stale"] = True
                state["stale_since"] = self._sim_time
                
        logger.debug(f"Injected event: {event.event_type} affecting {event.symbols}")
    
    def _cleanup_expired_events(self):
        """Remove expired events and reset their effects."""
        now = self._sim_time
        
        still_active = []
        for event, end_time in self._active_events:
            if now >= end_time:
                # Event expired, reset effects
                for symbol in event.symbols:
                    if symbol not in self._state:
                        continue
                    state = self._state[symbol]
                    
                    if event.event_type in [ScenarioEventType.CAPITULATION_DUMP, 
                                            ScenarioEventType.FLASH_CRASH_WICK]:
                        state["in_crash"] = False
                        state["crash_target"] = None
                        state["crash_speed"] = None
                        state["spread_multiplier"] = 1.0
                        state["liquidity_factor"] = 1.0
                        
                    elif event.event_type == ScenarioEventType.VOL_REGIME_SHIFT:
                        state["vol_multiplier"] = 1.0
                        
                    elif event.event_type == ScenarioEventType.LIQUIDITY_DRY_UP:
                        state["liquidity_factor"] = 1.0
                        state["spread_multiplier"] = 1.0
                        
                    elif event.event_type == ScenarioEventType.STALE_DATA:
                        state["stale"] = False
                        state["stale_since"] = None
            else:
                still_active.append((event, end_time))
                
        self._active_events = still_active
    
    def _generate_price_move(self, symbol: str, dt_sec: float) -> float:
        """Generate a single price move using GBM with regime volatility."""
        state = self._state[symbol]
        
        # Base volatility (annualized to per-second)
        vol = state["volatility"] * state["vol_multiplier"]
        vol_per_sec = vol / math.sqrt(365 * 24 * 3600)
        
        # Random component (normal distribution)
        z = self._rng.gauss(0, 1)
        
        # GBM: dS = S * (mu*dt + sigma*sqrt(dt)*Z)
        # Simplified: no drift in sandbox
        move = vol_per_sec * math.sqrt(dt_sec) * z
        
        # Apply crash dynamics if active
        if state["in_crash"] and state["crash_target"]:
            current = state["price"]
            target = state["crash_target"]
            speed = state.get("crash_speed", 0.01)
            
            # Move towards target
            direction = -1 if target < current else 1
            crash_move = direction * (speed / 100) * dt_sec * abs(current)
            
            # Don't overshoot target
            if direction < 0:
                move = min(move, crash_move)
            else:
                move = max(move, crash_move)
        
        return move
    
    def generate_tick(self, symbol: str) -> Optional[PriceTick]:
        """Generate a single price tick for a symbol."""
        if symbol not in self._state:
            return None
            
        state = self._state[symbol]
        
        # Check if data is stale
        if state["stale"]:
            stale_age = (self._sim_time - state["stale_since"]).total_seconds() if state["stale_since"] else 0
            # Return last known price but marked as stale
            last_tick = self._tick_history[symbol][-1] if self._tick_history[symbol] else None
            if last_tick:
                return PriceTick(
                    symbol=symbol,
                    timestamp=self._sim_time,
                    price=last_tick.price,
                    bid=last_tick.bid,
                    ask=last_tick.ask,
                    spread_pct=last_tick.spread_pct,
                    volume=0,
                    liquidity_factor=state["liquidity_factor"],
                    is_gap=False,
                )
            return None
        
        # Generate price move
        dt = self.TICK_INTERVAL_MS / 1000
        move = self._generate_price_move(symbol, dt)
        
        # Update price
        new_price = max(0.01, state["price"] * (1 + move))
        state["price"] = new_price
        
        # Calculate spread
        base_spread = new_price * (self.BASE_SPREAD_BPS / 10000)
        actual_spread = base_spread * state["spread_multiplier"]
        spread_pct = (actual_spread / new_price) * 100
        
        bid = new_price - actual_spread / 2
        ask = new_price + actual_spread / 2
        
        # Update state
        state["bid"] = bid
        state["ask"] = ask
        
        # Generate volume (random)
        volume = self._rng.uniform(0.1, 10) * state["liquidity_factor"]
        
        tick = PriceTick(
            symbol=symbol,
            timestamp=self._sim_time,
            price=new_price,
            bid=bid,
            ask=ask,
            spread_pct=spread_pct,
            volume=volume,
            liquidity_factor=state["liquidity_factor"],
            is_gap=False,
        )
        
        self._tick_history[symbol].append(tick)
        
        return tick
    
    def advance_time(self, ms: int = None):
        """Advance simulation time."""
        ms = ms or self.TICK_INTERVAL_MS
        self._sim_time += timedelta(milliseconds=ms)
        self._cleanup_expired_events()
    
    def generate_ticks_for_duration(self, duration_sec: int) -> Dict[str, List[PriceTick]]:
        """Generate all ticks for a duration."""
        ticks = {symbol: [] for symbol in self.symbols}
        
        num_ticks = int(duration_sec * 1000 / self.TICK_INTERVAL_MS)
        
        for _ in range(num_ticks):
            self.advance_time()
            for symbol in self.symbols:
                tick = self.generate_tick(symbol)
                if tick:
                    ticks[symbol].append(tick)
        
        return ticks
    
    def aggregate_candles(self, symbol: str, interval_sec: int = 60) -> List[Candle]:
        """Aggregate ticks into candles."""
        history = self._tick_history.get(symbol, [])
        if not history:
            return []
        
        candles = []
        current_candle = None
        candle_start = None
        
        for tick in history:
            tick_time = tick.timestamp
            
            # Determine candle boundary
            candle_boundary = tick_time.replace(second=0, microsecond=0)
            if interval_sec >= 3600:
                candle_boundary = candle_boundary.replace(minute=0)
            
            if candle_start is None or candle_boundary > candle_start:
                # Save previous candle
                if current_candle:
                    candles.append(current_candle)
                
                # Start new candle
                candle_start = candle_boundary
                current_candle = Candle(
                    symbol=symbol,
                    timestamp=candle_start,
                    open=tick.price,
                    high=tick.price,
                    low=tick.price,
                    close=tick.price,
                    volume=tick.volume,
                    trades=1,
                )
            else:
                # Update current candle
                current_candle.high = max(current_candle.high, tick.price)
                current_candle.low = min(current_candle.low, tick.price)
                current_candle.close = tick.price
                current_candle.volume += tick.volume
                current_candle.trades += 1
        
        # Don't forget last candle
        if current_candle:
            candles.append(current_candle)
        
        return candles
    
    def get_market_snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        """Get current market state for a symbol."""
        if symbol not in self._state:
            return None
            
        state = self._state[symbol]
        
        stale_age = 0
        if state["stale"] and state["stale_since"]:
            stale_age = int((self._sim_time - state["stale_since"]).total_seconds())
        
        return MarketSnapshot(
            symbol=symbol,
            timestamp=self._sim_time,
            mid_price=state["price"],
            bid=state["bid"],
            ask=state["ask"],
            spread_pct=(state["ask"] - state["bid"]) / state["price"] * 100,
            liquidity_factor=state["liquidity_factor"],
            volatility=state["volatility"] * state["vol_multiplier"],
            is_stale=state["stale"],
            stale_age_sec=stale_age,
        )
    
    def get_all_snapshots(self) -> Dict[str, MarketSnapshot]:
        """Get market snapshots for all symbols."""
        return {symbol: self.get_market_snapshot(symbol) for symbol in self.symbols}
    
    def get_price(self, symbol: str) -> float:
        """Get current mid price for a symbol."""
        if symbol not in self._state:
            return 0.0
        return self._state[symbol]["price"]
    
    def get_bid_ask(self, symbol: str) -> Tuple[float, float]:
        """Get current bid/ask for a symbol."""
        if symbol not in self._state:
            return (0.0, 0.0)
        state = self._state[symbol]
        return (state["bid"], state["ask"])
