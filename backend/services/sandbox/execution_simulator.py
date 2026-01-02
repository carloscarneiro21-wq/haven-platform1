"""
Stress Sandbox - Execution Simulator
=====================================
Simulates order execution with realistic fills, slippage, spreads, and partial fills.

Features:
- Dynamic spread based on volatility and liquidity
- Slippage model based on order size and market conditions
- Partial fills during low liquidity
- Latency simulation
- Rejection scenarios (rate limits, stale data, etc.)
"""

import random
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import logging

from services.sandbox.synthetic_feed import SyntheticPriceFeed, MarketSnapshot

logger = logging.getLogger(__name__)


# ============ Enums ============

class ExecutionStatus(str, Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class RejectionReason(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    STALE_DATA = "STALE_DATA"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    ORDER_ACK_TIMEOUT = "ORDER_ACK_TIMEOUT"
    PRICE_MOVED = "PRICE_MOVED"
    HONEYPOT_BLOCKED = "HONEYPOT_BLOCKED"
    MAX_SLIPPAGE_EXCEEDED = "MAX_SLIPPAGE_EXCEEDED"


# ============ Models ============

class OrderRequest(BaseModel):
    """Order request for simulation."""
    order_id: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str  # "market" or "limit"
    limit_price: Optional[float] = None
    max_slippage_pct: float = 1.0  # Max acceptable slippage
    

class ExecutionResult(BaseModel):
    """Result of order execution simulation."""
    order_id: str
    symbol: str
    side: str
    status: ExecutionStatus
    
    # Fill details
    requested_qty: float
    filled_qty: float
    avg_fill_price: float
    
    # Costs
    slippage_pct: float
    spread_pct: float
    fee_pct: float = 0.1  # 0.1% default
    
    # Market conditions
    liquidity_factor: float
    volatility: float
    
    # Timing
    latency_ms: int
    timestamp: datetime
    
    # If rejected
    rejection_reason: Optional[RejectionReason] = None
    rejection_message: Optional[str] = None
    
    # DEX specific
    mev_hit: bool = False
    gas_cost_usd: float = 0.0
    price_impact_pct: float = 0.0


# ============ Execution Simulator ============

class ExecutionSimulator:
    """
    Simulates order execution with realistic market dynamics.
    """
    
    # Base parameters
    BASE_SLIPPAGE_BPS = 5  # 0.05%
    LATENCY_BASE_MS = 50
    LATENCY_VAR_MS = 100
    
    # Fee structure
    MAKER_FEE_PCT = 0.1
    TAKER_FEE_PCT = 0.1
    
    def __init__(self, price_feed: SyntheticPriceFeed, seed: int):
        self.price_feed = price_feed
        self._rng = random.Random(seed)
        
        # Active fault conditions
        self._rate_limited = False
        self._rate_limit_until: Optional[datetime] = None
        self._latency_multiplier = 1.0
        self._ack_delay_ms = 0
        self._order_ack_delay_active = False
        
        # Statistics
        self._executions: List[ExecutionResult] = []
        self._total_slippage = 0.0
        self._total_spread = 0.0
        
    def inject_rate_limit(self, duration_sec: int, backoff_sec: int):
        """Inject rate limiting condition."""
        self._rate_limited = True
        now = self.price_feed._sim_time or datetime.now(timezone.utc)
        self._rate_limit_until = now + timedelta(seconds=duration_sec)
        logger.debug(f"Rate limit injected for {duration_sec}s")
        
    def inject_latency(self, multiplier: float, duration_sec: int):
        """Inject additional latency."""
        self._latency_multiplier = multiplier
        # Would need to track end time for cleanup
        
    def inject_ack_delay(self, delay_ms: int, duration_sec: int):
        """Inject order acknowledgment delays."""
        self._ack_delay_ms = delay_ms
        self._order_ack_delay_active = True
        
    def clear_faults(self):
        """Clear all injected faults."""
        self._rate_limited = False
        self._rate_limit_until = None
        self._latency_multiplier = 1.0
        self._ack_delay_ms = 0
        self._order_ack_delay_active = False
        
    def _calculate_slippage(self, qty: float, liquidity_factor: float, 
                           volatility: float, is_market: bool) -> float:
        """Calculate slippage based on order size and conditions."""
        # Base slippage
        base = self.BASE_SLIPPAGE_BPS / 10000
        
        # Size impact (larger orders = more slippage)
        size_factor = 1 + (qty / 100)  # Simplified
        
        # Liquidity impact (lower liquidity = more slippage)
        liquidity_impact = 1 / max(0.1, liquidity_factor)
        
        # Volatility impact
        vol_impact = 1 + volatility * 10
        
        # Market orders have more slippage than limits
        order_type_mult = 1.5 if is_market else 1.0
        
        # Random component
        random_factor = self._rng.uniform(0.8, 1.2)
        
        slippage = base * size_factor * liquidity_impact * vol_impact * order_type_mult * random_factor
        
        return min(slippage, 0.1)  # Cap at 10%
    
    def _calculate_partial_fill(self, qty: float, liquidity_factor: float) -> float:
        """Determine fill quantity based on liquidity."""
        if liquidity_factor >= 0.8:
            # Normal liquidity - full fill
            return qty
        elif liquidity_factor >= 0.5:
            # Reduced liquidity - might partial
            fill_pct = self._rng.uniform(0.7, 1.0)
            return qty * fill_pct
        elif liquidity_factor >= 0.2:
            # Low liquidity - likely partial
            fill_pct = self._rng.uniform(0.3, 0.7)
            return qty * fill_pct
        else:
            # Very low liquidity - small fill or reject
            if self._rng.random() < 0.3:
                return 0  # Rejected
            fill_pct = self._rng.uniform(0.1, 0.3)
            return qty * fill_pct
    
    def _calculate_latency(self) -> int:
        """Calculate execution latency in ms."""
        base = self.LATENCY_BASE_MS + self._rng.randint(0, self.LATENCY_VAR_MS)
        latency = int(base * self._latency_multiplier)
        
        if self._order_ack_delay_active:
            latency += self._ack_delay_ms
        
        return latency
    
    async def execute_order(self, order: OrderRequest) -> ExecutionResult:
        """
        Execute an order with realistic simulation.
        
        Returns ExecutionResult with fill details or rejection reason.
        """
        now = self.price_feed._sim_time or datetime.now(timezone.utc)
        
        # Check rate limiting
        if self._rate_limited and self._rate_limit_until and now < self._rate_limit_until:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=ExecutionStatus.REJECTED,
                requested_qty=order.quantity,
                filled_qty=0,
                avg_fill_price=0,
                slippage_pct=0,
                spread_pct=0,
                liquidity_factor=0,
                volatility=0,
                latency_ms=self._calculate_latency(),
                timestamp=now,
                rejection_reason=RejectionReason.RATE_LIMITED,
                rejection_message="Rate limit exceeded, retry after backoff",
            )
        
        # Get market snapshot
        snapshot = self.price_feed.get_market_snapshot(order.symbol)
        if not snapshot:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=ExecutionStatus.REJECTED,
                requested_qty=order.quantity,
                filled_qty=0,
                avg_fill_price=0,
                slippage_pct=0,
                spread_pct=0,
                liquidity_factor=0,
                volatility=0,
                latency_ms=self._calculate_latency(),
                timestamp=now,
                rejection_reason=RejectionReason.STALE_DATA,
                rejection_message=f"No market data for {order.symbol}",
            )
        
        # Check for stale data
        if snapshot.is_stale and snapshot.stale_age_sec > 30:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=ExecutionStatus.REJECTED,
                requested_qty=order.quantity,
                filled_qty=0,
                avg_fill_price=0,
                slippage_pct=0,
                spread_pct=snapshot.spread_pct,
                liquidity_factor=snapshot.liquidity_factor,
                volatility=snapshot.volatility,
                latency_ms=self._calculate_latency(),
                timestamp=now,
                rejection_reason=RejectionReason.STALE_DATA,
                rejection_message=f"Data is {snapshot.stale_age_sec}s stale",
            )
        
        # Calculate execution parameters
        is_market = order.order_type.lower() == "market"
        slippage_pct = self._calculate_slippage(
            order.quantity, 
            snapshot.liquidity_factor, 
            snapshot.volatility,
            is_market
        ) * 100  # Convert to percentage
        
        # Check max slippage
        if slippage_pct > order.max_slippage_pct:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=ExecutionStatus.REJECTED,
                requested_qty=order.quantity,
                filled_qty=0,
                avg_fill_price=0,
                slippage_pct=slippage_pct,
                spread_pct=snapshot.spread_pct,
                liquidity_factor=snapshot.liquidity_factor,
                volatility=snapshot.volatility,
                latency_ms=self._calculate_latency(),
                timestamp=now,
                rejection_reason=RejectionReason.MAX_SLIPPAGE_EXCEEDED,
                rejection_message=f"Slippage {slippage_pct:.2f}% > max {order.max_slippage_pct}%",
            )
        
        # Calculate fill quantity
        filled_qty = self._calculate_partial_fill(order.quantity, snapshot.liquidity_factor)
        
        if filled_qty == 0:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                status=ExecutionStatus.REJECTED,
                requested_qty=order.quantity,
                filled_qty=0,
                avg_fill_price=0,
                slippage_pct=slippage_pct,
                spread_pct=snapshot.spread_pct,
                liquidity_factor=snapshot.liquidity_factor,
                volatility=snapshot.volatility,
                latency_ms=self._calculate_latency(),
                timestamp=now,
                rejection_reason=RejectionReason.INSUFFICIENT_LIQUIDITY,
                rejection_message="Insufficient liquidity for fill",
            )
        
        # Calculate fill price
        if order.side.lower() == "buy":
            # Buy at ask + slippage
            fill_price = snapshot.ask * (1 + slippage_pct / 100)
        else:
            # Sell at bid - slippage
            fill_price = snapshot.bid * (1 - slippage_pct / 100)
        
        # For limit orders, check if price is acceptable
        if not is_market and order.limit_price:
            if order.side.lower() == "buy" and fill_price > order.limit_price:
                return ExecutionResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    status=ExecutionStatus.REJECTED,
                    requested_qty=order.quantity,
                    filled_qty=0,
                    avg_fill_price=0,
                    slippage_pct=slippage_pct,
                    spread_pct=snapshot.spread_pct,
                    liquidity_factor=snapshot.liquidity_factor,
                    volatility=snapshot.volatility,
                    latency_ms=self._calculate_latency(),
                    timestamp=now,
                    rejection_reason=RejectionReason.PRICE_MOVED,
                    rejection_message=f"Fill price {fill_price:.2f} > limit {order.limit_price:.2f}",
                )
            elif order.side.lower() == "sell" and fill_price < order.limit_price:
                return ExecutionResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    status=ExecutionStatus.REJECTED,
                    requested_qty=order.quantity,
                    filled_qty=0,
                    avg_fill_price=0,
                    slippage_pct=slippage_pct,
                    spread_pct=snapshot.spread_pct,
                    liquidity_factor=snapshot.liquidity_factor,
                    volatility=snapshot.volatility,
                    latency_ms=self._calculate_latency(),
                    timestamp=now,
                    rejection_reason=RejectionReason.PRICE_MOVED,
                    rejection_message=f"Fill price {fill_price:.2f} < limit {order.limit_price:.2f}",
                )
        
        # Determine status
        status = ExecutionStatus.FILLED if filled_qty >= order.quantity * 0.99 else ExecutionStatus.PARTIAL
        
        # Calculate latency
        latency = self._calculate_latency()
        
        # Simulate latency (in real async scenario)
        # await asyncio.sleep(latency / 1000)
        
        result = ExecutionResult(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            status=status,
            requested_qty=order.quantity,
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            slippage_pct=slippage_pct,
            spread_pct=snapshot.spread_pct,
            liquidity_factor=snapshot.liquidity_factor,
            volatility=snapshot.volatility,
            latency_ms=latency,
            timestamp=now,
        )
        
        # Track statistics
        self._executions.append(result)
        self._total_slippage += slippage_pct
        self._total_spread += snapshot.spread_pct
        
        logger.debug(f"Executed {order.side} {filled_qty}/{order.quantity} {order.symbol} @ {fill_price:.2f}")
        
        return result
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        if not self._executions:
            return {
                "total_executions": 0,
                "filled": 0,
                "partial": 0,
                "rejected": 0,
                "avg_slippage_pct": 0,
                "avg_spread_pct": 0,
                "slippage_p95": 0,
                "spread_p95": 0,
            }
        
        filled = [e for e in self._executions if e.status == ExecutionStatus.FILLED]
        partial = [e for e in self._executions if e.status == ExecutionStatus.PARTIAL]
        rejected = [e for e in self._executions if e.status == ExecutionStatus.REJECTED]
        
        slippages = [e.slippage_pct for e in self._executions if e.slippage_pct > 0]
        spreads = [e.spread_pct for e in self._executions if e.spread_pct > 0]
        
        def percentile(data: List[float], pct: int) -> float:
            if not data:
                return 0
            sorted_data = sorted(data)
            idx = int(len(sorted_data) * pct / 100)
            return sorted_data[min(idx, len(sorted_data) - 1)]
        
        return {
            "total_executions": len(self._executions),
            "filled": len(filled),
            "partial": len(partial),
            "rejected": len(rejected),
            "avg_slippage_pct": sum(slippages) / len(slippages) if slippages else 0,
            "avg_spread_pct": sum(spreads) / len(spreads) if spreads else 0,
            "slippage_p95": percentile(slippages, 95),
            "spread_p95": percentile(spreads, 95),
        }
    
    def get_all_executions(self) -> List[ExecutionResult]:
        """Get all execution results."""
        return self._executions.copy()
