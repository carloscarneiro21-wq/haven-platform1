"""Paper Executor - Realistic paper trading simulation.

Simulates:
- Real-time prices from data feed
- Slippage based on order size and volatility
- Trading fees (maker/taker)
- Network latency
- Partial fills
- Order rejections

All paper trades are stored in DB with full simulation metadata.
"""

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import numpy as np

logger = logging.getLogger(__name__)


class PaperTradeExecutor:
    """Realistic paper trading executor.
    
    Simulates:
    - Slippage: 0.01% base + order size impact
    - Fees: 0.1% (Binance standard)
    - Latency: 50-300ms
    - Partial fills: 15% probability
    - Rejections: 2% probability (market conditions)
    """
    
    # Fee structure (Binance spot)
    MAKER_FEE = 0.001  # 0.1%
    TAKER_FEE = 0.001  # 0.1%
    
    # Slippage model
    BASE_SLIPPAGE = 0.0001  # 0.01%
    SIZE_IMPACT_FACTOR = 0.00001  # Additional slippage per €1000
    
    # Latency range (ms)
    MIN_LATENCY_MS = 50
    MAX_LATENCY_MS = 300
    
    # Probabilities
    PARTIAL_FILL_PROB = 0.15
    REJECTION_PROB = 0.02
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._data_feed = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize paper executor."""
        # Try to get data feed for real prices
        try:
            from services.data_feed import get_data_feed
            self._data_feed = get_data_feed()
        except Exception as e:
            logger.warning(f"Could not initialize data feed: {e}")
        
        self._initialized = True
        logger.info("PaperTradeExecutor initialized")
    
    async def execute(self, request) -> "TradeResult":
        """Execute a paper trade with realistic simulation."""
        from services.execution.router import TradeResult
        
        result = TradeResult(
            request_id=request.request_id,
            execution_id=str(uuid.uuid4()),
            mode="paper",
            symbol=request.symbol,
            side=request.side,
        )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Simulate network latency
            latency_ms = random.randint(self.MIN_LATENCY_MS, self.MAX_LATENCY_MS)
            await asyncio.sleep(latency_ms / 1000)
            result.latency_ms = latency_ms
            
            # Check for random rejection (simulates market conditions)
            if random.random() < self.REJECTION_PROB:
                result.success = False
                result.status = "REJECTED"
                result.fill_status = "REJECTED"
                result.error_message = "Order rejected: Simulated market conditions"
                return result
            
            # Get current price
            current_price = await self._get_current_price(request.symbol, request.price)
            
            # Calculate execution price with slippage
            slippage = self._calculate_slippage(request.amount, current_price, request.side)
            if request.side.upper() == "BUY":
                execution_price = current_price * (1 + slippage)
            else:
                execution_price = current_price * (1 - slippage)
            
            # Determine fill amount (partial fills)
            if random.random() < self.PARTIAL_FILL_PROB:
                fill_pct = random.uniform(0.3, 0.95)
                executed_amount = request.amount * fill_pct
                result.fill_status = "PARTIAL"
                result.status = "PARTIAL"
            else:
                executed_amount = request.amount
                result.fill_status = "FILLED"
                result.status = "FILLED"
            
            # Calculate fees
            is_taker = request.order_type.upper() == "MARKET"
            fee_rate = self.TAKER_FEE if is_taker else self.MAKER_FEE
            fees = executed_amount * execution_price * fee_rate
            
            # Update result
            result.success = True
            result.entry_price = execution_price
            result.executed_amount = executed_amount
            result.remaining_amount = request.amount - executed_amount
            result.fees = fees
            result.slippage = slippage * 100  # Convert to percentage
            
            # Store paper trade
            await self._store_paper_trade(request, result)
            
            logger.info(
                f"Paper trade executed: {request.side} {executed_amount:.4f} {request.symbol} "
                f"@ {execution_price:.2f} (slippage: {slippage*100:.3f}%, fees: €{fees:.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Paper execution error: {e}")
            result.success = False
            result.status = "ERROR"
            result.error_message = str(e)
            return result
    
    async def _get_current_price(self, symbol: str, fallback_price: Optional[float]) -> float:
        """Get current price from data feed or use fallback."""
        if self._data_feed:
            try:
                ticker = await self._data_feed.fetch_ticker(symbol)
                if ticker and "last" in ticker:
                    return ticker["last"]
            except Exception:
                pass
        
        # Fallback to provided price or reasonable defaults
        if fallback_price and fallback_price > 0:
            return fallback_price
        
        # Default prices for common symbols
        defaults = {
            "BTC/USDT": 65000.0,
            "BTCUSDT": 65000.0,
            "ETH/USDT": 3500.0,
            "ETHUSDT": 3500.0,
            "SOL/USDT": 150.0,
            "SOLUSDT": 150.0,
        }
        return defaults.get(symbol.upper(), 100.0)
    
    def _calculate_slippage(self, amount: float, price: float, side: str) -> float:
        """Calculate realistic slippage based on order size."""
        # Base slippage
        base = self.BASE_SLIPPAGE
        
        # Size impact (larger orders have more slippage)
        order_value = amount * price
        size_impact = (order_value / 1000) * self.SIZE_IMPACT_FACTOR
        
        # Random market variation
        variation = np.random.uniform(0.5, 1.5)
        
        total_slippage = (base + size_impact) * variation
        
        # Cap at 1%
        return min(total_slippage, 0.01)
    
    async def _store_paper_trade(self, request, result):
        """Store paper trade in database."""
        try:
            doc = {
                "trade_id": result.execution_id,
                "request_id": request.request_id,
                "mode": "paper",
                "agent_id": request.agent_id,
                "agent_type": request.agent_type,
                "symbol": request.symbol,
                "side": request.side,
                "order_type": request.order_type,
                "requested_amount": request.amount,
                "executed_amount": result.executed_amount,
                "entry_price": result.entry_price,
                "fees": result.fees,
                "slippage_pct": result.slippage,
                "latency_ms": result.latency_ms,
                "fill_status": result.fill_status,
                "status": result.status,
                "strategy": request.strategy,
                "reason": request.reason,
                "venue": request.venue,
                "simulation_metadata": {
                    "fee_rate": self.TAKER_FEE if request.order_type.upper() == "MARKET" else self.MAKER_FEE,
                    "base_slippage": self.BASE_SLIPPAGE,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            await self.db.paper_trades.insert_one(doc)
            
        except Exception as e:
            logger.error(f"Failed to store paper trade: {e}")
