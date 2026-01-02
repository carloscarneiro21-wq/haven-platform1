"""Execution Router - Single canonical executor for HAVEN.

🔒 CRITICAL: ALL agents MUST call this router.
NO agent is allowed to call CEX or DEX SDKs directly.

Pseudo-code:
    executeTrade(params) {
        if (TRADING_MODE === 'paper') {
            return paperExecutor(params)
        }
        if (TRADING_MODE === 'live' && LIVE_CEX_ENABLED && GO_LIVE_GATE === 'GO') {
            return liveExecutor(params)
        }
        throw Error('Execution blocked by safety rules')
    }
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from services.execution.config import TradingConfig, TradingMode, get_trading_config

logger = logging.getLogger(__name__)


class TradeRequest(BaseModel):
    """Trade request from any agent."""
    # Identity
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    agent_type: str  # MM, MOM, SNIPER, DEX, etc.
    
    # Trade details
    symbol: str
    side: str  # BUY or SELL
    amount: float
    price: Optional[float] = None  # None for market orders
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT
    
    # Optional
    venue: str = "binance"  # binance, kraken, uniswap, etc.
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    
    # Metadata
    reason: str = ""
    strategy: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeResult(BaseModel):
    """Result of trade execution."""
    # Identity
    request_id: str
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Mode
    mode: str  # paper, binance_testnet, binance_live
    venue: Optional[str] = None
    order_id: Optional[str] = None
    executed_quote_qty: Optional[float] = None
    avg_fill_price: Optional[float] = None
    pnl_usdt: Optional[float] = None
    
    # Status
    success: bool = False
    status: str = "PENDING"  # PENDING, FILLED, PARTIAL, REJECTED, BLOCKED
    
    # Execution details
    symbol: str
    side: str
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    executed_amount: float = 0.0
    remaining_amount: float = 0.0
    
    # Costs
    fees: float = 0.0
    slippage: float = 0.0
    
    # Performance
    latency_ms: int = 0
    fill_status: str = "PENDING"  # PENDING, FILLED, PARTIAL, REJECTED
    
    # Errors
    error_message: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    # Timestamps
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionRouter:
    """Central execution router for all HAVEN agents.
    
    🔒 SAFETY RULES:
    1. If TRADING_MODE=paper → All trades go through paperExecutor
    2. If TRADING_MODE=live but flags disabled → Execution BLOCKED
    3. If kill switch active → Execution BLOCKED
    4. GO-LIVE gate must be 'GO' for live execution
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        config: Optional[TradingConfig] = None,
        go_live_gate = None,
    ):
        self.db = db
        self.config = config or get_trading_config()
        self.go_live_gate = go_live_gate
        
        # Executors (lazy initialized)
        self._paper_executor = None
        self._binance_testnet_executor = None
        self._binance_live_executor = None
        
        # Stats
        self._total_requests = 0
        self._paper_executions = 0
        self._live_executions = 0
        self._blocked_executions = 0
        
        # Daily tracking
        self._daily_loss_eur = 0.0
        self._daily_loss_usdt = 0.0
        self._daily_trades = 0
        self._last_reset_date: Optional[str] = None
        
        # Event logger
        self.event_logger = None
        
        logger.info(f"ExecutionRouter initialized in {self.config.trading_mode.value} mode")
    
    async def initialize(self):
        """Initialize executors."""
        from services.execution.paper_executor import PaperTradeExecutor
        from services.execution.live_executor import LiveTradeExecutor
        from services.execution.binance_executor import BinanceMarketExecutor
        
        self._paper_executor = PaperTradeExecutor(self.db)
        await self._paper_executor.initialize()
        
        # NOTE: We keep LiveTradeExecutor for older DEX paths, but CEX live is Binance.
        self._binance_testnet_executor = BinanceMarketExecutor("BINANCE_TESTNET")
        self._binance_live_executor = BinanceMarketExecutor("BINANCE_LIVE")
        
        logger.info("ExecutionRouter initialized with Paper + Binance executors")
    
    def _check_daily_reset(self):
        """Reset daily counters if new day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_loss_eur = 0.0
            self._daily_loss_usdt = 0.0
            self._daily_trades = 0
            self._last_reset_date = today
    
    async def execute(self, request: TradeRequest) -> TradeResult:
        """Execute a trade request through the appropriate executor.
        
        This is the SINGLE ENTRY POINT for all trade execution in HAVEN.
        
        Flow:
        1. Pre-flight safety checks
        2. Determine execution mode
        3. Route to appropriate executor
        4. Store result
        5. Update stats
        """
        self._total_requests += 1
        self._check_daily_reset()
        
        result = TradeResult(
            request_id=request.request_id,
            symbol=request.symbol,
            side=request.side,
            mode=self.config.trading_mode.value,
        )
        
        try:
            # 1. Pre-flight safety checks
            block_reason = await self._pre_flight_checks(request)
            if block_reason:
                result.success = False
                result.status = "BLOCKED"
                result.blocked_reason = block_reason
                self._blocked_executions += 1
                await self._store_result(request, result)
                return result
            
            # 2. Route based on trading mode
            if self.config.trading_mode == TradingMode.PAPER:
                result = await self._execute_paper(request)
                self._paper_executions += 1
            elif self.config.trading_mode in [TradingMode.BINANCE_TESTNET, TradingMode.BINANCE_LIVE]:
                live_block = await self._live_pre_flight_checks(request)
                if live_block:
                    result.success = False
                    result.status = "BLOCKED"
                    result.blocked_reason = live_block
                    self._blocked_executions += 1
                else:
                    # Route to Binance executor
                    executor = self._binance_testnet_executor if self.config.trading_mode == TradingMode.BINANCE_TESTNET else self._binance_live_executor
                    result = await executor.execute(request)
                    self._live_executions += 1
            else:
                result.success = False
                result.status = "ERROR"
                result.error_message = f"Unknown trading mode: {self.config.trading_mode}"
            
            # 3. Update daily stats
            if result.success:
                self._daily_trades += 1
                # Track daily loss in USDT using result.pnl_usdt if present (Binance path)
                if getattr(result, "pnl_usdt", None) is not None and result.pnl_usdt < 0:
                    self._daily_loss_usdt += abs(result.pnl_usdt)
                elif getattr(result, "pnl_eur", None) is not None and result.pnl_eur < 0:
                    self._daily_loss_eur += abs(result.pnl_eur)
            
            # 4. Store execution result
            await self._store_result(request, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Execution error: {e}")
            result.success = False
            result.status = "ERROR"
            result.error_message = str(e)
            await self._store_result(request, result)
            return result
    
    async def _pre_flight_checks(self, request: TradeRequest) -> Optional[str]:
        """Run pre-flight safety checks. Returns block reason if blocked."""
        # Kill switch check
        if self.config.kill_switch_active:
            return f"Kill switch active: {self.config.kill_switch_reason}"
        
        # Daily trade limit (legacy)
        if self._daily_trades >= self.config.max_daily_trades:
            return f"Daily trade limit reached: {self._daily_trades}/{self.config.max_daily_trades}"

        # Daily loss limit (USDT)
        if abs(self._daily_loss_usdt) >= self.config.daily_loss_limit_usdt:
            self.config.activate_kill_switch("Daily loss limit reached")
            return f"Daily loss limit reached: ${abs(self._daily_loss_usdt):.2f}/${self.config.daily_loss_limit_usdt:.2f}"

        # Allowed symbols whitelist (normalize BTC/USDT, BTC-USDT -> BTCUSDT)
        if self.config.allowed_symbols:
            req_sym = request.symbol.upper().replace("/", "").replace("-", "")
            allowed = {s.upper().replace("/", "").replace("-", "") for s in self.config.allowed_symbols}
            if req_sym not in allowed:
                return "Symbol not allowed"

        # Order cap (USDT) - interpret request.amount as USDT for BUY
        if request.side.upper() == "BUY" and request.amount > self.config.max_order_notional_usdt:
            return f"Order notional exceeds cap: ${request.amount:.2f}/${self.config.max_order_notional_usdt:.2f}"

        return None
        
        return None
    
    async def _live_pre_flight_checks(self, request: TradeRequest) -> Optional[str]:
        """Additional checks for BINANCE_* execution."""
        if not self.config.live_cex_enabled:
            return "BLOCKED_LIVE_DISABLED"

        # BINANCE_LIVE is locked until readiness passes (kept simple for now)
        if self.config.trading_mode == TradingMode.BINANCE_LIVE:
            if not self.go_live_gate:
                return "BLOCKED_LIVE_NOT_READY"
            gate_status = await self.go_live_gate.get_current_status()
            if gate_status.get("decision") != "GO":
                return "BLOCKED_LIVE_NOT_READY"

        return None
    
    async def _execute_paper(self, request: TradeRequest) -> TradeResult:
        """Execute trade in paper mode."""
        if not self._paper_executor:
            from services.execution.paper_executor import PaperTradeExecutor
            self._paper_executor = PaperTradeExecutor(self.db)
            await self._paper_executor.initialize()
        
        return await self._paper_executor.execute(request)
    
    async def _execute_live(self, request: TradeRequest) -> TradeResult:
        """Execute trade in live mode."""
        if not self._live_executor:
            from services.execution.live_executor import LiveTradeExecutor
            self._live_executor = LiveTradeExecutor(self.db, self.go_live_gate)
        
        return await self._live_executor.execute(request)
    
    async def _store_result(self, request: TradeRequest, result: TradeResult):
        """Store execution result in database."""
        try:
            doc = {
                "request": request.model_dump(),
                "result": result.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            # Convert datetime objects
            doc["request"]["created_at"] = doc["request"]["created_at"].isoformat()
            doc["result"]["executed_at"] = doc["result"]["executed_at"].isoformat()
            
            await self.db.execution_history.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to store execution result: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get router status."""
        return {
            "trading_mode": self.config.trading_mode.value,
            "config": self.config.get_status(),
            "stats": {
                "total_requests": self._total_requests,
                "paper_executions": self._paper_executions,
                "live_executions": self._live_executions,
                "blocked_executions": self._blocked_executions,
            },
            "daily": {
                "trades": self._daily_trades,
                "loss_eur": self._daily_loss_eur,
                "loss_usdt": self._daily_loss_usdt,
                "date": self._last_reset_date,
            },
        }
    
    def update_daily_loss(self, pnl_eur: float):
        """Update daily loss tracking."""
        self._check_daily_reset()
        if pnl_eur < 0:
            self._daily_loss_eur += abs(pnl_eur)


# Global singleton
_execution_router: Optional[ExecutionRouter] = None


def get_execution_router() -> Optional[ExecutionRouter]:
    """Get global execution router instance."""
    return _execution_router


def set_execution_router(router: ExecutionRouter):
    """Set global execution router instance."""
    global _execution_router
    _execution_router = router
