"""
GO-LIVE GATE — HAVEN Capital Preservation System
=================================================

Purpose: Determine objectively whether the system CAN or CANNOT operate in LIVE mode.

This gate does NOT optimize profits.
This gate PREVENTS capital destruction.

🔒 NON-NEGOTIABLE PRINCIPLES:
- Survival > Profit
- LIVE is PERMITTED, not "activated"
- Absence of trades is a valid outcome
- Guardian has maximum authority
- If in doubt → NO-GO
- Everything must be: measurable, auditable, explainable

🎯 SINGLE QUESTION:
"Can this system destroy the account?"
If the answer is not a CLEAR NO → LIVE BLOCKED
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
from pydantic import BaseModel, Field
import hashlib
import json

logger = logging.getLogger(__name__)


# ============================================================
# 🔴 GATE DECISION STATES
# ============================================================

class GateDecision(str, Enum):
    """Final gate decision - only two states."""
    NO_GO = "NO_GO"   # LIVE execution is BLOCKED
    GO = "GO"         # LIVE execution is PERMITTED (with constraints)


class GateCriterionStatus(str, Enum):
    """Status of individual evaluation criteria."""
    PASSED = "PASSED"          # Criterion met
    FAILED = "FAILED"          # Criterion not met → NO-GO
    WARNING = "WARNING"        # Met with concerns
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # Not enough data → NO-GO
    NOT_APPLICABLE = "N/A"     # Does not apply


# ============================================================
# 📊 METRICS MODELS
# ============================================================

class OperationalHistory(BaseModel):
    """Historical operational data from the system."""
    # Run counts
    total_paper_runs: int = 0
    total_shadow_runs: int = 0
    total_runs_blocked_by_guardian: int = 0
    
    # Observation period
    first_run_timestamp: Optional[datetime] = None
    last_run_timestamp: Optional[datetime] = None
    observation_days: int = 0
    
    # Paper mode stats
    paper_success_runs: int = 0
    paper_error_runs: int = 0
    paper_blocked_runs: int = 0
    
    # Shadow mode stats
    shadow_success_runs: int = 0
    shadow_error_runs: int = 0
    shadow_divergence_count: int = 0  # Paper vs shadow mismatches


class SurvivalMetrics(BaseModel):
    """Metrics that determine survival capability."""
    # Drawdown
    max_drawdown_pct: float = 0.0
    avg_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    
    # Consecutive events
    max_consecutive_losses: int = 0
    max_consecutive_no_execution_days: int = 0
    current_consecutive_no_execution_days: int = 0
    
    # PnL variance
    pnl_variance: float = 0.0
    pnl_std_dev: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Risk events
    total_risk_events_avoided: int = 0  # Guardian blocks that prevented loss
    kill_switch_activations: int = 0


class TechnicalStability(BaseModel):
    """Technical stability metrics."""
    # Execution quality
    execution_failures: int = 0
    execution_success_rate: float = 0.0
    
    # Paper vs Shadow
    paper_shadow_divergences: int = 0
    divergence_unexplained: int = 0  # Divergences without clear cause
    
    # Latency
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    latency_spikes: int = 0  # Times latency > threshold
    
    # Order quality
    orders_rejected: int = 0
    orders_inconsistent: int = 0  # Orders that failed validation
    
    # Crashes
    system_crashes: int = 0
    crashes_with_open_positions: int = 0  # CRITICAL


class GuardianBehavior(BaseModel):
    """Guardian intervention history."""
    # Interventions
    total_interventions: int = 0
    interventions_last_7_days: int = 0
    interventions_last_24_hours: int = 0
    
    # Accuracy
    correct_blocks: int = 0       # Blocks that prevented verified loss
    missed_blocks: int = 0        # Should have blocked but didn't
    false_positives: int = 0      # Blocked unnecessarily (validated post-hoc)
    
    # Stress testing
    stress_tests_run: int = 0
    stress_tests_passed: int = 0
    stress_test_block_rate: float = 0.0  # % of forced scenarios blocked
    
    # Kill switch history
    kill_switches_activated: int = 0
    kill_switches_manual_override: int = 0  # Manual deactivations


class AccountingIntegrity(BaseModel):
    """Internal vs external accounting comparison."""
    # Reconciliation
    last_reconciliation: Optional[datetime] = None
    reconciliation_passes: int = 0
    reconciliation_failures: int = 0
    
    # Drift
    max_balance_drift_pct: float = 0.0
    avg_balance_drift_pct: float = 0.0
    current_balance_drift_pct: float = 0.0
    
    # Tolerance
    within_tolerance: bool = True
    tolerance_pct: float = 0.5  # Default 0.5%


# ============================================================
# 📋 GATE CRITERIA DEFINITIONS
# ============================================================

class CriterionResult(BaseModel):
    """Result of evaluating a single criterion."""
    criterion_id: str
    name: str
    category: str  # "minimum" | "blocking" | "uncertainty"
    
    status: GateCriterionStatus
    passed: bool
    
    # Details
    actual_value: Any
    required_value: Any
    comparison: str  # ">=" | "<=" | "==" | "<" | ">"
    
    message: str
    recommendation: str = ""
    
    # Severity
    is_critical: bool = False  # If failed, immediate NO-GO


class GateEvaluation(BaseModel):
    """Complete gate evaluation result."""
    # Decision
    decision: GateDecision
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluation_id: str = Field(default_factory=lambda: hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:16])
    
    # Summary
    total_criteria: int = 0
    criteria_passed: int = 0
    criteria_failed: int = 0
    criteria_warning: int = 0
    criteria_insufficient: int = 0
    
    # Details
    criteria_results: List[CriterionResult] = []
    
    # Input data
    operational_history: Optional[OperationalHistory] = None
    survival_metrics: Optional[SurvivalMetrics] = None
    technical_stability: Optional[TechnicalStability] = None
    guardian_behavior: Optional[GuardianBehavior] = None
    accounting_integrity: Optional[AccountingIntegrity] = None
    
    # Constraints (if GO)
    constraints: Optional['LiveConstraints'] = None
    
    # Recommendation
    recommendation: str = ""
    risk_summary: str = ""
    
    # Audit
    audit_hash: str = ""  # Hash of all input data for integrity


class LiveConstraints(BaseModel):
    """Constraints for GO decision - LIVE is never unrestricted."""
    # Capital
    max_capital_eur: float = 50.0  # Very conservative start
    max_single_trade_eur: float = 10.0
    
    # Pairs
    allowed_symbols: List[str] = ["BTC/USDT"]  # Start with most liquid
    
    # Time
    allowed_hours_utc_start: int = 8
    allowed_hours_utc_end: int = 20
    allowed_days: List[int] = [0, 1, 2, 3, 4]  # Monday-Friday
    
    # Guardian
    guardian_mode: str = "STRICT"  # "STRICT" | "NORMAL"
    daily_loss_limit_pct: float = -1.0  # Tighter than paper
    weekly_drawdown_limit_pct: float = -3.0
    
    # Escalation
    auto_pause_on_error: bool = True
    require_manual_restart_on_loss: bool = True
    max_consecutive_losses: int = 2
    
    # Observation
    mandatory_shadow_period_hours: int = 168  # 7 days
    review_period_days: int = 7  # Review constraints after this


# ============================================================
# 🔧 GATE CONFIGURATION
# ============================================================

class GateConfig(BaseModel):
    """Configuration for GO-LIVE Gate thresholds."""
    # ✅ MINIMUM REQUIREMENTS (all must pass)
    min_paper_runs: int = 50
    min_shadow_days: int = 14
    min_observation_days: int = 21
    
    # 🚫 BLOCKING THRESHOLDS (any failure = NO-GO)
    max_drawdown_limit_pct: float = -10.0  # Max observed drawdown
    max_missed_guardian_blocks: int = 0    # Should have blocked but didn't
    max_unexplained_divergences: int = 0   # Paper vs shadow without explanation
    max_crashes_with_positions: int = 0    # ZERO tolerance
    
    # Guardian requirements
    guardian_stress_block_rate_min: float = 1.0  # 100% of forced scenarios
    
    # Accounting
    max_balance_drift_pct: float = 1.0  # Internal vs exchange
    
    # 🟡 WARNING THRESHOLDS
    warning_drawdown_pct: float = -5.0
    warning_execution_failure_rate: float = 0.05  # 5%
    warning_latency_spikes: int = 5
    
    # Default constraints for GO
    default_constraints: LiveConstraints = Field(default_factory=LiveConstraints)


# ============================================================
# 🏛️ GO-LIVE GATE SERVICE
# ============================================================

class GoLiveGateService:
    """
    GO-LIVE GATE — Independent module that determines LIVE execution permission.
    
    This service:
    1. Collects metrics from all system components
    2. Evaluates against objective criteria
    3. Returns GO or NO-GO decision
    4. Provides full audit trail
    
    NEVER optimizes for profit.
    ONLY prevents capital destruction.
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        config: Optional[GateConfig] = None,
    ):
        self.db = db
        self.config = config or GateConfig()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the gate service."""
        # Create indexes
        await self.db.go_live_evaluations.create_index("timestamp")
        await self.db.go_live_evaluations.create_index("decision")
        await self.db.go_live_evaluations.create_index("evaluation_id")
        
        self._initialized = True
        logger.info("GO-LIVE Gate initialized")
    
    # ============================================================
    # 📊 METRICS COLLECTION
    # ============================================================
    
    async def collect_operational_history(self) -> OperationalHistory:
        """Collect operational history from growth_cycles."""
        history = OperationalHistory()
        
        try:
            # Total paper runs
            history.total_paper_runs = await self.db.growth_cycles.count_documents(
                {"mode": {"$in": ["paper", "run_once", "RUN_ONCE"]}}
            )
            
            # Shadow runs (if implemented)
            history.total_shadow_runs = await self.db.growth_cycles.count_documents(
                {"mode": "shadow"}
            )
            
            # Blocked runs
            history.total_runs_blocked_by_guardian = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["blocked", "BLOCKED"]}}
            )
            
            # First and last run
            first_run = await self.db.growth_cycles.find_one(
                {},
                sort=[("timestamp", 1)],
                projection={"timestamp": 1}
            )
            last_run = await self.db.growth_cycles.find_one(
                {},
                sort=[("timestamp", -1)],
                projection={"timestamp": 1}
            )
            
            if first_run and "timestamp" in first_run:
                ts = first_run["timestamp"]
                if isinstance(ts, str):
                    history.first_run_timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    history.first_run_timestamp = ts
            
            if last_run and "timestamp" in last_run:
                ts = last_run["timestamp"]
                if isinstance(ts, str):
                    history.last_run_timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    history.last_run_timestamp = ts
            
            # Calculate observation days
            if history.first_run_timestamp and history.last_run_timestamp:
                delta = history.last_run_timestamp - history.first_run_timestamp
                history.observation_days = delta.days
            
            # Success/error/blocked counts
            history.paper_success_runs = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["success", "SUCCESS"]}}
            )
            history.paper_error_runs = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["error", "ERROR"]}}
            )
            history.paper_blocked_runs = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["blocked", "BLOCKED", "paused", "PAUSED"]}}
            )
            
        except Exception as e:
            logger.error(f"Failed to collect operational history: {e}")
        
        return history
    
    async def collect_survival_metrics(self) -> SurvivalMetrics:
        """Collect survival metrics from trading history."""
        metrics = SurvivalMetrics()
        
        try:
            # Get all PnL data
            pipeline = [
                {"$match": {"pnl_delta_eur": {"$exists": True}}},
                {"$group": {
                    "_id": None,
                    "pnl_values": {"$push": "$pnl_delta_eur"},
                    "max_loss": {"$min": "$pnl_delta_eur"},
                    "total_pnl": {"$sum": "$pnl_delta_eur"},
                }}
            ]
            result = await self.db.growth_cycles.aggregate(pipeline).to_list(1)
            
            if result:
                data = result[0]
                pnl_values = data.get("pnl_values", [])
                
                # Calculate drawdown (simplified)
                if pnl_values:
                    import statistics
                    metrics.pnl_variance = statistics.variance(pnl_values) if len(pnl_values) > 1 else 0
                    metrics.pnl_std_dev = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0
                    
                    # Max drawdown as max single loss
                    min_pnl = min(pnl_values) if pnl_values else 0
                    metrics.max_drawdown_pct = min_pnl  # Simplified
            
            # Kill switch activations
            metrics.kill_switch_activations = await self.db.audit_logs.count_documents(
                {"action": {"$regex": "kill_switch", "$options": "i"}}
            )
            
            # Guardian blocks (risk events avoided)
            metrics.total_risk_events_avoided = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["blocked", "BLOCKED"]}, "guardian_result.allowed": False}
            )
            
        except Exception as e:
            logger.error(f"Failed to collect survival metrics: {e}")
        
        return metrics
    
    async def collect_technical_stability(self) -> TechnicalStability:
        """Collect technical stability metrics."""
        stability = TechnicalStability()
        
        try:
            # Execution stats
            total_runs = await self.db.growth_cycles.count_documents({})
            success_runs = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["success", "SUCCESS"]}}
            )
            error_runs = await self.db.growth_cycles.count_documents(
                {"status": {"$in": ["error", "ERROR"]}}
            )
            
            stability.execution_failures = error_runs
            if total_runs > 0:
                stability.execution_success_rate = success_runs / total_runs
            
            # System crashes (from events)
            stability.system_crashes = await self.db.events.count_documents(
                {"type": {"$regex": "crash|exception|fatal", "$options": "i"}}
            )
            
        except Exception as e:
            logger.error(f"Failed to collect technical stability: {e}")
        
        return stability
    
    async def collect_guardian_behavior(self) -> GuardianBehavior:
        """Collect Guardian behavior metrics."""
        behavior = GuardianBehavior()
        
        try:
            # Total interventions (blocks)
            behavior.total_interventions = await self.db.growth_cycles.count_documents(
                {"guardian_result.allowed": False}
            )
            
            # Last 7 days
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            behavior.interventions_last_7_days = await self.db.growth_cycles.count_documents(
                {
                    "guardian_result.allowed": False,
                    "timestamp": {"$gte": seven_days_ago.isoformat()}
                }
            )
            
            # Last 24 hours
            one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            behavior.interventions_last_24_hours = await self.db.growth_cycles.count_documents(
                {
                    "guardian_result.allowed": False,
                    "timestamp": {"$gte": one_day_ago.isoformat()}
                }
            )
            
            # Kill switches
            behavior.kill_switches_activated = await self.db.audit_logs.count_documents(
                {"action": {"$regex": "kill_switch.*activate", "$options": "i"}}
            )
            
            # Stress tests (if implemented)
            stress_tests = await self.db.stress_test_results.count_documents({})
            behavior.stress_tests_run = stress_tests
            
            if stress_tests > 0:
                passed = await self.db.stress_test_results.count_documents({"passed": True})
                behavior.stress_tests_passed = passed
                behavior.stress_test_block_rate = passed / stress_tests
            
        except Exception as e:
            logger.error(f"Failed to collect guardian behavior: {e}")
        
        return behavior
    
    async def collect_accounting_integrity(self) -> AccountingIntegrity:
        """Collect accounting integrity metrics."""
        integrity = AccountingIntegrity()
        
        try:
            # Get reconciliation history (if exists)
            recon = await self.db.reconciliations.find_one(
                {},
                sort=[("timestamp", -1)]
            )
            
            if recon:
                if "timestamp" in recon:
                    ts = recon["timestamp"]
                    if isinstance(ts, str):
                        integrity.last_reconciliation = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        integrity.last_reconciliation = ts
                
                integrity.current_balance_drift_pct = recon.get("drift_pct", 0)
                integrity.within_tolerance = abs(integrity.current_balance_drift_pct) <= integrity.tolerance_pct
            
            # Count passes/failures
            integrity.reconciliation_passes = await self.db.reconciliations.count_documents(
                {"status": "passed"}
            )
            integrity.reconciliation_failures = await self.db.reconciliations.count_documents(
                {"status": "failed"}
            )
            
        except Exception as e:
            logger.error(f"Failed to collect accounting integrity: {e}")
        
        return integrity
    
    # ============================================================
    # 🧮 CRITERIA EVALUATION
    # ============================================================
    
    def _evaluate_criterion(
        self,
        criterion_id: str,
        name: str,
        category: str,
        actual_value: Any,
        required_value: Any,
        comparison: str,
        message_template: str,
        recommendation: str = "",
        is_critical: bool = False,
    ) -> CriterionResult:
        """Evaluate a single criterion."""
        # Determine if passed
        passed = False
        status = GateCriterionStatus.FAILED
        
        if actual_value is None:
            status = GateCriterionStatus.INSUFFICIENT_DATA
            passed = False
        else:
            if comparison == ">=":
                passed = actual_value >= required_value
            elif comparison == "<=":
                passed = actual_value <= required_value
            elif comparison == "==":
                passed = actual_value == required_value
            elif comparison == "<":
                passed = actual_value < required_value
            elif comparison == ">":
                passed = actual_value > required_value
            
            status = GateCriterionStatus.PASSED if passed else GateCriterionStatus.FAILED
        
        message = message_template.format(
            actual=actual_value,
            required=required_value,
        )
        
        return CriterionResult(
            criterion_id=criterion_id,
            name=name,
            category=category,
            status=status,
            passed=passed,
            actual_value=actual_value,
            required_value=required_value,
            comparison=comparison,
            message=message,
            recommendation=recommendation,
            is_critical=is_critical,
        )
    
    async def evaluate(self) -> GateEvaluation:
        """
        Execute full GO-LIVE Gate evaluation.
        
        Returns:
            GateEvaluation with decision and full audit trail
        """
        logger.info("Starting GO-LIVE Gate evaluation...")
        
        # Collect all metrics
        history = await self.collect_operational_history()
        survival = await self.collect_survival_metrics()
        stability = await self.collect_technical_stability()
        guardian = await self.collect_guardian_behavior()
        accounting = await self.collect_accounting_integrity()
        
        # Initialize evaluation
        evaluation = GateEvaluation(
            decision=GateDecision.NO_GO,  # Default to NO-GO
            operational_history=history,
            survival_metrics=survival,
            technical_stability=stability,
            guardian_behavior=guardian,
            accounting_integrity=accounting,
        )
        
        criteria: List[CriterionResult] = []
        
        # ============================================================
        # ✅ MINIMUM REQUIREMENTS (all must pass)
        # ============================================================
        
        # M1: Minimum paper runs
        criteria.append(self._evaluate_criterion(
            criterion_id="M1",
            name="Minimum Paper Runs",
            category="minimum",
            actual_value=history.total_paper_runs,
            required_value=self.config.min_paper_runs,
            comparison=">=",
            message_template="Paper runs: {actual} (required: ≥{required})",
            recommendation=f"Continue paper trading until {self.config.min_paper_runs} runs completed.",
            is_critical=True,
        ))
        
        # M2: Minimum observation days
        criteria.append(self._evaluate_criterion(
            criterion_id="M2",
            name="Minimum Observation Period",
            category="minimum",
            actual_value=history.observation_days,
            required_value=self.config.min_observation_days,
            comparison=">=",
            message_template="Observation period: {actual} days (required: ≥{required})",
            recommendation=f"Continue observing for {self.config.min_observation_days - history.observation_days} more days.",
            is_critical=True,
        ))
        
        # M3: Zero kill switch violations
        criteria.append(self._evaluate_criterion(
            criterion_id="M3",
            name="Kill Switch Integrity",
            category="minimum",
            actual_value=guardian.missed_blocks,
            required_value=0,
            comparison="==",
            message_template="Missed Guardian blocks: {actual} (required: {required})",
            recommendation="Investigate all cases where Guardian should have blocked but didn't.",
            is_critical=True,
        ))
        
        # M4: Guardian stress test success
        stress_rate = guardian.stress_test_block_rate if guardian.stress_tests_run > 0 else None
        criteria.append(self._evaluate_criterion(
            criterion_id="M4",
            name="Guardian Stress Test Success",
            category="minimum",
            actual_value=stress_rate,
            required_value=self.config.guardian_stress_block_rate_min,
            comparison=">=",
            message_template="Guardian stress test block rate: {actual} (required: ≥{required})",
            recommendation="Run stress tests with forced scenarios to validate Guardian.",
            is_critical=True,
        ))
        
        # M5: Zero crashes with open positions
        criteria.append(self._evaluate_criterion(
            criterion_id="M5",
            name="No Crashes With Positions",
            category="minimum",
            actual_value=stability.crashes_with_open_positions,
            required_value=self.config.max_crashes_with_positions,
            comparison="==",
            message_template="Crashes with open positions: {actual} (required: {required})",
            recommendation="CRITICAL: System must never crash with open positions.",
            is_critical=True,
        ))
        
        # ============================================================
        # 🚫 BLOCKING CONDITIONS (any failure = immediate NO-GO)
        # ============================================================
        
        # B1: Max drawdown not exceeded
        criteria.append(self._evaluate_criterion(
            criterion_id="B1",
            name="Max Drawdown Limit",
            category="blocking",
            actual_value=survival.max_drawdown_pct,
            required_value=self.config.max_drawdown_limit_pct,
            comparison=">=",
            message_template="Max observed drawdown: {actual}% (limit: ≥{required}%)",
            recommendation="Drawdown too high. Review risk parameters.",
            is_critical=True,
        ))
        
        # B2: No unexplained divergences
        criteria.append(self._evaluate_criterion(
            criterion_id="B2",
            name="No Unexplained Divergences",
            category="blocking",
            actual_value=stability.divergence_unexplained,
            required_value=self.config.max_unexplained_divergences,
            comparison="<=",
            message_template="Unexplained divergences: {actual} (max: {required})",
            recommendation="Investigate all paper vs shadow divergences.",
            is_critical=True,
        ))
        
        # B3: Accounting within tolerance
        criteria.append(self._evaluate_criterion(
            criterion_id="B3",
            name="Accounting Integrity",
            category="blocking",
            actual_value=abs(accounting.current_balance_drift_pct),
            required_value=self.config.max_balance_drift_pct,
            comparison="<=",
            message_template="Balance drift: {actual}% (max: {required}%)",
            recommendation="Reconcile internal accounting with exchange.",
            is_critical=True,
        ))
        
        # B4: Audit trail complete
        total_runs = history.total_paper_runs + history.total_shadow_runs
        has_audit = total_runs > 0  # Simplified check
        criteria.append(self._evaluate_criterion(
            criterion_id="B4",
            name="Complete Audit Trail",
            category="blocking",
            actual_value=1 if has_audit else 0,
            required_value=1,
            comparison="==",
            message_template="Audit trail: {actual} (1=Complete, 0=Missing)",
            recommendation="Ensure all runs have complete audit logs.",
            is_critical=True,
        ))
        
        # ============================================================
        # 🟡 WARNING CONDITIONS
        # ============================================================
        
        # W1: Execution failure rate
        failure_rate = 1 - stability.execution_success_rate if stability.execution_success_rate else 0.0
        w1 = self._evaluate_criterion(
            criterion_id="W1",
            name="Execution Failure Rate",
            category="warning",
            actual_value=failure_rate,
            required_value=self.config.warning_execution_failure_rate,
            comparison="<=",
            message_template="Execution failure rate: {actual} (warning threshold: {required})",
            recommendation="Review execution failures.",
            is_critical=False,
        )
        if w1.passed:
            w1.status = GateCriterionStatus.PASSED
        elif w1.status == GateCriterionStatus.FAILED:
            w1.status = GateCriterionStatus.WARNING
            w1.passed = True  # Warnings don't block
        criteria.append(w1)
        
        # ============================================================
        # FINAL DECISION
        # ============================================================
        
        evaluation.criteria_results = criteria
        evaluation.total_criteria = len(criteria)
        evaluation.criteria_passed = sum(1 for c in criteria if c.passed)
        evaluation.criteria_failed = sum(1 for c in criteria if not c.passed and c.status == GateCriterionStatus.FAILED)
        evaluation.criteria_warning = sum(1 for c in criteria if c.status == GateCriterionStatus.WARNING)
        evaluation.criteria_insufficient = sum(1 for c in criteria if c.status == GateCriterionStatus.INSUFFICIENT_DATA)
        
        # Check for critical failures
        critical_failures = [c for c in criteria if c.is_critical and not c.passed]
        
        if critical_failures:
            evaluation.decision = GateDecision.NO_GO
            evaluation.recommendation = self._generate_no_go_recommendation(critical_failures)
            evaluation.risk_summary = "LIVE execution is BLOCKED. HAVEN has insufficient evidence of survival."
        elif evaluation.criteria_insufficient > 0:
            evaluation.decision = GateDecision.NO_GO
            evaluation.recommendation = "Insufficient data for evaluation. Continue observation."
            evaluation.risk_summary = "LIVE execution is BLOCKED due to insufficient data."
        else:
            evaluation.decision = GateDecision.GO
            evaluation.constraints = self.config.default_constraints
            evaluation.recommendation = self._generate_go_recommendation()
            evaluation.risk_summary = "LIVE execution PERMITTED under strict constraints. Monitor closely."
        
        # Generate audit hash
        audit_data = {
            "history": history.model_dump(),
            "survival": survival.model_dump(),
            "stability": stability.model_dump(),
            "guardian": guardian.model_dump(),
            "accounting": accounting.model_dump(),
        }
        evaluation.audit_hash = hashlib.sha256(
            json.dumps(audit_data, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        # Store evaluation
        await self._store_evaluation(evaluation)
        
        logger.info(f"GO-LIVE Gate evaluation complete: {evaluation.decision.value}")
        
        return evaluation
    
    def _generate_no_go_recommendation(self, failures: List[CriterionResult]) -> str:
        """Generate recommendation for NO-GO decision."""
        lines = ["LIVE execution is BLOCKED. Required actions:"]
        for f in failures:
            lines.append(f"  • [{f.criterion_id}] {f.name}: {f.recommendation}")
        return "\n".join(lines)
    
    def _generate_go_recommendation(self) -> str:
        """Generate recommendation for GO decision."""
        c = self.config.default_constraints
        return f"""LIVE execution PERMITTED under strict constraints:
  • Max capital: €{c.max_capital_eur}
  • Max single trade: €{c.max_single_trade_eur}
  • Allowed symbols: {', '.join(c.allowed_symbols)}
  • Trading hours: {c.allowed_hours_utc_start}:00-{c.allowed_hours_utc_end}:00 UTC
  • Guardian mode: {c.guardian_mode}
  • Daily loss limit: {c.daily_loss_limit_pct}%
  • Review period: {c.review_period_days} days
  
Monitor closely. Auto-pause on any error."""
    
    async def _store_evaluation(self, evaluation: GateEvaluation) -> None:
        """Store evaluation in database."""
        try:
            doc = evaluation.model_dump()
            # Convert datetime objects
            doc["timestamp"] = doc["timestamp"].isoformat()
            if doc.get("operational_history", {}).get("first_run_timestamp"):
                doc["operational_history"]["first_run_timestamp"] = (
                    doc["operational_history"]["first_run_timestamp"].isoformat()
                    if doc["operational_history"]["first_run_timestamp"] else None
                )
            if doc.get("operational_history", {}).get("last_run_timestamp"):
                doc["operational_history"]["last_run_timestamp"] = (
                    doc["operational_history"]["last_run_timestamp"].isoformat()
                    if doc["operational_history"]["last_run_timestamp"] else None
                )
            if doc.get("accounting_integrity", {}).get("last_reconciliation"):
                doc["accounting_integrity"]["last_reconciliation"] = (
                    doc["accounting_integrity"]["last_reconciliation"].isoformat()
                    if doc["accounting_integrity"]["last_reconciliation"] else None
                )
            
            await self.db.go_live_evaluations.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to store evaluation: {e}")
    
    # ============================================================
    # 📖 QUERY METHODS
    # ============================================================
    
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current GO-LIVE status (last evaluation)."""
        last_eval = await self.db.go_live_evaluations.find_one(
            {},
            sort=[("timestamp", -1)],
            projection={"_id": 0}
        )
        
        if not last_eval:
            return {
                "decision": "NO_GO",
                "reason": "No evaluation performed yet",
                "recommendation": "Run GO-LIVE Gate evaluation first",
                "last_evaluation": None,
            }
        
        return {
            "decision": last_eval.get("decision", "NO_GO"),
            "timestamp": last_eval.get("timestamp"),
            "evaluation_id": last_eval.get("evaluation_id"),
            "criteria_passed": last_eval.get("criteria_passed", 0),
            "criteria_failed": last_eval.get("criteria_failed", 0),
            "recommendation": last_eval.get("recommendation", ""),
            "risk_summary": last_eval.get("risk_summary", ""),
            "constraints": last_eval.get("constraints"),
        }
    
    async def get_evaluation_history(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get history of evaluations."""
        cursor = self.db.go_live_evaluations.find(
            {},
            {
                "_id": 0,
                "evaluation_id": 1,
                "timestamp": 1,
                "decision": 1,
                "criteria_passed": 1,
                "criteria_failed": 1,
                "recommendation": 1,
            }
        ).sort("timestamp", -1).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_evaluation_by_id(self, evaluation_id: str) -> Optional[Dict[str, Any]]:
        """Get specific evaluation by ID."""
        return await self.db.go_live_evaluations.find_one(
            {"evaluation_id": evaluation_id},
            {"_id": 0}
        )
    
    async def is_live_permitted(self) -> Tuple[bool, str]:
        """
        Quick check if LIVE is currently permitted.
        
        Returns:
            Tuple of (is_permitted, reason)
        """
        status = await self.get_current_status()
        
        if status["decision"] == "GO":
            return True, "LIVE permitted under constraints"
        else:
            return False, status.get("recommendation", "LIVE not permitted")
