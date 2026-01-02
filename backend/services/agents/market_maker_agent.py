"""
Market Maker Agent - Intent Plan Generator
==========================================

Produces hypothetical orders for paper trading validation.
Does NOT execute trades - only generates "intent plans".

Core MM Strategy:
- Place bid/ask orders around mid price
- Capture spread when orders fill
- Grid-based positioning with skew management
- Tight risk controls for micro-capital
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field
import numpy as np

logger = logging.getLogger(__name__)


# ============ Enums ============

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    LIMIT_MAKER = "limit_maker"  # Post-only


class IntentStatus(str, Enum):
    READY = "READY"           # Plan ready to execute
    PAUSED = "PAUSED"         # Agent paused
    BLOCKED = "BLOCKED"       # Blocked by Guardian
    NO_OPPORTUNITY = "NO_OPPORTUNITY"  # No viable trades


# ============ Reason Codes ============

MM_REASON_CODES = {
    # Grid calculation
    "GRID_CENTERED": "Grid centrado no mid price {mid_price:.2f}",
    "GRID_SKEWED_LONG": "Grid com skew long (+{skew_pct:.1f}%): mais bids que asks",
    "GRID_SKEWED_SHORT": "Grid com skew short ({skew_pct:.1f}%): mais asks que bids",
    "GRID_LEVELS_SET": "Grid configurado com {levels} níveis, largura {width_pct:.2f}%",
    
    # Order generation
    "ORDERS_GENERATED": "Geradas {count} ordens ({bids} bids, {asks} asks)",
    "ORDER_SIZE_CAPPED": "Tamanho de ordem limitado a {max_eur:.2f}€",
    "SPREAD_CAPTURE_TARGET": "Target de captura de spread: {target_pct:.3f}%",
    
    # Risk
    "INVENTORY_BALANCED": "Inventário dentro dos limites (+/-{limit_pct:.0f}%)",
    "INVENTORY_SKEWED": "Inventário enviesado: {current_pct:.1f}% (limit: {limit_pct:.0f}%)",
    "POSITION_LIMIT_OK": "Posição máxima: {max_eur:.2f}€ dentro do budget",
    
    # Pause reasons
    "PAUSE_SPREAD_WIDE": "Spread muito largo ({spread_pct:.3f}%) para MM rentável",
    "PAUSE_TREND_DETECTED": "Tendência detectada - MM não adequado",
    "PAUSE_HIGH_VOL": "Volatilidade muito alta para MM conservador",
    "PAUSE_VIABILITY": "Viabilidade falhou: edge insuficiente",
    "PAUSE_GUARDIAN": "Bloqueado pelo Guardian: {reason}",
    "PAUSE_NO_BUDGET": "Budget insuficiente para operar",
}


# ============ Models ============

class MMPresetConfig(BaseModel):
    """Configuration from MM preset."""
    preset_id: str
    grid_width_total_pct: float = 0.4
    grid_levels: int = 5
    maker_only: bool = True
    skew_max_pct: float = 30.0
    daily_kill_pct: float = 2.0
    viability_multiplier: float = 2.0
    max_position_eur: float = 50.0
    order_size_pct: float = 10.0  # % of bucket per order


class IntendedOrder(BaseModel):
    """A hypothetical order in the intent plan."""
    id: str = Field(default_factory=lambda: f"intent_{datetime.now(timezone.utc).strftime('%H%M%S%f')[:12]}")
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT_MAKER
    price: float
    size_base: float
    size_eur: float
    grid_level: int = 0
    distance_from_mid_pct: float = 0.0
    expected_fill_probability: float = 0.5
    rationale: str = ""


class MMIntentPlan(BaseModel):
    """Intent plan from Market Maker agent."""
    agent_type: str = "MM"
    agent_id: str
    preset_id: str
    symbol: str
    venue: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Status
    status: IntentStatus = IntentStatus.READY
    
    # Market context
    mid_price: float
    bid: float
    ask: float
    spread_pct: float
    
    # Grid config used
    grid_width_pct: float
    grid_levels: int
    grid_skew_pct: float = 0.0
    
    # Intended orders
    orders: List[IntendedOrder] = []
    total_bid_size_eur: float = 0.0
    total_ask_size_eur: float = 0.0
    
    # Expected outcomes
    expected_spread_capture_pct: float = 0.0
    expected_profit_per_round_trip_eur: float = 0.0
    
    # Reason codes with severity
    reason_codes: List[Dict[str, Any]] = []
    
    def add_reason(self, code: str, severity: str = "info", **kwargs):
        """Add a reason code with formatted message."""
        template = MM_REASON_CODES.get(code, code)
        try:
            message = template.format(**kwargs)
        except KeyError:
            message = template
        self.reason_codes.append({
            "code": code,
            "severity": severity,
            "message": message,
        })


# ============ Market Maker Agent ============

from services.agents.trade_execution_mixin import TradeExecutionMixin


class MarketMakerAgent(TradeExecutionMixin):
    """
    Market Maker agent that produces intent plans.
    
    Does NOT execute trades. Generates hypothetical orders
    for validation before connecting to paper trading engine.
    """
    
    def __init__(
        self,
        agent_id: str,
        db=None,
        viability_service=None,
        risk_budget_service=None,
    ):
        self.agent_id = agent_id
        self.db = db
        self.viability_service = viability_service
        self.risk_budget_service = risk_budget_service
        
        # State
        self._current_inventory_pct = 0.0  # -100 to +100
        self._last_plan: Optional[MMIntentPlan] = None
    
    async def generate_intent_plan(
        self,
        symbol: str,
        venue: str,
        preset_config: MMPresetConfig,
        market_data: Dict[str, Any],
        available_budget_eur: float,
        guardian_check: Optional[Dict[str, Any]] = None,
    ) -> MMIntentPlan:
        """
        Generate an intent plan for MM strategy.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            venue: Exchange (e.g., "binance")
            preset_config: MM preset configuration
            market_data: Current market data (bid, ask, etc.)
            available_budget_eur: Available capital in EUR
            guardian_check: Optional guardian validation result
        
        Returns:
            MMIntentPlan with hypothetical orders
        """
        # Extract market data
        bid = market_data.get("bid", 0)
        ask = market_data.get("ask", 0)
        mid_price = (bid + ask) / 2 if bid and ask else 0
        spread_pct = ((ask - bid) / mid_price * 100) if mid_price > 0 else 0
        
        # Initialize plan
        plan = MMIntentPlan(
            agent_id=self.agent_id,
            preset_id=preset_config.preset_id,
            symbol=symbol,
            venue=venue,
            mid_price=mid_price,
            bid=bid,
            ask=ask,
            spread_pct=spread_pct,
            grid_width_pct=preset_config.grid_width_total_pct,
            grid_levels=preset_config.grid_levels,
        )
        
        # === Pre-checks ===
        
        # Guardian check
        if guardian_check and not guardian_check.get("allowed", True):
            plan.status = IntentStatus.BLOCKED
            plan.add_reason(
                "PAUSE_GUARDIAN",
                severity="error",
                reason=guardian_check.get("block_reason", "unknown")
            )
            return plan
        
        # Budget check
        if available_budget_eur < 5:
            plan.status = IntentStatus.PAUSED
            plan.add_reason("PAUSE_NO_BUDGET", severity="error")
            return plan
        
        # Spread check
        max_spread_for_mm = 0.15  # 0.15%
        if spread_pct > max_spread_for_mm:
            plan.status = IntentStatus.PAUSED
            plan.add_reason(
                "PAUSE_SPREAD_WIDE",
                severity="warn",
                spread_pct=spread_pct
            )
            return plan
        
        # Viability check
        expected_spread_capture = spread_pct * 0.5  # Capture ~50% of spread
        total_cost_estimate = 0.05 + spread_pct / 2  # fees + half spread
        
        if expected_spread_capture < total_cost_estimate * preset_config.viability_multiplier:
            plan.status = IntentStatus.NO_OPPORTUNITY
            plan.add_reason("PAUSE_VIABILITY", severity="warn")
            return plan
        
        # === Generate Grid ===
        
        # Calculate grid parameters
        half_width = preset_config.grid_width_total_pct / 2
        levels = preset_config.grid_levels
        
        # Skew based on inventory
        skew_pct = self._calculate_skew(preset_config.skew_max_pct)
        plan.grid_skew_pct = skew_pct
        
        plan.add_reason(
            "GRID_CENTERED",
            severity="info",
            mid_price=mid_price
        )
        
        if abs(skew_pct) > 5:
            if skew_pct > 0:
                plan.add_reason("GRID_SKEWED_LONG", severity="info", skew_pct=skew_pct)
            else:
                plan.add_reason("GRID_SKEWED_SHORT", severity="info", skew_pct=skew_pct)
        
        plan.add_reason(
            "GRID_LEVELS_SET",
            severity="info",
            levels=levels,
            width_pct=preset_config.grid_width_total_pct
        )
        
        # === Generate Orders ===
        
        # Order size calculation
        max_order_eur = min(
            available_budget_eur * (preset_config.order_size_pct / 100),
            preset_config.max_position_eur / levels
        )
        
        if max_order_eur < 5:
            max_order_eur = 5  # Minimum order
        
        plan.add_reason(
            "ORDER_SIZE_CAPPED",
            severity="info",
            max_eur=max_order_eur
        )
        
        orders = []
        bid_count = 0
        ask_count = 0
        total_bid_eur = 0.0
        total_ask_eur = 0.0
        
        # Generate bid orders (below mid)
        bid_levels = (levels // 2) + (1 if skew_pct > 0 else 0)
        for i in range(bid_levels):
            distance_pct = (half_width / max(bid_levels, 1)) * (i + 1) * (1 + skew_pct / 100)
            price = mid_price * (1 - distance_pct / 100)
            
            # Skip if price is invalid
            if price <= 0:
                continue
            
            # Size decreases further from mid
            size_eur = max_order_eur * (1 - i * 0.1)
            size_base = size_eur / price
            
            fill_prob = max(0.2, 0.8 - i * 0.15)  # Higher prob closer to mid
            
            order = IntendedOrder(
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT_MAKER if preset_config.maker_only else OrderType.LIMIT,
                price=round(price, 8),
                size_base=round(size_base, 8),
                size_eur=round(size_eur, 2),
                grid_level=-(i + 1),
                distance_from_mid_pct=round(-distance_pct, 4),
                expected_fill_probability=fill_prob,
                rationale=f"Bid level {i+1}/{bid_levels} at -{distance_pct:.3f}% from mid"
            )
            orders.append(order)
            bid_count += 1
            total_bid_eur += size_eur
        
        # Generate ask orders (above mid)
        ask_levels = levels - bid_levels
        for i in range(ask_levels):
            distance_pct = (half_width / max(ask_levels, 1)) * (i + 1) * (1 - skew_pct / 100)
            price = mid_price * (1 + distance_pct / 100)
            
            # Skip if price is invalid
            if price <= 0:
                continue
            
            size_eur = max_order_eur * (1 - i * 0.1)
            size_base = size_eur / price
            
            fill_prob = max(0.2, 0.8 - i * 0.15)
            
            order = IntendedOrder(
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT_MAKER if preset_config.maker_only else OrderType.LIMIT,
                price=round(price, 8),
                size_base=round(size_base, 8),
                size_eur=round(size_eur, 2),
                grid_level=i + 1,
                distance_from_mid_pct=round(distance_pct, 4),
                expected_fill_probability=fill_prob,
                rationale=f"Ask level {i+1}/{ask_levels} at +{distance_pct:.3f}% from mid"
            )
            orders.append(order)
            ask_count += 1
            total_ask_eur += size_eur
        
        plan.orders = orders
        plan.total_bid_size_eur = round(total_bid_eur, 2)
        plan.total_ask_size_eur = round(total_ask_eur, 2)
        
        plan.add_reason(
            "ORDERS_GENERATED",
            severity="info",
            count=len(orders),
            bids=bid_count,
            asks=ask_count
        )
        
        # === Expected Outcomes ===
        
        plan.expected_spread_capture_pct = round(spread_pct * 0.5, 4)
        
        # Estimate profit per round trip
        avg_order_eur = (total_bid_eur + total_ask_eur) / max(len(orders), 1)
        profit_per_rt = avg_order_eur * (plan.expected_spread_capture_pct / 100) - 0.01  # minus fees
        plan.expected_profit_per_round_trip_eur = round(max(0, profit_per_rt), 4)
        
        plan.add_reason(
            "SPREAD_CAPTURE_TARGET",
            severity="info",
            target_pct=plan.expected_spread_capture_pct
        )
        
        # === Finalize ===
        
        plan.status = IntentStatus.READY
        plan.add_reason(
            "POSITION_LIMIT_OK",
            severity="info",
            max_eur=preset_config.max_position_eur
        )
        
        self._last_plan = plan
        
        logger.info(
            f"MM Intent Plan: {symbol}@{venue} - {len(orders)} orders, "
            f"status={plan.status.value}"
        )
        
        return plan
    
    def _calculate_skew(self, max_skew_pct: float) -> float:
        """Calculate grid skew based on current inventory."""
        # Skew opposite to inventory to rebalance
        # If long (+inventory), skew short to sell more
        skew = -self._current_inventory_pct * (max_skew_pct / 100)
        return max(-max_skew_pct, min(max_skew_pct, skew))
    
    def update_inventory(self, fill_side: str, fill_eur: float, total_budget: float) -> None:
        """Update inventory tracking after a fill."""
        if total_budget <= 0:
            return
        
        pct_change = (fill_eur / total_budget) * 100
        
        if fill_side == "buy":
            self._current_inventory_pct += pct_change
        else:
            self._current_inventory_pct -= pct_change
        
        # Clamp to -100, +100
        self._current_inventory_pct = max(-100, min(100, self._current_inventory_pct))
    
    def get_last_plan(self) -> Optional[MMIntentPlan]:
        """Get the last generated plan."""
        return self._last_plan
    
    def to_dict(self, plan: MMIntentPlan) -> Dict[str, Any]:
        """Convert plan to dict for API response."""
        return plan.model_dump(mode='json')
