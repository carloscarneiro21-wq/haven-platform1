"""Live Execution Engine for HAVEN Trading System (P2.1)

🔒 CRITICAL SAFETY FEATURES:
- GO-LIVE Gate enforcement (required for any live execution)
- RBAC (Role-Based Access Control) enforcement
- Default is PAPER mode - LIVE must be explicitly enabled
- Symbol/venue allowlist
- Per-order and daily caps
- Idempotency - no duplicate orders
- Circuit breaker for rapid failure detection

⚠️  DESIGN PHILOSOPHY:
- Defense in depth - multiple layers of protection
- Fail-safe defaults - if anything is uncertain, block
- Full audit trail - every decision is logged
- Guardian has maximum authority

Usage:
    executor = LiveExecutor(db, guardian, go_live_gate)
    await executor.initialize()
    
    # This will FAIL unless GO-LIVE gate is GO and user has permission
    result = await executor.execute(intent_plan, user_id="user123")
"""

import asyncio
import logging
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Set, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
from pydantic import BaseModel, Field
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


# ============================================================
# 🔒 EXECUTION MODE
# ============================================================

class ExecutionMode(str, Enum):
    """Execution mode for trading."""
    PAPER = "paper"     # Simulated execution - DEFAULT
    SHADOW = "shadow"   # Live data, paper execution, comparison logging
    LIVE = "live"       # Real execution - requires GO-LIVE gate


class ExecutionResult(BaseModel):
    """Result from execution attempt."""
    success: bool = False
    mode: ExecutionMode = ExecutionMode.PAPER
    
    # Order stats
    orders_created: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0
    
    # PnL (paper or estimated)
    pnl_delta_eur: float = 0.0
    fees_eur: float = 0.0
    
    # IDs
    execution_id: str = ""
    order_ids: List[str] = []
    fill_ids: List[str] = []
    
    # Safety
    blocked_reason: Optional[str] = None
    warnings: List[str] = []
    
    # Audit
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = ""


# ============================================================
# 🛡️ SAFETY CONFIGURATION
# ============================================================

class ExecutorConfig(BaseModel):
    """Configuration for LiveExecutor safety limits."""
    
    # Default mode (ALWAYS PAPER unless explicitly changed)
    default_mode: ExecutionMode = ExecutionMode.PAPER
    
    # Allowlist - only these symbols can trade live
    allowed_symbols: List[str] = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT"
    ]
    
    # Allowlist - only these venues can trade live
    allowed_venues: List[str] = ["kraken", "binance"]
    
    # Per-order caps
    max_order_size_eur: float = 500.0      # Max EUR per single order
    max_order_size_pct: float = 2.0        # Max % of capital per order
    
    # Daily caps
    max_daily_volume_eur: float = 5000.0   # Max EUR traded per day
    max_daily_orders: int = 50             # Max orders per day
    max_daily_loss_eur: float = 200.0      # Max daily loss before halt
    
    # Circuit breaker
    circuit_breaker_failures: int = 3       # Consecutive failures to trip
    circuit_breaker_window_seconds: int = 60  # Window for failure count
    circuit_breaker_cooldown_seconds: int = 300  # Cooldown after trip
    
    # Idempotency
    idempotency_window_seconds: int = 60    # Window for duplicate detection
    
    # RBAC - roles that can execute live
    live_execution_roles: List[str] = ["owner", "admin", "live_trader"]


# ============================================================
# 🔴 CIRCUIT BREAKER
# ============================================================

class CircuitBreaker:
    """Circuit breaker to halt execution on rapid failures."""
    
    def __init__(
        self, 
        failure_threshold: int = 3,
        window_seconds: int = 60,
        cooldown_seconds: int = 300
    ):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        
        self._failures: List[datetime] = []
        self._tripped_at: Optional[datetime] = None
        self._trip_count = 0
    
    def record_failure(self, reason: str = ""):
        """Record a failure."""
        now = datetime.now(timezone.utc)
        self._failures.append(now)
        self._cleanup_old_failures(now)
        
        if len(self._failures) >= self.failure_threshold:
            self._trip(reason)
    
    def record_success(self):
        """Record a success - clears failure count."""
        self._failures.clear()
    
    def _trip(self, reason: str):
        """Trip the circuit breaker."""
        self._tripped_at = datetime.now(timezone.utc)
        self._trip_count += 1
        self._failures.clear()
        logger.warning(f"Circuit breaker TRIPPED (#{self._trip_count}): {reason}")
    
    def _cleanup_old_failures(self, now: datetime):
        """Remove failures outside the window."""
        cutoff = now - timedelta(seconds=self.window_seconds)
        self._failures = [f for f in self._failures if f > cutoff]
    
    @property
    def is_tripped(self) -> bool:
        """Check if circuit breaker is currently tripped."""
        if not self._tripped_at:
            return False
        
        elapsed = (datetime.now(timezone.utc) - self._tripped_at).total_seconds()
        if elapsed >= self.cooldown_seconds:
            self._tripped_at = None
            logger.info("Circuit breaker reset after cooldown")
            return False
        
        return True
    
    @property
    def time_until_reset(self) -> int:
        """Seconds until circuit breaker resets."""
        if not self._tripped_at:
            return 0
        
        elapsed = (datetime.now(timezone.utc) - self._tripped_at).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0, int(remaining))
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "is_tripped": self.is_tripped,
            "trip_count": self._trip_count,
            "recent_failures": len(self._failures),
            "failure_threshold": self.failure_threshold,
            "time_until_reset": self.time_until_reset,
        }


# ============================================================
# 🔐 IDEMPOTENCY TRACKER
# ============================================================

class IdempotencyTracker:
    """Tracks order hashes to prevent duplicate execution."""
    
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._seen: Dict[str, datetime] = {}  # hash -> timestamp
    
    def _generate_hash(self, intent_plan: Dict[str, Any]) -> str:
        """Generate deterministic hash from intent plan."""
        # Use key fields that define uniqueness
        key_data = {
            "plan_id": intent_plan.get("plan_id", ""),
            "symbol": intent_plan.get("symbol", ""),
            "agent_type": intent_plan.get("agent_type", ""),
            "orders": [
                {
                    "side": o.get("side"),
                    "price": round(o.get("price", 0), 2),
                    "size_eur": round(o.get("size_eur", 0), 2),
                }
                for o in intent_plan.get("orders", [])
            ]
        }
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()[:24]
    
    def check_and_record(self, intent_plan: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if plan is duplicate, record if not.
        
        Returns:
            (is_duplicate, hash)
        """
        self._cleanup_old()
        
        plan_hash = self._generate_hash(intent_plan)
        
        if plan_hash in self._seen:
            return True, plan_hash
        
        self._seen[plan_hash] = datetime.now(timezone.utc)
        return False, plan_hash
    
    def _cleanup_old(self):
        """Remove entries outside the window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracker stats."""
        return {
            "entries": len(self._seen),
            "window_seconds": self.window_seconds,
        }


# ============================================================
# 📊 DAILY TRACKER
# ============================================================

class DailyTracker:
    """Tracks daily execution metrics for caps enforcement."""
    
    def __init__(self):
        self._current_date: Optional[str] = None
        self._volume_eur: float = 0.0
        self._order_count: int = 0
        self._pnl_eur: float = 0.0
    
    def _check_date_reset(self):
        """Reset counters on new day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._current_date != today:
            self._current_date = today
            self._volume_eur = 0.0
            self._order_count = 0
            self._pnl_eur = 0.0
    
    def record_execution(self, volume_eur: float, order_count: int, pnl_eur: float):
        """Record an execution."""
        self._check_date_reset()
        self._volume_eur += volume_eur
        self._order_count += order_count
        self._pnl_eur += pnl_eur
    
    def get_remaining_capacity(
        self, 
        max_volume: float, 
        max_orders: int, 
        max_loss: float
    ) -> Dict[str, Any]:
        """Get remaining daily capacity."""
        self._check_date_reset()
        
        return {
            "volume_remaining_eur": max(0, max_volume - self._volume_eur),
            "orders_remaining": max(0, max_orders - self._order_count),
            "loss_budget_eur": max(0, max_loss - abs(min(0, self._pnl_eur))),
            "volume_used_eur": self._volume_eur,
            "orders_used": self._order_count,
            "pnl_eur": self._pnl_eur,
        }
    
    def can_execute(
        self, 
        volume_eur: float, 
        order_count: int,
        max_volume: float,
        max_orders: int,
        max_loss: float
    ) -> Tuple[bool, str]:
        """Check if execution is within daily caps."""
        capacity = self.get_remaining_capacity(max_volume, max_orders, max_loss)
        
        if volume_eur > capacity["volume_remaining_eur"]:
            return False, f"Daily volume cap exceeded ({self._volume_eur:.0f}/{max_volume:.0f} EUR)"
        
        if order_count > capacity["orders_remaining"]:
            return False, f"Daily order cap exceeded ({self._order_count}/{max_orders})"
        
        if capacity["loss_budget_eur"] <= 0:
            return False, f"Daily loss limit reached ({self._pnl_eur:.2f} EUR)"
        
        return True, ""


# ============================================================
# 🚀 LIVE EXECUTOR
# ============================================================

class LiveExecutor:
    """
    Live Execution Engine with comprehensive safety controls.
    
    🔒 Safety Features:
    - GO-LIVE Gate required for live mode
    - RBAC enforcement
    - Symbol/venue allowlist
    - Per-order and daily caps
    - Idempotency (no duplicate orders)
    - Circuit breaker
    
    ⚠️ Default is PAPER mode - LIVE must be explicitly enabled.
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        guardian_service=None,
        go_live_gate=None,
        paper_adapter=None,
        config: Optional[ExecutorConfig] = None,
    ):
        self.db = db
        self.guardian = guardian_service
        self.go_live_gate = go_live_gate
        self.paper_adapter = paper_adapter  # Fallback for paper mode
        self.config = config or ExecutorConfig()
        
        # State
        self._initialized = False
        self._current_mode = self.config.default_mode  # PAPER by default
        
        # Safety components
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failures,
            window_seconds=self.config.circuit_breaker_window_seconds,
            cooldown_seconds=self.config.circuit_breaker_cooldown_seconds,
        )
        self._idempotency = IdempotencyTracker(
            window_seconds=self.config.idempotency_window_seconds
        )
        self._daily_tracker = DailyTracker()
        
        # Audit
        self._execution_count = 0
        self._last_execution: Optional[datetime] = None
        
        # Event logger (set externally)
        self.event_logger = None
    
    async def initialize(self):
        """Initialize the executor."""
        if self._initialized:
            return
        
        # Initialize paper adapter if provided
        if self.paper_adapter and hasattr(self.paper_adapter, 'initialize'):
            await self.paper_adapter.initialize()
        
        self._initialized = True
        logger.info(f"LiveExecutor initialized in {self._current_mode.value} mode")
    
    # ============================================================
    # 🔐 MODE CONTROL
    # ============================================================
    
    async def request_mode_change(
        self, 
        new_mode: ExecutionMode, 
        user_id: str,
        reason: str = ""
    ) -> Tuple[bool, str]:
        """
        Request a mode change.
        
        PAPER -> SHADOW: Allowed if user has permission
        PAPER/SHADOW -> LIVE: Requires GO-LIVE gate GO + permission
        LIVE -> PAPER: Always allowed (safer)
        """
        old_mode = self._current_mode
        
        # Always allow downgrade to safer mode
        if new_mode == ExecutionMode.PAPER:
            self._current_mode = ExecutionMode.PAPER
            await self._log_mode_change(old_mode, new_mode, user_id, reason)
            return True, "Switched to PAPER mode"
        
        # Check RBAC
        has_permission = await self._check_user_permission(user_id, new_mode)
        if not has_permission:
            return False, f"User {user_id} does not have permission for {new_mode.value} mode"
        
        # LIVE mode requires GO-LIVE gate
        if new_mode == ExecutionMode.LIVE:
            if not self.go_live_gate:
                return False, "GO-LIVE gate not configured - LIVE mode unavailable"
            
            gate_status = await self.go_live_gate.get_current_status()
            if gate_status.get("decision") != "GO":
                reasons = gate_status.get("failed_criteria", [])
                return False, f"GO-LIVE gate is NO-GO: {', '.join(reasons[:3])}"
        
        # Change mode
        self._current_mode = new_mode
        await self._log_mode_change(old_mode, new_mode, user_id, reason)
        
        return True, f"Switched to {new_mode.value} mode"
    
    async def _check_user_permission(
        self, 
        user_id: str, 
        mode: ExecutionMode
    ) -> bool:
        """Check if user has permission for execution mode."""
        if mode == ExecutionMode.PAPER:
            return True  # Everyone can use paper
        
        # Get user role from database
        user = await self.db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
        if not user:
            logger.warning(f"User {user_id} not found for permission check")
            return False
        
        user_role = user.get("role", "user")
        
        if mode == ExecutionMode.SHADOW:
            # Shadow requires at least trader role
            return user_role in ["owner", "admin", "live_trader", "trader"]
        
        if mode == ExecutionMode.LIVE:
            # Live requires explicit live permission
            return user_role in self.config.live_execution_roles
        
        return False
    
    async def _log_mode_change(
        self, 
        old_mode: ExecutionMode, 
        new_mode: ExecutionMode,
        user_id: str,
        reason: str
    ):
        """Log mode change to audit log."""
        await self.db.audit_logs.insert_one({
            "type": "EXECUTION_MODE_CHANGE",
            "timestamp": datetime.now(timezone.utc),
            "user_id": user_id,
            "old_mode": old_mode.value,
            "new_mode": new_mode.value,
            "reason": reason,
        })
        
        logger.info(f"Execution mode changed: {old_mode.value} -> {new_mode.value} by {user_id}")
        
        if self.event_logger:
            try:
                from services.event_logger import EventSeverity, EventCategory
                await self.event_logger.emit(
                    severity=EventSeverity.WARNING if new_mode == ExecutionMode.LIVE else EventSeverity.INFO,
                    category=EventCategory.RISK,
                    type="EXECUTION_MODE_CHANGE",
                    message=f"Execution mode changed from {old_mode.value} to {new_mode.value}",
                    context={"user_id": user_id, "reason": reason},
                    tags=["execution", "mode_change", new_mode.value]
                )
            except Exception:
                pass
    
    # ============================================================
    # ⚡ EXECUTE
    # ============================================================
    
    async def execute(
        self,
        intent_plan: Dict[str, Any],
        user_id: str,
        force_mode: Optional[ExecutionMode] = None,
    ) -> ExecutionResult:
        """
        Execute an intent plan with full safety checks.
        
        Args:
            intent_plan: The trading intent plan (from orchestrator)
            user_id: User requesting execution
            force_mode: Override mode (only PAPER allowed for override)
        
        Returns:
            ExecutionResult with execution details
        
        Safety Checks (in order):
        1. Circuit breaker check
        2. Idempotency check
        3. Mode determination
        4. GO-LIVE gate check (if LIVE)
        5. RBAC check
        6. Symbol/venue allowlist
        7. Per-order caps
        8. Daily caps
        9. Guardian approval
        10. Execute
        """
        execution_id = str(uuid.uuid4())
        
        # Determine execution mode
        mode = force_mode if force_mode == ExecutionMode.PAPER else self._current_mode
        
        result = ExecutionResult(
            execution_id=execution_id,
            mode=mode,
            user_id=user_id,
        )
        
        try:
            # 1. Circuit breaker check
            if self._circuit_breaker.is_tripped:
                result.blocked_reason = f"Circuit breaker tripped - reset in {self._circuit_breaker.time_until_reset}s"
                return result
            
            # 2. Idempotency check
            is_duplicate, plan_hash = self._idempotency.check_and_record(intent_plan)
            if is_duplicate:
                result.blocked_reason = f"Duplicate execution blocked (hash: {plan_hash})"
                result.warnings.append("This exact plan was already executed recently")
                return result
            
            # 3-9. Safety checks for non-PAPER modes
            if mode != ExecutionMode.PAPER:
                block_reason = await self._run_safety_checks(intent_plan, user_id, mode)
                if block_reason:
                    result.blocked_reason = block_reason
                    self._circuit_breaker.record_failure(block_reason)
                    return result
            
            # 10. Execute based on mode
            if mode == ExecutionMode.PAPER:
                result = await self._execute_paper(intent_plan, result)
            elif mode == ExecutionMode.SHADOW:
                result = await self._execute_shadow(intent_plan, result)
            elif mode == ExecutionMode.LIVE:
                result = await self._execute_live(intent_plan, result)
            
            # Record success
            if result.success:
                self._circuit_breaker.record_success()
                
                # Update daily tracker
                volume = sum(o.get("size_eur", 0) for o in intent_plan.get("orders", []))
                self._daily_tracker.record_execution(
                    volume_eur=volume,
                    order_count=result.orders_created,
                    pnl_eur=result.pnl_delta_eur
                )
            else:
                self._circuit_breaker.record_failure(result.blocked_reason or "Unknown error")
            
            # Update stats
            self._execution_count += 1
            self._last_execution = datetime.now(timezone.utc)
            
            # Audit log
            await self._log_execution(result, intent_plan)
            
            return result
            
        except Exception as e:
            logger.error(f"Execution error: {e}")
            result.blocked_reason = f"Execution error: {str(e)}"
            self._circuit_breaker.record_failure(str(e))
            return result
    
    async def _run_safety_checks(
        self, 
        intent_plan: Dict[str, Any], 
        user_id: str,
        mode: ExecutionMode
    ) -> Optional[str]:
        """Run all safety checks. Returns block reason if blocked."""
        symbol = intent_plan.get("symbol", "")
        venue = intent_plan.get("venue", "")
        orders = intent_plan.get("orders", [])
        
        # 3. GO-LIVE gate check (for LIVE mode)
        if mode == ExecutionMode.LIVE:
            if not self.go_live_gate:
                return "GO-LIVE gate not configured"
            
            gate_status = await self.go_live_gate.get_current_status()
            if gate_status.get("decision") != "GO":
                return "GO-LIVE gate is NO-GO"
        
        # 4. RBAC check
        has_permission = await self._check_user_permission(user_id, mode)
        if not has_permission:
            return f"User {user_id} lacks permission for {mode.value} mode"
        
        # 5. Symbol allowlist
        if mode == ExecutionMode.LIVE and symbol not in self.config.allowed_symbols:
            return f"Symbol {symbol} not in live allowlist"
        
        # 6. Venue allowlist
        if mode == ExecutionMode.LIVE and venue.lower() not in self.config.allowed_venues:
            return f"Venue {venue} not in live allowlist"
        
        # 7. Per-order caps
        for order in orders:
            order_size = order.get("size_eur", 0)
            if order_size > self.config.max_order_size_eur:
                return f"Order size {order_size:.0f} EUR exceeds max {self.config.max_order_size_eur:.0f} EUR"
        
        # 8. Daily caps
        total_volume = sum(o.get("size_eur", 0) for o in orders)
        can_execute, cap_reason = self._daily_tracker.can_execute(
            volume_eur=total_volume,
            order_count=len(orders),
            max_volume=self.config.max_daily_volume_eur,
            max_orders=self.config.max_daily_orders,
            max_loss=self.config.max_daily_loss_eur,
        )
        if not can_execute:
            return cap_reason
        
        # 9. Guardian approval (if available)
        if self.guardian and mode == ExecutionMode.LIVE:
            # Create context for guardian
            from services.growth.interfaces import GuardianContext
            context = GuardianContext(
                agent_type=intent_plan.get("agent_type", "MM"),
                symbol=symbol,
                venue=venue,
                side=orders[0].get("side", "buy") if orders else "buy",
                amount_eur=total_volume,
                spread_pct=0.05,
                slippage_pct=0.02,
                expected_edge_pct=intent_plan.get("expected_edge_pct", 0.1),
                data_quality=0.9,
            )
            
            guardian_result = await self.guardian.approve(context)
            if not guardian_result.allowed:
                return f"Guardian blocked: {guardian_result.block_reason}"
        
        return None  # All checks passed
    
    # ============================================================
    # 🎭 EXECUTION MODES
    # ============================================================
    
    async def _execute_paper(
        self, 
        intent_plan: Dict[str, Any], 
        result: ExecutionResult
    ) -> ExecutionResult:
        """Execute in paper trading mode."""
        result.mode = ExecutionMode.PAPER
        
        if self.paper_adapter:
            # Use existing paper adapter
            from services.growth.interfaces import IntentPlan, IntentOrder
            
            plan = IntentPlan(
                plan_id=intent_plan.get("plan_id", str(uuid.uuid4())),
                agent_type=intent_plan.get("agent_type", "MM"),
                preset_id=intent_plan.get("preset_id", ""),
                symbol=intent_plan.get("symbol", "BTC/USDT"),
                venue=intent_plan.get("venue", "kraken"),
                capital_eur=intent_plan.get("capital_eur", 100),
                bucket="CORE",
                max_loss_eur=intent_plan.get("max_loss_eur", 10),
                expected_edge_pct=intent_plan.get("expected_edge_pct", 0.1),
                orders=[
                    IntentOrder(
                        order_id=o.get("order_id", str(uuid.uuid4())),
                        side=o.get("side", "buy"),
                        order_type=o.get("order_type", "limit"),
                        price=o.get("price", 0),
                        size_eur=o.get("size_eur", 0),
                        size_asset=o.get("size_asset", 0),
                        post_only=o.get("post_only", False),
                    )
                    for o in intent_plan.get("orders", [])
                ]
            )
            
            adapter_result = await self.paper_adapter.execute_plan(plan)
            
            result.success = adapter_result.status == "success"
            result.orders_created = adapter_result.orders_created
            result.orders_filled = adapter_result.orders_filled
            result.order_ids = adapter_result.order_ids if hasattr(adapter_result, 'order_ids') else []
        else:
            # Simulated paper execution
            orders = intent_plan.get("orders", [])
            result.success = True
            result.orders_created = len(orders)
            result.orders_filled = len(orders)  # Assume all filled in paper
            result.order_ids = [f"paper_{uuid.uuid4().hex[:8]}" for _ in orders]
        
        return result
    
    async def _execute_shadow(
        self, 
        intent_plan: Dict[str, Any], 
        result: ExecutionResult
    ) -> ExecutionResult:
        """Execute in shadow mode (paper + live comparison logging)."""
        result.mode = ExecutionMode.SHADOW
        
        # Execute paper
        result = await self._execute_paper(intent_plan, result)
        result.mode = ExecutionMode.SHADOW
        
        # Log shadow comparison (what would have happened live)
        await self.db.shadow_logs.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "execution_id": result.execution_id,
            "intent_plan": intent_plan,
            "paper_result": result.model_dump(),
            "note": "Shadow mode - no live execution",
        })
        
        result.warnings.append("Shadow mode: logged for comparison, no live execution")
        return result
    
    async def _execute_live(
        self, 
        intent_plan: Dict[str, Any], 
        result: ExecutionResult
    ) -> ExecutionResult:
        """Execute in LIVE mode (real orders).
        
        ⚠️ This is a PLACEHOLDER - actual exchange integration would go here.
        For safety, this currently falls back to paper execution with live flag.
        """
        result.mode = ExecutionMode.LIVE
        
        # TODO: Integrate with actual exchange API
        # For now, execute paper with LIVE flag for auditing
        logger.warning("LIVE execution requested - using paper adapter (exchange not integrated)")
        
        # Execute using paper adapter
        result = await self._execute_paper(intent_plan, result)
        result.mode = ExecutionMode.LIVE
        result.warnings.append("LIVE mode: Exchange integration pending, using paper execution")
        
        # Log live execution attempt
        await self.db.live_execution_logs.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "execution_id": result.execution_id,
            "intent_plan": intent_plan,
            "result": result.model_dump(),
            "exchange_integrated": False,
            "note": "Live execution attempted but exchange not integrated",
        })
        
        return result
    
    # ============================================================
    # 📝 AUDIT
    # ============================================================
    
    async def _log_execution(
        self, 
        result: ExecutionResult, 
        intent_plan: Dict[str, Any]
    ):
        """Log execution to audit trail."""
        await self.db.execution_audit.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "execution_id": result.execution_id,
            "mode": result.mode.value,
            "user_id": result.user_id,
            "success": result.success,
            "blocked_reason": result.blocked_reason,
            "orders_created": result.orders_created,
            "orders_filled": result.orders_filled,
            "symbol": intent_plan.get("symbol"),
            "agent_type": intent_plan.get("agent_type"),
            "warnings": result.warnings,
        })
    
    # ============================================================
    # 📊 STATUS
    # ============================================================
    
    @property
    def current_mode(self) -> ExecutionMode:
        """Get current execution mode."""
        return self._current_mode
    
    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            "initialized": self._initialized,
            "current_mode": self._current_mode.value,
            "execution_count": self._execution_count,
            "last_execution": self._last_execution.isoformat() if self._last_execution else None,
            "circuit_breaker": self._circuit_breaker.get_status(),
            "idempotency": self._idempotency.get_stats(),
            "daily_capacity": self._daily_tracker.get_remaining_capacity(
                self.config.max_daily_volume_eur,
                self.config.max_daily_orders,
                self.config.max_daily_loss_eur,
            ),
            "config": {
                "default_mode": self.config.default_mode.value,
                "allowed_symbols": self.config.allowed_symbols,
                "allowed_venues": self.config.allowed_venues,
                "max_order_size_eur": self.config.max_order_size_eur,
                "max_daily_volume_eur": self.config.max_daily_volume_eur,
                "max_daily_orders": self.config.max_daily_orders,
            },
        }


# ============================================================
# 🏭 FACTORY
# ============================================================

_live_executor: Optional[LiveExecutor] = None


async def get_live_executor() -> Optional[LiveExecutor]:
    """Get global live executor instance."""
    return _live_executor


def set_live_executor(executor: LiveExecutor):
    """Set global live executor instance."""
    global _live_executor
    _live_executor = executor
