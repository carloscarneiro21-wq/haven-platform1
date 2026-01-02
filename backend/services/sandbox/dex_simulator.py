"""
Stress Sandbox - DEX Simulator
==============================
Simulates DEX-specific conditions: AMM price impact, MEV/sandwich attacks,
fee-on-transfer tokens, honeypots, and gas dynamics.

This is SIMULATION ONLY - no on-chain interaction.
"""

import random
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ============ Enums ============

class TokenTrapType(str, Enum):
    NONE = "none"
    FEE_ON_TRANSFER = "fee_on_transfer"
    HONEYPOT = "honeypot"
    BLACKLIST = "blacklist"
    MAX_TX = "max_tx"
    

class MEVResult(str, Enum):
    NO_MEV = "no_mev"
    FRONTRUN = "frontrun"
    SANDWICH = "sandwich"
    BACKRUN = "backrun"


# ============ Models ============

class PoolState(BaseModel):
    """AMM pool state."""
    symbol: str
    token0_reserve: float
    token1_reserve: float  # Usually quote (USDT, ETH, etc.)
    fee_pct: float = 0.3  # 0.3% typical
    k: float = 0  # Constant product
    
    def update_k(self):
        self.k = self.token0_reserve * self.token1_reserve
        

class SwapRequest(BaseModel):
    """DEX swap request."""
    swap_id: str
    pool_symbol: str
    side: str  # "buy" (token0) or "sell" (token0)
    amount_in: float
    min_amount_out: float
    max_slippage_pct: float = 1.0
    gas_price_gwei: float = 20.0


class SwapResult(BaseModel):
    """Result of DEX swap simulation."""
    swap_id: str
    pool_symbol: str
    side: str
    status: str  # "success", "reverted", "blocked"
    
    # Amounts
    amount_in: float
    amount_out: float
    expected_out: float
    
    # Impact
    price_impact_pct: float
    slippage_pct: float
    
    # Fees
    swap_fee_pct: float
    tax_pct: float = 0.0  # Fee-on-transfer tax
    gas_cost_usd: float
    
    # MEV
    mev_result: MEVResult = MEVResult.NO_MEV
    mev_loss_pct: float = 0.0
    
    # Token trap
    trap_type: TokenTrapType = TokenTrapType.NONE
    trap_blocked: bool = False
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ DEX Simulator ============

class DexSimulator:
    """
    Simulates DEX/AMM execution with realistic conditions.
    
    Features:
    - Constant product AMM (x * y = k)
    - Price impact based on trade size vs reserves
    - Fee-on-transfer simulation
    - Honeypot detection (sell blocked)
    - MEV/sandwich attack simulation
    - Gas cost modeling
    """
    
    # Default gas costs
    BASE_GAS_UNITS = 150000  # Swap gas
    GAS_PRICE_GWEI_DEFAULT = 20
    ETH_PRICE_USD = 2200  # For gas cost calculation
    
    def __init__(self, seed: int):
        self._rng = random.Random(seed)
        
        # Pool states
        self._pools: Dict[str, PoolState] = {}
        
        # Token trap states
        self._token_traps: Dict[str, TokenTrapType] = {}
        
        # MEV conditions
        self._mev_probability = 0.1  # Base 10% MEV risk
        self._gas_multiplier = 1.0
        
        # Swap history
        self._swaps: List[SwapResult] = []
        
    def initialize_pool(self, symbol: str, token0_reserve: float, 
                       token1_reserve: float, fee_pct: float = 0.3):
        """Initialize or reset a pool."""
        pool = PoolState(
            symbol=symbol,
            token0_reserve=token0_reserve,
            token1_reserve=token1_reserve,
            fee_pct=fee_pct,
        )
        pool.update_k()
        self._pools[symbol] = pool
        logger.debug(f"Initialized pool {symbol}: {token0_reserve}/{token1_reserve}")
        
    def initialize_default_pools(self):
        """Initialize default pools for common pairs."""
        # Reserves represent liquidity depth
        self.initialize_pool("BTCUSDT", 100, 4200000)  # 100 BTC, $4.2M
        self.initialize_pool("ETHUSDT", 1000, 2200000)  # 1000 ETH, $2.2M
        self.initialize_pool("BNBUSDT", 5000, 1500000)  # 5000 BNB
        self.initialize_pool("SOLUSDT", 10000, 1000000)  # 10000 SOL
        
    def set_token_trap(self, symbol: str, trap_type: TokenTrapType):
        """Set a token trap for simulation."""
        self._token_traps[symbol] = trap_type
        logger.debug(f"Set token trap for {symbol}: {trap_type}")
        
    def clear_token_trap(self, symbol: str):
        """Clear token trap."""
        if symbol in self._token_traps:
            del self._token_traps[symbol]
            
    def inject_liquidity_reduction(self, symbol: str, reduction_pct: float):
        """Reduce pool liquidity (simulates dry-up)."""
        if symbol in self._pools:
            pool = self._pools[symbol]
            multiplier = 1 - (reduction_pct / 100)
            pool.token0_reserve *= multiplier
            pool.token1_reserve *= multiplier
            pool.update_k()
            logger.debug(f"Reduced {symbol} liquidity by {reduction_pct}%")
            
    def inject_mev_risk(self, probability: float):
        """Increase MEV risk probability."""
        self._mev_probability = min(probability, 0.9)
        
    def inject_gas_spike(self, multiplier: float):
        """Multiply gas costs."""
        self._gas_multiplier = multiplier
        
    def reset_conditions(self):
        """Reset all injected conditions."""
        self._mev_probability = 0.1
        self._gas_multiplier = 1.0
        self._token_traps.clear()
        
    def _calculate_price_impact(self, pool: PoolState, amount_in: float, 
                                is_buy: bool) -> Tuple[float, float]:
        """
        Calculate price impact using constant product formula.
        
        Returns (amount_out, price_impact_pct)
        """
        if is_buy:
            # Buying token0 with token1
            # x * y = k
            # (x - dx) * (y + dy) = k
            # dx = x - k / (y + dy)
            reserve_in = pool.token1_reserve
            reserve_out = pool.token0_reserve
        else:
            # Selling token0 for token1
            reserve_in = pool.token0_reserve
            reserve_out = pool.token1_reserve
        
        # Apply fee to input
        amount_in_after_fee = amount_in * (1 - pool.fee_pct / 100)
        
        # Calculate output using constant product
        # new_reserve_in = reserve_in + amount_in_after_fee
        # new_reserve_out = k / new_reserve_in
        # amount_out = reserve_out - new_reserve_out
        
        new_reserve_in = reserve_in + amount_in_after_fee
        new_reserve_out = pool.k / new_reserve_in
        amount_out = reserve_out - new_reserve_out
        
        # Calculate spot price and executed price
        spot_price = reserve_out / reserve_in if reserve_in > 0 else 0
        executed_price = amount_out / amount_in if amount_in > 0 else 0
        
        # Price impact
        if spot_price > 0:
            price_impact_pct = abs((executed_price - spot_price) / spot_price) * 100
        else:
            price_impact_pct = 0
        
        return max(0, amount_out), price_impact_pct
    
    def _simulate_mev(self, swap: SwapRequest, base_amount_out: float, 
                      price_impact: float) -> Tuple[MEVResult, float, float]:
        """
        Simulate MEV attack probability and impact.
        
        Returns (mev_result, adjusted_amount_out, mev_loss_pct)
        """
        # MEV probability increases with:
        # - Trade size (higher impact = more attractive)
        # - Slippage tolerance (more room to extract)
        # - Base MEV risk level
        
        size_factor = min(1.0, price_impact / 2)  # Higher impact = more attractive
        slippage_factor = min(1.0, swap.max_slippage_pct / 2)
        
        adjusted_prob = self._mev_probability * (1 + size_factor + slippage_factor)
        adjusted_prob = min(adjusted_prob, 0.8)  # Cap at 80%
        
        if self._rng.random() > adjusted_prob:
            return MEVResult.NO_MEV, base_amount_out, 0.0
        
        # Determine MEV type
        mev_type = self._rng.choices(
            [MEVResult.FRONTRUN, MEVResult.SANDWICH, MEVResult.BACKRUN],
            weights=[0.3, 0.5, 0.2]
        )[0]
        
        # Calculate extraction (within slippage bounds)
        max_extraction = base_amount_out * (swap.max_slippage_pct / 100) * 0.8
        extraction = self._rng.uniform(0.3, 1.0) * max_extraction
        
        mev_loss_pct = (extraction / base_amount_out * 100) if base_amount_out > 0 else 0
        adjusted_out = base_amount_out - extraction
        
        return mev_type, adjusted_out, mev_loss_pct
    
    def _calculate_gas_cost(self, gas_price_gwei: float) -> float:
        """Calculate gas cost in USD."""
        effective_gas_price = gas_price_gwei * self._gas_multiplier
        gas_cost_eth = (self.BASE_GAS_UNITS * effective_gas_price) / 1e9
        gas_cost_usd = gas_cost_eth * self.ETH_PRICE_USD
        return gas_cost_usd
    
    async def simulate_swap(self, swap: SwapRequest) -> SwapResult:
        """
        Simulate a DEX swap.
        
        Returns SwapResult with all details.
        """
        pool = self._pools.get(swap.pool_symbol)
        if not pool:
            return SwapResult(
                swap_id=swap.swap_id,
                pool_symbol=swap.pool_symbol,
                side=swap.side,
                status="reverted",
                amount_in=swap.amount_in,
                amount_out=0,
                expected_out=0,
                price_impact_pct=0,
                slippage_pct=0,
                swap_fee_pct=0,
                gas_cost_usd=self._calculate_gas_cost(swap.gas_price_gwei),
            )
        
        # Check for token trap
        trap_type = self._token_traps.get(swap.pool_symbol, TokenTrapType.NONE)
        
        # Honeypot: can buy but can't sell
        if trap_type == TokenTrapType.HONEYPOT and swap.side.lower() == "sell":
            return SwapResult(
                swap_id=swap.swap_id,
                pool_symbol=swap.pool_symbol,
                side=swap.side,
                status="blocked",
                amount_in=swap.amount_in,
                amount_out=0,
                expected_out=0,
                price_impact_pct=0,
                slippage_pct=100,
                swap_fee_pct=pool.fee_pct,
                gas_cost_usd=self._calculate_gas_cost(swap.gas_price_gwei),
                trap_type=trap_type,
                trap_blocked=True,
            )
        
        # Max TX trap
        if trap_type == TokenTrapType.MAX_TX:
            max_tx = pool.token0_reserve * 0.01  # 1% of pool
            if swap.amount_in > max_tx:
                return SwapResult(
                    swap_id=swap.swap_id,
                    pool_symbol=swap.pool_symbol,
                    side=swap.side,
                    status="reverted",
                    amount_in=swap.amount_in,
                    amount_out=0,
                    expected_out=0,
                    price_impact_pct=0,
                    slippage_pct=0,
                    swap_fee_pct=pool.fee_pct,
                    gas_cost_usd=self._calculate_gas_cost(swap.gas_price_gwei),
                    trap_type=trap_type,
                    trap_blocked=True,
                )
        
        # Calculate base swap
        is_buy = swap.side.lower() == "buy"
        amount_out, price_impact = self._calculate_price_impact(pool, swap.amount_in, is_buy)
        
        # Apply fee-on-transfer tax
        tax_pct = 0.0
        if trap_type == TokenTrapType.FEE_ON_TRANSFER:
            tax_pct = self._rng.uniform(3, 15)  # 3-15% tax
            amount_out *= (1 - tax_pct / 100)
        
        # Calculate expected output (without MEV)
        expected_out = amount_out
        
        # Simulate MEV
        mev_result, final_amount_out, mev_loss = self._simulate_mev(
            swap, amount_out, price_impact
        )
        
        # Calculate actual slippage
        if expected_out > 0:
            slippage_pct = abs((final_amount_out - expected_out) / expected_out) * 100
        else:
            slippage_pct = 0
        
        # Check slippage tolerance
        if final_amount_out < swap.min_amount_out:
            return SwapResult(
                swap_id=swap.swap_id,
                pool_symbol=swap.pool_symbol,
                side=swap.side,
                status="reverted",
                amount_in=swap.amount_in,
                amount_out=0,
                expected_out=expected_out,
                price_impact_pct=price_impact,
                slippage_pct=slippage_pct,
                swap_fee_pct=pool.fee_pct,
                tax_pct=tax_pct,
                gas_cost_usd=self._calculate_gas_cost(swap.gas_price_gwei),
                mev_result=mev_result,
                mev_loss_pct=mev_loss,
                trap_type=trap_type,
            )
        
        # Update pool reserves (simplified - in real AMM this would be atomic)
        if is_buy:
            pool.token1_reserve += swap.amount_in * (1 - pool.fee_pct / 100)
            pool.token0_reserve -= final_amount_out
        else:
            pool.token0_reserve += swap.amount_in * (1 - pool.fee_pct / 100)
            pool.token1_reserve -= final_amount_out
        
        # Gas cost
        gas_cost = self._calculate_gas_cost(swap.gas_price_gwei)
        
        result = SwapResult(
            swap_id=swap.swap_id,
            pool_symbol=swap.pool_symbol,
            side=swap.side,
            status="success",
            amount_in=swap.amount_in,
            amount_out=final_amount_out,
            expected_out=expected_out,
            price_impact_pct=price_impact,
            slippage_pct=slippage_pct,
            swap_fee_pct=pool.fee_pct,
            tax_pct=tax_pct,
            gas_cost_usd=gas_cost,
            mev_result=mev_result,
            mev_loss_pct=mev_loss,
            trap_type=trap_type,
        )
        
        self._swaps.append(result)
        
        logger.debug(f"DEX swap: {swap.side} {swap.amount_in} -> {final_amount_out} (impact: {price_impact:.2f}%)")
        
        return result
    
    def get_pool_state(self, symbol: str) -> Optional[PoolState]:
        """Get current pool state."""
        return self._pools.get(symbol)
    
    def get_swap_stats(self) -> Dict[str, Any]:
        """Get swap statistics."""
        if not self._swaps:
            return {
                "total_swaps": 0,
                "successful": 0,
                "reverted": 0,
                "blocked": 0,
                "mev_hits": 0,
                "avg_price_impact": 0,
                "avg_slippage": 0,
                "total_gas_usd": 0,
            }
        
        successful = [s for s in self._swaps if s.status == "success"]
        reverted = [s for s in self._swaps if s.status == "reverted"]
        blocked = [s for s in self._swaps if s.status == "blocked"]
        mev_hits = [s for s in self._swaps if s.mev_result != MEVResult.NO_MEV]
        
        return {
            "total_swaps": len(self._swaps),
            "successful": len(successful),
            "reverted": len(reverted),
            "blocked": len(blocked),
            "mev_hits": len(mev_hits),
            "avg_price_impact": sum(s.price_impact_pct for s in successful) / len(successful) if successful else 0,
            "avg_slippage": sum(s.slippage_pct for s in successful) / len(successful) if successful else 0,
            "total_gas_usd": sum(s.gas_cost_usd for s in self._swaps),
        }
    
    def get_all_swaps(self) -> List[SwapResult]:
        """Get all swap results."""
        return self._swaps.copy()
