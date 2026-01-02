"""TradeExecutionMixin

A tiny mixin for MM/MOM agent classes to execute a single PAPER trade via
AgentTradeClient.

We avoid adding new abstractions in the orchestrator; this is a minimal shim
that lets existing intent-plan agents produce a trade.

Rules:
- open: checks positions + max-open + rate limit + kill switch
- close: uses persisted trade_id from state (fallbacks to resolving latest open)
"""

from typing import Any, Dict, Optional

from services.agent_trade_client import AgentOpenPayload, AgentClosePayload
from services.agent_trade_client import get_agent_trade_client


class TradeExecutionMixin:
    async def maybe_open_trade(
        self,
        *,
        agent_id: str,
        symbol: str,
        side: str,
        qty: float,
        entry_price: Optional[float],
        strategy: str,
        meta: Dict[str, Any],
    ):
        client = get_agent_trade_client()
        if not client:
            return {"status": "error", "message": "AgentTradeClient not available"}

        payload = AgentOpenPayload(
            symbol=symbol,
            side=side.upper(),
            qty=qty,
            entry_price=entry_price,
            strategy=strategy,
            agent_id=agent_id,
            meta=meta or {},
        )
        return await client.open_trade(payload)

    async def maybe_close_trade(
        self,
        *,
        agent_id: str,
        symbol: str,
        strategy: str,
        exit_price: Optional[float],
        reason: str,
        meta: Dict[str, Any],
    ):
        client = get_agent_trade_client()
        if not client:
            return {"status": "error", "message": "AgentTradeClient not available"}

        payload = AgentClosePayload(
            exit_price=exit_price,
            reason=reason,
            meta=meta or {},
        )
        return await client.close_trade(agent_id=agent_id, symbol=symbol, strategy=strategy, payload=payload)
