"""Audit logging service for tracking sensitive actions."""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # User management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ROLE_CHANGE = "user.role_change"
    USER_ACTIVATE = "user.activate"
    USER_DEACTIVATE = "user.deactivate"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    
    # Password reset flow
    PASSWORD_RESET_REQUEST = "auth.password_reset_request"
    PASSWORD_RESET = "auth.password_reset"
    
    # Settings changes
    SETTINGS_UPDATE = "settings.update"
    TRADING_MODE_CHANGE = "settings.trading_mode_change"
    RISK_SETTINGS_UPDATE = "settings.risk_update"
    
    # Agent management
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_START = "agent.start"
    AGENT_STOP = "agent.stop"
    
    # Agent Presets
    PRESET_SAVE = "preset.save"
    PRESET_DELETE = "preset.delete"
    PRESET_APPLY = "preset.apply"
    
    # Trading actions
    SWAP_PLAN_CREATE = "swap.plan_create"
    SWAP_APPROVE = "swap.approve"
    SWAP_REJECT = "swap.reject"
    SWAP_EXECUTE = "swap.execute"
    POSITION_CLOSE = "position.close"
    
    # System actions
    KILL_SWITCH_ACTIVATE = "system.kill_switch_activate"
    KILL_SWITCH_DEACTIVATE = "system.kill_switch_deactivate"
    RUNTIME_START = "system.runtime_start"
    RUNTIME_STOP = "system.runtime_stop"
    
    # Validation/Testing
    SCHEDULE_START = "schedule.start"
    SCHEDULE_STOP = "schedule.stop"
    BASELINE_CREATE = "baseline.create"
    VALIDATION_RUN = "validation.run"
    STRESS_TEST_RUN = "stress_test.run"
    
    # Credentials
    CREDENTIAL_STORE = "credential.store"
    CREDENTIAL_DELETE = "credential.delete"
    
    # DEX Sniper
    SNIPER_START = "sniper.start"
    SNIPER_STOP = "sniper.stop"
    SNIPER_CONFIG_UPDATE = "sniper.config_update"
    SNIPER_HARDENING_EVALUATE = "sniper.hardening_evaluate"
    SNIPER_HARDENED_PROFILE_GENERATED = "sniper.hardened_profile_generated"
    SNIPER_MODE_TOGGLE = "sniper.mode_toggle"
    SNIPER_MODE_BLOCK = "sniper.mode_block"


class AuditLog(BaseModel):
    """Audit log entry model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    user_id: str
    username: str
    role: str
    
    action: AuditAction
    resource_type: str
    resource_id: Optional[str] = None
    
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    
    ip: str
    user_agent: Optional[str] = None
    
    correlation_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditService:
    """Service for recording and querying audit logs."""
    
    def __init__(self, db: AsyncIOMotorDatabase, event_logger=None):
        self.db = db
        self.collection = db.audit_logs
        self.event_logger = event_logger
    
    async def initialize(self):
        """Create indexes for audit logs."""
        await self.collection.create_index("ts")
        await self.collection.create_index("user_id")
        await self.collection.create_index("action")
        await self.collection.create_index("resource_type")
        await self.collection.create_index("correlation_id")
        logger.info("Audit service initialized")
    
    async def log(
        self,
        user_id: str,
        username: str,
        role: str,
        action: "AuditAction | str",
        resource_type: str,
        resource_id: Optional[str] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        ip: str = "unknown",
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Record an audit log entry."""
        # Sanitize sensitive data
        if before:
            before = self._sanitize_data(before)
        if after:
            after = self._sanitize_data(after)
        
        # Convert string action to AuditAction if needed
        if isinstance(action, str):
            try:
                action = AuditAction(action)
            except ValueError:
                # If not a valid enum value, try to find by matching values
                for enum_action in AuditAction:
                    if enum_action.value == action:
                        action = enum_action
                        break
                else:
                    # Default to SETTINGS_UPDATE if no match
                    action = AuditAction.SETTINGS_UPDATE
        
        audit_log = AuditLog(
            user_id=user_id,
            username=username,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            ip=ip,
            user_agent=user_agent,
            correlation_id=correlation_id or str(uuid.uuid4()),
            success=success,
            error=error,
            metadata=metadata or {},
        )
        
        # Store in MongoDB
        doc = audit_log.model_dump()
        doc["ts"] = doc["ts"].isoformat()
        # Convert action enum to string value for MongoDB
        if hasattr(doc.get("action"), "value"):
            doc["action"] = doc["action"].value
        await self.collection.insert_one(doc)
        
        action_value = action.value if hasattr(action, 'value') else str(action)
        logger.info(f"Audit: {action_value} by {username} on {resource_type}/{resource_id}")
        
        # Emit event
        if self.event_logger:
            try:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.INFO,
                    category=EventCategory.SECURITY,
                    type="AUDIT_ACTION_RECORDED",
                    message=f"Audit: {action_value} by {username}",
                    context={
                        "action": action_value,
                        "user_id": user_id,
                        "username": username,
                        "role": role,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "success": success,
                    },
                    correlation_id=audit_log.correlation_id,
                )
            except Exception as e:
                logger.error(f"Failed to emit audit event: {e}")
        
        return audit_log
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields from data before logging."""
        sensitive_fields = [
            "password", "hashed_password", "password_hash",
            "api_key", "api_secret", "passphrase",
            "secret", "token", "access_token", "refresh_token",
            "private_key", "encryption_key", "master_key",
            "bot_token", "telegram_bot_token",
        ]
        
        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_fields):
                if isinstance(value, str) and len(value) > 4:
                    sanitized[key] = f"****{value[-4:]}"
                else:
                    sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query audit logs with filters."""
        query = {}
        
        if user_id:
            query["user_id"] = user_id
        if action:
            query["action"] = action
        if resource_type:
            query["resource_type"] = resource_type
        
        if from_ts or to_ts:
            query["ts"] = {}
            if from_ts:
                query["ts"]["$gte"] = from_ts.isoformat()
            if to_ts:
                query["ts"]["$lte"] = to_ts.isoformat()
        
        cursor = self.collection.find(
            query,
            {"_id": 0}
        ).sort("ts", -1).skip(skip).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_user_activity(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent activity for a specific user."""
        return await self.get_logs(user_id=user_id, limit=limit)
    
    async def get_security_events(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get security-related audit events."""
        security_actions = [
            AuditAction.USER_LOGIN_FAILED.value,
            AuditAction.USER_ROLE_CHANGE.value,
            AuditAction.USER_PASSWORD_RESET.value,
            AuditAction.KILL_SWITCH_ACTIVATE.value,
            AuditAction.TRADING_MODE_CHANGE.value,
        ]
        
        cursor = self.collection.find(
            {"action": {"$in": security_actions}},
            {"_id": 0}
        ).sort("ts", -1).limit(limit)
        
        return await cursor.to_list(limit)


# Global audit service instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> Optional[AuditService]:
    """Get the global audit service instance."""
    return _audit_service


def set_audit_service(service: AuditService):
    """Set the global audit service instance."""
    global _audit_service
    _audit_service = service
