"""Trading models for the crypto trading system."""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from enum import Enum
import uuid


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class AgentType(str, Enum):
    DCA = "dca"
    GRID = "grid"
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"


class AgentStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


# ============ Market Data Models ============

class Candle(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketFeatures(BaseModel):
    """Calculated indicators and regime detection."""
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Price data
    last_price: float = 0.0
    price_change_24h: float = 0.0
    
    # Moving Averages
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    sma_20: float = 0.0
    sma_50: float = 0.0
    
    # Momentum
    rsi_14: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    
    # Trend
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    
    # Volatility
    atr_14: float = 0.0
    bollinger_upper: float = 0.0
    bollinger_middle: float = 0.0
    bollinger_lower: float = 0.0
    volatility_pct: float = 0.0
    
    # Regime
    regime: MarketRegime = MarketRegime.RANGING


# ============ Order Models ============

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))  # For duplicate prevention
    agent_id: str
    agent_type: AgentType
    symbol: str
    exchange: str = "binance"
    
    side: OrderSide
    order_type: OrderType
    amount: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    
    status: OrderStatus = OrderStatus.PENDING
    filled: float = 0.0
    remaining: float = 0.0
    average_price: float = 0.0
    commission: float = 0.0
    
    reason: str = ""  # Why the order was created
    
    # Replay protection
    replay_count: int = 0  # Track how many times this order was attempted
    original_order_id: Optional[str] = None  # For retry tracking
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    filled_at: Optional[datetime] = None


class OrderPlan(BaseModel):
    """Plan of orders to execute from an agent."""
    agent_id: str
    agent_type: AgentType
    orders: List[Order] = []
    reason: str = ""
    priority: int = 0  # Higher = more urgent


class Signal(BaseModel):
    """Trading signal from an agent."""
    agent_id: str
    agent_type: AgentType
    symbol: str
    action: Literal["buy", "sell", "hold", "close"]
    strength: float = 0.0  # 0-1, confidence
    reason: str = ""
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Position Models ============

class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    agent_type: AgentType
    symbol: str
    exchange: str = "binance"
    
    side: OrderSide
    entry_price: float
    current_price: float = 0.0
    amount: float
    
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    
    is_open: bool = True


# ============ Trade Models ============

class Trade(BaseModel):
    """Completed trade record."""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    position_id: Optional[str] = None
    agent_id: str
    agent_type: AgentType
    symbol: str
    exchange: str = "binance"
    
    side: OrderSide
    amount: float
    price: float
    value: float = 0.0
    commission: float = 0.0
    
    pnl: float = 0.0
    reason: str = ""
    
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Agent Config Models ============

class DCAConfig(BaseModel):
    """DCA Agent configuration."""
    enabled: bool = True
    symbol: str = "BTC/USDT"
    
    # Interval settings
    interval_hours: int = 24
    next_execution: Optional[datetime] = None
    
    # Sizing
    base_amount: float = 100.0  # USDT per buy
    max_amount: float = 500.0
    scaling_factor: float = 1.5  # Multiply on dips
    
    # Dip triggers
    dip_threshold_pct: float = 5.0  # Extra buy on 5% dip
    dip_cooldown_hours: int = 4
    
    # Limits
    max_exposure: float = 10000.0  # Max total investment
    current_exposure: float = 0.0


class GridConfig(BaseModel):
    """Grid Trading Agent configuration."""
    enabled: bool = True
    symbol: str = "BTC/USDT"
    
    # Grid parameters
    grid_type: Literal["arithmetic", "geometric"] = "arithmetic"
    num_grids: int = 10
    upper_price: float = 0.0
    lower_price: float = 0.0
    
    # Auto-adjust
    auto_adjust: bool = True
    volatility_multiplier: float = 2.0
    
    # Sizing
    amount_per_grid: float = 50.0  # USDT per grid level
    
    # Current state
    active_buy_orders: int = 0
    active_sell_orders: int = 0
    grid_levels: List[float] = []


class TrendConfig(BaseModel):
    """Trend Following Agent configuration."""
    enabled: bool = True
    symbol: str = "BTC/USDT"
    
    # Entry conditions
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    adx_threshold: float = 25.0
    
    # Position sizing
    position_size_pct: float = 5.0  # % of capital
    max_position_size: float = 1000.0
    
    # Risk management
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    trailing_stop_pct: float = 2.0
    
    # Current state
    in_position: bool = False
    position_side: Optional[OrderSide] = None


class MeanReversionConfig(BaseModel):
    """Mean Reversion Agent configuration."""
    enabled: bool = True
    symbol: str = "BTC/USDT"
    
    # Entry conditions
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    bb_deviation: float = 2.0  # Std deviations for Bollinger Bands
    vwap_deviation_pct: float = 2.0  # % deviation from VWAP
    
    # Position sizing
    position_size_pct: float = 5.0  # % of capital
    max_position_size: float = 1000.0
    
    # Risk management
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 3.0
    
    # Regime filter
    require_ranging: bool = True
    max_adx: float = 25.0  # ADX below this = ranging market
    
    # Current state
    in_position: bool = False
    position_side: Optional[OrderSide] = None


class BreakoutConfig(BaseModel):
    """Breakout/Momentum Agent configuration."""
    enabled: bool = True
    symbol: str = "BTC/USDT"
    
    # Breakout detection
    lookback_periods: int = 20  # Periods to find levels
    breakout_threshold_pct: float = 1.0  # % above/below level
    volume_multiplier: float = 1.5  # Volume > avg * multiplier
    
    # Volatility expansion
    atr_multiplier: float = 1.5  # ATR expansion threshold
    
    # Position sizing
    position_size_pct: float = 5.0
    max_position_size: float = 1000.0
    
    # Risk management (ATR-based)
    stop_loss_atr_mult: float = 2.0  # Stop at entry - 2*ATR
    take_profit_atr_mult: float = 3.0  # TP at entry + 3*ATR
    trailing_stop_atr_mult: float = 1.5
    
    # Filters
    min_adx: float = 20.0  # Minimum trend strength for breakouts
    
    # Current state
    in_position: bool = False
    position_side: Optional[OrderSide] = None


class AgentConfig(BaseModel):
    """Combined agent configuration."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType
    status: AgentStatus = AgentStatus.STOPPED
    
    dca: Optional[DCAConfig] = None
    grid: Optional[GridConfig] = None
    trend: Optional[TrendConfig] = None
    mean_reversion: Optional[MeanReversionConfig] = None
    breakout: Optional[BreakoutConfig] = None
    
    # Capital allocation
    allocated_capital: float = 0.0
    used_capital: float = 0.0
    
    # Performance
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Risk Models ============

class RiskSettings(BaseModel):
    """Global risk management settings."""
    # Daily limits
    max_daily_loss: float = 500.0
    max_daily_loss_pct: float = 5.0
    current_daily_pnl: float = 0.0
    
    # Position limits
    max_position_size: float = 5000.0
    max_total_exposure: float = 20000.0
    current_total_exposure: float = 0.0
    
    # Drawdown
    max_drawdown_pct: float = 15.0
    current_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    
    # Circuit breakers
    kill_switch_active: bool = False
    cooldown_until: Optional[datetime] = None
    consecutive_losses: int = 0
    max_consecutive_losses: int = 5
    
    # Correlation limits
    max_correlated_exposure: float = 10000.0
    
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RiskCheckResult(BaseModel):
    """Result of a risk check."""
    allowed: bool
    reason: str = ""
    adjusted_amount: Optional[float] = None
    warnings: List[str] = []


# ============ Portfolio Models ============

class PortfolioSummary(BaseModel):
    """Portfolio overview."""
    total_equity: float = 0.0
    available_balance: float = 0.0
    used_margin: float = 0.0
    
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    
    open_positions: int = 0
    pending_orders: int = 0
    
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============ Log Models ============

class TradeLog(BaseModel):
    """Detailed trade decision log."""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    agent_type: AgentType
    symbol: str
    
    action: str
    reason: str
    market_conditions: Dict[str, Any] = {}
    signal_strength: float = 0.0
    
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemLog(BaseModel):
    """System event log."""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    level: Literal["info", "warning", "error", "critical"]
    component: str
    message: str
    details: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
