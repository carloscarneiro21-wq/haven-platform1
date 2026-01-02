"""Trades Service - Real-time trade monitoring and management.

Provides:
- Trade storage and retrieval
- Summary statistics (PnL, win rate, etc.)
- Real-time trade events for WebSocket broadcasting
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStrategy(str, Enum):
    MM = "MM"
    MOM = "MOM"
    SNIPER = "SNIPER"
    DEX = "DEX"
    DCA = "DCA"
    GRID = "GRID"
    TREND = "TREND"
    BREAKOUT = "BREAKOUT"


class AgentTrade(BaseModel):
    """Agent trade record."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str
    agent_name: str
    strategy: str
    mode: str = "paper"  # paper | binance_testnet | binance_live
    venue: str = "PAPER"  # PAPER | BINANCE_TESTNET | BINANCE_LIVE
    order_id: Optional[str] = None
    executed_qty: Optional[float] = None
    cumulative_quote_qty: Optional[float] = None
    avg_fill_price: Optional[float] = None
    symbol: str
    side: str  # BUY | SELL
    qty: float
    entry_price: float
    exit_price: Optional[float] = None
    status: str = "OPEN"  # OPEN, FILLED, PARTIAL, REJECTED, CLOSED
    fees: float = 0.0
    slippage: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class TradesService:
    """Service for managing and querying agent trades."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._event_callbacks: List[Callable] = []
        self._initialized = False
    
    async def initialize(self):
        """Initialize service and create indexes."""
        if self._initialized:
            return
        
        # Create indexes for agent_trades collection
        try:
            # ts desc for recent trades
            await self.db.agent_trades.create_index([("ts", -1)])
            # agent_id + ts for agent-specific queries
            await self.db.agent_trades.create_index([("agent_id", 1), ("ts", -1)])
            # symbol + ts for symbol-specific queries
            await self.db.agent_trades.create_index([("symbol", 1), ("ts", -1)])
            # mode index for paper/live filtering
            await self.db.agent_trades.create_index([("mode", 1)])
            # status index
            await self.db.agent_trades.create_index([("status", 1)])
            
            self._initialized = True
            logger.info("TradesService initialized with indexes")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
    
    def register_event_callback(self, callback: Callable):
        """Register callback for trade events (for WebSocket broadcasting)."""
        self._event_callbacks.append(callback)
    
    async def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Emit event to all registered callbacks."""
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, payload)
                else:
                    callback(event_type, payload)
            except Exception as e:
                logger.error(f"Event callback error: {e}")
    
    async def create_trade(self, trade: AgentTrade) -> AgentTrade:
        """Create a new trade record."""
        doc = trade.model_dump()
        doc["ts"] = doc["ts"].isoformat() if isinstance(doc["ts"], datetime) else doc["ts"]
        
        await self.db.agent_trades.insert_one(doc)
        
        # Emit event (ensure no Mongo _id leaks into websocket payload)
        safe_doc = {**doc}
        safe_doc.pop("_id", None)
        await self._emit_event("trade.created", safe_doc)
        
        logger.info(f"Trade created: {trade.id} - {trade.symbol} {trade.side}")
        return trade
    
    async def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing trade."""
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        result = await self.db.agent_trades.find_one_and_update(
            {"id": trade_id},
            {"$set": updates},
            return_document=True
        )
        
        if result:
            result.pop("_id", None)
            await self._emit_event("trade.updated", {"id": trade_id, **updates})
        
        return result
    
    async def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        fees: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """Close a trade with exit price and calculate PnL."""
        trade = await self.db.agent_trades.find_one({"id": trade_id}, {"_id": 0})
        if not trade:
            return None
        
        # Calculate PnL
        entry = trade.get("entry_price", 0)
        qty = trade.get("qty", 0)
        side = trade.get("side", "BUY")
        
        if side == "BUY":
            pnl = (exit_price - entry) * qty - fees - trade.get("fees", 0)
        else:
            pnl = (entry - exit_price) * qty - fees - trade.get("fees", 0)
        
        pnl_pct = (pnl / (entry * qty)) * 100 if entry * qty > 0 else 0
        
        updates = {
            "exit_price": exit_price,
            "status": "CLOSED",
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "fees": trade.get("fees", 0) + fees,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        return await self.update_trade(trade_id, updates)
    
    async def get_trades(
        self,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        status: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get trades with filters."""
        query = {}
        
        if from_ts:
            query["ts"] = {"$gte": from_ts.isoformat()}
        if to_ts:
            if "ts" in query:
                query["ts"]["$lte"] = to_ts.isoformat()
            else:
                query["ts"] = {"$lte": to_ts.isoformat()}
        
        if agent_id:
            query["agent_id"] = agent_id
        if symbol:
            query["symbol"] = {"$regex": symbol, "$options": "i"}
        if strategy:
            query["strategy"] = strategy
        if status:
            query["status"] = status
        if mode:
            query["mode"] = mode
        
        cursor = self.db.agent_trades.find(query, {"_id": 0})
        cursor = cursor.sort("ts", -1).skip(offset).limit(limit)
        
        trades = await cursor.to_list(length=limit)
        return trades
    
    async def get_summary(
        self,
        window: str = "24h",
        group_by: str = "agent",
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get trade summary statistics."""
        # Calculate time window
        now = datetime.now(timezone.utc)
        if window == "1h":
            from_ts = now - timedelta(hours=1)
        elif window == "24h":
            from_ts = now - timedelta(hours=24)
        elif window == "7d":
            from_ts = now - timedelta(days=7)
        else:
            from_ts = now - timedelta(hours=24)
        
        # Build query
        match_query = {"ts": {"$gte": from_ts.isoformat()}}
        if mode:
            match_query["mode"] = mode
        
        # Aggregation pipeline
        pipeline = [
            {"$match": match_query},
            {
                "$group": {
                    "_id": f"${group_by}_id" if group_by == "agent" else f"${group_by}",
                    "name": {"$first": f"${group_by}_name" if group_by == "agent" else f"${group_by}"},
                    "total_trades": {"$sum": 1},
                    "total_pnl": {"$sum": "$pnl"},
                    "total_fees": {"$sum": "$fees"},
                    "wins": {
                        "$sum": {
                            "$cond": [{"$gt": ["$pnl", 0]}, 1, 0]
                        }
                    },
                    "losses": {
                        "$sum": {
                            "$cond": [{"$lt": ["$pnl", 0]}, 1, 0]
                        }
                    },
                    "total_volume": {
                        "$sum": {"$multiply": ["$qty", "$entry_price"]}
                    },
                    "avg_pnl": {"$avg": "$pnl"},
                    "max_pnl": {"$max": "$pnl"},
                    "min_pnl": {"$min": "$pnl"},
                }
            },
            {"$sort": {"total_pnl": -1}}
        ]
        
        results = await self.db.agent_trades.aggregate(pipeline).to_list(100)
        
        # Calculate overall stats
        total_pnl = sum(r.get("total_pnl", 0) for r in results)
        total_trades = sum(r.get("total_trades", 0) for r in results)
        total_wins = sum(r.get("wins", 0) for r in results)
        total_losses = sum(r.get("losses", 0) for r in results)
        
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        avg_trade = total_pnl / total_trades if total_trades > 0 else 0
        
        # Exposure by symbol
        exposure_pipeline = [
            {"$match": {**match_query, "status": "OPEN"}},
            {
                "$group": {
                    "_id": "$symbol",
                    "exposure": {
                        "$sum": {"$multiply": ["$qty", "$entry_price"]}
                    },
                    "count": {"$sum": 1}
                }
            }
        ]
        exposure_results = await self.db.agent_trades.aggregate(exposure_pipeline).to_list(50)
        
        return {
            "window": window,
            "from_ts": from_ts.isoformat(),
            "to_ts": now.isoformat(),
            "overall": {
                "cumulative_pnl": total_pnl,
                "total_trades": total_trades,
                "wins": total_wins,
                "losses": total_losses,
                "win_rate": win_rate,
                "avg_trade": avg_trade,
            },
            f"by_{group_by}": [
                {
                    "id": r.get("_id"),
                    "name": r.get("name") or r.get("_id"),
                    "total_trades": r.get("total_trades", 0),
                    "total_pnl": r.get("total_pnl", 0),
                    "wins": r.get("wins", 0),
                    "losses": r.get("losses", 0),
                    "win_rate": (r.get("wins", 0) / r.get("total_trades", 1)) * 100,
                    "avg_pnl": r.get("avg_pnl", 0),
                }
                for r in results
            ],
            "exposure": [
                {
                    "symbol": e.get("_id"),
                    "exposure": e.get("exposure", 0),
                    "positions": e.get("count", 0),
                }
                for e in exposure_results
            ],
        }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics for WebSocket broadcasting."""
        # Get recent summary
        summary = await self.get_summary(window="24h", group_by="agent")
        
        # Get real-time metrics
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        
        recent_trades = await self.db.agent_trades.count_documents(
            {"ts": {"$gte": one_hour_ago.isoformat()}}
        )
        
        return {
            "ts": now.isoformat(),
            "cumulative_pnl": summary["overall"]["cumulative_pnl"],
            "pnl_by_agent": summary.get("by_agent", []),
            "exposure_by_symbol": summary.get("exposure", []),
            "trade_counts": {
                "total_24h": summary["overall"]["total_trades"],
                "last_hour": recent_trades,
                "win_rate": summary["overall"]["win_rate"],
            },
        }


# Global instance
_trades_service: Optional[TradesService] = None


def get_trades_service() -> Optional[TradesService]:
    return _trades_service


def set_trades_service(service: TradesService):
    global _trades_service
    _trades_service = service
