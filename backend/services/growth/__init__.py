"""
Growth Module Package
=====================

Clean interfaces and implementations for the Growth Module.
"""

from .interfaces import (
    # Run modes & status
    RunMode,
    RunStatus,
    
    # Data models
    MarketSnapshot,
    IntentOrder,
    IntentPlan,
    ViabilityStatus,
    ViabilityResult,
    GuardianAction,
    GuardianResult,
    GuardianContext,
    ExecutionResult,
    RunResult,
    
    # Interface ABCs
    IGrowthOrchestrator,
    IGrowthModule,
    IViabilityEngine,
    IGuardian,
    IPaperExecutor,
    
    # Helpers
    get_timestamp_bucket,
    get_config_hash,
)

__all__ = [
    "RunMode",
    "RunStatus",
    "MarketSnapshot",
    "IntentOrder",
    "IntentPlan",
    "ViabilityStatus",
    "ViabilityResult",
    "GuardianAction",
    "GuardianResult",
    "GuardianContext",
    "ExecutionResult",
    "RunResult",
    "IGrowthOrchestrator",
    "IGrowthModule",
    "IViabilityEngine",
    "IGuardian",
    "IPaperExecutor",
    "get_timestamp_bucket",
    "get_config_hash",
]
