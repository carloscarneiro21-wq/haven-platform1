"""
System Configuration Service for Capital Growth Module
=======================================================

Centralized configuration for:
- Risk budgets (Core/Edge/Reserve)
- Regime thresholds
- Guardian limits (daily loss, weekly drawdown)
- Viability multipliers
- Agent concurrency rules
- Default behavior for micro-capital accounts (100€)

All changes are audited.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum
import copy

logger = logging.getLogger(__name__)


# ============ Enums ============

class MarketRegime(str, Enum):
    """Market regime types detected by router."""
    RANGE = "RANGE"          # Sideways, good for MM
    TREND = "TREND"          # Directional, good for MOM
    HIGH_VOL = "HIGH_VOL"    # High volatility, careful
    CHOP = "CHOP"            # Choppy, avoid trading


class PrimaryAgent(str, Enum):
    """Primary agent types for growth module."""
    MM = "MM"          # Market Maker
    MOM = "MOM"        # Momentum
    PAUSE = "PAUSE"    # No trading


# ============ Config Models ============

class RiskBudgetConfig(BaseModel):
    """Risk budget allocation percentages."""
    core_pct: float = Field(default=60.0, ge=0, le=100, description="Core bucket % for MM (steady)")
    edge_pct: float = Field(default=40.0, ge=0, le=100, description="Edge bucket % for MOM (acceleration)")
    reserve_pct: float = Field(default=0.0, ge=0, le=20, description="Reserve bucket % (unused)")


class GuardianConfig(BaseModel):
    """Guardian limits for risk management."""
    daily_loss_limit_pct: float = Field(default=-2.0, le=0, description="Daily kill switch trigger %")
    weekly_drawdown_limit_pct: float = Field(default=-5.0, le=0, description="Weekly drawdown cap %")
    max_spread_pct: float = Field(default=0.15, ge=0, description="Max spread % to allow trading")
    max_slippage_pct: float = Field(default=0.10, ge=0, description="Max slippage % estimate")
    min_latency_quality: float = Field(default=0.8, ge=0, le=1, description="Min data quality score")
    cooldown_after_loss_minutes: int = Field(default=30, ge=5, description="Cooldown after hitting daily limit")
    pause_on_spread_widening: bool = Field(default=True, description="Pause if spread widens suddenly")
    pause_on_high_latency: bool = Field(default=True, description="Pause if data latency is high")


class ViabilityConfig(BaseModel):
    """Viability filter thresholds for micro-capital."""
    default_multiplier: float = Field(default=2.0, ge=1.5, description="Default: edge > cost * multiplier")
    mm_multiplier: float = Field(default=2.0, ge=1.5, description="MM viability multiplier")
    mom_conservative_multiplier: float = Field(default=2.5, ge=1.5, description="MOM conservative multiplier")
    mom_standard_multiplier: float = Field(default=2.2, ge=1.5, description="MOM standard multiplier")
    mom_aggressive_multiplier: float = Field(default=2.0, ge=1.5, description="MOM aggressive multiplier")
    mom_defensive_multiplier: float = Field(default=3.0, ge=1.5, description="MOM defensive/recovery multiplier")
    min_expected_profit_eur: float = Field(default=0.05, ge=0.01, description="Min expected profit per trade")


class RegimeThresholds(BaseModel):
    """Thresholds for market regime detection."""
    # ATR% thresholds
    atr_low_pct: float = Field(default=0.5, description="ATR% below this = low volatility")
    atr_high_pct: float = Field(default=2.0, description="ATR% above this = high volatility")
    
    # Trend thresholds (ADX or MA slope)
    adx_trend_threshold: float = Field(default=25.0, description="ADX above this = trending")
    adx_strong_trend: float = Field(default=35.0, description="ADX above this = strong trend")
    
    # Volume thresholds
    volume_spike_multiplier: float = Field(default=2.0, description="Volume > avg * this = spike")
    volume_dry_threshold: float = Field(default=0.5, description="Volume < avg * this = dry")
    
    # Spread thresholds
    spread_tight_pct: float = Field(default=0.05, description="Spread below this = tight")
    spread_wide_pct: float = Field(default=0.15, description="Spread above this = wide")


class AgentConcurrencyConfig(BaseModel):
    """Rules for agent concurrency."""
    allow_only_one_primary: bool = Field(default=True, description="Only MM OR MOM, not both")
    min_capital_for_multi: float = Field(default=500.0, description="Min € to allow multiple agents")
    owner_can_override: bool = Field(default=True, description="OWNER can bypass restrictions")
    max_concurrent_agents: int = Field(default=1, ge=1, le=5, description="Max agents at once")


class PairWhitelistConfig(BaseModel):
    """Whitelisted pairs for trading."""
    enabled: bool = Field(default=True, description="Enforce whitelist")
    pairs: List[str] = Field(
        default=[
            "BTC/USDT", "ETH/USDT", "BNB/USDT",  # Binance
            "BTC/EUR", "ETH/EUR"                   # Kraken
        ],
        description="Allowed trading pairs"
    )
    auto_select_best_venue: bool = Field(default=True, description="Let Pair Advisor choose venue")


class DefaultsConfig(BaseModel):
    """Default behavior settings."""
    default_mode: str = Field(default="paper", description="paper or live")
    default_capital_eur: float = Field(default=100.0, description="Default starting capital")
    router_enabled: bool = Field(default=True, description="Auto-select agent via router")
    auto_rebalance: bool = Field(default=True, description="Auto-rebalance buckets")


# ============ Main System Config ============

class SystemConfig(BaseModel):
    """Master configuration for the Capital Growth Module."""
    id: str = Field(default="growth_config_v1", description="Config document ID")
    version: int = Field(default=1, description="Config schema version")
    
    # Sub-configs
    risk_budget: RiskBudgetConfig = Field(default_factory=RiskBudgetConfig)
    guardian: GuardianConfig = Field(default_factory=GuardianConfig)
    viability: ViabilityConfig = Field(default_factory=ViabilityConfig)
    regime_thresholds: RegimeThresholds = Field(default_factory=RegimeThresholds)
    concurrency: AgentConcurrencyConfig = Field(default_factory=AgentConcurrencyConfig)
    pair_whitelist: PairWhitelistConfig = Field(default_factory=PairWhitelistConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    
    # Enabled agents
    mm_enabled: bool = Field(default=True, description="Market Maker agent enabled")
    mom_enabled: bool = Field(default=True, description="Momentum agent enabled")
    
    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


# ============ Default Config Factory ============

def get_default_system_config() -> SystemConfig:
    """Get default system configuration."""
    return SystemConfig(
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ============ System Config Service ============

class SystemConfigService:
    """
    Service for managing system configuration.
    
    Features:
    - Single config document in MongoDB
    - All changes audited
    - Supports per-user overrides (future)
    """
    
    COLLECTION = "system_configs"
    CONFIG_ID = "growth_config_v1"
    
    def __init__(self, db: AsyncIOMotorDatabase, audit_service=None):
        self.db = db
        self.collection = db[self.COLLECTION]
        self.audit_service = audit_service
        self._config_cache: Optional[SystemConfig] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the service and ensure config exists."""
        if self._initialized:
            return
        
        # Check if config exists
        existing = await self.collection.find_one({"id": self.CONFIG_ID}, {"_id": 0})
        
        if not existing:
            # Create default config
            default = get_default_system_config()
            doc = default.model_dump()
            
            # Convert datetime to ISO string for MongoDB
            if doc.get("created_at"):
                doc["created_at"] = doc["created_at"].isoformat() if hasattr(doc["created_at"], 'isoformat') else doc["created_at"]
            if doc.get("updated_at"):
                doc["updated_at"] = doc["updated_at"].isoformat() if hasattr(doc["updated_at"], 'isoformat') else doc["updated_at"]
            
            await self.collection.insert_one(doc)
            self._config_cache = default
            logger.info("System config initialized with defaults")
        else:
            self._config_cache = SystemConfig(**existing)
            logger.info("System config loaded from database")
        
        self._initialized = True
    
    async def get_config(self) -> SystemConfig:
        """Get the current system configuration."""
        await self.initialize()
        
        # Refresh from DB
        doc = await self.collection.find_one({"id": self.CONFIG_ID}, {"_id": 0})
        if doc:
            self._config_cache = SystemConfig(**doc)
        
        return self._config_cache
    
    async def update_config(
        self,
        updates: Dict[str, Any],
        user_id: str,
        username: str,
        role: str,
    ) -> SystemConfig:
        """
        Update system configuration.
        
        Args:
            updates: Dict of fields to update (supports nested paths)
            user_id: User making the change
            username: Username for audit
            role: User role for audit
        
        Returns:
            Updated SystemConfig
        """
        await self.initialize()
        
        # Get current config
        current = await self.get_config()
        # Use mode='json' to ensure proper serialization of datetime/enums
        current_dict = current.model_dump(mode='json')
        
        # Store old values for audit
        old_values = {}
        
        # Apply updates
        for path, value in updates.items():
            parts = path.split(".")
            target = current_dict
            old_target = copy.deepcopy(current_dict)
            
            # Navigate to parent
            for part in parts[:-1]:
                if part in target:
                    target = target[part]
                    old_target = old_target[part]
                else:
                    target[part] = {}
                    target = target[part]
                    old_target = {}
            
            # Store old value
            old_values[path] = old_target.get(parts[-1]) if old_target else None
            
            # Apply new value - convert Enum to string if needed
            if hasattr(value, 'value'):
                value = value.value
            target[parts[-1]] = value
        
        # Update metadata
        current_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        current_dict["updated_by"] = user_id
        
        # Save to DB
        await self.collection.replace_one(
            {"id": self.CONFIG_ID},
            current_dict,
            upsert=True
        )
        
        # Audit log
        if self.audit_service:
            await self.audit_service.log(
                user_id=user_id,
                username=username,
                role=role,
                action="settings.update",
                resource_type="system_config",
                resource_id=self.CONFIG_ID,
                metadata={
                    "updates": updates,
                    "old_values": old_values,
                }
            )
        
        # Update cache
        self._config_cache = SystemConfig(**current_dict)
        logger.info(f"System config updated by {username}: {list(updates.keys())}")
        
        return self._config_cache
    
    async def reset_to_defaults(
        self,
        user_id: str,
        username: str,
        role: str,
    ) -> SystemConfig:
        """Reset configuration to defaults."""
        default = get_default_system_config()
        default.updated_at = datetime.now(timezone.utc)
        default.updated_by = user_id
        
        doc = default.model_dump()
        if doc.get("created_at"):
            doc["created_at"] = doc["created_at"].isoformat() if hasattr(doc["created_at"], 'isoformat') else doc["created_at"]
        if doc.get("updated_at"):
            doc["updated_at"] = doc["updated_at"].isoformat() if hasattr(doc["updated_at"], 'isoformat') else doc["updated_at"]
        
        await self.collection.replace_one(
            {"id": self.CONFIG_ID},
            doc,
            upsert=True
        )
        
        # Audit log
        if self.audit_service:
            await self.audit_service.log(
                user_id=user_id,
                username=username,
                role=role,
                action="settings.update",
                resource_type="system_config",
                resource_id=self.CONFIG_ID,
                metadata={"action": "reset_to_defaults"}
            )
        
        self._config_cache = default
        logger.info(f"System config reset to defaults by {username}")
        
        return self._config_cache
    
    def to_dict(self, config: SystemConfig) -> Dict[str, Any]:
        """Convert config to dict for API response."""
        return config.model_dump(mode='json')


# ============ Global Instance ============

_system_config_service: Optional[SystemConfigService] = None


def get_system_config_service() -> Optional[SystemConfigService]:
    """Get global system config service instance."""
    return _system_config_service


def set_system_config_service(service: SystemConfigService) -> None:
    """Set global system config service instance."""
    global _system_config_service
    _system_config_service = service
    logger.info("SystemConfigService set globally")
