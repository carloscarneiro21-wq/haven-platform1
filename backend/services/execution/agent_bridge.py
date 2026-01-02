"""Agent Execution Bridge - Connects ExecutionRouter with TradesService.

This module bridges the gap between:
- ExecutionRouter (used by agents for execution)
- TradesService (used by UI for displaying trades)

When an agent executes a trade through ExecutionRouter:
1. Trade is validated and simulated (fees, slippage, latency)
2. Trade is persisted via TradesService (agent_trades collection)
3. WebSocket event is emitted for real-time UI updates
4. Trade ID is returned for later close operations

Supports:
- Opening new positions
- Closing existing positions (with PnL calculation)
- Kill switch enforcement
- Position tracking per agent/strategy
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4

from services.execution.router import ExecutionRouter, TradeRequest, TradeResult, get_execution_router
from services.execution.config import get_trading_config
from services.trades_service import TradesService, AgentTrade, get_trades_service
from services.agent_execution_log import AgentExecutionLogStore

logger = logging.getLogger(__name__)


class AgentExecutionBridge:
    """Bridge between agents and the paper trading system.
    
    Usage:
        bridge = AgentExecutionBridge()
        await bridge.initialize()
        
        # Open a position
        result = await bridge.open_position(
            agent_id="mm_agent_1",
            agent_name="Market Maker",
            strategy="MM",
            symbol="BTC/USDT",
            side="BUY",
            qty=0.1,
            price=65000.0,
        )
        
        # Later, close the position
        close_result = await bridge.close_position(
            trade_id=result["trade_id"],
            exit_price=66000.0,
        )
    """
    
    def __init__(self):
        self._execution_router: Optional[ExecutionRouter] = None
        self._trades_service: Optional[TradesService] = None
        self._logs: Optional[AgentExecutionLogStore] = None
        self._open_positions: Dict[str, str] = {}  # key: agent_id:strategy:symbol -> trade_id
        self._initialized = False
    
    async def initialize(self):
        """Initialize the bridge with required services."""
        self._execution_router = get_execution_router()
        self._trades_service = get_trades_service()
        
        if not self._execution_router:
            logger.warning("ExecutionRouter not available - bridge limited functionality")
        
        if not self._trades_service:
            logger.warning("TradesService not available - bridge limited functionality")
        else:
            # Execution logs (powers Trades Report 'failures' section)
            self._logs = AgentExecutionLogStore(self._trades_service.db)
            await self._logs.initialize()
        
        self._initialized = True
        logger.info("AgentExecutionBridge initialized")
    
    def _get_position_key(self, agent_id: str, strategy: str, symbol: str) -> str:
        """Generate unique key for tracking open positions."""
        return f"{agent_id}:{strategy}:{symbol}"
    
    async def open_position(
        self,
        agent_id: str,
        agent_name: str,
        strategy: str,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Open a new position for an agent.
        
        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name
            strategy: Trading strategy (MM, MOM, SNIPER, DEX, etc.)
            symbol: Trading pair (e.g., BTC/USDT)
            side: BUY or SELL
            qty: Quantity to trade
            price: Target price (optional, uses market price if not provided)
            reason: Reason for the trade
            metadata: Additional metadata
        
        Returns:
            Dict with trade_id, success, and execution details
        """
        config = get_trading_config()
        
        # Check kill switch
        if config.kill_switch_active:
            logger.warning(f"[Agent:{agent_id}] Position blocked - Kill switch active: {config.kill_switch_reason}")
            return {
                "success": False,
                "blocked": True,
                "reason": f"Kill switch active: {config.kill_switch_reason}",
                "trade_id": None,
            }
        
        # Normalize symbol
        normalized_symbol = symbol.upper()
        if "/" not in normalized_symbol:
            if normalized_symbol.endswith("USDT"):
                normalized_symbol = normalized_symbol[:-4] + "/USDT"
            elif normalized_symbol.endswith("USD"):
                normalized_symbol = normalized_symbol[:-3] + "/USD"
        
        # Create trade request for execution router
        request = TradeRequest(
            agent_id=agent_id,
            agent_type=strategy,
            symbol=normalized_symbol,
            side=side.upper(),
            amount=qty,
            price=price,
            order_type="MARKET",
            strategy=strategy,
            reason=reason,
            metadata=metadata or {},
        )
        
        # Execute through router (validates limits, simulates fees/slippage)
        result = None
        if self._execution_router:
            result = await self._execution_router.execute(request)
            
            if not result.success:
                reason = result.blocked_reason or result.error_message
                logger.warning(f"[Agent:{agent_id}] Execution failed: {reason}")

                # Log failure (must be clean and informative for geo-block scenarios)
                if self._logs:
                    reason_l = (reason or "").lower()
                    code = "OTHER"
                    if any(x in reason_l for x in ["http 451", "status code 451", "restricted location", "geolocation", "geo"]):
                        code = "BINANCE_UNAVAILABLE"
                    elif any(x in reason_l for x in ["connecterror", "connection", "timed out", "timeout", "name or service not known", "temporary failure", "host"]):
                        code = "BINANCE_UNAVAILABLE"
                    elif "binance" in reason_l:
                        code = "BINANCE_ERROR"

                    await self._logs.log(
                        agent_id=agent_id,
                        strategy=strategy,
                        symbol=normalized_symbol,
                        action="open",
                        status="blocked" if result.status == "BLOCKED" else "error",
                        code=code,
                        message=reason or "Execution failed",
                        details={
                            "trading_mode": get_trading_config().trading_mode.value,
                            "venue": getattr(result, "venue", None),
                            "blocked_reason": result.blocked_reason,
                            "error_message": result.error_message,
                            "request": {
                                "request_id": request.request_id,
                                "symbol": request.symbol,
                                "side": request.side,
                                "amount": request.amount,
                                "order_type": request.order_type,
                                "price": request.price,
                            },
                        },
                    )

                return {
                    "success": False,
                    "blocked": result.status == "BLOCKED",
                    "reason": reason,
                    "trade_id": None,
                }
            
            # Use execution result values
            entry_price = result.entry_price
            executed_qty = result.executed_amount
            fees = result.fees
            slippage = result.slippage
            latency_ms = result.latency_ms
        else:
            # Fallback if router not available
            entry_price = price or 0
            executed_qty = qty
            fees = qty * entry_price * 0.001  # 0.1% fee
            slippage = 0.01
            latency_ms = 100
        
        # Create trade in TradesService (this emits WS event)
        if self._trades_service:
            # Determine venue and mode
            config = get_trading_config()
            venue = "PAPER"
            order_id = None
            cumulative_quote_qty = None
            avg_fill_price = None
            
            # If we have execution router result, use its values
            if result:
                venue = getattr(result, 'venue', None) or ("BINANCE_TESTNET" if config.trading_mode.value == "binance_testnet" else "PAPER")
                order_id = getattr(result, 'order_id', None)
                cumulative_quote_qty = getattr(result, 'executed_quote_qty', None)
                avg_fill_price = getattr(result, 'avg_fill_price', None)
            else:
                # Fallback values when router not available
                venue = "BINANCE_TESTNET" if config.trading_mode.value == "binance_testnet" else "PAPER"
            
            trade = AgentTrade(
                agent_id=agent_id,
                agent_name=agent_name,
                strategy=strategy,
                mode=config.trading_mode.value,
                venue=venue,
                order_id=order_id,
                executed_qty=executed_qty,
                cumulative_quote_qty=cumulative_quote_qty,
                avg_fill_price=avg_fill_price,
                symbol=normalized_symbol,
                side=side.upper(),
                qty=executed_qty,
                entry_price=entry_price,
                exit_price=None,
                status="OPEN",
                fees=fees,
                slippage=slippage,
                pnl=0.0,
                pnl_pct=0.0,
                meta={
                    "reason": reason,
                    "latency_ms": latency_ms,
                    "requested_qty": qty,
                    **(metadata or {}),
                },
            )
            
            created_trade = await self._trades_service.create_trade(trade)
            trade_id = created_trade.id
            
            # Track open position
            position_key = self._get_position_key(agent_id, strategy, normalized_symbol)
            self._open_positions[position_key] = trade_id
            
            logger.info(
                f"[Agent:{agent_id}] Opened {side} position: {executed_qty} {normalized_symbol} @ {entry_price:.2f} "
                f"(trade_id={trade_id}, fees={fees:.2f}, slippage={slippage:.3f}%)"
            )

            # Log success (useful for audit / report)
            if self._logs:
                await self._logs.log(
                    agent_id=agent_id,
                    strategy=strategy,
                    symbol=normalized_symbol,
                    action="open",
                    status="success",
                    code="SUCCESS",
                    message="Trade opened",
                    details={
                        "trade_id": trade_id,
                        "trading_mode": config.trading_mode.value,
                        "venue": venue,
                        "order_id": order_id,
                        "executed_qty": executed_qty,
                        "entry_price": entry_price,
                    },
                )
            
            return {
                "success": True,
                "blocked": False,
                "trade_id": trade_id,
                "entry_price": entry_price,
                "qty": executed_qty,
                "fees": fees,
                "slippage": slippage,
                "latency_ms": latency_ms,
            }
        else:
            logger.error(f"[Agent:{agent_id}] TradesService not available - trade not persisted")
            return {
                "success": False,
                "blocked": False,
                "reason": "TradesService not available",
                "trade_id": None,
            }
    
    async def close_position(
        self,
        trade_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        exit_price: float = 0.0,
        fees: float = 0.0,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Close an open position.
        
        Args:
            trade_id: Specific trade ID to close (preferred)
            agent_id: Agent ID (used if trade_id not provided)
            strategy: Strategy (used if trade_id not provided)
            symbol: Symbol (used if trade_id not provided)
            exit_price: Exit price for the trade
            fees: Additional fees for closing
            reason: Reason for closing
        
        If trade_id is not provided, will try to find the last OPEN trade
        matching agent_id + strategy + symbol.
        
        Returns:
            Dict with success, pnl, and trade details
        """
        config = get_trading_config()
        
        # Check kill switch (even for closes, to ensure consistency)
        if config.kill_switch_active:
            logger.warning("[Close] Position close blocked - Kill switch active")
            return {
                "success": False,
                "blocked": True,
                "reason": f"Kill switch active: {config.kill_switch_reason}",
            }
        
        if not self._trades_service:
            return {
                "success": False,
                "reason": "TradesService not available",
            }
        
        # Find trade_id if not provided
        if not trade_id:
            if agent_id and strategy and symbol:
                # Normalize symbol
                normalized_symbol = symbol.upper()
                if "/" not in normalized_symbol:
                    if normalized_symbol.endswith("USDT"):
                        normalized_symbol = normalized_symbol[:-4] + "/USDT"
                
                # Check tracked positions first
                position_key = self._get_position_key(agent_id, strategy, normalized_symbol)
                trade_id = self._open_positions.get(position_key)
                
                if not trade_id:
                    # Search in database for last OPEN trade
                    trades = await self._trades_service.get_trades(
                        agent_id=agent_id,
                        symbol=normalized_symbol,
                        strategy=strategy,
                        status="OPEN",
                        limit=1,
                    )
                    if trades:
                        trade_id = trades[0].get("id")
            
            if not trade_id:
                return {
                    "success": False,
                    "reason": "No matching open trade found",
                }
        
        # Close the trade
        result = await self._trades_service.close_trade(
            trade_id=trade_id,
            exit_price=exit_price,
            fees=fees,
        )
        
        if result:
            # Remove from tracked positions
            for key, tid in list(self._open_positions.items()):
                if tid == trade_id:
                    del self._open_positions[key]
                    break
            
            pnl = result.get("pnl", 0)
            pnl_pct = result.get("pnl_pct", 0)
            
            logger.info(
                f"[Close] Trade {trade_id} closed @ {exit_price:.2f} - "
                f"PnL: €{pnl:.2f} ({pnl_pct:.2f}%)"
            )
            
            # Update daily loss in router if negative
            if pnl < 0 and self._execution_router:
                self._execution_router.update_daily_loss(pnl)
            
            return {
                "success": True,
                "trade_id": trade_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "status": "CLOSED",
            }
        else:
            return {
                "success": False,
                "reason": f"Failed to close trade {trade_id}",
            }
    
    async def get_open_positions(self, agent_id: Optional[str] = None) -> list:
        """Get all open positions, optionally filtered by agent."""
        if not self._trades_service:
            return []
        
        trades = await self._trades_service.get_trades(
            agent_id=agent_id,
            status="OPEN",
            mode="paper",
            limit=100,
        )
        return trades
    
    def get_status(self) -> Dict[str, Any]:
        """Get bridge status."""
        return {
            "initialized": self._initialized,
            "execution_router_available": self._execution_router is not None,
            "trades_service_available": self._trades_service is not None,
            "tracked_positions": len(self._open_positions),
        }


# Global singleton
_agent_bridge: Optional[AgentExecutionBridge] = None


def get_agent_bridge() -> Optional[AgentExecutionBridge]:
    """Get global agent execution bridge."""
    return _agent_bridge


async def init_agent_bridge() -> AgentExecutionBridge:
    """Initialize and return the global agent execution bridge."""
    global _agent_bridge
    if _agent_bridge is None:
        _agent_bridge = AgentExecutionBridge()
        await _agent_bridge.initialize()
    return _agent_bridge
