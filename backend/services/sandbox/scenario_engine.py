"""
Stress Sandbox - Scenario Engine
================================
Generates repeatable event timelines for stress testing trading agents.

Supports three packs:
- CRASH: Market crashes, flash crashes, volatility spikes
- DEX: Liquidity dry-ups, gas spikes, MEV, token traps
- INFRA: WS drops, API latency, rate limits, stale data

All scenarios are seeded for reproducibility.
"""

import random
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


# ============ Enums ============

class Severity(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"
    APOC = "APOC"


class EventPack(str, Enum):
    CRASH = "crash"
    DEX = "dex"
    INFRA = "infra"


class ScenarioEventType(str, Enum):
    # Crash Events
    CAPITULATION_DUMP = "CAPITULATION_DUMP"
    FLASH_CRASH_WICK = "FLASH_CRASH_WICK"
    GAP_MOVE = "GAP_MOVE"
    VOL_REGIME_SHIFT = "VOL_REGIME_SHIFT"
    
    # DEX Events
    LIQUIDITY_DRY_UP = "LIQUIDITY_DRY_UP"
    GAS_SPIKE = "GAS_SPIKE"
    MEV_RISK_UP = "MEV_RISK_UP"
    TOKEN_TRAP_ROTATION = "TOKEN_TRAP_ROTATION"
    
    # Infra Events
    WS_DROP = "WS_DROP"
    API_LATENCY = "API_LATENCY"
    RATE_LIMIT_429 = "RATE_LIMIT_429"
    STALE_DATA = "STALE_DATA"
    ORDER_ACK_DELAY = "ORDER_ACK_DELAY"


# ============ Models ============

class ScenarioEvent(BaseModel):
    """Single event in a scenario timeline."""
    t: int  # Offset in seconds from start
    event_type: ScenarioEventType
    pack: EventPack
    severity: Severity
    duration_sec: int
    params: Dict[str, Any] = Field(default_factory=dict)
    symbols: List[str] = Field(default_factory=list)
    
    
class ScenarioTimeline(BaseModel):
    """Complete scenario timeline."""
    seed: int
    duration_min: int
    severity: Severity
    packs: Dict[str, bool]
    symbols: List[str]
    events: List[ScenarioEvent]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Event Parameter Ranges by Severity ============

SEVERITY_MULTIPLIERS = {
    Severity.LOW: 0.5,
    Severity.MED: 1.0,
    Severity.HIGH: 1.5,
    Severity.APOC: 2.5,
}

# Event configuration templates
EVENT_CONFIGS = {
    # CRASH EVENTS
    ScenarioEventType.CAPITULATION_DUMP: {
        "pack": EventPack.CRASH,
        "drop_pct_range": (15, 35),  # 15-35% drop
        "duration_range": (120, 1200),  # 2-20 minutes
        "spread_multiplier_range": (2, 5),
        "liquidity_factor_range": (0.2, 0.5),
    },
    ScenarioEventType.FLASH_CRASH_WICK: {
        "pack": EventPack.CRASH,
        "wick_pct_range": (25, 60),  # 25-60% wick
        "wick_duration_range": (30, 120),  # 30s-2min
        "recovery_pct_range": (30, 80),  # 30-80% recovery
        "recovery_duration_range": (120, 600),  # 2-10 min
    },
    ScenarioEventType.GAP_MOVE: {
        "pack": EventPack.CRASH,
        "gap_pct_range": (5, 20),  # 5-20% gap
        "direction_bias": 0.3,  # 30% up, 70% down
    },
    ScenarioEventType.VOL_REGIME_SHIFT: {
        "pack": EventPack.CRASH,
        "vol_multiplier_range": (3, 10),
        "duration_range": (900, 10800),  # 15min - 3h
    },
    
    # DEX EVENTS
    ScenarioEventType.LIQUIDITY_DRY_UP: {
        "pack": EventPack.DEX,
        "reserve_reduction_pct_range": (50, 90),
        "duration_range": (60, 600),
    },
    ScenarioEventType.GAS_SPIKE: {
        "pack": EventPack.DEX,
        "gas_multiplier_range": (3, 20),
        "duration_range": (60, 1800),
    },
    ScenarioEventType.MEV_RISK_UP: {
        "pack": EventPack.DEX,
        "sandwich_prob_range": (0.2, 0.8),
        "duration_range": (120, 1200),
    },
    ScenarioEventType.TOKEN_TRAP_ROTATION: {
        "pack": EventPack.DEX,
        "trap_types": ["fee_on_transfer", "honeypot", "blacklist", "max_tx"],
        "trap_probability": 0.15,
    },
    
    # INFRA EVENTS
    ScenarioEventType.WS_DROP: {
        "pack": EventPack.INFRA,
        "drop_duration_range": (10, 120),
        "reconnect_delay_range": (2, 15),
    },
    ScenarioEventType.API_LATENCY: {
        "pack": EventPack.INFRA,
        "latency_ms_range": (200, 5000),
        "duration_range": (30, 600),
    },
    ScenarioEventType.RATE_LIMIT_429: {
        "pack": EventPack.INFRA,
        "rate_limit_probability": 0.3,
        "backoff_sec_range": (1, 30),
        "duration_range": (60, 600),
    },
    ScenarioEventType.STALE_DATA: {
        "pack": EventPack.INFRA,
        "stale_lag_sec_range": (5, 60),
        "duration_range": (30, 300),
    },
    ScenarioEventType.ORDER_ACK_DELAY: {
        "pack": EventPack.INFRA,
        "ack_delay_ms_range": (500, 10000),
        "duration_range": (60, 600),
    },
}


class ScenarioEngine:
    """
    Generates repeatable stress test scenarios.
    
    Given a seed, always produces the same event timeline.
    """
    
    def __init__(self, default_symbols: List[str] = None):
        self.default_symbols = default_symbols or ["BTCUSDT", "ETHUSDT"]
        
    def _init_rng(self, seed: int) -> random.Random:
        """Initialize a seeded random number generator."""
        return random.Random(seed)
        
    def _apply_severity(self, value: float, severity: Severity, is_negative: bool = False) -> float:
        """Apply severity multiplier to a value."""
        mult = SEVERITY_MULTIPLIERS[severity]
        if is_negative:
            return value * mult
        return value * mult
    
    def _sample_range(self, rng: random.Random, range_tuple: Tuple[float, float], 
                      severity: Severity = None) -> float:
        """Sample a value from a range, optionally applying severity."""
        low, high = range_tuple
        value = rng.uniform(low, high)
        if severity:
            value = self._apply_severity(value, severity)
        return value
    
    def _sample_int_range(self, rng: random.Random, range_tuple: Tuple[int, int],
                          severity: Severity = None) -> int:
        """Sample an integer from a range."""
        return int(self._sample_range(rng, range_tuple, severity))
    
    def _should_trigger_event(self, rng: random.Random, base_prob: float, 
                               severity: Severity) -> bool:
        """Determine if an event should trigger based on probability and severity."""
        adjusted_prob = base_prob * SEVERITY_MULTIPLIERS[severity]
        return rng.random() < min(adjusted_prob, 0.95)
    
    def generate_crash_events(self, rng: random.Random, duration_sec: int, 
                               severity: Severity, symbols: List[str]) -> List[ScenarioEvent]:
        """Generate crash pack events."""
        events = []
        
        # Number of events based on severity and duration
        base_events = max(1, duration_sec // 1800)  # 1 event per 30 min minimum
        num_events = int(base_events * SEVERITY_MULTIPLIERS[severity])
        
        for _ in range(num_events):
            event_type = rng.choice([
                ScenarioEventType.CAPITULATION_DUMP,
                ScenarioEventType.FLASH_CRASH_WICK,
                ScenarioEventType.GAP_MOVE,
                ScenarioEventType.VOL_REGIME_SHIFT,
            ])
            
            config = EVENT_CONFIGS[event_type]
            t = rng.randint(0, max(0, duration_sec - 300))  # Leave some buffer at end
            affected_symbols = rng.sample(symbols, k=min(len(symbols), rng.randint(1, len(symbols))))
            
            params = {}
            if event_type == ScenarioEventType.CAPITULATION_DUMP:
                params = {
                    "drop_pct": self._sample_range(rng, config["drop_pct_range"], severity),
                    "spread_multiplier": self._sample_range(rng, config["spread_multiplier_range"]),
                    "liquidity_factor": self._sample_range(rng, config["liquidity_factor_range"]),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.FLASH_CRASH_WICK:
                params = {
                    "wick_pct": self._sample_range(rng, config["wick_pct_range"], severity),
                    "wick_duration_sec": self._sample_int_range(rng, config["wick_duration_range"]),
                    "recovery_pct": self._sample_range(rng, config["recovery_pct_range"]),
                    "recovery_duration_sec": self._sample_int_range(rng, config["recovery_duration_range"]),
                }
                event_duration = params["wick_duration_sec"] + params["recovery_duration_sec"]
                
            elif event_type == ScenarioEventType.GAP_MOVE:
                params = {
                    "gap_pct": self._sample_range(rng, config["gap_pct_range"], severity),
                    "direction": "up" if rng.random() < config["direction_bias"] else "down",
                }
                event_duration = 1  # Instant
                
            elif event_type == ScenarioEventType.VOL_REGIME_SHIFT:
                params = {
                    "vol_multiplier": self._sample_range(rng, config["vol_multiplier_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
            
            events.append(ScenarioEvent(
                t=t,
                event_type=event_type,
                pack=EventPack.CRASH,
                severity=severity,
                duration_sec=event_duration,
                params=params,
                symbols=affected_symbols,
            ))
        
        return events
    
    def generate_dex_events(self, rng: random.Random, duration_sec: int,
                            severity: Severity, symbols: List[str]) -> List[ScenarioEvent]:
        """Generate DEX pack events."""
        events = []
        
        base_events = max(1, duration_sec // 2400)
        num_events = int(base_events * SEVERITY_MULTIPLIERS[severity])
        
        for _ in range(num_events):
            event_type = rng.choice([
                ScenarioEventType.LIQUIDITY_DRY_UP,
                ScenarioEventType.GAS_SPIKE,
                ScenarioEventType.MEV_RISK_UP,
                ScenarioEventType.TOKEN_TRAP_ROTATION,
            ])
            
            config = EVENT_CONFIGS[event_type]
            t = rng.randint(0, max(0, duration_sec - 120))
            affected_symbols = rng.sample(symbols, k=min(len(symbols), rng.randint(1, 2)))
            
            params = {}
            if event_type == ScenarioEventType.LIQUIDITY_DRY_UP:
                params = {
                    "reserve_reduction_pct": self._sample_range(rng, config["reserve_reduction_pct_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.GAS_SPIKE:
                params = {
                    "gas_multiplier": self._sample_range(rng, config["gas_multiplier_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.MEV_RISK_UP:
                params = {
                    "sandwich_probability": self._sample_range(rng, config["sandwich_prob_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.TOKEN_TRAP_ROTATION:
                params = {
                    "trap_type": rng.choice(config["trap_types"]),
                    "active": True,
                }
                event_duration = duration_sec // 4  # Token traps last a while
            
            events.append(ScenarioEvent(
                t=t,
                event_type=event_type,
                pack=EventPack.DEX,
                severity=severity,
                duration_sec=event_duration,
                params=params,
                symbols=affected_symbols,
            ))
        
        return events
    
    def generate_infra_events(self, rng: random.Random, duration_sec: int,
                              severity: Severity, symbols: List[str]) -> List[ScenarioEvent]:
        """Generate infrastructure pack events."""
        events = []
        
        base_events = max(1, duration_sec // 1200)
        num_events = int(base_events * SEVERITY_MULTIPLIERS[severity])
        
        for _ in range(num_events):
            event_type = rng.choice([
                ScenarioEventType.WS_DROP,
                ScenarioEventType.API_LATENCY,
                ScenarioEventType.RATE_LIMIT_429,
                ScenarioEventType.STALE_DATA,
                ScenarioEventType.ORDER_ACK_DELAY,
            ])
            
            config = EVENT_CONFIGS[event_type]
            t = rng.randint(0, max(0, duration_sec - 60))
            
            params = {}
            if event_type == ScenarioEventType.WS_DROP:
                params = {
                    "drop_duration_sec": self._sample_int_range(rng, config["drop_duration_range"], severity),
                    "reconnect_delay_sec": self._sample_int_range(rng, config["reconnect_delay_range"]),
                }
                event_duration = params["drop_duration_sec"] + params["reconnect_delay_sec"]
                
            elif event_type == ScenarioEventType.API_LATENCY:
                params = {
                    "latency_ms": self._sample_int_range(rng, config["latency_ms_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.RATE_LIMIT_429:
                params = {
                    "rate_limit_probability": config["rate_limit_probability"] * SEVERITY_MULTIPLIERS[severity],
                    "backoff_sec": self._sample_int_range(rng, config["backoff_sec_range"]),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.STALE_DATA:
                params = {
                    "stale_lag_sec": self._sample_int_range(rng, config["stale_lag_sec_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
                
            elif event_type == ScenarioEventType.ORDER_ACK_DELAY:
                params = {
                    "ack_delay_ms": self._sample_int_range(rng, config["ack_delay_ms_range"], severity),
                }
                event_duration = self._sample_int_range(rng, config["duration_range"])
            
            events.append(ScenarioEvent(
                t=t,
                event_type=event_type,
                pack=EventPack.INFRA,
                severity=severity,
                duration_sec=event_duration,
                params=params,
                symbols=symbols,  # Infra affects all symbols
            ))
        
        return events
    
    def generate_timeline(
        self,
        seed: int,
        duration_min: int,
        severity: Severity,
        packs: Dict[str, bool],
        symbols: List[str] = None
    ) -> ScenarioTimeline:
        """
        Generate a complete scenario timeline.
        
        Same seed + inputs = same output (deterministic).
        """
        symbols = symbols or self.default_symbols
        duration_sec = duration_min * 60
        
        # Initialize seeded RNG
        rng = self._init_rng(seed)
        
        events = []
        
        if packs.get("crash", False):
            events.extend(self.generate_crash_events(rng, duration_sec, severity, symbols))
            
        if packs.get("dex", False):
            events.extend(self.generate_dex_events(rng, duration_sec, severity, symbols))
            
        if packs.get("infra", False):
            events.extend(self.generate_infra_events(rng, duration_sec, severity, symbols))
        
        # Sort events by time
        events.sort(key=lambda e: e.t)
        
        logger.info(f"Generated timeline: seed={seed}, {len(events)} events, {duration_min}min, severity={severity}")
        
        return ScenarioTimeline(
            seed=seed,
            duration_min=duration_min,
            severity=severity,
            packs=packs,
            symbols=symbols,
            events=events,
        )
    
    def get_preset_scenarios(self) -> List[Dict[str, Any]]:
        """Return list of preset scenario configurations."""
        return [
            {
                "id": "crash_basic",
                "name": "Market Crash - Basic",
                "description": "Moderate market crash with dumps and volatility spikes",
                "packs": {"crash": True, "dex": False, "infra": False},
                "severity": "MED",
                "duration_min": 120,
            },
            {
                "id": "crash_severe",
                "name": "Black Swan Event",
                "description": "Severe market crash with flash crashes and gaps",
                "packs": {"crash": True, "dex": False, "infra": False},
                "severity": "APOC",
                "duration_min": 240,
            },
            {
                "id": "dex_chaos",
                "name": "DEX Chaos",
                "description": "DEX-specific issues: liquidity, MEV, token traps",
                "packs": {"crash": False, "dex": True, "infra": False},
                "severity": "HIGH",
                "duration_min": 60,
            },
            {
                "id": "infra_storm",
                "name": "Infrastructure Storm",
                "description": "WS drops, latency spikes, rate limits",
                "packs": {"crash": False, "dex": False, "infra": True},
                "severity": "HIGH",
                "duration_min": 90,
            },
            {
                "id": "apocalypse",
                "name": "Full Apocalypse",
                "description": "All packs combined at maximum severity",
                "packs": {"crash": True, "dex": True, "infra": True},
                "severity": "APOC",
                "duration_min": 180,
            },
            {
                "id": "sniper_hardening",
                "name": "Sniper Hardening Test",
                "description": "DEX traps + MEV focused for sniper training",
                "packs": {"crash": False, "dex": True, "infra": True},
                "severity": "HIGH",
                "duration_min": 60,
            },
        ]
