"""
Viability Service for Capital Growth Module
===========================================

Pre-trade viability filter that ensures:
- Expected edge > total cost * multiplier
- Costs include: fees + spread + slippage
- Critical for micro-capital (100€) survival

Only allows trades when profit is mathematically viable.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)

# Import event enums lazily to avoid circular imports
def _get_event_enums():
    """Get event enums, importing lazily."""
    try:
        from services.event_logger import EventSeverity, EventCategory
        return EventSeverity, EventCategory
    except ImportError:
        return None, None


# ============ Enums ============

class ViabilityStatus(str, Enum):
    """Viability check result."""
    VIABLE = "VIABLE"
    NOT_VIABLE = "NOT_VIABLE"
    MARGINAL = "MARGINAL"  # Edge > cost but < cost * multiplier


class CostComponent(str, Enum):
    """Components of trade cost."""
    MAKER_FEE = "MAKER_FEE"
    TAKER_FEE = "TAKER_FEE"
    SPREAD = "SPREAD"
    SLIPPAGE = "SLIPPAGE"


# ============ Fee Structures ============

# Default fee structures per venue
VENUE_FEES = {
    "kraken": {
        "maker": 0.16,  # 0.16%
        "taker": 0.26,  # 0.26%
    },
    "binance": {
        "maker": 0.10,  # 0.10%
        "taker": 0.10,  # 0.10%
    },
}

# Slippage estimates by order size
SLIPPAGE_ESTIMATES = {
    "micro": {  # < 10€
        "kraken": 0.02,  # 0.02%
        "binance": 0.01,
    },
    "small": {  # 10-50€
        "kraken": 0.03,
        "binance": 0.02,
    },
    "medium": {  # 50-200€
        "kraken": 0.05,
        "binance": 0.03,
    },
}


# ============ Models ============

class CostBreakdown(BaseModel):
    """Detailed breakdown of trade costs."""
    maker_fee_pct: float = 0.0
    taker_fee_pct: float = 0.0
    spread_pct: float = 0.0
    slippage_pct: float = 0.0
    
    # Total costs
    total_entry_pct: float = 0.0  # Cost to enter
    total_exit_pct: float = 0.0   # Cost to exit
    total_round_trip_pct: float = 0.0  # Entry + Exit
    
    # EUR amounts
    total_cost_eur: float = 0.0
    
    def calculate_totals(self, use_maker: bool = True) -> None:
        """Calculate total costs."""
        fee = self.maker_fee_pct if use_maker else self.taker_fee_pct
        
        self.total_entry_pct = (self.spread_pct / 2) + self.slippage_pct + fee
        self.total_exit_pct = (self.spread_pct / 2) + self.slippage_pct + fee
        self.total_round_trip_pct = self.total_entry_pct + self.total_exit_pct


class ViabilityInput(BaseModel):
    """Input for viability check."""
    agent_type: str  # "MM" or "MOM"
    preset_id: str
    symbol: str
    venue: str
    order_size_eur: float
    
    # Market conditions
    current_spread_pct: float
    bid_price: float
    ask_price: float
    
    # Expected performance
    expected_move_pct: float = Field(description="Expected price move to capture")
    hold_time_minutes: int = Field(default=60, description="Expected hold time")
    
    # Override fees (optional)
    custom_maker_fee: Optional[float] = None
    custom_taker_fee: Optional[float] = None
    
    # Use maker or taker
    expect_maker: bool = True


class ViabilityResult(BaseModel):
    """Result of viability check."""
    status: ViabilityStatus
    viable: bool
    
    # Costs
    cost_breakdown: CostBreakdown
    
    # Edge analysis
    expected_edge_pct: float = 0.0  # Expected profit %
    required_edge_pct: float = 0.0  # Minimum required
    edge_surplus_pct: float = 0.0   # How much above minimum
    
    # EUR projections
    expected_profit_eur: float = 0.0
    break_even_move_pct: float = 0.0
    
    # Multiplier used
    viability_multiplier: float = 2.0
    
    # Reasons
    reasons: List[str] = []
    warnings: List[str] = []
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Viability Service ============

class ViabilityService:
    """
    Pre-trade viability checker.
    
    Features:
    - Cost estimation (fees + spread + slippage)
    - Edge requirement calculation
    - Multiplier-based viability gate
    - Venue-specific fee handling
    """
    
    def __init__(self, system_config_service=None, event_logger=None):
        self.system_config_service = system_config_service
        self.event_logger = event_logger
    
    async def check_viability(self, input: ViabilityInput) -> ViabilityResult:
        """
        Check if a trade is viable.
        
        Args:
            input: Trade parameters
        
        Returns:
            ViabilityResult with status and breakdown
        """
        result = ViabilityResult(
            status=ViabilityStatus.NOT_VIABLE,
            viable=False,
            cost_breakdown=CostBreakdown(),
        )
        
        # Get multiplier from config
        multiplier = await self._get_multiplier(input.agent_type, input.preset_id)
        result.viability_multiplier = multiplier
        
        # === Calculate Costs ===
        costs = await self._calculate_costs(input)
        result.cost_breakdown = costs
        
        # === Calculate Required Edge ===
        result.required_edge_pct = costs.total_round_trip_pct * multiplier
        
        # === Compare with Expected Edge ===
        result.expected_edge_pct = input.expected_move_pct
        result.edge_surplus_pct = result.expected_edge_pct - result.required_edge_pct
        
        # === Break-even Analysis ===
        result.break_even_move_pct = costs.total_round_trip_pct
        
        # === EUR Projections ===
        gross_profit = input.order_size_eur * (input.expected_move_pct / 100)
        costs.total_cost_eur = input.order_size_eur * (costs.total_round_trip_pct / 100)
        result.expected_profit_eur = gross_profit - costs.total_cost_eur
        
        # === Viability Decision ===
        if result.expected_edge_pct > result.required_edge_pct:
            result.status = ViabilityStatus.VIABLE
            result.viable = True
            result.reasons.append(
                f"✓ Viable: edge {result.expected_edge_pct:.3f}% > "
                f"required {result.required_edge_pct:.3f}% (cost {costs.total_round_trip_pct:.3f}% × {multiplier})"
            )
            result.reasons.append(
                f"Expected profit: {result.expected_profit_eur:.4f}€"
            )
        elif result.expected_edge_pct > costs.total_round_trip_pct:
            # Profitable but below multiplier threshold
            result.status = ViabilityStatus.MARGINAL
            result.viable = False
            result.reasons.append(
                f"⚠ Marginal: edge {result.expected_edge_pct:.3f}% > cost {costs.total_round_trip_pct:.3f}% "
                f"but < required {result.required_edge_pct:.3f}%"
            )
            result.warnings.append(
                "Trade would be profitable but margin too thin for risk"
            )
        else:
            result.status = ViabilityStatus.NOT_VIABLE
            result.viable = False
            result.reasons.append(
                f"✗ Not viable: edge {result.expected_edge_pct:.3f}% ≤ cost {costs.total_round_trip_pct:.3f}%"
            )
            result.reasons.append(
                f"Need at least {result.break_even_move_pct:.3f}% move to break even"
            )
        
        # === Additional Warnings ===
        if input.current_spread_pct > 0.10:
            result.warnings.append(f"High spread: {input.current_spread_pct:.3f}%")
        
        if costs.slippage_pct > 0.05:
            result.warnings.append(f"Elevated slippage estimate: {costs.slippage_pct:.3f}%")
        
        if result.expected_profit_eur < 0.05 and result.viable:
            result.warnings.append(f"Very small expected profit: {result.expected_profit_eur:.4f}€")
        
        # Log
        await self._log_check(input, result)
        
        return result
    
    async def _get_multiplier(self, agent_type: str, preset_id: str) -> float:
        """Get viability multiplier from config."""
        if self.system_config_service:
            config = await self.system_config_service.get_config()
            viability = config.viability
            
            if agent_type == "MM":
                return viability.mm_multiplier
            elif agent_type == "MOM":
                if "CONSERVATIVE" in preset_id:
                    return viability.mom_conservative_multiplier
                elif "AGGRESSIVE" in preset_id:
                    return viability.mom_aggressive_multiplier
                elif "DEFENSIVE" in preset_id:
                    return viability.mom_defensive_multiplier
                else:
                    return viability.mom_standard_multiplier
        
        # Defaults
        return 2.0
    
    async def _calculate_costs(self, input: ViabilityInput) -> CostBreakdown:
        """Calculate detailed cost breakdown."""
        costs = CostBreakdown()
        
        # Get venue fees
        venue_lower = input.venue.lower()
        fees = VENUE_FEES.get(venue_lower, VENUE_FEES["binance"])
        
        costs.maker_fee_pct = input.custom_maker_fee if input.custom_maker_fee is not None else fees["maker"]
        costs.taker_fee_pct = input.custom_taker_fee if input.custom_taker_fee is not None else fees["taker"]
        
        # Spread cost (half on entry, half on exit)
        costs.spread_pct = input.current_spread_pct
        
        # Slippage estimate
        costs.slippage_pct = self._estimate_slippage(input.order_size_eur, input.venue)
        
        # Calculate totals
        costs.calculate_totals(use_maker=input.expect_maker)
        
        return costs
    
    def _estimate_slippage(self, order_size_eur: float, venue: str) -> float:
        """Estimate slippage based on order size."""
        venue_lower = venue.lower()
        
        if order_size_eur < 10:
            estimates = SLIPPAGE_ESTIMATES["micro"]
        elif order_size_eur < 50:
            estimates = SLIPPAGE_ESTIMATES["small"]
        else:
            estimates = SLIPPAGE_ESTIMATES["medium"]
        
        return estimates.get(venue_lower, 0.03)
    
    async def _log_check(self, input: ViabilityInput, result: ViabilityResult) -> None:
        """Log viability check."""
        if self.event_logger:
            EventSeverity, EventCategory = _get_event_enums()
            if not EventSeverity or not EventCategory:
                return
            
            severity = EventSeverity.INFO if result.viable else EventSeverity.WARNING
            await self.event_logger.emit(
                type="VIABILITY_CHECK",
                category=EventCategory.RISK,
                severity=severity,
                message=f"Viability {result.status.value}: {input.symbol} {input.order_size_eur:.2f}€",
                context={
                    "agent_type": input.agent_type,
                    "preset_id": input.preset_id,
                    "symbol": input.symbol,
                    "venue": input.venue,
                    "order_size_eur": input.order_size_eur,
                    "status": result.status.value,
                    "viable": result.viable,
                    "expected_edge_pct": result.expected_edge_pct,
                    "required_edge_pct": result.required_edge_pct,
                    "total_cost_pct": result.cost_breakdown.total_round_trip_pct,
                    "expected_profit_eur": result.expected_profit_eur,
                },
                tags=["viability", input.agent_type.lower()]
            )
    
    def get_min_viable_move(
        self,
        venue: str,
        order_size_eur: float,
        use_maker: bool = True,
        multiplier: float = 2.0,
    ) -> Dict[str, float]:
        """
        Calculate minimum price move needed for viability.
        
        Useful for understanding what trades are possible with current market.
        """
        venue_lower = venue.lower()
        fees = VENUE_FEES.get(venue_lower, VENUE_FEES["binance"])
        
        fee = fees["maker"] if use_maker else fees["taker"]
        slippage = self._estimate_slippage(order_size_eur, venue)
        
        # Assume 0.05% spread as baseline
        spread = 0.05
        
        entry_cost = (spread / 2) + slippage + fee
        exit_cost = (spread / 2) + slippage + fee
        round_trip = entry_cost + exit_cost
        
        break_even = round_trip
        min_viable = round_trip * multiplier
        
        return {
            "break_even_pct": break_even,
            "min_viable_pct": min_viable,
            "total_cost_pct": round_trip,
            "fee_pct": fee * 2,
            "spread_pct": spread,
            "slippage_pct": slippage * 2,
        }


# ============ Quick Viability Check ============

async def quick_viability_check(
    expected_move_pct: float,
    spread_pct: float,
    venue: str,
    order_size_eur: float,
    multiplier: float = 2.0,
    use_maker: bool = True,
) -> Tuple[bool, float, float]:
    """
    Quick viability check without full service.
    
    Returns:
        (is_viable, total_cost_pct, required_edge_pct)
    """
    venue_lower = venue.lower()
    fees = VENUE_FEES.get(venue_lower, VENUE_FEES["binance"])
    
    fee = fees["maker"] if use_maker else fees["taker"]
    
    # Slippage estimate
    if order_size_eur < 10:
        slippage = SLIPPAGE_ESTIMATES["micro"].get(venue_lower, 0.02)
    elif order_size_eur < 50:
        slippage = SLIPPAGE_ESTIMATES["small"].get(venue_lower, 0.03)
    else:
        slippage = SLIPPAGE_ESTIMATES["medium"].get(venue_lower, 0.05)
    
    # Round-trip cost
    entry = (spread_pct / 2) + slippage + fee
    exit_cost = (spread_pct / 2) + slippage + fee
    total_cost = entry + exit_cost
    
    required_edge = total_cost * multiplier
    is_viable = expected_move_pct > required_edge
    
    return is_viable, total_cost, required_edge
