# Realistic Simulation Engine with Fees, Slippage, Partial Fills
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Literal
from enum import Enum
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class FeeStructure(BaseModel):
    """Exchange fee structure"""
    maker_fee: float = 0.001  # 0.1%
    taker_fee: float = 0.001  # 0.1%
    # Binance VIP levels have lower fees, this is default


class SlippageModel(BaseModel):
    """Slippage simulation parameters"""
    base_slippage_pct: float = 0.0005  # 0.05% base
    volatility_multiplier: float = 1.5  # Higher in volatile markets
    size_impact: float = 0.0001  # Additional slippage per $10k order


class ExecutionConfig(BaseModel):
    """Execution simulation configuration"""
    fees: FeeStructure = FeeStructure()
    slippage: SlippageModel = SlippageModel()
    min_partial_fill_pct: float = 0.1  # Minimum 10% of order
    latency_ms_range: tuple = (50, 200)  # Simulated network latency
    partial_fill_probability: float = 0.15  # 15% chance of partial fill


class SimulatedExecution(BaseModel):
    """Result of a simulated order execution"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    requested_amount: float
    requested_price: Optional[float]
    executed_amount: float
    executed_price: float
    slippage: float
    slippage_pct: float
    fees: float
    fee_pct: float
    net_cost: float  # Total cost including fees (for buys)
    net_proceeds: float  # Total proceeds after fees (for sells)
    is_partial: bool
    fill_pct: float
    latency_ms: int
    timestamp: datetime


class RealisticExecutionEngine:
    """Simulates realistic order execution with fees, slippage, and partial fills"""
    
    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
    
    def calculate_slippage(
        self,
        side: str,
        price: float,
        amount: float,
        volatility: float = 0.02,
        orderbook_depth: float = 100000
    ) -> float:
        """Calculate realistic slippage based on order size and market conditions"""
        # Base slippage
        base = self.config.slippage.base_slippage_pct
        
        # Volatility impact
        vol_impact = base * volatility * self.config.slippage.volatility_multiplier
        
        # Size impact (larger orders move price more)
        order_value = price * amount
        size_impact = (order_value / orderbook_depth) * self.config.slippage.size_impact
        
        # Total slippage percentage
        total_slippage_pct = base + vol_impact + size_impact
        
        # Random variation (+/- 50%)
        variation = random.uniform(0.5, 1.5)
        total_slippage_pct *= variation
        
        # Direction: buys slip up, sells slip down
        slippage_amount = price * total_slippage_pct
        if side == "buy":
            return slippage_amount  # Pay more
        else:
            return -slippage_amount  # Receive less
    
    def calculate_fees(
        self,
        amount: float,
        price: float,
        is_maker: bool = False
    ) -> float:
        """Calculate trading fees"""
        fee_rate = self.config.fees.maker_fee if is_maker else self.config.fees.taker_fee
        return amount * price * fee_rate
    
    def simulate_partial_fill(self, amount: float) -> tuple:
        """Determine if order is partially filled and by how much"""
        if random.random() < self.config.partial_fill_probability:
            # Partial fill
            fill_pct = random.uniform(self.config.min_partial_fill_pct, 0.95)
            return (amount * fill_pct, True, fill_pct)
        else:
            # Full fill
            return (amount, False, 1.0)
    
    def simulate_latency(self) -> int:
        """Simulate network/execution latency"""
        return random.randint(*self.config.latency_ms_range)
    
    def execute_market_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        volatility: float = 0.02,
        orderbook_depth: float = 100000
    ) -> SimulatedExecution:
        """Simulate market order execution"""
        # Calculate slippage
        slippage = self.calculate_slippage(side, current_price, amount, volatility, orderbook_depth)
        executed_price = current_price + slippage
        slippage_pct = (slippage / current_price) * 100
        
        # Simulate partial fill
        executed_amount, is_partial, fill_pct = self.simulate_partial_fill(amount)
        
        # Calculate fees (market orders are taker)
        fees = self.calculate_fees(executed_amount, executed_price, is_maker=False)
        fee_pct = (fees / (executed_amount * executed_price)) * 100
        
        # Calculate net values
        if side == "buy":
            net_cost = (executed_amount * executed_price) + fees
            net_proceeds = 0
        else:
            net_cost = 0
            net_proceeds = (executed_amount * executed_price) - fees
        
        # Simulate latency
        latency = self.simulate_latency()
        
        return SimulatedExecution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="market",
            requested_amount=amount,
            requested_price=None,
            executed_amount=executed_amount,
            executed_price=executed_price,
            slippage=slippage,
            slippage_pct=slippage_pct,
            fees=fees,
            fee_pct=fee_pct,
            net_cost=net_cost,
            net_proceeds=net_proceeds,
            is_partial=is_partial,
            fill_pct=fill_pct,
            latency_ms=latency,
            timestamp=datetime.now(timezone.utc)
        )
    
    def execute_limit_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        amount: float,
        limit_price: float,
        current_price: float,
        volatility: float = 0.02
    ) -> Optional[SimulatedExecution]:
        """Simulate limit order execution (only fills if price crosses limit)"""
        # Check if order would fill
        if side == "buy" and current_price > limit_price:
            return None  # Won't fill yet
        if side == "sell" and current_price < limit_price:
            return None  # Won't fill yet
        
        # Order fills at limit price (or better)
        if side == "buy":
            executed_price = min(limit_price, current_price)
        else:
            executed_price = max(limit_price, current_price)
        
        # Small slippage even for limit orders (rare)
        if random.random() < 0.05:  # 5% chance
            small_slippage = executed_price * 0.0001 * (1 if side == "buy" else -1)
            executed_price += small_slippage
        
        # Partial fill simulation
        executed_amount, is_partial, fill_pct = self.simulate_partial_fill(amount)
        
        # Calculate fees (limit orders can be maker)
        is_maker = random.random() < 0.7  # 70% chance of maker
        fees = self.calculate_fees(executed_amount, executed_price, is_maker=is_maker)
        fee_pct = (fees / (executed_amount * executed_price)) * 100
        
        # Calculate net values
        slippage = executed_price - limit_price
        slippage_pct = (slippage / limit_price) * 100
        
        if side == "buy":
            net_cost = (executed_amount * executed_price) + fees
            net_proceeds = 0
        else:
            net_cost = 0
            net_proceeds = (executed_amount * executed_price) - fees
        
        return SimulatedExecution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="limit",
            requested_amount=amount,
            requested_price=limit_price,
            executed_amount=executed_amount,
            executed_price=executed_price,
            slippage=slippage,
            slippage_pct=slippage_pct,
            fees=fees,
            fee_pct=fee_pct,
            net_cost=net_cost,
            net_proceeds=net_proceeds,
            is_partial=is_partial,
            fill_pct=fill_pct,
            latency_ms=self.simulate_latency(),
            timestamp=datetime.now(timezone.utc)
        )


class PositionManager:
    """Manages positions with realistic P&L calculations"""
    
    def __init__(self, execution_engine: RealisticExecutionEngine):
        self.engine = execution_engine
        self.positions: Dict[str, Dict] = {}  # key: position_id
    
    def open_position(
        self,
        position_id: str,
        agent_id: str,
        symbol: str,
        side: str,
        amount: float,
        entry_price: float,
        execution: SimulatedExecution
    ) -> Dict:
        """Open a new position with execution details"""
        position = {
            "id": position_id,
            "agent_id": agent_id,
            "symbol": symbol,
            "side": side,
            "amount": execution.executed_amount,
            "entry_price": execution.executed_price,
            "current_price": execution.executed_price,
            "entry_fees": execution.fees,
            "entry_slippage": execution.slippage,
            "unrealized_pnl": 0,
            "realized_pnl": 0,
            "status": "open",
            "opened_at": execution.timestamp,
            "closed_at": None,
            "exit_price": None,
            "exit_fees": 0,
            "total_fees": execution.fees,
            "executions": [execution.model_dump()]
        }
        
        self.positions[position_id] = position
        return position
    
    def update_position_price(self, position_id: str, current_price: float) -> Dict:
        """Update position with current price and recalculate P&L"""
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        position["current_price"] = current_price
        
        # Calculate unrealized P&L (before exit fees)
        if position["side"] == "buy":
            price_diff = current_price - position["entry_price"]
        else:
            price_diff = position["entry_price"] - current_price
        
        position["unrealized_pnl"] = (price_diff * position["amount"]) - position["entry_fees"]
        
        return position
    
    def close_position(
        self,
        position_id: str,
        exit_price: float,
        volatility: float = 0.02
    ) -> Optional[Dict]:
        """Close position with realistic exit execution"""
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        if position["status"] == "closed":
            return position
        
        # Simulate exit execution
        exit_side = "sell" if position["side"] == "buy" else "buy"
        execution = self.engine.execute_market_order(
            order_id=f"exit_{position_id}",
            symbol=position["symbol"],
            side=exit_side,
            amount=position["amount"],
            current_price=exit_price,
            volatility=volatility
        )
        
        # Update position
        position["exit_price"] = execution.executed_price
        position["exit_fees"] = execution.fees
        position["total_fees"] = position["entry_fees"] + execution.fees
        position["closed_at"] = execution.timestamp
        position["status"] = "closed"
        position["executions"].append(execution.model_dump())
        
        # Calculate realized P&L
        if position["side"] == "buy":
            gross_pnl = (execution.executed_price - position["entry_price"]) * execution.executed_amount
        else:
            gross_pnl = (position["entry_price"] - execution.executed_price) * execution.executed_amount
        
        position["realized_pnl"] = gross_pnl - position["total_fees"]
        position["unrealized_pnl"] = 0
        
        return position


class CircuitBreaker:
    """Circuit breaker for automatic agent shutdown"""
    
    def __init__(
        self,
        max_consecutive_losses: int = 5,
        max_daily_loss_pct: float = 5.0,
        max_drawdown_pct: float = 10.0,
        cooldown_minutes: int = 60
    ):
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_minutes = cooldown_minutes
        
        self.consecutive_losses: Dict[str, int] = {}  # agent_id -> count
        self.daily_pnl: Dict[str, float] = {}  # agent_id -> pnl
        self.peak_equity: Dict[str, float] = {}  # agent_id -> peak
        self.tripped: Dict[str, Dict] = {}  # agent_id -> trip info
    
    def record_trade(
        self,
        agent_id: str,
        pnl: float,
        current_equity: float,
        initial_capital: float
    ) -> Dict:
        """Record a trade and check circuit breaker conditions"""
        # Initialize if needed
        if agent_id not in self.consecutive_losses:
            self.consecutive_losses[agent_id] = 0
            self.daily_pnl[agent_id] = 0
            self.peak_equity[agent_id] = initial_capital
        
        # Update consecutive losses
        if pnl < 0:
            self.consecutive_losses[agent_id] += 1
        else:
            self.consecutive_losses[agent_id] = 0
        
        # Update daily P&L
        self.daily_pnl[agent_id] += pnl
        
        # Update peak equity
        if current_equity > self.peak_equity[agent_id]:
            self.peak_equity[agent_id] = current_equity
        
        # Check conditions
        reasons = []
        
        # Consecutive losses
        if self.consecutive_losses[agent_id] >= self.max_consecutive_losses:
            reasons.append(f"consecutive_losses:{self.consecutive_losses[agent_id]}")
        
        # Daily loss
        daily_loss_pct = abs(self.daily_pnl[agent_id]) / initial_capital * 100
        if self.daily_pnl[agent_id] < 0 and daily_loss_pct >= self.max_daily_loss_pct:
            reasons.append(f"daily_loss:{daily_loss_pct:.2f}%")
        
        # Drawdown
        drawdown = (self.peak_equity[agent_id] - current_equity) / self.peak_equity[agent_id] * 100
        if drawdown >= self.max_drawdown_pct:
            reasons.append(f"drawdown:{drawdown:.2f}%")
        
        is_tripped = len(reasons) > 0
        
        if is_tripped:
            self.tripped[agent_id] = {
                "tripped_at": datetime.now(timezone.utc),
                "reasons": reasons,
                "cooldown_until": datetime.now(timezone.utc) + timedelta(minutes=self.cooldown_minutes)
            }
        
        return {
            "agent_id": agent_id,
            "tripped": is_tripped,
            "reasons": reasons,
            "consecutive_losses": self.consecutive_losses[agent_id],
            "daily_pnl": self.daily_pnl[agent_id],
            "daily_loss_pct": daily_loss_pct if self.daily_pnl[agent_id] < 0 else 0,
            "drawdown_pct": drawdown
        }
    
    def is_agent_blocked(self, agent_id: str) -> tuple:
        """Check if agent is blocked by circuit breaker"""
        if agent_id not in self.tripped:
            return (False, None)
        
        trip_info = self.tripped[agent_id]
        if datetime.now(timezone.utc) < trip_info["cooldown_until"]:
            return (True, trip_info)
        else:
            # Cooldown expired, reset
            del self.tripped[agent_id]
            self.consecutive_losses[agent_id] = 0
            return (False, None)
    
    def reset_daily(self):
        """Reset daily counters (call at day boundary)"""
        self.daily_pnl = {}


from datetime import timedelta
