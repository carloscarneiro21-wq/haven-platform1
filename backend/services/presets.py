"""Agent Presets Service - Manage trading agent presets."""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import logging

logger = logging.getLogger(__name__)


# ============ Initial Presets for €50 BTC/USDT Spot Micro-Gains Strategy ============

INITIAL_PRESETS = {
    "dca": {
        "conservative": {
            "name": "DCA Conservador",
            "description": "Compras pequenas e frequentes, baixo risco",
            "emoji": "🟢",
            "params": {
                "interval_hours": 24,
                "base_amount": 5.0,
                "max_amount": 10.0,
                "dip_threshold_pct": 3.0,
                "dip_cooldown_hours": 8,
                "max_exposure": 50.0,
                "scaling_factor": 1.2,
            }
        },
        "moderate": {
            "name": "DCA Moderado",
            "description": "Equilíbrio entre frequência e tamanho",
            "emoji": "🟡",
            "params": {
                "interval_hours": 12,
                "base_amount": 8.0,
                "max_amount": 15.0,
                "dip_threshold_pct": 2.5,
                "dip_cooldown_hours": 6,
                "max_exposure": 50.0,
                "scaling_factor": 1.5,
            }
        },
        "aggressive": {
            "name": "DCA Agressivo",
            "description": "Compras maiores em dips, mais frequente",
            "emoji": "🔴",
            "params": {
                "interval_hours": 8,
                "base_amount": 10.0,
                "max_amount": 20.0,
                "dip_threshold_pct": 2.0,
                "dip_cooldown_hours": 4,
                "max_exposure": 50.0,
                "scaling_factor": 2.0,
            }
        }
    },
    "grid": {
        "conservative": {
            "name": "Grid Conservador",
            "description": "Grid apertado, muitos níveis pequenos",
            "emoji": "🟢",
            "params": {
                "num_grids": 15,
                "amount_per_grid": 3.0,
                "auto_adjust": True,
                "volatility_multiplier": 1.5,
            }
        },
        "moderate": {
            "name": "Grid Moderado",
            "description": "Equilíbrio entre range e número de níveis",
            "emoji": "🟡",
            "params": {
                "num_grids": 10,
                "amount_per_grid": 5.0,
                "auto_adjust": True,
                "volatility_multiplier": 2.0,
            }
        },
        "aggressive": {
            "name": "Grid Agressivo",
            "description": "Grid largo, mais capital por nível",
            "emoji": "🔴",
            "params": {
                "num_grids": 8,
                "amount_per_grid": 6.0,
                "auto_adjust": True,
                "volatility_multiplier": 2.5,
            }
        }
    },
    "trend": {
        "conservative": {
            "name": "Trend Conservador",
            "description": "Stop apertado, take profit moderado",
            "emoji": "🟢",
            "params": {
                "stop_loss_pct": 2.0,
                "take_profit_pct": 4.0,
                "trailing_stop_pct": 1.5,
                "position_size_pct": 3.0,
                "adx_threshold": 30.0,
            }
        },
        "moderate": {
            "name": "Trend Moderado",
            "description": "Equilíbrio risco/recompensa",
            "emoji": "🟡",
            "params": {
                "stop_loss_pct": 3.0,
                "take_profit_pct": 6.0,
                "trailing_stop_pct": 2.0,
                "position_size_pct": 5.0,
                "adx_threshold": 25.0,
            }
        },
        "aggressive": {
            "name": "Trend Agressivo",
            "description": "Stop largo, objetivo maior",
            "emoji": "🔴",
            "params": {
                "stop_loss_pct": 4.0,
                "take_profit_pct": 10.0,
                "trailing_stop_pct": 3.0,
                "position_size_pct": 8.0,
                "adx_threshold": 20.0,
            }
        }
    },
    "mean_reversion": {
        "conservative": {
            "name": "Mean Rev. Conservador",
            "description": "RSI extremos, ADX baixo",
            "emoji": "🟢",
            "params": {
                "rsi_oversold": 25.0,
                "rsi_overbought": 75.0,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 2.5,
                "max_adx": 20.0,
                "position_size_pct": 3.0,
            }
        },
        "moderate": {
            "name": "Mean Rev. Moderado",
            "description": "Equilíbrio entre sinais e frequência",
            "emoji": "🟡",
            "params": {
                "rsi_oversold": 30.0,
                "rsi_overbought": 70.0,
                "stop_loss_pct": 2.0,
                "take_profit_pct": 3.0,
                "max_adx": 25.0,
                "position_size_pct": 5.0,
            }
        },
        "aggressive": {
            "name": "Mean Rev. Agressivo",
            "description": "RSI relaxados, mais trades",
            "emoji": "🔴",
            "params": {
                "rsi_oversold": 35.0,
                "rsi_overbought": 65.0,
                "stop_loss_pct": 2.5,
                "take_profit_pct": 4.0,
                "max_adx": 30.0,
                "position_size_pct": 8.0,
            }
        }
    },
    "breakout": {
        "conservative": {
            "name": "Breakout Conservador",
            "description": "Threshold alto, confirma bem",
            "emoji": "🟢",
            "params": {
                "lookback_periods": 30,
                "breakout_threshold_pct": 1.5,
                "min_adx": 25.0,
                "stop_loss_atr_mult": 2.5,
                "take_profit_atr_mult": 4.0,
                "position_size_pct": 3.0,
            }
        },
        "moderate": {
            "name": "Breakout Moderado",
            "description": "Equilíbrio entre captura e falsos sinais",
            "emoji": "🟡",
            "params": {
                "lookback_periods": 20,
                "breakout_threshold_pct": 1.0,
                "min_adx": 20.0,
                "stop_loss_atr_mult": 2.0,
                "take_profit_atr_mult": 3.0,
                "position_size_pct": 5.0,
            }
        },
        "aggressive": {
            "name": "Breakout Agressivo",
            "description": "Entrada rápida, mais risco",
            "emoji": "🔴",
            "params": {
                "lookback_periods": 14,
                "breakout_threshold_pct": 0.5,
                "min_adx": 15.0,
                "stop_loss_atr_mult": 1.5,
                "take_profit_atr_mult": 2.5,
                "position_size_pct": 8.0,
            }
        }
    }
}


class PresetService:
    """Service for managing agent presets."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.agent_presets
        
    async def initialize(self):
        """Initialize presets collection with defaults if empty."""
        count = await self.collection.count_documents({})
        if count == 0:
            await self._create_initial_presets()
            logger.info("Created initial agent presets")
        
        # Create indexes
        await self.collection.create_index("agent_type")
        await self.collection.create_index("preset_key")
        await self.collection.create_index([("agent_type", 1), ("is_global", 1)])
        
    async def _create_initial_presets(self):
        """Create initial preset documents."""
        presets = []
        now = datetime.now(timezone.utc).isoformat()
        
        for agent_type, preset_levels in INITIAL_PRESETS.items():
            for preset_key, preset_data in preset_levels.items():
                preset = {
                    "id": str(uuid.uuid4()),
                    "agent_type": agent_type,
                    "preset_key": preset_key,
                    "name": preset_data["name"],
                    "description": preset_data["description"],
                    "emoji": preset_data["emoji"],
                    "params": preset_data["params"],
                    "is_global": True,
                    "is_system": True,
                    "created_by": "system",
                    "created_at": now,
                    "updated_at": now,
                }
                presets.append(preset)
        
        if presets:
            await self.collection.insert_many(presets)
            
    async def get_presets(self, agent_type: Optional[str] = None, include_custom: bool = True, user_id: Optional[str] = None) -> List[Dict]:
        """Get presets, optionally filtered by agent type."""
        query = {}
        
        if agent_type:
            query["agent_type"] = agent_type
        
        if not include_custom:
            query["is_global"] = True
        elif user_id:
            # Include global presets and user's custom presets
            query["$or"] = [
                {"is_global": True},
                {"created_by": user_id}
            ]
        
        presets = await self.collection.find(query, {"_id": 0}).to_list(100)
        return presets
    
    async def get_preset_by_id(self, preset_id: str) -> Optional[Dict]:
        """Get a specific preset by ID."""
        return await self.collection.find_one({"id": preset_id}, {"_id": 0})
    
    async def get_preset_by_key(self, agent_type: str, preset_key: str) -> Optional[Dict]:
        """Get a preset by agent type and key (conservative/moderate/aggressive)."""
        return await self.collection.find_one(
            {"agent_type": agent_type, "preset_key": preset_key, "is_global": True},
            {"_id": 0}
        )
    
    async def save_preset(
        self,
        name: str,
        agent_type: str,
        params: Dict[str, Any],
        user_id: str,
        user_role: str,
        description: str = "",
        is_global: bool = False
    ) -> Dict:
        """Save a new preset."""
        now = datetime.now(timezone.utc).isoformat()
        
        # Only OWNER/ADMIN can create global presets
        if is_global and user_role not in ["owner", "admin"]:
            raise PermissionError("Only OWNER/ADMIN can create global presets")
        
        preset = {
            "id": str(uuid.uuid4()),
            "agent_type": agent_type,
            "preset_key": f"custom_{uuid.uuid4().hex[:8]}",
            "name": name,
            "description": description,
            "emoji": "⭐",
            "params": params,
            "is_global": is_global,
            "is_system": False,
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
        
        await self.collection.insert_one(preset)
        
        # Return without _id
        preset.pop("_id", None)
        
        logger.info(f"Preset saved: {name} for {agent_type} by {user_id}")
        return preset
    
    async def delete_preset(self, preset_id: str, user_id: str, user_role: str) -> bool:
        """Delete a preset."""
        preset = await self.get_preset_by_id(preset_id)
        
        if not preset:
            return False
        
        # Cannot delete system presets
        if preset.get("is_system"):
            raise PermissionError("Cannot delete system presets")
        
        # Only creator or OWNER/ADMIN can delete
        if preset.get("created_by") != user_id and user_role not in ["owner", "admin"]:
            raise PermissionError("Not authorized to delete this preset")
        
        result = await self.collection.delete_one({"id": preset_id})
        return result.deleted_count > 0
    
    async def update_preset(
        self,
        preset_id: str,
        user_id: str,
        user_role: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict]:
        """Update an existing preset."""
        preset = await self.get_preset_by_id(preset_id)
        
        if not preset:
            return None
        
        # Cannot update system presets
        if preset.get("is_system"):
            raise PermissionError("Cannot update system presets")
        
        # Only creator or OWNER/ADMIN can update
        if preset.get("created_by") != user_id and user_role not in ["owner", "admin"]:
            raise PermissionError("Not authorized to update this preset")
        
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Remove protected fields
        for field in ["id", "created_by", "created_at", "is_system"]:
            updates.pop(field, None)
        
        await self.collection.update_one(
            {"id": preset_id},
            {"$set": updates}
        )
        
        return await self.get_preset_by_id(preset_id)


def get_preset_diff(current_params: Dict, preset_params: Dict) -> Dict:
    """Calculate the difference between current and preset parameters."""
    diff = {
        "added": {},
        "removed": {},
        "changed": {},
        "unchanged": {}
    }
    
    all_keys = set(current_params.keys()) | set(preset_params.keys())
    
    for key in all_keys:
        current_val = current_params.get(key)
        preset_val = preset_params.get(key)
        
        if key not in current_params:
            diff["added"][key] = preset_val
        elif key not in preset_params:
            diff["removed"][key] = current_val
        elif current_val != preset_val:
            diff["changed"][key] = {
                "from": current_val,
                "to": preset_val
            }
        else:
            diff["unchanged"][key] = current_val
    
    return diff
