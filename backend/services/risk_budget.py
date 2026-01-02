"""
Risk Budget Allocator for Capital Growth Module
===============================================

Manages capital allocation between:
- Core bucket (60%): For MM (steady gains)
- Edge bucket (40%): For MOM (acceleration)
- Reserve bucket (0-10%): Safety buffer

Rules:
- With 100€, only ONE primary agent at a time
- Multi-agent only allowed when capital >= threshold
- OWNER can override restrictions
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum

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

class BucketType(str, Enum):
    """Budget bucket types."""
    CORE = "CORE"      # MM steady gains
    EDGE = "EDGE"      # MOM acceleration
    RESERVE = "RESERVE"  # Safety buffer


class AllocationStatus(str, Enum):
    """Status of allocation request."""
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    PARTIAL = "PARTIAL"  # Approved with reduced amount


# ============ Models ============

class BucketState(BaseModel):
    """State of a budget bucket."""
    bucket_type: BucketType
    allocated_pct: float = Field(description="% of total capital allocated")
    available_eur: float = Field(description="Available EUR in this bucket")
    in_use_eur: float = Field(description="Currently deployed EUR")
    max_single_trade_eur: float = Field(description="Max EUR per trade")


class AllocationRequest(BaseModel):
    """Request to allocate capital for a trade."""
    agent_id: str
    agent_type: str  # "MM" or "MOM"
    bucket_type: BucketType
    requested_eur: float
    symbol: str


class AllocationResult(BaseModel):
    """Result of allocation request."""
    status: AllocationStatus
    approved_eur: float = 0.0
    bucket_type: BucketType
    reasons: List[str] = []
    warnings: List[str] = []


class PortfolioState(BaseModel):
    """Overall portfolio state."""
    total_capital_eur: float
    available_capital_eur: float
    deployed_capital_eur: float
    
    core_bucket: BucketState
    edge_bucket: BucketState
    reserve_bucket: BucketState
    
    active_agents: Dict[str, str] = {}  # agent_id -> agent_type
    allow_multi_agent: bool = False
    
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Risk Budget Service ============

class RiskBudgetService:
    """
    Capital allocation service for growth module.
    
    Features:
    - Bucket-based allocation (Core/Edge/Reserve)
    - Single-agent enforcement for micro-capital
    - Concurrency control
    - Position sizing
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
        
        # Default allocations
        self._default_allocations = {
            BucketType.CORE: 60.0,
            BucketType.EDGE: 40.0,
            BucketType.RESERVE: 0.0,
        }
        
        self._state: Optional[PortfolioState] = None
        self._initialized = False
    
    async def initialize(self, total_capital_eur: float) -> None:
        """Initialize risk budget with total capital."""
        config = await self._get_config()
        
        # Calculate bucket allocations
        core_pct = config.get("core_pct", 60.0)
        edge_pct = config.get("edge_pct", 40.0)
        reserve_pct = config.get("reserve_pct", 0.0)
        
        # Normalize to 100%
        total_pct = core_pct + edge_pct + reserve_pct
        if total_pct != 100.0:
            factor = 100.0 / total_pct
            core_pct *= factor
            edge_pct *= factor
            reserve_pct *= factor
        
        core_eur = total_capital_eur * (core_pct / 100)
        edge_eur = total_capital_eur * (edge_pct / 100)
        reserve_eur = total_capital_eur * (reserve_pct / 100)
        
        # Max single trade sizing (10% of bucket for micro-capital)
        max_trade_factor = 0.10 if total_capital_eur < 500 else 0.20
        
        self._state = PortfolioState(
            total_capital_eur=total_capital_eur,
            available_capital_eur=total_capital_eur,
            deployed_capital_eur=0.0,
            core_bucket=BucketState(
                bucket_type=BucketType.CORE,
                allocated_pct=core_pct,
                available_eur=core_eur,
                in_use_eur=0.0,
                max_single_trade_eur=core_eur * max_trade_factor,
            ),
            edge_bucket=BucketState(
                bucket_type=BucketType.EDGE,
                allocated_pct=edge_pct,
                available_eur=edge_eur,
                in_use_eur=0.0,
                max_single_trade_eur=edge_eur * max_trade_factor,
            ),
            reserve_bucket=BucketState(
                bucket_type=BucketType.RESERVE,
                allocated_pct=reserve_pct,
                available_eur=reserve_eur,
                in_use_eur=0.0,
                max_single_trade_eur=0.0,  # Reserve not for trading
            ),
            allow_multi_agent=total_capital_eur >= config.get("min_capital_for_multi", 500.0),
        )
        
        self._initialized = True
        logger.info(f"RiskBudget initialized: {total_capital_eur}€ (Core: {core_eur:.2f}€, Edge: {edge_eur:.2f}€)")
    
    async def _get_config(self) -> Dict[str, Any]:
        """Get risk budget config."""
        if self.system_config_service:
            config = await self.system_config_service.get_config()
            concurrency = config.concurrency.model_dump()
            budget = config.risk_budget.model_dump()
            return {**budget, **concurrency}
        
        return {
            "core_pct": 60.0,
            "edge_pct": 40.0,
            "reserve_pct": 0.0,
            "allow_only_one_primary": True,
            "min_capital_for_multi": 500.0,
            "owner_can_override": True,
            "max_concurrent_agents": 1,
        }
    
    async def request_allocation(
        self,
        request: AllocationRequest,
        user_role: str = "user",
    ) -> AllocationResult:
        """
        Request capital allocation for a trade.
        
        Args:
            request: Allocation request details
            user_role: User's role (for override checks)
        
        Returns:
            AllocationResult with approved amount
        """
        if not self._state:
            return AllocationResult(
                status=AllocationStatus.DENIED,
                bucket_type=request.bucket_type,
                reasons=["RiskBudget not initialized"],
            )
        
        result = AllocationResult(
            bucket_type=request.bucket_type,
        )
        
        config = await self._get_config()
        
        # === Concurrency Check ===
        active_count = len(self._state.active_agents)
        max_concurrent = config.get("max_concurrent_agents", 1)
        
        # Check if this agent is already active
        is_existing_agent = request.agent_id in self._state.active_agents
        
        if not is_existing_agent:
            # New agent trying to join
            if active_count >= max_concurrent:
                # Check if multi-agent is allowed
                if not self._state.allow_multi_agent:
                    # Check for OWNER override
                    if user_role.upper() == "OWNER" and config.get("owner_can_override", True):
                        result.warnings.append("OWNER override: bypassing single-agent restriction")
                    else:
                        result.status = AllocationStatus.DENIED
                        result.reasons.append(
                            f"Single-agent mode enforced (capital < {config.get('min_capital_for_multi', 500)}€). "
                            f"Active: {list(self._state.active_agents.values())}"
                        )
                        await self._log_denial(request, result)
                        return result
                else:
                    if active_count >= max_concurrent:
                        result.status = AllocationStatus.DENIED
                        result.reasons.append(
                            f"Max concurrent agents reached: {active_count}/{max_concurrent}"
                        )
                        await self._log_denial(request, result)
                        return result
        
        # === Get Bucket ===
        bucket = self._get_bucket(request.bucket_type)
        if not bucket:
            result.status = AllocationStatus.DENIED
            result.reasons.append(f"Invalid bucket type: {request.bucket_type}")
            return result
        
        # === Check Available Capital ===
        if bucket.available_eur <= 0:
            result.status = AllocationStatus.DENIED
            result.reasons.append(f"No capital available in {request.bucket_type.value} bucket")
            await self._log_denial(request, result)
            return result
        
        # === Apply Position Sizing ===
        max_trade = bucket.max_single_trade_eur
        requested = request.requested_eur
        
        if requested > bucket.available_eur:
            # Partial allocation
            requested = bucket.available_eur
            result.status = AllocationStatus.PARTIAL
            result.warnings.append(
                f"Reduced allocation: requested {request.requested_eur:.2f}€, available {bucket.available_eur:.2f}€"
            )
        
        if requested > max_trade:
            # Cap to max trade size
            requested = max_trade
            result.status = AllocationStatus.PARTIAL if result.status != AllocationStatus.PARTIAL else result.status
            result.warnings.append(
                f"Capped to max trade size: {max_trade:.2f}€"
            )
        
        # === Approve Allocation ===
        result.approved_eur = requested
        if result.status != AllocationStatus.PARTIAL:
            result.status = AllocationStatus.APPROVED
        result.reasons.append(f"Allocated {requested:.2f}€ from {request.bucket_type.value} bucket")
        
        # Update state
        bucket.available_eur -= requested
        bucket.in_use_eur += requested
        self._state.deployed_capital_eur += requested
        self._state.available_capital_eur -= requested
        self._state.active_agents[request.agent_id] = request.agent_type
        self._state.last_updated = datetime.now(timezone.utc)
        
        logger.info(f"Allocated {requested:.2f}€ to {request.agent_id} ({request.agent_type})")
        
        return result
    
    async def release_allocation(
        self,
        agent_id: str,
        bucket_type: BucketType,
        amount_eur: float,
        pnl_eur: float = 0.0,
    ) -> bool:
        """
        Release allocated capital back to bucket.
        
        Args:
            agent_id: Agent releasing capital
            bucket_type: Which bucket to return to
            amount_eur: Original allocated amount
            pnl_eur: Profit/loss from the trade
        
        Returns:
            True if released successfully
        """
        if not self._state:
            return False
        
        bucket = self._get_bucket(bucket_type)
        if not bucket:
            return False
        
        # Return capital + P&L
        return_amount = amount_eur + pnl_eur
        
        bucket.in_use_eur -= amount_eur
        bucket.available_eur += return_amount
        
        self._state.deployed_capital_eur -= amount_eur
        self._state.available_capital_eur += return_amount
        self._state.total_capital_eur += pnl_eur  # Update total with P&L
        
        # Remove from active if no more positions
        if bucket.in_use_eur <= 0 and agent_id in self._state.active_agents:
            del self._state.active_agents[agent_id]
        
        self._state.last_updated = datetime.now(timezone.utc)
        
        logger.info(f"Released {amount_eur:.2f}€ from {agent_id}, P&L: {pnl_eur:.2f}€")
        
        return True
    
    def _get_bucket(self, bucket_type: BucketType) -> Optional[BucketState]:
        """Get bucket by type."""
        if not self._state:
            return None
        
        if bucket_type == BucketType.CORE:
            return self._state.core_bucket
        elif bucket_type == BucketType.EDGE:
            return self._state.edge_bucket
        elif bucket_type == BucketType.RESERVE:
            return self._state.reserve_bucket
        return None
    
    async def _log_denial(self, request: AllocationRequest, result: AllocationResult) -> None:
        """Log denied allocation."""
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if EventSeverity and EventCategory:
                await self.event_logger.emit(
                    type="ALLOCATION_DENIED",
                    category=EventCategory.RISK,
                    severity=EventSeverity.WARNING,
                    message=f"Allocation denied: {request.agent_id} requested {request.requested_eur:.2f}€",
                    context={
                        "agent_id": request.agent_id,
                        "agent_type": request.agent_type,
                        "bucket": request.bucket_type.value,
                        "requested_eur": request.requested_eur,
                        "reasons": result.reasons,
                    },
                    tags=["risk_budget", "denied"]
                )
    
    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get current portfolio state."""
        if not self._state:
            return None
        
        return {
            "total_capital_eur": self._state.total_capital_eur,
            "available_capital_eur": self._state.available_capital_eur,
            "deployed_capital_eur": self._state.deployed_capital_eur,
            "buckets": {
                "core": self._state.core_bucket.model_dump(),
                "edge": self._state.edge_bucket.model_dump(),
                "reserve": self._state.reserve_bucket.model_dump(),
            },
            "active_agents": self._state.active_agents,
            "allow_multi_agent": self._state.allow_multi_agent,
            "last_updated": self._state.last_updated.isoformat(),
        }
    
    async def rebalance_buckets(self) -> None:
        """Rebalance buckets based on current config and capital."""
        if not self._state:
            return
        
        config = await self._get_config()
        total = self._state.total_capital_eur
        
        # Only rebalance available capital (not deployed)
        available_for_rebalance = self._state.available_capital_eur
        
        # Calculate target allocations
        core_target = (config.get("core_pct", 60.0) / 100) * total
        edge_target = (config.get("edge_pct", 40.0) / 100) * total
        
        # Adjust only the available portions
        # This is a simplified rebalance - production would need more sophistication
        
        self._state.last_updated = datetime.now(timezone.utc)
        logger.info("Buckets rebalanced")
    
    def get_recommended_bucket(self, agent_type: str) -> BucketType:
        """Get recommended bucket for an agent type."""
        if agent_type == "MM":
            return BucketType.CORE
        elif agent_type == "MOM":
            return BucketType.EDGE
        return BucketType.CORE


# ============ Position Sizer ============

class PositionSizer:
    """
    Calculate optimal position sizes for micro-capital.
    
    Rules:
    - Never risk more than X% of bucket per trade
    - Account for fees and slippage
    - Scale with confidence
    """
    
    @staticmethod
    def calculate_position_size(
        bucket_available: float,
        risk_per_trade_pct: float = 5.0,
        confidence: float = 1.0,
        total_cost_pct: float = 0.15,
        min_order_eur: float = 1.0,
    ) -> float:
        """
        Calculate position size.
        
        Args:
            bucket_available: Available capital in bucket
            risk_per_trade_pct: Max % of bucket to risk
            confidence: Router confidence (0-1)
            total_cost_pct: Estimated total cost %
            min_order_eur: Minimum order size
        
        Returns:
            Recommended position size in EUR
        """
        # Base size from risk percentage
        base_size = bucket_available * (risk_per_trade_pct / 100)
        
        # Adjust for confidence
        confidence_factor = 0.5 + (confidence * 0.5)  # 0.5 to 1.0
        adjusted_size = base_size * confidence_factor
        
        # Ensure we can cover costs
        min_for_profit = (total_cost_pct / 100) * adjusted_size * 3  # Need 3x cost for profit
        if adjusted_size < min_for_profit:
            adjusted_size = min_for_profit
        
        # Apply minimum
        if adjusted_size < min_order_eur:
            return 0.0  # Don't trade if below minimum
        
        return round(adjusted_size, 2)
