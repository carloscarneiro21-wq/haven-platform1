"""
Agent Presets V2 for Capital Growth Module
==========================================

Preset sets for:
- MarketMakerAgent (MM): 5 presets
- MomentumAgent (MOM): 4 presets

Features:
- System defaults (immutable)
- User custom presets (editable)
- Enable/disable without deletion
- Audit logging on all changes
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import copy

logger = logging.getLogger(__name__)


# ============ Enums ============

class AgentTypeV2(str, Enum):
    """Agent types for growth module."""
    MM = "MM"      # Market Maker
    MOM = "MOM"    # Momentum


class PresetType(str, Enum):
    """Preset ownership type."""
    SYSTEM = "system"  # Immutable system defaults
    CUSTOM = "custom"  # User-customized


# ============ MM Preset Schema ============

class MMGridConfig(BaseModel):
    """Grid configuration for Market Maker."""
    grid_width_total_pct: float = Field(default=1.5, ge=0.0, le=5.0, description="Total grid width %")
    grid_levels: int = Field(default=12, ge=0, le=30, description="Number of grid levels")
    spacing_type: str = Field(default="geometric", description="arithmetic or geometric")
    spacing_factor: float = Field(default=1.0, ge=0.0, le=2.0, description="Spacing density factor")


class MMInventoryConfig(BaseModel):
    """Inventory control for Market Maker."""
    target_ratio: float = Field(default=0.5, ge=0.0, le=1.0, description="Target base/quote ratio (0.5 = 50/50)")
    skew_max_pct: float = Field(default=12.0, ge=0, le=30, description="Max inventory skew %")
    rebalance_threshold_pct: float = Field(default=5.0, ge=0, le=20, description="Rebalance when skew exceeds this")


class MMExecutionConfig(BaseModel):
    """Execution rules for Market Maker."""
    maker_only: bool = Field(default=True, description="Only post maker orders")
    maker_preferred: bool = Field(default=True, description="Prefer maker, allow taker if needed")
    taker_allowed_spread_pct: float = Field(default=0.04, ge=0, le=0.2, description="Allow taker if spread <= this")
    rebalance_interval_seconds: int = Field(default=60, ge=15, le=300, description="Grid rebalance interval")
    cancel_stale_after_seconds: int = Field(default=120, ge=30, le=600, description="Cancel unfilled orders after")


class MMSafetyConfig(BaseModel):
    """Safety features for Market Maker."""
    trend_filter_enabled: bool = Field(default=True, description="Pause if strong trend detected")
    trend_adx_threshold: float = Field(default=30.0, ge=20, le=50, description="ADX threshold for trend pause")
    daily_kill_pct: float = Field(default=-2.0, le=0, description="Daily loss % to trigger kill switch")
    pause_on_spread_widening: bool = Field(default=False, description="Pause if spread widens suddenly")
    cooldown_after_loss_minutes: int = Field(default=30, ge=10, le=120, description="Cooldown after loss")


class MMViabilityConfig(BaseModel):
    """Viability requirements for Market Maker."""
    edge_cost_multiplier: float = Field(default=2.0, ge=1.0, le=15.0, description="Edge > cost * multiplier")
    min_expected_profit_eur: float = Field(default=0.02, ge=0.0, description="Min profit per cycle")


class MMPresetConfig(BaseModel):
    """Complete Market Maker preset configuration."""
    # Identification
    id: str = Field(default_factory=lambda: f"mm_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Preset display name")
    description: str = Field(default="", description="Preset description")
    preset_type: PresetType = Field(default=PresetType.CUSTOM)
    agent_type: AgentTypeV2 = Field(default=AgentTypeV2.MM)
    enabled: bool = Field(default=True)
    
    # Position sizing
    position_size_factor: float = Field(default=1.0, ge=0.0, le=2.0, description="Position size multiplier")
    
    # Sub-configs
    grid: MMGridConfig = Field(default_factory=MMGridConfig)
    inventory: MMInventoryConfig = Field(default_factory=MMInventoryConfig)
    execution: MMExecutionConfig = Field(default_factory=MMExecutionConfig)
    safety: MMSafetyConfig = Field(default_factory=MMSafetyConfig)
    viability: MMViabilityConfig = Field(default_factory=MMViabilityConfig)
    
    # Metadata
    version: int = Field(default=1)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# ============ MOM Preset Schema ============

class MOMEntryConfig(BaseModel):
    """Entry rules for Momentum agent."""
    entry_type: str = Field(default="breakout", description="breakout, pullback, continuation")
    min_momentum_score: float = Field(default=0.6, ge=0.3, le=1.0, description="Min momentum indicator score")
    volume_confirmation: bool = Field(default=True, description="Require volume spike for entry")
    volume_spike_multiplier: float = Field(default=1.5, ge=1.2, le=3.0, description="Volume > avg * this")
    atr_min_pct: float = Field(default=0.5, ge=0.2, le=2.0, description="Min ATR% for entry")
    spread_max_pct: float = Field(default=0.10, ge=0.03, le=0.25, description="Max spread % for entry")


class MOMExitConfig(BaseModel):
    """Exit rules for Momentum agent."""
    take_profit_pct: float = Field(default=10.0, ge=3, le=30, description="Take profit %")
    stop_loss_pct: float = Field(default=-3.5, le=0, ge=-10, description="Stop loss %")
    trailing_enabled: bool = Field(default=True, description="Enable trailing stop")
    trailing_activation_pct: float = Field(default=4.0, ge=2, le=15, description="Activate trailing after this % profit")
    trailing_distance_pct: float = Field(default=3.0, ge=1, le=10, description="Trailing stop distance %")
    time_stop_minutes: int = Field(default=180, ge=30, le=1440, description="Max hold time in minutes")


class MOMRateLimitConfig(BaseModel):
    """Rate limiting for Momentum agent."""
    max_trades_per_day: int = Field(default=3, ge=1, le=10, description="Max trades per day")
    cooldown_minutes: int = Field(default=30, ge=10, le=180, description="Cooldown between trades")
    max_open_positions: int = Field(default=1, ge=1, le=3, description="Max concurrent positions")


class MOMSafetyConfig(BaseModel):
    """Safety features for Momentum agent."""
    daily_kill_pct: float = Field(default=-3.0, le=0, description="Daily loss % to trigger kill")
    require_stable_data: bool = Field(default=True, description="Block if data quality low")
    pause_after_consecutive_losses: int = Field(default=2, ge=1, le=5, description="Pause after N consecutive losses")


class MOMViabilityConfig(BaseModel):
    """Viability requirements for Momentum agent."""
    edge_cost_multiplier: float = Field(default=2.2, ge=1.5, le=5.0, description="Edge > cost * multiplier")
    min_expected_profit_eur: float = Field(default=0.10, ge=0.05, description="Min profit per trade")


class MOMPresetConfig(BaseModel):
    """Complete Momentum agent preset configuration."""
    # Identification
    id: str = Field(default_factory=lambda: f"mom_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Preset display name")
    description: str = Field(default="", description="Preset description")
    preset_type: PresetType = Field(default=PresetType.CUSTOM)
    agent_type: AgentTypeV2 = Field(default=AgentTypeV2.MOM)
    enabled: bool = Field(default=True)
    
    # Sub-configs
    entry: MOMEntryConfig = Field(default_factory=MOMEntryConfig)
    exit: MOMExitConfig = Field(default_factory=MOMExitConfig)
    rate_limit: MOMRateLimitConfig = Field(default_factory=MOMRateLimitConfig)
    safety: MOMSafetyConfig = Field(default_factory=MOMSafetyConfig)
    viability: MOMViabilityConfig = Field(default_factory=MOMViabilityConfig)
    
    # Special flags
    activation_conditions: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Special conditions for activation (e.g., require ATR high)"
    )
    
    # Metadata
    version: int = Field(default=1)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


# ============ System Default Presets ============

def get_mm_system_presets() -> List[MMPresetConfig]:
    """Get all MM system default presets."""
    now = datetime.now(timezone.utc)
    
    presets = [
        # MM_1_TIGHT_RANGE
        MMPresetConfig(
            id="MM_1_TIGHT_RANGE",
            name="MM 1: Tight Range",
            description="For markets with low spread and minimal volatility. Compact grid, maker-only.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            position_size_factor=1.0,
            grid=MMGridConfig(
                grid_width_total_pct=0.8,
                grid_levels=12,
                spacing_type="geometric",
                spacing_factor=0.8,  # Light geometric
            ),
            inventory=MMInventoryConfig(
                target_ratio=0.5,
                skew_max_pct=10.0,
            ),
            execution=MMExecutionConfig(
                maker_only=True,
                rebalance_interval_seconds=60,
            ),
            safety=MMSafetyConfig(
                trend_filter_enabled=True,
                daily_kill_pct=-2.0,
            ),
            viability=MMViabilityConfig(
                edge_cost_multiplier=2.0,
            ),
            created_at=now,
        ),
        
        # MM_2_NORMAL_RANGE
        MMPresetConfig(
            id="MM_2_NORMAL_RANGE",
            name="MM 2: Normal Range",
            description="Balanced configuration for normal market conditions.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            position_size_factor=1.0,
            grid=MMGridConfig(
                grid_width_total_pct=1.5,
                grid_levels=14,
                spacing_type="geometric",
                spacing_factor=1.0,
            ),
            inventory=MMInventoryConfig(
                target_ratio=0.5,
                skew_max_pct=12.0,
            ),
            execution=MMExecutionConfig(
                maker_only=True,
                rebalance_interval_seconds=45,
            ),
            safety=MMSafetyConfig(
                trend_filter_enabled=True,
                daily_kill_pct=-2.0,
            ),
            viability=MMViabilityConfig(
                edge_cost_multiplier=2.0,
            ),
            created_at=now,
        ),
        
        # MM_3_WIDE_VOL
        MMPresetConfig(
            id="MM_3_WIDE_VOL",
            name="MM 3: Wide Volatility",
            description="Wider grid for markets with high volatility.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            position_size_factor=1.0,
            grid=MMGridConfig(
                grid_width_total_pct=2.5,
                grid_levels=16,
                spacing_type="geometric",
                spacing_factor=1.2,
            ),
            inventory=MMInventoryConfig(
                target_ratio=0.5,
                skew_max_pct=15.0,
            ),
            execution=MMExecutionConfig(
                maker_only=False,
                maker_preferred=True,
                taker_allowed_spread_pct=0.04,
                rebalance_interval_seconds=30,
            ),
            safety=MMSafetyConfig(
                trend_filter_enabled=True,
                daily_kill_pct=-2.0,
            ),
            viability=MMViabilityConfig(
                edge_cost_multiplier=2.0,
            ),
            created_at=now,
        ),
        
        # MM_4_DEFENSIVE
        MMPresetConfig(
            id="MM_4_DEFENSIVE",
            name="MM 4: Defensive",
            description="Conservative configuration after losses or in uncertain market.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            position_size_factor=0.6,  # Reduced size
            grid=MMGridConfig(
                grid_width_total_pct=1.2,
                grid_levels=10,
                spacing_type="arithmetic",
                spacing_factor=1.0,
            ),
            inventory=MMInventoryConfig(
                target_ratio=0.5,
                skew_max_pct=8.0,  # Tighter
            ),
            execution=MMExecutionConfig(
                maker_only=True,
                rebalance_interval_seconds=90,  # Slower
            ),
            safety=MMSafetyConfig(
                trend_filter_enabled=True,
                daily_kill_pct=-1.0,  # Tighter kill switch
                pause_on_spread_widening=True,
                cooldown_after_loss_minutes=45,
            ),
            viability=MMViabilityConfig(
                edge_cost_multiplier=2.5,  # Higher bar
            ),
            created_at=now,
        ),
        
        # MM_5_TREND_AVOID
        MMPresetConfig(
            id="MM_5_TREND_AVOID",
            name="MM 5: Trend Avoid (Mode)",
            description="Special mode: completely pauses MM when strong trend is detected.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            position_size_factor=0.0,  # No positions
            grid=MMGridConfig(
                grid_width_total_pct=0.0,  # No grid
                grid_levels=0,
            ),
            inventory=MMInventoryConfig(
                target_ratio=0.5,
                skew_max_pct=0.0,  # Force 0 exposure
            ),
            execution=MMExecutionConfig(
                maker_only=True,
                rebalance_interval_seconds=300,  # Slow check
            ),
            safety=MMSafetyConfig(
                trend_filter_enabled=True,
                trend_adx_threshold=25.0,  # Lower threshold
                daily_kill_pct=-1.0,
            ),
            viability=MMViabilityConfig(
                edge_cost_multiplier=10.0,  # Effectively blocks all
            ),
            created_at=now,
        ),
    ]
    
    return presets


def get_mom_system_presets() -> List[MOMPresetConfig]:
    """Get all MOM system default presets."""
    now = datetime.now(timezone.utc)
    
    presets = [
        # MOM_1_BREAKOUT_CONSERVATIVE
        MOMPresetConfig(
            id="MOM_1_BREAKOUT_CONSERVATIVE",
            name="MOM 1: Breakout Conservative",
            description="Conservative breakouts with tight TP/SL. Few trades, high quality.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            entry=MOMEntryConfig(
                entry_type="breakout",
                min_momentum_score=0.7,
                volume_confirmation=True,
                volume_spike_multiplier=1.5,
            ),
            exit=MOMExitConfig(
                take_profit_pct=6.0,
                stop_loss_pct=-3.0,
                trailing_enabled=True,
                trailing_activation_pct=3.0,
                trailing_distance_pct=2.0,
            ),
            rate_limit=MOMRateLimitConfig(
                max_trades_per_day=2,
                cooldown_minutes=45,
            ),
            safety=MOMSafetyConfig(
                daily_kill_pct=-3.0,
            ),
            viability=MOMViabilityConfig(
                edge_cost_multiplier=2.5,
            ),
            created_at=now,
        ),
        
        # MOM_2_BREAKOUT_STANDARD
        MOMPresetConfig(
            id="MOM_2_BREAKOUT_STANDARD",
            name="MOM 2: Breakout Standard",
            description="Balanced configuration for breakouts in normal conditions.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            entry=MOMEntryConfig(
                entry_type="breakout",
                min_momentum_score=0.6,
                volume_confirmation=True,
                volume_spike_multiplier=1.5,
            ),
            exit=MOMExitConfig(
                take_profit_pct=10.0,
                stop_loss_pct=-3.5,
                trailing_enabled=True,
                trailing_activation_pct=4.0,
                trailing_distance_pct=3.0,
            ),
            rate_limit=MOMRateLimitConfig(
                max_trades_per_day=3,
                cooldown_minutes=30,
            ),
            safety=MOMSafetyConfig(
                daily_kill_pct=-3.0,
            ),
            viability=MOMViabilityConfig(
                edge_cost_multiplier=2.2,
            ),
            created_at=now,
        ),
        
        # MOM_3_HIGH_VOL_AGGRESSIVE
        MOMPresetConfig(
            id="MOM_3_HIGH_VOL_AGGRESSIVE",
            name="MOM 3: High Vol Aggressive",
            description="Aggressive in high volatility. Requires high ATR + volume spike.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            entry=MOMEntryConfig(
                entry_type="breakout",
                min_momentum_score=0.65,
                volume_confirmation=True,
                volume_spike_multiplier=2.0,
                atr_min_pct=1.5,  # High ATR required
                spread_max_pct=0.08,  # Tight spread still
            ),
            exit=MOMExitConfig(
                take_profit_pct=15.0,
                stop_loss_pct=-4.0,
                trailing_enabled=True,
                trailing_activation_pct=6.0,
                trailing_distance_pct=4.0,
            ),
            rate_limit=MOMRateLimitConfig(
                max_trades_per_day=4,
                cooldown_minutes=20,
            ),
            safety=MOMSafetyConfig(
                daily_kill_pct=-4.0,
            ),
            viability=MOMViabilityConfig(
                edge_cost_multiplier=2.0,
            ),
            activation_conditions={
                "require_high_atr": True,
                "atr_min_pct": 1.5,
                "volume_spike": True,
                "spread_ok": True,
            },
            created_at=now,
        ),
        
        # MOM_4_DEFENSIVE_RECOVERY
        MOMPresetConfig(
            id="MOM_4_DEFENSIVE_RECOVERY",
            name="MOM 4: Defensive Recovery",
            description="Used after drawdown when market stabilizes. Very tight TP/SL.",
            preset_type=PresetType.SYSTEM,
            enabled=True,
            entry=MOMEntryConfig(
                entry_type="pullback",  # Safer entries
                min_momentum_score=0.75,  # Higher bar
                volume_confirmation=True,
                volume_spike_multiplier=1.3,
            ),
            exit=MOMExitConfig(
                take_profit_pct=5.0,  # Quick profit
                stop_loss_pct=-2.5,  # Tight stop
                trailing_enabled=True,
                trailing_activation_pct=2.0,
                trailing_distance_pct=1.5,
            ),
            rate_limit=MOMRateLimitConfig(
                max_trades_per_day=1,  # Very limited
                cooldown_minutes=60,
            ),
            safety=MOMSafetyConfig(
                daily_kill_pct=-2.0,
                pause_after_consecutive_losses=1,  # Stop after 1 loss
            ),
            viability=MOMViabilityConfig(
                edge_cost_multiplier=3.0,  # High bar
            ),
            activation_conditions={
                "post_drawdown_recovery": True,
                "market_stabilized": True,
            },
            created_at=now,
        ),
    ]
    
    return presets


# ============ Presets Service ============

class AgentPresetsV2Service:
    """
    Service for managing MM and MOM presets.
    
    Features:
    - System defaults (immutable)
    - User custom presets (editable)
    - Enable/disable without deletion
    - Audit logging
    """
    
    COLLECTION = "agent_presets_v2"
    
    def __init__(self, db: AsyncIOMotorDatabase, audit_service=None):
        self.db = db
        self.collection = db[self.COLLECTION]
        self.audit_service = audit_service
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize service and ensure system presets exist."""
        if self._initialized:
            return
        
        # Create indexes
        await self.collection.create_index("id", unique=True)
        await self.collection.create_index([("agent_type", 1), ("preset_type", 1)])
        await self.collection.create_index([("agent_type", 1), ("enabled", 1)])
        
        # Check if system presets exist
        system_count = await self.collection.count_documents({"preset_type": "system"})
        
        if system_count == 0:
            # Insert system defaults
            mm_presets = get_mm_system_presets()
            mom_presets = get_mom_system_presets()
            
            for preset in mm_presets:
                doc = preset.model_dump()
                doc["created_at"] = doc["created_at"].isoformat() if doc.get("created_at") else None
                doc["updated_at"] = doc["updated_at"].isoformat() if doc.get("updated_at") else None
                await self.collection.insert_one(doc)
            
            for preset in mom_presets:
                doc = preset.model_dump()
                doc["created_at"] = doc["created_at"].isoformat() if doc.get("created_at") else None
                doc["updated_at"] = doc["updated_at"].isoformat() if doc.get("updated_at") else None
                await self.collection.insert_one(doc)
            
            logger.info(f"Inserted {len(mm_presets)} MM + {len(mom_presets)} MOM system presets")
        
        self._initialized = True
        logger.info("AgentPresetsV2Service initialized")
    
    async def get_all_presets(
        self,
        agent_type: Optional[AgentTypeV2] = None,
        include_disabled: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get all presets, optionally filtered."""
        await self.initialize()
        
        query = {}
        if agent_type:
            query["agent_type"] = agent_type.value
        if not include_disabled:
            query["enabled"] = True
        
        cursor = self.collection.find(query, {"_id": 0})
        return await cursor.to_list(length=100)
    
    async def get_preset_by_id(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific preset by ID."""
        await self.initialize()
        return await self.collection.find_one({"id": preset_id}, {"_id": 0})
    
    async def get_mm_presets(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """Get all MM presets."""
        return await self.get_all_presets(AgentTypeV2.MM, include_disabled)
    
    async def get_mom_presets(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """Get all MOM presets."""
        return await self.get_all_presets(AgentTypeV2.MOM, include_disabled)
    
    async def create_custom_preset(
        self,
        agent_type: AgentTypeV2,
        config: Dict[str, Any],
        user_id: str,
        username: str,
    ) -> Dict[str, Any]:
        """Create a new custom preset."""
        await self.initialize()
        
        now = datetime.now(timezone.utc)
        
        # Build preset based on type
        if agent_type == AgentTypeV2.MM:
            preset = MMPresetConfig(
                preset_type=PresetType.CUSTOM,
                created_at=now,
                updated_at=now,
                created_by=user_id,
                **config
            )
        else:
            preset = MOMPresetConfig(
                preset_type=PresetType.CUSTOM,
                created_at=now,
                updated_at=now,
                created_by=user_id,
                **config
            )
        
        doc = preset.model_dump()
        doc["created_at"] = doc["created_at"].isoformat() if doc.get("created_at") else None
        doc["updated_at"] = doc["updated_at"].isoformat() if doc.get("updated_at") else None
        
        await self.collection.insert_one(doc)
        
        # Audit
        if self.audit_service:
            await self.audit_service.log(
                user_id=user_id,
                username=username,
                role="user",
                action="preset.save",
                resource_type="agent_preset_v2",
                resource_id=preset.id,
                metadata={"agent_type": agent_type.value, "name": preset.name}
            )
        
        logger.info(f"Created custom {agent_type.value} preset: {preset.id}")
        if "_id" in doc:
            del doc["_id"]
        return doc
    
    async def update_preset(
        self,
        preset_id: str,
        updates: Dict[str, Any],
        user_id: str,
        username: str,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing preset (custom only)."""
        await self.initialize()
        
        # Get current
        current = await self.get_preset_by_id(preset_id)
        if not current:
            return None
        
        # Check if system preset
        if current.get("preset_type") == "system":
            raise ValueError("Cannot modify system presets. Create a custom copy instead.")
        
        # Apply updates
        for key, value in updates.items():
            if key not in ["id", "preset_type", "agent_type", "created_at", "created_by"]:
                current[key] = value
        
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await self.collection.replace_one({"id": preset_id}, current)
        
        # Audit
        if self.audit_service:
            await self.audit_service.log(
                user_id=user_id,
                username=username,
                role="user",
                action="preset.save",
                resource_type="agent_preset_v2",
                resource_id=preset_id,
                metadata={"updates": list(updates.keys())}
            )
        
        logger.info(f"Updated preset: {preset_id}")
        return current
    
    async def toggle_preset(
        self,
        preset_id: str,
        enabled: bool,
        user_id: str,
        username: str,
    ) -> bool:
        """Enable or disable a preset."""
        await self.initialize()
        
        result = await self.collection.update_one(
            {"id": preset_id},
            {"$set": {"enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        if result.modified_count > 0:
            if self.audit_service:
                await self.audit_service.log(
                    user_id=user_id,
                    username=username,
                    role="user",
                    action="preset.save",
                    resource_type="agent_preset_v2",
                    resource_id=preset_id,
                    metadata={"enabled": enabled}
                )
            logger.info(f"Preset {preset_id} {'enabled' if enabled else 'disabled'}")
            return True
        return False
    
    async def delete_custom_preset(
        self,
        preset_id: str,
        user_id: str,
        username: str,
    ) -> bool:
        """Delete a custom preset (not system presets)."""
        await self.initialize()
        
        # Check if custom
        current = await self.get_preset_by_id(preset_id)
        if not current:
            return False
        
        if current.get("preset_type") == "system":
            raise ValueError("Cannot delete system presets")
        
        result = await self.collection.delete_one({"id": preset_id})
        
        if result.deleted_count > 0:
            if self.audit_service:
                await self.audit_service.log(
                    user_id=user_id,
                    username=username,
                    role="user",
                    action="preset.delete",
                    resource_type="agent_preset_v2",
                    resource_id=preset_id,
                    metadata={"name": current.get("name")}
                )
            logger.info(f"Deleted custom preset: {preset_id}")
            return True
        return False
    
    async def clone_to_custom(
        self,
        source_preset_id: str,
        new_name: str,
        user_id: str,
        username: str,
    ) -> Optional[Dict[str, Any]]:
        """Clone a preset (system or custom) to a new custom preset."""
        source = await self.get_preset_by_id(source_preset_id)
        if not source:
            return None
        
        # Create copy
        agent_type = AgentTypeV2(source["agent_type"])
        
        new_config = copy.deepcopy(source)
        del new_config["id"]
        new_config["name"] = new_name
        new_config["description"] = f"Clone of {source['name']}"
        
        return await self.create_custom_preset(
            agent_type=agent_type,
            config=new_config,
            user_id=user_id,
            username=username,
        )


# ============ Global Instance ============

_presets_service: Optional[AgentPresetsV2Service] = None


def get_presets_v2_service() -> Optional[AgentPresetsV2Service]:
    """Get global presets service instance."""
    return _presets_service


def set_presets_v2_service(service: AgentPresetsV2Service) -> None:
    """Set global presets service instance."""
    global _presets_service
    _presets_service = service
    logger.info("AgentPresetsV2Service set globally")


# ============ Convenience Methods for Config Editor ============

class PresetsServiceWrapper:
    """Wrapper to provide simplified interface for config editor."""
    
    def __init__(self, service: AgentPresetsV2Service):
        self.service = service
    
    async def get_presets(self, preset_type: str) -> List[Dict[str, Any]]:
        """Get all presets for a type (MM or MOM)."""
        preset_type = preset_type.upper()
        if preset_type == "MM":
            return await self.service.get_mm_presets(include_disabled=True)
        elif preset_type == "MOM":
            return await self.service.get_mom_presets(include_disabled=True)
        return []
    
    async def get_preset(self, preset_type: str, preset_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific preset."""
        return await self.service.get_preset_by_id(preset_id)
    
    async def update_preset(self, preset_type: str, preset_id: str, data: Dict[str, Any]) -> bool:
        """Update a preset (full replacement)."""
        try:
            await self.service.collection.replace_one(
                {"id": preset_id},
                data
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update preset {preset_id}: {e}")
            return False
    
    async def save_preset(self, preset_type: str, data: Dict[str, Any]) -> bool:
        """Save a new preset."""
        try:
            await self.service.collection.insert_one(data)
            return True
        except Exception as e:
            logger.error(f"Failed to save preset: {e}")
            return False


def get_presets_wrapper() -> Optional[PresetsServiceWrapper]:
    """Get wrapper for config editor routes."""
    if _presets_service:
        return PresetsServiceWrapper(_presets_service)
    return None
