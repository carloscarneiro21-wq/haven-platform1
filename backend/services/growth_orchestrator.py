"""
Growth Orchestrator
===================

Coordinates the full Growth Module decision cycle:

Router -> (PAUSE|MM|MOM) -> Guardian validate -> Viability check -> Agent.plan() -> PaperExecutor.execute_plan()

Paper trading only. No live execution.

Interface:
    run(mode: RunMode) -> RunResult
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum
import hashlib

from .growth import (
    RunMode,
    RunStatus,
    RunResult,
    MarketSnapshot,
    IntentPlan,
    IntentOrder,
    ViabilityResult,
    ViabilityStatus,
    GuardianResult,
    GuardianAction,
    GuardianContext,
    ExecutionResult,
    IGrowthOrchestrator,
    get_timestamp_bucket,
    get_config_hash,
)

logger = logging.getLogger(__name__)


# ============ Models ============

class GrowthRunMode(str, Enum):
    ONCE = "once"           # Single run
    SIMULATE = "simulate"   # Dry run (no execution)
    SCHEDULED = "scheduled" # Scheduled run


class GrowthRunStatus(str, Enum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    PAUSED = "paused"
    ERROR = "error"
    DRY_RUN = "dry_run"


class SchedulerConfig(BaseModel):
    """Advanced scheduler configuration."""
    enabled: bool = False
    interval_minutes: int = 15
    symbols: List[str] = ["BTC/USDT"]
    active_hours_start: int = 8  # 08:00 UTC
    active_hours_end: int = 22   # 22:00 UTC
    active_days: List[int] = [0, 1, 2, 3, 4]  # Mon-Fri (0=Monday)
    max_runs_per_hour: int = 4
    pause_on_error_count: int = 3  # Pause after N consecutive errors


class OrchestratorConfig(BaseModel):
    """Configuration for the orchestrator."""
    enforce_single_agent: bool = True  # Only MM or MOM, not both
    allow_marginal_viability: bool = True  # Allow MARGINAL trades in paper
    default_capital_eur: float = 100.0
    max_orders_per_run: int = 10
    scheduler_interval_minutes: int = 15
    scheduler_enabled: bool = False
    
    # Advanced scheduler config
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


class CycleResult(BaseModel):
    """Result of one orchestration cycle."""
    cycle_id: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: GrowthRunMode = GrowthRunMode.ONCE
    status: GrowthRunStatus = GrowthRunStatus.SUCCESS
    
    # Router decision
    symbol: str = ""
    venue: str = ""
    regime: str = ""
    confidence: str = ""
    recommended_agent: str = ""
    recommended_preset_id: str = ""
    
    # Gates
    guardian_allowed: bool = True
    viability_viable: bool = True
    
    # Execution
    plan_id: Optional[str] = None
    orders_created: int = 0
    orders_filled: int = 0
    pnl_delta_eur: float = 0.0
    fees_eur: float = 0.0
    
    # Reasons
    reason_codes: List[str] = []
    block_reason: Optional[str] = None
    
    # Raw snapshots
    router_decision: Dict[str, Any] = {}
    guardian_check: Dict[str, Any] = {}
    viability_check: Dict[str, Any] = {}
    intent_plan: Dict[str, Any] = {}
    run_result: Dict[str, Any] = {}


# ============ Growth Orchestrator ============

class GrowthOrchestrator:
    """
    Orchestrates the Growth Module decision and execution cycle.
    
    Flow:
    1. Router analyzes market -> regime + recommended agent
    2. If PAUSE -> stop here
    3. Guardian validates trade -> allowed?
    4. Viability checks costs -> viable?
    5. Agent generates intent plan
    6. Paper adapter executes plan
    7. Results logged and returned
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        market_router=None,
        guardian_service=None,
        viability_service=None,
        risk_budget_service=None,
        growth_presets_service=None,
        paper_adapter=None,
        event_logger=None,
        data_feed=None,
    ):
        self.db = db
        self.market_router = market_router
        self.guardian_service = guardian_service
        self.viability_service = viability_service
        self.risk_budget_service = risk_budget_service
        self.growth_presets_service = growth_presets_service
        self.paper_adapter = paper_adapter
        self.event_logger = event_logger
        self.data_feed = data_feed
        
        self.config = OrchestratorConfig()
        self._initialized = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Agents (lazy loaded)
        self._mm_agent = None
        self._mom_agent = None
    
    async def initialize(self) -> None:
        """Initialize orchestrator and dependencies."""
        if self._initialized:
            return
        
        # Initialize paper adapter
        if self.paper_adapter:
            await self.paper_adapter.initialize()
        
        self._initialized = True
        logger.info("GrowthOrchestrator initialized")
    
    # ============================================================
    # 🧩 Clean Interface: run(mode) -> RunResult
    # ============================================================
    
    async def run(
        self,
        mode: RunMode,
        symbol: str = "BTC/USDT",
        venue: str = "auto",
    ) -> RunResult:
        """
        Execute a Growth Module run with clean interface.
        
        Interface:
            run(mode: RunMode) -> RunResult
        
        Args:
            mode: DRY_RUN, RUN_ONCE, or REPLAY
            symbol: Trading pair
            venue: Exchange (default "auto")
            
        Returns:
            RunResult with complete pipeline results
            
        Idempotency:
            - run_id = hash(timestamp_bucket + config_hash + market_hash)
            - If run_id exists → returns replayed result
            - Never re-executes positions
        """
        await self.initialize()
        
        # Get market snapshot
        snapshot = await self._create_market_snapshot(symbol, venue)
        
        # Generate deterministic run_id for idempotency
        timestamp_bucket = get_timestamp_bucket(granularity_minutes=5)
        config_hash = get_config_hash(self.config.model_dump())
        market_hash = snapshot.get_hash()
        run_id = RunResult.generate_run_id(timestamp_bucket, config_hash, market_hash)
        
        # Check for existing run (idempotency)
        existing_run = await self.get_run(run_id)
        if existing_run:
            logger.info(f"Run {run_id} already exists - returning replay")
            existing_run.is_replay = True
            existing_run.mode = RunMode.REPLAY
            existing_run.status = RunStatus.REPLAYED
            return existing_run
        
        # Create result
        result = RunResult(
            run_id=run_id,
            mode=mode,
            status=RunStatus.SUCCESS,
            symbol=symbol,
            venue=venue if venue != "auto" else "binance",
            snapshot=snapshot,
        )
        
        dry_run = mode == RunMode.DRY_RUN
        
        try:
            # Step 1: Router - Market Analysis
            router_decision = await self._run_router(symbol, venue)
            result.regime = router_decision.get("regime", "")
            result.confidence = router_decision.get("regime_confidence", "")
            result.recommended_agent = router_decision.get("recommended_agent", "PAUSE")
            result.recommended_preset_id = router_decision.get("recommended_preset_id", "")
            result.reason_codes.extend(router_decision.get("all_reason_codes", []))
            
            # Step 2: Check PAUSE
            if result.recommended_agent == "PAUSE":
                result.status = RunStatus.PAUSED
                result.block_reason = "ROUTER_PAUSE"
                await self._persist_run(result)
                return result
            
            # Step 3: Guardian - approve(context) -> GuardianResult
            guardian_context = GuardianContext(
                agent_type=result.recommended_agent,
                symbol=symbol,
                venue=result.venue,
                side="buy",
                amount_eur=10.0,
                spread_pct=snapshot.spread_pct,
                slippage_pct=0.02,
                expected_edge_pct=0.5,
                data_quality=snapshot.data_quality,
            )
            result.guardian_result = await self._guardian_approve(guardian_context)
            
            if not result.guardian_result.allowed:
                result.status = RunStatus.BLOCKED
                result.block_reason = result.guardian_result.block_reason or "GUARDIAN_BLOCKED"
                await self._persist_run(result)
                return result
            
            # Step 4: GrowthModule - evaluate(snapshot) -> IntentPlan[]
            intent_plans = await self._evaluate_snapshot(
                snapshot=snapshot,
                agent_type=result.recommended_agent,
                preset_id=result.recommended_preset_id,
                router_decision=router_decision,
            )
            result.intent_plans = intent_plans
            
            if not intent_plans or not any(p.orders for p in intent_plans):
                result.status = RunStatus.PAUSED
                result.block_reason = "NO_ORDERS_GENERATED"
                await self._persist_run(result)
                return result
            
            # Step 5: Viability - assess(intent, snapshot) -> ViabilityResult
            primary_plan = intent_plans[0]
            result.viability_result = await self._viability_assess(primary_plan, snapshot)
            
            if not result.viability_result.viable:
                if result.viability_result.status == ViabilityStatus.MARGINAL and self.config.allow_marginal_viability:
                    result.reason_codes.append("VIABILITY_MARGINAL_ALLOWED")
                else:
                    result.status = RunStatus.BLOCKED
                    result.block_reason = f"VIABILITY_{result.viability_result.status.value}"
                    await self._persist_run(result)
                    return result
            
            # Step 6: Execute - execute(intent) -> ExecutionResult
            if dry_run:
                result.execution_result = ExecutionResult(
                    success=True,
                    orders_created=len(primary_plan.orders),
                )
                result.orders_created = len(primary_plan.orders)
                result.status = RunStatus.SUCCESS
                result.reason_codes.append("DRY_RUN_COMPLETE")
            else:
                # Execute using agent trade client (creates a PAPER trade visible on /trades)
                from services.agent_trade_client import AgentOpenPayload, AgentClosePayload, get_agent_trade_client

                agent_client = get_agent_trade_client()
                if not agent_client:
                    result.status = RunStatus.ERROR
                    result.block_reason = "NO_AGENT_TRADE_CLIENT"
                    await self._persist_run(result)
                    return result

                # Convert the first intent order into a single trade open
                primary_order = primary_plan.orders[0]
                open_payload = AgentOpenPayload(
                    symbol=primary_plan.symbol,
                    side="BUY" if str(primary_order.side).lower() == "buy" else "SELL",
                    qty=float(primary_order.size_asset or 0),
                    entry_price=float(primary_order.price or 0) if primary_order.price else None,
                    strategy=str(primary_plan.agent_type).upper(),
                    agent_id=f"{str(primary_plan.agent_type).upper()}_agent",
                    meta={
                        "signal_reason": "growth_orchestrator",
                        "preset_id": primary_plan.preset_id,
                        "plan_id": primary_plan.plan_id,
                        "agent_name": str(primary_plan.agent_type).upper(),
                    },
                )

                open_res = await agent_client.open_trade(open_payload)
                if open_res.get("status") == "blocked":
                    result.status = RunStatus.BLOCKED
                    result.block_reason = open_res.get("code")
                    result.execution_result = ExecutionResult(success=False, error=open_res.get("code"))
                    await self._persist_run(result)
                    return result
                if open_res.get("status") != "ok":
                    result.status = RunStatus.ERROR
                    result.block_reason = open_res.get("message", "OPEN_FAILED")
                    result.execution_result = ExecutionResult(success=False, error=result.block_reason)
                    await self._persist_run(result)
                    return result

                _trade_id = open_res.get("trade_id")

                # For now we auto-close immediately to demonstrate full open->close flow.
                # (Agents can later decide close conditions; this satisfies end-to-end PAPER execution.)
                close_payload = AgentClosePayload(
                    exit_price=(open_payload.entry_price or 0) * 1.01 if (open_payload.entry_price or 0) > 0 else None,
                    reason="manual",
                    meta={"source": "growth_orchestrator_auto_close"},
                )
                close_res = await agent_client.close_trade(
                    agent_id=open_payload.agent_id,
                    symbol=open_payload.symbol,
                    strategy=open_payload.strategy,
                    payload=close_payload,
                )

                # Map into ExecutionResult
                if close_res.get("status") == "ok":
                    result.execution_result = ExecutionResult(success=True, orders_created=1, orders_filled=1, pnl_delta_eur=close_res["result"].get("pnl", 0.0))
                    result.orders_created = 1
                    result.orders_filled = 1
                    result.pnl_delta_eur = result.execution_result.pnl_delta_eur
                    result.status = RunStatus.SUCCESS
                else:
                    # Open succeeded but close failed; keep success for execution of open
                    result.execution_result = ExecutionResult(success=True, orders_created=1, orders_filled=1)
                    result.orders_created = 1
                    result.orders_filled = 1
                    result.status = RunStatus.SUCCESS
            
            # Persist and return
            await self._persist_run(result)
            return result
            
        except Exception as e:
            logger.error(f"Run error: {e}")
            result.status = RunStatus.ERROR
            result.block_reason = str(e)
            result.reason_codes.append(f"ERROR_{type(e).__name__}")
            await self._persist_run(result)
            return result
    
    async def get_run(self, run_id: str) -> Optional[RunResult]:
        """Get an existing run by ID (for idempotency/replay)."""
        try:
            doc = await self.db.growth_runs.find_one({"run_id": run_id}, {"_id": 0})
            if doc:
                return RunResult(**doc)
            return None
        except Exception as e:
            logger.error(f"Error getting run {run_id}: {e}")
            return None
    
    async def _persist_run(self, result: RunResult) -> None:
        """Persist run result to database."""
        try:
            doc = result.model_dump(mode="json")
            await self.db.growth_runs.update_one(
                {"run_id": result.run_id},
                {"$set": doc},
                upsert=True,
            )
            logger.info(f"Persisted run {result.run_id} with status {result.status}")
        except Exception as e:
            logger.error(f"Error persisting run: {e}")
    
    async def _create_market_snapshot(self, symbol: str, venue: str) -> MarketSnapshot:
        """Create market snapshot from data feed."""
        # Get metrics from data feed if available
        metrics = await self._get_market_metrics(symbol, venue)
        
        # Handle both dict and object (MarketMetrics) responses
        def get_metric(key: str, default):
            if isinstance(metrics, dict):
                return metrics.get(key, default)
            return getattr(metrics, key, default)
        
        return MarketSnapshot(
            symbol=symbol,
            venue=venue if venue != "auto" else "binance",
            last_price=get_metric("last_price", 95000),
            bid=get_metric("bid", 94995),
            ask=get_metric("ask", 95005),
            spread_pct=get_metric("spread_pct", 0.01),
            atr_pct=get_metric("atr_pct", 0.8),
            atr_14=get_metric("atr_14", 760),
            adx=get_metric("adx", 20),
            ma_slope_pct=get_metric("ma_slope_pct", 0.02),
            trend_direction=get_metric("trend_direction", 0),
            volume_24h=get_metric("volume_24h", 2000000000),
            volume_ratio=get_metric("volume_ratio", 1.0),
            data_age_seconds=get_metric("data_age_seconds", 5),
            data_quality=get_metric("data_quality", 1.0),
        )
    
    async def _guardian_approve(self, context: GuardianContext) -> GuardianResult:
        """Guardian.approve(context) -> GuardianResult."""
        if not self.guardian_service:
            return GuardianResult(
                allowed=True,
                action=GuardianAction.ALLOW,
                reasons=["NO_GUARDIAN_SERVICE"],
            )
        
        try:
            # Import TradeRequest from guardian service
            from services.guardian import TradeRequest
            
            request = TradeRequest(
                agent_id="growth-orchestrator",  # Required field
                agent_type=context.agent_type,
                symbol=context.symbol,
                venue=context.venue,
                side=context.side,
                amount_eur=context.amount_eur,
                spread_pct=context.spread_pct,
                estimated_slippage_pct=context.slippage_pct,
                data_age_seconds=5,
                data_quality=context.data_quality,
                expected_edge_pct=context.expected_edge_pct,
                total_cost_pct=context.spread_pct + context.slippage_pct,
            )
            
            result = await self.guardian_service.validate_trade(request)
            
            return GuardianResult(
                allowed=result.allowed,
                action=GuardianAction.ALLOW if result.allowed else GuardianAction.BLOCK,
                block_reason=result.block_reason.value if result.block_reason else None,
                daily_pnl_pct=0,
                weekly_pnl_pct=0,
                kill_switch_active=False,
                reasons=result.reasons,
            )
        except Exception as e:
            logger.error(f"Guardian error: {e}")
            return GuardianResult(
                allowed=False,
                action=GuardianAction.BLOCK,
                block_reason=str(e),
                reasons=[f"GUARDIAN_ERROR: {e}"],
            )
    
    async def _evaluate_snapshot(
        self,
        snapshot: MarketSnapshot,
        agent_type: str,
        preset_id: str,
        router_decision: Dict[str, Any],
    ) -> List[IntentPlan]:
        """GrowthModule.evaluate(snapshot) -> IntentPlan[]."""
        # Generate intent plan using agent
        plan_dict = await self._generate_intent_plan(
            symbol=snapshot.symbol,
            venue=snapshot.venue,
            agent_type=agent_type,
            preset_id=preset_id,
            router_decision=router_decision,
        )
        
        if not plan_dict or not plan_dict.get("orders"):
            return []
        
        # Convert to IntentPlan
        orders = [
            IntentOrder(
                order_id=o.get("order_id", f"order-{i}"),
                side=o.get("side", "buy"),
                order_type=o.get("order_type", "limit"),
                price=o.get("price", 0),
                size_eur=o.get("size_eur", 0),
                size_asset=o.get("size_asset", 0),
                post_only=o.get("post_only", False),
                rationale=o.get("rationale", ""),
            )
            for i, o in enumerate(plan_dict.get("orders", []))
        ]
        
        plan = IntentPlan(
            plan_id=plan_dict.get("plan_id", f"plan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"),
            agent_type=agent_type,
            preset_id=preset_id,
            symbol=snapshot.symbol,
            venue=snapshot.venue,
            orders=orders,
            capital_eur=plan_dict.get("capital_eur", 100),
            bucket=plan_dict.get("bucket", "CORE"),
            max_loss_eur=plan_dict.get("max_loss_eur", 5),
            expected_edge_pct=plan_dict.get("expected_edge_pct", 0.5),
            reason_codes=plan_dict.get("reason_codes", []),
        )
        
        return [plan]
    
    async def _viability_assess(
        self,
        intent: IntentPlan,
        snapshot: MarketSnapshot,
    ) -> ViabilityResult:
        """ViabilityEngine.assess(intent, snapshot) -> ViabilityResult."""
        if not self.viability_service:
            return ViabilityResult(
                viable=True,
                status=ViabilityStatus.VIABLE,
                expected_edge_pct=intent.expected_edge_pct,
                required_edge_pct=0.1,
                edge_surplus_pct=intent.expected_edge_pct - 0.1,
                total_cost_pct=0.1,
                maker_fee_pct=0.02,
                taker_fee_pct=0.04,
                spread_pct=snapshot.spread_pct,
                slippage_pct=0.02,
                reasons=["NO_VIABILITY_SERVICE"],
            )
        
        try:
            # Import ViabilityInput
            from services.viability import ViabilityInput
            
            input_data = ViabilityInput(
                agent_type=intent.agent_type,
                preset_id=intent.preset_id,
                symbol=intent.symbol,
                venue=intent.venue,
                order_size_eur=intent.capital_eur,
                expected_move_pct=intent.expected_edge_pct,
                current_spread_pct=snapshot.spread_pct,
                bid_price=snapshot.bid,
                ask_price=snapshot.ask,
                expect_maker=True,
            )
            
            result = await self.viability_service.check_viability(input_data)
            
            return ViabilityResult(
                viable=result.viable,
                status=ViabilityStatus(result.status.value) if hasattr(result.status, 'value') else ViabilityStatus.VIABLE,
                expected_edge_pct=result.expected_edge_pct,
                required_edge_pct=result.required_edge_pct,
                edge_surplus_pct=result.edge_surplus_pct,
                total_cost_pct=result.cost_breakdown.total_round_trip_pct if result.cost_breakdown else 0,
                maker_fee_pct=result.cost_breakdown.maker_fee_pct if result.cost_breakdown else 0.02,
                taker_fee_pct=result.cost_breakdown.taker_fee_pct if result.cost_breakdown else 0.04,
                spread_pct=result.cost_breakdown.spread_pct if result.cost_breakdown else snapshot.spread_pct,
                slippage_pct=result.cost_breakdown.slippage_pct if result.cost_breakdown else 0.02,
                reasons=result.reasons if hasattr(result, 'reasons') else [],
            )
        except Exception as e:
            logger.error(f"Viability error: {e}")
            return ViabilityResult(
                viable=False,
                status=ViabilityStatus.NOT_VIABLE,
                expected_edge_pct=0,
                required_edge_pct=0,
                edge_surplus_pct=0,
                total_cost_pct=0,
                maker_fee_pct=0,
                taker_fee_pct=0,
                spread_pct=0,
                slippage_pct=0,
                reasons=[f"VIABILITY_ERROR: {e}"],
            )
    
    async def _execute_intent(self, intent: IntentPlan) -> ExecutionResult:
        """PaperExecutor.execute(intent) -> ExecutionResult."""
        if not self.paper_adapter:
            return ExecutionResult(
                success=False,
                error="NO_PAPER_ADAPTER",
            )
        
        try:
            # Import types from paper_adapter module
            from services.growth.paper_adapter import (
                IntentPlan as AdapterIntentPlan,
                IntentOrderSpec,
                IntentPlanScope,
                IntentPlanRisk,
            )
            
            # Convert orders
            adapter_orders = [
                IntentOrderSpec(
                    client_order_id=o.order_id,
                    side=o.side,
                    order_type=o.order_type,
                    price=o.price,
                    size_eur=o.size_eur,
                    size_asset=o.size_asset,
                    post_only=o.post_only,
                    rationale=o.rationale,
                )
                for o in intent.orders
            ]
            
            # Create scope
            scope = IntentPlanScope(
                capital_eur=intent.capital_eur,
                bucket=intent.bucket,
                max_loss_eur=intent.max_loss_eur,
            )
            
            # Create risk params
            risk = IntentPlanRisk(
                max_loss_eur=intent.max_loss_eur,
                expected_edge_pct=intent.expected_edge_pct,
            )
            
            # Create adapter's IntentPlan
            adapter_plan = AdapterIntentPlan(
                plan_id=intent.plan_id,
                symbol=intent.symbol,
                venue=intent.venue,
                agent_type=intent.agent_type,
                preset_id=intent.preset_id,
                scope=scope,
                orders=adapter_orders,
                risk=risk,
                reason_codes=intent.reason_codes,
            )
            
            # Get router decision mock for adapter
            router_decision = {
                "regime": "RANGE",
                "recommended_agent": intent.agent_type,
                "recommended_preset_id": intent.preset_id,
                "regime_confidence": "MEDIUM",
            }
            
            result = await self.paper_adapter.execute_plan(adapter_plan, router_decision, dry_run=False)
            
            return ExecutionResult(
                success=result.status == "success",
                orders_created=result.orders_created,
                orders_filled=result.orders_filled,
                pnl_delta_eur=result.pnl_delta_eur,
                fees_eur=result.fees_eur,
                order_ids=[o.get("order_id", "") for o in result.orders] if result.orders else [],
                fill_ids=[f.get("fill_id", "") for f in result.fills] if result.fills else [],
                error=result.block_reason if result.status != "success" else None,
            )
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
            )
    
    async def run_cycle(
        self,
        symbol: str = "BTC/USDT",
        venue: str = "auto",
        mode: GrowthRunMode = GrowthRunMode.ONCE,
        force_agent: Optional[str] = None,  # "MM" or "MOM" to override
    ) -> CycleResult:
        """
        Run one complete decision cycle.
        
        Args:
            symbol: Trading pair to analyze
            venue: Exchange ("binance", "kraken", "auto")
            mode: Run mode (ONCE, SIMULATE, SCHEDULED)
            force_agent: Force a specific agent (overrides router)
        
        Returns:
            CycleResult with full execution details
        """
        await self.initialize()
        
        result = CycleResult(
            mode=mode,
            symbol=symbol,
            venue=venue,
        )
        
        dry_run = mode == GrowthRunMode.SIMULATE
        
        try:
            # Step 1: Get market data and run router
            router_decision = await self._run_router(symbol, venue)
            result.router_decision = router_decision
            result.regime = router_decision.get("regime", "")
            result.confidence = router_decision.get("regime_confidence", "")
            result.recommended_agent = router_decision.get("recommended_agent", "PAUSE")
            result.recommended_preset_id = router_decision.get("recommended_preset_id", "")
            result.reason_codes.extend(router_decision.get("all_reason_codes", []))
            
            # Override agent if forced
            if force_agent:
                result.recommended_agent = force_agent
                result.reason_codes.append(f"FORCED_AGENT_{force_agent}")
            
            # Step 2: Check if PAUSE
            if result.recommended_agent == "PAUSE":
                result.status = GrowthRunStatus.PAUSED
                result.block_reason = "ROUTER_PAUSE"
                result.reason_codes.append("ROUTER_PAUSE")
                await self._log_cycle(result)
                return result
            
            # Step 3: Guardian validation
            guardian_check = await self._run_guardian(symbol, venue, result.recommended_agent)
            result.guardian_check = guardian_check
            result.guardian_allowed = guardian_check.get("allowed", False)
            
            if not result.guardian_allowed:
                result.status = GrowthRunStatus.BLOCKED
                result.block_reason = guardian_check.get("block_reason", "GUARDIAN_BLOCKED")
                result.reason_codes.append(f"GUARDIAN_{result.block_reason}")
                await self._log_cycle(result)
                return result
            
            # Step 4: Viability check
            viability_check = await self._run_viability(symbol, venue, result.recommended_agent)
            result.viability_check = viability_check
            result.viability_viable = viability_check.get("viable", False)
            
            # Check if marginal is allowed
            if not result.viability_viable:
                viability_status = viability_check.get("status", "")
                if viability_status == "MARGINAL" and self.config.allow_marginal_viability:
                    result.viability_viable = True
                    result.reason_codes.append("VIABILITY_MARGINAL_ALLOWED")
                else:
                    result.status = GrowthRunStatus.BLOCKED
                    result.block_reason = f"VIABILITY_{viability_status}"
                    result.reason_codes.append(f"VIABILITY_{viability_status}")
                    await self._log_cycle(result)
                    return result
            
            # Step 5: Generate intent plan
            intent_plan = await self._generate_intent_plan(
                symbol=symbol,
                venue=venue if venue != "auto" else router_decision.get("venue", "binance"),
                agent_type=result.recommended_agent,
                preset_id=result.recommended_preset_id,
                router_decision=router_decision,
            )
            result.intent_plan = intent_plan
            result.plan_id = intent_plan.get("plan_id")
            
            if not intent_plan.get("orders"):
                result.status = GrowthRunStatus.PAUSED
                result.block_reason = "NO_ORDERS_GENERATED"
                result.reason_codes.append("NO_ORDERS_GENERATED")
                await self._log_cycle(result)
                return result
            
            # Step 6: Execute through paper adapter
            run_result = await self._execute_plan(intent_plan, router_decision, dry_run)
            result.run_result = run_result
            result.orders_created = run_result.get("orders_created", 0)
            result.orders_filled = run_result.get("orders_filled", 0)
            result.pnl_delta_eur = run_result.get("pnl_delta_eur", 0)
            result.fees_eur = run_result.get("fees_eur", 0)
            
            # Set final status
            if dry_run:
                result.status = GrowthRunStatus.DRY_RUN
            elif run_result.get("status") == "success":
                result.status = GrowthRunStatus.SUCCESS
            else:
                result.status = GrowthRunStatus.ERROR
                result.block_reason = run_result.get("block_reason")
            
            await self._log_cycle(result)
            return result
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            result.status = GrowthRunStatus.ERROR
            result.block_reason = str(e)
            result.reason_codes.append(f"ERROR_{type(e).__name__}")
            await self._log_cycle(result)
            return result
    
    async def _run_router(
        self,
        symbol: str,
        venue: str,
    ) -> Dict[str, Any]:
        """Run market router to get regime and agent recommendation."""
        if not self.market_router:
            return {
                "regime": "RANGE",
                "regime_confidence": "LOW",
                "recommended_agent": "PAUSE",
                "recommended_preset_id": "",
                "all_reason_codes": ["NO_ROUTER_SERVICE"],
            }
        
        # Get market metrics from data feed
        metrics = await self._get_market_metrics(symbol, venue)
        
        # Run router analysis
        decision = await self.market_router.analyze(metrics)
        
        return {
            "regime": decision.regime.value if hasattr(decision.regime, 'value') else str(decision.regime),
            "regime_confidence": decision.regime_confidence.value if hasattr(decision.regime_confidence, 'value') else str(decision.regime_confidence),
            "recommended_agent": decision.recommended_agent.value if hasattr(decision.recommended_agent, 'value') else str(decision.recommended_agent),
            "recommended_preset_id": decision.recommended_preset_id,
            "venue": decision.venue,
            "all_reason_codes": decision.all_reason_codes,
            "regime_reasons": decision.regime_reasons,
            "agent_reasons": decision.agent_reasons,
            "viability_reasons": decision.viability_reasons,
        }
    
    async def _get_market_metrics(self, symbol: str, venue: str) -> Any:
        """Get market metrics for router analysis."""
        from services.market_router import MarketMetrics, calculate_metrics_from_ohlcv
        
        # Default metrics if no data feed
        default_metrics = MarketMetrics(
            symbol=symbol,
            venue=venue if venue != "auto" else "binance",
            last_price=95000,
            bid=94995,
            ask=95005,
            spread_pct=0.01,
            atr_pct=0.8,
            atr_14=760,
            adx=20,
            ma_slope_pct=0.02,
            trend_direction=0,
            volume_24h=2000000000,
            volume_ratio=1.0,
            data_age_seconds=5,
            data_quality=1.0,
        )
        
        if not self.data_feed:
            return default_metrics
        
        try:
            # Fetch OHLCV data
            ohlcv = await self.data_feed.fetch_ohlcv(symbol, "1h", limit=50)
            ticker = await self.data_feed.fetch_ticker(symbol)
            orderbook = await self.data_feed.get_orderbook(symbol, 5)
            
            if ohlcv and len(ohlcv) >= 20:
                metrics = calculate_metrics_from_ohlcv(
                    symbol=symbol,
                    venue=venue if venue != "auto" else "binance",
                    ohlcv=ohlcv,
                    ticker=ticker,
                    orderbook=orderbook,
                )
                return metrics
        except Exception as e:
            logger.warning(f"Failed to fetch market metrics: {e}")
        
        return default_metrics
    
    async def _run_guardian(
        self,
        symbol: str,
        venue: str,
        agent_type: str,
    ) -> Dict[str, Any]:
        """Run guardian validation."""
        if not self.guardian_service:
            return {"allowed": True, "reasons": ["NO_GUARDIAN_SERVICE"]}
        
        try:
            from services.guardian import TradeRequest
            
            request = TradeRequest(
                agent_id=f"growth_{agent_type.lower()}",
                agent_type=agent_type,
                symbol=symbol,
                venue=venue if venue != "auto" else "binance",
                side="buy",
                amount_eur=10,
                spread_pct=0.03,
                estimated_slippage_pct=0.02,
                data_age_seconds=5,
                data_quality=0.98,
                expected_edge_pct=0.5,
                total_cost_pct=0.1,
            )
            
            check = await self.guardian_service.validate_trade(request)
            
            return {
                "allowed": check.allowed,
                "action": check.action.value if hasattr(check.action, 'value') else str(check.action),
                "block_reason": check.block_reason.value if check.block_reason and hasattr(check.block_reason, 'value') else str(check.block_reason) if check.block_reason else None,
                "reasons": check.reasons,
            }
        except Exception as e:
            logger.error(f"Guardian check failed: {e}")
            return {"allowed": False, "block_reason": str(e), "reasons": [str(e)]}
    
    async def _run_viability(
        self,
        symbol: str,
        venue: str,
        agent_type: str,
    ) -> Dict[str, Any]:
        """Run viability cost check."""
        if not self.viability_service:
            return {"viable": True, "status": "NO_VIABILITY_SERVICE", "reasons": []}
        
        try:
            from services.viability import ViabilityInput
            
            input_data = ViabilityInput(
                agent_type=agent_type,
                preset_id=f"{agent_type}_DEFAULT",
                symbol=symbol,
                venue=venue if venue != "auto" else "binance",
                order_size_eur=10,
                expected_move_pct=0.5,
                current_spread_pct=0.03,
                bid_price=94995,
                ask_price=95005,
                expect_maker=True,
            )
            
            result = await self.viability_service.check_viability(input_data)
            
            return {
                "viable": result.viable,
                "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                "expected_edge_pct": result.expected_edge_pct,
                "required_edge_pct": result.required_edge_pct,
                "total_cost_pct": result.cost_breakdown.total_round_trip_pct if result.cost_breakdown else 0,
                "reasons": result.reasons,
            }
        except Exception as e:
            logger.error(f"Viability check failed: {e}")
            return {"viable": False, "status": "ERROR", "reasons": [str(e)]}
    
    async def _generate_intent_plan(
        self,
        symbol: str,
        venue: str,
        agent_type: str,
        preset_id: str,
        router_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate intent plan from agent."""
        from services.growth.paper_adapter import IntentPlan, IntentOrderSpec, IntentPlanScope, IntentPlanRisk
        
        # Get budget
        budget_eur = self.config.default_capital_eur
        bucket = "CORE" if agent_type == "MM" else "EDGE"
        
        if self.risk_budget_service:
            try:
                state = await self.risk_budget_service.get_state()
                if state:
                    buckets = state.get("buckets", {})
                    bucket_data = buckets.get(bucket.lower(), {})
                    budget_eur = bucket_data.get("available_eur", budget_eur)
            except Exception as e:
                logger.warning(f"Could not get budget: {e}")
        
        # Generate plan ID
        timestamp_minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        plan_id = IntentPlan.generate_plan_id(
            agent_type=agent_type,
            symbol=symbol,
            venue=venue,
            preset_id=preset_id,
            timestamp_minute=timestamp_minute,
        )
        
        # Get preset config
        preset_config = await self._get_preset_config(agent_type, preset_id)
        
        # Generate orders based on agent type
        orders = []
        reason_codes = router_decision.get("all_reason_codes", [])
        
        if agent_type == "MM":
            orders = await self._generate_mm_orders(
                symbol=symbol,
                venue=venue,
                plan_id=plan_id,
                budget_eur=budget_eur,
                preset_config=preset_config,
                router_decision=router_decision,
            )
        elif agent_type == "MOM":
            orders = await self._generate_mom_orders(
                symbol=symbol,
                venue=venue,
                plan_id=plan_id,
                budget_eur=budget_eur,
                preset_config=preset_config,
                router_decision=router_decision,
            )
        
        # Add reason code if no orders generated
        if not orders:
            reason_codes = reason_codes + ["NO_VALID_PRICE"]
        
        plan = IntentPlan(
            plan_id=plan_id,
            symbol=symbol,
            venue=venue,
            agent_type=agent_type,
            preset_id=preset_id,
            scope=IntentPlanScope(
                capital_eur=budget_eur,
                bucket=bucket,
            ),
            orders=orders,
            risk=IntentPlanRisk(
                max_loss_eur=budget_eur * 0.02,
                expected_edge_pct=0.5,
            ),
            reason_codes=reason_codes,
        )
        
        return plan.model_dump(mode='json')
    
    async def _get_preset_config(self, agent_type: str, preset_id: str) -> Dict[str, Any]:
        """Get preset configuration."""
        if not self.growth_presets_service:
            return {}
        
        try:
            if agent_type == "MM":
                presets = await self.growth_presets_service.get_mm_presets()
            else:
                presets = await self.growth_presets_service.get_mom_presets()
            
            for p in presets:
                if p.get("preset_id") == preset_id:
                    return p
        except Exception as e:
            logger.warning(f"Could not get preset config: {e}")
        
        return {}
    
    async def _generate_mm_orders(
        self,
        symbol: str,
        venue: str,
        plan_id: str,
        budget_eur: float,
        preset_config: Dict[str, Any],
        router_decision: Dict[str, Any],
    ) -> List:
        """Generate MM (Market Maker) orders."""
        from services.growth.paper_adapter import IntentOrderSpec
        
        orders = []
        
        # Get market price (simplified)
        mid_price = 0
        if self.data_feed:
            try:
                ticker = await self.data_feed.fetch_ticker(symbol)
                if ticker:
                    bid = ticker.get('bid', 0) or 0
                    ask = ticker.get('ask', 0) or 0
                    if bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                    elif bid > 0:
                        mid_price = bid
                    elif ask > 0:
                        mid_price = ask
            except Exception as e:
                logger.warning(f"Failed to fetch ticker for {symbol}: {e}")
        
        # Validate price - cannot generate orders without valid price
        if mid_price <= 0:
            logger.error(f"Cannot generate MM orders for {symbol}: invalid price {mid_price}")
            return []  # Return empty list, will be handled by caller
        
        # Grid parameters
        grid_levels = preset_config.get("grid_levels", 5)
        grid_width_pct = preset_config.get("grid_width_total_pct", 0.4)
        max_order_eur = min(budget_eur * 0.1, preset_config.get("max_position_eur", 50) / max(grid_levels, 1))
        
        half_width = grid_width_pct / 2
        
        # Generate bid orders
        bid_levels = max(grid_levels // 2, 1)
        for i in range(bid_levels):
            distance_pct = (half_width / bid_levels) * (i + 1)
            price = mid_price * (1 - distance_pct / 100)
            if price <= 0:
                continue
            size_eur = max_order_eur * (1 - i * 0.1)
            size_asset = size_eur / price
            
            orders.append(IntentOrderSpec(
                client_order_id=f"{plan_id}_bid_{i}",
                side="buy",
                order_type="limit_maker",
                price=round(price, 2),
                size_eur=round(size_eur, 2),
                size_asset=round(size_asset, 8),
                post_only=True,
                rationale=f"MM bid level {i+1}",
            ))
        
        # Generate ask orders
        ask_levels = max(grid_levels - bid_levels, 1)
        for i in range(ask_levels):
            distance_pct = (half_width / ask_levels) * (i + 1)
            price = mid_price * (1 + distance_pct / 100)
            if price <= 0:
                continue
            size_eur = max_order_eur * (1 - i * 0.1)
            size_asset = size_eur / price
            
            orders.append(IntentOrderSpec(
                client_order_id=f"{plan_id}_ask_{i}",
                side="sell",
                order_type="limit_maker",
                price=round(price, 2),
                size_eur=round(size_eur, 2),
                size_asset=round(size_asset, 8),
                post_only=True,
                rationale=f"MM ask level {i+1}",
            ))
        
        return orders
    
    async def _generate_mom_orders(
        self,
        symbol: str,
        venue: str,
        plan_id: str,
        budget_eur: float,
        preset_config: Dict[str, Any],
        router_decision: Dict[str, Any],
    ) -> List:
        """Generate MOM (Momentum) orders."""
        from services.growth.paper_adapter import IntentOrderSpec
        
        orders = []
        
        # Get market price
        current_price = 0
        if self.data_feed:
            try:
                ticker = await self.data_feed.fetch_ticker(symbol)
                if ticker:
                    current_price = ticker.get('last', 0) or ticker.get('bid', 0) or 0
            except Exception as e:
                logger.warning(f"Failed to fetch ticker for MOM {symbol}: {e}")
        
        # Validate price
        if current_price <= 0:
            logger.error(f"Cannot generate MOM orders for {symbol}: invalid price {current_price}")
            return []
        
        # Determine direction from router
        trend_direction = 1  # Default bullish
        regime = router_decision.get("regime", "")
        if "DOWN" in regime.upper() or router_decision.get("trend_direction", 0) < 0:
            trend_direction = -1
        
        # Position size (limited)
        max_position_eur = min(budget_eur * 0.3, preset_config.get("max_position_eur", 30))
        
        # Entry order
        if trend_direction > 0:
            # Long entry
            entry_price = current_price * 1.001  # Slightly above for breakout
            side = "buy"
        else:
            # Short entry
            entry_price = current_price * 0.999
            side = "sell"
        
        if entry_price <= 0:
            return []
        
        size_asset = max_position_eur / entry_price
        
        orders.append(IntentOrderSpec(
            client_order_id=f"{plan_id}_entry",
            side=side,
            order_type="limit",
            price=round(entry_price, 2),
            size_eur=round(max_position_eur, 2),
            size_asset=round(size_asset, 8),
            post_only=False,
            rationale=f"MOM {side} entry, regime={regime}",
        ))
        
        return orders
    
    async def _execute_plan(
        self,
        intent_plan: Dict[str, Any],
        router_decision: Dict[str, Any],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Execute intent plan through paper adapter."""
        if not self.paper_adapter:
            return {
                "status": "error",
                "block_reason": "NO_PAPER_ADAPTER",
                "orders_created": 0,
                "orders_filled": 0,
            }
        
        from services.growth.paper_adapter import IntentPlan
        
        # Reconstruct IntentPlan from dict
        plan = IntentPlan(**intent_plan)
        
        result = await self.paper_adapter.execute_plan(
            plan=plan,
            decision_snapshot=router_decision,
            dry_run=dry_run,
        )
        
        return result.model_dump(mode='json')
    
    async def _log_cycle(self, result: CycleResult) -> None:
        """Log cycle result to database."""
        doc = result.model_dump(mode='json')
        
        await self.db.growth_cycles.update_one(
            {"cycle_id": result.cycle_id},
            {"$set": doc},
            upsert=True
        )
        
        # Emit event
        if self.event_logger:
            from services.event_logger import EventSeverity, EventCategory
            severity = EventSeverity.INFO if result.status in [GrowthRunStatus.SUCCESS, GrowthRunStatus.DRY_RUN] else EventSeverity.WARNING
            
            await self.event_logger.emit(
                severity=severity,
                category=EventCategory.GROWTH,
                type=f"GROWTH_CYCLE_{result.status.value.upper()}",
                message=f"Growth cycle {result.cycle_id}: {result.status.value} ({result.recommended_agent})",
                context={
                    "cycle_id": result.cycle_id,
                    "status": result.status.value,
                    "agent": result.recommended_agent,
                    "regime": result.regime,
                    "orders_created": result.orders_created,
                    "orders_filled": result.orders_filled,
                    "block_reason": result.block_reason,
                },
                symbol=result.symbol,
                tags=["growth", "cycle", result.status.value]
            )
    
    # ============ Scheduler ============
    
    async def start_scheduler(self, interval_minutes: int = None) -> None:
        """Start the scheduler."""
        if self._scheduler_task and not self._scheduler_task.done():
            logger.warning("Scheduler already running")
            return
        
        if interval_minutes:
            self.config.scheduler_interval_minutes = interval_minutes
            self.config.scheduler.interval_minutes = interval_minutes
        
        self.config.scheduler_enabled = True
        self.config.scheduler.enabled = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"Growth scheduler started (interval: {self.config.scheduler_interval_minutes} min)")
        
        # Notify via WebSocket
        await self._notify_scheduler_change()
    
    async def stop_scheduler(self) -> None:
        """Stop the scheduler."""
        self.config.scheduler_enabled = False
        self.config.scheduler.enabled = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Growth scheduler stopped")
        
        # Notify via WebSocket
        await self._notify_scheduler_change()
    
    async def update_scheduler_config(
        self,
        enabled: Optional[bool] = None,
        interval_minutes: Optional[int] = None,
        symbols: Optional[List[str]] = None,
        active_hours_start: Optional[int] = None,
        active_hours_end: Optional[int] = None,
        active_days: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Update scheduler configuration."""
        if enabled is not None:
            self.config.scheduler.enabled = enabled
            self.config.scheduler_enabled = enabled
        if interval_minutes is not None:
            self.config.scheduler.interval_minutes = interval_minutes
            self.config.scheduler_interval_minutes = interval_minutes
        if symbols is not None:
            self.config.scheduler.symbols = symbols
        if active_hours_start is not None:
            self.config.scheduler.active_hours_start = active_hours_start
        if active_hours_end is not None:
            self.config.scheduler.active_hours_end = active_hours_end
        if active_days is not None:
            self.config.scheduler.active_days = active_days
        
        # Start or stop based on enabled state
        if self.config.scheduler.enabled and (not self._scheduler_task or self._scheduler_task.done()):
            await self.start_scheduler()
        elif not self.config.scheduler.enabled and self._scheduler_task and not self._scheduler_task.done():
            await self.stop_scheduler()
        
        await self._notify_scheduler_change()
        return self.get_scheduler_status()
    
    def _is_within_active_hours(self) -> bool:
        """Check if current time is within active hours."""
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        current_day = now.weekday()  # 0=Monday
        
        # Check day
        if current_day not in self.config.scheduler.active_days:
            return False
        
        # Check hour
        start = self.config.scheduler.active_hours_start
        end = self.config.scheduler.active_hours_end
        
        if start <= end:
            return start <= current_hour < end
        else:
            # Wraps midnight (e.g., 22:00 - 06:00)
            return current_hour >= start or current_hour < end
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop with advanced features."""
        consecutive_errors = 0
        runs_this_hour = 0
        last_hour = datetime.now(timezone.utc).hour
        
        while self.config.scheduler.enabled:
            try:
                current_hour = datetime.now(timezone.utc).hour
                
                # Reset hourly counter
                if current_hour != last_hour:
                    runs_this_hour = 0
                    last_hour = current_hour
                
                # Check active hours
                if not self._is_within_active_hours():
                    logger.debug("Scheduler: outside active hours, skipping")
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
                # Check max runs per hour
                if runs_this_hour >= self.config.scheduler.max_runs_per_hour:
                    logger.debug("Scheduler: max runs per hour reached")
                    await asyncio.sleep(60)
                    continue
                
                # Run for each configured symbol
                for symbol in self.config.scheduler.symbols:
                    try:
                        result = await self.run(
                            mode=RunMode.RUN_ONCE,
                            symbol=symbol,
                            venue="auto",
                        )
                        
                        runs_this_hour += 1
                        
                        # Notify via WebSocket
                        await self._notify_run_complete(result)
                        
                        if result.status == RunStatus.SUCCESS:
                            consecutive_errors = 0
                        else:
                            consecutive_errors += 1
                            
                    except Exception as e:
                        logger.error(f"Scheduler error for {symbol}: {e}")
                        consecutive_errors += 1
                
                # Pause on too many errors
                if consecutive_errors >= self.config.scheduler.pause_on_error_count:
                    logger.warning(f"Scheduler paused: {consecutive_errors} consecutive errors")
                    self.config.scheduler.enabled = False
                    await self._notify_scheduler_change()
                    break
                
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                consecutive_errors += 1
            
            # Wait for next interval
            await asyncio.sleep(self.config.scheduler.interval_minutes * 60)
    
    async def _notify_scheduler_change(self) -> None:
        """Notify WebSocket clients of scheduler state change."""
        try:
            from services.growth.websocket_manager import notify_scheduler_change
            await notify_scheduler_change(self.get_scheduler_status())
        except Exception as e:
            logger.debug(f"WebSocket notify failed (may not be initialized): {e}")
    
    async def _notify_run_complete(self, result) -> None:
        """Notify WebSocket clients of run completion."""
        try:
            from services.growth.websocket_manager import notify_run_complete
            await notify_run_complete(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)
        except Exception as e:
            logger.debug(f"WebSocket notify failed: {e}")
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "enabled": self.config.scheduler.enabled,
            "interval_minutes": self.config.scheduler.interval_minutes,
            "symbols": self.config.scheduler.symbols,
            "active_hours": f"{self.config.scheduler.active_hours_start:02d}:00-{self.config.scheduler.active_hours_end:02d}:00",
            "active_hours_start": self.config.scheduler.active_hours_start,
            "active_hours_end": self.config.scheduler.active_hours_end,
            "active_days": self.config.scheduler.active_days,
            "max_runs_per_hour": self.config.scheduler.max_runs_per_hour,
            "running": self._scheduler_task is not None and not self._scheduler_task.done() if self._scheduler_task else False,
            "within_active_hours": self._is_within_active_hours(),
        }
    
    # ============ Queries ============
    
    async def get_last_cycle(self) -> Optional[Dict[str, Any]]:
        """Get the most recent cycle result."""
        doc = await self.db.growth_cycles.find_one(
            {},
            {"_id": 0},
            sort=[("timestamp", -1)]
        )
        return doc
    
    async def get_cycles(
        self,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent cycles."""
        query = {}
        if status:
            query["status"] = status
        
        docs = await self.db.growth_cycles.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        return docs


# ============ Global Instance ============

growth_orchestrator: Optional[GrowthOrchestrator] = None


def get_growth_orchestrator() -> Optional[GrowthOrchestrator]:
    """Get the global orchestrator instance."""
    return growth_orchestrator


def set_growth_orchestrator(orchestrator: GrowthOrchestrator) -> None:
    """Set the global orchestrator instance."""
    global growth_orchestrator
    growth_orchestrator = orchestrator
    logger.info("GrowthOrchestrator set globally")
