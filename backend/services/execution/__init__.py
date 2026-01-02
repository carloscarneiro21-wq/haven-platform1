"""Execution module - Centralized trading execution for HAVEN.

This module provides:
- TradingConfig: Global trading mode configuration
- ExecutionRouter: Single canonical executor for all agents
- PaperExecutor: Realistic paper trading simulation
- LiveExecutor: Future live trading (blocked by default)

PRINCIPLE: All agents MUST use ExecutionRouter. No direct CEX/DEX calls.
"""

from services.execution.config import TradingConfig, TradingMode, get_trading_config
from services.execution.router import ExecutionRouter, get_execution_router
from services.execution.paper_executor import PaperTradeExecutor
from services.execution.live_executor import LiveTradeExecutor

__all__ = [
    "TradingConfig",
    "TradingMode",
    "get_trading_config",
    "ExecutionRouter",
    "get_execution_router",
    "PaperTradeExecutor",
    "LiveTradeExecutor",
]
