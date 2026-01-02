"""Rate limiting middleware for API protection."""
import time
import hashlib
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
from collections import defaultdict
import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


# Rate limit configurations (requests per minute)
RATE_LIMITS = {
    # Auth endpoints - strict limits
    "/api/auth/login": {"requests": 5, "window": 60, "by": "ip"},
    "/api/auth/token": {"requests": 5, "window": 60, "by": "ip"},
    "/api/auth/register": {"requests": 3, "window": 60, "by": "ip"},

    # Trades monitor READ endpoints (more permissive to avoid UI 429s)
    "/api/trades": {"requests": 240, "window": 60, "by": "user"},
    "/api/trades/summary": {"requests": 240, "window": 60, "by": "user"},
    "/api/trades/report": {"requests": 120, "window": 60, "by": "user"},

    # Heavy/expensive endpoints
    "/api/validation/run": {"requests": 2, "window": 60, "by": "user"},
    "/api/events/export": {"requests": 2, "window": 60, "by": "user"},
    "/api/stress-lab/run": {"requests": 2, "window": 60, "by": "user"},
    "/api/stress-tests/run": {"requests": 2, "window": 60, "by": "user"},

    # DEX endpoints - moderate limits
    "/api/dex/pairs/scan": {"requests": 10, "window": 60, "by": "user"},
    "/api/dex/sniper/run-once": {"requests": 10, "window": 60, "by": "user"},

    # Default for all other endpoints
    "default": {"requests": 60, "window": 60, "by": "user_or_ip"},
}

# Health check endpoints - more permissive (exact match only)
HEALTH_ENDPOINTS = {"/api/health", "/api/heartbeat", "/api/"}
HEALTH_LIMIT = {"requests": 120, "window": 60, "by": "ip"}


class InMemoryRateLimiter:
    """In-memory rate limiter using sliding window."""
    
    def __init__(self):
        # Structure: {key: [(timestamp, count), ...]}
        self._windows: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Returns:
            (allowed, remaining, reset_at)
        """
        async with self._lock:
            now = time.time()
            window_start = now - window_seconds
            
            # Clean old entries
            self._windows[key] = [
                (ts, count) for ts, count in self._windows[key]
                if ts > window_start
            ]
            
            # Count requests in current window
            total_requests = sum(count for _, count in self._windows[key])
            
            if total_requests >= max_requests:
                # Rate limited
                reset_at = int(self._windows[key][0][0] + window_seconds) if self._windows[key] else int(now + window_seconds)
                return False, 0, reset_at
            
            # Add current request
            self._windows[key].append((now, 1))
            remaining = max_requests - total_requests - 1
            reset_at = int(now + window_seconds)
            
            return True, remaining, reset_at
    
    async def cleanup(self):
        """Remove expired entries."""
        async with self._lock:
            now = time.time()
            max_window = 3600  # Keep max 1 hour of data
            
            keys_to_delete = []
            for key, entries in self._windows.items():
                self._windows[key] = [
                    (ts, count) for ts, count in entries
                    if ts > now - max_window
                ]
                if not self._windows[key]:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._windows[key]


class MongoRateLimiter:
    """MongoDB-backed rate limiter for distributed systems."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.rate_limits
    
    async def initialize(self):
        """Create indexes for rate limiting."""
        await self.collection.create_index("expires_at", expireAfterSeconds=0)
        await self.collection.create_index([("key", 1), ("window_start", 1)])
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit using MongoDB.
        
        Returns:
            (allowed, remaining, reset_at)
        """
        now = datetime.now(timezone.utc)
        window_start = int(now.timestamp() / window_seconds) * window_seconds
        
        doc_key = f"{key}:{window_start}"
        
        # Atomic increment
        result = await self.collection.find_one_and_update(
            {"key": doc_key},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "window_start": window_start,
                    "expires_at": datetime.fromtimestamp(window_start + window_seconds * 2, tz=timezone.utc)
                }
            },
            upsert=True,
            return_document=True
        )
        
        count = result.get("count", 1)
        reset_at = window_start + window_seconds
        
        if count > max_requests:
            return False, 0, int(reset_at)
        
        remaining = max_requests - count
        return True, remaining, int(reset_at)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, app, db: AsyncIOMotorDatabase = None, event_logger = None):
        super().__init__(app)
        self.memory_limiter = InMemoryRateLimiter()
        self.mongo_limiter = MongoRateLimiter(db) if db else None
        self.event_logger = event_logger
        self._use_mongo = db is not None
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for proxy headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from Authorization header or request state."""
        # First check request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return user_id
        
        # Try to extract from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                import base64
                import json
                token = auth_header[7:]
                # Decode JWT payload (middle part)
                payload_b64 = token.split(".")[1]
                # Add padding if needed
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                return payload.get("sub")  # user_id is stored in 'sub' claim
            except Exception:
                pass
        
        return None
    
    def _get_rate_limit_config(self, path: str) -> dict:
        """Get rate limit config for path."""
        # Check exact match
        if path in RATE_LIMITS:
            return RATE_LIMITS[path]
        
        # Check prefix match
        for pattern, config in RATE_LIMITS.items():
            if pattern != "default" and path.startswith(pattern):
                return config
        
        return RATE_LIMITS["default"]
    
    def _get_rate_limit_key(self, request: Request, config: dict) -> str:
        """Generate rate limit key based on config."""
        by = config.get("by", "user_or_ip")
        path = request.url.path
        
        if by == "ip":
            identifier = self._get_client_ip(request)
        elif by == "user":
            identifier = self._get_user_id(request) or self._get_client_ip(request)
        else:  # user_or_ip
            identifier = self._get_user_id(request) or self._get_client_ip(request)
        
        # Hash the key for privacy
        key_raw = f"{path}:{identifier}"
        return hashlib.sha256(key_raw.encode()).hexdigest()[:16]
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        path = request.url.path
        method = request.method
        
        # Skip rate limiting for OPTIONS (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)
        
        config = self._get_rate_limit_config(path)
        key = self._get_rate_limit_key(request, config)
        
        # Check rate limit
        limiter = self.mongo_limiter if self._use_mongo and self.mongo_limiter else self.memory_limiter
        
        allowed, remaining, reset_at = await limiter.check_rate_limit(
            key,
            config["requests"],
            config["window"]
        )
        
        if not allowed:
            client_ip = self._get_client_ip(request)
            user_id = self._get_user_id(request)
            
            # Log rate limit hit
            logger.warning(f"Rate limit hit: {path} from {client_ip} (user: {user_id})")
            
            # Emit security event
            if self.event_logger:
                try:
                    from services.event_logger import EventSeverity, EventCategory
                    await self.event_logger.emit(
                        severity=EventSeverity.WARNING,
                        category=EventCategory.SECURITY,
                        type="SECURITY_RATE_LIMIT_HIT",
                        message=f"Rate limit exceeded for {path}",
                        context={
                            "path": path,
                            "ip": client_ip,
                            "user_id": user_id,
                            "limit": config["requests"],
                            "window_s": config["window"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to emit rate limit event: {e}")
            
            retry_after = max(1, reset_at - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={
                    "X-RateLimit-Limit": str(config["requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "Retry-After": str(retry_after),
                }
            )
        
        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(config["requests"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        
        return response
