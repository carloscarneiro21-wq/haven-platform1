"""
Sniper Hardening Service
========================
Evaluates and blocks unsafe sniper entries under DEX/MEV/illiquidity/infra instability.
Produces hardened profiles saved to agent_profile_versions.

Supports TWO MODES:
- Mode A: Dedicated Sniper Strategy (strategy_id = "sniper")
- Mode B: Sniper Mode for any agent (sniper_mode_enabled = true)

This is SIMULATION ONLY - no live trading modifications.
"""

import random
import math
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)


# ============ Enums ============

class GateStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class HardeningDecision(str, Enum):
    """Decision from hardening evaluation."""
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class VenueType(str, Enum):
    """Type of trading venue."""
    DEX = "DEX"
    CEX = "CEX"
    SIM_SANDBOX = "SIM_SANDBOX"


class HardeningMode(str, Enum):
    """Hardening mode type."""
    DEDICATED_SNIPER = "dedicated_sniper"  # Mode A
    SNIPER_MODE = "sniper_mode"  # Mode B - any agent


class GateName(str, Enum):
    LIQUIDITY_GATE = "LIQUIDITY_GATE"
    TAX_GATE = "TAX_GATE"
    HONEYPOT_GATE = "HONEYPOT_GATE"
    PRICE_IMPACT_GATE = "PRICE_IMPACT_GATE"
    MEV_GATE = "MEV_GATE"
    INFRA_STABILITY_GATE = "INFRA_STABILITY_GATE"
    VOLATILITY_GATE = "VOLATILITY_GATE"
    TOKEN_TRAP_GATE = "TOKEN_TRAP_GATE"  # Renamed from BLACKLIST_TRAP_GATE


# ============ Models ============

class GateResult(BaseModel):
    """Result of a single gate evaluation."""
    name: GateName
    status: GateStatus
    reason_code: str
    details: Dict[str, Any] = Field(default_factory=dict)
    threshold: Optional[float] = None
    actual_value: Optional[float] = None


class HardenedSniperParams(BaseModel):
    """Hardened sniper parameters."""
    min_pool_liquidity_usd: float = 75000  # Conservative default
    max_tax_pct: float = 3.0  # Stricter than default
    max_price_impact_pct: float = 2.0
    max_slippage_pct: float = 1.5
    max_trade_size_pct_of_liquidity: float = 0.5  # More conservative
    entry_delay_sec: int = 45  # Longer delay
    require_sell_simulation: bool = True
    require_honeypot_checks: bool = True
    block_if_blacklist_signals: bool = True
    block_if_trading_toggle_risk: bool = True
    max_retries: int = 2  # Fewer retries
    retry_backoff_ms: int = 1000  # Longer backoff


class HardenedConstraints(BaseModel):
    """Conservative constraints for hardened profile."""
    max_daily_dd_pct: float = 3.0  # Stricter than default
    max_weekly_dd_pct: float = 7.0
    max_slippage_pct: float = 1.5
    max_spread_pct: float = 0.3
    max_trades_per_min: int = 5  # Slower pace
    cooldown_after_loss_sec: int = 120  # Longer cooldown
    require_approval: bool = True  # Always require approval for paper_live
    kill_switch_on_faults: bool = True


class HardenedDexRules(BaseModel):
    """Strict DEX rules for hardened profile."""
    min_pool_liquidity_usd: float = 75000
    max_price_impact_pct: float = 1.5
    max_tax_pct: float = 3.0
    disallow_fee_on_transfer: bool = True
    disallow_honeypot_signals: bool = True
    allowed_routers: List[str] = Field(default_factory=list)
    approval_policy: str = "exact"


class HardenedInfraRules(BaseModel):
    """Strict infra rules for hardened profile."""
    ws_drop_tolerance_per_hour: int = 3
    max_api_latency_ms: int = 1500
    max_429_per_min: int = 2
    stale_data_limit_sec: int = 20


class OrderIntent(BaseModel):
    """Order intent for evaluation context."""
    side: str = "buy"  # "buy" or "sell"
    desired_qty: float = 0
    slippage_tolerance: float = 1.0  # percentage


class SniperModeConfig(BaseModel):
    """Configuration for Sniper Mode on any agent (Mode B)."""
    enabled: bool = True
    min_pool_liquidity_usd: float = 75000
    max_tax_pct: float = 3.0
    max_price_impact_pct: float = 2.0
    max_slippage_pct: float = 1.5
    max_trade_size_pct_of_liquidity: float = 0.5
    entry_delay_sec: int = 45
    require_sell_simulation: bool = True
    block_if_blacklist_signals: bool = True
    block_if_trading_toggle_risk: bool = True


class EvaluationInput(BaseModel):
    """Input for sniper hardening evaluation."""
    run_id: str
    agent_id: str
    symbol: str
    strategy_id: str = "sniper"  # For Mode A or the agent's actual strategy
    severity: str = "MED"
    packs: Dict[str, bool] = Field(default_factory=lambda: {"crash": True, "dex": True, "infra": True})
    overrides: Optional[Dict[str, Any]] = None
    
    # Mode selection
    mode: HardeningMode = HardeningMode.DEDICATED_SNIPER
    venue_type: VenueType = VenueType.SIM_SANDBOX
    
    # Order intent
    order_intent: Optional[OrderIntent] = None
    
    # Current agent params (for Mode B)
    current_agent_params: Optional[Dict[str, Any]] = None
    sniper_mode_config: Optional[SniperModeConfig] = None
    
    # Simulation context data (from sandbox run)
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
    max_tx_limit: Optional[bool] = None  # Token has maxTx limit
    max_wallet_limit: Optional[bool] = None  # Token has maxWallet limit


class EvaluationOutput(BaseModel):
    """Output of sniper hardening evaluation."""
    evaluation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    run_id: str
    agent_id: str
    strategy_id: str = "sniper"
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Mode info
    mode: HardeningMode = HardeningMode.DEDICATED_SNIPER
    venue_type: VenueType = VenueType.SIM_SANDBOX
    
    gates: List[GateResult]
    overall_status: GateStatus
    decision: HardeningDecision = HardeningDecision.ALLOW  # ALLOW/WARN/BLOCK
    passed_count: int = 0
    failed_count: int = 0
    warn_count: int = 0
    
    risk_score: float  # 0-100, higher = more risky
    mev_risk: float  # 0-100
    
    recommended_profile: Optional[Dict[str, Any]] = None
    recommended_position_size_pct: float = 100  # % of original size
    suggested_params: Optional[Dict[str, Any]] = None
    
    reason_codes: List[str] = Field(default_factory=list)
    top_failing_gate: Optional[str] = None  # Name of the most critical failing gate


class HardenedProfileOutput(BaseModel):
    """Output when generating a hardened profile."""
    profile_id: str
    agent_id: str
    strategy_id: str
    source_run_id: str
    version: int
    tags: List[str]
    params: Dict[str, Any]
    constraints: Dict[str, Any]
    dex_rules: Dict[str, Any]
    infra_rules: Dict[str, Any]
    evaluation_id: str
    risk_score: float
    created_at: datetime


# ============ Sniper Hardening Service ============

class SniperHardeningService:
    """
    Evaluates sniper entry conditions and generates hardened profiles.
    
    All operations are SIMULATION ONLY.
    """
    
    # Severity multipliers for thresholds
    SEVERITY_MULTIPLIERS = {
        "LOW": 1.2,   # More lenient
        "MED": 1.0,   # Normal
        "HIGH": 0.8,  # Stricter
        "APOC": 0.6,  # Very strict
    }
    
    # Base thresholds
    BASE_THRESHOLDS = {
        "min_pool_liquidity_usd": 50000,
        "max_tax_pct": 5.0,
        "max_price_impact_pct": 3.0,
        "max_slippage_pct": 2.0,
        "max_trade_size_pct_of_liquidity": 1.0,
        "ws_drop_tolerance_per_hour": 5,
        "max_api_latency_ms": 2000,
        "stale_data_limit_sec": 30,
        "max_spread_pct": 0.5,
        "mev_risk_threshold": 50,
    }
    
    def __init__(self, db=None, seed: int = None):
        self._db = db
        self._rng = random.Random(seed) if seed else random.Random()
        
    def _get_severity_multiplier(self, severity: str) -> float:
        return self.SEVERITY_MULTIPLIERS.get(severity.upper(), 1.0)
    
    def _apply_severity(self, base_value: float, severity: str, invert: bool = False) -> float:
        """Apply severity multiplier to a threshold."""
        multiplier = self._get_severity_multiplier(severity)
        if invert:
            # For "more is better" values like liquidity
            return base_value * (2 - multiplier)
        return base_value * multiplier
    
    def _evaluate_liquidity_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        LIQUIDITY_GATE: Check pool liquidity and trade size ratio.
        """
        threshold = self._apply_severity(
            self.BASE_THRESHOLDS["min_pool_liquidity_usd"], 
            input_data.severity,
            invert=True  # Higher severity = higher required liquidity
        )
        
        pool_liquidity = input_data.pool_liquidity_usd or 0
        trade_size = input_data.trade_size_usd or 0
        
        if pool_liquidity < threshold:
            return GateResult(
                name=GateName.LIQUIDITY_GATE,
                status=GateStatus.FAIL,
                reason_code="INSUFFICIENT_LIQUIDITY",
                details={
                    "pool_liquidity_usd": pool_liquidity,
                    "min_required": threshold,
                    "deficit_pct": ((threshold - pool_liquidity) / threshold * 100) if threshold > 0 else 0
                },
                threshold=threshold,
                actual_value=pool_liquidity,
            )
        
        # Check trade size ratio
        max_size_pct = self._apply_severity(
            self.BASE_THRESHOLDS["max_trade_size_pct_of_liquidity"],
            input_data.severity
        )
        
        if pool_liquidity > 0:
            size_ratio = (trade_size / pool_liquidity) * 100
            if size_ratio > max_size_pct:
                return GateResult(
                    name=GateName.LIQUIDITY_GATE,
                    status=GateStatus.WARN,
                    reason_code="TRADE_SIZE_TOO_LARGE",
                    details={
                        "trade_size_pct_of_liquidity": size_ratio,
                        "max_allowed": max_size_pct,
                    },
                    threshold=max_size_pct,
                    actual_value=size_ratio,
                )
        
        return GateResult(
            name=GateName.LIQUIDITY_GATE,
            status=GateStatus.PASS,
            reason_code="LIQUIDITY_OK",
            details={"pool_liquidity_usd": pool_liquidity, "trade_size_usd": trade_size},
            threshold=threshold,
            actual_value=pool_liquidity,
        )
    
    def _evaluate_tax_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        TAX_GATE: Check for fee-on-transfer tax.
        """
        threshold = self._apply_severity(
            self.BASE_THRESHOLDS["max_tax_pct"],
            input_data.severity
        )
        
        detected_tax = input_data.detected_tax_pct or 0
        
        if detected_tax > threshold:
            return GateResult(
                name=GateName.TAX_GATE,
                status=GateStatus.FAIL,
                reason_code="TAX_TOO_HIGH",
                details={
                    "detected_tax_pct": detected_tax,
                    "max_allowed": threshold,
                },
                threshold=threshold,
                actual_value=detected_tax,
            )
        
        if detected_tax > threshold * 0.6:
            return GateResult(
                name=GateName.TAX_GATE,
                status=GateStatus.WARN,
                reason_code="TAX_APPROACHING_LIMIT",
                details={"detected_tax_pct": detected_tax, "threshold": threshold},
                threshold=threshold,
                actual_value=detected_tax,
            )
        
        return GateResult(
            name=GateName.TAX_GATE,
            status=GateStatus.PASS,
            reason_code="TAX_OK",
            details={"detected_tax_pct": detected_tax},
            threshold=threshold,
            actual_value=detected_tax,
        )
    
    def _evaluate_honeypot_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        HONEYPOT_GATE: Check if sell simulation passed.
        """
        sell_passed = input_data.sell_simulation_passed
        
        if sell_passed is False:
            return GateResult(
                name=GateName.HONEYPOT_GATE,
                status=GateStatus.FAIL,
                reason_code="SELL_SIMULATION_FAILED",
                details={"sell_simulation_passed": False, "likely_honeypot": True},
            )
        
        if sell_passed is None:
            return GateResult(
                name=GateName.HONEYPOT_GATE,
                status=GateStatus.WARN,
                reason_code="SELL_SIMULATION_NOT_RUN",
                details={"sell_simulation_passed": None, "risk": "unknown"},
            )
        
        return GateResult(
            name=GateName.HONEYPOT_GATE,
            status=GateStatus.PASS,
            reason_code="HONEYPOT_CHECK_OK",
            details={"sell_simulation_passed": True},
        )
    
    def _evaluate_price_impact_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        PRICE_IMPACT_GATE: Check estimated price impact.
        """
        threshold = self._apply_severity(
            self.BASE_THRESHOLDS["max_price_impact_pct"],
            input_data.severity
        )
        
        impact = input_data.estimated_price_impact_pct or 0
        
        if impact > threshold:
            return GateResult(
                name=GateName.PRICE_IMPACT_GATE,
                status=GateStatus.FAIL,
                reason_code="PRICE_IMPACT_TOO_HIGH",
                details={"estimated_impact_pct": impact, "max_allowed": threshold},
                threshold=threshold,
                actual_value=impact,
            )
        
        if impact > threshold * 0.7:
            return GateResult(
                name=GateName.PRICE_IMPACT_GATE,
                status=GateStatus.WARN,
                reason_code="PRICE_IMPACT_HIGH",
                details={"estimated_impact_pct": impact, "threshold": threshold},
                threshold=threshold,
                actual_value=impact,
            )
        
        return GateResult(
            name=GateName.PRICE_IMPACT_GATE,
            status=GateStatus.PASS,
            reason_code="PRICE_IMPACT_OK",
            details={"estimated_impact_pct": impact},
            threshold=threshold,
            actual_value=impact,
        )
    
    def _evaluate_mev_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        MEV_GATE: Compute MEV risk score and evaluate.
        """
        # Calculate MEV risk score (0-100)
        mev_events = input_data.mev_events_count or 0
        slippage = input_data.avg_slippage_pct or 0
        trade_size = input_data.trade_size_usd or 0
        liquidity = input_data.pool_liquidity_usd or 100000
        
        # Base risk from MEV events
        event_risk = min(mev_events * 15, 50)
        
        # Risk from slippage (higher slippage = more MEV opportunity)
        slippage_risk = min(slippage * 10, 30)
        
        # Risk from trade size vs liquidity
        size_ratio = (trade_size / liquidity * 100) if liquidity > 0 else 0
        size_risk = min(size_ratio * 5, 20)
        
        mev_risk = event_risk + slippage_risk + size_risk
        mev_risk = min(mev_risk, 100)
        
        # Apply severity
        threshold = self._apply_severity(
            self.BASE_THRESHOLDS["mev_risk_threshold"],
            input_data.severity
        )
        
        if mev_risk > threshold:
            return GateResult(
                name=GateName.MEV_GATE,
                status=GateStatus.FAIL,
                reason_code="MEV_RISK_TOO_HIGH",
                details={
                    "mev_risk_score": mev_risk,
                    "threshold": threshold,
                    "mev_events": mev_events,
                    "slippage_pct": slippage,
                    "recommended_size_reduction_pct": min(50, mev_risk - threshold),
                },
                threshold=threshold,
                actual_value=mev_risk,
            )
        
        if mev_risk > threshold * 0.6:
            return GateResult(
                name=GateName.MEV_GATE,
                status=GateStatus.WARN,
                reason_code="MEV_RISK_ELEVATED",
                details={
                    "mev_risk_score": mev_risk,
                    "threshold": threshold,
                    "recommendation": "Consider reducing position size",
                },
                threshold=threshold,
                actual_value=mev_risk,
            )
        
        return GateResult(
            name=GateName.MEV_GATE,
            status=GateStatus.PASS,
            reason_code="MEV_RISK_OK",
            details={"mev_risk_score": mev_risk},
            threshold=threshold,
            actual_value=mev_risk,
        )
    
    def _evaluate_infra_stability_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        INFRA_STABILITY_GATE: Check infrastructure stability.
        """
        ws_drops = input_data.ws_drops_per_hour or 0
        latency = input_data.api_latency_ms or 0
        stale_data = input_data.stale_data_detected or False
        
        ws_threshold = int(self._apply_severity(
            self.BASE_THRESHOLDS["ws_drop_tolerance_per_hour"],
            input_data.severity
        ))
        
        latency_threshold = self._apply_severity(
            self.BASE_THRESHOLDS["max_api_latency_ms"],
            input_data.severity
        )
        
        issues = []
        status = GateStatus.PASS
        
        if ws_drops > ws_threshold:
            issues.append(f"WS drops ({ws_drops}) > threshold ({ws_threshold})")
            status = GateStatus.FAIL
        
        if latency > latency_threshold:
            issues.append(f"Latency ({latency}ms) > threshold ({latency_threshold}ms)")
            status = GateStatus.FAIL if status == GateStatus.FAIL else GateStatus.WARN
        
        if stale_data:
            issues.append("Stale data detected")
            status = GateStatus.FAIL
        
        if status == GateStatus.FAIL:
            return GateResult(
                name=GateName.INFRA_STABILITY_GATE,
                status=GateStatus.FAIL,
                reason_code="INFRA_UNSTABLE",
                details={
                    "ws_drops_per_hour": ws_drops,
                    "api_latency_ms": latency,
                    "stale_data": stale_data,
                    "issues": issues,
                },
            )
        
        if status == GateStatus.WARN:
            return GateResult(
                name=GateName.INFRA_STABILITY_GATE,
                status=GateStatus.WARN,
                reason_code="INFRA_DEGRADED",
                details={
                    "ws_drops_per_hour": ws_drops,
                    "api_latency_ms": latency,
                    "issues": issues,
                },
            )
        
        return GateResult(
            name=GateName.INFRA_STABILITY_GATE,
            status=GateStatus.PASS,
            reason_code="INFRA_OK",
            details={
                "ws_drops_per_hour": ws_drops,
                "api_latency_ms": latency,
            },
        )
    
    def _evaluate_volatility_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        VOLATILITY_GATE: Check volatility regime and spread.
        """
        regime_shift = input_data.volatility_regime_shift or False
        spread = input_data.spread_pct or 0
        
        spread_threshold = self._apply_severity(
            self.BASE_THRESHOLDS["max_spread_pct"],
            input_data.severity
        )
        
        if regime_shift and spread > spread_threshold:
            return GateResult(
                name=GateName.VOLATILITY_GATE,
                status=GateStatus.FAIL,
                reason_code="VOLATILITY_REGIME_SHIFT_WITH_WIDE_SPREAD",
                details={
                    "volatility_regime_shift": True,
                    "spread_pct": spread,
                    "spread_threshold": spread_threshold,
                },
                threshold=spread_threshold,
                actual_value=spread,
            )
        
        if regime_shift:
            return GateResult(
                name=GateName.VOLATILITY_GATE,
                status=GateStatus.WARN,
                reason_code="VOLATILITY_REGIME_SHIFT",
                details={"volatility_regime_shift": True, "spread_pct": spread},
            )
        
        if spread > spread_threshold:
            return GateResult(
                name=GateName.VOLATILITY_GATE,
                status=GateStatus.WARN,
                reason_code="SPREAD_WIDE",
                details={"spread_pct": spread, "threshold": spread_threshold},
                threshold=spread_threshold,
                actual_value=spread,
            )
        
        return GateResult(
            name=GateName.VOLATILITY_GATE,
            status=GateStatus.PASS,
            reason_code="VOLATILITY_OK",
            details={"spread_pct": spread},
        )
    
    def _evaluate_token_trap_gate(self, input_data: EvaluationInput) -> GateResult:
        """
        TOKEN_TRAP_GATE: Check for blacklist, maxTx/maxWallet, and trading toggle risks.
        """
        blacklist_signals = input_data.blacklist_signals or False
        toggle_risk = input_data.trading_toggle_risk or False
        max_tx = input_data.max_tx_limit or False
        max_wallet = input_data.max_wallet_limit or False
        
        issues = []
        
        if blacklist_signals:
            issues.append("blacklist_signals")
        if toggle_risk:
            issues.append("trading_toggle_risk")
        if max_tx:
            issues.append("max_tx_limit")
        if max_wallet:
            issues.append("max_wallet_limit")
        
        if blacklist_signals or toggle_risk:
            return GateResult(
                name=GateName.TOKEN_TRAP_GATE,
                status=GateStatus.FAIL,
                reason_code="TOKEN_TRAP_DETECTED",
                details={
                    "blacklist_signals": blacklist_signals,
                    "trading_toggle_risk": toggle_risk,
                    "max_tx_limit": max_tx,
                    "max_wallet_limit": max_wallet,
                    "issues": issues,
                },
            )
        
        if max_tx or max_wallet:
            return GateResult(
                name=GateName.TOKEN_TRAP_GATE,
                status=GateStatus.WARN,
                reason_code="TOKEN_RESTRICTIONS_DETECTED",
                details={
                    "max_tx_limit": max_tx,
                    "max_wallet_limit": max_wallet,
                    "issues": issues,
                },
            )
        
        return GateResult(
            name=GateName.TOKEN_TRAP_GATE,
            status=GateStatus.PASS,
            reason_code="NO_TRAP_SIGNALS",
            details={
                "blacklist_signals": False,
                "trading_toggle_risk": False,
                "max_tx_limit": False,
                "max_wallet_limit": False,
            },
        )
    
    def _calculate_risk_score(self, gates: List[GateResult]) -> float:
        """Calculate overall risk score from gate results."""
        base_score = 0
        
        for gate in gates:
            if gate.status == GateStatus.FAIL:
                base_score += 25
            elif gate.status == GateStatus.WARN:
                base_score += 10
        
        return min(base_score, 100)
    
    def _calculate_mev_risk(self, input_data: EvaluationInput) -> float:
        """Calculate MEV-specific risk score."""
        mev_events = input_data.mev_events_count or 0
        slippage = input_data.avg_slippage_pct or 0
        trade_size = input_data.trade_size_usd or 0
        liquidity = input_data.pool_liquidity_usd or 100000
        
        event_risk = min(mev_events * 15, 50)
        slippage_risk = min(slippage * 10, 30)
        size_ratio = (trade_size / liquidity * 100) if liquidity > 0 else 0
        size_risk = min(size_ratio * 5, 20)
        
        return min(event_risk + slippage_risk + size_risk, 100)
    
    def _calculate_recommended_position_size(self, risk_score: float, mev_risk: float) -> float:
        """Calculate recommended position size as percentage of original."""
        combined_risk = (risk_score + mev_risk) / 2
        
        if combined_risk < 20:
            return 100
        elif combined_risk < 40:
            return 80
        elif combined_risk < 60:
            return 60
        elif combined_risk < 80:
            return 40
        else:
            return 20
    
    def _generate_hardened_params(self, input_data: EvaluationInput, 
                                   evaluation: EvaluationOutput) -> Dict[str, Any]:
        """Generate hardened sniper parameters based on evaluation."""
        severity = input_data.severity.upper()
        
        # Start with conservative defaults
        params = HardenedSniperParams()
        
        # Adjust based on severity
        multiplier = self._get_severity_multiplier(severity)
        
        # More conservative as risk increases
        risk_factor = 1 + (evaluation.risk_score / 100)
        
        return {
            "min_pool_liquidity_usd": params.min_pool_liquidity_usd * risk_factor,
            "max_tax_pct": params.max_tax_pct * multiplier,
            "max_price_impact_pct": params.max_price_impact_pct * multiplier,
            "max_slippage_pct": params.max_slippage_pct * multiplier,
            "max_trade_size_pct_of_liquidity": params.max_trade_size_pct_of_liquidity * multiplier,
            "entry_delay_sec": int(params.entry_delay_sec * risk_factor),
            "require_sell_simulation": True,
            "require_honeypot_checks": True,
            "block_if_blacklist_signals": True,
            "block_if_trading_toggle_risk": True,
            "max_retries": params.max_retries,
            "retry_backoff_ms": int(params.retry_backoff_ms * risk_factor),
        }
    
    async def evaluate(self, input_data: EvaluationInput) -> EvaluationOutput:
        """
        Run all gates and evaluate sniper entry conditions.
        
        Supports both modes:
        - Mode A: Dedicated Sniper Strategy
        - Mode B: Sniper Mode for any agent
        
        SIMULATION ONLY - no live calls.
        """
        # Apply sniper_mode_config overrides if provided (Mode B)
        if input_data.sniper_mode_config and input_data.mode == HardeningMode.SNIPER_MODE:
            config = input_data.sniper_mode_config
            # Override thresholds based on sniper_mode_config
            self.BASE_THRESHOLDS = {
                "min_pool_liquidity_usd": config.min_pool_liquidity_usd,
                "max_tax_pct": config.max_tax_pct,
                "max_price_impact_pct": config.max_price_impact_pct,
                "max_slippage_pct": config.max_slippage_pct,
                "max_trade_size_pct_of_liquidity": config.max_trade_size_pct_of_liquidity,
                "ws_drop_tolerance_per_hour": 5,
                "max_api_latency_ms": 2000,
                "stale_data_limit_sec": 30,
                "max_spread_pct": 0.5,
                "mev_risk_threshold": 50,
            }
        
        gates = [
            self._evaluate_liquidity_gate(input_data),
            self._evaluate_tax_gate(input_data),
            self._evaluate_honeypot_gate(input_data),
            self._evaluate_price_impact_gate(input_data),
            self._evaluate_mev_gate(input_data),
            self._evaluate_infra_stability_gate(input_data),
            self._evaluate_volatility_gate(input_data),
            self._evaluate_token_trap_gate(input_data),
        ]
        
        # Count statuses
        passed = sum(1 for g in gates if g.status == GateStatus.PASS)
        failed = sum(1 for g in gates if g.status == GateStatus.FAIL)
        warned = sum(1 for g in gates if g.status == GateStatus.WARN)
        
        # Determine overall status
        if failed > 0:
            overall_status = GateStatus.FAIL
        elif warned > 0:
            overall_status = GateStatus.WARN
        else:
            overall_status = GateStatus.PASS
        
        # Determine decision (ALLOW/WARN/BLOCK)
        if failed > 0:
            decision = HardeningDecision.BLOCK
        elif warned > 0:
            decision = HardeningDecision.WARN
        else:
            decision = HardeningDecision.ALLOW
        
        # Find top failing gate
        top_failing = None
        for g in gates:
            if g.status == GateStatus.FAIL:
                top_failing = g.name.value
                break
        
        # Calculate scores
        risk_score = self._calculate_risk_score(gates)
        mev_risk = self._calculate_mev_risk(input_data)
        
        # Recommended position size
        position_size = self._calculate_recommended_position_size(risk_score, mev_risk)
        
        # Collect reason codes
        reason_codes = [g.reason_code for g in gates if g.status != GateStatus.PASS]
        
        output = EvaluationOutput(
            run_id=input_data.run_id,
            agent_id=input_data.agent_id,
            strategy_id=input_data.strategy_id,
            symbol=input_data.symbol,
            mode=input_data.mode,
            venue_type=input_data.venue_type,
            gates=gates,
            overall_status=overall_status,
            decision=decision,
            passed_count=passed,
            failed_count=failed,
            warn_count=warned,
            risk_score=risk_score,
            mev_risk=mev_risk,
            recommended_position_size_pct=position_size,
            reason_codes=reason_codes,
            top_failing_gate=top_failing,
        )
        
        # Generate recommended profile (different structure for Mode A vs Mode B)
        hardened_params = self._generate_hardened_params(input_data, output)
        
        if input_data.mode == HardeningMode.DEDICATED_SNIPER:
            # Mode A: params.sniper
            output.recommended_profile = {
                "params": {"sniper": hardened_params},
                "constraints": HardenedConstraints().model_dump(),
                "dex_rules": HardenedDexRules().model_dump(),
                "infra_rules": HardenedInfraRules().model_dump(),
            }
        else:
            # Mode B: params.sniper_mode
            output.recommended_profile = {
                "params": {
                    "sniper_mode": {
                        "enabled": True,
                        **hardened_params
                    }
                },
                "constraints": HardenedConstraints().model_dump(),
                "dex_rules": HardenedDexRules().model_dump(),
                "infra_rules": HardenedInfraRules().model_dump(),
            }
        
        output.suggested_params = hardened_params
        
        mode_str = "dedicated_sniper" if input_data.mode == HardeningMode.DEDICATED_SNIPER else "sniper_mode"
        logger.info(f"[SIMULATION] Sniper hardening evaluation ({mode_str}): {decision.value} "
                   f"(risk={risk_score:.1f}, mev={mev_risk:.1f})")
        
        return output
    
    async def generate_hardened_profile(
        self,
        evaluation: EvaluationOutput,
        strategy_id: str = "sniper",
        label: str = "",
        severity: str = "MED",
    ) -> HardenedProfileOutput:
        """
        Generate and persist a hardened profile based on evaluation.
        
        For Mode A (dedicated sniper): saves under params.sniper
        For Mode B (sniper mode): saves under params.sniper_mode
        
        Returns the created profile.
        """
        from services.sandbox.learning_models import ProfileSource
        
        profile_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc)
        
        # Determine version number
        version = 1
        if self._db is not None:
            existing = await self._db.agent_profile_versions.count_documents({
                "agent_id": evaluation.agent_id,
                "strategy_id": strategy_id,
            })
            version = existing + 1
        
        # Build tags based on mode
        if evaluation.mode == HardeningMode.DEDICATED_SNIPER:
            tags = [
                "sniper_hardened",
                severity.lower(),
                "sandbox",
                f"risk_{int(evaluation.risk_score)}",
                f"mev_{int(evaluation.mev_risk)}",
            ]
        else:
            # Mode B tags
            tags = [
                "sniper_mode",
                severity.lower(),
                "sandbox",
                f"risk_{int(evaluation.risk_score)}",
                f"mev_{int(evaluation.mev_risk)}",
            ]
        
        if label:
            tags.append(label)
        
        profile_data = {
            "profile_id": profile_id,
            "agent_id": evaluation.agent_id,
            "strategy_id": strategy_id,
            "mode": evaluation.mode.value,
            "source": ProfileSource.SANDBOX.value,
            "source_run_id": evaluation.run_id,
            "version": version,
            "label": label or f"Hardened Profile (Risk: {evaluation.risk_score:.0f})",
            "tags": tags,
            "params": evaluation.recommended_profile["params"],
            "constraints": evaluation.recommended_profile["constraints"],
            "dex_rules": evaluation.recommended_profile["dex_rules"],
            "infra_rules": evaluation.recommended_profile["infra_rules"],
            "created_at": now.isoformat(),
        }
        
        # Persist to database
        if self._db is not None:
            await self._db.agent_profile_versions.insert_one(profile_data)
            logger.info(f"[SIMULATION] Created hardened profile: {profile_id}")
        
        return HardenedProfileOutput(
            profile_id=profile_id,
            agent_id=evaluation.agent_id,
            strategy_id=strategy_id,
            source_run_id=evaluation.run_id,
            version=version,
            tags=tags,
            params=evaluation.recommended_profile["params"],
            constraints=evaluation.recommended_profile["constraints"],
            dex_rules=evaluation.recommended_profile["dex_rules"],
            infra_rules=evaluation.recommended_profile["infra_rules"],
            evaluation_id=evaluation.evaluation_id,
            risk_score=evaluation.risk_score,
            created_at=now,
        )
    
    async def get_evaluation_by_run(
        self, 
        run_id: str, 
        agent_id: str = None
    ) -> List[Dict[str, Any]]:
        """Get stored evaluations for a sandbox run."""
        if self._db is None:
            return []
        
        query = {"run_id": run_id}
        if agent_id:
            query["agent_id"] = agent_id
        
        cursor = self._db.sniper_hardening_evaluations.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1)
        
        return await cursor.to_list(length=100)
    
    async def store_evaluation(self, evaluation: EvaluationOutput) -> None:
        """Store evaluation result."""
        if self._db is None:
            return
        
        await self._db.sniper_hardening_evaluations.insert_one({
            **evaluation.model_dump(),
            "timestamp": evaluation.timestamp.isoformat(),
            "tag": "SIMULATION",
        })
    
    async def store_learning_metrics(
        self,
        run_id: str,
        agent_id: str,
        evaluation: EvaluationOutput,
        blocked_by_reason: Dict[str, int] = None,
    ) -> None:
        """Store sniper-specific learning metrics."""
        if self._db is None:
            return
        
        metrics = {
            "run_id": run_id,
            "agent_id": agent_id,
            "strategy_id": "sniper",
            "profile_id": "",
            "symbol": evaluation.symbol,
            "metrics": {
                "risk_score": evaluation.risk_score,
                "mev_risk": evaluation.mev_risk,
                "mev_hits_est": 0,  # Could be populated from evaluation
                "blocked_trades_by_reason": blocked_by_reason or {},
                "gate_results": {
                    "passed": evaluation.passed_count,
                    "failed": evaluation.failed_count,
                    "warned": evaluation.warn_count,
                },
                "reason_codes": evaluation.reason_codes,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tag": "SIMULATION",
        }
        
        await self._db.learning_metrics.insert_one(metrics)
