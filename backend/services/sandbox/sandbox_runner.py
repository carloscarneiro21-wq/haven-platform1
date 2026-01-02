"""
Stress Sandbox - Main Runner
============================
Orchestrates sandbox runs, coordinating all simulators and generating reports.

SAFETY: Forces PAPER mode, never executes live trades.
"""

import asyncio
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
import logging

from services.sandbox.scenario_engine import (
    ScenarioEngine, ScenarioTimeline, ScenarioEvent, 
    ScenarioEventType, Severity, EventPack
)
from services.sandbox.synthetic_feed import SyntheticPriceFeed, PriceTick, MarketSnapshot
from services.sandbox.execution_simulator import (
    ExecutionSimulator, OrderRequest, ExecutionResult, ExecutionStatus
)
from services.sandbox.dex_simulator import DexSimulator, SwapRequest, SwapResult, TokenTrapType
from services.sandbox.fault_injector import FaultInjector, FaultState

logger = logging.getLogger(__name__)


# ============ Enums ============

class SandboxRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class GuardianDecision(str, Enum):
    SAFE = "SAFE"
    WARN = "WARN"
    HALT = "HALT"


# ============ Models ============

class SandboxConfig(BaseModel):
    """Configuration for a sandbox run."""
    symbols: List[str] = Field(default=["BTCUSDT", "ETHUSDT"])
    packs: Dict[str, bool] = Field(default={"crash": True, "dex": True, "infra": True})
    severity: Severity = Severity.MED
    duration_min: int = 60
    seed: Optional[int] = None
    
    # Guardian thresholds (overridable)
    dd_limit_pct: float = 8.0
    slippage_p95_limit_pct: float = 1.5
    infra_fault_limit: int = 5
    

class SandboxMetrics(BaseModel):
    """Metrics collected during a sandbox run."""
    survival_score: float = 100.0  # 0-100
    max_dd_pct: float = 0.0
    current_dd_pct: float = 0.0
    time_to_stabilize_sec: int = 0
    
    # Execution metrics
    total_trades: int = 0
    filled_trades: int = 0
    blocked_trades: int = 0
    rejected_trades: int = 0
    
    slippage_avg: float = 0.0
    slippage_p95: float = 0.0
    spread_avg: float = 0.0
    spread_p95: float = 0.0
    
    # DEX metrics
    mev_hits_est: int = 0
    total_gas_usd: float = 0.0
    
    # Infra metrics
    ws_downtime_sec: float = 0.0
    ws_reconnect_count: int = 0
    rate_limit_hits: int = 0
    
    # Guardian
    guardian_status: GuardianDecision = GuardianDecision.SAFE
    guardian_reason: Optional[str] = None
    halt_count: int = 0
    warn_count: int = 0
    

class SandboxRun(BaseModel):
    """Sandbox run record."""
    run_id: str
    seed: int
    config: SandboxConfig
    status: SandboxRunStatus = SandboxRunStatus.PENDING
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_sec: int = 0
    
    # Results
    timeline_events: int = 0
    metrics: SandboxMetrics = Field(default_factory=SandboxMetrics)
    
    # Simulation state
    sim_pnl: float = 0.0
    sim_equity: float = 10000.0  # Starting capital
    starting_equity: float = 10000.0


class SandboxReport(BaseModel):
    """Complete sandbox run report."""
    run_id: str
    seed: int
    config: SandboxConfig
    started_at: datetime
    ended_at: datetime
    duration_sec: int
    status: SandboxRunStatus
    
    metrics: SandboxMetrics
    
    # Detailed data
    events_injected: List[Dict[str, Any]]
    executions: List[Dict[str, Any]]
    guardian_decisions: List[Dict[str, Any]]
    
    # Summary
    summary: str


# ============ Sandbox Runner ============

class SandboxRunner:
    """
    Main sandbox orchestrator.
    
    SAFETY:
    - Forces trading_mode = "paper"
    - live_cex_enabled must be false
    - All actions logged as "SIMULATION"
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Check feature flag
        self.enabled = os.environ.get("SANDBOX_ENABLED", "true").lower() == "true"
        
        # Components (initialized per run)
        self._scenario_engine: Optional[ScenarioEngine] = None
        self._price_feed: Optional[SyntheticPriceFeed] = None
        self._exec_simulator: Optional[ExecutionSimulator] = None
        self._dex_simulator: Optional[DexSimulator] = None
        self._fault_injector: Optional[FaultInjector] = None
        
        # Current run
        self._current_run: Optional[SandboxRun] = None
        self._timeline: Optional[ScenarioTimeline] = None
        self._running = False
        
        # Event tracking
        self._events_processed: List[ScenarioEvent] = []
        self._guardian_decisions: List[Dict[str, Any]] = []
        
        # Event logger reference
        self.event_logger = None
        
    def set_event_logger(self, logger):
        """Set event logger for audit logging."""
        self.event_logger = logger
        
    async def _log_audit(self, event_type: str, message: str, details: Dict[str, Any] = None):
        """Log to audit as SIMULATION."""
        if self.event_logger:
            from services.event_logger import EventSeverity, EventCategory
            await self.event_logger.emit(
                severity=EventSeverity.INFO,
                category=EventCategory.SYSTEM,
                type=f"SANDBOX_{event_type}",
                message=f"[SIMULATION] {message}",
                context=details or {},
                tags=["SIMULATION", "SANDBOX"],
            )
        
        # Also log to sandbox_events collection
        if self._current_run:
            await self.db.sandbox_events.insert_one({
                "run_id": self._current_run.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "message": message,
                "details": details or {},
                "tag": "SIMULATION",
            })
    
    def _check_safety(self) -> bool:
        """Verify safety conditions before running."""
        # Check live_cex_enabled
        live_cex = os.environ.get("LIVE_CEX_ENABLED", "false").lower()
        if live_cex == "true":
            logger.error("SAFETY: Cannot run sandbox with LIVE_CEX_ENABLED=true")
            return False
        
        # Check trading mode
        trading_mode = os.environ.get("TRADING_MODE", "paper").lower()
        if trading_mode == "live":
            logger.warning("SAFETY: Forcing trading_mode to paper for sandbox")
            os.environ["TRADING_MODE"] = "paper"
        
        return True
    
    async def start_run(self, config: SandboxConfig) -> SandboxRun:
        """
        Start a new sandbox run.
        
        Returns the run object with run_id.
        """
        if not self.enabled:
            raise ValueError("Sandbox is disabled (SANDBOX_ENABLED=false)")
            
        if self._running:
            raise ValueError("A sandbox run is already in progress")
            
        if not self._check_safety():
            raise ValueError("Safety check failed - cannot start sandbox")
        
        # Generate seed if not provided
        seed = config.seed or int(datetime.now(timezone.utc).timestamp() * 1000) % 2147483647
        config.seed = seed
        
        # Create run record
        run = SandboxRun(
            run_id=str(uuid.uuid4())[:8],
            seed=seed,
            config=config,
            status=SandboxRunStatus.PENDING,
        )
        
        # Initialize components
        self._scenario_engine = ScenarioEngine(config.symbols)
        self._price_feed = SyntheticPriceFeed(config.symbols)
        self._price_feed.initialize(seed, datetime.now(timezone.utc))
        
        self._exec_simulator = ExecutionSimulator(self._price_feed, seed)
        self._dex_simulator = DexSimulator(seed)
        self._dex_simulator.initialize_default_pools()
        
        self._fault_injector = FaultInjector(seed)
        
        # Generate timeline
        self._timeline = self._scenario_engine.generate_timeline(
            seed=seed,
            duration_min=config.duration_min,
            severity=config.severity,
            packs=config.packs,
            symbols=config.symbols,
        )
        
        run.timeline_events = len(self._timeline.events)
        
        # Store run
        self._current_run = run
        self._events_processed = []
        self._guardian_decisions = []
        
        # Save to DB
        await self.db.sandbox_runs.insert_one({
            "run_id": run.run_id,
            "seed": run.seed,
            "config": config.model_dump(),
            "status": run.status.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await self._log_audit("RUN_CREATED", f"Sandbox run created: {run.run_id}", {
            "run_id": run.run_id,
            "seed": seed,
            "duration_min": config.duration_min,
            "severity": config.severity.value,
            "packs": config.packs,
        })
        
        logger.info(f"Sandbox run created: {run.run_id}, seed={seed}, {run.timeline_events} events")
        
        return run
    
    async def execute_run(self, run_id: str = None) -> SandboxRun:
        """
        Execute the sandbox run simulation.
        
        This runs the full duration, processing all events.
        """
        if not self._current_run:
            raise ValueError("No run to execute")
            
        if run_id and run_id != self._current_run.run_id:
            raise ValueError(f"Run ID mismatch: {run_id} != {self._current_run.run_id}")
        
        run = self._current_run
        run.status = SandboxRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        self._running = True
        
        await self._log_audit("RUN_STARTED", f"Sandbox run started: {run.run_id}", {
            "run_id": run.run_id,
        })
        
        try:
            # Run simulation
            await self._run_simulation()
            
            run.status = SandboxRunStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Sandbox run failed: {e}")
            run.status = SandboxRunStatus.FAILED
            run.metrics.guardian_reason = str(e)
            
        finally:
            self._running = False
            run.ended_at = datetime.now(timezone.utc)
            run.duration_sec = int((run.ended_at - run.started_at).total_seconds())
            
            # Update DB
            await self.db.sandbox_runs.update_one(
                {"run_id": run.run_id},
                {"$set": {
                    "status": run.status.value,
                    "started_at": run.started_at.isoformat(),
                    "ended_at": run.ended_at.isoformat(),
                    "duration_sec": run.duration_sec,
                    "metrics": run.metrics.model_dump(),
                }}
            )
            
            await self._log_audit("RUN_COMPLETED", f"Sandbox run completed: {run.run_id}", {
                "run_id": run.run_id,
                "status": run.status.value,
                "survival_score": run.metrics.survival_score,
            })
        
        return run
    
    async def _run_simulation(self):
        """Run the actual simulation loop."""
        run = self._current_run
        config = run.config
        timeline = self._timeline
        
        duration_sec = config.duration_min * 60
        sim_time = self._price_feed._sim_time
        start_time = sim_time
        
        # Track event index
        event_idx = 0
        events = timeline.events
        
        # Simulation loop - process in 1-second steps
        step_sec = 1
        elapsed = 0
        
        while elapsed < duration_sec and self._running:
            current_time = start_time + timedelta(seconds=elapsed)
            
            # Process events that should trigger at this time
            while event_idx < len(events) and events[event_idx].t <= elapsed:
                event = events[event_idx]
                await self._process_event(event, current_time)
                event_idx += 1
            
            # Advance price feed
            self._price_feed._sim_time = current_time
            for _ in range(10):  # 10 ticks per second
                self._price_feed.advance_time(100)
                for symbol in config.symbols:
                    self._price_feed.generate_tick(symbol)
            
            # Update fault injector time
            self._fault_injector.set_sim_time(current_time)
            
            # Run guardian check
            await self._check_guardian()
            
            # Update metrics
            self._update_metrics()
            
            elapsed += step_sec
            
            # Allow other async tasks
            if elapsed % 10 == 0:
                await asyncio.sleep(0)
        
        # Final metrics calculation
        self._calculate_final_metrics()
    
    async def _process_event(self, event: ScenarioEvent, current_time: datetime):
        """Process a single scenario event."""
        self._events_processed.append(event)
        
        # Log event injection
        await self._log_audit("EVENT_INJECTED", f"Event: {event.event_type.value}", {
            "event_type": event.event_type.value,
            "pack": event.pack.value,
            "severity": event.severity.value,
            "duration_sec": event.duration_sec,
            "params": event.params,
            "symbols": event.symbols,
        })
        
        # Route to appropriate simulator
        if event.pack == EventPack.CRASH:
            self._price_feed.inject_event(event, current_time)
            
        elif event.pack == EventPack.DEX:
            if event.event_type == ScenarioEventType.LIQUIDITY_DRY_UP:
                for symbol in event.symbols:
                    self._dex_simulator.inject_liquidity_reduction(
                        symbol, 
                        event.params.get("reserve_reduction_pct", 50)
                    )
            elif event.event_type == ScenarioEventType.MEV_RISK_UP:
                self._dex_simulator.inject_mev_risk(
                    event.params.get("sandwich_probability", 0.3)
                )
            elif event.event_type == ScenarioEventType.GAS_SPIKE:
                self._dex_simulator.inject_gas_spike(
                    event.params.get("gas_multiplier", 5)
                )
            elif event.event_type == ScenarioEventType.TOKEN_TRAP_ROTATION:
                trap_type = TokenTrapType(event.params.get("trap_type", "none"))
                for symbol in event.symbols:
                    self._dex_simulator.set_token_trap(symbol, trap_type)
                    
        elif event.pack == EventPack.INFRA:
            self._fault_injector.inject_event(event, current_time)
            
            # Also notify execution simulator
            if event.event_type == ScenarioEventType.RATE_LIMIT_429:
                self._exec_simulator.inject_rate_limit(
                    event.duration_sec,
                    event.params.get("backoff_sec", 10)
                )
            elif event.event_type == ScenarioEventType.API_LATENCY:
                latency_mult = event.params.get("latency_ms", 500) / 100
                self._exec_simulator.inject_latency(latency_mult, event.duration_sec)
            elif event.event_type == ScenarioEventType.ORDER_ACK_DELAY:
                self._exec_simulator.inject_ack_delay(
                    event.params.get("ack_delay_ms", 1000),
                    event.duration_sec
                )
    
    async def _check_guardian(self):
        """Check guardian conditions and update status."""
        run = self._current_run
        config = run.config
        metrics = run.metrics
        
        decision = GuardianDecision.SAFE
        reason = None
        
        # Check drawdown limit
        if metrics.current_dd_pct > config.dd_limit_pct:
            decision = GuardianDecision.HALT
            reason = f"DD_LIMIT: {metrics.current_dd_pct:.2f}% > {config.dd_limit_pct}%"
            
        # Check slippage P95
        elif metrics.slippage_p95 > config.slippage_p95_limit_pct:
            decision = GuardianDecision.WARN
            reason = f"SLIPPAGE_P95: {metrics.slippage_p95:.2f}% > {config.slippage_p95_limit_pct}%"
            
        # Check infra faults
        fault_stats = self._fault_injector.get_stats()
        if fault_stats["ws_drop_count"] > config.infra_fault_limit:
            decision = GuardianDecision.WARN
            reason = f"INFRA_FAULTS: {fault_stats['ws_drop_count']} WS drops"
        
        # Update metrics
        if decision != metrics.guardian_status:
            if decision == GuardianDecision.HALT:
                metrics.halt_count += 1
            elif decision == GuardianDecision.WARN:
                metrics.warn_count += 1
                
            metrics.guardian_status = decision
            metrics.guardian_reason = reason
            
            # Record decision
            self._guardian_decisions.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "decision": decision.value,
                "reason": reason,
            })
            
            await self._log_audit("GUARDIAN_DECISION", f"Guardian: {decision.value}", {
                "decision": decision.value,
                "reason": reason,
            })
    
    def _update_metrics(self):
        """Update running metrics."""
        run = self._current_run
        metrics = run.metrics
        
        # Get execution stats
        exec_stats = self._exec_simulator.get_execution_stats()
        metrics.total_trades = exec_stats["total_executions"]
        metrics.filled_trades = exec_stats["filled"]
        metrics.rejected_trades = exec_stats["rejected"]
        metrics.slippage_avg = exec_stats["avg_slippage_pct"]
        metrics.slippage_p95 = exec_stats["slippage_p95"]
        metrics.spread_avg = exec_stats["avg_spread_pct"]
        metrics.spread_p95 = exec_stats["spread_p95"]
        
        # Get DEX stats
        dex_stats = self._dex_simulator.get_swap_stats()
        metrics.mev_hits_est = dex_stats["mev_hits"]
        metrics.total_gas_usd = dex_stats["total_gas_usd"]
        
        # Get fault stats
        fault_stats = self._fault_injector.get_stats()
        metrics.ws_downtime_sec = fault_stats["ws_total_downtime_sec"]
        metrics.ws_reconnect_count = fault_stats["ws_drop_count"]
        metrics.rate_limit_hits = fault_stats["rate_limit_429_count"]
        
        # Calculate simulated PnL (simplified)
        # In a real implementation, this would track actual positions
        # For now, penalize based on events and conditions
        base_pnl_change = -0.1  # Slight loss per tick during chaos
        if metrics.guardian_status == GuardianDecision.HALT:
            base_pnl_change = -0.5
        elif metrics.guardian_status == GuardianDecision.WARN:
            base_pnl_change = -0.2
            
        run.sim_pnl += base_pnl_change
        run.sim_equity = run.starting_equity + run.sim_pnl
        
        # Update drawdown
        if run.sim_equity < run.starting_equity:
            metrics.current_dd_pct = ((run.starting_equity - run.sim_equity) / run.starting_equity) * 100
            metrics.max_dd_pct = max(metrics.max_dd_pct, metrics.current_dd_pct)
    
    def _calculate_final_metrics(self):
        """Calculate final survival score and metrics."""
        run = self._current_run
        metrics = run.metrics
        
        # Survival score calculation (0-100)
        # Penalize for:
        # - Drawdown
        # - Guardian halts
        # - High slippage
        # - Infra issues
        
        score = 100.0
        
        # Drawdown penalty (up to -40 points)
        score -= min(40, metrics.max_dd_pct * 5)
        
        # Guardian halt penalty (-10 per halt)
        score -= metrics.halt_count * 10
        
        # Warn penalty (-5 per warn)
        score -= metrics.warn_count * 5
        
        # Slippage penalty (up to -20 points)
        score -= min(20, metrics.slippage_p95 * 10)
        
        # Infra penalty (up to -20 points)
        infra_penalty = metrics.ws_reconnect_count * 2 + metrics.rate_limit_hits
        score -= min(20, infra_penalty)
        
        # Blocked trades penalty
        if metrics.total_trades > 0:
            block_rate = metrics.blocked_trades / metrics.total_trades
            score -= block_rate * 10
        
        metrics.survival_score = max(0, min(100, score))
    
    async def stop_run(self) -> Optional[SandboxRun]:
        """Stop the current run."""
        if not self._current_run:
            return None
            
        self._running = False
        self._current_run.status = SandboxRunStatus.STOPPED
        
        await self._log_audit("RUN_STOPPED", f"Sandbox run stopped: {self._current_run.run_id}", {
            "run_id": self._current_run.run_id,
        })
        
        return self._current_run
    
    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Get current run status."""
        if not self._current_run:
            return None
            
        run = self._current_run
        return {
            "run_id": run.run_id,
            "seed": run.seed,
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "duration_sec": run.duration_sec,
            "metrics": run.metrics.model_dump(),
            "sim_equity": run.sim_equity,
            "events_processed": len(self._events_processed),
            "guardian_status": run.metrics.guardian_status.value,
        }
    
    async def get_report(self, run_id: str) -> Optional[SandboxReport]:
        """Generate full report for a run."""
        # Try current run first
        if self._current_run and self._current_run.run_id == run_id:
            run = self._current_run
        else:
            # Load from DB
            run_doc = await self.db.sandbox_runs.find_one({"run_id": run_id}, {"_id": 0})
            if not run_doc:
                return None
            run = SandboxRun(**run_doc)
        
        # Get events
        events_cursor = self.db.sandbox_events.find(
            {"run_id": run_id}, 
            {"_id": 0}
        ).sort("timestamp", 1)
        events = await events_cursor.to_list(1000)
        
        # Get executions
        executions = []
        if self._exec_simulator:
            executions = [e.model_dump() for e in self._exec_simulator.get_all_executions()]
        
        # Build summary
        metrics = run.metrics
        summary = f"""
Sandbox Run {run_id} - {run.status.value}
Seed: {run.seed} | Duration: {run.duration_sec}s | Severity: {run.config.severity.value}

SURVIVAL SCORE: {metrics.survival_score:.1f}/100

Key Metrics:
- Max Drawdown: {metrics.max_dd_pct:.2f}%
- Slippage P95: {metrics.slippage_p95:.2f}%
- Guardian Status: {metrics.guardian_status.value}
- Halts: {metrics.halt_count} | Warns: {metrics.warn_count}

Execution:
- Total Trades: {metrics.total_trades}
- Filled: {metrics.filled_trades} | Rejected: {metrics.rejected_trades}

Infrastructure:
- WS Downtime: {metrics.ws_downtime_sec:.1f}s
- Rate Limits: {metrics.rate_limit_hits}

DEX:
- MEV Hits: {metrics.mev_hits_est}
- Gas Cost: ${metrics.total_gas_usd:.2f}
"""
        
        return SandboxReport(
            run_id=run_id,
            seed=run.seed,
            config=run.config,
            started_at=run.started_at or datetime.now(timezone.utc),
            ended_at=run.ended_at or datetime.now(timezone.utc),
            duration_sec=run.duration_sec,
            status=run.status,
            metrics=metrics,
            events_injected=events,
            executions=executions,
            guardian_decisions=self._guardian_decisions,
            summary=summary.strip(),
        )
    
    async def get_scenarios(self) -> List[Dict[str, Any]]:
        """Get list of preset scenarios."""
        if not self._scenario_engine:
            self._scenario_engine = ScenarioEngine()
        return self._scenario_engine.get_preset_scenarios()
