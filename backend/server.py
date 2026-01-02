"""Main FastAPI server for Crypto Trading System with full features."""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks, Header, Security, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from contextlib import asynccontextmanager
import asyncio
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
import secrets
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from uuid import uuid4

# Load environment
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import services
from services.runtime import TradingRuntime, init_runtime, get_runtime
from services.data_feed import DataFeed, get_data_feed
from services.auth import AuthService, UserCreate, ExchangeCredentials, Token
from services.notifications import NotificationService, NotificationLevel
from services.stress_tests import StressTestEngine, STRESS_SCENARIOS
from services.stress_lab import StressLab, StressScenarioType, STRESS_SCENARIOS as LAB_SCENARIOS
from services.monitoring import MonitoringPanel
from services.event_logger import EventLogger, EventSeverity, EventCategory, EventType, get_event_logger
from services.validation import ProductionValidator, WatchMode, TestBaseline, get_validator, get_watch_mode, get_test_baseline
from services.scheduler import ValidationScheduler, get_validation_scheduler
from services.rbac import UserRole, Permission, RBACDependency, has_permission
from services.audit import AuditService, AuditAction, set_audit_service, get_audit_service
from services.security import get_secret_manager, LiveHardCaps, SECURITY_HEADERS, sanitize_headers
from services.rate_limit import RateLimitMiddleware, InMemoryRateLimiter
from services.presets import PresetService, get_preset_diff, INITIAL_PRESETS
from services.pair_advisor import PairAdvisorEngine, AgentStrategy
from services.backtest_engine import (
    BacktestEngine, get_backtest_engine, set_backtest_engine,
    STRATEGIES as BACKTEST_STRATEGIES, STRATEGY_DEFAULTS as BACKTEST_STRATEGY_DEFAULTS
)
from services.optimization_engine import (
    OptimizationEngine, get_optimization_engine, set_optimization_engine,
    STRATEGY_PARAM_RANGES
)
from services.strategy_agent_mapper import get_strategy_mapper

# Sandbox imports
from services.sandbox import SandboxRunner, SandboxConfig, Severity

# Growth Module imports
from services.system_config import SystemConfigService, set_system_config_service, get_system_config_service
from services.growth_presets import AgentPresetsV2Service, set_presets_v2_service, get_presets_v2_service, AgentTypeV2
from services.market_router import MarketRouter, MarketMetrics, calculate_metrics_from_ohlcv
from services.guardian import GuardianService, TradeRequest
from services.risk_budget import RiskBudgetService, AllocationRequest, BucketType
from services.viability import ViabilityService, ViabilityInput
from services.go_live_gate import GoLiveGateService, GateConfig

from models.trading import (
    AgentType, AgentStatus, RiskSettings, PortfolioSummary
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'crypto_trading')
client: AsyncIOMotorClient = None
db: AsyncIOMotorDatabase = None

# Global services
trading_runtime: TradingRuntime = None
auth_service: AuthService = None
notification_service: NotificationService = None
stress_lab: StressLab = None
monitoring_panel: MonitoringPanel = None
event_logger: EventLogger = None
production_validator: ProductionValidator = None
watch_mode: WatchMode = None
test_baseline_manager: TestBaseline = None
validation_scheduler: ValidationScheduler = None
audit_service: AuditService = None
live_hard_caps: LiveHardCaps = None
rbac: RBACDependency = None
rate_limiter: InMemoryRateLimiter = None
preset_service: PresetService = None
pair_advisor: PairAdvisorEngine = None

# Growth Module services
system_config_service: SystemConfigService = None
growth_presets_service: AgentPresetsV2Service = None
market_router: MarketRouter = None
guardian_service: GuardianService = None
risk_budget_service: RiskBudgetService = None
viability_service: ViabilityService = None
growth_orchestrator = None
go_live_gate: GoLiveGateService = None

# Execution Router (Paper Trading Mode)
execution_router = None

# Trades Service
trades_service = None

security = HTTPBearer(auto_error=False)


async def seed_owner_account(db, audit_service=None):
    """
    Idempotent owner account seeding using bcrypt directly.
    
    Ensures the platform always has an accessible OWNER account after redeploys.
    - Creates owner if not exists
    - Password from env OWNER_PASSWORD (default: Haven2025)
    - Uses bcrypt directly for compatibility with bcrypt 4.x
    """
    import bcrypt
    
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    owner_password = os.environ.get("OWNER_PASSWORD", "Haven2025")
    
    try:
        # Check if owner exists
        existing_owner = await db.users.find_one({"username": "owner"})
        
        if existing_owner:
            # Do NOT modify existing owner here (no password sync on boot).
            logger.info("=== Owner exists; seed_owner_account will not modify existing user ===")
            
            logger.info("=== Owner password synchronized on startup ===")
        else:
            # Create owner using bcrypt hash
            new_hash = hash_password(owner_password)
            
            owner_doc = {
                "id": str(uuid4()),
                "username": "owner",
                "email": os.environ.get("OWNER_EMAIL", "owner@haven.local"),
                "hashed_password": new_hash,
                "role": "owner",
                "status": "active",
                "is_active": True,
                "force_password_change": False,
                "is_default_credentials": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "system_seed",
            }
            
            await db.users.insert_one(owner_doc)
            
            logger.info("=== Owner account auto-created via startup seed ===")
            
            if audit_service:
                await audit_service.log(
                    user_id="system",
                    username="system",
                    role="system",
                    action="OWNER_CREATED",
                    resource_type="auth",
                    resource_id=owner_doc["id"],
                    metadata={"tag": "AUTH_SEED", "reason": "startup_seed"}
                )
    except Exception as e:
        logger.error(f"Failed to seed owner account: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global client, db, trading_runtime, auth_service, notification_service, stress_lab, monitoring_panel, event_logger, production_validator, watch_mode, test_baseline_manager, validation_scheduler, audit_service, live_hard_caps, rbac, rate_limiter, preset_service, pair_advisor
    global system_config_service, growth_presets_service, market_router, guardian_service, risk_budget_service, viability_service, growth_orchestrator
    
    logger.info("Starting Crypto Trading System...")
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    try:
        await db.command("ping")
        logger.info("MongoDB connected successfully")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise
    
    # Initialize Event Logger FIRST (so other services can use it)
    event_logger = EventLogger(db)
    await event_logger.initialize()
    
    # Initialize Rate Limiter (in-memory for now)
    rate_limiter = InMemoryRateLimiter()
    logger.info("Rate limiter initialized (in-memory mode)")
    
    # Initialize Audit Service
    audit_service = AuditService(db, event_logger)
    await audit_service.initialize()
    set_audit_service(audit_service)
    
    # Seed owner account FIRST (before ensure_admin_exists)
    # Requirement: seed only when users collection is empty
    logger.info("=== Starting owner account seed ===")
    if await db.users.count_documents({}) == 0:
        await seed_owner_account(db, audit_service)
        logger.info("=== Owner account seed complete (users was empty) ===")
    else:
        logger.info("=== Owner account seed skipped (users not empty) ===")
        # Backfill: ensure existing owner has an email for password recovery
        owner_email = os.environ.get("OWNER_EMAIL", "owner@haven.local")
        await db.users.update_one(
            {"username": "owner", "$or": [{"email": None}, {"email": ""}]},
            {"$set": {"email": owner_email, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    
    # Initialize services
    auth_service = AuthService(db)
    await auth_service.ensure_admin_exists()
    
    # SECURITY HARDENING DISABLED
    # Note: Login/auth is bypassed in this deployment, so default-credential enforcement
    # would only spam critical events without improving security.
    
    # Initialize RBAC
    rbac = RBACDependency(auth_service)
    
    # Initialize Preset Service
    preset_service = PresetService(db)
    await preset_service.initialize()
    logger.info("Preset service initialized")
    
    # Initialize Pair Advisor Engine
    pair_advisor = PairAdvisorEngine(db, event_logger=event_logger)
    await pair_advisor.initialize()
    logger.info("Pair Advisor Engine initialized")
    
    # ============ Growth Module Initialization ============
    # System Config Service
    system_config_service = SystemConfigService(db, audit_service=audit_service)
    await system_config_service.initialize()
    set_system_config_service(system_config_service)
    logger.info("Growth Module: SystemConfig initialized")
    
    # Growth Presets Service (MM + MOM presets)
    growth_presets_service = AgentPresetsV2Service(db, audit_service=audit_service)
    await growth_presets_service.initialize()
    set_presets_v2_service(growth_presets_service)
    logger.info("Growth Module: Presets V2 initialized (5 MM + 4 MOM presets)")
    
    # Market Router (regime detection)
    market_router = MarketRouter(db, system_config_service=system_config_service, event_logger=event_logger)
    logger.info("Growth Module: MarketRouter initialized")
    
    # Guardian Service (risk enforcement)
    guardian_service = GuardianService(db, system_config_service=system_config_service, event_logger=event_logger)
    logger.info("Growth Module: Guardian initialized")
    
    # Risk Budget Service (capital allocation)
    risk_budget_service = RiskBudgetService(db, system_config_service=system_config_service, event_logger=event_logger)
    logger.info("Growth Module: RiskBudget initialized")
    
    # Viability Service (pre-trade check)
    viability_service = ViabilityService(system_config_service=system_config_service, event_logger=event_logger)
    logger.info("Growth Module: Viability initialized")
    
    logger.info("=== Growth Module base services initialized ===")
    # ============ End Growth Module ============
    
    # Initialize Live Hard Caps
    live_hard_caps = LiveHardCaps(db, event_logger)
    
    notification_service = NotificationService(db)
    await notification_service.initialize()
    
    # Initialize trading runtime
    trading_runtime = await init_runtime(db)
    trading_runtime.notifications = notification_service
    trading_runtime.event_logger = event_logger  # Inject event logger
    
    # Inject event logger into data feed
    if trading_runtime.data_feed:
        trading_runtime.data_feed.event_logger = event_logger
    
    # Initialize executor with idempotency keys
    if trading_runtime.executor:
        await trading_runtime.executor.initialize()
        trading_runtime.executor.event_logger = event_logger
    
    # Initialize Stress Lab
    stress_lab = StressLab(db)
    stress_lab.set_runtime(trading_runtime)
    stress_lab.event_logger = event_logger
    
    # Initialize Monitoring Panel
    monitoring_panel = MonitoringPanel(db)
    monitoring_panel.set_runtime(trading_runtime)
    
    # Initialize Production Validator
    production_validator = get_validator(db)
    production_validator.set_runtime(trading_runtime)
    production_validator.set_event_logger(event_logger)
    
    # Initialize Watch Mode
    watch_mode = get_watch_mode(db)
    watch_mode.set_runtime(trading_runtime)
    watch_mode.set_event_logger(event_logger)
    
    # Initialize Test Baseline Manager
    test_baseline_manager = get_test_baseline(db)
    test_baseline_manager.set_runtime(trading_runtime)
    test_baseline_manager.set_event_logger(event_logger)
    
    # Set event logger on DataFeedHealth for anti-flapping events
    if trading_runtime and trading_runtime.data_feed:
        trading_runtime.data_feed.health.set_event_logger(event_logger)
    
    # Initialize Validation Scheduler
    validation_scheduler = get_validation_scheduler(db)
    validation_scheduler.set_validator(production_validator)
    validation_scheduler.set_event_logger(event_logger)
    await validation_scheduler.initialize()  # Load state and check catch-up
    
    # ============ Initialize Growth Orchestrator (needs trading_runtime) ============
    from services.growth_orchestrator import GrowthOrchestrator, set_growth_orchestrator
    from services.growth.paper_adapter import GrowthPaperAdapter
    
    # Use existing paper executor from trading_runtime
    paper_executor = trading_runtime.executor if trading_runtime else None
    
    paper_adapter = GrowthPaperAdapter(
        db=db, 
        paper_executor=paper_executor,
        event_logger=event_logger
    )
    await paper_adapter.initialize()
    
    # Use existing data_feed from trading_runtime
    data_feed = trading_runtime.data_feed if trading_runtime else None
    
    growth_orchestrator = GrowthOrchestrator(
        db=db,
        market_router=market_router,
        guardian_service=guardian_service,
        viability_service=viability_service,
        risk_budget_service=risk_budget_service,
        growth_presets_service=growth_presets_service,
        paper_adapter=paper_adapter,
        event_logger=event_logger,
        data_feed=data_feed,
    )
    await growth_orchestrator.initialize()
    set_growth_orchestrator(growth_orchestrator)
    logger.info("=== Growth Module Orchestrator initialized ===")
    
    # Initialize GO-LIVE Gate (must be after Growth Module)
    go_live_gate = GoLiveGateService(db=db, config=GateConfig())
    await go_live_gate.initialize()
    
    # Register GO-LIVE Gate routes
    from routes.go_live_gate import router as go_live_router, set_gate_service
    set_gate_service(go_live_gate)
    app.include_router(go_live_router)
    logger.info("=== GO-LIVE Gate initialized ===")
    
    # Register Config Editor routes (P1.1)
    from routes.config_editor import router as config_editor_router, set_services as set_config_editor_services
    from services.growth_presets import get_presets_wrapper
    set_config_editor_services(
        system_config=system_config_service,
        presets=get_presets_wrapper(),
        guardian=guardian_service,
        audit=audit_service,
    )
    app.include_router(config_editor_router)
    logger.info("=== Config Editor routes initialized ===")
    
    # Initialize Backtest Engine
    backtest_engine = BacktestEngine(db=db)
    set_backtest_engine(backtest_engine)
    logger.info("=== Backtest Engine initialized ===")
    
    # Initialize Optimization Engine
    optimization_engine = OptimizationEngine(db=db, backtest_engine=backtest_engine)
    set_optimization_engine(optimization_engine)
    logger.info("=== Optimization Engine initialized ===")
    
    # Initialize Sniper Hardening Service
    global sniper_hardening_service
    from services.sandbox.sniper_hardening import SniperHardeningService
    sniper_hardening_service = SniperHardeningService(db=db)
    logger.info("=== Sniper Hardening Service initialized ===")
    
    # Initialize Analytics Service
    global analytics_service
    from services.analytics import AnalyticsService
    analytics_service = AnalyticsService(db=db)
    logger.info("=== Analytics Service initialized ===")
    
    # Initialize DEX Trading Services
    from routes.dex_trading import router as dex_router, init_dex_services
    init_dex_services(db)
    app.include_router(dex_router)
    logger.info("=== DEX Trading Services initialized (TESTNET MODE) ===")
    
    # Initialize Execution Router (PAPER MODE by default)
    global execution_router
    from services.execution import ExecutionRouter, get_trading_config
    from services.execution.router import set_execution_router
    
    trading_config = get_trading_config()
    execution_router = ExecutionRouter(db=db, config=trading_config, go_live_gate=go_live_gate)
    await execution_router.initialize()
    set_execution_router(execution_router)
    logger.info(f"=== Execution Router initialized in {trading_config.trading_mode.value.upper()} mode ===")
    
    # Initialize Trades Service and WebSocket Manager
    from services.trades_service import TradesService, set_trades_service
    from services.ws_stream import get_ws_manager
    from routes.trades import router as trades_router
    
    global trades_service
    trades_service = TradesService(db=db)
    await trades_service.initialize()
    set_trades_service(trades_service)
    
    # Setup WebSocket manager
    ws_manager = get_ws_manager()
    ws_manager.set_trades_service(trades_service)
    await ws_manager.start()
    
    # Include trades router
    app.include_router(trades_router, prefix="/api")
    logger.info("=== Trades Service and WebSocket Manager initialized ===")
    
    # Initialize Agent Execution Bridge
    from services.execution.agent_bridge import init_agent_bridge
    agent_bridge = await init_agent_bridge()
    logger.info("=== Agent Execution Bridge initialized ===")
    

    # Initialize Agent Trade Client (guardrails + persistent trade_id state)
    from services.agent_trade_client import AgentTradeClient, set_agent_trade_client

    # Initialize Agent Execution Log Store (used by Trades Report)
    from services.agent_execution_log import AgentExecutionLogStore
    agent_exec_logs = AgentExecutionLogStore(db=db)
    await agent_exec_logs.initialize()

    agent_trade_client = AgentTradeClient(db=db)
    await agent_trade_client.initialize()
    set_agent_trade_client(agent_trade_client)
    logger.info("=== Agent Trade Client initialized ===")

    # Emit startup event
    await event_logger.emit(
        severity=EventSeverity.INFO,
        category=EventCategory.ENGINE,
        type=EventType.ENGINE_STARTED,
        message="Trading system started successfully",
        context={
            "agents_count": len(trading_runtime.orchestrator.agents) if trading_runtime.orchestrator else 0,
            "data_source": trading_runtime.data_feed.health.get_active_source() if trading_runtime.data_feed else "unknown",
            "scheduler_enabled": validation_scheduler._enabled if validation_scheduler else False,
        }
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Crypto Trading System...")
    
    # Emit shutdown event
    if event_logger:
        await event_logger.emit(
            severity=EventSeverity.INFO,
            category=EventCategory.ENGINE,
            type=EventType.ENGINE_STOPPED,
            message="Trading system shutting down",
        )
    
    if notification_service:
        await notification_service.cleanup()
    
    if trading_runtime:
        await trading_runtime.cleanup()
    
    if client:
        client.close()


app = FastAPI(
    title="Crypto Trading System",
    description="Multi-agent crypto trading platform with paper trading",
    version="2.0.0",
    lifespan=lifespan
)


# ============ Rate Limiting Middleware ============

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Global rate limiting middleware."""
    from services.rate_limit import RATE_LIMITS, HEALTH_ENDPOINTS, HEALTH_LIMIT
    import hashlib
    import time
    
    path = request.url.path
    method = request.method
    
    # Skip rate limiting for OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return await call_next(request)
    
    # Skip if rate limiter not initialized
    if rate_limiter is None:
        return await call_next(request)
    
    # Check if this is a health endpoint (exact match only)
    if path in HEALTH_ENDPOINTS:
        config = HEALTH_LIMIT
    else:
        # Get rate limit config for this path
        config = RATE_LIMITS.get(path)
        if not config:
            # Check prefix match (but not for health endpoints)
            for pattern, cfg in RATE_LIMITS.items():
                if pattern != "default" and path.startswith(pattern):
                    config = cfg
                    break
            if not config:
                config = RATE_LIMITS["default"]
    
    # Get client IP (with proxy support)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        real_ip = request.headers.get("X-Real-IP")
        client_ip = real_ip if real_ip else (request.client.host if request.client else "unknown")
    
    # Get user ID from JWT if present
    user_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import base64
            import json
            token = auth_header[7:]
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_id = payload.get("sub")
        except Exception:
            pass
    
    # Determine identifier based on config
    by = config.get("by", "user_or_ip")
    if by == "ip":
        identifier = client_ip
    elif by == "user":
        identifier = user_id or client_ip
    else:  # user_or_ip
        identifier = user_id or client_ip
    
    # Generate rate limit key
    key_raw = f"{path}:{identifier}"
    key = hashlib.sha256(key_raw.encode()).hexdigest()[:16]
    
    # Check rate limit
    allowed, remaining, reset_at = await rate_limiter.check_rate_limit(
        key,
        config["requests"],
        config["window"]
    )
    
    if not allowed:
        logger.warning(f"Rate limit hit: {path} from {client_ip} (user: {user_id})")
        
        # Emit security event
        if event_logger:
            try:
                await event_logger.emit(
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
    
    # Process request and add rate limit headers
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(config["requests"])
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_at)
    
    return response


# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Root-level health check for Kubernetes probes (without /api prefix)
@app.get("/health")
async def root_health():
    """Root health check for Kubernetes liveness/readiness probes."""
    return {"status": "healthy"}

# CORS - Restrict origins in production
cors_origins = os.environ.get('CORS_ORIGINS', '*')
if cors_origins == '*':
    logger.warning("CORS is set to allow all origins. Configure CORS_ORIGINS for production!")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins.split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


# ============ Auth Dependency ============

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Get current authenticated user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await auth_service.verify_token(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    if user.get("status") and user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is not active")

    return user


async def require_auth(user=Depends(get_current_user)):
    """Require authentication."""
    return user


async def require_admin(user = Depends(require_auth)):
    """Require admin or owner role."""
    role = user.get("role", "viewer")
    if role not in [UserRole.ADMIN.value, UserRole.OWNER.value]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_owner(user = Depends(require_auth)):
    """Require owner role."""
    if user.get("role") != UserRole.OWNER.value:
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


async def require_tester_or_higher(user = Depends(require_auth)):
    """Require tester, admin, or owner role."""
    role = user.get("role", "viewer")
    if role not in [UserRole.TESTER.value, UserRole.ADMIN.value, UserRole.OWNER.value]:
        raise HTTPException(status_code=403, detail="Tester access required")
    return user


async def require_viewer_or_higher(user = Depends(require_auth)):
    """Require any authenticated user (viewer or above)."""
    return user  # require_auth already validates authentication


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


# ============ Request/Response Models ============

class RuntimeControlRequest(BaseModel):
    action: str
    interval: Optional[int] = 60


class AgentControlRequest(BaseModel):
    action: str


class AgentConfigUpdate(BaseModel):
    updates: Dict[str, Any]


class RiskSettingsUpdate(BaseModel):
    max_daily_loss: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_position_size: Optional[float] = None
    max_total_exposure: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None


class CapitalAllocationRequest(BaseModel):
    allocations: Dict[str, float]


class KillSwitchRequest(BaseModel):
    activate: bool
    reason: Optional[str] = "Manual control"


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class NotificationConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notify_on_trade: Optional[bool] = None
    notify_on_stop_loss: Optional[bool] = None
    notify_on_take_profit: Optional[bool] = None
    notify_on_kill_switch: Optional[bool] = None
    notify_on_agent_error: Optional[bool] = None
    notify_on_risk_warning: Optional[bool] = None


class ExchangeCredentialsRequest(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None


# Admin User Management Models
class AdminUserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    role: str = UserRole.TESTER.value


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuditLogQuery(BaseModel):
    user_id: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    from_ts: Optional[str] = None
    to_ts: Optional[str] = None
    limit: int = 100
    skip: int = 0


# ============ Health & Heartbeat Endpoints ============

@api_router.get("/")
async def root():
    """API health check."""
    return {"message": "Crypto Trading System API", "status": "online", "version": "2.0.0"}


@api_router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mongodb": "connected" if db is not None else "disconnected",
        "runtime": "initialized" if trading_runtime is not None else "not initialized"
    }


@api_router.get("/heartbeat")
async def heartbeat():
    """Heartbeat endpoint for external monitoring."""
    if not trading_runtime:
        return {"status": "not_initialized", "timestamp": datetime.now(timezone.utc).isoformat()}
    return await trading_runtime.get_heartbeat()


@api_router.get("/engine/status")
async def engine_status():
    """Detailed engine status for monitoring."""
    if not trading_runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    
    status = trading_runtime.get_status()
    risk_status = await trading_runtime.risk_manager.get_status() if trading_runtime.risk_manager else {}
    
    return {
        "engine": status,
        "risk": risk_status,
        "data_feed": trading_runtime.data_feed.get_status() if trading_runtime.data_feed else None,
    }


# ============ Trading Mode Status ============

@api_router.get("/trading/status")
async def trading_status(user=Depends(require_auth)):
    """Get current trading mode status (PAPER/BINANCE_TESTNET/BINANCE_LIVE)."""
    from services.execution.config import get_trading_config

    config = get_trading_config()
    status = config.get_status()

    # Add execution router stats if available
    if execution_router:
        status["router"] = execution_router.get_status()

    # Add GO-LIVE gate status (only relevant for BINANCE_LIVE)
    if go_live_gate:
        try:
            status["go_live_gate"] = await go_live_gate.get_current_status()
        except Exception:
            status["go_live_gate"] = {"decision": "NO_GO", "reason": "Gate not evaluated"}

    return status


@api_router.get("/system/live_readiness")
async def system_live_readiness(user=Depends(require_auth)):
    """Return readiness checklist for enabling BINANCE_LIVE."""
    from services.live_readiness import LiveReadinessService

    svc = LiveReadinessService(db)
    return await svc.get_status()


@api_router.post("/trading/kill-switch")
async def trading_kill_switch(
    request: Request,
    user = Depends(require_owner)
):
    """Activate or deactivate the trading kill switch (OWNER only)."""
    from services.execution.config import get_trading_config
    
    body = await request.json()
    action = body.get("action", "activate")
    reason = body.get("reason", "Manual activation")
    
    config = get_trading_config()
    
    if action == "activate":
        config.activate_kill_switch(reason)
        
        # Log audit
        if audit_service:
            await audit_service.log(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                action="KILL_SWITCH_ACTIVATED",
                resource_type="trading",
                resource_id="kill_switch",
                metadata={"reason": reason}
            )
        
        return {"success": True, "message": "Kill switch activated", "reason": reason}
    
    elif action == "deactivate":
        config.deactivate_kill_switch()
        
        if audit_service:
            await audit_service.log(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                action="KILL_SWITCH_DEACTIVATED",
                resource_type="trading",
                resource_id="kill_switch",
                metadata={}
            )
        
        return {"success": True, "message": "Kill switch deactivated"}
    
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")


# ============ Auth Endpoints ============

# Rate limiting storage (in-memory, reset on restart)
_login_attempts = {}  # {ip: [(timestamp, success), ...]}
_reset_attempts = {}  # {ip: [timestamp, ...]}

def _check_rate_limit(ip: str, attempts_dict: dict, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    """Check if IP is rate limited. Returns True if allowed, False if blocked."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    
    if ip in attempts_dict:
        # Filter to only recent attempts
        attempts_dict[ip] = [t for t in attempts_dict[ip] if t > window_start]
        if len(attempts_dict[ip]) >= max_attempts:
            return False
    return True

def _record_attempt(ip: str, attempts_dict: dict):
    """Record an attempt for rate limiting."""
    now = datetime.now(timezone.utc)
    if ip not in attempts_dict:
        attempts_dict[ip] = []
    attempts_dict[ip].append(now)


class SignUpRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)
    confirm_password: str


class RecoverRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str


# Rate limiting for forgot password (per IP and per account)
_forgot_password_ip_attempts: Dict[str, list] = {}
_forgot_password_account_attempts: Dict[str, list] = {}


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str


@api_router.post("/auth/register")
async def register(request: RegisterRequest, req: Request):
    """Register a new user account."""
    ip = get_client_ip(req)

    # Rate limit check
    if not _check_rate_limit(ip, _reset_attempts, max_attempts=10, window_minutes=60):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")

    _record_attempt(ip, _reset_attempts)

    # Validate passwords match
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Check if username exists (case-sensitive)
    existing_username = await db.users.find_one({"username": request.username})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check if email exists
    existing_email = await db.users.find_one({"email": request.email.lower().strip()})
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user as USER role (not OWNER, not ADMIN)
    import bcrypt

    def hash_pw(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    user_id = secrets.token_hex(16)
    user_doc = {
        "id": user_id,
        "username": request.username,
        "email": request.email.lower().strip(),
        "hashed_password": hash_pw(request.password),
        "role": "user",
        "status": "active",
        "is_active": True,
        "force_password_change": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.users.insert_one(user_doc)
    logger.info(f"New user registered: {request.email}")

    return {"status": "success"}


@api_router.post("/auth/login")
async def login(request: LoginRequest, req: Request):
    """Login and get access token."""
    ip = get_client_ip(req)

    # Rate limit check (5 failed attempts per 15 minutes)
    if not _check_rate_limit(ip, _login_attempts, max_attempts=5, window_minutes=15):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 15 minutes.")

    identifier = request.username_or_email.strip()
    user = await db.users.find_one(
        {
            "$or": [
                {"username": identifier},
                {"email": {"$regex": f"^{identifier}$", "$options": "i"}},
            ]
        },
        {"_id": 0},
    )
    if not user:
        _record_attempt(ip, _login_attempts)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Status enforcement
    if user.get("status") and user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is not active")

    import bcrypt
    hashed = user.get("hashed_password", "")
    if not hashed or not bcrypt.checkpw(request.password.encode('utf-8'), hashed.encode('utf-8')):
        _record_attempt(ip, _login_attempts)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_service.create_access_token(
        data={
            "sub": user["id"],
            "username": user.get("username") or user.get("email"),
            "role": user.get("role", "user"),
        },
        expires_delta=timedelta(hours=12),
    )

    return {"access_token": token, "token_type": "bearer"}


@api_router.post("/auth/recover")
async def recover_password(request: RecoverRequest, req: Request):
    """
    Request a password reset link.
    
    Security features:
    - Always returns success (doesn't reveal if account exists)
    - Rate limited: 5 requests per hour per IP + per account key
    - Token is hashed before storage
    - Token expires in 15 minutes
    """
    # Generic success message (never reveal if account exists)
    success_message = "If an account exists with that email, you will receive a password reset link."
    
    try:
        from services.email import get_email_service, generate_reset_token, hash_token
    except ImportError as e:
        logger.error(f"Failed to import email service: {e}")
        return {"status": "sent"}
    
    try:
        ip = get_client_ip(req)
        user_agent = req.headers.get("user-agent", "")[:500]
    
        # Rate limit by IP (5 requests per hour)
        if not _check_rate_limit(ip, _forgot_password_ip_attempts, max_attempts=5, window_minutes=60):
            raise HTTPException(status_code=429, detail="Too many reset requests. Please try again later.")
    
        # Record IP attempt
        _record_attempt(ip, _forgot_password_ip_attempts)
    
        # Rate limit by account key (normalize email)
        account_key = request.email.lower().strip()
        if not _check_rate_limit(account_key, _forgot_password_account_attempts, max_attempts=5, window_minutes=60):
            # Still return success to not reveal account existence
            logger.warning(f"Rate limit hit for account key: {account_key[:3]}***")
            return {"status": "sent"}

        _record_attempt(account_key, _forgot_password_account_attempts)

        # Find user by email (case-insensitive)
        user = await db.users.find_one({
            "email": {"$regex": f"^{request.email}$", "$options": "i"}
        }, {"_id": 0})

        # Owner fallback: allow recovery by username 'owner' if owner email is missing
        if not user:
            owner_email = os.environ.get("OWNER_EMAIL", "owner@haven.local")
            if request.email.lower().strip() in ["owner", owner_email.lower()] :
                user = await db.users.find_one({"username": "owner"}, {"_id": 0})
                if user and not user.get("email"):
                    user["email"] = owner_email
    
        if user and user.get("email"):
            # Ensure user has an ID
            user_id = user.get("id")
            if not user_id:
                logger.warning(f"User found but has no ID: {user.get('username', 'unknown')}")
                return {"status": "sent"}
            
            # Generate secure reset token
            raw_token, token_hash = generate_reset_token()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
            # Store reset record with hashed token
            reset_doc = {
                "user_id": user_id,
                "token_hash": token_hash,  # Store ONLY the hash
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
                "used_at": None,
                "request_ip": ip,
                "user_agent": user_agent,
            }
        
            await db.password_resets.insert_one(reset_doc)
        
            # Send email with raw token
            email_service = get_email_service()
            email_result = await email_service.send_password_reset_email(
                to_email=user["email"],
                username=user.get("username", "User"),
                reset_token=raw_token,
            )
        
            # Audit log (DO NOT log raw token)
            if audit_service:
                await audit_service.log(
                    user_id=user_id,
                    username=user.get("username", "unknown"),
                    role=user.get("role", "unknown"),
                    action=AuditAction.PASSWORD_RESET_REQUEST,
                    resource_type="auth",
                    resource_id=user_id,
                    ip=ip,
                    metadata={
                        "email_provider": email_result.get("provider"),
                        "email_sent": email_result.get("success"),
                        "tag": "AUTH",
                    }
                )
        
            logger.info(f"Password reset requested for user: {user.get('username', 'unknown')[:3]}***")
        
            # In production, never return token
            # For development/demo, include if email not configured
            # Requirements:
            # - Always return 200
            # - If SMTP NOT configured AND user exists -> return demo token
            if email_result.get("provider") == "mock":
                return {"status": "demo", "token": raw_token}

            return {"status": "sent"}
    
        # User not found - still return success
        logger.info(f"Password reset requested for non-existent account: {account_key[:3]}***")
        return {"status": "sent"}
    
    except Exception as e:
        logger.error(f"Error in recover_password: {str(e)}")
        # Always return success to not reveal implementation details
        return {"status": "sent"}


@api_router.post("/auth/reset-password")
async def reset_password(request: ResetPasswordRequest, req: Request):
    """
    Reset password using token.
    
    Security features:
    - Token is one-time use
    - Token expires after 15 minutes
    - Password is hashed with bcrypt
    - Token hash is verified (not plain token)
    """
    try:
        from services.email import hash_token
    except ImportError as e:
        logger.error(f"Failed to import hash_token: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")
    
    ip = get_client_ip(req)
    
    # Validate passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    # Validate password strength
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if len(request.new_password) > 128:
        raise HTTPException(status_code=400, detail="Password too long")
    
    # Hash the provided token to compare with stored hash
    token_hash = hash_token(request.token)
    
    # Find valid reset token (not used, not expired)
    reset_doc = await db.password_resets.find_one({
        "token_hash": token_hash,
        "used_at": None
    }, {"_id": 0})
    
    if not reset_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    
    # Check expiration
    expires_at_str = reset_doc["expires_at"]
    if isinstance(expires_at_str, str):
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    else:
        expires_at = expires_at_str
    
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")
    
    # Get user
    user = await db.users.find_one({"id": reset_doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="User account not found")
    
    # Update password with strong hashing using bcrypt directly
    import bcrypt
    def hash_pw(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    await db.users.update_one(
        {"id": reset_doc["user_id"]},
        {
            "$set": {
                "hashed_password": hash_pw(request.new_password),
                "password_reset_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Mark token as used
    used_at = datetime.now(timezone.utc).isoformat()
    await db.password_resets.update_one(
        {"token_hash": token_hash},
        {"$set": {"used_at": used_at, "used_ip": ip}}
    )
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=reset_doc["user_id"],
            username=user.get("username", "unknown"),
            role=user.get("role", "unknown"),
            action=AuditAction.PASSWORD_RESET,
            resource_type="auth",
            resource_id=reset_doc["user_id"],
            ip=ip,
            metadata={
                "tag": "AUTH",
            }
        )
    
    logger.info(f"Password reset completed for user_id: {reset_doc['user_id'][:8]}***")
    
    return {"status": "success", "message": "Password has been reset successfully. You can now log in."}


@api_router.get("/auth/me")
async def get_me(user = Depends(require_auth)):
    """Get current user info."""
    return await auth_service.get_user(user["id"])


@api_router.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, user = Depends(require_auth)):
    """Change own password."""
    success, error = await auth_service.change_password(
        user["id"],
        request.current_password,
        request.new_password
    )
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    # Mark default credentials as changed (emits SECURITY_DEFAULT_CREDENTIALS_REVOKED)
    await auth_service.mark_credentials_as_changed(user["id"], event_logger)
    
    return {"status": "password_changed"}


# ============ Admin User Management Endpoints ============

@api_router.get("/admin/users")
async def admin_list_users(skip: int = 0, limit: int = 100, user = Depends(require_admin)):
    """List all users (admin only)."""
    return await auth_service.admin_list_users(skip, limit)


@api_router.post("/admin/users")
async def admin_create_user(request: AdminUserCreate, req: Request, user = Depends(require_admin)):
    """Create a new user with temporary password (admin only)."""
    ip = get_client_ip(req)
    
    new_user, temp_password = await auth_service.admin_create_user(
        username=request.username,
        email=request.email,
        role=request.role,
        created_by=user["id"],
    )
    
    if not new_user:
        raise HTTPException(status_code=400, detail=temp_password)  # temp_password contains error
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.USER_CREATE,
            resource_type="user",
            resource_id=new_user.id,
            after={"username": request.username, "role": request.role, "email": request.email},
            ip=ip,
        )
    
    return {
        "status": "created",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "role": new_user.role,
        },
        "temporary_password": temp_password,
        "message": "User must change password on first login"
    }


@api_router.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, request: AdminUserUpdate, req: Request, user = Depends(require_admin)):
    """Update user (admin only)."""
    ip = get_client_ip(req)
    
    # Get current state for audit
    current_user = await auth_service.get_user(user_id)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    success, error = await auth_service.admin_update_user(user_id, updates, user["user_id"])
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.USER_UPDATE if "role" not in updates else AuditAction.USER_ROLE_CHANGE,
            resource_type="user",
            resource_id=user_id,
            before={k: current_user.get(k) for k in updates.keys()},
            after=updates,
            ip=ip,
        )
    
    return {"status": "updated", "updates": list(updates.keys())}


@api_router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, req: Request, user = Depends(require_admin)):
    """Reset user password (admin only)."""
    ip = get_client_ip(req)
    
    temp_password, error = await auth_service.admin_reset_password(user_id, user["user_id"])
    
    if not temp_password:
        raise HTTPException(status_code=400, detail=error)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.USER_PASSWORD_RESET,
            resource_type="user",
            resource_id=user_id,
            ip=ip,
        )
    
    return {
        "status": "password_reset",
        "temporary_password": temp_password,
        "message": "User must change password on next login"
    }


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, req: Request, user = Depends(require_admin)):
    """Delete/deactivate user (admin only)."""
    ip = get_client_ip(req)
    
    success, error = await auth_service.admin_delete_user(user_id, user["user_id"])
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.USER_DEACTIVATE,
            resource_type="user",
            resource_id=user_id,
            ip=ip,
        )
    
    return {"status": "deleted"}


# ============ Audit Log Endpoints ============

@api_router.get("/admin/audit")
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    user = Depends(require_admin)
):
    """Get audit logs (admin only)."""
    if not audit_service:
        return []
    
    from_dt = datetime.fromisoformat(from_ts) if from_ts else None
    to_dt = datetime.fromisoformat(to_ts) if to_ts else None
    
    return await audit_service.get_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        from_ts=from_dt,
        to_ts=to_dt,
        limit=limit,
        skip=skip,
    )


@api_router.get("/admin/audit/security")
async def get_security_audit_logs(limit: int = 100, user = Depends(require_admin)):
    """Get security-related audit events (admin only)."""
    if not audit_service:
        return []
    return await audit_service.get_security_events(limit)


# ============ Security Hardening Endpoints ============

@api_router.get("/admin/security/check")
async def check_security(user = Depends(require_admin)):
    """Check for security issues (admin only)."""
    result = await auth_service.check_default_credentials(event_logger)
    return result


@api_router.post("/admin/security/hardening")
async def run_security_hardening(req: Request, user = Depends(require_owner)):
    """
    Run full security hardening (owner only).
    - Checks for default credentials
    - Forces password change for users with defaults
    - Ensures at least one active OWNER
    """
    ip = get_client_ip(req)
    
    result = await auth_service.security_hardening(event_logger)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.SETTINGS_UPDATE,
            resource_type="security_hardening",
            after=result,
            ip=ip,
        )
    
    return result


# ============ Exchange Credentials Endpoints ============

@api_router.post("/credentials/exchange")
async def store_credentials(request: ExchangeCredentialsRequest, req: Request, user = Depends(require_auth)):
    """Store exchange API credentials (encrypted)."""
    ip = get_client_ip(req)
    creds = ExchangeCredentials(**request.model_dump())
    await auth_service.store_exchange_credentials(user["user_id"], creds)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.CREDENTIAL_STORE,
            resource_type="exchange_credential",
            resource_id=request.exchange,
            after={"exchange": request.exchange},
            ip=ip,
        )
    
    return {"status": "stored", "exchange": request.exchange}


@api_router.get("/credentials/exchange")
async def list_credentials(user = Depends(require_auth)):
    """List stored exchange credentials (without secrets)."""
    return await auth_service.list_exchange_credentials(user["user_id"])


@api_router.delete("/credentials/exchange/{exchange}")
async def delete_credentials(exchange: str, req: Request, user = Depends(require_auth)):
    """Delete exchange credentials."""
    success = await auth_service.delete_exchange_credentials(user["user_id"], exchange)
    if not success:
        raise HTTPException(status_code=404, detail="Credentials not found")
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action=AuditAction.CREDENTIAL_DELETE,
            resource_type="exchange_credential",
            resource_id=exchange,
            ip=get_client_ip(req),
        )
    
    return {"status": "deleted"}


# ============ Dashboard Endpoints ============

@api_router.get("/dashboard")
async def get_dashboard():
    """Get all dashboard data."""
    if not trading_runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return await trading_runtime.get_dashboard_data()


@api_router.get("/portfolio")
async def get_portfolio():
    """Get portfolio summary."""
    doc = await db.portfolio_summary.find_one({}, {"_id": 0})
    if doc:
        return doc
    return PortfolioSummary().model_dump()


# ============ Runtime Control Endpoints ============

@api_router.get("/runtime/status")
async def get_runtime_status():
    """Get runtime status."""
    if not trading_runtime:
        return {"running": False, "message": "Runtime not initialized"}
    return trading_runtime.get_status()


@api_router.post("/runtime/control")
async def control_runtime(request: RuntimeControlRequest):
    """Start or stop the trading runtime."""
    if not trading_runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    
    if request.action == "start":
        await trading_runtime.start(request.interval)
        return {"status": "started", "interval": request.interval}
    elif request.action == "stop":
        await trading_runtime.stop()
        return {"status": "stopped"}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")


@api_router.post("/runtime/cycle")
async def run_single_cycle():
    """Run a single trading cycle manually."""
    if not trading_runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    await trading_runtime.run_single_cycle()
    return {"status": "cycle completed"}


# ============ Agent Endpoints ============

@api_router.get("/agents")
async def get_agents():
    """Get all agent statuses."""
    if not trading_runtime or not trading_runtime.orchestrator:
        return []
    return trading_runtime.orchestrator.get_all_agent_statuses()


@api_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get specific agent status."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    status = trading_runtime.orchestrator.get_agent_status(agent_id)
    if not status:
        raise HTTPException(status_code=404, detail="Agent not found")
    return status


@api_router.post("/agents/{agent_id}/control")
async def control_agent(agent_id: str, request: AgentControlRequest):
    """Start or stop an agent."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    if request.action == "start":
        success = await trading_runtime.orchestrator.start_agent(agent_id)
    elif request.action == "stop":
        success = await trading_runtime.orchestrator.stop_agent(agent_id)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": request.action, "agent_id": agent_id}


@api_router.put("/agents/{agent_id}/config")
async def update_agent_config(agent_id: str, request: AgentConfigUpdate):
    """Update agent configuration."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    success = await trading_runtime.orchestrator.update_agent_config(agent_id, request.updates)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "updated", "agent_id": agent_id}


@api_router.post("/agents/start-all")
async def start_all_agents():
    """Start all agents."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    await trading_runtime.orchestrator.start_all_agents()
    return {"status": "all agents started"}


@api_router.post("/agents/stop-all")
async def stop_all_agents():
    """Stop all agents."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    await trading_runtime.orchestrator.stop_all_agents()
    return {"status": "all agents stopped"}


# ============ Agent Presets Endpoints ============

class PresetSaveRequest(BaseModel):
    name: str
    agent_type: str
    params: Dict[str, Any]
    description: str = ""
    is_global: bool = False


class ApplyPresetRequest(BaseModel):
    preset_id: Optional[str] = None
    preset_key: Optional[str] = None  # conservative/moderate/aggressive


@api_router.get("/presets")
async def get_presets(agent_type: Optional[str] = None, user = Depends(require_auth)):
    """Get all presets, optionally filtered by agent type."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    
    presets = await preset_service.get_presets(
        agent_type=agent_type,
        include_custom=True,
        user_id=user["user_id"]
    )
    return presets


@api_router.get("/presets/defaults")
async def get_default_presets():
    """Get all built-in presets without auth (for frontend reference)."""
    return INITIAL_PRESETS


@api_router.get("/presets/{preset_id}")
async def get_preset(preset_id: str, user = Depends(require_auth)):
    """Get a specific preset by ID."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    
    preset = await preset_service.get_preset_by_id(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@api_router.post("/presets/save")
async def save_preset(request: PresetSaveRequest, user = Depends(require_auth)):
    """Save a new custom preset. Only OWNER/ADMIN can create global presets."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    
    # Validate agent type
    valid_types = ["dca", "grid", "trend", "mean_reversion", "breakout"]
    if request.agent_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid agent type. Must be one of: {valid_types}")
    
    # TESTER cannot save global presets
    if request.is_global and user["role"] not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only OWNER/ADMIN can create global presets")
    
    try:
        preset = await preset_service.save_preset(
            name=request.name,
            agent_type=request.agent_type,
            params=request.params,
            user_id=user["id"],
            user_role=user["role"],
            description=request.description,
            is_global=request.is_global
        )
        
        # Log audit event
        if audit_service:
            await audit_service.log(
                user_id=user["id"],
                username=user.get("username", "unknown"),
                role=user["role"],
                action=AuditAction.PRESET_SAVE,
                resource_type="preset",
                resource_id=preset["id"],
                metadata={"name": request.name, "agent_type": request.agent_type, "is_global": request.is_global}
            )
        
        # Emit event
        if event_logger:
            await event_logger.emit(
                type="AGENT_PRESET_SAVED",
                category=EventCategory.AGENT,
                severity=EventSeverity.INFO,
                message=f"Preset '{request.name}' saved for {request.agent_type}",
                context={
                    "preset_id": preset["id"],
                    "name": request.name,
                    "agent_type": request.agent_type,
                    "is_global": request.is_global,
                    "user_id": user["user_id"]
                }
            )
        
        return preset
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str, user = Depends(require_auth)):
    """Delete a preset. Cannot delete system presets."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    
    try:
        success = await preset_service.delete_preset(
            preset_id=preset_id,
            user_id=user["id"],
            user_role=user["role"]
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Preset not found")
        
        # Log audit event
        if audit_service:
            await audit_service.log(
                user_id=user["id"],
                username=user.get("username", "unknown"),
                role=user["role"],
                action=AuditAction.PRESET_DELETE,
                resource_type="preset",
                resource_id=preset_id
            )
        
        return {"status": "deleted", "preset_id": preset_id}
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.post("/agents/{agent_id}/apply-preset")
async def apply_preset_to_agent(agent_id: str, request: ApplyPresetRequest, user = Depends(require_auth)):
    """Apply a preset to an agent."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Get agent
    agent_status = trading_runtime.orchestrator.get_agent_status(agent_id)
    if not agent_status:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_type = agent_status.get("type")
    
    # Get preset
    preset = None
    if request.preset_id:
        preset = await preset_service.get_preset_by_id(request.preset_id)
    elif request.preset_key:
        preset = await preset_service.get_preset_by_key(agent_type, request.preset_key)
    
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    # Verify preset matches agent type
    if preset["agent_type"] != agent_type:
        raise HTTPException(status_code=400, detail=f"Preset is for {preset['agent_type']}, not {agent_type}")
    
    # Apply preset parameters
    success = await trading_runtime.orchestrator.update_agent_config(agent_id, preset["params"])
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to apply preset")
    
    # Log audit event
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user.get("username", "unknown"),
            role=user["role"],
            action=AuditAction.PRESET_APPLY,
            resource_type="agent",
            resource_id=agent_id,
            metadata={
                "preset_id": preset["id"],
                "preset_name": preset["name"],
                "agent_type": agent_type,
                "params": preset["params"]
            }
        )
    
    # Emit event
    if event_logger:
        await event_logger.emit(
            type="AGENT_PRESET_APPLIED",
            category=EventCategory.AGENT,
            severity=EventSeverity.INFO,
            message=f"Preset '{preset['name']}' applied to {agent_type} agent",
            context={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "preset_id": preset["id"],
                "preset_name": preset["name"],
                "preset_key": preset.get("preset_key"),
                "params": preset["params"],
                "user_id": user["user_id"]
            }
        )
    
    return {
        "status": "applied",
        "agent_id": agent_id,
        "preset": {
            "id": preset["id"],
            "name": preset["name"],
            "params": preset["params"]
        }
    }


@api_router.post("/agents/{agent_id}/preview-preset")
async def preview_preset_diff(agent_id: str, request: ApplyPresetRequest, user = Depends(require_auth)):
    """Preview what changes a preset would make to an agent."""
    if not preset_service:
        raise HTTPException(status_code=503, detail="Preset service not initialized")
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Get agent
    agent_status = trading_runtime.orchestrator.get_agent_status(agent_id)
    if not agent_status:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_type = agent_status.get("type")
    
    # Get preset
    preset = None
    if request.preset_id:
        preset = await preset_service.get_preset_by_id(request.preset_id)
    elif request.preset_key:
        preset = await preset_service.get_preset_by_key(agent_type, request.preset_key)
    
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    # Get current agent config - extract relevant params based on agent type
    current_params = {}
    for key in preset["params"].keys():
        if key in agent_status:
            current_params[key] = agent_status[key]
    
    # Calculate diff
    diff = get_preset_diff(current_params, preset["params"])
    
    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "preset": {
            "id": preset["id"],
            "name": preset["name"],
            "emoji": preset.get("emoji", ""),
            "description": preset.get("description", "")
        },
        "diff": diff,
        "current_params": current_params,
        "preset_params": preset["params"]
    }


# ============ Pair Advisor Endpoints ============

@api_router.get("/pair-advisor/recommendations")
async def get_pair_recommendations(
    agent_type: Optional[str] = None,
    top_n: int = 5,
    force_refresh: bool = False,
    user = Depends(require_auth)
):
    """Get pair recommendations for trading agents.
    
    - agent_type: dca, grid, trend (optional, returns all if not specified)
    - top_n: Number of recommendations per agent (default 5)
    - force_refresh: Bypass cache and regenerate recommendations
    """
    if not pair_advisor:
        raise HTTPException(status_code=503, detail="Pair Advisor not initialized")
    
    if agent_type:
        # Validate agent type
        try:
            strategy = AgentStrategy(agent_type.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}. Must be one of: dca, grid, trend")
        
        recommendations = await pair_advisor.get_recommendations(strategy, top_n, force_refresh)
        return {
            "agent": agent_type.upper(),
            "recommendations": [r.to_dict() for r in recommendations],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cache_ttl_seconds": pair_advisor.CACHE_TTL_SECONDS,
        }
    else:
        # Get all recommendations
        results = await pair_advisor.get_all_recommendations(top_n)
        return {
            "recommendations": results,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cache_ttl_seconds": pair_advisor.CACHE_TTL_SECONDS,
        }


@api_router.get("/pair-advisor/pair/{pair:path}")
async def get_pair_analysis(
    pair: str,
    agent_type: Optional[str] = None,
    user = Depends(require_auth)
):
    """Get detailed analysis for a specific pair.
    
    - pair: Trading pair (e.g., BTC/USDT, ETH-USDT, BTCUSDT)
    - agent_type: Filter by specific agent type (optional)
    """
    if not pair_advisor:
        raise HTTPException(status_code=503, detail="Pair Advisor not initialized")
    
    # Normalize pair format - support multiple formats
    pair = pair.upper().replace("-", "/").replace("_", "/")
    if "/" not in pair and len(pair) >= 6:
        # Try to split BTCUSDT -> BTC/USDT
        for quote in ["USDT", "EUR", "USD", "BTC", "ETH"]:
            if pair.endswith(quote):
                pair = pair[:-len(quote)] + "/" + quote
                break
    
    strategy = None
    if agent_type:
        try:
            strategy = AgentStrategy(agent_type.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")
    
    analysis = await pair_advisor.get_recommendation_for_pair(pair, strategy)
    
    return {
        "pair": pair,
        "analysis": analysis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/pair-advisor/supported-pairs")
async def get_supported_pairs(user = Depends(require_auth)):
    """Get list of supported pairs per venue."""
    from services.pair_advisor import SUPPORTED_PAIRS, VENUE_FEES
    
    return {
        "pairs_by_venue": {
            venue.value: pairs 
            for venue, pairs in SUPPORTED_PAIRS.items()
        },
        "fees_by_venue": {
            venue.value: {
                "maker": f"{fees['maker']*100:.2f}%",
                "taker": f"{fees['taker']*100:.2f}%",
            }
            for venue, fees in VENUE_FEES.items()
        },
        "micro_capital_gates": {
            "max_spread_pct": 0.10,
            "max_slippage_pct": 0.05,
            "order_sizes_eur": [5, 10],
        }
    }


class ApplyRecommendationRequest(BaseModel):
    pair: str
    venue: str
    preset_level: str = "moderate"  # conservative, moderate, aggressive
    save_custom_preset: bool = False
    custom_preset_name: Optional[str] = None


@api_router.post("/pair-advisor/apply")
async def apply_recommendation(
    request: ApplyRecommendationRequest,
    agent_type: str,
    user = Depends(require_auth)
):
    """Apply a pair recommendation to an agent.
    
    - Updates the agent's symbol to the recommended pair
    - Optionally applies a preset (conservative/moderate/aggressive)
    - Optionally saves a custom preset for this pair
    """
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    
    # Validate agent type
    valid_types = ["dca", "grid", "trend", "mean_reversion", "breakout"]
    if agent_type.lower() not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")
    
    # Find the agent of this type
    agent_id = None
    for aid, agent in trading_runtime.orchestrator.agents.items():
        if agent.config.agent_type.value == agent_type.lower():
            agent_id = aid
            break
    
    if not agent_id:
        raise HTTPException(status_code=404, detail=f"No {agent_type} agent found")
    
    # Normalize pair
    pair = request.pair.upper().replace("-", "/")
    venue = request.venue.upper()
    
    # Build config updates
    config_updates = {
        "symbol": pair,
    }
    
    # Get preset values if requested
    preset_applied = None
    if request.preset_level and preset_service:
        preset = await preset_service.get_preset_by_key(agent_type.lower(), request.preset_level)
        if preset:
            config_updates.update(preset["params"])
            preset_applied = preset["name"]
    
    # Apply configuration
    success = await trading_runtime.orchestrator.update_agent_config(agent_id, config_updates)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to apply recommendation")
    
    # Optionally save custom preset for this pair
    custom_preset_id = None
    if request.save_custom_preset and request.custom_preset_name and preset_service:
        try:
            custom_preset = await preset_service.save_preset(
                name=request.custom_preset_name or f"{agent_type.upper()}-{pair}",
                agent_type=agent_type.lower(),
                params=config_updates,
                user_id=user["id"],
                user_role=user["role"],
                description=f"Preset gerado pelo Pair Advisor para {pair} @ {venue}",
                is_global=False
            )
            custom_preset_id = custom_preset["id"]
        except Exception as e:
            logger.warning(f"Failed to save custom preset: {e}")
    
    # Log audit
    if audit_service:
        await audit_service.log(
            user_id=user["id"],
            username=user.get("username", "unknown"),
            role=user["role"],
            action=AuditAction.AGENT_UPDATE,
            resource_type="agent",
            resource_id=agent_id,
            metadata={
                "action": "apply_recommendation",
                "pair": pair,
                "venue": venue,
                "preset_level": request.preset_level,
                "preset_applied": preset_applied,
            }
        )
    
    # Emit event
    if event_logger:
        await event_logger.emit(
            type="PAIR_ADVISOR_APPLIED",
            category=EventCategory.AGENT,
            severity=EventSeverity.INFO,
            message=f"Recommendation applied: {pair} @ {venue} to {agent_type.upper()} agent",
            context={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "pair": pair,
                "venue": venue,
                "preset_level": request.preset_level,
                "preset_applied": preset_applied,
                "user_id": user["user_id"],
            }
        )
    
    return {
        "status": "applied",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "pair": pair,
        "venue": venue,
        "preset_applied": preset_applied,
        "custom_preset_id": custom_preset_id,
        "message": f"Agente {agent_type.upper()} configurado para {pair} @ {venue}"
    }


@api_router.get("/pair-advisor/audit")
async def get_pair_advisor_audit(
    limit: int = 20,
    agent_type: Optional[str] = None,
    user = Depends(require_admin)
):
    """Get audit log of pair advisor recommendations (admin only)."""
    query = {}
    if agent_type:
        query["strategy"] = agent_type.lower()
    
    cursor = db.pair_advisor_audit.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    audits = await cursor.to_list(limit)
    
    return {
        "audits": audits,
        "total": len(audits),
    }


# ============ Risk Management Endpoints ============

@api_router.get("/risk")
async def get_risk_status():
    """Get risk management status."""
    if not trading_runtime or not trading_runtime.risk_manager:
        raise HTTPException(status_code=503, detail="Risk manager not initialized")
    return await trading_runtime.risk_manager.get_status()


@api_router.put("/risk/settings")
async def update_risk_settings(request: RiskSettingsUpdate):
    """Update risk settings."""
    if not trading_runtime or not trading_runtime.risk_manager:
        raise HTTPException(status_code=503, detail="Risk manager not initialized")
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    await trading_runtime.risk_manager.update_settings(updates)
    return {"status": "updated", "settings": updates}


@api_router.post("/risk/kill-switch")
async def toggle_kill_switch(request: KillSwitchRequest):
    """Activate or deactivate kill switch."""
    if not trading_runtime or not trading_runtime.risk_manager:
        raise HTTPException(status_code=503, detail="Risk manager not initialized")
    
    if request.activate:
        await trading_runtime.risk_manager.activate_kill_switch(request.reason)
        if trading_runtime.orchestrator:
            await trading_runtime.orchestrator.stop_all_agents()
        if notification_service and notification_service.config.enabled:
            await notification_service.notify_kill_switch_activated(request.reason)
        return {"status": "kill switch activated", "reason": request.reason}
    else:
        await trading_runtime.risk_manager.deactivate_kill_switch()
        return {"status": "kill switch deactivated"}


# ============ Notification Endpoints ============

@api_router.get("/notifications/config")
async def get_notification_config():
    """Get notification configuration."""
    if not notification_service:
        raise HTTPException(status_code=503, detail="Notification service not initialized")
    return notification_service.get_config()


@api_router.put("/notifications/config")
async def update_notification_config(request: NotificationConfigUpdate):
    """Update notification configuration."""
    if not notification_service:
        raise HTTPException(status_code=503, detail="Notification service not initialized")
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    config = await notification_service.update_config(updates)
    return config.model_dump()


@api_router.post("/notifications/test")
async def test_notification():
    """Send test notification."""
    if not notification_service:
        raise HTTPException(status_code=503, detail="Notification service not initialized")
    success, message = await notification_service.test_connection()
    return {"success": success, "message": message}


@api_router.get("/notifications/history")
async def get_notification_history(limit: int = 50):
    """Get notification history."""
    if not notification_service:
        raise HTTPException(status_code=503, detail="Notification service not initialized")
    return await notification_service.get_recent_notifications(limit)


# ============ Capital Allocation Endpoints ============

@api_router.post("/capital/allocate")
async def allocate_capital(request: CapitalAllocationRequest):
    """Reallocate capital between agents."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    await trading_runtime.orchestrator.reallocate_capital(request.allocations)
    return {"status": "reallocated", "allocations": request.allocations}


@api_router.put("/capital/total")
async def update_total_capital(total: float):
    """Update total trading capital."""
    if not trading_runtime or not trading_runtime.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    await trading_runtime.orchestrator.update_total_capital(total)
    return {"status": "updated", "total_capital": total}


# ============ Market Data Endpoints ============

@api_router.get("/market/ticker/{symbol}")
async def get_ticker(symbol: str):
    """Get ticker for a symbol."""
    if not trading_runtime or not trading_runtime.data_feed:
        raise HTTPException(status_code=503, detail="Data feed not initialized")
    symbol = symbol.replace("-", "/")
    ticker = await trading_runtime.data_feed.fetch_ticker(symbol)
    return ticker


@api_router.get("/market/features/{symbol}")
async def get_market_features(symbol: str):
    """Get calculated features for a symbol."""
    if not trading_runtime or not trading_runtime.data_feed:
        raise HTTPException(status_code=503, detail="Data feed not initialized")
    symbol = symbol.replace("-", "/")
    features = await trading_runtime.data_feed.calculate_features(symbol)
    return features.model_dump()


@api_router.get("/market/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "1h", limit: int = 100):
    """Get candle data for a symbol."""
    if not trading_runtime or not trading_runtime.data_feed:
        raise HTTPException(status_code=503, detail="Data feed not initialized")
    symbol = symbol.replace("-", "/")
    candles = await trading_runtime.data_feed.fetch_candles(symbol, timeframe, limit)
    # Convert Candle objects to dictionaries manually
    return [{
        "timestamp": c.timestamp,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume
    } for c in candles]


@api_router.get("/market/orderbook/{symbol}")
async def get_orderbook(symbol: str, limit: int = 20):
    """Get order book for a symbol."""
    if not trading_runtime or not trading_runtime.data_feed:
        raise HTTPException(status_code=503, detail="Data feed not initialized")
    symbol = symbol.replace("-", "/")
    orderbook = await trading_runtime.data_feed.get_orderbook(symbol, limit)
    return orderbook


@api_router.get("/market/health")
async def get_data_feed_health():
    """Get data feed health status."""
    if not trading_runtime or not trading_runtime.data_feed:
        raise HTTPException(status_code=503, detail="Data feed not initialized")
    return trading_runtime.data_feed.get_status()


# ============ Position & Trade Endpoints ============

@api_router.get("/positions")
async def get_positions(open_only: bool = True):
    """Get all positions."""
    if not trading_runtime or not trading_runtime.executor:
        raise HTTPException(status_code=503, detail="Executor not initialized")
    positions = await trading_runtime.executor.get_positions(open_only=open_only)
    return [p.model_dump() for p in positions]


@api_router.get("/orders")
async def get_orders(agent_id: Optional[str] = None):
    """Get open orders."""
    if not trading_runtime or not trading_runtime.executor:
        raise HTTPException(status_code=503, detail="Executor not initialized")
    orders = await trading_runtime.executor.get_open_orders(agent_id)
    return [o.model_dump() for o in orders]


@api_router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order."""
    if not trading_runtime or not trading_runtime.executor:
        raise HTTPException(status_code=503, detail="Executor not initialized")
    order = await trading_runtime.executor.cancel_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.model_dump()


# Legacy trades endpoint moved to routes/trades.py
# GET /api/trades now handled by trades_router


# ============ Logs Endpoints ============

@api_router.get("/logs/trades")
async def get_trade_logs(limit: int = 100, agent_type: Optional[str] = None):
    """Get trade decision logs."""
    query = {}
    if agent_type:
        query["agent_type"] = agent_type
    logs = await db.trade_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


@api_router.get("/logs/system")
async def get_system_logs(limit: int = 100, level: Optional[str] = None):
    """Get system logs."""
    query = {}
    if level:
        query["level"] = level
    logs = await db.system_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


# ============ Stress Test Endpoints ============

@api_router.get("/stress-tests/scenarios")
async def get_stress_scenarios():
    """Get available stress test scenarios."""
    return [s.model_dump() for s in STRESS_SCENARIOS]


@api_router.post("/stress-tests/run")
async def run_stress_tests(background_tasks: BackgroundTasks):
    """Run all stress tests."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    engine = StressTestEngine(db, trading_runtime)
    await engine.run_all_tests()
    return engine.get_summary()


@api_router.get("/stress-tests/results")
async def get_stress_test_results():
    """Get latest stress test results."""
    results = await db.stress_test_results.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(10).to_list(10)
    return results


# ============ Stress Lab Endpoints (Interactive) ============

class StressLabRunRequest(BaseModel):
    scenario_type: str
    confirmation_code: str


@api_router.get("/stress-lab/scenarios")
async def get_stress_lab_scenarios():
    """Get available interactive stress test scenarios."""
    return stress_lab.get_scenarios() if stress_lab else []


@api_router.get("/stress-lab/status")
async def get_stress_lab_status():
    """Get current stress lab status."""
    if not stress_lab:
        return {"running": False, "active_test": None}
    
    return {
        "running": stress_lab.is_test_running(),
        "active_test": await stress_lab.get_active_test()
    }


@api_router.post("/stress-lab/run")
async def run_stress_lab_scenario(request: StressLabRunRequest):
    """Run an interactive stress test scenario. Requires confirmation code 'STRESS'."""
    if not stress_lab:
        raise HTTPException(status_code=503, detail="Stress Lab not initialized")
    
    try:
        scenario_type = StressScenarioType(request.scenario_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scenario type: {request.scenario_type}")
    
    try:
        result = await stress_lab.run_scenario(scenario_type, request.confirmation_code)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.get("/stress-lab/history")
async def get_stress_lab_history(limit: int = 20):
    """Get stress test run history."""
    if not stress_lab:
        return []
    return await stress_lab.get_test_history(limit)


# ============ Monitoring Panel Endpoints ============

@api_router.get("/monitoring/status")
async def get_monitoring_status():
    """Get complete monitoring status for 24/7 operation - CANONICAL ENDPOINT.
    
    This is the single source of truth for monitoring data.
    Never returns 'UNKNOWN' - uses 'OFFLINE' as fallback.
    """
    import os
    
    # Build stable response even if services are down
    now = datetime.now(timezone.utc)
    sandbox_enabled = os.environ.get("SANDBOX_ENABLED", "true").lower() == "true"
    db_connected = db is not None
    runtime_ready = trading_runtime is not None
    
    # Default safe response
    response = {
        "build_id": os.environ.get("BUILD_ID", "dev"),
        "mongodb": "connected" if db_connected else "disconnected",
        "runtime": "initialized" if runtime_ready else "starting",
        "safety": {
            "trading_mode": "paper",
            "live_cex_enabled": False
        },
        "feed": {
            "mode": "SYNTHETIC_SANDBOX" if sandbox_enabled else "OFFLINE",
            "source": "sandbox" if sandbox_enabled else "offline",
            "last_tick_at": None,
            "ws": {
                "enabled": True,
                "path": "/api/ws/growth",
                "connected": False
            },
            "note": "Sandbox mode - synthetic data" if sandbox_enabled else "Feed offline"
        },
        "scheduler": {
            "scheduled_jobs": 0,
            "last_run_at": None,
            "note": None
        },
        "risk": {
            "guardian_status": "SAFE",
            "weekly_drawdown_pct": 0.0,
            "daily_pnl_pct": 0.0,
            "note": None
        },
        # Legacy fields for backwards compatibility
        "timestamp": now.isoformat(),
        "engine_running": False,
        "engine_healthy": True,
        "engine_last_tick_at": None,
        "engine_tick_age_seconds": 0,
        "data_source": "sandbox" if sandbox_enabled else "offline",
        "data_freshness_seconds": 0,
        "data_stale": False,
        "open_positions_count": 0,
        "total_exposure": 0,
        "daily_pnl": 0,
        "daily_pnl_pct": 0,
        "daily_drawdown": 0,
        "daily_drawdown_pct": 0,
        "risk_state": "OK",
        "kill_switch_active": False,
        "safe_mode": False,
        "safe_mode_reason": "",
        "consecutive_losses": 0,
        "agents_total": 0,
        "agents_running": 0,
        "agents_in_error": 0,
        "alerts_last_sent_at": None,
        "alerts_sent_today": 0,
        "cycle_count": 0,
        "error_count": 0,
        "recovery_attempts": 0,
        "watchdog_status": "healthy",
        "watchdog_warnings": [],
        "data_feed_health": {}
    }
    
    # Enrich with real data if monitoring panel is available
    if monitoring_panel is not None:
        try:
            status = await monitoring_panel.get_status()
            status_dict = status.model_dump()
            
            # Update feed info
            if runtime_ready and trading_runtime.data_feed is not None:
                try:
                    df_status = trading_runtime.data_feed.get_status()
                    health = df_status.get("health", {})
                    
                    response["feed"]["source"] = df_status.get("active_source", response["feed"]["source"])
                    
                    # Check if data is stale
                    if df_status.get("safe_mode"):
                        response["feed"]["mode"] = "OFFLINE"
                        response["feed"]["note"] = df_status.get("safe_mode_reason", "Safe mode active")
                    elif df_status.get("active_source") == "binance":
                        response["feed"]["mode"] = "CEX_PAPER"
                        response["feed"]["note"] = "CEX paper trading mode"
                except Exception as feed_err:
                    logger.debug(f"Feed status unavailable: {feed_err}")
            
            # Update scheduler info
            if db_connected:
                try:
                    jobs = await db.scheduled_runs.count_documents({"status": "scheduled"})
                    last_run = await db.scheduled_runs.find_one(
                        {"status": "completed"}, 
                        {"_id": 0, "completed_at": 1},
                        sort=[("completed_at", -1)]
                    )
                    response["scheduler"]["scheduled_jobs"] = jobs
                    if last_run and last_run.get("completed_at"):
                        response["scheduler"]["last_run_at"] = last_run["completed_at"]
                except Exception:
                    response["scheduler"]["note"] = "Scheduler data unavailable"
            
            # Update risk info
            response["risk"]["guardian_status"] = "HALT" if status.kill_switch_active else ("WARN" if status.safe_mode else "SAFE")
            response["risk"]["weekly_drawdown_pct"] = status.daily_drawdown_pct
            response["risk"]["daily_pnl_pct"] = status.daily_pnl_pct
            
            # Merge all legacy fields
            for key in ["engine_running", "engine_healthy", "engine_tick_age_seconds",
                       "data_source", "data_freshness_seconds", "data_stale",
                       "open_positions_count", "total_exposure", "daily_pnl",
                       "daily_pnl_pct", "daily_drawdown", "daily_drawdown_pct",
                       "kill_switch_active", "safe_mode", "safe_mode_reason",
                       "consecutive_losses", "agents_total", "agents_running",
                       "agents_in_error", "alerts_sent_today", "cycle_count",
                       "error_count", "recovery_attempts", "watchdog_status",
                       "watchdog_warnings", "data_feed_health"]:
                if key in status_dict:
                    response[key] = status_dict[key]
            
            # Convert risk_state enum to string
            response["risk_state"] = status.risk_state.value if hasattr(status.risk_state, 'value') else str(status.risk_state)
            
            # Handle datetime fields
            if status.engine_last_tick_at:
                response["engine_last_tick_at"] = status.engine_last_tick_at.isoformat()
            if status.alerts_last_sent_at:
                response["alerts_last_sent_at"] = status.alerts_last_sent_at.isoformat()
                
        except Exception as e:
            logger.warning(f"Error enriching monitoring status: {e}")
            response["watchdog_warnings"].append(f"Partial data: {str(e)}")
    
    return response


# ============ Legacy Endpoint Aliases (prevent 404 spam) ============

@api_router.get("/growth/schedule/stats")
async def get_schedule_stats_alias():
    """Alias for scheduler stats - prevents 404 errors."""
    try:
        jobs = 0
        last_run = None
        if db is not None:
            jobs = await db.scheduled_runs.count_documents({"status": "scheduled"})
            doc = await db.scheduled_runs.find_one(
                {"status": "completed"}, 
                {"_id": 0, "completed_at": 1},
                sort=[("completed_at", -1)]
            )
            last_run = doc.get("completed_at") if doc else None
        
        return {
            "scheduled_jobs": jobs,
            "last_run_at": last_run,
            "note": None
        }
    except Exception:
        return {
            "scheduled_jobs": 0,
            "last_run_at": None,
            "note": "Scheduler not configured"
        }


@api_router.get("/status")
async def get_status_alias():
    """Alias for basic status - prevents 404 errors."""
    import os
    sandbox_enabled = os.environ.get("SANDBOX_ENABLED", "true").lower() == "true"
    
    return {
        "feed": {
            "mode": "SYNTHETIC_SANDBOX" if sandbox_enabled else "OFFLINE",
            "source": "sandbox" if sandbox_enabled else "offline"
        },
        "runtime": "initialized" if trading_runtime is not None else "starting",
        "mongodb": "connected" if db is not None else "disconnected"
    }


@api_router.get("/monitoring/health")
async def get_monitoring_health():
    """Simple health check for external monitoring tools."""
    if not monitoring_panel:
        return {"status": "unknown", "timestamp": datetime.now(timezone.utc).isoformat()}
    
    status = await monitoring_panel.get_status()
    return {
        "status": status.watchdog_status,
        "risk_state": status.risk_state.value,
        "engine_healthy": status.engine_healthy,
        "data_stale": status.data_stale,
        "safe_mode": status.safe_mode,
        "kill_switch": status.kill_switch_active,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.post("/monitoring/safe-mode/enter")
async def enter_safe_mode(reason: str = "Manual trigger"):
    """Manually enter safe mode."""
    if not monitoring_panel:
        raise HTTPException(status_code=503, detail="Monitoring panel not initialized")
    
    await monitoring_panel.trigger_safe_mode(reason)
    return {"success": True, "message": f"Safe mode entered: {reason}"}


@api_router.post("/monitoring/safe-mode/exit")
async def exit_safe_mode():
    """Exit safe mode."""
    if not monitoring_panel:
        raise HTTPException(status_code=503, detail="Monitoring panel not initialized")
    
    await monitoring_panel.exit_safe_mode()
    return {"success": True, "message": "Safe mode exited"}


@api_router.get("/monitoring/history")
async def get_monitoring_history(limit: int = 100):
    """Get historical monitoring data."""
    if not monitoring_panel:
        return []
    return await monitoring_panel.get_status_history(limit)


# ============ Reconciliation Endpoint ============

@api_router.post("/runtime/reconcile")
async def reconcile_state():
    """Force state reconciliation (idempotency check)."""
    if not trading_runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    
    # Count orders before
    orders_before = await db.orders.count_documents({})
    positions_before = await db.positions.count_documents({"is_open": True})
    
    # Run reconciliation
    await trading_runtime._recover_state()
    
    # Count after
    orders_after = await db.orders.count_documents({})
    positions_after = await db.positions.count_documents({"is_open": True})
    
    return {
        "success": True,
        "orders": {"before": orders_before, "after": orders_after, "diff": orders_after - orders_before},
        "positions": {"before": positions_before, "after": positions_after, "diff": positions_after - positions_before},
        "idempotency_keys_loaded": len(trading_runtime._processed_order_ids),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============ Event Timeline Endpoints ============

@api_router.get("/events")
async def get_events(
    limit: int = 50,
    severity: str = None,
    category: str = None,
    type: str = None,
    from_ts: str = None,
    to_ts: str = None,
    agent_id: str = None,
    symbol: str = None,
    run_id: str = None,
):
    """Query events with filters."""
    if not event_logger:
        return []
    
    from_dt = datetime.fromisoformat(from_ts) if from_ts else None
    to_dt = datetime.fromisoformat(to_ts) if to_ts else None
    
    return await event_logger.get_events(
        limit=limit,
        severity=severity,
        category=category,
        type=type,
        from_ts=from_dt,
        to_ts=to_dt,
        agent_id=agent_id,
        symbol=symbol,
        run_id=run_id,
    )


@api_router.get("/events/summary")
async def get_events_summary():
    """Get event summary with counts by severity and recent critical events."""
    if not event_logger:
        return {
            "total_24h": 0,
            "warnings_1h": 0,
            "by_severity": {},
            "by_category": {},
            "recent_critical": [],
        }
    
    return await event_logger.get_summary()


@api_router.get("/events/types")
async def get_event_types():
    """Get all unique event types."""
    if not event_logger:
        return []
    
    return await event_logger.get_event_types()


@api_router.get("/events/correlation/{correlation_id}")
async def get_correlation_chain(correlation_id: str):
    """Get all events in a correlation chain."""
    if not event_logger:
        return []
    
    return await event_logger.get_correlation_chain(correlation_id)


@api_router.get("/events/test-scope")
async def get_test_scope_status():
    """Get current test scope status."""
    if not event_logger:
        return {"active": False, "scope": None}
    
    scope = event_logger.get_active_test_scope()
    return {
        "active": event_logger.is_test_scope_active(),
        "scope": scope
    }


@api_router.get("/events/snapshots")
async def get_daily_snapshots(limit: int = 30):
    """Get daily snapshot events."""
    if not event_logger:
        return []
    
    return await event_logger.get_daily_snapshots(limit)


@api_router.post("/events/snapshot")
async def create_daily_snapshot():
    """Manually create a daily snapshot event."""
    if not event_logger:
        raise HTTPException(status_code=503, detail="Event logger not initialized")
    
    # Gather data from various sources
    portfolio = {"total_equity": 10000}
    risk = {"current_daily_pnl": 0, "current_drawdown_pct": 0}
    
    try:
        portfolio_doc = await db.portfolio.find_one({}, {"_id": 0})
        if portfolio_doc:
            portfolio = portfolio_doc
        
        risk_doc = await db.risk_settings.find_one({}, {"_id": 0})
        if risk_doc:
            risk = risk_doc
        
        trades_count = await db.trades.count_documents({
            "executed_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}
        })
        positions_count = await db.positions.count_documents({"is_open": True})
        
    except Exception as e:
        logger.warning(f"Failed to gather snapshot data: {e}")
        trades_count = 0
        positions_count = 0
    
    equity = portfolio.get("total_equity", 10000)
    daily_pnl = risk.get("current_daily_pnl", 0)
    daily_dd_pct = risk.get("current_drawdown_pct", 0)
    
    event = await event_logger.create_daily_snapshot(
        equity=equity,
        daily_pnl=daily_pnl,
        daily_pnl_pct=(daily_pnl / equity * 100) if equity > 0 else 0,
        daily_drawdown=daily_dd_pct * equity / 100,
        daily_drawdown_pct=daily_dd_pct,
        trades_count=trades_count,
        positions_count=positions_count,
        safe_mode_count=trading_runtime.data_feed._safe_mode_count if trading_runtime and trading_runtime.data_feed else 0,
    )
    
    return {"success": True, "event_id": event.id}


class TestEventRequest(BaseModel):
    severity: str = "INFO"
    category: str = "SYSTEM"
    type: str = "TEST_EVENT"
    message: str = "Test event from API"


@api_router.post("/events/test")
async def create_test_event(request: TestEventRequest):
    """Create a test event (for testing UI). Only in PAPER mode."""
    if not event_logger:
        raise HTTPException(status_code=503, detail="Event logger not initialized")
    
    try:
        severity = EventSeverity(request.severity)
        category = EventCategory(request.category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    event = await event_logger.emit(
        severity=severity,
        category=category,
        type=request.type,
        message=request.message,
        context={"test": True, "created_via": "api"},
        tags=["test"]
    )
    
    return {"success": True, "event_id": event.id}


@api_router.get("/events/export")
async def export_events(limit: int = 1000):
    """Export events as JSON."""
    if not event_logger:
        return []
    
    events = await event_logger.get_events(limit=limit)
    return events


# ============ Production Validation Pack Endpoints ============
# SECURITY: These endpoints are PAPER MODE ONLY

class ValidationRunRequest(BaseModel):
    """Request to start a validation run."""
    pass  # No parameters needed, just start


def check_paper_mode():
    """Check if system is in paper mode. Raise 403 if not."""
    from services.validation import is_paper_mode, get_trading_mode
    if not is_paper_mode():
        raise HTTPException(
            status_code=403, 
            detail=f"Validation endpoints are BLOCKED in {get_trading_mode().value.upper()} mode. Only available in PAPER mode."
        )


@api_router.post("/validation/run")
async def start_validation_run(user = Depends(get_current_user)):
    """
    Start a new Production Validation Pack run.
    
    SECURITY:
    - PAPER MODE ONLY
    - Authentication recommended (optional for dev)
    - Cannot trigger real orders
    """
    check_paper_mode()
    
    if not production_validator:
        raise HTTPException(status_code=503, detail="Production validator not initialized")
    
    try:
        run_id = await production_validator.start_validation()
    except Exception as e:
        if "BLOCKED" in str(e):
            raise HTTPException(status_code=403, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    
    return {
        "success": True,
        "run_id": run_id,
        "trading_mode": "paper",
        "message": "Validation started. Use /api/validation/status/{run_id} to check progress."
    }


@api_router.get("/validation/status/{run_id}")
async def get_validation_status(run_id: str):
    """Get status of a validation run."""
    if not production_validator:
        raise HTTPException(status_code=503, detail="Production validator not initialized")
    
    status = await production_validator.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Validation run {run_id} not found")
    
    return status


@api_router.get("/validation/result/{run_id}")
async def get_validation_result(run_id: str):
    """Get complete result of a validation run."""
    if not production_validator:
        raise HTTPException(status_code=503, detail="Production validator not initialized")
    
    result = await production_validator.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Validation run {run_id} not found")
    
    return result


@api_router.get("/validation/history")
async def get_validation_history(limit: int = 10):
    """Get history of validation runs from MongoDB."""
    if not production_validator:
        raise HTTPException(status_code=503, detail="Production validator not initialized")
    
    return await production_validator.get_history(limit)


# ============ Watch Mode Endpoints ============

@api_router.post("/validation/watch/start")
async def start_watch_mode_endpoint(user = Depends(get_current_user)):
    """
    Start the Watch Mode (15-minute periodic checks).
    
    SECURITY:
    - PAPER MODE ONLY
    - Singleton - only 1 watcher active
    """
    check_paper_mode()
    
    if not watch_mode:
        raise HTTPException(status_code=503, detail="Watch mode not initialized")
    
    try:
        result = await watch_mode.start()
        response = {"success": True, "message": "Watch Mode started (15 min interval)"}
        if result:
            response.update(result)
        return response
    except Exception as e:
        if "BLOCKED" in str(e):
            raise HTTPException(status_code=403, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/validation/watch/stop")
async def stop_watch_mode_endpoint(user = Depends(get_current_user)):
    """Stop the Watch Mode."""
    if not watch_mode:
        raise HTTPException(status_code=503, detail="Watch mode not initialized")
    
    await watch_mode.stop()
    return {"success": True, "message": "Watch Mode stopped"}


@api_router.get("/validation/watch/status")
async def get_watch_mode_status():
    """Get Watch Mode status."""
    if not watch_mode:
        return {"running": False, "message": "Watch mode not initialized"}
    
    from services.validation import get_trading_mode, WatchMode
    
    return {
        "running": watch_mode._running,
        "instance_id": watch_mode._instance_id,
        "active_instance": WatchMode._active_instance_id,
        "last_snapshot_date": watch_mode._last_snapshot_date,
        "check_count": watch_mode._check_count,
        "trading_mode": get_trading_mode().value,
        "interval_seconds": watch_mode.WATCH_INTERVAL,
    }


@api_router.get("/validation/watch/results")
async def get_watch_results(limit: int = 100):
    """Get Watch Mode check results history."""
    if not watch_mode:
        return []
    
    return await watch_mode.get_watch_results(limit)


# ============ Test Baseline Endpoints ============

@api_router.post("/baseline/create")
async def create_baseline(user = Depends(get_current_user)):
    """
    Create a frozen baseline snapshot of all system parameters.
    
    Use this before starting a 7-day paper trading test to:
    - Capture agent configs, risk thresholds, runtime settings
    - Emit TEST_BASELINE_CREATED event
    - Enable drift detection later
    """
    check_paper_mode()
    
    if not test_baseline_manager:
        raise HTTPException(status_code=503, detail="Test baseline manager not initialized")
    
    baseline = await test_baseline_manager.create_baseline()
    return {
        "success": True,
        "baseline": baseline,
        "message": f"Baseline {baseline['id']} created. Ready for 7-day paper trading."
    }


@api_router.get("/baseline/latest")
async def get_latest_baseline():
    """Get the latest test baseline."""
    if not test_baseline_manager:
        raise HTTPException(status_code=503, detail="Test baseline manager not initialized")
    
    baseline = await test_baseline_manager.get_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline found. Create one with POST /api/baseline/create")
    
    return baseline


@api_router.get("/baseline/{baseline_id}")
async def get_baseline_by_id(baseline_id: str):
    """Get a specific test baseline by ID."""
    if not test_baseline_manager:
        raise HTTPException(status_code=503, detail="Test baseline manager not initialized")
    
    baseline = await test_baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline {baseline_id} not found")
    
    return baseline


@api_router.get("/baseline/history")
async def get_baseline_history(limit: int = 10):
    """Get baseline history."""
    if not test_baseline_manager:
        return []
    
    return await test_baseline_manager.get_baseline_history(limit)


@api_router.get("/baseline/drift")
async def check_baseline_drift(baseline_id: str = None):
    """
    Compare current system state with a baseline to detect config drift.
    
    Returns:
    - has_drift: true if any parameters changed
    - changes: list of changed fields with old/new values
    """
    if not test_baseline_manager:
        raise HTTPException(status_code=503, detail="Test baseline manager not initialized")
    
    result = await test_baseline_manager.compare_with_current(baseline_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


# ============ Validation Scheduler Endpoints ============

@api_router.post("/validation/schedule/start")
async def start_validation_scheduler(user = Depends(get_current_user)):
    """
    Enable daily automatic validation at 09:00 Europe/Lisbon.
    
    SECURITY:
    - PAPER MODE ONLY
    - Authentication required
    """
    check_paper_mode()
    
    if not validation_scheduler:
        raise HTTPException(status_code=503, detail="Validation scheduler not initialized")
    
    try:
        result = await validation_scheduler.start()
        return {
            "success": True,
            "message": "Daily validation scheduler started",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/validation/schedule/stop")
async def stop_validation_scheduler(user = Depends(get_current_user)):
    """Stop the daily automatic validation scheduler."""
    if not validation_scheduler:
        raise HTTPException(status_code=503, detail="Validation scheduler not initialized")
    
    result = await validation_scheduler.stop()
    return {
        "success": True,
        "message": "Daily validation scheduler stopped",
        **result
    }


@api_router.get("/validation/schedule/status")
async def get_validation_scheduler_status():
    """
    Get scheduler status.
    
    Returns:
    - enabled: whether scheduler is active
    - timezone: schedule timezone (Europe/Lisbon)
    - schedule_time: daily run time (09:00)
    - next_run_at: ISO timestamp of next scheduled run
    - last_run_at: ISO timestamp of last scheduled run
    - last_run_id: ID of last scheduled validation run
    """
    if not validation_scheduler:
        return {
            "enabled": False,
            "message": "Scheduler not initialized"
        }
    
    return validation_scheduler.get_status()


@api_router.post("/validation/schedule/trigger")
async def trigger_validation_manually(user = Depends(get_current_user)):
    """
    Manually trigger a scheduled validation (for testing).
    
    SECURITY:
    - PAPER MODE ONLY
    - Same logic as automatic trigger
    """
    check_paper_mode()
    
    if not validation_scheduler:
        raise HTTPException(status_code=503, detail="Validation scheduler not initialized")
    
    result = await validation_scheduler.trigger_now()
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


# ============ Live Trading Toggle Endpoints ============

@api_router.get("/settings/trading-mode")
async def get_trading_mode_settings():
    """Get current trading mode settings."""
    import os
    return {
        "trading_mode": os.environ.get("TRADING_MODE", "paper"),
        "live_cex_enabled": os.environ.get("LIVE_CEX_ENABLED", "false").lower() == "true",
        "approval_mode": os.environ.get("APPROVAL_MODE", "true").lower() == "true",
    }


@api_router.post("/settings/trading-mode")
async def update_trading_mode_settings(
    request: dict,
    user = Depends(get_current_user)
):
    """
    Update trading mode settings.
    
    Body:
        trading_mode: "paper" or "live"
        live_cex_enabled: boolean
        approval_mode: boolean
    
    SECURITY:
    - Authentication required
    - Changes are runtime-only (not persisted to .env)
    - Enable live requires explicit confirmation
    """
    import os
    
    confirmation = request.get("confirmation_code")
    
    # If enabling live mode, require confirmation
    if request.get("trading_mode") == "live" or request.get("live_cex_enabled"):
        if confirmation != "ENABLE_LIVE":
            return {
                "error": "Live mode requires confirmation code 'ENABLE_LIVE'",
                "current_settings": await get_trading_mode_settings()
            }
    
    # Update environment variables (runtime only)
    if "trading_mode" in request:
        os.environ["TRADING_MODE"] = request["trading_mode"]
    if "live_cex_enabled" in request:
        os.environ["LIVE_CEX_ENABLED"] = str(request["live_cex_enabled"]).lower()
    if "approval_mode" in request:
        os.environ["APPROVAL_MODE"] = str(request["approval_mode"]).lower()
    
    # Emit event
    if event_logger:
        from services.event_logger import EventSeverity, EventCategory
        await event_logger.emit(
            severity=EventSeverity.WARNING,
            category=EventCategory.SYSTEM,
            type="TRADING_MODE_CHANGED",
            message="Trading mode settings updated",
            context={
                "trading_mode": os.environ.get("TRADING_MODE"),
                "live_cex_enabled": os.environ.get("LIVE_CEX_ENABLED"),
                "approval_mode": os.environ.get("APPROVAL_MODE"),
                "changed_by": user.get("id", "unknown"),
            },
            tags=["settings", "trading_mode", "security"]
        )
    
    return {
        "success": True,
        "settings": await get_trading_mode_settings()
    }


# ============================================================
# GROWTH MODULE ENDPOINTS
# ============================================================

# ---------- System Config ----------

@api_router.get("/growth/config")
async def get_system_config(user = Depends(get_current_user)):
    """Get current system configuration for Growth Module."""
    if not system_config_service:
        raise HTTPException(status_code=503, detail="System config service not initialized")
    
    config = await system_config_service.get_config()
    return {
        "config": system_config_service.to_dict(config),
    }


@api_router.put("/growth/config")
async def update_system_config(
    updates: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Update system configuration.
    OWNER/ADMIN only. All changes are audited.
    
    Updates format: {"path.to.field": new_value}
    Example: {"guardian.daily_loss_limit_pct": -3.0}
    """
    if not system_config_service:
        raise HTTPException(status_code=503, detail="System config service not initialized")
    
    # Check permission
    user_role = (user.get("role") or "").upper()
    if user_role not in ["OWNER", "ADMIN"]:
        raise HTTPException(status_code=403, detail="OWNER or ADMIN role required")
    
    try:
        config = await system_config_service.update_config(
            updates=updates,
            user_id=user.get("user_id"),
            username=user.get("username"),
            role=user_role,
        )
        
        return {
            "success": True,
            "config": system_config_service.to_dict(config),
            "updated_fields": list(updates.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/growth/config/reset")
async def reset_system_config(user = Depends(get_current_user)):
    """Reset system configuration to defaults. OWNER only."""
    if not system_config_service:
        raise HTTPException(status_code=503, detail="System config service not initialized")
    
    user_role = (user.get("role") or "").upper()
    if user_role != "OWNER":
        raise HTTPException(status_code=403, detail="OWNER role required")
    
    config = await system_config_service.reset_to_defaults(
        user_id=user.get("user_id"),
        username=user.get("username"),
        role=user_role,
    )
    
    return {
        "success": True,
        "message": "Configuration reset to defaults",
        "config": system_config_service.to_dict(config),
    }


# ---------- Growth Presets (MM + MOM) ----------

@api_router.get("/growth/presets")
async def get_all_growth_presets(
    agent_type: Optional[str] = None,
    include_disabled: bool = False,
    user = Depends(get_current_user)
):
    """
    Get all Growth Module presets (MM and MOM).
    
    Query params:
        agent_type: Filter by "MM" or "MOM" (optional)
        include_disabled: Include disabled presets (default: false)
    """
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    filter_type = None
    if agent_type:
        try:
            filter_type = AgentTypeV2(agent_type.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail="agent_type must be 'MM' or 'MOM'")
    
    presets = await growth_presets_service.get_all_presets(
        agent_type=filter_type,
        include_disabled=include_disabled,
    )
    
    return {
        "count": len(presets),
        "presets": presets,
    }


@api_router.get("/growth/presets/mm")
async def get_mm_presets(
    include_disabled: bool = False,
    user = Depends(get_current_user)
):
    """Get all Market Maker presets."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    presets = await growth_presets_service.get_mm_presets(include_disabled)
    return {"count": len(presets), "presets": presets}


@api_router.get("/growth/presets/mom")
async def get_mom_presets(
    include_disabled: bool = False,
    user = Depends(get_current_user)
):
    """Get all Momentum presets."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    presets = await growth_presets_service.get_mom_presets(include_disabled)
    return {"count": len(presets), "presets": presets}


@api_router.get("/growth/presets/{preset_id}")
async def get_growth_preset(preset_id: str, user = Depends(get_current_user)):
    """Get a specific preset by ID."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    preset = await growth_presets_service.get_preset_by_id(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
    
    return {"preset": preset}


@api_router.post("/growth/presets")
async def create_custom_preset(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Create a custom preset.
    
    Body:
        agent_type: "MM" or "MOM"
        name: Preset name
        ... (other config fields)
    """
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    agent_type_str = data.pop("agent_type", None)
    if not agent_type_str:
        raise HTTPException(status_code=400, detail="agent_type is required")
    
    try:
        agent_type = AgentTypeV2(agent_type_str.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="agent_type must be 'MM' or 'MOM'")
    
    preset = await growth_presets_service.create_custom_preset(
        agent_type=agent_type,
        config=data,
        user_id=user.get("user_id"),
        username=user.get("username"),
    )
    
    return {"success": True, "preset": preset}


@api_router.put("/growth/presets/{preset_id}")
async def update_custom_preset(
    preset_id: str,
    updates: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Update a custom preset (cannot modify system presets)."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    try:
        preset = await growth_presets_service.update_preset(
            preset_id=preset_id,
            updates=updates,
            user_id=user.get("user_id"),
            username=user.get("username"),
        )
        
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
        
        return {"success": True, "preset": preset}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/growth/presets/{preset_id}/toggle")
async def toggle_preset(
    preset_id: str,
    enabled: bool,
    user = Depends(get_current_user)
):
    """Enable or disable a preset."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    success = await growth_presets_service.toggle_preset(
        preset_id=preset_id,
        enabled=enabled,
        user_id=user.get("user_id"),
        username=user.get("username"),
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
    
    return {"success": True, "preset_id": preset_id, "enabled": enabled}


@api_router.post("/growth/presets/{preset_id}/clone")
async def clone_preset(
    preset_id: str,
    new_name: str,
    user = Depends(get_current_user)
):
    """Clone a preset (system or custom) to a new custom preset."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    preset = await growth_presets_service.clone_to_custom(
        source_preset_id=preset_id,
        new_name=new_name,
        user_id=user.get("user_id"),
        username=user.get("username"),
    )
    
    if not preset:
        raise HTTPException(status_code=404, detail=f"Source preset {preset_id} not found")
    
    return {"success": True, "preset": preset}


@api_router.delete("/growth/presets/{preset_id}")
async def delete_custom_preset(preset_id: str, user = Depends(get_current_user)):
    """Delete a custom preset (cannot delete system presets)."""
    if not growth_presets_service:
        raise HTTPException(status_code=503, detail="Presets service not initialized")
    
    try:
        success = await growth_presets_service.delete_custom_preset(
            preset_id=preset_id,
            user_id=user.get("user_id"),
            username=user.get("username"),
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
        
        return {"success": True, "deleted": preset_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- Market Router ----------

@api_router.post("/growth/router/analyze")
async def analyze_market_for_routing(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Analyze market conditions and get routing recommendation.
    
    Body:
        symbol: Trading pair (e.g., "BTC/USDT")
        venue: Exchange (e.g., "binance" or "kraken")
        metrics: Market metrics dict OR
        ohlcv: Raw OHLCV data for metrics calculation
        current_capital_eur: User's current capital (default: 100)
        recent_pnl_pct: Recent P&L % for defensive mode (default: 0)
    """
    if not market_router:
        raise HTTPException(status_code=503, detail="Market router not initialized")
    
    symbol = data.get("symbol")
    venue = data.get("venue")
    
    if not symbol or not venue:
        raise HTTPException(status_code=400, detail="symbol and venue are required")
    
    # Build metrics
    if "metrics" in data:
        metrics = MarketMetrics(**data["metrics"])
    elif "ohlcv" in data and "bid" in data and "ask" in data:
        from datetime import datetime, timezone
        metrics = calculate_metrics_from_ohlcv(
            symbol=symbol,
            venue=venue,
            ohlcv=data["ohlcv"],
            bid=data["bid"],
            ask=data["ask"],
            last_data_timestamp=datetime.now(timezone.utc),
        )
    else:
        raise HTTPException(status_code=400, detail="Either 'metrics' or 'ohlcv'+'bid'+'ask' required")
    
    decision = await market_router.analyze(
        metrics=metrics,
        current_capital_eur=data.get("current_capital_eur", 100.0),
        recent_pnl_pct=data.get("recent_pnl_pct", 0.0),
    )
    
    return {
        "decision": decision.to_dict(),
    }


@api_router.get("/growth/router/decisions")
async def get_cached_router_decisions(user = Depends(get_current_user)):
    """Get all cached routing decisions."""
    if not market_router:
        raise HTTPException(status_code=503, detail="Market router not initialized")
    
    decisions = market_router.get_all_decisions()
    
    return {
        "count": len(decisions),
        "decisions": {k: v.to_dict() for k, v in decisions.items()},
    }


# ---------- Guardian ----------

@api_router.get("/growth/guardian/state")
async def get_guardian_state(user = Depends(get_current_user)):
    """Get current Guardian state (P&L tracking, kill switch status)."""
    if not guardian_service:
        raise HTTPException(status_code=503, detail="Guardian service not initialized")
    
    return {
        "state": guardian_service.get_state(),
    }


@api_router.post("/growth/guardian/validate")
async def validate_trade_request(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Validate a trade request against Guardian rules.
    
    Body:
        agent_id: Agent ID
        agent_type: "MM" or "MOM"
        symbol: Trading pair
        venue: Exchange
        side: "buy" or "sell"
        amount_eur: Trade amount
        spread_pct: Current spread
        estimated_slippage_pct: Estimated slippage
        data_age_seconds: Age of market data
        data_quality: Data quality score (0-1)
        expected_edge_pct: Expected profit %
        total_cost_pct: Estimated total cost %
    """
    if not guardian_service:
        raise HTTPException(status_code=503, detail="Guardian service not initialized")
    
    request = TradeRequest(**data)
    check = await guardian_service.validate_trade(request)
    
    return {
        "action": check.action.value,
        "allowed": check.allowed,
        "reasons": check.reasons,
        "warnings": check.warnings,
        "block_reason": check.block_reason.value if check.block_reason else None,
    }


@api_router.post("/growth/guardian/deactivate-kill-switch")
async def deactivate_guardian_kill_switch(
    force: bool = False,
    user = Depends(get_current_user)
):
    """
    Manually deactivate the kill switch. OWNER only.
    
    Query params:
        force: Force deactivate even during cooldown (default: false)
    """
    if not guardian_service:
        raise HTTPException(status_code=503, detail="Guardian service not initialized")
    
    user_role = (user.get("role") or "").upper()
    if user_role != "OWNER":
        raise HTTPException(status_code=403, detail="OWNER role required")
    
    success = await guardian_service.deactivate_kill_switch(
        user_id=user.get("user_id"),
        force=force,
    )
    
    if not success:
        return {
            "success": False,
            "message": "Kill switch not active or still in cooldown",
            "state": guardian_service.get_state(),
        }
    
    return {
        "success": True,
        "message": "Kill switch deactivated",
        "state": guardian_service.get_state(),
    }


@api_router.post("/growth/guardian/reset-daily")
async def reset_guardian_daily(user = Depends(get_current_user)):
    """Reset daily P&L tracking. OWNER/ADMIN only."""
    if not guardian_service:
        raise HTTPException(status_code=503, detail="Guardian service not initialized")
    
    user_role = (user.get("role") or "").upper()
    if user_role not in ["OWNER", "ADMIN"]:
        raise HTTPException(status_code=403, detail="OWNER or ADMIN role required")
    
    guardian_service.reset_daily()
    
    return {"success": True, "message": "Daily stats reset", "state": guardian_service.get_state()}


# ---------- Risk Budget ----------

@api_router.get("/growth/budget/state")
async def get_risk_budget_state(user = Depends(get_current_user)):
    """Get current risk budget allocation state."""
    if not risk_budget_service:
        raise HTTPException(status_code=503, detail="Risk budget service not initialized")
    
    state = risk_budget_service.get_state()
    
    if not state:
        return {"initialized": False, "state": None}
    
    return {"initialized": True, "state": state}


@api_router.post("/growth/budget/initialize")
async def initialize_risk_budget(
    total_capital_eur: float,
    user = Depends(get_current_user)
):
    """
    Initialize risk budget with starting capital.
    
    Body:
        total_capital_eur: Starting capital in EUR
    """
    if not risk_budget_service:
        raise HTTPException(status_code=503, detail="Risk budget service not initialized")
    
    if total_capital_eur <= 0:
        raise HTTPException(status_code=400, detail="Capital must be positive")
    
    await risk_budget_service.initialize(total_capital_eur)
    
    # Also initialize Guardian
    if guardian_service:
        await guardian_service.initialize(total_capital_eur)
    
    return {
        "success": True,
        "message": f"Risk budget initialized with {total_capital_eur}€",
        "state": risk_budget_service.get_state(),
    }


@api_router.post("/growth/budget/allocate")
async def request_allocation(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Request capital allocation for a trade.
    
    Body:
        agent_id: Agent requesting allocation
        agent_type: "MM" or "MOM"
        bucket_type: "CORE" or "EDGE"
        requested_eur: Amount requested
        symbol: Trading pair
    """
    if not risk_budget_service:
        raise HTTPException(status_code=503, detail="Risk budget service not initialized")
    
    try:
        bucket_type = BucketType(data.get("bucket_type", "CORE").upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="bucket_type must be 'CORE' or 'EDGE'")
    
    request = AllocationRequest(
        agent_id=data.get("agent_id"),
        agent_type=data.get("agent_type"),
        bucket_type=bucket_type,
        requested_eur=data.get("requested_eur", 0),
        symbol=data.get("symbol", ""),
    )
    
    result = await risk_budget_service.request_allocation(
        request=request,
        user_role=user.get("role", "user"),
    )
    
    return {
        "status": result.status.value,
        "approved_eur": result.approved_eur,
        "bucket": result.bucket_type.value,
        "reasons": result.reasons,
        "warnings": result.warnings,
    }


# ---------- Viability ----------

@api_router.post("/growth/viability/check")
async def check_trade_viability(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Check if a trade is viable (edge > cost * multiplier).
    
    Body:
        agent_type: "MM" or "MOM"
        preset_id: Preset being used
        symbol: Trading pair
        venue: Exchange
        order_size_eur: Trade size
        current_spread_pct: Current spread
        bid_price: Current bid
        ask_price: Current ask
        expected_move_pct: Expected price move to capture
        expect_maker: Expect maker execution (default: true)
    """
    if not viability_service:
        raise HTTPException(status_code=503, detail="Viability service not initialized")
    
    input_data = ViabilityInput(**data)
    result = await viability_service.check_viability(input_data)
    
    return {
        "status": result.status.value,
        "viable": result.viable,
        "expected_edge_pct": result.expected_edge_pct,
        "required_edge_pct": result.required_edge_pct,
        "edge_surplus_pct": result.edge_surplus_pct,
        "expected_profit_eur": result.expected_profit_eur,
        "break_even_move_pct": result.break_even_move_pct,
        "viability_multiplier": result.viability_multiplier,
        "cost_breakdown": result.cost_breakdown.model_dump(),
        "reasons": result.reasons,
        "warnings": result.warnings,
    }


@api_router.get("/growth/viability/min-move")
async def get_min_viable_move(
    venue: str,
    order_size_eur: float = 10.0,
    use_maker: bool = True,
    multiplier: float = 2.0,
    user = Depends(get_current_user)
):
    """
    Get minimum price move needed for viability.
    
    Query params:
        venue: Exchange name
        order_size_eur: Trade size (default: 10)
        use_maker: Use maker fees (default: true)
        multiplier: Viability multiplier (default: 2.0)
    """
    if not viability_service:
        raise HTTPException(status_code=503, detail="Viability service not initialized")
    
    result = viability_service.get_min_viable_move(
        venue=venue,
        order_size_eur=order_size_eur,
        use_maker=use_maker,
        multiplier=multiplier,
    )
    
    return result


# ---------- Growth Module Summary ----------

@api_router.get("/growth/status")
async def get_growth_module_status(user = Depends(get_current_user)):
    """Get overall status of the Growth Module."""
    status = {
        "initialized": {
            "system_config": system_config_service is not None,
            "presets": growth_presets_service is not None,
            "router": market_router is not None,
            "guardian": guardian_service is not None,
            "risk_budget": risk_budget_service is not None,
            "viability": viability_service is not None,
        },
        "guardian_state": guardian_service.get_state() if guardian_service else None,
        "budget_state": risk_budget_service.get_state() if risk_budget_service else None,
    }
    
    # Count presets
    if growth_presets_service:
        mm_presets = await growth_presets_service.get_mm_presets()
        mom_presets = await growth_presets_service.get_mom_presets()
        status["presets"] = {
            "mm_count": len(mm_presets),
            "mom_count": len(mom_presets),
        }
    
    return status


# ============ Growth Orchestrator Endpoints ============

@api_router.post("/growth/run/once")
async def growth_run_once(
    symbol: str = "BTC/USDT",
    venue: str = "auto",
    force_agent: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Run one complete Growth Module cycle.
    
    This executes: Router -> Guardian -> Viability -> Agent.plan() -> PaperExecutor
    
    Paper trading only.
    """
    from services.growth_orchestrator import get_growth_orchestrator
    from services.growth import RunMode
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    # Use new clean interface: run(mode) -> RunResult
    result = await orchestrator.run(
        mode=RunMode.RUN_ONCE,
        symbol=symbol,
        venue=venue,
    )
    
    return result.model_dump(mode='json')


@api_router.post("/growth/run/simulate")
async def growth_run_simulate(
    symbol: str = "BTC/USDT",
    venue: str = "auto",
    force_agent: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Dry run (simulate) without creating actual paper orders.
    
    Returns the same structure as /run/once but without execution.
    """
    from services.growth_orchestrator import get_growth_orchestrator
    from services.growth import RunMode
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    # Use new clean interface: run(mode) -> RunResult
    result = await orchestrator.run(
        mode=RunMode.DRY_RUN,
        symbol=symbol,
        venue=venue,
    )
    
    return result.model_dump(mode='json')


@api_router.get("/growth/run/last")
async def growth_get_last_run(user = Depends(get_current_user)):
    """Get the last Growth Module run result."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    last_cycle = await orchestrator.get_last_cycle()
    
    if not last_cycle:
        return {"message": "No runs yet"}
    
    return last_cycle


@api_router.get("/growth/run/history")
async def growth_get_run_history(
    limit: int = 20,
    status: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get Growth Module run history."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    cycles = await orchestrator.get_cycles(limit=limit, status=status)
    
    return {"cycles": cycles, "count": len(cycles)}


@api_router.get("/growth/paper/orders")
async def growth_get_paper_orders(
    limit: int = 50,
    user = Depends(get_current_user)
):
    """Get recent paper orders from Growth Module runs."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    if not orchestrator.paper_adapter:
        return {"orders": [], "count": 0}
    
    orders = await orchestrator.paper_adapter.get_paper_orders(limit=limit)
    
    return {"orders": orders, "count": len(orders)}


@api_router.get("/growth/paper/pnl")
async def growth_get_paper_pnl(user = Depends(get_current_user)):
    """Get PnL summary from Growth Module paper trading."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    if not orchestrator.paper_adapter:
        return {
            "total_runs": 0,
            "total_pnl_eur": 0,
            "total_fees_eur": 0,
            "net_pnl_eur": 0,
        }
    
    summary = await orchestrator.paper_adapter.get_pnl_summary()
    
    return summary


@api_router.post("/growth/run/schedule")
async def growth_set_schedule(
    enabled: bool,
    interval_minutes: int = 15,
    user = Depends(require_owner)
):
    """
    Enable or disable the Growth Module scheduler.
    
    OWNER/ADMIN only.
    
    The scheduler runs cycles automatically at the specified interval.
    """
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    if enabled:
        await orchestrator.start_scheduler(interval_minutes=interval_minutes)
    else:
        await orchestrator.stop_scheduler()
    
    return {
        "success": True,
        "scheduler": orchestrator.get_scheduler_status(),
    }


@api_router.get("/growth/schedule/config")
async def growth_get_schedule_config(user = Depends(get_current_user)):
    """Get scheduler configuration (alias for /growth/run/schedule)."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    return orchestrator.get_scheduler_status()


@api_router.get("/growth/schedule/stats")
async def growth_get_schedule_stats(user = Depends(get_current_user)):
    """Get scheduler statistics for today."""
    try:
        from datetime import datetime, timezone
        
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get today's runs from growth_runs collection
        today_runs = await db.growth_runs.count_documents({
            "started_at": {"$gte": today}
        })
        
        # Get blocked runs
        blocked_runs = await db.growth_runs.count_documents({
            "started_at": {"$gte": today},
            "guardian_decision": "BLOCK"
        })
        
        # Get last run
        last_run = await db.growth_runs.find_one(
            {},
            {"_id": 0, "run_id": 1, "started_at": 1, "status": 1},
            sort=[("started_at", -1)]
        )
        
        return {
            "status": "ok",
            "runs_today": today_runs,
            "blocked_today": blocked_runs,
            "last_run": last_run,
            "max_runs_per_hour": 4,
            "cooldown_after_block_min": 30
        }
    except Exception as e:
        logger.warning(f"Error getting schedule stats: {e}")
        return {
            "status": "ok",
            "scheduled_jobs": 0,
            "last_run_at": None,
            "note": "Scheduler stats not configured in this deployment."
        }


@api_router.put("/growth/schedule/config")
async def growth_update_schedule_config(
    request: Request,
    user = Depends(require_owner)
):
    """
    Update scheduler configuration (alias for scheduler/config).
    """
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    # Parse request body
    body = await request.json()
    
    result = await orchestrator.update_scheduler_config(
        enabled=body.get("enabled"),
        interval_minutes=body.get("interval_minutes"),
        symbols=body.get("symbols"),
        active_hours_start=body.get("active_hours_start"),
        active_hours_end=body.get("active_hours_end"),
        active_days=body.get("active_days"),
    )
    
    return result


@api_router.get("/growth/run/schedule")
async def growth_get_schedule(user = Depends(get_current_user)):
    """Get current scheduler status."""
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    return orchestrator.get_scheduler_status()


@api_router.put("/growth/scheduler/config")
async def growth_update_scheduler_config(
    enabled: Optional[bool] = None,
    interval_minutes: Optional[int] = None,
    symbols: Optional[List[str]] = None,
    active_hours_start: Optional[int] = None,
    active_hours_end: Optional[int] = None,
    active_days: Optional[List[int]] = None,
    user = Depends(require_owner)
):
    """
    Update advanced scheduler configuration.
    
    OWNER/ADMIN only.
    
    Parameters:
    - enabled: Turn scheduler on/off
    - interval_minutes: Minutes between runs (5, 15, 30, 60)
    - symbols: List of symbols to trade (e.g., ["BTC/USDT", "ETH/USDT"])
    - active_hours_start: Start hour UTC (0-23)
    - active_hours_end: End hour UTC (0-23)
    - active_days: Days to run (0=Mon, 1=Tue, ..., 6=Sun)
    """
    from services.growth_orchestrator import get_growth_orchestrator
    
    orchestrator = get_growth_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Growth orchestrator not initialized")
    
    result = await orchestrator.update_scheduler_config(
        enabled=enabled,
        interval_minutes=interval_minutes,
        symbols=symbols,
        active_hours_start=active_hours_start,
        active_hours_end=active_hours_end,
        active_days=active_days,
    )
    
    return {
        "success": True,
        "scheduler": result,
    }


# ============================================================
# BACKTEST / REPLAY TOOL (P4)
# ============================================================

@api_router.get("/backtest/strategies")
async def get_backtest_strategies(user = Depends(get_current_user)):
    """Get available backtest strategies and their default parameters."""
    return {
        "strategies": [
            {
                "name": name,
                "description": fn.__doc__.strip().split("\n")[0] if fn.__doc__ else name,
                "defaults": BACKTEST_STRATEGY_DEFAULTS.get(name, {}),
            }
            for name, fn in BACKTEST_STRATEGIES.items()
        ]
    }


@api_router.post("/backtest/run")
async def run_backtest(
    request: Request,
    user = Depends(get_current_user),
):
    """
    Run a backtest simulation.
    
    Request body:
    {
        "symbol": "BTC/USDT",
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "strategy": "momentum",
        "strategy_params": {"oversold": 25, "overbought": 75},
        "initial_capital": 10000,
        "position_size_pct": 0.95
    }
    """
    engine = get_backtest_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Backtest engine not initialized")
    
    body = await request.json()
    
    # Parse dates
    try:
        start_date = datetime.fromisoformat(body["start_date"].replace("Z", "+00:00"))
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid start_date: {e}")
    
    try:
        end_date = datetime.fromisoformat(body["end_date"].replace("Z", "+00:00"))
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid end_date: {e}")
    
    # Validate date range
    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Maximum backtest period is 365 days")
    
    # Run backtest
    result = await engine.run(
        symbol=body.get("symbol", "BTC/USDT"),
        start_date=start_date,
        end_date=end_date,
        strategy=body.get("strategy", "momentum"),
        strategy_params=body.get("strategy_params"),
        initial_capital=body.get("initial_capital", 10000.0),
        position_size_pct=body.get("position_size_pct", 0.95),
    )
    
    return result.to_dict()


@api_router.get("/backtest/history")
async def get_backtest_history(
    limit: int = 20,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    user = Depends(get_current_user),
):
    """Get historical backtest results."""
    engine = get_backtest_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Backtest engine not initialized")
    
    results = await engine.get_history(
        limit=min(limit, 100),
        symbol=symbol,
        strategy=strategy,
    )
    return {"results": results}


@api_router.get("/backtest/{backtest_id}")
async def get_backtest_result(
    backtest_id: str,
    user = Depends(get_current_user),
):
    """Get a specific backtest result."""
    engine = get_backtest_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Backtest engine not initialized")
    
    result = await engine.get_result(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    return result


# ============================================================
# BACKTEST OPTIMIZATION (P6)
# ============================================================

@api_router.get("/backtest/optimize/param-ranges")
async def get_optimization_param_ranges(user = Depends(get_current_user)):
    """Get parameter ranges available for optimization."""
    return {
        "param_ranges": {
            strategy: [
                {
                    "name": r.name,
                    "min": r.min_val,
                    "max": r.max_val,
                    "step": r.step,
                    "type": r.param_type,
                }
                for r in ranges
            ]
            for strategy, ranges in STRATEGY_PARAM_RANGES.items()
        }
    }


@api_router.post("/backtest/optimize")
async def run_optimization(
    request: Request,
    user = Depends(get_current_user),
):
    """
    Run backtest optimization with walk-forward validation.
    
    Request body:
    {
        "strategy": "momentum",
        "symbol": "BTC/USDT",
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "initial_capital": 10000,
        "num_variations": 20,
        "train_ratio": 0.7,
        "base_params": {"oversold": 30, "overbought": 70}  // optional
    }
    
    Returns top parameter variations with train/test metrics and overfit risk.
    """
    engine = get_optimization_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Optimization engine not initialized")
    
    body = await request.json()
    
    # Parse dates
    try:
        start_date = datetime.fromisoformat(body["start_date"].replace("Z", "+00:00"))
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid start_date: {e}")
    
    try:
        end_date = datetime.fromisoformat(body["end_date"].replace("Z", "+00:00"))
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid end_date: {e}")
    
    # Validate date range
    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Maximum optimization period is 365 days")
    
    if (end_date - start_date).days < 30:
        raise HTTPException(status_code=400, detail="Minimum optimization period is 30 days")
    
    # Validate variations count
    num_variations = body.get("num_variations", 20)
    if num_variations < 5 or num_variations > 50:
        raise HTTPException(status_code=400, detail="num_variations must be between 5 and 50")
    
    # Run optimization
    job = await engine.run_optimization(
        strategy=body.get("strategy", "momentum"),
        symbol=body.get("symbol", "BTC/USDT"),
        start_date=start_date,
        end_date=end_date,
        initial_capital=body.get("initial_capital", 10000.0),
        num_variations=num_variations,
        train_ratio=body.get("train_ratio", 0.7),
        base_params=body.get("base_params"),
    )
    
    return job.to_dict()


@api_router.get("/backtest/optimize/history")
async def get_optimization_history(
    limit: int = 10,
    user = Depends(get_current_user),
):
    """Get historical optimization jobs."""
    engine = get_optimization_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Optimization engine not initialized")
    
    results = await engine.get_history(limit=min(limit, 50))
    return {"results": results}


@api_router.get("/backtest/optimize/{job_id}")
async def get_optimization_job(
    job_id: str,
    user = Depends(get_current_user),
):
    """Get a specific optimization job."""
    engine = get_optimization_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Optimization engine not initialized")
    
    result = await engine.get_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Optimization job not found")
    
    return result


# ============================================================
# STRATEGY -> AGENT MAPPING (P6)
# ============================================================

@api_router.get("/mapping/strategies")
async def get_strategy_mappings(user = Depends(get_current_user)):
    """
    Get all strategy-to-agent mappings with explanations.
    
    Returns mapping for each backtest strategy to recommended agent type
    with reasoning, market conditions, and risk profile.
    """
    mapper = get_strategy_mapper()
    return {
        "mappings": mapper.get_all_mappings(),
        "agents": ["GRID", "TREND", "DCA", "MM"],
    }


@api_router.post("/mapping/suggest-agent-from-result")
async def suggest_agent_from_backtest_result(
    request: Request,
    user = Depends(get_current_user),
):
    """
    Suggest an agent based on backtest results.
    
    Request body:
    {
        "strategy": "momentum",
        "symbol": "BTC/USDT",
        "metrics": {
            "total_return_pct": 15.5,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 12.3,
            "win_rate": 55.0,
            "profit_factor": 1.8,
            "total_trades": 25
        }
    }
    
    Returns agent suggestion with confidence, reasoning, and recommended params.
    """
    body = await request.json()
    
    strategy = body.get("strategy")
    symbol = body.get("symbol", "BTC/USDT")
    metrics = body.get("metrics", {})
    
    if not strategy:
        raise HTTPException(status_code=400, detail="strategy is required")
    if not metrics:
        raise HTTPException(status_code=400, detail="metrics are required")
    
    mapper = get_strategy_mapper()
    suggestion = mapper.suggest_agent_from_backtest(strategy, metrics, symbol)
    
    return suggestion.to_dict()


# ============================================================
# SAVE OPTIMIZED PRESET (with audit logging)
# ============================================================

@api_router.post("/backtest/save-as-preset")
async def save_optimization_as_preset(
    request: Request,
    user = Depends(require_owner),
):
    """
    Save optimized parameters as a custom preset.
    
    Requires explicit user action and owner role.
    Creates audit log entry.
    Does NOT overwrite base presets.
    
    Request body:
    {
        "name": "My Optimized Momentum",
        "description": "Momentum with optimized RSI thresholds",
        "strategy": "momentum",
        "params": {"oversold": 25, "overbought": 75},
        "optimization_job_id": "optional-job-id",
        "metrics_summary": {"test_return_pct": 15.5, "overfit_risk": 25}
    }
    """
    body = await request.json()
    
    preset_name = body.get("name")
    if not preset_name:
        raise HTTPException(status_code=400, detail="Preset name is required")
    
    # Validate name doesn't conflict with system presets
    system_preset_names = ["conservative", "moderate", "aggressive", "default"]
    if preset_name.lower() in system_preset_names:
        raise HTTPException(status_code=400, detail="Cannot use system preset names")
    
    # Create custom preset document
    preset_id = str(uuid4())
    preset_doc = {
        "id": preset_id,
        "name": preset_name,
        "description": body.get("description", ""),
        "type": "custom_optimized",
        "strategy": body.get("strategy"),
        "params": body.get("params", {}),
        "optimization_job_id": body.get("optimization_job_id"),
        "metrics_summary": body.get("metrics_summary", {}),
        "created_by": user.get("username"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": False,  # Requires explicit activation
    }
    
    # Save to database
    await db.custom_presets.insert_one({**preset_doc, "_id": None})
    
    # Audit log
    audit_service = get_audit_service()
    if audit_service:
        await audit_service.log(
            action="preset.save",
            user_id=user.get("user_id", ""),
            username=user.get("username", ""),
            role=user.get("role", ""),
            ip="internal",
            resource_type="custom_preset",
            resource_id=preset_id,
            after=preset_doc,
            success=True,
            metadata={
                "source": "backtest_optimization",
                "optimization_job_id": body.get("optimization_job_id"),
            }
        )
    
    return {
        "success": True,
        "preset_id": preset_id,
        "message": f"Preset '{preset_name}' saved. Activate manually before use.",
    }


# ============================================================
# WebSocket for Real-Time Updates
# ============================================================

@app.websocket("/api/ws/stream")
async def trades_websocket(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint for real-time trades and metrics streaming.
    
    Authentication:
    - JWT required via query param (?token=xxx) or Authorization header
    - Invalid/missing token closes with code 4401
    
    Events (server -> client):
    - trade.created: New trade executed
    - trade.updated: Trade status/PnL updated  
    - metrics.updated: Periodic metrics (every 5s)
    - heartbeat: Connection keepalive (every 30s)
    
    Client messages:
    - { "type": "subscribe", "topics": ["trades", "metrics"], "filters": {...} }
    - { "type": "unsubscribe", "topics": ["trades"] }
    - { "type": "ping" }
    """
    from services.ws_stream import get_ws_manager
    from urllib.parse import parse_qs, urlparse
    
    manager = get_ws_manager()
    
    # Get token from query param
    auth_token = token
    
    # If token not in FastAPI param, try to extract from URL manually
    if not auth_token:
        try:
            # Parse the URL query string
            query_string = str(websocket.scope.get("query_string", b""), "utf-8")
            if query_string:
                params = parse_qs(query_string)
                if "token" in params:
                    auth_token = params["token"][0]
                    logger.debug(f"[WS] Token extracted from query string: {auth_token[:30]}...")
        except Exception as e:
            logger.warning(f"[WS] Failed to parse query string: {e}")
    
    # Try to get from headers (workaround for some WS clients)
    if not auth_token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]
            logger.debug(f"[WS] Token from Authorization header")
    
    # Log token status (not the actual token)
    if auth_token:
        logger.info(f"[WS] Connection attempt with token (length={len(auth_token)})")
    else:
        logger.warning(f"[WS] Connection attempt without token")
    
    # Authenticate and connect
    conn_id = await manager.connect(websocket, auth_token or "")
    if not conn_id:
        # Connection was rejected (auth failed)
        return
    
    try:
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                await manager.handle_message(conn_id, data)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"WebSocket receive error: {e}")
                break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(conn_id, reason="client_disconnect", code=1000)


@app.websocket("/api/ws/growth")
async def growth_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Growth Module updates.
    
    Sends push notifications for:
    - PnL changes
    - Order updates
    - Guardian state changes
    - Run completions
    - Scheduler state changes
    """
    from services.growth.websocket_manager import get_growth_ws_manager
    from services.growth_orchestrator import get_growth_orchestrator
    
    manager = get_growth_ws_manager()
    user_id = f"user_{id(websocket)}"
    
    try:
        await manager.connect(websocket, user_id)
        
        # Send initial state
        orchestrator = get_growth_orchestrator()
        if orchestrator:
            # Get current data
            try:
                last_run = await orchestrator.get_last_cycle()
                manager.update_state("run", last_run)
                manager.update_state("scheduler", orchestrator.get_scheduler_status())
                
                # Get PnL if paper adapter available
                if orchestrator.paper_adapter:
                    pnl = await orchestrator.paper_adapter.get_pnl_summary()
                    manager.update_state("pnl", pnl)
                    orders = await orchestrator.paper_adapter.get_recent_orders(limit=20)
                    manager.update_state("orders", orders)
            except Exception as e:
                logger.warning(f"Error getting initial WS state: {e}")
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Handle subscription changes
                if data.get("action") == "subscribe":
                    types = data.get("types", [])
                    manager.subscriptions[user_id] = set(types)
                
                # Handle ping/pong
                elif data.get("action") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"WebSocket receive error: {e}")
                break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(user_id)


# ============================================================
# END GROWTH MODULE ENDPOINTS
# ============================================================


# ============================================================
# SANDBOX ENDPOINTS (SIMULATION ONLY)
# ============================================================

# Sandbox runner instance
sandbox_runner = None

async def get_sandbox_runner():
    """Get or create sandbox runner instance."""
    global sandbox_runner
    if sandbox_runner is None:
        sandbox_runner = SandboxRunner(db)
        sandbox_runner.set_event_logger(event_logger)
    return sandbox_runner


@api_router.get("/sandbox/scenarios")
async def get_sandbox_scenarios():
    """
    Get list of available sandbox scenarios/presets.
    
    SIMULATION MODE ONLY.
    """
    runner = await get_sandbox_runner()
    scenarios = await runner.get_scenarios()
    return {
        "scenarios": scenarios,
        "sandbox_enabled": runner.enabled,
    }


@api_router.post("/sandbox/run")
async def start_sandbox_run(
    request: dict,
    user = Depends(get_current_user)
):
    """
    Start a new sandbox stress test run.
    
    Body:
        symbols: List of symbols to test
        packs: {"crash": true, "dex": true, "infra": true}
        severity: "LOW" | "MED" | "HIGH" | "APOC"
        duration_min: Duration in minutes
        seed: Optional seed for reproducibility
    
    SECURITY:
    - SIMULATION ONLY
    - Forces PAPER mode
    - Logged as SIMULATION in audit
    """
    from services.sandbox import SandboxConfig, Severity
    
    runner = await get_sandbox_runner()
    
    if not runner.enabled:
        raise HTTPException(status_code=503, detail="Sandbox is disabled (SANDBOX_ENABLED=false)")
    
    # Parse config
    config = SandboxConfig(
        symbols=request.get("symbols", ["BTCUSDT", "ETHUSDT"]),
        packs=request.get("packs", {"crash": True, "dex": True, "infra": True}),
        severity=Severity(request.get("severity", "MED")),
        duration_min=request.get("duration_min", 60),
        seed=request.get("seed"),
    )
    
    try:
        # Start run
        run = await runner.start_run(config)
        
        # Execute in background
        asyncio.create_task(runner.execute_run(run.run_id))
        
        return {
            "run_id": run.run_id,
            "seed": run.seed,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "timeline_events": run.timeline_events,
            "status": run.status.value,
            "message": "Sandbox run started - SIMULATION MODE",
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/sandbox/stop")
async def stop_sandbox_run(user = Depends(get_current_user)):
    """
    Stop the current sandbox run.
    """
    runner = await get_sandbox_runner()
    
    run = await runner.stop_run()
    
    if not run:
        return {"status": "no_run", "message": "No sandbox run in progress"}
    
    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "message": "Sandbox run stopped",
    }


@api_router.get("/sandbox/status")
async def get_sandbox_status():
    """
    Get current sandbox run status and metrics.
    
    Returns null if no run in progress.
    """
    runner = await get_sandbox_runner()
    
    status = await runner.get_status()
    
    return {
        "sandbox_enabled": runner.enabled,
        "has_active_run": status is not None,
        "run": status,
        "mode": "SIMULATION",
    }


@api_router.get("/sandbox/report/{run_id}")
async def get_sandbox_report(run_id: str):
    """
    Get full report for a sandbox run.
    
    Returns detailed metrics, events, executions, and guardian decisions.
    """
    runner = await get_sandbox_runner()
    
    report = await runner.get_report(run_id)
    
    if not report:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    return report.model_dump()


@api_router.get("/sandbox/runs")
async def get_sandbox_runs(limit: int = 20):
    """
    Get list of recent sandbox runs.
    """
    cursor = db.sandbox_runs.find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    
    runs = await cursor.to_list(length=limit)
    return {"runs": runs}


# ============ Learning & Profile Endpoints ============

@api_router.get("/profiles/{agent_id}")
async def get_agent_profile(agent_id: str):
    """Get active profile for an agent."""
    profile = await db.agent_profiles.find_one(
        {"agent_id": agent_id},
        {"_id": 0}
    )
    
    if not profile:
        return {"agent_id": agent_id, "profile_active_id": None}
    
    # Get the active version details
    if profile.get("profile_active_id"):
        version = await db.agent_profile_versions.find_one(
            {"profile_id": profile["profile_active_id"]},
            {"_id": 0}
        )
        profile["active_version"] = version
    
    return profile


@api_router.get("/profiles/{agent_id}/versions")
async def get_agent_profile_versions(agent_id: str, strategy_id: str = None):
    """Get all profile versions for an agent."""
    query = {"agent_id": agent_id}
    if strategy_id:
        query["strategy_id"] = strategy_id
    
    cursor = db.agent_profile_versions.find(
        query,
        {"_id": 0}
    ).sort("version", -1)
    
    versions = await cursor.to_list(100)
    return {"versions": versions}


@api_router.post("/profiles/activate")
async def activate_profile(
    request: dict,
    user = Depends(get_current_user)
):
    """
    Activate a specific profile version for an agent.
    
    Body:
        agent_id: Agent ID
        strategy_id: Strategy ID
        profile_id: Profile version ID to activate
    """
    agent_id = request.get("agent_id")
    strategy_id = request.get("strategy_id")
    profile_id = request.get("profile_id")
    
    if not all([agent_id, strategy_id, profile_id]):
        raise HTTPException(status_code=400, detail="agent_id, strategy_id, and profile_id required")
    
    # Verify profile exists
    version = await db.agent_profile_versions.find_one({"profile_id": profile_id})
    if not version:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    
    # Update or create agent profile
    await db.agent_profiles.update_one(
        {"agent_id": agent_id, "strategy_id": strategy_id},
        {
            "$set": {
                "profile_active_id": profile_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True
    )
    
    # Audit log
    await log_admin_audit(
        action="ACTIVATE_PROFILE",
        user_id=user.get("id"),
        resource_type="agent_profile",
        resource_id=f"{agent_id}/{strategy_id}",
        details={
            "profile_id": profile_id,
            "tag": "SIMULATION" if version.get("source") == "sandbox" else "MANUAL",
        }
    )
    
    return {
        "success": True,
        "agent_id": agent_id,
        "profile_id": profile_id,
    }


# ============ Promotion Endpoints ============

@api_router.post("/promotions/request")
async def create_promotion_request(
    request: dict,
    user = Depends(get_current_user)
):
    """
    Create a promotion request from Sandbox to Paper/Live.
    
    Body:
        agent_id: Agent ID
        strategy_id: Strategy ID
        to_profile_id: Profile version to promote
        from_profile_id: Optional current profile ID
        target_env: "paper_live" | "live"
        notes: Optional notes
    """
    from services.sandbox.learning_models import PromotionRequest, PromotionStatus, PromotionTarget
    
    # MVP SAFETY GUARD: Block promotions to "live" environment
    target_env = request.get("target_env", "paper_live")
    if target_env == "live":
        raise HTTPException(
            status_code=400, 
            detail="Promotion to LIVE environment is disabled in MVP. Only 'paper_live' is allowed."
        )
    
    # Verify profile exists
    to_profile = await db.agent_profile_versions.find_one({"profile_id": request["to_profile_id"]})
    if not to_profile:
        raise HTTPException(status_code=404, detail=f"Profile {request['to_profile_id']} not found")
    
    promotion = PromotionRequest(
        requested_by=user.get("user_id", user.get("id", "unknown")),
        agent_id=request["agent_id"],
        strategy_id=request["strategy_id"],
        from_profile_id=request.get("from_profile_id", ""),
        to_profile_id=request["to_profile_id"],
        target_env=PromotionTarget(target_env),
        status=PromotionStatus.PENDING,
        approval_notes=request.get("notes", ""),
    )
    
    await db.promotion_requests.insert_one(promotion.model_dump())
    
    # Audit
    await log_admin_audit(
        action="PROMOTION_REQUESTED",
        user_id=user.get("id"),
        resource_type="promotion",
        resource_id=promotion.request_id,
        details={
            "agent_id": promotion.agent_id,
            "to_profile_id": promotion.to_profile_id,
            "target_env": promotion.target_env.value,
            "tag": "PROMOTION",
        }
    )
    
    return {
        "request_id": promotion.request_id,
        "status": promotion.status.value,
    }


@api_router.post("/promotions/approve")
async def approve_promotion(
    request: dict,
    user = Depends(require_owner)
):
    """
    Approve or reject a promotion request.
    
    OWNER ONLY.
    
    Body:
        request_id: Promotion request ID
        approve: boolean
        notes: Optional approval/rejection notes
    """
    from services.sandbox.learning_models import PromotionStatus
    
    request_id = request.get("request_id")
    approve = request.get("approve", False)
    notes = request.get("notes", "")
    
    promo = await db.promotion_requests.find_one({"request_id": request_id})
    if not promo:
        raise HTTPException(status_code=404, detail=f"Promotion {request_id} not found")
    
    new_status = PromotionStatus.APPROVED if approve else PromotionStatus.REJECTED
    
    await db.promotion_requests.update_one(
        {"request_id": request_id},
        {
            "$set": {
                "status": new_status.value,
                "approval_notes": notes if approve else None,
                "rejection_reason": notes if not approve else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )
    
    # Audit
    await log_admin_audit(
        action="PROMOTION_APPROVED" if approve else "PROMOTION_REJECTED",
        user_id=user.get("id"),
        resource_type="promotion",
        resource_id=request_id,
        details={
            "approved": approve,
            "notes": notes,
            "tag": "PROMOTION",
        }
    )
    
    return {
        "request_id": request_id,
        "status": new_status.value,
        "approved": approve,
    }


@api_router.post("/promotions/apply")
async def apply_promotion(
    request: dict,
    user = Depends(require_owner)
):
    """
    Apply an approved promotion.
    
    OWNER ONLY.
    
    Body:
        request_id: Approved promotion request ID
    """
    from services.sandbox.learning_models import PromotionStatus
    
    request_id = request.get("request_id")
    
    promo = await db.promotion_requests.find_one({"request_id": request_id})
    if not promo:
        raise HTTPException(status_code=404, detail=f"Promotion {request_id} not found")
    
    if promo.get("status") != PromotionStatus.APPROVED.value:
        raise HTTPException(status_code=400, detail="Promotion must be approved before applying")
    
    # For LIVE target, verify safety conditions
    if promo.get("target_env") == "live":
        # Check live_cex_enabled is still false
        if os.environ.get("LIVE_CEX_ENABLED", "false").lower() == "true":
            raise HTTPException(status_code=400, detail="Cannot apply LIVE promotion while LIVE_CEX_ENABLED=true")
        
        # Additional checks could be added here (GO-LIVE Gate, etc.)
    
    # Activate the profile
    await db.agent_profiles.update_one(
        {"agent_id": promo["agent_id"], "strategy_id": promo["strategy_id"]},
        {
            "$set": {
                "profile_active_id": promo["to_profile_id"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True
    )
    
    # Update promotion status
    await db.promotion_requests.update_one(
        {"request_id": request_id},
        {
            "$set": {
                "status": PromotionStatus.APPLIED.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )
    
    # Audit
    await log_admin_audit(
        action="PROMOTION_APPLIED",
        user_id=user.get("id"),
        resource_type="promotion",
        resource_id=request_id,
        details={
            "agent_id": promo["agent_id"],
            "profile_id": promo["to_profile_id"],
            "target_env": promo["target_env"],
            "tag": "PROMOTION",
        }
    )
    
    return {
        "request_id": request_id,
        "status": "applied",
        "profile_activated": promo["to_profile_id"],
    }


@api_router.get("/promotions")
async def list_promotions(
    status: str = None,
    agent_id: str = None,
    limit: int = 50
):
    """Get list of promotion requests with requester info."""
    query = {}
    if status:
        query["status"] = status
    if agent_id:
        query["agent_id"] = agent_id
    
    cursor = db.promotion_requests.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    
    promotions = await cursor.to_list(length=limit)
    return {"promotions": promotions}


@api_router.get("/promotions/{request_id}")
async def get_promotion(request_id: str):
    """Get a specific promotion request with full details."""
    promo = await db.promotion_requests.find_one(
        {"request_id": request_id},
        {"_id": 0}
    )
    if not promo:
        raise HTTPException(status_code=404, detail=f"Promotion {request_id} not found")
    
    # Enrich with profile info
    if promo.get("to_profile_id"):
        to_profile = await db.agent_profile_versions.find_one(
            {"profile_id": promo["to_profile_id"]},
            {"_id": 0}
        )
        promo["to_profile"] = to_profile
    
    if promo.get("from_profile_id"):
        from_profile = await db.agent_profile_versions.find_one(
            {"profile_id": promo["from_profile_id"]},
            {"_id": 0}
        )
        promo["from_profile"] = from_profile
    
    return promo


@api_router.get("/profiles/by-run/{run_id}")
async def get_profiles_by_run(run_id: str):
    """Get all profiles generated by a specific sandbox run."""
    cursor = db.agent_profile_versions.find(
        {"source_run_id": run_id},
        {"_id": 0}
    ).sort("created_at", -1)
    
    profiles = await cursor.to_list(length=100)
    return {"profiles": profiles, "run_id": run_id}


@api_router.get("/profiles/diff")
async def get_profile_diff(
    from_profile: str = None,
    to_profile: str = None
):
    """
    Get diff between two profile versions.
    
    Useful for reviewing changes before promotion.
    Compares: params, constraints, dex_rules, infra_rules
    """
    from_doc = None
    to_doc = None
    
    if from_profile:
        from_doc = await db.agent_profile_versions.find_one(
            {"profile_id": from_profile},
            {"_id": 0}
        )
    
    if to_profile:
        to_doc = await db.agent_profile_versions.find_one(
            {"profile_id": to_profile},
            {"_id": 0}
        )
    
    if not from_doc and not to_doc:
        raise HTTPException(status_code=404, detail="Neither profile found")
    
    # Comprehensive diff - compare all key sections
    changes = []
    
    def compare_section(section_name: str, from_data: dict, to_data: dict):
        """Compare two dictionaries and return changes."""
        from_data = from_data or {}
        to_data = to_data or {}
        all_keys = set(from_data.keys()) | set(to_data.keys())
        
        for key in sorted(all_keys):
            from_val = from_data.get(key)
            to_val = to_data.get(key)
            if from_val != to_val:
                changes.append({
                    "section": section_name,
                    "field": key,
                    "from": from_val,
                    "to": to_val,
                    "change_type": "modified" if from_val and to_val else ("added" if to_val else "removed")
                })
    
    if from_doc or to_doc:
        # Compare params
        compare_section(
            "params",
            from_doc.get("params", {}) if from_doc else {},
            to_doc.get("params", {}) if to_doc else {}
        )
        
        # Compare constraints
        compare_section(
            "constraints",
            from_doc.get("constraints", {}) if from_doc else {},
            to_doc.get("constraints", {}) if to_doc else {}
        )
        
        # Compare dex_rules
        compare_section(
            "dex_rules",
            from_doc.get("dex_rules", {}) if from_doc else {},
            to_doc.get("dex_rules", {}) if to_doc else {}
        )
        
        # Compare infra_rules
        compare_section(
            "infra_rules",
            from_doc.get("infra_rules", {}) if from_doc else {},
            to_doc.get("infra_rules", {}) if to_doc else {}
        )
    
    # Summary stats
    summary = {
        "total_changes": len(changes),
        "by_section": {}
    }
    for change in changes:
        section = change["section"]
        summary["by_section"][section] = summary["by_section"].get(section, 0) + 1
    
    return {
        "from_profile": from_profile,
        "to_profile": to_profile,
        "changes": changes,
        "summary": summary,
        "from_doc": from_doc,
        "to_doc": to_doc,
    }


# ============================================================
# SNIPER HARDENING ENDPOINTS
# ============================================================

# Initialize sniper hardening service
sniper_hardening_service = None

# Initialize analytics service
analytics_service = None


class SniperEvaluationRequest(BaseModel):
    run_id: str
    agent_id: str
    symbol: str
    strategy_id: str = "sniper"  # For Mode A or actual strategy for Mode B
    severity: str = "MED"
    packs: Dict[str, bool] = Field(default_factory=lambda: {"crash": True, "dex": True, "infra": True})
    overrides: Optional[Dict[str, Any]] = None
    # Mode selection
    mode: str = "dedicated_sniper"  # "dedicated_sniper" or "sniper_mode"
    venue_type: str = "SIM_SANDBOX"  # "DEX", "CEX", "SIM_SANDBOX"
    # Order intent
    order_side: str = "buy"
    desired_qty: float = 0
    slippage_tolerance: float = 1.0
    # Context data from sandbox
    pool_liquidity_usd: Optional[float] = None
    trade_size_usd: Optional[float] = None
    detected_tax_pct: Optional[float] = None
    sell_simulation_passed: Optional[bool] = None
    estimated_price_impact_pct: Optional[float] = None
    mev_events_count: Optional[int] = None
    avg_slippage_pct: Optional[float] = None
    ws_drops_per_hour: Optional[int] = None
    api_latency_ms: Optional[float] = None
    stale_data_detected: Optional[bool] = None
    volatility_regime_shift: Optional[bool] = None
    spread_pct: Optional[float] = None
    blacklist_signals: Optional[bool] = None
    trading_toggle_risk: Optional[bool] = None
    max_tx_limit: Optional[bool] = None
    max_wallet_limit: Optional[bool] = None
    # Sniper mode config (for Mode B)
    sniper_mode_config: Optional[Dict[str, Any]] = None


class GenerateProfileRequest(BaseModel):
    evaluation_id: str
    strategy_id: str = "sniper"
    label: str = ""
    severity: str = "MED"


@api_router.post("/sniper/hardening/evaluate")
async def evaluate_sniper_hardening(
    request: SniperEvaluationRequest,
    user = Depends(get_current_user)
):
    """
    Evaluate sniper entry conditions and run all hardening gates.
    
    Supports TWO MODES:
    - Mode A: Dedicated Sniper Strategy (mode="dedicated_sniper")
    - Mode B: Sniper Mode for any agent (mode="sniper_mode")
    
    SIMULATION ONLY - no live trading modifications.
    
    Returns gate results, risk scores, decision (ALLOW/WARN/BLOCK), 
    and recommended profile parameters.
    """
    if not sniper_hardening_service:
        raise HTTPException(status_code=503, detail="Sniper hardening service not initialized")
    
    from services.sandbox.sniper_hardening import (
        EvaluationInput, HardeningMode, VenueType, OrderIntent, SniperModeConfig
    )
    
    # Parse mode and venue type
    mode = HardeningMode.DEDICATED_SNIPER if request.mode == "dedicated_sniper" else HardeningMode.SNIPER_MODE
    venue_type = VenueType(request.venue_type) if request.venue_type in ["DEX", "CEX", "SIM_SANDBOX"] else VenueType.SIM_SANDBOX
    
    # Build order intent
    order_intent = OrderIntent(
        side=request.order_side,
        desired_qty=request.desired_qty,
        slippage_tolerance=request.slippage_tolerance,
    )
    
    # Build sniper mode config if provided
    sniper_mode_cfg = None
    if request.sniper_mode_config:
        sniper_mode_cfg = SniperModeConfig(**request.sniper_mode_config)
    
    # Build evaluation input
    input_data = EvaluationInput(
        run_id=request.run_id,
        agent_id=request.agent_id,
        symbol=request.symbol,
        strategy_id=request.strategy_id,
        severity=request.severity,
        packs=request.packs,
        overrides=request.overrides,
        mode=mode,
        venue_type=venue_type,
        order_intent=order_intent,
        sniper_mode_config=sniper_mode_cfg,
        pool_liquidity_usd=request.pool_liquidity_usd,
        trade_size_usd=request.trade_size_usd,
        detected_tax_pct=request.detected_tax_pct,
        sell_simulation_passed=request.sell_simulation_passed,
        estimated_price_impact_pct=request.estimated_price_impact_pct,
        mev_events_count=request.mev_events_count,
        avg_slippage_pct=request.avg_slippage_pct,
        ws_drops_per_hour=request.ws_drops_per_hour,
        api_latency_ms=request.api_latency_ms,
        stale_data_detected=request.stale_data_detected,
        volatility_regime_shift=request.volatility_regime_shift,
        spread_pct=request.spread_pct,
        blacklist_signals=request.blacklist_signals,
        trading_toggle_risk=request.trading_toggle_risk,
        max_tx_limit=request.max_tx_limit,
        max_wallet_limit=request.max_wallet_limit,
    )
    
    # Run evaluation
    evaluation = await sniper_hardening_service.evaluate(input_data)
    
    # Store evaluation result
    await sniper_hardening_service.store_evaluation(evaluation)
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user.get("user_id", user.get("id")),
            username=user.get("username", "unknown"),
            role=user.get("role", "unknown"),
            action=AuditAction.SNIPER_HARDENING_EVALUATE,
            resource_type="sniper_hardening",
            resource_id=evaluation.evaluation_id,
            metadata={
                "run_id": request.run_id,
                "agent_id": request.agent_id,
                "strategy_id": request.strategy_id,
                "symbol": request.symbol,
                "mode": mode.value,
                "decision": evaluation.decision.value,
                "overall_status": evaluation.overall_status.value,
                "risk_score": evaluation.risk_score,
                "mev_risk": evaluation.mev_risk,
                "reason_codes": evaluation.reason_codes,
                "top_failing_gate": evaluation.top_failing_gate,
                "tag": "SIMULATION",
            }
        )
    
    return {
        "evaluation_id": evaluation.evaluation_id,
        "run_id": evaluation.run_id,
        "agent_id": evaluation.agent_id,
        "strategy_id": evaluation.strategy_id,
        "symbol": evaluation.symbol,
        "mode": evaluation.mode.value,
        "venue_type": evaluation.venue_type.value,
        "timestamp": evaluation.timestamp.isoformat(),
        "decision": evaluation.decision.value,
        "overall_status": evaluation.overall_status.value,
        "top_failing_gate": evaluation.top_failing_gate,
        "gates": [
            {
                "name": g.name.value,
                "status": g.status.value,
                "reason_code": g.reason_code,
                "details": g.details,
                "threshold": g.threshold,
                "actual_value": g.actual_value,
            }
            for g in evaluation.gates
        ],
        "passed_count": evaluation.passed_count,
        "failed_count": evaluation.failed_count,
        "warn_count": evaluation.warn_count,
        "risk_score": evaluation.risk_score,
        "mev_risk": evaluation.mev_risk,
        "recommended_position_size_pct": evaluation.recommended_position_size_pct,
        "recommended_profile": evaluation.recommended_profile,
        "suggested_params": evaluation.suggested_params,
        "reason_codes": evaluation.reason_codes,
    }


@api_router.post("/sniper/hardening/generate-profile")
async def generate_hardened_profile(
    request: dict,
    user = Depends(get_current_user)
):
    """
    Generate and persist a hardened sniper profile based on evaluation.
    
    For Mode A (dedicated sniper): saves under params.sniper
    For Mode B (sniper mode): saves under params.sniper_mode
    
    SIMULATION ONLY.
    
    The generated profile can be promoted via the Promotion Flow (paper_live only).
    """
    if not sniper_hardening_service:
        raise HTTPException(status_code=503, detail="Sniper hardening service not initialized")
    
    evaluation_id = request.get("evaluation_id")
    strategy_id = request.get("strategy_id", "sniper")
    label = request.get("label", "")
    severity = request.get("severity", "MED")
    
    if not evaluation_id:
        raise HTTPException(status_code=400, detail="evaluation_id is required")
    
    # Get stored evaluation
    stored_eval = await db.sniper_hardening_evaluations.find_one(
        {"evaluation_id": evaluation_id},
        {"_id": 0}
    )
    
    if not stored_eval:
        raise HTTPException(status_code=404, detail=f"Evaluation {evaluation_id} not found")
    
    # Reconstruct evaluation output
    from services.sandbox.sniper_hardening import (
        EvaluationOutput, GateResult, GateName, GateStatus, 
        HardeningMode, HardeningDecision, VenueType
    )
    
    gates = [
        GateResult(
            name=GateName(g["name"]) if isinstance(g["name"], str) else g["name"],
            status=GateStatus(g["status"]) if isinstance(g["status"], str) else g["status"],
            reason_code=g["reason_code"],
            details=g.get("details", {}),
            threshold=g.get("threshold"),
            actual_value=g.get("actual_value"),
        )
        for g in stored_eval.get("gates", [])
    ]
    
    # Parse mode from stored eval
    stored_mode = stored_eval.get("mode", "dedicated_sniper")
    mode = HardeningMode(stored_mode) if stored_mode in ["dedicated_sniper", "sniper_mode"] else HardeningMode.DEDICATED_SNIPER
    
    # Parse decision
    stored_decision = stored_eval.get("decision", "ALLOW")
    decision = HardeningDecision(stored_decision) if stored_decision in ["ALLOW", "WARN", "BLOCK"] else HardeningDecision.ALLOW
    
    evaluation = EvaluationOutput(
        evaluation_id=stored_eval["evaluation_id"],
        run_id=stored_eval["run_id"],
        agent_id=stored_eval["agent_id"],
        strategy_id=stored_eval.get("strategy_id", "sniper"),
        symbol=stored_eval["symbol"],
        mode=mode,
        decision=decision,
        gates=gates,
        overall_status=GateStatus(stored_eval["overall_status"]) if isinstance(stored_eval["overall_status"], str) else stored_eval["overall_status"],
        passed_count=stored_eval.get("passed_count", 0),
        failed_count=stored_eval.get("failed_count", 0),
        warn_count=stored_eval.get("warn_count", 0),
        risk_score=stored_eval.get("risk_score", 0),
        mev_risk=stored_eval.get("mev_risk", 0),
        recommended_profile=stored_eval.get("recommended_profile"),
        recommended_position_size_pct=stored_eval.get("recommended_position_size_pct", 100),
        reason_codes=stored_eval.get("reason_codes", []),
        top_failing_gate=stored_eval.get("top_failing_gate"),
    )
    
    # Generate profile
    profile = await sniper_hardening_service.generate_hardened_profile(
        evaluation=evaluation,
        strategy_id=strategy_id,
        label=label,
        severity=severity,
    )
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user.get("user_id", user.get("id")),
            username=user.get("username", "unknown"),
            role=user.get("role", "unknown"),
            action=AuditAction.SNIPER_HARDENED_PROFILE_GENERATED,
            resource_type="agent_profile",
            resource_id=profile.profile_id,
            metadata={
                "evaluation_id": evaluation_id,
                "agent_id": profile.agent_id,
                "strategy_id": strategy_id,
                "mode": mode.value,
                "risk_score": profile.risk_score,
                "tags": profile.tags,
                "tag": "SIMULATION",
            }
        )
    
    return {
        "profile_id": profile.profile_id,
        "agent_id": profile.agent_id,
        "strategy_id": profile.strategy_id,
        "mode": mode.value,
        "source_run_id": profile.source_run_id,
        "version": profile.version,
        "tags": profile.tags,
        "params": profile.params,
        "constraints": profile.constraints,
        "dex_rules": profile.dex_rules,
        "infra_rules": profile.infra_rules,
        "evaluation_id": profile.evaluation_id,
        "risk_score": profile.risk_score,
        "created_at": profile.created_at.isoformat(),
    }


@api_router.get("/sniper/hardening/by-run/{run_id}")
async def get_sniper_hardening_by_run(
    run_id: str,
    agent_id: str = None,
    user = Depends(get_current_user)
):
    """
    Get all sniper hardening evaluations for a sandbox run.
    """
    query = {"run_id": run_id}
    if agent_id:
        query["agent_id"] = agent_id
    
    cursor = db.sniper_hardening_evaluations.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1)
    
    evaluations = await cursor.to_list(length=100)
    
    return {
        "run_id": run_id,
        "evaluations": evaluations,
        "count": len(evaluations),
    }


@api_router.get("/sniper/hardening/profiles")
async def get_hardened_profiles(
    agent_id: str = None,
    limit: int = 20,
    user = Depends(get_current_user)
):
    """
    Get all hardened sniper profiles.
    """
    query = {"tags": "sniper_hardened"}
    if agent_id:
        query["agent_id"] = agent_id
    
    cursor = db.agent_profile_versions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    
    profiles = await cursor.to_list(length=limit)
    
    return {"profiles": profiles, "count": len(profiles)}


@api_router.post("/agents/{agent_id}/sniper-mode/toggle")
async def toggle_sniper_mode(
    agent_id: str,
    request: dict,
    user = Depends(get_current_user)
):
    """
    Toggle Sniper Mode for any agent (Mode B).
    
    SIMULATION ONLY - applies to paper trading only.
    
    Body:
        enabled: bool - Enable/disable sniper mode
        overrides: dict - Optional config overrides (min_pool_liquidity_usd, max_tax_pct, etc.)
    """
    from services.sandbox.sniper_hardening import SniperModeConfig
    
    enabled = request.get("enabled", True)
    overrides = request.get("overrides", {})
    
    # Build sniper mode config
    config = SniperModeConfig(enabled=enabled, **overrides)
    
    # Store in agent config
    update_result = await db.agents.update_one(
        {"agent_id": agent_id},
        {
            "$set": {
                "sniper_mode_enabled": enabled,
                "sniper_mode_config": config.model_dump(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True
    )
    
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user.get("user_id", user.get("id")),
            username=user.get("username", "unknown"),
            role=user.get("role", "unknown"),
            action=AuditAction.SNIPER_MODE_TOGGLE,
            resource_type="agent",
            resource_id=agent_id,
            metadata={
                "enabled": enabled,
                "overrides": overrides,
                "tag": "SIMULATION",
            }
        )
    
    logger.info(f"[SIMULATION] Sniper mode {'enabled' if enabled else 'disabled'} for agent {agent_id}")
    
    return {
        "agent_id": agent_id,
        "sniper_mode_enabled": enabled,
        "sniper_mode_config": config.model_dump(),
        "message": f"Sniper mode {'enabled' if enabled else 'disabled'} for agent {agent_id}",
    }


@api_router.get("/agents/{agent_id}/sniper-mode")
async def get_sniper_mode_status(
    agent_id: str,
    user = Depends(get_current_user)
):
    """
    Get sniper mode status for an agent.
    """
    agent = await db.agents.find_one(
        {"agent_id": agent_id},
        {"_id": 0, "sniper_mode_enabled": 1, "sniper_mode_config": 1}
    )
    
    if not agent:
        return {
            "agent_id": agent_id,
            "sniper_mode_enabled": False,
            "sniper_mode_config": None,
        }
    
    return {
        "agent_id": agent_id,
        "sniper_mode_enabled": agent.get("sniper_mode_enabled", False),
        "sniper_mode_config": agent.get("sniper_mode_config"),
    }


# ============================================================
# ANALYTICS ENDPOINTS (READ-ONLY)
# ============================================================


@api_router.get("/analytics/sandbox")
async def get_sandbox_analytics(
    days: int = 30,
    user = Depends(require_auth)
):
    """
    Get sandbox analytics for observability dashboard.
    READ-ONLY - No modifications to data.
    
    Returns:
        - Historical survival scores
        - Max drawdown by run
        - Time-to-stabilize per scenario
        - Runs grouped by severity
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    
    return await analytics_service.get_sandbox_analytics(days=days)


@api_router.get("/analytics/guardian")
async def get_guardian_analytics(
    days: int = 30,
    user = Depends(require_auth)
):
    """
    Get guardian analytics for observability dashboard.
    READ-ONLY - No modifications to data.
    
    Returns:
        - Total blocked trades
        - Top block reasons
        - WARN vs BLOCK ratio
        - Guardian HALT count
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    
    return await analytics_service.get_guardian_analytics(days=days)


@api_router.get("/analytics/sniper")
async def get_sniper_analytics(
    days: int = 30,
    user = Depends(require_auth)
):
    """
    Get sniper hardening analytics for observability dashboard.
    READ-ONLY - No modifications to data.
    
    Returns:
        - % of sniper attempts blocked
        - Top failing gates
        - MEV risk distribution
        - Average suggested size reduction
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    
    return await analytics_service.get_sniper_analytics(days=days)


@api_router.get("/analytics/promotions")
async def get_promotions_analytics(
    days: int = 30,
    user = Depends(require_auth)
):
    """
    Get promotions analytics for observability dashboard.
    READ-ONLY - No modifications to data.
    
    Returns:
        - Profiles promoted to paper_live
        - Rejected promotions count
        - Average improvement vs previous profile
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    
    return await analytics_service.get_promotions_analytics(days=days)


@api_router.get("/analytics/all")
async def get_all_analytics(
    days: int = 30,
    user = Depends(require_auth)
):
    """
    Get all analytics combined for dashboard.
    READ-ONLY - No modifications to data.
    
    Returns all analytics in a single response for efficient loading.
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Analytics service not available")
    
    return await analytics_service.get_all_analytics(days=days)


# ============================================================
# END SANDBOX ENDPOINTS
# ============================================================


# ============================================================
# DEX COMPATIBILITY LAYER (SIMULATION ONLY)
# ============================================================
# These endpoints exist for frontend compatibility.
# All DEX functionality is DISABLED in production.
# Use Sandbox/Sniper Hardening for simulated token evaluation.

@api_router.get("/dex/status")
async def get_dex_status(user = Depends(get_current_user)):
    """
    Get DEX status - SIMULATION ONLY.
    Real DEX trading is disabled. Use Sandbox for simulations.
    """
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user.get("id", "unknown"),
            username=user.get("username", "unknown"),
            role=user.get("role", "user"),
            action="DEX_STATUS_CHECK",
            resource_type="dex",
            metadata={"tag": "SIMULATION"}
        )
    
    return {
        "mode": "SIMULATION_ONLY",
        "dex_enabled": False,
        "sniper_enabled": False,
        "note": "DEX is disabled in production. Simulation available via Sandbox/Sniper Hardening."
    }

@api_router.get("/dex/pairs/new")
async def get_new_pairs(limit: int = 20, user = Depends(get_current_user)):
    """
    Get new token pairs - SIMULATION ONLY.
    Returns empty list as DEX discovery is disabled.
    """
    return {
        "items": [],
        "note": "DEX discovery disabled. Use Sandbox presets for simulated token discovery."
    }

@api_router.get("/dex/swaps/pending")
async def get_pending_swaps(user = Depends(get_current_user)):
    """Get pending swaps - SIMULATION ONLY."""
    return {"items": []}

@api_router.get("/dex/positions")
async def get_dex_positions(status: str = "all", limit: int = 20, user = Depends(get_current_user)):
    """Get DEX positions - SIMULATION ONLY."""
    return {"items": []}

@api_router.post("/dex/pairs/scan")
async def scan_pairs(user = Depends(get_current_user)):
    """Scan pairs - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Pair scanning disabled. Use Sandbox for simulated scenarios."
    }

@api_router.post("/dex/sniper/start")
async def start_sniper(user = Depends(get_current_user)):
    """
    Start DEX sniper - SIMULATION ONLY.
    Real sniper is disabled. Use Sniper Hardening for evaluation.
    """
    # Audit log
    if audit_service:
        await audit_service.log(
            user_id=user.get("id", "unknown"),
            username=user.get("username", "unknown"),
            role=user.get("role", "user"),
            action="DEX_SNIPER_START_ATTEMPT",
            resource_type="dex",
            metadata={"tag": "SIMULATION", "result": "disabled"}
        )
    
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Use Sniper Hardening (Sandbox) endpoints to evaluate/generate hardened profiles."
    }

@api_router.post("/dex/sniper/stop")
async def stop_sniper(user = Depends(get_current_user)):
    """Stop DEX sniper - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Sniper is not running. Use Sandbox for simulations."
    }

@api_router.post("/dex/sniper/run-once")
async def run_sniper_once(user = Depends(get_current_user)):
    """Run sniper once - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Use Sniper Hardening evaluation endpoint instead."
    }

@api_router.post("/dex/token/score")
async def score_token(request: Request, user = Depends(get_current_user)):
    """Score a token - SIMULATION ONLY."""
    body = await request.json()
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "token": body.get("token", ""),
        "note": "Token scoring disabled. Use Sniper Hardening for token evaluation."
    }

@api_router.post("/dex/swap/plan")
async def create_swap_plan(request: Request, user = Depends(get_current_user)):
    """Create swap plan - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Swap creation disabled in production."
    }

@api_router.post("/dex/swap/{plan_id}/approve")
async def approve_swap(plan_id: str, user = Depends(get_current_user)):
    """Approve swap - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Swap approval disabled in production."
    }

@api_router.post("/dex/swap/{plan_id}/reject")
async def reject_swap(plan_id: str, request: Request, user = Depends(get_current_user)):
    """Reject swap - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY"
    }

@api_router.post("/dex/swap/{plan_id}/simulate")
async def simulate_swap(plan_id: str, user = Depends(get_current_user)):
    """Simulate swap - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "note": "Use Sandbox for swap simulations."
    }

@api_router.post("/dex/tx/submitted")
async def mark_tx_submitted(request: Request, user = Depends(get_current_user)):
    """Mark TX submitted - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY"
    }

@api_router.get("/dex/position/{position_id}/sell-tx")
async def get_sell_tx(position_id: str, wallet_address: str = "", user = Depends(get_current_user)):
    """Get sell TX - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "tx_data": None
    }

@api_router.post("/dex/position/{position_id}/close")
async def close_position(position_id: str, request: Request, user = Depends(get_current_user)):
    """Close position - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY"
    }

@api_router.get("/dex/tx/monitor/{tx_hash}")
async def monitor_tx(tx_hash: str, user = Depends(get_current_user)):
    """Monitor TX - SIMULATION ONLY."""
    return {
        "status": "disabled",
        "mode": "SIMULATION_ONLY",
        "tx_hash": tx_hash
    }


# ============================================================
# END DEX ENDPOINTS
# ============================================================


# Include router
app.include_router(api_router)
