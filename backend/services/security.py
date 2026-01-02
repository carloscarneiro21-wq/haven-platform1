"""Security utilities for encryption, hard caps, and log sanitization."""
import os
import base64
import secrets
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


# ============ Encryption ============

class SecretManager:
    """
    Manages encryption/decryption of sensitive data using AES-256-GCM.
    
    Uses APP_MASTER_KEY from environment for encryption.
    Falls back to generated key if not set (NOT recommended for production).
    """
    
    def __init__(self):
        master_key = os.environ.get("APP_MASTER_KEY")
        
        if master_key:
            # Decode base64 master key
            try:
                self.key = base64.b64decode(master_key)
                if len(self.key) != 32:
                    raise ValueError("Master key must be 32 bytes (256 bits)")
            except Exception as e:
                logger.error(f"Invalid APP_MASTER_KEY: {e}")
                self.key = self._generate_key()
        else:
            logger.warning("APP_MASTER_KEY not set! Using generated key (NOT production-safe)")
            self.key = self._generate_key()
        
        self.aesgcm = AESGCM(self.key)
    
    def _generate_key(self) -> bytes:
        """Generate a random 256-bit key."""
        return secrets.token_bytes(32)
    
    def encrypt(self, plaintext: str) -> Dict[str, str]:
        """
        Encrypt a string using AES-256-GCM.
        
        Returns:
            Dict with 'encrypted_value', 'nonce', and 'created_at'
        """
        nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode(), None)
        
        return {
            "encrypted_value": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def decrypt(self, encrypted_data: Dict[str, str]) -> str:
        """
        Decrypt data encrypted with encrypt().
        
        Args:
            encrypted_data: Dict with 'encrypted_value' and 'nonce'
        
        Returns:
            Decrypted plaintext string
        """
        ciphertext = base64.b64decode(encrypted_data["encrypted_value"])
        nonce = base64.b64decode(encrypted_data["nonce"])
        
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
    
    def mask_secret(self, value: str, visible_chars: int = 4) -> str:
        """
        Mask a secret value for display.
        
        Returns: "****XXXX" where XXXX is the last 4 characters
        """
        if not value or len(value) <= visible_chars:
            return "****"
        return f"****{value[-visible_chars:]}"
    
    def is_configured(self, encrypted_data: Dict[str, str]) -> bool:
        """Check if an encrypted secret is configured."""
        return bool(encrypted_data and encrypted_data.get("encrypted_value"))


# Global secret manager instance
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get the global secret manager instance."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager


# ============ Live Trading Hard Caps ============

class LiveHardCaps:
    """
    Hard limits for live trading to prevent catastrophic losses.
    These cannot be bypassed even by OWNER role.
    """
    
    # DEX Hard Caps (PancakeSwap/BSC)
    DEX_MAX_TRADE_SIZE_EUR = 5.0  # Max €5 per trade
    DEX_MAX_SLIPPAGE_PCT = 2.0   # Max 2% slippage
    DEX_MAX_TRADES_PER_DAY = 3   # Max 3 trades per day
    
    # CEX Hard Caps (Kraken/Binance)
    CEX_MAX_ORDER_SIZE_EUR = 10.0  # Max €10 per order
    CEX_MAX_DAILY_VOLUME_EUR = 50.0  # Max €50 daily volume
    CEX_MAX_OPEN_ORDERS = 5  # Max 5 concurrent orders
    
    # Global Hard Caps
    MAX_DAILY_LOSS_EUR = 20.0  # Max €20 daily loss before kill switch
    
    def __init__(self, db: AsyncIOMotorDatabase, event_logger=None):
        self.db = db
        self.event_logger = event_logger
        self._daily_stats = {}
    
    async def check_dex_trade(
        self,
        amount_eur: float,
        slippage_pct: float,
        user_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a DEX trade is within hard caps.
        
        Returns:
            (allowed, rejection_reason)
        """
        # Check trade size
        if amount_eur > self.DEX_MAX_TRADE_SIZE_EUR:
            reason = f"Trade size €{amount_eur:.2f} exceeds hard cap of €{self.DEX_MAX_TRADE_SIZE_EUR:.2f}"
            await self._emit_blocked_event("DEX_TRADE", reason, user_id)
            return False, reason
        
        # Check slippage
        if slippage_pct > self.DEX_MAX_SLIPPAGE_PCT:
            reason = f"Slippage {slippage_pct:.1f}% exceeds hard cap of {self.DEX_MAX_SLIPPAGE_PCT:.1f}%"
            await self._emit_blocked_event("DEX_TRADE", reason, user_id)
            return False, reason
        
        # Check daily trade count
        trades_today = await self._get_daily_dex_trades(user_id)
        if trades_today >= self.DEX_MAX_TRADES_PER_DAY:
            reason = f"Daily trade limit ({self.DEX_MAX_TRADES_PER_DAY}) reached"
            await self._emit_blocked_event("DEX_TRADE", reason, user_id)
            return False, reason
        
        return True, None
    
    async def check_cex_order(
        self,
        amount_eur: float,
        user_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a CEX order is within hard caps.
        
        Returns:
            (allowed, rejection_reason)
        """
        # Check order size
        if amount_eur > self.CEX_MAX_ORDER_SIZE_EUR:
            reason = f"Order size €{amount_eur:.2f} exceeds hard cap of €{self.CEX_MAX_ORDER_SIZE_EUR:.2f}"
            await self._emit_blocked_event("CEX_ORDER", reason, user_id)
            return False, reason
        
        # Check daily volume
        daily_volume = await self._get_daily_cex_volume(user_id)
        if daily_volume + amount_eur > self.CEX_MAX_DAILY_VOLUME_EUR:
            reason = f"Daily volume would exceed €{self.CEX_MAX_DAILY_VOLUME_EUR:.2f} limit"
            await self._emit_blocked_event("CEX_ORDER", reason, user_id)
            return False, reason
        
        # Check open orders count
        open_orders = await self._get_open_orders_count(user_id)
        if open_orders >= self.CEX_MAX_OPEN_ORDERS:
            reason = f"Max open orders ({self.CEX_MAX_OPEN_ORDERS}) reached"
            await self._emit_blocked_event("CEX_ORDER", reason, user_id)
            return False, reason
        
        return True, None
    
    async def check_daily_loss(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if daily loss limit is exceeded.
        
        Returns:
            (ok, reason) - ok=False means should trigger kill switch
        """
        daily_pnl = await self._get_daily_pnl(user_id)
        
        if daily_pnl < -self.MAX_DAILY_LOSS_EUR:
            reason = f"Daily loss €{abs(daily_pnl):.2f} exceeds hard cap of €{self.MAX_DAILY_LOSS_EUR:.2f}"
            await self._emit_blocked_event("DAILY_LOSS", reason, user_id)
            return False, reason
        
        return True, None
    
    async def _get_daily_dex_trades(self, user_id: str) -> int:
        """Get count of DEX trades today."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count = await self.db.dex_positions.count_documents({
            "entry_time": {"$gte": today.isoformat()},
        })
        return count
    
    async def _get_daily_cex_volume(self, user_id: str) -> float:
        """Get total CEX trading volume today in EUR."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        pipeline = [
            {"$match": {"executed_at": {"$gte": today.isoformat()}}},
            {"$group": {"_id": None, "total": {"$sum": "$value"}}}
        ]
        result = await self.db.trades.aggregate(pipeline).to_list(1)
        return result[0]["total"] if result else 0.0
    
    async def _get_open_orders_count(self, user_id: str) -> int:
        """Get count of open orders."""
        return await self.db.orders.count_documents({"status": {"$in": ["open", "pending"]}})
    
    async def _get_daily_pnl(self, user_id: str) -> float:
        """Get total PnL for today."""
        doc = await self.db.risk_settings.find_one({}, {"_id": 0, "current_daily_pnl": 1})
        return doc.get("current_daily_pnl", 0.0) if doc else 0.0
    
    async def _emit_blocked_event(self, action_type: str, reason: str, user_id: str):
        """Emit CRITICAL event for blocked action."""
        if self.event_logger:
            try:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.CRITICAL,
                    category=EventCategory.RISK,
                    type="LIVE_ACTION_BLOCKED_HARD_CAP",
                    message=f"Live action blocked: {reason}",
                    context={
                        "action_type": action_type,
                        "reason": reason,
                        "user_id": user_id,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to emit hard cap event: {e}")


# ============ Log Sanitization ============

SENSITIVE_FIELDS = [
    "password", "hashed_password", "password_hash",
    "api_key", "api_secret", "passphrase",
    "secret", "token", "access_token", "refresh_token",
    "private_key", "encryption_key", "master_key",
    "bot_token", "telegram_bot_token",
    "authorization", "auth", "bearer",
    "cookie", "session",
]


def sanitize_dict(data: Dict[str, Any], mask: str = "[REDACTED]") -> Dict[str, Any]:
    """
    Recursively sanitize sensitive fields in a dictionary.
    
    Args:
        data: Dictionary to sanitize
        mask: Replacement string for sensitive values
    
    Returns:
        Sanitized copy of the dictionary
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            if isinstance(value, str) and len(value) > 4:
                sanitized[key] = f"****{value[-4:]}"
            else:
                sanitized[key] = mask
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, mask)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_dict(item, mask) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    
    return sanitized


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Sanitize HTTP headers for logging."""
    sensitive_headers = ["authorization", "cookie", "x-api-key", "x-auth-token"]
    
    sanitized = {}
    for key, value in headers.items():
        if key.lower() in sensitive_headers:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    
    return sanitized


# ============ Security Headers ============

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "1; mode=block",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def add_security_headers(response):
    """Add security headers to a response."""
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response
