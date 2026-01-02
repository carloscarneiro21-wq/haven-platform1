"""Role-Based Access Control (RBAC) system for the trading platform."""
from enum import Enum
from typing import List, Optional, Dict, Any, Callable
from functools import wraps
from fastapi import HTTPException, Depends, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles with hierarchical permissions."""
    OWNER = "owner"      # Full access, can manage other admins
    ADMIN = "admin"      # Full access except owner-only actions
    TESTER = "tester"    # Can view and run simulations, no config changes
    VIEWER = "viewer"    # Read-only access


# Role hierarchy (higher index = more permissions)
ROLE_HIERARCHY = {
    UserRole.VIEWER: 0,
    UserRole.TESTER: 1,
    UserRole.ADMIN: 2,
    UserRole.OWNER: 3,
}


class Permission(str, Enum):
    """Granular permissions for endpoints."""
    # Read permissions
    READ_DASHBOARD = "read:dashboard"
    READ_AGENTS = "read:agents"
    READ_POSITIONS = "read:positions"
    READ_RISK = "read:risk"
    READ_EVENTS = "read:events"
    READ_LOGS = "read:logs"
    READ_MONITORING = "read:monitoring"
    READ_VALIDATION = "read:validation"
    READ_DEX = "read:dex"
    READ_SETTINGS = "read:settings"
    READ_AUDIT = "read:audit"
    
    # Write permissions
    WRITE_AGENTS = "write:agents"
    WRITE_RISK = "write:risk"
    WRITE_SETTINGS = "write:settings"
    WRITE_TRADING_MODE = "write:trading_mode"
    WRITE_CREDENTIALS = "write:credentials"
    
    # Action permissions
    ACTION_RUNTIME_CONTROL = "action:runtime_control"
    ACTION_KILL_SWITCH = "action:kill_switch"
    ACTION_STRESS_TEST = "action:stress_test"
    ACTION_VALIDATION_RUN = "action:validation_run"
    ACTION_SCHEDULE_CONTROL = "action:schedule_control"
    ACTION_BASELINE_CREATE = "action:baseline_create"
    ACTION_DEX_TRADE = "action:dex_trade"
    ACTION_SWAP_APPROVE = "action:swap_approve"
    ACTION_SNIPER_CONTROL = "action:sniper_control"
    
    # Admin permissions
    ADMIN_USER_MANAGE = "admin:user_manage"
    ADMIN_AUDIT_VIEW = "admin:audit_view"
    
    # Owner-only permissions
    OWNER_HARD_CAPS = "owner:hard_caps"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.VIEWER: [
        Permission.READ_DASHBOARD,
        Permission.READ_AGENTS,
        Permission.READ_POSITIONS,
        Permission.READ_RISK,
        Permission.READ_EVENTS,
        Permission.READ_LOGS,
        Permission.READ_MONITORING,
        Permission.READ_VALIDATION,
        Permission.READ_DEX,
        Permission.READ_SETTINGS,
    ],
    UserRole.TESTER: [
        # Inherits all VIEWER permissions
        Permission.READ_DASHBOARD,
        Permission.READ_AGENTS,
        Permission.READ_POSITIONS,
        Permission.READ_RISK,
        Permission.READ_EVENTS,
        Permission.READ_LOGS,
        Permission.READ_MONITORING,
        Permission.READ_VALIDATION,
        Permission.READ_DEX,
        Permission.READ_SETTINGS,
        # Additional tester permissions
        Permission.WRITE_CREDENTIALS,  # Can store own exchange keys
    ],
    UserRole.ADMIN: [
        # All read permissions
        Permission.READ_DASHBOARD,
        Permission.READ_AGENTS,
        Permission.READ_POSITIONS,
        Permission.READ_RISK,
        Permission.READ_EVENTS,
        Permission.READ_LOGS,
        Permission.READ_MONITORING,
        Permission.READ_VALIDATION,
        Permission.READ_DEX,
        Permission.READ_SETTINGS,
        Permission.READ_AUDIT,
        # All write permissions
        Permission.WRITE_AGENTS,
        Permission.WRITE_RISK,
        Permission.WRITE_SETTINGS,
        Permission.WRITE_TRADING_MODE,
        Permission.WRITE_CREDENTIALS,
        # All action permissions
        Permission.ACTION_RUNTIME_CONTROL,
        Permission.ACTION_KILL_SWITCH,
        Permission.ACTION_STRESS_TEST,
        Permission.ACTION_VALIDATION_RUN,
        Permission.ACTION_SCHEDULE_CONTROL,
        Permission.ACTION_BASELINE_CREATE,
        Permission.ACTION_DEX_TRADE,
        Permission.ACTION_SWAP_APPROVE,
        Permission.ACTION_SNIPER_CONTROL,
        # Admin permissions
        Permission.ADMIN_USER_MANAGE,
        Permission.ADMIN_AUDIT_VIEW,
    ],
    UserRole.OWNER: [
        # All permissions including owner-only
        Permission.READ_DASHBOARD,
        Permission.READ_AGENTS,
        Permission.READ_POSITIONS,
        Permission.READ_RISK,
        Permission.READ_EVENTS,
        Permission.READ_LOGS,
        Permission.READ_MONITORING,
        Permission.READ_VALIDATION,
        Permission.READ_DEX,
        Permission.READ_SETTINGS,
        Permission.READ_AUDIT,
        Permission.WRITE_AGENTS,
        Permission.WRITE_RISK,
        Permission.WRITE_SETTINGS,
        Permission.WRITE_TRADING_MODE,
        Permission.WRITE_CREDENTIALS,
        Permission.ACTION_RUNTIME_CONTROL,
        Permission.ACTION_KILL_SWITCH,
        Permission.ACTION_STRESS_TEST,
        Permission.ACTION_VALIDATION_RUN,
        Permission.ACTION_SCHEDULE_CONTROL,
        Permission.ACTION_BASELINE_CREATE,
        Permission.ACTION_DEX_TRADE,
        Permission.ACTION_SWAP_APPROVE,
        Permission.ACTION_SNIPER_CONTROL,
        Permission.ADMIN_USER_MANAGE,
        Permission.ADMIN_AUDIT_VIEW,
        Permission.OWNER_HARD_CAPS,
    ],
}


def has_permission(role: str, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    try:
        user_role = UserRole(role)
        return permission in ROLE_PERMISSIONS.get(user_role, [])
    except ValueError:
        return False


def has_role_or_higher(user_role: str, required_role: UserRole) -> bool:
    """Check if user has the required role or higher."""
    try:
        user_role_enum = UserRole(user_role)
        return ROLE_HIERARCHY.get(user_role_enum, -1) >= ROLE_HIERARCHY.get(required_role, 999)
    except ValueError:
        return False


class RBACDependency:
    """FastAPI dependency for role-based access control."""
    
    def __init__(self, auth_service):
        self.auth_service = auth_service
        self.security = HTTPBearer(auto_error=False)
    
    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = None):
        """Get current user from token (optional auth)."""
        if not credentials:
            return None
        try:
            return await self.auth_service.verify_token(credentials.credentials)
        except:
            return None
    
    async def require_auth(self, credentials: HTTPAuthorizationCredentials):
        """Require authentication."""
        if not credentials:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = await self.auth_service.verify_token(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        if not user.get("is_active", True):
            raise HTTPException(status_code=403, detail="Account is disabled")
        return user
    
    def require_role(self, *allowed_roles: UserRole):
        """Require one of the specified roles."""
        async def dependency(credentials: HTTPAuthorizationCredentials = Security(self.security)):
            user = await self.require_auth(credentials)
            user_role = user.get("role", "viewer")
            
            if not any(has_role_or_higher(user_role, role) for role in allowed_roles):
                raise HTTPException(
                    status_code=403, 
                    detail=f"Required role: {', '.join(r.value for r in allowed_roles)}. Your role: {user_role}"
                )
            return user
        return dependency
    
    def require_permission(self, permission: Permission):
        """Require a specific permission."""
        async def dependency(credentials: HTTPAuthorizationCredentials = Security(self.security)):
            user = await self.require_auth(credentials)
            user_role = user.get("role", "viewer")
            
            if not has_permission(user_role, permission):
                raise HTTPException(
                    status_code=403, 
                    detail=f"Permission denied: {permission.value}"
                )
            return user
        return dependency
    
    def require_owner(self):
        """Require owner role."""
        return self.require_role(UserRole.OWNER)
    
    def require_admin(self):
        """Require admin or owner role."""
        return self.require_role(UserRole.ADMIN, UserRole.OWNER)
    
    def require_tester_or_higher(self):
        """Require tester, admin, or owner role."""
        return self.require_role(UserRole.TESTER, UserRole.ADMIN, UserRole.OWNER)
    
    def require_viewer_or_higher(self):
        """Require any authenticated user."""
        return self.require_role(UserRole.VIEWER, UserRole.TESTER, UserRole.ADMIN, UserRole.OWNER)


# Endpoint protection map - defines minimum role/permission for each endpoint pattern
ENDPOINT_PROTECTION = {
    # Public endpoints (no auth required)
    "/api/": None,
    "/api/health": None,
    "/api/heartbeat": None,
    "/api/auth/login": None,
    "/api/auth/register": None,
    
    # Read-only (VIEWER+)
    "/api/dashboard": Permission.READ_DASHBOARD,
    "/api/portfolio": Permission.READ_DASHBOARD,
    "/api/agents": Permission.READ_AGENTS,
    "/api/positions": Permission.READ_POSITIONS,
    "/api/orders": Permission.READ_POSITIONS,
    "/api/trades": Permission.READ_POSITIONS,
    "/api/risk": Permission.READ_RISK,
    "/api/events": Permission.READ_EVENTS,
    "/api/logs": Permission.READ_LOGS,
    "/api/monitoring": Permission.READ_MONITORING,
    "/api/validation/status": Permission.READ_VALIDATION,
    "/api/validation/result": Permission.READ_VALIDATION,
    "/api/validation/history": Permission.READ_VALIDATION,
    "/api/dex/status": Permission.READ_DEX,
    "/api/dex/pairs": Permission.READ_DEX,
    "/api/dex/token/score": Permission.READ_DEX,
    "/api/dex/positions": Permission.READ_DEX,
    "/api/dex/swaps": Permission.READ_DEX,
    "/api/market": Permission.READ_DASHBOARD,
    "/api/settings/trading-mode": Permission.READ_SETTINGS,
    
    # Write operations (ADMIN+)
    "/api/agents/*/control": Permission.WRITE_AGENTS,
    "/api/agents/*/config": Permission.WRITE_AGENTS,
    "/api/risk/settings": Permission.WRITE_RISK,
    "/api/risk/kill-switch": Permission.ACTION_KILL_SWITCH,
    "/api/notifications/config": Permission.WRITE_SETTINGS,
    "/api/capital": Permission.WRITE_SETTINGS,
    
    # Action endpoints (ADMIN+)
    "/api/runtime/control": Permission.ACTION_RUNTIME_CONTROL,
    "/api/runtime/cycle": Permission.ACTION_RUNTIME_CONTROL,
    "/api/stress-lab/run": Permission.ACTION_STRESS_TEST,
    "/api/stress-tests/run": Permission.ACTION_STRESS_TEST,
    "/api/validation/run": Permission.ACTION_VALIDATION_RUN,
    "/api/validation/schedule": Permission.ACTION_SCHEDULE_CONTROL,
    "/api/validation/watch": Permission.ACTION_SCHEDULE_CONTROL,
    "/api/baseline/create": Permission.ACTION_BASELINE_CREATE,
    
    # DEX Trading (ADMIN+)
    "/api/dex/swap/plan": Permission.ACTION_DEX_TRADE,
    "/api/dex/swap/*/approve": Permission.ACTION_SWAP_APPROVE,
    "/api/dex/swap/*/reject": Permission.ACTION_SWAP_APPROVE,
    "/api/dex/sniper/start": Permission.ACTION_SNIPER_CONTROL,
    "/api/dex/sniper/stop": Permission.ACTION_SNIPER_CONTROL,
    "/api/dex/tx/submitted": Permission.ACTION_DEX_TRADE,
    "/api/dex/position/*/close": Permission.ACTION_DEX_TRADE,
    
    # Settings (ADMIN+)
    "/api/settings/trading-mode:POST": Permission.WRITE_TRADING_MODE,
    
    # Admin endpoints (ADMIN/OWNER only)
    "/api/admin/users": Permission.ADMIN_USER_MANAGE,
    "/api/admin/audit": Permission.ADMIN_AUDIT_VIEW,
}


def get_required_permission(path: str, method: str = "GET") -> Optional[Permission]:
    """Get required permission for an endpoint."""
    # Check exact match with method
    key_with_method = f"{path}:{method}"
    if key_with_method in ENDPOINT_PROTECTION:
        return ENDPOINT_PROTECTION[key_with_method]
    
    # Check exact match
    if path in ENDPOINT_PROTECTION:
        return ENDPOINT_PROTECTION[path]
    
    # Check prefix matches
    for pattern, permission in ENDPOINT_PROTECTION.items():
        if "*" in pattern:
            # Simple wildcard matching
            prefix = pattern.split("*")[0]
            if path.startswith(prefix):
                return permission
        elif path.startswith(pattern):
            return permission
    
    # Default: require authentication
    return Permission.READ_DASHBOARD
