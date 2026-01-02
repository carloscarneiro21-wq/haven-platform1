"""
Learning Data Models
====================
MongoDB collection schemas for persisted learning from sandbox runs.

Collections:
- agent_profiles: Active profile per agent
- agent_profile_versions: Versioned learned profiles
- learning_runs: Sandbox runs with learning outputs
- learning_metrics: Per-agent/strategy metrics per run
- promotion_requests: Sandbox → Live promotion workflow
- guardian_rule_versions: Versioned guardian rules
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum
import uuid


# ============ Enums ============

class ProfileSource(str, Enum):
    SANDBOX = "sandbox"
    MANUAL = "manual"
    LIVE_OBSERVATION = "live_observation"


class PromotionTarget(str, Enum):
    PAPER_LIVE = "paper_live"
    LIVE = "live"


class PromotionStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class GuardianScope(str, Enum):
    GLOBAL = "global"
    STRATEGY = "strategy"
    AGENT = "agent"


# ============ Profile Models ============

class ProfileConstraints(BaseModel):
    """Universal safety constraints."""
    max_daily_dd_pct: float = 5.0
    max_weekly_dd_pct: float = 10.0
    max_slippage_pct: float = 1.0
    max_spread_pct: float = 0.5
    max_trades_per_min: int = 10
    cooldown_after_loss_sec: int = 60
    require_approval: bool = True
    kill_switch_on_faults: bool = True


class DexRules(BaseModel):
    """DEX-specific constraints."""
    min_pool_liquidity_usd: float = 50000
    max_price_impact_pct: float = 2.0
    max_tax_pct: float = 5.0
    disallow_fee_on_transfer: bool = True
    disallow_honeypot_signals: bool = True
    allowed_routers: List[str] = Field(default_factory=list)
    approval_policy: str = "exact"  # exact, bucket, infinite_disallowed


class InfraRules(BaseModel):
    """Infrastructure stability requirements."""
    ws_drop_tolerance_per_hour: int = 5
    max_api_latency_ms: int = 2000
    max_429_per_min: int = 3
    stale_data_limit_sec: int = 30


class SniperParams(BaseModel):
    """Sniper strategy parameters."""
    min_pool_liquidity_usd: float = 50000
    min_initial_liquidity_lock_min: int = 5
    max_tax_pct: float = 5.0
    max_price_impact_pct: float = 3.0
    max_slippage_pct: float = 2.0
    max_trade_size_pct_of_liquidity: float = 1.0
    entry_delay_sec: int = 30
    require_sell_simulation: bool = True
    require_honeypot_checks: bool = True
    block_if_blacklist_signals: bool = True
    block_if_trading_toggle_risk: bool = True
    max_retries: int = 3
    retry_backoff_ms: int = 500


class GridParams(BaseModel):
    """Grid strategy parameters."""
    levels: int = 10
    spacing_pct: float = 1.0
    max_position: float = 1000
    cooldown_sec: int = 60
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 3.0


class MomentumParams(BaseModel):
    """Momentum strategy parameters."""
    entry_threshold: float = 0.02
    exit_threshold: float = 0.01
    position_size: float = 100
    max_trades_per_hour: int = 5


# ============ Agent Profile Version ============

class AgentProfileVersion(BaseModel):
    """Versioned learned profile from sandbox."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_id: str
    strategy_id: str
    source: ProfileSource
    source_run_id: Optional[str] = None
    version: int = 1
    label: str = ""
    tags: List[str] = Field(default_factory=list)
    
    # Strategy params (polymorphic based on strategy_id)
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Universal constraints
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)
    
    # DEX rules
    dex_rules: DexRules = Field(default_factory=DexRules)
    
    # Infra rules
    infra_rules: InfraRules = Field(default_factory=InfraRules)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentProfile(BaseModel):
    """Active profile selection for an agent."""
    agent_id: str
    strategy_id: str
    profile_active_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Learning Run Models ============

class LearningRunSummary(BaseModel):
    """Summary metrics from a learning run."""
    survival_score: float = 0
    max_dd_pct: float = 0
    time_to_stabilize_sec: int = 0
    slippage_p95: float = 0
    spread_p95: float = 0
    ws_downtime_sec: float = 0
    mev_hits_est: int = 0


class LearningRun(BaseModel):
    """Learning run record."""
    run_id: str
    seed: int
    severity: str
    packs: Dict[str, bool]
    symbols: List[str]
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str = "running"  # completed, stopped, failed
    created_profiles: List[str] = Field(default_factory=list)
    summary: LearningRunSummary = Field(default_factory=LearningRunSummary)


class LearningMetrics(BaseModel):
    """Per-agent metrics from a learning run."""
    run_id: str
    agent_id: str
    strategy_id: str
    profile_id: str
    symbol: str
    
    metrics: Dict[str, Any] = Field(default_factory=lambda: {
        "pnl_pct": 0,
        "max_dd_pct": 0,
        "sharpe_like": None,
        "win_rate": 0,
        "trades": 0,
        "blocked_trades": 0,
        "halt_count": 0,
        "slippage_avg": 0,
        "slippage_p95": 0,
        "spread_avg": 0,
        "spread_p95": 0,
        "infra_faults": 0,
        "mev_hits_est": 0,
    })
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Promotion Models ============

class PromotionRequest(BaseModel):
    """Promotion request from Sandbox to Live."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    requested_by: str
    agent_id: str
    strategy_id: str
    from_profile_id: str
    to_profile_id: str
    target_env: PromotionTarget
    status: PromotionStatus = PromotionStatus.DRAFT
    approval_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Guardian Rule Models ============

class GuardianRules(BaseModel):
    """Guardian rule configuration."""
    dd_intraday_limit_pct: float = 5.0
    slippage_p95_limit_pct: float = 1.5
    infra_fault_limit: int = 5
    block_token_traps: bool = True
    require_approval_on_warn: bool = True


class GuardianRuleVersion(BaseModel):
    """Versioned guardian ruleset."""
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    version: int = 1
    scope: GuardianScope
    strategy_id: Optional[str] = None
    agent_id: Optional[str] = None
    rules: GuardianRules = Field(default_factory=GuardianRules)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Collection Helpers ============

def get_collection_schemas() -> Dict[str, Dict[str, Any]]:
    """Return MongoDB collection schemas and indexes."""
    return {
        "agent_profiles": {
            "indexes": [
                {"keys": [("agent_id", 1), ("strategy_id", 1)], "unique": True}
            ]
        },
        "agent_profile_versions": {
            "indexes": [
                {"keys": [("agent_id", 1), ("strategy_id", 1), ("version", 1)], "unique": True},
                {"keys": [("profile_id", 1)], "unique": True}
            ]
        },
        "learning_runs": {
            "indexes": [
                {"keys": [("run_id", 1)], "unique": True}
            ]
        },
        "learning_metrics": {
            "indexes": [
                {"keys": [("run_id", 1), ("agent_id", 1), ("strategy_id", 1)]},
                {"keys": [("agent_id", 1), ("strategy_id", 1), ("profile_id", 1)]}
            ]
        },
        "promotion_requests": {
            "indexes": [
                {"keys": [("request_id", 1)], "unique": True},
                {"keys": [("agent_id", 1), ("strategy_id", 1), ("status", 1)]}
            ]
        },
        "guardian_rule_versions": {
            "indexes": [
                {"keys": [("scope", 1), ("strategy_id", 1), ("agent_id", 1), ("version", 1)]}
            ]
        },
        # Existing sandbox collections
        "sandbox_runs": {
            "indexes": [
                {"keys": [("run_id", 1)], "unique": True}
            ]
        },
        "sandbox_events": {
            "indexes": [
                {"keys": [("run_id", 1), ("timestamp", 1)]}
            ]
        },
        "sandbox_executions": {
            "indexes": [
                {"keys": [("run_id", 1)]}
            ]
        },
        "sandbox_reports": {
            "indexes": [
                {"keys": [("run_id", 1)], "unique": True}
            ]
        },
    }


async def ensure_indexes(db) -> None:
    """Ensure all required indexes exist."""
    schemas = get_collection_schemas()
    
    for collection_name, schema in schemas.items():
        collection = db[collection_name]
        for index_spec in schema.get("indexes", []):
            try:
                await collection.create_index(
                    index_spec["keys"],
                    unique=index_spec.get("unique", False)
                )
            except Exception as e:
                # Index might already exist
                pass
