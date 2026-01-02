"""Authentication service with JWT, RBAC, and encrypted exchange key storage."""
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from jose import JWTError, jwt
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, EmailStr
import logging
import bcrypt
import warnings

from services.rbac import UserRole

logger = logging.getLogger(__name__)

# Suppress passlib bcrypt version warning
warnings.filterwarnings("ignore", message=".*bcrypt.*")

# JWT Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY env var is required")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Encryption key for exchange API keys
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode())

# Password hashing - use bcrypt directly for compatibility
def _hash_password(password: str) -> str:
    """Hash password using bcrypt directly for compatibility."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def _verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt directly for compatibility."""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    email: Optional[EmailStr] = None
    role: str = UserRole.TESTER.value  # Default role for new users


class UserInDB(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    hashed_password: str
    role: str = UserRole.TESTER.value
    is_active: bool = True
    force_password_change: bool = False  # True for admin-created accounts
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: Dict[str, Any]


class ExchangeCredentials(BaseModel):
    exchange: str  # binance, okx, bybit
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None  # For OKX


class AuthService:
    """Authentication and user management service."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
        
    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt directly."""
        return _hash_password(password)
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against hash using bcrypt directly."""
        return _verify_password(plain_password, hashed_password)
    
    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        return self.fernet.encrypt(data.encode()).decode()
    
    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        return self.fernet.decrypt(encrypted_data.encode()).decode()
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token (string only)."""
        encoded_jwt, _expire = self._create_access_token(data, expires_delta)
        return encoded_jwt

    def _create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, datetime]:
        """Create JWT access token."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt, expire
    
    async def create_user(self, user_data: UserCreate) -> Optional[UserInDB]:
        """Create a new user."""
        # Check if username exists
        existing = await self.db.users.find_one({"username": user_data.username})
        if existing:
            return None
            
        # Create user document
        user_id = secrets.token_hex(16)
        user = UserInDB(
            id=user_id,
            username=user_data.username,
            email=user_data.email,
            hashed_password=self._hash_password(user_data.password),
            role=user_data.role,
        )
        
        doc = user.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await self.db.users.insert_one(doc)
        logger.info(f"Created user: {user_data.username}")
        
        return user
    
    async def authenticate_user(self, username: str, password: str, ip: str = "unknown") -> Optional[Token]:
        """Authenticate user and return token."""
        user_doc = await self.db.users.find_one({"username": username}, {"_id": 0})
        
        if not user_doc:
            # Log failed login attempt
            await self._log_login_attempt(username, False, ip, "User not found")
            return None
            
        if not self._verify_password(password, user_doc['hashed_password']):
            await self._log_login_attempt(username, False, ip, "Invalid password")
            return None
            
        if not user_doc.get('is_active', True):
            await self._log_login_attempt(username, False, ip, "Account disabled")
            return None
        
        # Update last login
        await self.db.users.update_one(
            {"id": user_doc['id']},
            {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Log successful login
        await self._log_login_attempt(username, True, ip)
        
        token_data = {
            "sub": user_doc['id'],
            "username": user_doc['username'],
            "role": user_doc['role'],
        }
        
        access_token, expires_at = self._create_access_token(token_data)
        
        return Token(
            access_token=access_token,
            expires_at=expires_at,
            user={
                "id": user_doc['id'],
                "username": user_doc['username'],
                "email": user_doc.get('email'),
                "role": user_doc['role'],
                "force_password_change": user_doc.get('force_password_change', False),
            }
        )
    
    async def _log_login_attempt(self, username: str, success: bool, ip: str, reason: str = None):
        """Log login attempts for security auditing."""
        await self.db.login_attempts.insert_one({
            "username": username,
            "success": success,
            "ip": ip,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id is None:
                return None
                
            # Verify user still exists and is active
            user_doc = await self.db.users.find_one({"id": user_id, "is_active": True}, {"_id": 0})
            if not user_doc:
                return None
                
            return {
                "id": user_id,
                "user_id": user_id,
                "username": payload.get("username"),
                "role": payload.get("role"),
                "status": user_doc.get("status"),
                "is_active": user_doc.get("is_active", True),
            }
            
        except JWTError:
            return None
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        user_doc = await self.db.users.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
        return user_doc
    
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user profile."""
        # Don't allow updating sensitive fields directly
        safe_updates = {k: v for k, v in updates.items() if k not in ['id', 'hashed_password']}
        
        if 'password' in updates:
            safe_updates['hashed_password'] = self._hash_password(updates['password'])
            del safe_updates['password']
        
        result = await self.db.users.update_one(
            {"id": user_id},
            {"$set": safe_updates}
        )
        return result.modified_count > 0
    
    # Exchange Credentials Management
    async def store_exchange_credentials(self, user_id: str, creds: ExchangeCredentials) -> bool:
        """Store encrypted exchange credentials."""
        encrypted_key = self._encrypt(creds.api_key)
        encrypted_secret = self._encrypt(creds.api_secret)
        encrypted_passphrase = self._encrypt(creds.passphrase) if creds.passphrase else None
        
        doc = {
            "user_id": user_id,
            "exchange": creds.exchange,
            "api_key_encrypted": encrypted_key,
            "api_secret_encrypted": encrypted_secret,
            "passphrase_encrypted": encrypted_passphrase,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Upsert - replace if exists for same user/exchange
        await self.db.exchange_credentials.update_one(
            {"user_id": user_id, "exchange": creds.exchange},
            {"$set": doc},
            upsert=True
        )
        
        logger.info(f"Stored exchange credentials for user {user_id}: {creds.exchange}")
        return True
    
    async def get_exchange_credentials(self, user_id: str, exchange: str) -> Optional[ExchangeCredentials]:
        """Retrieve and decrypt exchange credentials."""
        doc = await self.db.exchange_credentials.find_one(
            {"user_id": user_id, "exchange": exchange},
            {"_id": 0}
        )
        
        if not doc:
            return None
        
        return ExchangeCredentials(
            exchange=doc['exchange'],
            api_key=self._decrypt(doc['api_key_encrypted']),
            api_secret=self._decrypt(doc['api_secret_encrypted']),
            passphrase=self._decrypt(doc['passphrase_encrypted']) if doc.get('passphrase_encrypted') else None,
        )
    
    async def list_exchange_credentials(self, user_id: str) -> List[Dict[str, Any]]:
        """List all exchange credentials for a user (without secrets)."""
        docs = await self.db.exchange_credentials.find(
            {"user_id": user_id},
            {"_id": 0, "api_key_encrypted": 0, "api_secret_encrypted": 0, "passphrase_encrypted": 0}
        ).to_list(100)
        
        return docs
    
    async def delete_exchange_credentials(self, user_id: str, exchange: str) -> bool:
        """Delete exchange credentials."""
        result = await self.db.exchange_credentials.delete_one(
            {"user_id": user_id, "exchange": exchange}
        )
        return result.deleted_count > 0
    
    async def ensure_admin_exists(self):
        """Ensure at least one owner user exists.

        NOTE: Seeding must be performed only when users collection is empty.
        That logic is handled by server startup.
        """
        return
    
    async def _create_default_user(self, username: str, password: str, role: str):
        """Create a default user with force_password_change=True."""
        user_id = secrets.token_hex(16)
        user = UserInDB(
            id=user_id,
            username=username,
            hashed_password=self._hash_password(password),
            role=role,
            is_active=True,
            force_password_change=True,  # CRITICAL: Must change password
        )
        
        doc = user.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['is_default_credentials'] = True  # Mark as default credentials
        
        await self.db.users.insert_one(doc)
    
    # ============ Security Hardening ============
    
    # Known default passwords for security checking
    # SECURITY HARDENING DISABLED: kept for potential future re-introduction of auth.
    DEFAULT_PASSWORDS = {
        "owner": "owner123!@#",
        "admin": "admin123!@#",
    }
    
    async def check_default_credentials(self, event_logger=None) -> Dict[str, Any]:
        """
        Check for users with default credentials.
        Returns a report of findings.
        """
        findings = []
        users_with_defaults = []
        
        for username, default_password in self.DEFAULT_PASSWORDS.items():
            user = await self.db.users.find_one({"username": username}, {"_id": 0})
            if user:
                # Check if password is still the default
                if self._verify_password(default_password, user.get('hashed_password', '')):
                    users_with_defaults.append({
                        "username": username,
                        "role": user.get('role'),
                        "is_active": user.get('is_active', True),
                        "force_password_change": user.get('force_password_change', False),
                    })
                    findings.append(f"User '{username}' has default password")
        
        # Emit CRITICAL event if defaults found
        if users_with_defaults and event_logger:
            for user in users_with_defaults:
                try:
                    from services.event_logger import EventSeverity, EventCategory
                    await event_logger.emit(
                        severity=EventSeverity.CRITICAL,
                        category=EventCategory.SECURITY,
                        type="SECURITY_DEFAULT_CREDENTIALS_DETECTED",
                        message=f"User '{user['username']}' has default credentials - SECURITY RISK",
                        context={"username": user['username'], "role": user['role']},
                    )
                except Exception as e:
                    logger.error(f"Failed to emit security event: {e}")
        
        return {
            "has_default_credentials": len(users_with_defaults) > 0,
            "users_with_defaults": users_with_defaults,
            "findings": findings,
        }
    
    async def enforce_default_credential_security(self, event_logger=None) -> Dict[str, Any]:
        """
        Enforce security for default credentials:
        - Set force_password_change=True for users with default passwords
        - Emit security events
        """
        actions_taken = []
        
        for username, default_password in self.DEFAULT_PASSWORDS.items():
            user = await self.db.users.find_one({"username": username}, {"_id": 0})
            if user:
                # Check if password is still the default
                if self._verify_password(default_password, user.get('hashed_password', '')):
                    # Force password change
                    await self.db.users.update_one(
                        {"username": username},
                        {"$set": {
                            "force_password_change": True,
                            "is_default_credentials": True,
                            "security_flag_at": datetime.now(timezone.utc).isoformat(),
                        }}
                    )
                    actions_taken.append(f"Set force_password_change=True for '{username}'")
                    
                    # Emit event
                    if event_logger:
                        try:
                            from services.event_logger import EventSeverity, EventCategory
                            await event_logger.emit(
                                severity=EventSeverity.CRITICAL,
                                category=EventCategory.SECURITY,
                                type="SECURITY_DEFAULT_CREDENTIALS_DETECTED",
                                message=f"User '{username}' forced to change default password",
                                context={"username": username, "action": "force_password_change"},
                            )
                        except Exception as e:
                            logger.error(f"Failed to emit security event: {e}")
        
        return {
            "actions_taken": actions_taken,
            "users_secured": len(actions_taken),
        }
    
    async def security_hardening(self, event_logger=None) -> Dict[str, Any]:
        """
        Full security hardening:
        1. Check for default credentials
        2. Force password change for users with defaults
        3. Ensure at least one active OWNER without default password
        4. Return comprehensive report
        """
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks_performed": [],
            "actions_taken": [],
            "warnings": [],
            "status": "unknown",
        }
        
        # 1. Check for default credentials
        check_result = await self.check_default_credentials(event_logger)
        report["checks_performed"].append("default_credentials_check")
        
        if check_result["has_default_credentials"]:
            report["warnings"].append(f"Found {len(check_result['users_with_defaults'])} users with default credentials")
            
            # 2. Enforce security
            enforce_result = await self.enforce_default_credential_security(event_logger)
            report["actions_taken"].extend(enforce_result["actions_taken"])
        
        # 3. Check for at least one active OWNER
        active_owners = await self.db.users.count_documents({
            "role": UserRole.OWNER.value,
            "is_active": True,
        })
        report["checks_performed"].append("active_owner_check")
        
        if active_owners == 0:
            report["warnings"].append("No active OWNER found - system may be inaccessible")
            report["status"] = "critical"
        else:
            # Check if any OWNER has non-default password
            owner_without_default = False
            owners = await self.db.users.find({"role": UserRole.OWNER.value}).to_list(10)
            for owner in owners:
                is_default = False
                for username, default_pwd in self.DEFAULT_PASSWORDS.items():
                    if owner.get('username') == username:
                        if self._verify_password(default_pwd, owner.get('hashed_password', '')):
                            is_default = True
                            break
                if not is_default:
                    owner_without_default = True
                    break
            
            if not owner_without_default:
                report["warnings"].append("All OWNER accounts have default passwords - change immediately!")
                report["status"] = "warning"
            else:
                report["status"] = "secure"
        
        # Emit final event
        if event_logger:
            try:
                from services.event_logger import EventSeverity, EventCategory
                severity = EventSeverity.CRITICAL if report["status"] == "critical" else (
                    EventSeverity.WARNING if report["status"] == "warning" else EventSeverity.INFO
                )
                await event_logger.emit(
                    severity=severity,
                    category=EventCategory.SECURITY,
                    type="SECURITY_HARDENING_COMPLETED",
                    message=f"Security hardening completed - Status: {report['status']}",
                    context=report,
                )
            except Exception as e:
                logger.error(f"Failed to emit security event: {e}")
        
        return report
    
    async def mark_credentials_as_changed(self, user_id: str, event_logger=None):
        """Mark that a user has changed their default credentials."""
        user = await self.db.users.find_one({"id": user_id})
        if user and user.get('is_default_credentials'):
            await self.db.users.update_one(
                {"id": user_id},
                {"$set": {
                    "is_default_credentials": False,
                    "credentials_changed_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            
            # Emit resolution event
            if event_logger:
                try:
                    from services.event_logger import EventSeverity, EventCategory
                    await event_logger.emit(
                        severity=EventSeverity.INFO,
                        category=EventCategory.SECURITY,
                        type="SECURITY_DEFAULT_CREDENTIALS_REVOKED",
                        message=f"User '{user.get('username')}' changed default credentials",
                        context={"username": user.get('username'), "user_id": user_id},
                    )
                except Exception as e:
                    logger.error(f"Failed to emit security event: {e}")
    
    # ============ Admin User Management ============
    
    async def admin_create_user(
        self, 
        username: str, 
        email: Optional[str],
        role: str,
        created_by: str,
    ) -> Tuple[Optional[UserInDB], str]:
        """
        Admin creates a new user with a temporary password.
        
        Returns:
            (user, temporary_password) or (None, error_message)
        """
        # Check if username exists
        existing = await self.db.users.find_one({"username": username})
        if existing:
            return None, "Username already exists"
        
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        
        user_id = secrets.token_hex(16)
        user = UserInDB(
            id=user_id,
            username=username,
            email=email,
            hashed_password=self._hash_password(temp_password),
            role=role,
            is_active=True,
            force_password_change=True,  # Must change on first login
        )
        
        doc = user.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['created_by'] = created_by
        
        await self.db.users.insert_one(doc)
        logger.info(f"Admin created user: {username} with role {role}")
        
        return user, temp_password
    
    async def admin_list_users(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """List all users (admin only)."""
        users = await self.db.users.find(
            {},
            {"_id": 0, "hashed_password": 0}
        ).skip(skip).limit(limit).to_list(limit)
        return users
    
    async def admin_update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
        updated_by: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Admin updates a user.
        
        Allowed updates: role, is_active, email
        """
        allowed_fields = ["role", "is_active", "email"]
        safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not safe_updates:
            return False, "No valid fields to update"
        
        # Prevent demoting last owner
        if "role" in safe_updates:
            current_user = await self.db.users.find_one({"id": user_id})
            if current_user and current_user.get("role") == UserRole.OWNER.value:
                # Check if there are other owners
                owner_count = await self.db.users.count_documents({"role": UserRole.OWNER.value})
                if owner_count <= 1 and safe_updates["role"] != UserRole.OWNER.value:
                    return False, "Cannot demote the last owner"
        
        safe_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        safe_updates["updated_by"] = updated_by
        
        result = await self.db.users.update_one(
            {"id": user_id},
            {"$set": safe_updates}
        )
        
        if result.modified_count > 0:
            logger.info(f"Admin updated user {user_id}: {list(safe_updates.keys())}")
            return True, None
        return False, "User not found or no changes made"
    
    async def admin_reset_password(
        self,
        user_id: str,
        reset_by: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Admin resets a user's password.
        
        Returns:
            (temporary_password, error_message)
        """
        user = await self.db.users.find_one({"id": user_id})
        if not user:
            return None, "User not found"
        
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        
        await self.db.users.update_one(
            {"id": user_id},
            {"$set": {
                "hashed_password": self._hash_password(temp_password),
                "force_password_change": True,
                "password_reset_at": datetime.now(timezone.utc).isoformat(),
                "password_reset_by": reset_by,
            }}
        )
        
        logger.info(f"Admin reset password for user {user_id}")
        return temp_password, None
    
    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        User changes their own password.
        """
        user = await self.db.users.find_one({"id": user_id})
        if not user:
            return False, "User not found"
        
        if not self._verify_password(current_password, user["hashed_password"]):
            return False, "Current password is incorrect"
        
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters"
        
        await self.db.users.update_one(
            {"id": user_id},
            {"$set": {
                "hashed_password": self._hash_password(new_password),
                "force_password_change": False,
                "password_changed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        
        logger.info(f"User {user_id} changed password")
        return True, None
    
    async def admin_delete_user(self, user_id: str, deleted_by: str) -> Tuple[bool, Optional[str]]:
        """
        Admin deletes a user (soft delete - sets is_active to False).
        """
        user = await self.db.users.find_one({"id": user_id})
        if not user:
            return False, "User not found"
        
        # Prevent deleting last owner
        if user.get("role") == UserRole.OWNER.value:
            owner_count = await self.db.users.count_documents({"role": UserRole.OWNER.value})
            if owner_count <= 1:
                return False, "Cannot delete the last owner"
        
        # Soft delete
        await self.db.users.update_one(
            {"id": user_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": deleted_by,
            }}
        )
        
        logger.info(f"Admin deleted user {user_id}")
        return True, None
