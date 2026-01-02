"""
Guardian Service for Capital Growth Module
==========================================

Non-trading risk enforcement service that:
1. Enforces daily/weekly loss limits (kill switches)
2. Blocks trades when conditions are unsafe
3. Validates pre-order safety
4. Logs all block decisions

Must run BEFORE any order is placed.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Import event enums lazily
def _get_event_enums():
    """Get event enums, importing lazily."""
    try:
        from services.event_logger import EventSeverity, EventCategory
        return EventSeverity, EventCategory
    except ImportError:
        return None, None


# ============ Enums ============

class GuardianAction(str, Enum):
    """Guardian decision actions."""
    ALLOW = "ALLOW"           # Trade allowed
    BLOCK = "BLOCK"           # Trade blocked
    WARN = "WARN"             # Allow but with warning
    KILL_SWITCH = "KILL_SWITCH"  # System-wide pause


class BlockReason(str, Enum):
    """Reasons for blocking a trade."""
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    WEEKLY_DRAWDOWN = "WEEKLY_DRAWDOWN"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_HIGH = "SLIPPAGE_HIGH"
    DATA_STALE = "DATA_STALE"
    LATENCY_HIGH = "LATENCY_HIGH"
    VIABILITY_FAILED = "VIABILITY_FAILED"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    AGENT_PAUSED = "AGENT_PAUSED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    SPREAD_WIDENING = "SPREAD_WIDENING"


# ============ Reason Code Messages ============

GUARDIAN_REASONS = {
    BlockReason.DAILY_LOSS_LIMIT: "Daily loss limit hit: {current_pct:.2f}% (limit: {limit_pct:.2f}%)",
    BlockReason.WEEKLY_DRAWDOWN: "Weekly drawdown exceeded: {current_pct:.2f}% (limit: {limit_pct:.2f}%)",
    BlockReason.SPREAD_TOO_WIDE: "Spread too wide: {spread_pct:.3f}% > {max_pct:.3f}%",
    BlockReason.SLIPPAGE_HIGH: "Expected slippage too high: {slippage_pct:.3f}% > {max_pct:.3f}%",
    BlockReason.DATA_STALE: "Market data stale: {age_seconds:.0f}s old (max: {max_seconds:.0f}s)",
    BlockReason.LATENCY_HIGH: "Data latency too high: quality {quality:.2f} < {min_quality:.2f}",
    BlockReason.VIABILITY_FAILED: "Trade not viable: edge {edge:.4f} < cost {cost:.4f} * {multiplier:.1f}",
    BlockReason.COOLDOWN_ACTIVE: "Cooldown active until {cooldown_end}",
    BlockReason.AGENT_PAUSED: "Agent {agent_id} is paused",
    BlockReason.INSUFFICIENT_BALANCE: "Insufficient balance: {available:.2f}€ < {required:.2f}€",
    BlockReason.CONCURRENCY_LIMIT: "Max concurrent agents reached: {current} >= {max}",
    BlockReason.SPREAD_WIDENING: "Spread widening detected: {current:.3f}% -> {previous:.3f}%",
}


# ============ Models ============

class GuardianState(BaseModel):
    """Current state tracked by Guardian."""
    # Daily tracking
    daily_pnl_eur: float = 0.0
    daily_pnl_pct: float = 0.0
    daily_trades: int = 0
    daily_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=0, minute=0, second=0))
    
    # Weekly tracking
    weekly_pnl_eur: float = 0.0
    weekly_pnl_pct: float = 0.0
    weekly_high_water_mark: float = 0.0
    weekly_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cooldown
    cooldown_until: Optional[datetime] = None
    cooldown_reason: Optional[str] = None
    
    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    kill_switch_activated_at: Optional[datetime] = None
    
    # Spread tracking (for widening detection)
    last_spreads: Dict[str, List[float]] = {}  # symbol -> last N spreads


class GuardianCheck(BaseModel):
    """Result of a Guardian check."""
    action: GuardianAction
    allowed: bool
    reasons: List[str] = []
    block_reason: Optional[BlockReason] = None
    warnings: List[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeRequest(BaseModel):
    """Request to validate a trade."""
    agent_id: str
    agent_type: str  # "MM" or "MOM"
    symbol: str
    venue: str
    side: str  # "buy" or "sell"
    amount_eur: float
    
    # Market conditions
    spread_pct: float
    estimated_slippage_pct: float = 0.0
    data_age_seconds: float = 0.0
    data_quality: float = 1.0
    
    # Viability (from ViabilityService)
    expected_edge_pct: float = 0.0
    total_cost_pct: float = 0.0
    viability_multiplier: float = 2.0


# ============ Guardian Service ============

class GuardianService:
    """
    Risk enforcement service that validates all trades.
    
    Features:
    - Daily/weekly loss limits
    - Spread/slippage validation
    - Data quality checks
    - Cooldown enforcement
    - Kill switch activation
    - Full audit trail
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        system_config_service=None,
        event_logger=None,
    ):
        self.db = db
        self.system_config_service = system_config_service
        self.event_logger = event_logger
        self._state = GuardianState()
        self._initialized = False
    
    async def initialize(self, starting_capital: float) -> None:
        """Initialize Guardian with starting capital."""
        self._state.weekly_high_water_mark = starting_capital
        self._initialized = True
        logger.info(f"Guardian initialized with starting capital: {starting_capital}€")
    
    async def validate_trade(self, request: TradeRequest) -> GuardianCheck:
        """
        Validate a trade request against all safety rules.
        
        Args:
            request: Trade request to validate
        
        Returns:
            GuardianCheck with action and reasons
        """
        check = GuardianCheck(
            action=GuardianAction.ALLOW,
            allowed=True,
        )
        
        # Get config
        config = await self._get_config()
        
        # === Kill Switch Check ===
        if self._state.kill_switch_active:
            check.action = GuardianAction.KILL_SWITCH
            check.allowed = False
            check.block_reason = BlockReason.DAILY_LOSS_LIMIT
            check.reasons.append(
                f"Kill switch active: {self._state.kill_switch_reason}"
            )
            await self._log_block(request, check)
            return check
        
        # === Cooldown Check ===
        if self._state.cooldown_until:
            now = datetime.now(timezone.utc)
            if now < self._state.cooldown_until:
                check.action = GuardianAction.BLOCK
                check.allowed = False
                check.block_reason = BlockReason.COOLDOWN_ACTIVE
                check.reasons.append(
                    GUARDIAN_REASONS[BlockReason.COOLDOWN_ACTIVE].format(
                        cooldown_end=self._state.cooldown_until.isoformat()
                    )
                )
                await self._log_block(request, check)
                return check
            else:
                # Cooldown expired
                self._state.cooldown_until = None
                self._state.cooldown_reason = None
        
        # === Daily Loss Limit ===
        daily_limit = config.get("daily_loss_limit_pct", -2.0)
        if self._state.daily_pnl_pct <= daily_limit:
            check.action = GuardianAction.KILL_SWITCH
            check.allowed = False
            check.block_reason = BlockReason.DAILY_LOSS_LIMIT
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.DAILY_LOSS_LIMIT].format(
                    current_pct=self._state.daily_pnl_pct,
                    limit_pct=daily_limit
                )
            )
            
            # Activate kill switch
            await self._activate_kill_switch(
                BlockReason.DAILY_LOSS_LIMIT.value,
                config.get("cooldown_after_loss_minutes", 30)
            )
            
            await self._log_block(request, check)
            return check
        
        # === Weekly Drawdown Check ===
        weekly_limit = config.get("weekly_drawdown_limit_pct", -5.0)
        if self._state.weekly_pnl_pct <= weekly_limit:
            check.action = GuardianAction.KILL_SWITCH
            check.allowed = False
            check.block_reason = BlockReason.WEEKLY_DRAWDOWN
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.WEEKLY_DRAWDOWN].format(
                    current_pct=self._state.weekly_pnl_pct,
                    limit_pct=weekly_limit
                )
            )
            
            await self._activate_kill_switch(
                BlockReason.WEEKLY_DRAWDOWN.value,
                60  # 1 hour cooldown for weekly
            )
            
            await self._log_block(request, check)
            return check
        
        # === Spread Check ===
        max_spread = config.get("max_spread_pct", 0.15)
        if request.spread_pct > max_spread:
            check.action = GuardianAction.BLOCK
            check.allowed = False
            check.block_reason = BlockReason.SPREAD_TOO_WIDE
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.SPREAD_TOO_WIDE].format(
                    spread_pct=request.spread_pct,
                    max_pct=max_spread
                )
            )
            await self._log_block(request, check)
            return check
        
        # === Slippage Check ===
        max_slippage = config.get("max_slippage_pct", 0.10)
        if request.estimated_slippage_pct > max_slippage:
            check.action = GuardianAction.BLOCK
            check.allowed = False
            check.block_reason = BlockReason.SLIPPAGE_HIGH
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.SLIPPAGE_HIGH].format(
                    slippage_pct=request.estimated_slippage_pct,
                    max_pct=max_slippage
                )
            )
            await self._log_block(request, check)
            return check
        
        # === Data Quality Check ===
        min_quality = config.get("min_latency_quality", 0.8)
        if request.data_quality < min_quality:
            check.action = GuardianAction.BLOCK
            check.allowed = False
            check.block_reason = BlockReason.LATENCY_HIGH
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.LATENCY_HIGH].format(
                    quality=request.data_quality,
                    min_quality=min_quality
                )
            )
            await self._log_block(request, check)
            return check
        
        # === Data Staleness Check ===
        max_data_age = 60  # 60 seconds max
        if request.data_age_seconds > max_data_age:
            check.action = GuardianAction.BLOCK
            check.allowed = False
            check.block_reason = BlockReason.DATA_STALE
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.DATA_STALE].format(
                    age_seconds=request.data_age_seconds,
                    max_seconds=max_data_age
                )
            )
            await self._log_block(request, check)
            return check
        
        # === Viability Check ===
        if request.expected_edge_pct <= request.total_cost_pct * request.viability_multiplier:
            check.action = GuardianAction.BLOCK
            check.allowed = False
            check.block_reason = BlockReason.VIABILITY_FAILED
            check.reasons.append(
                GUARDIAN_REASONS[BlockReason.VIABILITY_FAILED].format(
                    edge=request.expected_edge_pct,
                    cost=request.total_cost_pct,
                    multiplier=request.viability_multiplier
                )
            )
            await self._log_block(request, check)
            return check
        
        # === Spread Widening Check ===
        if config.get("pause_on_spread_widening", True):
            if self._detect_spread_widening(request.symbol, request.spread_pct):
                check.action = GuardianAction.WARN
                check.warnings.append(
                    "Spread widening detected - proceed with caution"
                )
        
        # === All Checks Passed ===
        check.reasons.append("All Guardian checks passed")
        
        # Track spread
        self._track_spread(request.symbol, request.spread_pct)
        
        return check
    
    async def _get_config(self) -> Dict[str, Any]:
        """Get Guardian config from system config."""
        if self.system_config_service:
            config = await self.system_config_service.get_config()
            return config.guardian.model_dump()
        
        # Defaults
        return {
            "daily_loss_limit_pct": -2.0,
            "weekly_drawdown_limit_pct": -5.0,
            "max_spread_pct": 0.15,
            "max_slippage_pct": 0.10,
            "min_latency_quality": 0.8,
            "cooldown_after_loss_minutes": 30,
            "pause_on_spread_widening": True,
        }
    
    async def _activate_kill_switch(self, reason: str, cooldown_minutes: int) -> None:
        """Activate the kill switch."""
        self._state.kill_switch_active = True
        self._state.kill_switch_reason = reason
        self._state.kill_switch_activated_at = datetime.now(timezone.utc)
        self._state.cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)
        
        logger.warning(f"KILL SWITCH ACTIVATED: {reason} (cooldown: {cooldown_minutes}min)")
        
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if EventSeverity and EventCategory:
                await self.event_logger.emit(
                    type="KILL_SWITCH_ACTIVATED",
                    category=EventCategory.SYSTEM,
                    severity=EventSeverity.CRITICAL,
                    message=f"Kill switch activated: {reason}",
                    context={
                        "reason": reason,
                        "cooldown_minutes": cooldown_minutes,
                        "daily_pnl_pct": self._state.daily_pnl_pct,
                        "weekly_pnl_pct": self._state.weekly_pnl_pct,
                    },
                    tags=["guardian", "kill_switch", "critical"]
                )
    
    async def deactivate_kill_switch(self, user_id: str, force: bool = False) -> bool:
        """Manually deactivate kill switch (OWNER only)."""
        if not self._state.kill_switch_active:
            return False
        
        now = datetime.now(timezone.utc)
        
        # Check if cooldown has passed
        if not force and self._state.cooldown_until and now < self._state.cooldown_until:
            return False
        
        self._state.kill_switch_active = False
        self._state.kill_switch_reason = None
        self._state.cooldown_until = None
        
        logger.info(f"Kill switch deactivated by user {user_id}")
        
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if EventSeverity and EventCategory:
                await self.event_logger.emit(
                    type="KILL_SWITCH_DEACTIVATED",
                    category=EventCategory.SYSTEM,
                    severity=EventSeverity.WARNING,
                    message=f"Kill switch deactivated by {user_id}",
                    context={"user_id": user_id, "forced": force},
                    tags=["guardian", "kill_switch"]
                )
        
        return True
    
    def update_pnl(self, pnl_eur: float, current_capital: float) -> None:
        """Update P&L tracking after a trade."""
        self._state.daily_pnl_eur += pnl_eur
        
        # Calculate percentage
        if current_capital > 0:
            self._state.daily_pnl_pct = (self._state.daily_pnl_eur / current_capital) * 100
        
        # Update weekly
        self._state.weekly_pnl_eur += pnl_eur
        if current_capital > 0:
            self._state.weekly_pnl_pct = (self._state.weekly_pnl_eur / self._state.weekly_high_water_mark) * 100
        
        # Update high water mark
        if current_capital > self._state.weekly_high_water_mark:
            self._state.weekly_high_water_mark = current_capital
        
        self._state.daily_trades += 1
        
        logger.debug(f"Guardian P&L updated: daily={self._state.daily_pnl_pct:.2f}%, weekly={self._state.weekly_pnl_pct:.2f}%")
    
    def reset_daily(self) -> None:
        """Reset daily tracking (call at start of trading day)."""
        self._state.daily_pnl_eur = 0.0
        self._state.daily_pnl_pct = 0.0
        self._state.daily_trades = 0
        self._state.daily_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        logger.info("Guardian daily stats reset")
    
    def reset_weekly(self) -> None:
        """Reset weekly tracking (call at start of trading week)."""
        self._state.weekly_pnl_eur = 0.0
        self._state.weekly_pnl_pct = 0.0
        self._state.weekly_start = datetime.now(timezone.utc)
        logger.info("Guardian weekly stats reset")
    
    def _detect_spread_widening(self, symbol: str, current_spread: float) -> bool:
        """Detect if spread is widening."""
        spreads = self._state.last_spreads.get(symbol, [])
        
        if len(spreads) < 3:
            return False
        
        avg_spread = sum(spreads[-5:]) / len(spreads[-5:])
        
        # Widening if current is >50% higher than recent average
        return current_spread > avg_spread * 1.5
    
    def _track_spread(self, symbol: str, spread: float) -> None:
        """Track spread for widening detection."""
        if symbol not in self._state.last_spreads:
            self._state.last_spreads[symbol] = []
        
        self._state.last_spreads[symbol].append(spread)
        
        # Keep last 10
        if len(self._state.last_spreads[symbol]) > 10:
            self._state.last_spreads[symbol] = self._state.last_spreads[symbol][-10:]
    
    async def _log_block(self, request: TradeRequest, check: GuardianCheck) -> None:
        """Log blocked trade to audit."""
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if EventSeverity and EventCategory:
                await self.event_logger.emit(
                    type="TRADE_BLOCKED",
                    category=EventCategory.RISK,
                    severity=EventSeverity.WARNING,
                    message=f"Trade blocked: {request.agent_id} {request.side} {request.symbol}",
                    context={
                        "agent_id": request.agent_id,
                        "agent_type": request.agent_type,
                        "symbol": request.symbol,
                        "venue": request.venue,
                        "side": request.side,
                        "amount_eur": request.amount_eur,
                        "block_reason": check.block_reason.value if check.block_reason else None,
                        "reasons": check.reasons,
                    },
                    tags=["guardian", "blocked", request.agent_type.lower()]
                )
    
    def get_state(self) -> Dict[str, Any]:
        """Get current Guardian state."""
        return {
            "daily_pnl_eur": self._state.daily_pnl_eur,
            "daily_pnl_pct": self._state.daily_pnl_pct,
            "daily_trades": self._state.daily_trades,
            "weekly_pnl_eur": self._state.weekly_pnl_eur,
            "weekly_pnl_pct": self._state.weekly_pnl_pct,
            "weekly_high_water_mark": self._state.weekly_high_water_mark,
            "kill_switch_active": self._state.kill_switch_active,
            "kill_switch_reason": self._state.kill_switch_reason,
            "cooldown_until": self._state.cooldown_until.isoformat() if self._state.cooldown_until else None,
        }
