"""Paper trading executor with realistic simulation."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
import numpy as np
import logging

from models.trading import (
    Order, OrderStatus, OrderSide, OrderType,
    Position, Trade, TradeLog, AgentType
)
from services.data_feed import DataFeed

logger = logging.getLogger(__name__)


class PaperExecutor:
    """Paper trading executor simulating real execution with idempotency."""
    
    # Fee structure (simulating Binance)
    MAKER_FEE = 0.001  # 0.1%
    TAKER_FEE = 0.001  # 0.1%
    
    # Slippage model
    BASE_SLIPPAGE = 0.0001  # 0.01%
    VOLATILITY_SLIPPAGE_FACTOR = 0.5
    
    # Latency simulation (ms)
    MIN_LATENCY = 50
    MAX_LATENCY = 200
    
    def __init__(self, db: AsyncIOMotorDatabase, data_feed: DataFeed):
        self.db = db
        self.data_feed = data_feed
        self._lock = asyncio.Lock()
        self._processed_idempotency_keys: set = set()  # Track processed keys
        self.event_logger = None  # Will be set externally
        
    async def initialize(self):
        """Initialize executor and load processed idempotency keys."""
        # Load recently processed idempotency keys (last 24h)
        recent_orders = await self.db.orders.find(
            {"created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}},
            {"_id": 0, "idempotency_key": 1}
        ).to_list(10000)
        self._processed_idempotency_keys = {o.get("idempotency_key") for o in recent_orders if o.get("idempotency_key")}
        logger.info(f"Loaded {len(self._processed_idempotency_keys)} idempotency keys")
        
    async def execute_order(self, order: Order) -> Order:
        """Execute an order with realistic simulation and idempotency check."""
        async with self._lock:
            # IDEMPOTENCY CHECK - Critical for preventing duplicates
            if order.idempotency_key in self._processed_idempotency_keys:
                # Check if order exists in DB
                existing = await self.db.orders.find_one(
                    {"idempotency_key": order.idempotency_key},
                    {"_id": 0}
                )
                if existing:
                    logger.warning(f"Duplicate order rejected (idempotency_key: {order.idempotency_key})")
                    
                    # Emit IDEMPOTENCY_DUPLICATE_BLOCKED event
                    if self.event_logger:
                        from services.event_logger import EventSeverity, EventCategory, EventType
                        await self.event_logger.emit(
                            severity=EventSeverity.WARNING,
                            category=EventCategory.ORDER,
                            type=EventType.IDEMPOTENCY_DUPLICATE_BLOCKED,
                            message=f"Duplicate order blocked for {order.symbol}",
                            context={
                                "idempotency_key": order.idempotency_key,
                                "order_id": order.id,
                                "symbol": order.symbol,
                                "side": order.side.value,
                                "amount": order.amount,
                            },
                            symbol=order.symbol,
                            agent_id=order.agent_id,
                            tags=["idempotency", "duplicate", "blocked"]
                        )
                    
                    return Order(**existing)
            
            # Mark as processing
            self._processed_idempotency_keys.add(order.idempotency_key)
            
            # Simulate network latency
            latency = np.random.uniform(self.MIN_LATENCY, self.MAX_LATENCY)
            await asyncio.sleep(latency / 1000)
            
            # Get current market data
            ticker = await self.data_feed.fetch_ticker(order.symbol)
            orderbook = await self.data_feed.get_orderbook(order.symbol, 10)
            
            if not ticker:
                order.status = OrderStatus.REJECTED
                order.reason = f"{order.reason} | Execution failed: No market data"
                await self._save_order(order)
                
                # Emit ORDER_REJECTED event
                if self.event_logger:
                    from services.event_logger import EventSeverity, EventCategory, EventType
                    await self.event_logger.emit(
                        severity=EventSeverity.ERROR,
                        category=EventCategory.ORDER,
                        type=EventType.ORDER_REJECTED,
                        message=f"Order rejected for {order.symbol}: No market data",
                        context={
                            "order_id": order.id,
                            "reason": "No market data",
                            "symbol": order.symbol,
                            "side": order.side.value,
                            "amount": order.amount,
                        },
                        symbol=order.symbol,
                        agent_id=order.agent_id,
                        tags=["rejected", "no_data"]
                    )
                
                return order
            
            current_price = ticker.get('last', 0)
            
            # Execute based on order type
            if order.order_type == OrderType.MARKET:
                order = await self._execute_market_order(order, orderbook, current_price)
            elif order.order_type == OrderType.LIMIT:
                order = await self._execute_limit_order(order, orderbook, current_price)
            elif order.order_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
                order = await self._check_conditional_order(order, current_price)
            
            # Save order state
            await self._save_order(order)
            
            # Create trade record if filled
            if order.status == OrderStatus.FILLED:
                await self._create_trade(order)
                await self._update_position(order)
            
            return order
    
    async def _execute_market_order(self, order: Order, orderbook: Dict, current_price: float) -> Order:
        """Execute market order against orderbook."""
        order.status = OrderStatus.OPEN
        
        # Determine execution side of orderbook
        if order.side == OrderSide.BUY:
            levels = orderbook.get('asks', [])
        else:
            levels = orderbook.get('bids', [])
        
        if not levels:
            # Use current price with slippage
            slippage = self._calculate_slippage(current_price, order.amount)
            if order.side == OrderSide.BUY:
                execution_price = current_price * (1 + slippage)
            else:
                execution_price = current_price * (1 - slippage)
            
            order.filled = order.amount
            order.remaining = 0
            order.average_price = execution_price
        else:
            # Walk through orderbook levels
            remaining = order.amount
            total_cost = 0
            filled_amount = 0
            
            for price, volume in levels:
                if remaining <= 0:
                    break
                
                fill_qty = min(remaining, volume)
                slippage = self._calculate_slippage(price, fill_qty)
                
                if order.side == OrderSide.BUY:
                    adjusted_price = price * (1 + slippage)
                else:
                    adjusted_price = price * (1 - slippage)
                
                total_cost += fill_qty * adjusted_price
                filled_amount += fill_qty
                remaining -= fill_qty
            
            order.filled = filled_amount
            order.remaining = order.amount - filled_amount
            order.average_price = total_cost / filled_amount if filled_amount > 0 else current_price
        
        # Calculate commission
        order.commission = order.filled * order.average_price * self.TAKER_FEE
        
        # Update status
        if order.remaining == 0:
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(timezone.utc)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        
        order.updated_at = datetime.now(timezone.utc)
        
        logger.info(f"Market order executed: {order.side.value} {order.filled} {order.symbol} @ {order.average_price:.2f}")
        
        return order
    
    async def _execute_limit_order(self, order: Order, orderbook: Dict, current_price: float) -> Order:
        """Execute limit order if price is favorable."""
        order.status = OrderStatus.OPEN
        
        can_execute = False
        if order.side == OrderSide.BUY:
            # Buy limit: execute if ask <= limit price
            if current_price <= order.price:
                can_execute = True
        else:
            # Sell limit: execute if bid >= limit price
            if current_price >= order.price:
                can_execute = True
        
        if can_execute:
            # Execute at limit price (better execution)
            execution_price = order.price
            slippage = self._calculate_slippage(execution_price, order.amount) * 0.5  # Less slippage for limit
            
            if order.side == OrderSide.BUY:
                execution_price = min(execution_price, current_price * (1 + slippage))
            else:
                execution_price = max(execution_price, current_price * (1 - slippage))
            
            order.filled = order.amount
            order.remaining = 0
            order.average_price = execution_price
            order.commission = order.filled * order.average_price * self.MAKER_FEE
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(timezone.utc)
            
            logger.info(f"Limit order filled: {order.side.value} {order.filled} {order.symbol} @ {order.average_price:.2f}")
        
        order.updated_at = datetime.now(timezone.utc)
        return order
    
    async def _check_conditional_order(self, order: Order, current_price: float) -> Order:
        """Check and execute conditional orders (stop-loss, take-profit)."""
        triggered = False
        
        if order.order_type == OrderType.STOP_LOSS:
            if order.side == OrderSide.SELL and current_price <= order.stop_price:
                triggered = True
            elif order.side == OrderSide.BUY and current_price >= order.stop_price:
                triggered = True
        
        elif order.order_type == OrderType.TAKE_PROFIT:
            if order.side == OrderSide.SELL and current_price >= order.stop_price:
                triggered = True
            elif order.side == OrderSide.BUY and current_price <= order.stop_price:
                triggered = True
        
        if triggered:
            # Convert to market order and execute
            order.order_type = OrderType.MARKET
            orderbook = await self.data_feed.get_orderbook(order.symbol, 10)
            order = await self._execute_market_order(order, orderbook, current_price)
            
            logger.info(f"Conditional order triggered: {order.side.value} {order.symbol} @ {current_price:.2f}")
        
        return order
    
    def _calculate_slippage(self, price: float, amount: float) -> float:
        """Calculate realistic slippage based on order size."""
        # Base slippage + size impact
        size_impact = (amount * price / 100000) * 0.0001  # Larger orders = more slippage
        volatility_impact = np.random.uniform(0, self.BASE_SLIPPAGE * self.VOLATILITY_SLIPPAGE_FACTOR)
        
        total_slippage = self.BASE_SLIPPAGE + size_impact + volatility_impact
        return min(total_slippage, 0.01)  # Cap at 1%
    
    async def _save_order(self, order: Order):
        """Save order to database."""
        doc = order.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        if doc.get('filled_at'):
            doc['filled_at'] = doc['filled_at'].isoformat()
        
        await self.db.orders.update_one(
            {"id": order.id},
            {"$set": doc},
            upsert=True
        )
    
    async def _create_trade(self, order: Order):
        """Create trade record from filled order."""
        trade = Trade(
            order_id=order.id,
            agent_id=order.agent_id,
            agent_type=order.agent_type,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            amount=order.filled,
            price=order.average_price,
            value=order.filled * order.average_price,
            commission=order.commission,
            reason=order.reason
        )
        
        doc = trade.model_dump()
        doc['executed_at'] = doc['executed_at'].isoformat()
        
        await self.db.trades.insert_one(doc)
        
        # Log the trade
        await self._log_trade(order, trade)
    
    async def _update_position(self, order: Order):
        """Update or create position based on filled order."""
        existing = await self.db.positions.find_one({
            "agent_id": order.agent_id,
            "symbol": order.symbol,
            "is_open": True
        }, {"_id": 0})
        
        if existing:
            position = Position(**existing)
            
            if order.side == position.side:
                # Adding to position
                total_cost = (position.entry_price * position.amount) + (order.average_price * order.filled)
                new_amount = position.amount + order.filled
                position.entry_price = total_cost / new_amount
                position.amount = new_amount
            else:
                # Reducing/closing position
                if order.filled >= position.amount:
                    # Close position
                    pnl = self._calculate_pnl(position, order.average_price)
                    position.realized_pnl = pnl
                    position.is_open = False
                    position.closed_at = datetime.now(timezone.utc)
                    position.amount = 0
                else:
                    # Partial close
                    close_ratio = order.filled / position.amount
                    pnl = self._calculate_pnl(position, order.average_price) * close_ratio
                    position.realized_pnl += pnl
                    position.amount -= order.filled
            
            position.current_price = order.average_price
            position.updated_at = datetime.now(timezone.utc)
            
            doc = position.model_dump()
            doc['opened_at'] = doc['opened_at'].isoformat()
            doc['updated_at'] = doc['updated_at'].isoformat()
            if doc.get('closed_at'):
                doc['closed_at'] = doc['closed_at'].isoformat()
            
            await self.db.positions.update_one(
                {"id": position.id},
                {"$set": doc}
            )
        else:
            # Create new position
            position = Position(
                agent_id=order.agent_id,
                agent_type=order.agent_type,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                entry_price=order.average_price,
                current_price=order.average_price,
                amount=order.filled,
                stop_loss=order.stop_price if order.order_type == OrderType.STOP_LOSS else None,
            )
            
            doc = position.model_dump()
            doc['opened_at'] = doc['opened_at'].isoformat()
            doc['updated_at'] = doc['updated_at'].isoformat()
            
            await self.db.positions.insert_one(doc)
    
    def _calculate_pnl(self, position: Position, exit_price: float) -> float:
        """Calculate PnL for position."""
        if position.side == OrderSide.BUY:
            return (exit_price - position.entry_price) * position.amount
        else:
            return (position.entry_price - exit_price) * position.amount
    
    async def _log_trade(self, order: Order, trade: Trade):
        """Log trade decision."""
        log = TradeLog(
            agent_id=order.agent_id,
            agent_type=order.agent_type,
            symbol=order.symbol,
            action=f"{order.side.value}_{order.order_type.value}",
            reason=order.reason,
            market_conditions={
                "price": order.average_price,
                "filled": order.filled,
                "commission": order.commission,
            },
            order_id=order.id,
            trade_id=trade.id
        )
        
        doc = log.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        
        await self.db.trade_logs.insert_one(doc)
    
    async def cancel_order(self, order_id: str) -> Optional[Order]:
        """Cancel an open order."""
        doc = await self.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not doc:
            return None
        
        order = Order(**doc)
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED]:
            return order
        
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(timezone.utc)
        
        await self._save_order(order)
        
        logger.info(f"Order canceled: {order_id}")
        
        return order
    
    async def get_open_orders(self, agent_id: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        query = {"status": {"$in": ["pending", "open", "partially_filled"]}}
        if agent_id:
            query["agent_id"] = agent_id
        
        docs = await self.db.orders.find(query, {"_id": 0}).to_list(1000)
        return [Order(**doc) for doc in docs]
    
    async def get_positions(self, agent_id: Optional[str] = None, open_only: bool = True) -> List[Position]:
        """Get positions."""
        query = {}
        if agent_id:
            query["agent_id"] = agent_id
        if open_only:
            query["is_open"] = True
        
        docs = await self.db.positions.find(query, {"_id": 0}).to_list(1000)
        return [Position(**doc) for doc in docs]
    
    async def update_position_prices(self):
        """Update current prices for all open positions."""
        positions = await self.get_positions(open_only=True)
        
        for position in positions:
            ticker = await self.data_feed.fetch_ticker(position.symbol)
            if ticker:
                current_price = ticker.get('last', position.current_price)
                position.current_price = current_price
                
                # Calculate unrealized PnL
                position.unrealized_pnl = self._calculate_pnl(position, current_price)
                if position.entry_price > 0:
                    position.unrealized_pnl_pct = (position.unrealized_pnl / (position.entry_price * position.amount)) * 100
                
                position.updated_at = datetime.now(timezone.utc)
                
                doc = position.model_dump()
                doc['opened_at'] = doc['opened_at'].isoformat()
                doc['updated_at'] = doc['updated_at'].isoformat()
                if doc.get('closed_at'):
                    doc['closed_at'] = doc['closed_at'].isoformat()
                
                await self.db.positions.update_one(
                    {"id": position.id},
                    {"$set": doc}
                )
