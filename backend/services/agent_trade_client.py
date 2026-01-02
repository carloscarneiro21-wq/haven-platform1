"""AgentTradeClient

Internal execution layer used by all automated agents (MM/MOM/SNIPER) to create
and close PAPER trades.

IMPORTANT: Agents should NOT call HTTP endpoints. They must call the same
underlying logic as the PRD endpoints via the AgentExecutionBridge/TradesService.

Guardrails implemented here:
- Positions check (same logic as GET /api/agent/positions)
- max OPEN positions per (agent_id + symbol) = 1
- rate limit opens: 2 per 60 seconds per agent_id (persisted)
- kill switch hard block on open and close
- persisted trade_id in agent state for deterministic closes

Blocked response contract:
{
  "status": "blocked",
  "code": "BLOCKED_KILL_SWITCH"|"BLOCKED_ALREADY_OPEN"|"BLOCKED_RATE_LIMIT"|"BLOCKED_MAX_OPEN",
  "message": "...",
  "details": {...}
}
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from services.agent_trade_state import AgentTradeStateStore
from services.execution.config import get_trading_config
from services.execution.agent_bridge import get_agent_bridge
from services.trades_service import get_trades_service

logger = logging.getLogger(__name__)


StrategyLiteral = Literal["MM", "MOM", "SNIPER"]
SideLiteral = Literal["BUY", "SELL"]
CloseReasonLiteral = Literal["tp", "sl", "timeout", "manual", "signal_flip"]


class AgentOpenPayload(BaseModel):
    symbol: str
    side: SideLiteral
    qty: float = Field(..., gt=0)
    entry_price: Optional[float] = Field(None, gt=0)
    strategy: StrategyLiteral
    agent_id: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class AgentClosePayload(BaseModel):
    exit_price: Optional[float] = Field(None, gt=0)
    reason: CloseReasonLiteral = "manual"
    meta: Dict[str, Any] = Field(default_factory=dict)


def blocked(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": "blocked",
        "code": code,
        "message": message,
        "details": details or {},
    }


class AgentTradeClient:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.state = AgentTradeStateStore(db)
        from services.agent_execution_log import AgentExecutionLogStore
        self.logs = AgentExecutionLogStore(db)

    async def initialize(self) -> None:
        await self.state.initialize()
        await self.logs.initialize()

    async def _get_open_positions(self, agent_id: str):
        """Same logic source as GET /api/agent/positions."""
        bridge = get_agent_bridge()
        if not bridge:
            return []
        return await bridge.get_open_positions(agent_id=agent_id)

    async def open_trade(self, payload: AgentOpenPayload) -> Dict[str, Any]:
        config = get_trading_config()
        if config.kill_switch_active:
            logger.warning(f"[AgentTradeClient] BLOCKED_KILL_SWITCH agent_id={payload.agent_id}")
            await self.logs.log(
                agent_id=payload.agent_id,
                strategy=payload.strategy,
                symbol=payload.symbol,
                action="open",
                status="blocked",
                code="BLOCKED_KILL_SWITCH",
                message=f"Kill switch active: {config.kill_switch_reason}",
                details={"kill_switch_reason": config.kill_switch_reason},
            )
            return blocked(
                "BLOCKED_KILL_SWITCH",
                f"Kill switch active: {config.kill_switch_reason}",
                {"kill_switch_reason": config.kill_switch_reason},
            )

        # (1) positions check before open
        positions = await self._get_open_positions(payload.agent_id)

        # Normalize symbol representation as stored in trades
        symbol = payload.symbol.upper()

        # Block duplicates for (symbol, agent_id, strategy)
        for p in positions:
            if p.get("symbol", "").upper() == symbol and (p.get("strategy") or "").upper() == payload.strategy:
                await self.logs.log(
                    agent_id=payload.agent_id,
                    strategy=payload.strategy,
                    symbol=payload.symbol,
                    action="open",
                    status="blocked",
                    code="BLOCKED_ALREADY_OPEN",
                    message="Open position already exists for (symbol, agent_id, strategy)",
                    details={"symbol": symbol, "agent_id": payload.agent_id, "strategy": payload.strategy, "trade_id": p.get("id")},
                )
                return blocked(
                    "BLOCKED_ALREADY_OPEN",
                    "Open position already exists for (symbol, agent_id, strategy)",
                    {"symbol": symbol, "agent_id": payload.agent_id, "strategy": payload.strategy, "trade_id": p.get("id")},
                )

        # (2) max OPEN positions per (agent_id + symbol) = 1
        for p in positions:
            if p.get("symbol", "").upper() == symbol:
                await self.logs.log(
                    agent_id=payload.agent_id,
                    strategy=payload.strategy,
                    symbol=payload.symbol,
                    action="open",
                    status="blocked",
                    code="BLOCKED_MAX_OPEN",
                    message="Max open positions reached for (agent_id + symbol)",
                    details={"symbol": symbol, "agent_id": payload.agent_id, "existing_trade_id": p.get("id"), "existing_strategy": p.get("strategy")},
                )
                return blocked(
                    "BLOCKED_MAX_OPEN",
                    "Max open positions reached for (agent_id + symbol)",
                    {"symbol": symbol, "agent_id": payload.agent_id, "existing_trade_id": p.get("id"), "existing_strategy": p.get("strategy")},
                )

        # (3) rate limit opens: 2/min/agent_id (persisted)
        recent = await self.state.get_open_events_in_window(payload.agent_id, window_seconds=60)
        if len(recent) >= 2:
            await self.logs.log(
                agent_id=payload.agent_id,
                strategy=payload.strategy,
                symbol=payload.symbol,
                action="open",
                status="blocked",
                code="BLOCKED_RATE_LIMIT",
                message="Open rate limit exceeded (max 2 opens per 60s per agent)",
                details={"agent_id": payload.agent_id, "window_seconds": 60, "count": len(recent)},
            )
            return blocked(
                "BLOCKED_RATE_LIMIT",
                "Open rate limit exceeded (max 2 opens per 60s per agent)",
                {"agent_id": payload.agent_id, "window_seconds": 60, "count": len(recent)},
            )

        # Hard guardrails (symbol whitelist + live disabled)
        if config.allowed_symbols:
            req_sym = symbol.replace("/", "").replace("-", "")
            allowed = {s.upper().replace("/", "").replace("-", "") for s in config.allowed_symbols}
            if req_sym not in allowed:
                await self.logs.log(
                    agent_id=payload.agent_id,
                    strategy=payload.strategy,
                    symbol=payload.symbol,
                    action="open",
                    status="blocked",
                    code="BLOCKED_SYMBOL_NOT_ALLOWED",
                    message="Symbol not allowed",
                    details={"symbol": symbol, "allowed_symbols": config.allowed_symbols},
                )
                return blocked("BLOCKED_SYMBOL_NOT_ALLOWED", "Symbol not allowed", {"symbol": symbol})

        if str(getattr(config.trading_mode, "value", config.trading_mode)) != "paper" and not config.live_cex_enabled:
            await self.logs.log(
                agent_id=payload.agent_id,
                strategy=payload.strategy,
                symbol=payload.symbol,
                action="open",
                status="blocked",
                code="BLOCKED_LIVE_DISABLED",
                message="Live CEX disabled",
                details={"trading_mode": config.trading_mode},
            )
            return blocked("BLOCKED_LIVE_DISABLED", "Live CEX disabled", {"trading_mode": config.trading_mode})

        # Execute via AgentExecutionBridge (same underlying logic as PRD endpoints)
        bridge = get_agent_bridge()
        if not bridge:
            await self.logs.log(
                agent_id=payload.agent_id,
                strategy=payload.strategy,
                symbol=payload.symbol,
                action="open",
                status="error",
                code="BRIDGE_UNAVAILABLE",
                message="Agent execution bridge not available",
                details={},
            )
            return {"status": "error", "message": "Agent execution bridge not available"}

        agent_name = payload.meta.get("agent_name") or payload.strategy
        meta = {
            **(payload.meta or {}),
            "agent_id": payload.agent_id,
            "strategy": payload.strategy,
        }

        result = await bridge.open_position(
            agent_id=payload.agent_id,
            agent_name=str(agent_name),
            strategy=payload.strategy,
            symbol=payload.symbol,
            side=payload.side,
            qty=payload.qty,
            price=payload.entry_price,
            reason=str(payload.meta.get("signal_reason") or payload.meta.get("reason") or ""),
            metadata=meta,
        )

        if not result.get("success"):
            if result.get("blocked"):
                # Preserve agent-bridge kill switch response as a standard code
                reason = (result.get("reason") or "").lower()
                if "kill switch" in reason:
                    await self.logs.log(
                        agent_id=payload.agent_id,
                        strategy=payload.strategy,
                        symbol=payload.symbol,
                        action="open",
                        status="blocked",
                        code="BLOCKED_KILL_SWITCH",
                        message=result.get("reason", "Kill switch active"),
                        details={"reason": result.get("reason")},
                    )
                    return blocked("BLOCKED_KILL_SWITCH", result.get("reason", "Kill switch active"), {"reason": result.get("reason")})

                await self.logs.log(
                    agent_id=payload.agent_id,
                    strategy=payload.strategy,
                    symbol=payload.symbol,
                    action="open",
                    status="blocked",
                    code="BLOCKED_EXECUTION",
                    message=result.get("reason", "Execution blocked"),
                    details={"reason": result.get("reason")},
                )
                return blocked("BLOCKED_EXECUTION", result.get("reason", "Execution blocked"), {"reason": result.get("reason")})

            await self.logs.log(
                agent_id=payload.agent_id,
                strategy=payload.strategy,
                symbol=payload.symbol,
                action="open",
                status="error",
                code="EXECUTION_ERROR",
                message=result.get("reason", "Execution failed"),
                details={"reason": result.get("reason")},
            )
            return {"status": "error", "message": result.get("reason", "Execution failed")}

        trade_id = result.get("trade_id")
        if trade_id:
            await self.state.set_open_trade_id(payload.agent_id, payload.symbol, payload.strategy, trade_id)
            await self.state.record_open_event(payload.agent_id)

        await self.logs.log(
            agent_id=payload.agent_id,
            strategy=payload.strategy,
            symbol=payload.symbol,
            action="open",
            status="success",
            code="SUCCESS",
            message="Open executed",
            details={"trade_id": trade_id},
        )

        return {"status": "ok", "trade_id": trade_id, "result": result}

    async def close_trade(self, agent_id: str, symbol: str, strategy: str, payload: AgentClosePayload) -> Dict[str, Any]:
        config = get_trading_config()
        if config.kill_switch_active:
            logger.warning(f"[AgentTradeClient] BLOCKED_KILL_SWITCH close agent_id={agent_id}")
            await self.logs.log(
                agent_id=agent_id,
                strategy=strategy,
                symbol=symbol,
                action="close",
                status="blocked",
                code="BLOCKED_KILL_SWITCH",
                message=f"Kill switch active: {config.kill_switch_reason}",
                details={"kill_switch_reason": config.kill_switch_reason},
            )
            return blocked(
                "BLOCKED_KILL_SWITCH",
                f"Kill switch active: {config.kill_switch_reason}",
                {"kill_switch_reason": config.kill_switch_reason},
            )

        # Symbol whitelist + live disabled guardrails
        sym = symbol.upper()
        if config.allowed_symbols:
            req_sym = sym.replace("/", "").replace("-", "")
            allowed = {s.upper().replace("/", "").replace("-", "") for s in config.allowed_symbols}
            if req_sym not in allowed:
                await self.logs.log(
                    agent_id=agent_id,
                    strategy=strategy,
                    symbol=symbol,
                    action="close",
                    status="blocked",
                    code="BLOCKED_SYMBOL_NOT_ALLOWED",
                    message="Symbol not allowed",
                    details={"symbol": sym, "allowed_symbols": config.allowed_symbols},
                )
                return blocked("BLOCKED_SYMBOL_NOT_ALLOWED", "Symbol not allowed", {"symbol": sym})

        if str(getattr(config.trading_mode, "value", config.trading_mode)) != "paper" and not config.live_cex_enabled:
            await self.logs.log(
                agent_id=agent_id,
                strategy=strategy,
                symbol=symbol,
                action="close",
                status="blocked",
                code="BLOCKED_LIVE_DISABLED",
                message="Live CEX disabled",
                details={"trading_mode": config.trading_mode},
            )
            return blocked("BLOCKED_LIVE_DISABLED", "Live CEX disabled", {"trading_mode": config.trading_mode})

        bridge = get_agent_bridge()
        trades_service = get_trades_service()
        if not bridge or not trades_service:
            await self.logs.log(
                agent_id=agent_id,
                strategy=strategy,
                symbol=symbol,
                action="close",
                status="error",
                code="SERVICE_UNAVAILABLE",
                message="Trade services not available",
                details={},
            )
            return {"status": "error", "message": "Trade services not available"}

        trade_id = await self.state.get_open_trade_id(agent_id, symbol, strategy)

        # Resolve trade_id if missing in state
        if not trade_id:
            positions = await self._get_open_positions(agent_id)
            matches = [
                p for p in positions
                if p.get("symbol", "").upper() == symbol.upper() and (p.get("strategy") or "").upper() == strategy.upper()
            ]
            if len(matches) == 1:
                trade_id = matches[0].get("id")
            elif len(matches) > 1:
                await self.logs.log(
                    agent_id=agent_id,
                    strategy=strategy,
                    symbol=symbol,
                    action="close",
                    status="blocked",
                    code="BLOCKED_AMBIGUOUS_TRADE",
                    message="Multiple OPEN trades found for (symbol, agent_id, strategy)",
                    details={"agent_id": agent_id, "symbol": symbol, "strategy": strategy, "count": len(matches)},
                )
                return blocked(
                    "BLOCKED_AMBIGUOUS_TRADE",
                    "Multiple OPEN trades found for (symbol, agent_id, strategy)",
                    {"agent_id": agent_id, "symbol": symbol, "strategy": strategy, "count": len(matches)},
                )
            else:
                await self.logs.log(
                    agent_id=agent_id,
                    strategy=strategy,
                    symbol=symbol,
                    action="close",
                    status="error",
                    code="NO_OPEN_TRADE",
                    message="No matching open trade found",
                    details={"agent_id": agent_id, "symbol": symbol, "strategy": strategy},
                )
                return {"status": "error", "message": "No matching open trade found"}

        # Determine exit price deterministically
        exit_price = payload.exit_price
        if not exit_price:
            t = await self.db.agent_trades.find_one({"id": trade_id}, {"_id": 0})
            if t:
                exit_price = float(t.get("entry_price") or 0) or 0
        if not exit_price or exit_price <= 0:
            await self.logs.log(
                agent_id=agent_id,
                strategy=strategy,
                symbol=symbol,
                action="close",
                status="error",
                code="MISSING_PRICE",
                message="exit_price is required",
                details={},
            )
            return {"status": "error", "message": "exit_price is required"}

        result = await bridge.close_position(
            trade_id=trade_id,
            exit_price=exit_price,
            fees=0.0,
            reason=payload.reason,
        )

        if not result.get("success"):
            if result.get("blocked"):
                await self.logs.log(
                    agent_id=agent_id,
                    strategy=strategy,
                    symbol=symbol,
                    action="close",
                    status="blocked",
                    code="BLOCKED_EXECUTION",
                    message=result.get("reason", "Close blocked"),
                    details={"reason": result.get("reason")},
                )
                return blocked("BLOCKED_EXECUTION", result.get("reason", "Close blocked"), {"reason": result.get("reason")})

            await self.logs.log(
                agent_id=agent_id,
                strategy=strategy,
                symbol=symbol,
                action="close",
                status="error",
                code="EXECUTION_ERROR",
                message=result.get("reason", "Close failed"),
                details={"reason": result.get("reason")},
            )
            return {"status": "error", "message": result.get("reason", "Close failed")}

        await self.state.clear_open_trade_id(agent_id, symbol, strategy)

        await self.logs.log(
            agent_id=agent_id,
            strategy=strategy,
            symbol=symbol,
            action="close",
            status="success",
            code="SUCCESS",
            message="Close executed",
            details={"trade_id": trade_id, "pnl": result.get("pnl"), "pnl_pct": result.get("pnl_pct")},
        )

        return {"status": "ok", "trade_id": trade_id, "result": result}


_agent_trade_client: Optional[AgentTradeClient] = None


def get_agent_trade_client() -> Optional[AgentTradeClient]:
    return _agent_trade_client


def set_agent_trade_client(client: AgentTradeClient) -> None:
    global _agent_trade_client
    _agent_trade_client = client
