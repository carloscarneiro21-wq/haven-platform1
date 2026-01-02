"""
Stress Sandbox Module
=====================
SIMULATION environment for testing trading agents under extreme conditions.

SAFETY:
- Forces PAPER mode
- No live trading
- All actions logged as "SIMULATION"
"""

from services.sandbox.scenario_engine import (
    ScenarioEngine, ScenarioTimeline, ScenarioEvent,
    ScenarioEventType, Severity, EventPack
)
from services.sandbox.synthetic_feed import (
    SyntheticPriceFeed, PriceTick, Candle, MarketSnapshot
)
from services.sandbox.execution_simulator import (
    ExecutionSimulator, OrderRequest, ExecutionResult, ExecutionStatus, RejectionReason
)
from services.sandbox.dex_simulator import (
    DexSimulator, SwapRequest, SwapResult, PoolState, TokenTrapType, MEVResult
)
from services.sandbox.fault_injector import (
    FaultInjector, FaultState, FaultEvent
)
from services.sandbox.sandbox_runner import (
    SandboxRunner, SandboxConfig, SandboxRun, SandboxReport, 
    SandboxMetrics, SandboxRunStatus, GuardianDecision
)

__all__ = [
    # Scenario Engine
    "ScenarioEngine", "ScenarioTimeline", "ScenarioEvent",
    "ScenarioEventType", "Severity", "EventPack",
    
    # Synthetic Feed
    "SyntheticPriceFeed", "PriceTick", "Candle", "MarketSnapshot",
    
    # Execution Simulator
    "ExecutionSimulator", "OrderRequest", "ExecutionResult", 
    "ExecutionStatus", "RejectionReason",
    
    # DEX Simulator
    "DexSimulator", "SwapRequest", "SwapResult", "PoolState", 
    "TokenTrapType", "MEVResult",
    
    # Fault Injector
    "FaultInjector", "FaultState", "FaultEvent",
    
    # Sandbox Runner
    "SandboxRunner", "SandboxConfig", "SandboxRun", "SandboxReport",
    "SandboxMetrics", "SandboxRunStatus", "GuardianDecision",
]
