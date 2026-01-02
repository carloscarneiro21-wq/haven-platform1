"""Enhanced Trading Runtime with state recovery, safe mode, and heartbeat."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    MarketFeatures, OrderPlan, Order, Trade, Position,
    PortfolioSummary, SystemLog, AgentType
)
from services.data_feed import DataFeed
from services.risk_manager import RiskManager
from services.executor import PaperExecutor
from services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class TradingRuntime:
    """
    Enhanced Trading Runtime with 24/7 capabilities.
    
    Features:
    - State recovery on restart
    - Safe mode (exits only when data stale)
    - Heartbeat monitoring
    - Idempotent order processing
    - Auto-recovery from errors
    - Event logging
    """
    
    DEFAULT_INTERVAL = 60  # seconds
    SYMBOLS = ["BTC/USDT", "ETH/USDT"]
    MAX_RECOVERY_ATTEMPTS = 3
    HEARTBEAT_INTERVAL = 30  # seconds
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.data_feed: Optional[DataFeed] = None
        self.risk_manager: Optional[RiskManager] = None
        self.executor: Optional[PaperExecutor] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.notifications = None  # Will be set externally
        self.event_logger = None   # Will be set externally
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._interval = self.DEFAULT_INTERVAL
        self._last_cycle: Optional[datetime] = None
        self._last_heartbeat: Optional[datetime] = None
        self._cycle_count = 0
        self._error_count = 0
        self._recovery_attempts = 0
        
        # Safe mode
        self._safe_mode = False
        self._safe_mode_reason = ""
        
        # State tracking
        self._pending_orders: Dict[str, Order] = {}
        self._processed_order_ids: set = set()  # For idempotency
        
    async def initialize(self):
        """Initialize all components with state recovery."""
        logger.info("Initializing Trading Runtime...")
        
        # Initialize data feed with DB for persistence
        self.data_feed = DataFeed(self.db)
        await self.data_feed.initialize()
        
        # Initialize risk manager
        self.risk_manager = RiskManager(self.db)
        await self.risk_manager.initialize()
        
        # Initialize executor
        self.executor = PaperExecutor(self.db, self.data_feed)
        
        # Initialize orchestrator
        self.orchestrator = Orchestrator(self.db, self.risk_manager)
        await self.orchestrator.initialize()
        
        # Recover state from previous session
        await self._recover_state()
        
        # Record startup
        await self._log_event("info", "runtime", "Trading runtime initialized", {
            "recovered_positions": await self.db.positions.count_documents({"is_open": True}),
            "recovered_orders": await self.db.orders.count_documents({"status": {"$in": ["pending", "open"]}}),
        })
        
        logger.info("Trading Runtime initialized with state recovery")
        
    async def _recover_state(self):
        """Recover state from database after restart."""
        logger.info("Recovering state from previous session...")
        
        try:
            # Load processed order IDs to prevent duplicates
            recent_orders = await self.db.orders.find(
                {"created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}},
                {"_id": 0, "id": 1}
            ).to_list(10000)
            self._processed_order_ids = {o["id"] for o in recent_orders}
            
            # Verify open positions are consistent
            open_positions = await self.executor.get_positions(open_only=True)
            for position in open_positions:
                # Update current prices
                ticker = await self.data_feed.fetch_ticker(position.symbol)
                if ticker:
                    position.current_price = ticker.get('last', position.current_price)
                    logger.info(f"Recovered position: {position.symbol} @ {position.entry_price}")
            
            # Check for orphaned pending orders
            pending_orders = await self.executor.get_open_orders()
            for order in pending_orders:
                if order.id not in self._processed_order_ids:
                    self._pending_orders[order.id] = order
                    logger.warning(f"Found orphaned order: {order.id}")
            
            # Reconcile last candle timestamp
            for symbol in self.SYMBOLS:
                candles = await self.data_feed.fetch_candles(symbol, '1h', 1)
                if candles:
                    last_ts = datetime.fromtimestamp(candles[-1].timestamp / 1000, tz=timezone.utc)
                    logger.info(f"Last candle for {symbol}: {last_ts.isoformat()}")
            
            logger.info(f"State recovery complete: {len(open_positions)} positions, {len(self._pending_orders)} pending orders")
            
        except Exception as e:
            logger.error(f"State recovery error: {e}")
            await self._log_event("error", "runtime", f"State recovery failed: {e}")
    
    async def cleanup(self):
        """Cleanup resources."""
        if self._running:
            await self.stop()
        
        if self.data_feed:
            await self.data_feed.cleanup()
        
        logger.info("Trading Runtime cleaned up")
    
    async def start(self, interval: int = None):
        """Start the runtime loop."""
        if self._running:
            logger.warning("Runtime already running")
            return
        
        if interval:
            self._interval = interval
        
        self._running = True
        self._error_count = 0
        self._recovery_attempts = 0
        
        # Start main loop
        self._task = asyncio.create_task(self._run_loop())
        
        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        await self._log_event("info", "runtime", "Trading runtime started", {
            "interval": self._interval,
            "symbols": self.SYMBOLS,
        })
        
        # Emit event
        if self.event_logger:
            from services.event_logger import EventSeverity, EventCategory, EventType
            await self.event_logger.emit(
                severity=EventSeverity.INFO,
                category=EventCategory.ENGINE,
                type=EventType.ENGINE_STARTED,
                message=f"Trading engine started with {self._interval}s interval",
                context={"interval": self._interval, "symbols": self.SYMBOLS}
            )
        
        logger.info(f"Trading Runtime started with {self._interval}s interval")
    
    async def stop(self):
        """Stop the runtime loop gracefully."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        # Save final state
        await self._save_runtime_state()
        
        await self._log_event("info", "runtime", "Trading runtime stopped", {
            "total_cycles": self._cycle_count,
            "error_count": self._error_count,
        })
        
        # Emit event
        if self.event_logger:
            from services.event_logger import EventSeverity, EventCategory, EventType
            await self.event_logger.emit(
                severity=EventSeverity.INFO,
                category=EventCategory.ENGINE,
                type=EventType.ENGINE_STOPPED,
                message=f"Trading engine stopped after {self._cycle_count} cycles",
                context={"total_cycles": self._cycle_count, "error_count": self._error_count}
            )
        
        logger.info("Trading Runtime stopped")
    
    async def _run_loop(self):
        """Main execution loop with error recovery."""
        while self._running:
            try:
                await self._run_cycle()
                self._error_count = 0  # Reset on successful cycle
                self._recovery_attempts = 0
                await asyncio.sleep(self._interval)
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"Runtime cycle error ({self._error_count}): {e}")
                await self._log_event("error", "runtime", f"Cycle error: {str(e)}")
                
                # Attempt recovery
                if self._error_count >= 3:
                    self._recovery_attempts += 1
                    if self._recovery_attempts >= self.MAX_RECOVERY_ATTEMPTS:
                        logger.critical("Max recovery attempts reached, entering safe mode")
                        self._safe_mode = True
                        self._safe_mode_reason = "Too many consecutive errors"
                        
                        # Notify
                        if self.notifications:
                            await self.notifications.notify_safe_mode_entered(self._safe_mode_reason)
                    else:
                        logger.warning(f"Attempting recovery ({self._recovery_attempts}/{self.MAX_RECOVERY_ATTEMPTS})")
                        await self._attempt_recovery()
                
                await asyncio.sleep(5)  # Brief pause before retry
    
    async def _heartbeat_loop(self):
        """Heartbeat monitoring loop."""
        while self._running:
            try:
                self._last_heartbeat = datetime.now(timezone.utc)
                
                # Save heartbeat to DB for external monitoring
                await self.db.runtime_heartbeat.update_one(
                    {},
                    {"$set": {
                        "timestamp": self._last_heartbeat.isoformat(),
                        "running": self._running,
                        "cycle_count": self._cycle_count,
                        "safe_mode": self._safe_mode,
                        "error_count": self._error_count,
                    }},
                    upsert=True
                )
                
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
    
    async def _attempt_recovery(self):
        """Attempt to recover from errors."""
        logger.info("Attempting runtime recovery...")
        
        try:
            # Reinitialize data feed
            if self.data_feed:
                await self.data_feed.cleanup()
            self.data_feed = DataFeed()
            await self.data_feed.initialize()
            
            # Reinitialize executor with new data feed
            self.executor = PaperExecutor(self.db, self.data_feed)
            
            # Recover state
            await self._recover_state()
            
            self._error_count = 0
            logger.info("Recovery successful")
            
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
    
    async def _run_cycle(self):
        """Execute one trading cycle with safe mode awareness."""
        cycle_start = datetime.now(timezone.utc)
        self._cycle_count += 1
        
        try:
            # Step 1: Fetch market data and calculate features
            features = await self._fetch_all_features()
            
            if not features:
                logger.warning("No market features available")
                return
            
            # Step 2: Check data feed health and safe mode
            self._check_safe_mode()
            
            # Step 2b: Emit any pending anti-flapping events
            if self.data_feed and self.data_feed.health:
                await self.data_feed.health.emit_pending_events()
            
            # Step 3: Update position prices
            await self.executor.update_position_prices()
            
            # Step 4: Update portfolio and risk metrics
            await self._update_portfolio_metrics()
            
            # Step 5: Run orchestrator (respecting safe mode)
            if self._safe_mode:
                # In safe mode: only process exits, no new entries
                order_plans = await self._get_exit_only_plans(features)
            else:
                order_plans = await self.orchestrator.run_cycle(features)
            
            # Step 6: Execute order plans with idempotency
            for plan in order_plans:
                await self._execute_order_plan_safe(plan, features)
            
            # Step 7: Log cycle completion
            self._last_cycle = cycle_start
            
            if self._cycle_count % 10 == 0:
                logger.info(f"Completed cycle {self._cycle_count} (safe_mode={self._safe_mode})")
                
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            raise
    
    def _check_safe_mode(self):
        """Check and update safe mode status."""
        if self.data_feed and self.data_feed.safe_mode:
            if not self._safe_mode:
                self._safe_mode = True
                self._safe_mode_reason = self.data_feed.safe_mode_reason
                logger.warning(f"Entering safe mode: {self._safe_mode_reason}")
        elif self._safe_mode and self._recovery_attempts == 0:
            # Exit safe mode if data is healthy and no recovery in progress
            self._safe_mode = False
            self._safe_mode_reason = ""
            logger.info("Exiting safe mode - data feed healthy")
    
    async def _get_exit_only_plans(self, features: Dict[str, MarketFeatures]) -> List[OrderPlan]:
        """In safe mode, only get exit signals (close positions)."""
        exit_plans = []
        
        # Check each open position for exit conditions
        positions = await self.executor.get_positions(open_only=True)
        
        for position in positions:
            symbol_features = features.get(position.symbol)
            if not symbol_features:
                continue
            
            # Get the agent for this position
            agent = await self.orchestrator.get_agent_by_type(AgentType(position.agent_type))
            if not agent:
                continue
            
            # Run agent cycle but filter to only exit signals
            plan = await agent.run_cycle(symbol_features)
            if plan and plan.orders:
                # Filter to only closing orders
                exit_orders = [o for o in plan.orders if o.reason and ('close' in o.reason.lower() or 'stop' in o.reason.lower() or 'profit' in o.reason.lower())]
                if exit_orders:
                    plan.orders = exit_orders
                    exit_plans.append(plan)
        
        return exit_plans
    
    async def _execute_order_plan_safe(self, plan: OrderPlan, features: Dict[str, MarketFeatures]):
        """Execute order plan with idempotency checks."""
        for order in plan.orders:
            # Idempotency check - skip if already processed
            if order.id in self._processed_order_ids:
                logger.warning(f"Skipping duplicate order: {order.id}")
                continue
            
            # Get current exposure
            positions = await self.executor.get_positions()
            current_exposure = sum(p.amount * p.current_price for p in positions)
            
            # Pre-trade risk check
            risk_result = await self.risk_manager.pre_trade_check(order, current_exposure)
            
            if not risk_result.allowed:
                logger.warning(f"Order rejected by risk manager: {risk_result.reason}")
                await self._log_event("warning", "risk", 
                    f"Order rejected: {risk_result.reason}",
                    {"order_id": order.id, "agent_id": order.agent_id}
                )
                continue
            
            # Adjust amount if needed
            if risk_result.adjusted_amount:
                order.amount = risk_result.adjusted_amount
                order.reason += f" (adjusted: {risk_result.warnings})"
            
            # Mark as processing
            self._processed_order_ids.add(order.id)
            
            # Execute order
            executed_order = await self.executor.execute_order(order)
            
            # Post-trade risk update
            if executed_order.status.value == "filled":
                trade = Trade(
                    order_id=executed_order.id,
                    agent_id=executed_order.agent_id,
                    agent_type=executed_order.agent_type,
                    symbol=executed_order.symbol,
                    side=executed_order.side,
                    amount=executed_order.filled,
                    price=executed_order.average_price,
                    value=executed_order.filled * executed_order.average_price,
                    commission=executed_order.commission,
                    pnl=0
                )
                await self.risk_manager.post_trade_update(trade)
                
                # Notify
                if self.notifications and self.notifications.config.enabled:
                    await self.notifications.notify_trade_executed(
                        symbol=executed_order.symbol,
                        side=executed_order.side.value,
                        amount=executed_order.filled,
                        price=executed_order.average_price,
                        agent=executed_order.agent_type.value,
                    )
                
                # Notify agent of fill
                agent = await self.orchestrator.get_agent_by_type(order.agent_type)
                if agent and hasattr(agent, 'on_order_filled'):
                    await agent.on_order_filled(executed_order, trade.value)
    
    async def _fetch_all_features(self) -> Dict[str, MarketFeatures]:
        """Fetch features for all monitored symbols."""
        features = {}
        
        for symbol in self.SYMBOLS:
            try:
                feature = await self.data_feed.calculate_features(symbol)
                features[symbol] = feature
            except Exception as e:
                logger.warning(f"Failed to fetch features for {symbol}: {e}")
        
        return features
    
    async def _update_portfolio_metrics(self):
        """Update portfolio summary and risk metrics."""
        positions = await self.executor.get_positions(open_only=True)
        
        total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        total_exposure = sum(p.amount * p.current_price for p in positions)
        
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_trades = await self.db.trades.find({
            "executed_at": {"$gte": today_start.isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        daily_pnl = sum(t.get('pnl', 0) for t in today_trades)
        
        total_equity = self.orchestrator.total_capital + total_unrealized_pnl
        await self.risk_manager.update_equity(total_equity, total_unrealized_pnl)
        
        all_trades = await self.db.trades.find({}, {"_id": 0}).to_list(10000)
        winning_trades = len([t for t in all_trades if t.get('pnl', 0) > 0])
        win_rate = (winning_trades / len(all_trades) * 100) if all_trades else 0
        
        summary = PortfolioSummary(
            total_equity=total_equity,
            available_balance=self.orchestrator.total_capital - total_exposure,
            used_margin=total_exposure,
            total_pnl=total_unrealized_pnl + sum(t.get('pnl', 0) for t in all_trades),
            daily_pnl=daily_pnl,
            open_positions=len(positions),
            pending_orders=len(await self.executor.get_open_orders()),
            win_rate=win_rate,
        )
        
        await self.db.portfolio_summary.replace_one(
            {},
            summary.model_dump(),
            upsert=True
        )
    
    async def _save_runtime_state(self):
        """Save runtime state for recovery."""
        state = {
            "last_cycle": self._last_cycle.isoformat() if self._last_cycle else None,
            "cycle_count": self._cycle_count,
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "interval": self._interval,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.runtime_state.replace_one({}, state, upsert=True)
    
    async def _log_event(self, level: str, component: str, message: str, details: Dict = None):
        """Log system event."""
        log = SystemLog(
            level=level,
            component=component,
            message=message,
            details=details or {}
        )
        
        doc = log.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        
        await self.db.system_logs.insert_one(doc)
    
    async def run_single_cycle(self):
        """Run a single cycle manually (for testing)."""
        await self._run_cycle()
    
    def get_status(self) -> Dict[str, Any]:
        """Get runtime status with health metrics."""
        data_feed_status = self.data_feed.get_status() if self.data_feed else {}
        
        # Calculate data freshness
        data_freshness_seconds = None
        if self._last_cycle:
            data_freshness_seconds = (datetime.now(timezone.utc) - self._last_cycle).total_seconds()
        
        return {
            "running": self._running,
            "interval": self._interval,
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle.isoformat() if self._last_cycle else None,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "symbols": self.SYMBOLS,
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "error_count": self._error_count,
            "recovery_attempts": self._recovery_attempts,
            "data_freshness_seconds": data_freshness_seconds,
            "data_feed": data_feed_status,
        }
    
    async def get_heartbeat(self) -> Dict[str, Any]:
        """Get heartbeat status for external monitoring."""
        return {
            "status": "healthy" if self._running and not self._safe_mode else "degraded" if self._safe_mode else "stopped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_cycle": self._last_cycle.isoformat() if self._last_cycle else None,
            "cycle_count": self._cycle_count,
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "data_feed_health": self.data_feed.health.get_status() if self.data_feed else None,
            "risk_status": await self.risk_manager.get_status() if self.risk_manager else None,
        }
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get all data needed for dashboard."""
        portfolio_doc = await self.db.portfolio_summary.find_one({}, {"_id": 0})
        portfolio = PortfolioSummary(**portfolio_doc) if portfolio_doc else PortfolioSummary()
        
        agent_statuses = self.orchestrator.get_all_agent_statuses() if self.orchestrator else []
        risk_status = await self.risk_manager.get_status() if self.risk_manager else {}
        positions = await self.executor.get_positions(open_only=True) if self.executor else []
        
        recent_trades = await self.db.trades.find(
            {}, {"_id": 0}
        ).sort("executed_at", -1).limit(20).to_list(20)
        
        features = {}
        if self.data_feed:
            for symbol in self.SYMBOLS:
                try:
                    feat = await self.data_feed.calculate_features(symbol)
                    features[symbol] = feat.model_dump()
                except:
                    pass
        
        recent_logs = await self.db.trade_logs.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        return {
            "runtime": self.get_status(),
            "portfolio": portfolio.model_dump(),
            "agents": agent_statuses,
            "risk": risk_status,
            "positions": [p.model_dump() for p in positions],
            "recent_trades": recent_trades,
            "market_features": features,
            "trade_logs": recent_logs,
        }


# Global runtime instance
runtime: Optional[TradingRuntime] = None


async def get_runtime() -> TradingRuntime:
    """Get or create runtime instance."""
    global runtime
    return runtime


async def init_runtime(db: AsyncIOMotorDatabase) -> TradingRuntime:
    """Initialize the runtime."""
    global runtime
    runtime = TradingRuntime(db)
    await runtime.initialize()
    return runtime
