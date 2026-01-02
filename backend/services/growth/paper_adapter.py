"""
Paper Trading Adapter for Growth Module
========================================

Converts Intent Plans from MM/MOM agents into paper orders
and handles execution through the existing PaperExecutor.

Provides idempotency, PnL tracking, and audit logging.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from models.trading import (
    Order, OrderSide, OrderType, OrderStatus, AgentType
)

logger = logging.getLogger(__name__)


# ============ Intent Plan Contract ============

class IntentOrderSpec(BaseModel):
    """Single order specification from an intent plan."""
    client_order_id: str
    side: str  # "buy" or "sell"
    order_type: str = "limit_maker"  # "limit", "limit_maker", "market"
    price: float
    size_eur: float
    size_asset: float
    post_only: bool = True
    reduce_only: bool = False
    ttl_seconds: int = 300  # Order validity
    rationale: str = ""


class IntentPlanScope(BaseModel):
    """Capital scope for the intent plan."""
    capital_eur: float
    bucket: str = "CORE"  # CORE, EDGE, RESERVE
    max_loss_eur: float = 0.0


class IntentPlanRisk(BaseModel):
    """Risk parameters for the intent plan."""
    max_loss_eur: float = 0.0
    expected_edge_pct: float = 0.0
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


class IntentPlan(BaseModel):
    """Standardized Intent Plan contract for MM/MOM agents."""
    plan_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    venue: str  # "binance", "kraken", "auto_resolved"
    agent_type: str  # "MM" or "MOM"
    preset_id: str
    scope: IntentPlanScope
    orders: List[IntentOrderSpec] = []
    risk: IntentPlanRisk = IntentPlanRisk()
    reason_codes: List[str] = []
    
    @classmethod
    def generate_plan_id(
        cls,
        agent_type: str,
        symbol: str,
        venue: str,
        preset_id: str,
        timestamp_minute: str
    ) -> str:
        """Generate deterministic plan_id for idempotency."""
        key = f"{agent_type}_{symbol}_{venue}_{preset_id}_{timestamp_minute}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class RunResult(BaseModel):
    """Result of a paper run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    plan_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Status
    status: str = "success"  # "success", "blocked", "error", "dry_run"
    is_dry_run: bool = False
    
    # Decision snapshot
    regime: str = ""
    recommended_agent: str = ""
    confidence: str = ""
    
    # Execution results
    orders_created: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    
    # PnL
    pnl_delta_eur: float = 0.0
    fees_eur: float = 0.0
    slippage_eur: float = 0.0
    
    # Reasons
    reason_codes: List[str] = []
    block_reason: Optional[str] = None
    
    # Raw data
    decision_snapshot: Dict[str, Any] = {}
    orders: List[Dict[str, Any]] = []
    fills: List[Dict[str, Any]] = []


# ============ Paper Adapter ============

class GrowthPaperAdapter:
    """
    Adapter to convert Growth Module intent plans to paper orders.
    
    Responsibilities:
    - Convert IntentPlan -> Order objects
    - Execute through PaperExecutor
    - Track PnL and fees
    - Maintain idempotency
    - Log all runs to growth_paper_runs collection
    """
    
    # Collection name for run history
    COLLECTION_NAME = "growth_paper_runs"
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        paper_executor=None,
        event_logger=None,
    ):
        self.db = db
        self.paper_executor = paper_executor
        self.event_logger = event_logger
        self._processed_plans: set = set()  # plan_ids processed in this session
    
    async def initialize(self):
        """Initialize adapter and ensure indexes."""
        # Create TTL index (7 days)
        await self.db[self.COLLECTION_NAME].create_index(
            "timestamp",
            expireAfterSeconds=7 * 24 * 60 * 60  # 7 days
        )
        
        # Create indexes for queries
        await self.db[self.COLLECTION_NAME].create_index("plan_id")
        await self.db[self.COLLECTION_NAME].create_index("run_id")
        await self.db[self.COLLECTION_NAME].create_index("status")
        
        # Load recent plan IDs for idempotency
        recent = await self.db[self.COLLECTION_NAME].find(
            {},
            {"plan_id": 1, "_id": 0}
        ).sort("timestamp", -1).limit(1000).to_list(1000)
        
        self._processed_plans = {r.get("plan_id") for r in recent if r.get("plan_id")}
        
        logger.info(f"GrowthPaperAdapter initialized, {len(self._processed_plans)} recent plans loaded")
    
    def is_plan_processed(self, plan_id: str) -> bool:
        """Check if a plan has already been processed (idempotency)."""
        return plan_id in self._processed_plans
    
    async def execute_plan(
        self,
        plan: IntentPlan,
        decision_snapshot: Dict[str, Any],
        dry_run: bool = False,
    ) -> RunResult:
        """
        Execute an intent plan through the paper trading engine.
        
        Args:
            plan: The intent plan to execute
            decision_snapshot: Router decision that led to this plan
            dry_run: If True, don't actually execute orders
        
        Returns:
            RunResult with execution details
        """
        # Check idempotency
        if not dry_run and self.is_plan_processed(plan.plan_id):
            logger.warning(f"Plan {plan.plan_id} already processed, skipping")
            existing = await self.db[self.COLLECTION_NAME].find_one(
                {"plan_id": plan.plan_id},
                {"_id": 0}
            )
            if existing:
                return RunResult(**existing)
            return RunResult(
                plan_id=plan.plan_id,
                status="blocked",
                block_reason="IDEMPOTENCY_DUPLICATE",
                reason_codes=["IDEMPOTENCY_DUPLICATE"],
            )
        
        # Initialize result
        result = RunResult(
            plan_id=plan.plan_id,
            status="dry_run" if dry_run else "success",
            is_dry_run=dry_run,
            regime=decision_snapshot.get("regime", ""),
            recommended_agent=decision_snapshot.get("recommended_agent", ""),
            confidence=decision_snapshot.get("regime_confidence", ""),
            decision_snapshot=decision_snapshot,
            reason_codes=plan.reason_codes.copy(),
        )
        
        # Convert intent orders to paper orders
        paper_orders = self._convert_to_paper_orders(plan)
        
        if dry_run:
            # Dry run - just return the plan without execution
            result.orders = [o.model_dump() for o in paper_orders]
            result.orders_created = len(paper_orders)
            await self._save_run(result)
            return result
        
        # Execute orders through paper executor
        if not self.paper_executor:
            result.status = "error"
            result.block_reason = "NO_EXECUTOR"
            result.reason_codes.append("NO_EXECUTOR")
            await self._save_run(result)
            return result
        
        executed_orders = []
        fills = []
        total_fees = 0.0
        total_slippage = 0.0
        pnl_delta = 0.0
        
        for order in paper_orders:
            try:
                executed = await self.paper_executor.execute_order(order)
                executed_orders.append(executed)
                
                if executed.status == OrderStatus.FILLED:
                    result.orders_filled += 1
                    total_fees += executed.commission or 0
                    
                    # Calculate slippage
                    if order.price and executed.average_price:
                        slippage_pct = abs(executed.average_price - order.price) / order.price
                        slippage_eur = slippage_pct * (executed.filled * executed.average_price)
                        total_slippage += slippage_eur
                    
                    fills.append({
                        "order_id": executed.id,
                        "symbol": executed.symbol,
                        "side": executed.side.value,
                        "filled": executed.filled,
                        "price": executed.average_price,
                        "commission": executed.commission,
                        "filled_at": executed.filled_at.isoformat() if executed.filled_at else None,
                    })
                elif executed.status == OrderStatus.REJECTED:
                    result.orders_rejected += 1
                    
            except Exception as e:
                logger.error(f"Error executing order {order.id}: {e}")
                result.orders_rejected += 1
        
        result.orders_created = len(paper_orders)
        result.orders = [self._order_to_dict(o) for o in executed_orders]
        result.fills = fills
        result.fees_eur = total_fees
        result.slippage_eur = total_slippage
        result.pnl_delta_eur = pnl_delta  # Will be updated when positions close
        
        # Mark plan as processed
        self._processed_plans.add(plan.plan_id)
        
        # Save run
        await self._save_run(result)
        
        # Emit event
        if self.event_logger:
            from services.event_logger import EventSeverity, EventCategory
            await self.event_logger.emit(
                severity=EventSeverity.INFO,
                category=EventCategory.GROWTH,
                type="GROWTH_RUN_COMPLETE",
                message=f"Growth run {result.run_id}: {result.orders_filled}/{result.orders_created} orders filled",
                context={
                    "run_id": result.run_id,
                    "plan_id": result.plan_id,
                    "agent_type": plan.agent_type,
                    "orders_created": result.orders_created,
                    "orders_filled": result.orders_filled,
                    "fees_eur": result.fees_eur,
                },
                symbol=plan.symbol,
                tags=["growth", "paper", plan.agent_type.lower()]
            )
        
        return result
    
    def _convert_to_paper_orders(self, plan: IntentPlan) -> List[Order]:
        """Convert intent orders to paper Order objects."""
        orders = []
        
        # Map agent type to AgentType enum
        agent_type_map = {
            "MM": AgentType.GRID,  # MM behaves like grid
            "MOM": AgentType.BREAKOUT,  # MOM behaves like breakout
        }
        agent_type = agent_type_map.get(plan.agent_type, AgentType.GRID)
        
        for intent_order in plan.orders:
            # Map order type
            order_type_map = {
                "limit": OrderType.LIMIT,
                "limit_maker": OrderType.LIMIT,
                "market": OrderType.MARKET,
            }
            order_type = order_type_map.get(intent_order.order_type, OrderType.LIMIT)
            
            # Map side
            side = OrderSide.BUY if intent_order.side.lower() == "buy" else OrderSide.SELL
            
            order = Order(
                id=str(uuid.uuid4()),
                idempotency_key=f"{plan.plan_id}_{intent_order.client_order_id}",
                agent_id=f"growth_{plan.agent_type.lower()}",
                agent_type=agent_type,
                symbol=plan.symbol,
                exchange=plan.venue,
                side=side,
                order_type=order_type,
                amount=intent_order.size_asset,
                price=intent_order.price,
                reason=intent_order.rationale or f"{plan.agent_type} order from plan {plan.plan_id}",
            )
            orders.append(order)
        
        return orders
    
    def _order_to_dict(self, order: Order) -> Dict[str, Any]:
        """Convert Order to dict for storage."""
        d = order.model_dump()
        d["created_at"] = d.get("created_at", datetime.now(timezone.utc)).isoformat() if isinstance(d.get("created_at"), datetime) else d.get("created_at")
        d["updated_at"] = d.get("updated_at", datetime.now(timezone.utc)).isoformat() if isinstance(d.get("updated_at"), datetime) else d.get("updated_at")
        if d.get("filled_at") and isinstance(d["filled_at"], datetime):
            d["filled_at"] = d["filled_at"].isoformat()
        return d
    
    async def _save_run(self, result: RunResult) -> None:
        """Save run result to database."""
        doc = result.model_dump()
        doc["timestamp"] = doc["timestamp"].isoformat() if isinstance(doc.get("timestamp"), datetime) else doc.get("timestamp")
        
        await self.db[self.COLLECTION_NAME].update_one(
            {"run_id": result.run_id},
            {"$set": doc},
            upsert=True
        )
    
    async def get_last_run(self) -> Optional[Dict[str, Any]]:
        """Get the most recent run."""
        doc = await self.db[self.COLLECTION_NAME].find_one(
            {},
            {"_id": 0},
            sort=[("timestamp", -1)]
        )
        return doc
    
    async def get_runs(
        self,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent runs."""
        query = {}
        if status:
            query["status"] = status
        
        docs = await self.db[self.COLLECTION_NAME].find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        return docs
    
    async def get_paper_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent paper orders from runs."""
        runs = await self.get_runs(limit=10)
        orders = []
        for run in runs:
            for order in run.get("orders", []):
                order["run_id"] = run.get("run_id")
                order["plan_id"] = run.get("plan_id")
                orders.append(order)
        return orders[:limit]
    
    async def get_pnl_summary(self) -> Dict[str, Any]:
        """Get PnL summary from all runs."""
        runs = await self.get_runs(limit=100, status="success")
        
        total_pnl = sum(r.get("pnl_delta_eur", 0) for r in runs)
        total_fees = sum(r.get("fees_eur", 0) for r in runs)
        total_slippage = sum(r.get("slippage_eur", 0) for r in runs)
        total_orders = sum(r.get("orders_created", 0) for r in runs)
        total_filled = sum(r.get("orders_filled", 0) for r in runs)
        
        return {
            "total_runs": len(runs),
            "total_pnl_eur": round(total_pnl, 4),
            "total_fees_eur": round(total_fees, 4),
            "total_slippage_eur": round(total_slippage, 4),
            "total_orders": total_orders,
            "total_filled": total_filled,
            "fill_rate_pct": round((total_filled / total_orders * 100) if total_orders > 0 else 0, 2),
            "net_pnl_eur": round(total_pnl - total_fees - total_slippage, 4),
        }
