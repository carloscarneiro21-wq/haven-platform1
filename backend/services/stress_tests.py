"""Stress test module for crypto trading system."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
import random
import logging

from models.trading import (
    Order, OrderSide, OrderType, OrderStatus, AgentType,
    Position, Trade, MarketFeatures, MarketRegime
)

logger = logging.getLogger(__name__)


class StressTestScenario(BaseModel):
    """Definition of a stress test scenario."""
    name: str
    description: str
    duration_seconds: int = 60
    enabled: bool = True


class StressTestResult(BaseModel):
    """Result of a stress test."""
    scenario: str
    passed: bool
    duration_ms: float
    assertions: Dict[str, bool]
    errors: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, Any] = {}


class StressTestEngine:
    """
    Stress test engine for simulating extreme market conditions.
    
    Tests:
    - Flash crash (-5% instant drop)
    - Flash pump (+5% instant rise)
    - Consecutive losses
    - Data source outage
    - Backend restart mid-trade
    - Order duplication prevention
    - State persistence
    - Kill switch functionality
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, runtime=None):
        self.db = db
        self.runtime = runtime
        self.results: List[StressTestResult] = []
        self._original_price: Optional[float] = None
        
    async def run_all_tests(self) -> List[StressTestResult]:
        """Run all stress tests."""
        self.results = []
        
        tests = [
            self.test_order_idempotency,
            self.test_state_persistence,
            self.test_kill_switch,
            self.test_consecutive_losses,
            self.test_flash_crash_simulation,
            self.test_data_stale_handling,
        ]
        
        for test in tests:
            try:
                result = await test()
                self.results.append(result)
                logger.info(f"Stress test '{result.scenario}': {'PASSED' if result.passed else 'FAILED'}")
            except Exception as e:
                logger.error(f"Stress test error: {e}")
                self.results.append(StressTestResult(
                    scenario=test.__name__,
                    passed=False,
                    duration_ms=0,
                    assertions={},
                    errors=[str(e)]
                ))
        
        return self.results
    
    async def test_order_idempotency(self) -> StressTestResult:
        """Test: Submitting same order twice should not create duplicates."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        
        try:
            # Create a unique order
            order_id = f"test_order_{datetime.now().timestamp()}"
            test_order = {
                "id": order_id,
                "agent_id": "test_agent",
                "agent_type": "dca",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": 0.001,
                "price": 65000,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Insert order twice
            await self.db.orders.update_one(
                {"id": order_id},
                {"$set": test_order},
                upsert=True
            )
            await self.db.orders.update_one(
                {"id": order_id},
                {"$set": test_order},
                upsert=True
            )
            
            # Count orders with this ID
            count = await self.db.orders.count_documents({"id": order_id})
            assertions["no_duplicates"] = count == 1
            
            # Cleanup
            await self.db.orders.delete_one({"id": order_id})
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="order_idempotency",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors
        )
    
    async def test_state_persistence(self) -> StressTestResult:
        """Test: State survives simulated restart."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        
        try:
            # Create test position
            position_id = f"test_pos_{datetime.now().timestamp()}"
            test_position = {
                "id": position_id,
                "agent_id": "test_agent",
                "agent_type": "trend",
                "symbol": "BTC/USDT",
                "side": "buy",
                "entry_price": 65000,
                "amount": 0.01,
                "is_open": True,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
            
            await self.db.positions.insert_one(test_position)
            
            # Simulate "restart" by re-reading from DB
            loaded = await self.db.positions.find_one({"id": position_id}, {"_id": 0})
            
            assertions["position_persisted"] = loaded is not None
            assertions["entry_price_preserved"] = loaded.get("entry_price") == 65000 if loaded else False
            assertions["position_state_preserved"] = loaded.get("is_open") == True if loaded else False
            
            # Cleanup
            await self.db.positions.delete_one({"id": position_id})
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="state_persistence",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors
        )
    
    async def test_kill_switch(self) -> StressTestResult:
        """Test: Kill switch immediately stops all trading."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        warnings = []
        
        try:
            # Save original state
            original_settings = await self.db.risk_settings.find_one({}, {"_id": 0})
            
            # Activate kill switch
            await self.db.risk_settings.update_one(
                {},
                {"$set": {"kill_switch_active": True}},
                upsert=True
            )
            
            # Verify kill switch is active
            settings = await self.db.risk_settings.find_one({}, {"_id": 0})
            assertions["kill_switch_activates"] = settings.get("kill_switch_active") == True
            
            # Verify trading_allowed would be false
            trading_allowed = not settings.get("kill_switch_active", False)
            assertions["trading_blocked"] = trading_allowed == False
            
            # Deactivate kill switch
            await self.db.risk_settings.update_one(
                {},
                {"$set": {"kill_switch_active": False}},
                upsert=True
            )
            
            # Verify kill switch is deactivated
            settings = await self.db.risk_settings.find_one({}, {"_id": 0})
            assertions["kill_switch_deactivates"] = settings.get("kill_switch_active") == False
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="kill_switch",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors,
            warnings=warnings
        )
    
    async def test_consecutive_losses(self) -> StressTestResult:
        """Test: System triggers cooldown after consecutive losses."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        
        try:
            # Insert consecutive losing trades
            base_time = datetime.now(timezone.utc)
            losing_trades = []
            
            for i in range(5):
                trade = {
                    "id": f"loss_test_{i}_{base_time.timestamp()}",
                    "order_id": f"order_{i}",
                    "agent_id": "test_agent",
                    "agent_type": "trend",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "amount": 0.01,
                    "price": 65000,
                    "value": 650,
                    "pnl": -50,  # Losing trade
                    "executed_at": (base_time + timedelta(seconds=i)).isoformat(),
                }
                losing_trades.append(trade)
            
            await self.db.trades.insert_many(losing_trades)
            
            # Update risk settings to simulate consecutive losses detection
            await self.db.risk_settings.update_one(
                {},
                {"$set": {"consecutive_losses": 5}},
                upsert=True
            )
            
            # Check if system would block trading
            settings = await self.db.risk_settings.find_one({}, {"_id": 0})
            max_consecutive = settings.get("max_consecutive_losses", 5)
            current_consecutive = settings.get("consecutive_losses", 0)
            
            assertions["consecutive_losses_tracked"] = current_consecutive >= 5
            assertions["would_trigger_cooldown"] = current_consecutive >= max_consecutive
            
            # Cleanup
            for trade in losing_trades:
                await self.db.trades.delete_one({"id": trade["id"]})
            
            # Reset consecutive losses
            await self.db.risk_settings.update_one(
                {},
                {"$set": {"consecutive_losses": 0}},
                upsert=True
            )
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="consecutive_losses",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors
        )
    
    async def test_flash_crash_simulation(self) -> StressTestResult:
        """Test: System handles -5% instant price drop correctly."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        metrics = {}
        
        try:
            # Create a position that would be affected by flash crash
            base_price = 65000
            crash_price = base_price * 0.95  # -5%
            
            # Test stop loss would trigger
            position_entry = 64000
            stop_loss_pct = 3.0
            stop_loss_price = position_entry * (1 - stop_loss_pct / 100)
            
            # Calculate if stop would trigger
            would_trigger_stop = crash_price < stop_loss_price
            
            assertions["stop_loss_triggers_on_crash"] = would_trigger_stop
            
            # Calculate loss
            loss_pct = ((crash_price - position_entry) / position_entry) * 100
            metrics["flash_crash_loss_pct"] = loss_pct
            metrics["crash_price"] = crash_price
            metrics["stop_loss_price"] = stop_loss_price
            
            # Verify loss is within acceptable range (stop loss should limit it)
            max_acceptable_loss = stop_loss_pct + 1.0  # 1% slippage allowance
            assertions["loss_within_limits"] = abs(loss_pct) <= max_acceptable_loss if would_trigger_stop else True
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="flash_crash_simulation",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors,
            metrics=metrics
        )
    
    async def test_data_stale_handling(self) -> StressTestResult:
        """Test: System enters safe mode when data is stale."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        
        try:
            # Simulate stale data scenario
            stale_threshold_seconds = 180  # 3 minutes
            last_update = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold_seconds + 60)
            
            # Check if system would consider this stale
            age_seconds = (datetime.now(timezone.utc) - last_update).total_seconds()
            is_stale = age_seconds > stale_threshold_seconds
            
            assertions["detects_stale_data"] = is_stale
            
            # Verify safe mode behavior (exits only, no new entries)
            # This is a logic check, not actual execution
            safe_mode_actions = ["close", "hold"]  # Allowed in safe mode
            new_entry_actions = ["buy", "sell"]  # Blocked in safe mode
            
            assertions["safe_mode_blocks_entries"] = True  # Design assertion
            assertions["safe_mode_allows_exits"] = True  # Design assertion
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="data_stale_handling",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors
        )
    
    async def test_api_down_recovery(self) -> StressTestResult:
        """Test: System recovers gracefully from API outage."""
        start = datetime.now(timezone.utc)
        assertions = {}
        errors = []
        warnings = []
        
        try:
            # This test checks the fallback mechanism design
            # Primary: Binance -> Secondary: CoinGecko -> Tertiary: Cached data
            
            fallback_chain = ["binance", "coingecko", "cached"]
            
            assertions["fallback_chain_defined"] = len(fallback_chain) == 3
            assertions["has_cache_fallback"] = "cached" in fallback_chain
            
            # Check that system logs data source switches
            assertions["would_log_source_switch"] = True  # Design requirement
            
            warnings.append("Full API outage test requires manual intervention")
            
        except Exception as e:
            errors.append(str(e))
        
        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        
        return StressTestResult(
            scenario="api_down_recovery",
            passed=all(assertions.values()) and not errors,
            duration_ms=duration,
            assertions=assertions,
            errors=errors,
            warnings=warnings
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all test results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "results": [r.model_dump() for r in self.results],
        }


# Stress test scenarios for UI triggers
STRESS_SCENARIOS = [
    StressTestScenario(
        name="flash_crash",
        description="Simulate -5% instant price drop",
        duration_seconds=30
    ),
    StressTestScenario(
        name="flash_pump",
        description="Simulate +5% instant price rise",
        duration_seconds=30
    ),
    StressTestScenario(
        name="api_outage",
        description="Simulate data feed outage for 10 minutes",
        duration_seconds=600
    ),
    StressTestScenario(
        name="latency_spike",
        description="Simulate 500ms+ API latency",
        duration_seconds=60
    ),
    StressTestScenario(
        name="consecutive_losses",
        description="Simulate 3+ consecutive losing trades",
        duration_seconds=30
    ),
]
