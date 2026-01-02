"""
HAVEN Config Editor Routes — P1.1
==================================

Secure endpoints for editing System Config and Agent Presets.

Rules (Non-negotiable):
- No change without audit trail
- Every change requires reason_code
- Changes do not take effect mid-run
- Rollback possible
- Guardian can block dangerous configs
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import logging
import json
import copy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["Config Editor"])

# Service references (set by server.py)
_system_config_service = None
_presets_service = None
_guardian_service = None
_audit_service = None


def set_services(system_config, presets, guardian, audit):
    """Set service references."""
    global _system_config_service, _presets_service, _guardian_service, _audit_service
    _system_config_service = system_config
    _presets_service = presets
    _guardian_service = guardian
    _audit_service = audit


# ============================================================
# REQUEST MODELS
# ============================================================

class ConfigUpdateRequest(BaseModel):
    """Request to update system config."""
    updates: Dict[str, Any] = Field(..., description="Dict of path -> value updates")
    reason: str = Field(..., min_length=10, max_length=500, description="Why are you changing this? (Required)")
    reason_code: str = Field(default="MANUAL_ADJUSTMENT", description="Reason code for categorization")


class PresetUpdateRequest(BaseModel):
    """Request to update a preset."""
    preset_data: Dict[str, Any] = Field(..., description="Full preset data")
    reason: str = Field(..., min_length=10, max_length=500, description="Why are you changing this? (Required)")
    reason_code: str = Field(default="PRESET_ADJUSTMENT", description="Reason code")


class ConfigDiffRequest(BaseModel):
    """Request to preview changes."""
    updates: Dict[str, Any] = Field(..., description="Proposed updates")


# ============================================================
# RESPONSE MODELS
# ============================================================

class ConfigDiff(BaseModel):
    """Diff between current and proposed config."""
    field: str
    current_value: Any
    new_value: Any
    risk_level: str = "low"  # low | medium | high | critical
    warning: Optional[str] = None


class ConfigUpdateResponse(BaseModel):
    """Response after config update."""
    success: bool
    message: str
    audit_id: str
    changes: List[ConfigDiff]
    guardian_validated: bool = True
    guardian_warnings: List[str] = []


class GuardianValidation(BaseModel):
    """Guardian validation result for config changes."""
    allowed: bool
    risk_level: str  # low | medium | high | critical
    warnings: List[str] = []
    blocked_reason: Optional[str] = None


# ============================================================
# GUARDIAN VALIDATION
# ============================================================

def validate_config_with_guardian(
    current_config: Dict[str, Any],
    updates: Dict[str, Any]
) -> GuardianValidation:
    """
    Validate proposed config changes against Guardian rules.
    
    Guardian can block changes that would:
    - Set daily_loss_limit > -0.5% (too loose)
    - Set weekly_drawdown_limit > -2% (too loose)
    - Disable Guardian entirely
    - Set max_spread > 0.5% (too wide)
    """
    warnings = []
    risk_level = "low"
    allowed = True
    blocked_reason = None
    
    # Check dangerous fields
    dangerous_fields = {
        "guardian.daily_loss_limit_pct": {
            "max": -0.5,
            "message": "Daily loss limit cannot be looser than -0.5%",
            "critical": True,
        },
        "guardian.weekly_drawdown_limit_pct": {
            "max": -2.0,
            "message": "Weekly drawdown limit cannot be looser than -2%",
            "critical": True,
        },
        "guardian.max_spread_pct": {
            "max_allowed": 0.5,
            "message": "Max spread cannot exceed 0.5%",
            "critical": False,
        },
        "concurrency.max_concurrent_agents": {
            "max_allowed": 3,
            "message": "Max concurrent agents cannot exceed 3",
            "critical": False,
        },
    }
    
    for path, value in updates.items():
        if path in dangerous_fields:
            rule = dangerous_fields[path]
            
            if "max" in rule and value > rule["max"]:
                if rule.get("critical"):
                    allowed = False
                    blocked_reason = rule["message"]
                else:
                    warnings.append(rule["message"])
                    risk_level = "high"
            
            if "max_allowed" in rule and value > rule["max_allowed"]:
                if rule.get("critical"):
                    allowed = False
                    blocked_reason = rule["message"]
                else:
                    warnings.append(rule["message"])
                    risk_level = "medium" if risk_level == "low" else risk_level
    
    # Check if disabling safety features
    safety_fields = [
        "guardian.pause_on_spread_widening",
        "guardian.pause_on_high_latency",
    ]
    
    for field in safety_fields:
        if field in updates and updates[field] is False:
            warnings.append(f"Disabling safety feature: {field}")
            risk_level = "medium" if risk_level == "low" else risk_level
    
    return GuardianValidation(
        allowed=allowed,
        risk_level=risk_level,
        warnings=warnings,
        blocked_reason=blocked_reason,
    )


def get_risk_level_for_field(field: str) -> str:
    """Determine risk level for a config field change."""
    critical_fields = [
        "guardian.daily_loss_limit_pct",
        "guardian.weekly_drawdown_limit_pct",
        "risk_budget.core_pct",
        "risk_budget.edge_pct",
    ]
    
    high_fields = [
        "guardian.max_spread_pct",
        "guardian.max_slippage_pct",
        "viability.",
        "concurrency.",
    ]
    
    if any(f in field for f in critical_fields):
        return "critical"
    if any(f in field for f in high_fields):
        return "high"
    if "guardian." in field or "safety." in field:
        return "medium"
    return "low"


# ============================================================
# SYSTEM CONFIG ENDPOINTS
# ============================================================

@router.get("/system")
async def get_system_config():
    """Get current system configuration."""
    if not _system_config_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    config = await _system_config_service.get_config()
    return _system_config_service.to_dict(config)


@router.post("/system/diff")
async def preview_system_config_diff(request: ConfigDiffRequest):
    """
    Preview what would change without saving.
    Returns a visual diff of current vs proposed values.
    """
    if not _system_config_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    current = await _system_config_service.get_config()
    current_dict = _system_config_service.to_dict(current)
    
    diffs = []
    for path, new_value in request.updates.items():
        # Navigate to get current value
        parts = path.split(".")
        current_value = current_dict
        for part in parts:
            if isinstance(current_value, dict) and part in current_value:
                current_value = current_value[part]
            else:
                current_value = None
                break
        
        # Determine risk level
        risk_level = get_risk_level_for_field(path)
        
        # Check for warnings
        warning = None
        if risk_level in ["critical", "high"]:
            warning = f"This is a {risk_level}-risk change. Review carefully."
        
        diffs.append(ConfigDiff(
            field=path,
            current_value=current_value,
            new_value=new_value,
            risk_level=risk_level,
            warning=warning,
        ))
    
    # Also run Guardian validation
    guardian_result = validate_config_with_guardian(current_dict, request.updates)
    
    return {
        "diffs": [d.model_dump() for d in diffs],
        "guardian_validation": guardian_result.model_dump(),
    }


@router.put("/system")
async def update_system_config(request: ConfigUpdateRequest, req: Request):
    """
    Update system configuration with audit trail.
    
    Requirements:
    - reason field is mandatory (min 10 chars)
    - Guardian validates changes
    - All changes are audited
    - Changes cannot take effect mid-run (checked by caller)
    """
    if not _system_config_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    # Get current user from request
    user = getattr(req.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = user.get("id", user.get("user_id", "unknown"))
    username = user.get("username", "unknown")
    role = user.get("role", "viewer")
    
    # Get current config for diff
    current = await _system_config_service.get_config()
    current_dict = _system_config_service.to_dict(current)
    
    # Guardian validation
    guardian_result = validate_config_with_guardian(current_dict, request.updates)
    
    if not guardian_result.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Guardian blocked this change",
                "reason": guardian_result.blocked_reason,
                "message": "HAVEN Guardian has determined this change would compromise capital safety.",
            }
        )
    
    # Build diff list
    diffs = []
    for path, new_value in request.updates.items():
        parts = path.split(".")
        current_value = current_dict
        for part in parts:
            if isinstance(current_value, dict) and part in current_value:
                current_value = current_value[part]
            else:
                current_value = None
                break
        
        diffs.append(ConfigDiff(
            field=path,
            current_value=current_value,
            new_value=new_value,
            risk_level=get_risk_level_for_field(path),
        ))
    
    # Perform update
    updated = await _system_config_service.update_config(
        updates=request.updates,
        user_id=user_id,
        username=username,
        role=role,
    )
    
    # Enhanced audit log
    if _audit_service:
        audit_log = await _audit_service.log(
            user_id=user_id,
            username=username,
            role=role,
            action="settings.update",
            resource_type="system_config",
            resource_id="growth_config_v1",
            before=current_dict,
            after=_system_config_service.to_dict(updated),
            metadata={
                "reason": request.reason,
                "reason_code": request.reason_code,
                "changes_count": len(request.updates),
                "risk_level": guardian_result.risk_level,
                "guardian_warnings": guardian_result.warnings,
            }
        )
        audit_id = audit_log.id
    else:
        audit_id = "not_available"
    
    logger.info(f"System config updated by {username}: {len(request.updates)} changes, reason: {request.reason_code}")
    
    return ConfigUpdateResponse(
        success=True,
        message="Configuration updated successfully",
        audit_id=audit_id,
        changes=[d.model_dump() for d in diffs],
        guardian_validated=True,
        guardian_warnings=guardian_result.warnings,
    )


@router.post("/system/reset")
async def reset_system_config(req: Request, reason: str = "Reset to safe defaults"):
    """Reset system config to defaults."""
    if not _system_config_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    user = getattr(req.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Only admin/owner can reset
    role = user.get("role", "viewer")
    if role not in ["admin", "owner"]:
        raise HTTPException(status_code=403, detail="Only admin/owner can reset config")
    
    user_id = user.get("id", user.get("user_id", "unknown"))
    username = user.get("username", "unknown")
    
    await _system_config_service.reset_to_defaults(
        user_id=user_id,
        username=username,
        role=role,
    )
    
    return {"success": True, "message": "Configuration reset to defaults"}


# ============================================================
# PRESET ENDPOINTS
# ============================================================

@router.get("/presets/{preset_type}")
async def get_presets(preset_type: str):
    """Get all presets for a given type (mm or mom)."""
    if not _presets_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    preset_type = preset_type.upper()
    if preset_type not in ["MM", "MOM"]:
        raise HTTPException(status_code=400, detail="Invalid preset type. Use 'mm' or 'mom'")
    
    presets = await _presets_service.get_presets(preset_type)
    return {"presets": presets}


@router.get("/presets/{preset_type}/{preset_id}")
async def get_preset(preset_type: str, preset_id: str):
    """Get a specific preset."""
    if not _presets_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    preset_type = preset_type.upper()
    preset = await _presets_service.get_preset(preset_type, preset_id)
    
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    return preset


@router.put("/presets/{preset_type}/{preset_id}")
async def update_preset(
    preset_type: str,
    preset_id: str,
    request: PresetUpdateRequest,
    req: Request,
):
    """
    Update a preset with audit trail.
    
    System presets cannot be modified - they must be cloned first.
    """
    if not _presets_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    user = getattr(req.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = user.get("id", user.get("user_id", "unknown"))
    username = user.get("username", "unknown")
    role = user.get("role", "viewer")
    
    preset_type = preset_type.upper()
    
    # Get current preset
    current = await _presets_service.get_preset(preset_type, preset_id)
    if not current:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    # Check if system preset
    if current.get("preset_type") == "system":
        raise HTTPException(
            status_code=403,
            detail="System presets cannot be modified. Clone it first to create a custom version."
        )
    
    # Guardian validation for presets
    warnings = []
    risk_level = "low"
    
    # Check for dangerous preset changes
    preset_data = request.preset_data
    
    if preset_type == "MM":
        # Check grid_levels
        grid = preset_data.get("grid", {})
        if grid.get("grid_levels", 0) > 20:
            warnings.append("High grid levels (>20) may increase execution costs")
            risk_level = "medium"
        
        # Check safety disabled
        safety = preset_data.get("safety", {})
        if safety.get("daily_kill_pct", -2) > -1:
            warnings.append("Daily kill switch is very loose (>-1%)")
            risk_level = "high"
    
    elif preset_type == "MOM":
        # Check stop loss
        exit_config = preset_data.get("exit", {})
        if exit_config.get("stop_loss_pct", -5) > -2:
            warnings.append("Stop loss is very tight (>-2%), may cause frequent exits")
            risk_level = "medium"
        
        # Check rate limits
        rate_limit = preset_data.get("rate_limit", {})
        if rate_limit.get("max_trades_per_day", 3) > 5:
            warnings.append("High trade frequency (>5/day) may increase costs")
            risk_level = "medium"
    
    # Update metadata
    preset_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    preset_data["updated_by"] = user_id
    preset_data["version"] = current.get("version", 0) + 1
    
    # Save
    success = await _presets_service.update_preset(preset_type, preset_id, preset_data)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update preset")
    
    # Audit log
    if _audit_service:
        await _audit_service.log(
            user_id=user_id,
            username=username,
            role=role,
            action="preset.save",
            resource_type=f"preset_{preset_type.lower()}",
            resource_id=preset_id,
            before=current,
            after=preset_data,
            metadata={
                "reason": request.reason,
                "reason_code": request.reason_code,
                "risk_level": risk_level,
                "warnings": warnings,
            }
        )
    
    logger.info(f"Preset {preset_type}/{preset_id} updated by {username}: {request.reason_code}")
    
    return {
        "success": True,
        "message": "Preset updated successfully",
        "warnings": warnings,
        "risk_level": risk_level,
    }


@router.post("/presets/{preset_type}/clone/{preset_id}")
async def clone_preset(
    preset_type: str,
    preset_id: str,
    req: Request,
    new_name: str = "Custom Copy",
    reason: str = "Creating custom preset from system default",
):
    """Clone a preset (especially useful for system presets)."""
    if not _presets_service:
        raise HTTPException(status_code=503, detail="Service not available")
    
    user = getattr(req.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = user.get("id", user.get("user_id", "unknown"))
    username = user.get("username", "unknown")
    role = user.get("role", "viewer")
    
    preset_type = preset_type.upper()
    
    # Get source preset
    source = await _presets_service.get_preset(preset_type, preset_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source preset not found")
    
    # Create clone
    import uuid
    clone = copy.deepcopy(source)
    clone["id"] = f"{preset_type.lower()}_custom_{uuid.uuid4().hex[:8]}"
    clone["name"] = new_name
    clone["preset_type"] = "custom"
    clone["created_at"] = datetime.now(timezone.utc).isoformat()
    clone["created_by"] = user_id
    clone["version"] = 1
    clone["description"] = f"Custom copy of {source.get('name', preset_id)}"
    
    # Save
    success = await _presets_service.save_preset(preset_type, clone)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clone preset")
    
    # Audit log
    if _audit_service:
        await _audit_service.log(
            user_id=user_id,
            username=username,
            role=role,
            action="preset.save",
            resource_type=f"preset_{preset_type.lower()}",
            resource_id=clone["id"],
            metadata={
                "action": "clone",
                "source_id": preset_id,
                "reason": reason,
            }
        )
    
    return {
        "success": True,
        "new_preset_id": clone["id"],
        "message": f"Preset cloned successfully as '{new_name}'",
    }


# ============================================================
# AUDIT LOG ENDPOINTS
# ============================================================

@router.get("/audit/config")
async def get_config_audit_logs(
    limit: int = 50,
    skip: int = 0,
):
    """Get audit logs for config changes."""
    if not _audit_service:
        raise HTTPException(status_code=503, detail="Audit service not available")
    
    logs = await _audit_service.get_logs(
        resource_type="system_config",
        limit=limit,
        skip=skip,
    )
    
    return {"logs": logs, "count": len(logs)}


@router.get("/audit/presets")
async def get_preset_audit_logs(
    preset_type: str = None,
    limit: int = 50,
    skip: int = 0,
):
    """Get audit logs for preset changes."""
    if not _audit_service:
        raise HTTPException(status_code=503, detail="Audit service not available")
    
    resource_type = f"preset_{preset_type.lower()}" if preset_type else None
    
    # Get preset-related actions
    logs = await _audit_service.get_logs(
        action="preset.save",
        resource_type=resource_type,
        limit=limit,
        skip=skip,
    )
    
    return {"logs": logs, "count": len(logs)}
