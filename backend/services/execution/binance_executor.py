"""Binance Spot MARKET executor.

Implements MARKET order execution for:
- BINANCE_TESTNET
- BINANCE_LIVE

NOTE: Hard safety checks should happen in ExecutionRouter and AgentTradeClient.
This executor assumes it's already allowed to execute.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from services.binance_spot_client import get_binance_client
from services.execution.router import TradeRequest, TradeResult

logger = logging.getLogger(__name__)


class BinanceMarketExecutor:
    def __init__(self, venue: str):
        self.venue = venue  # BINANCE_TESTNET|BINANCE_LIVE

    async def execute(self, request: TradeRequest) -> TradeResult:
        client = get_binance_client()

        result = TradeResult(
            request_id=request.request_id,
            mode=self.venue,
            symbol=request.symbol,
            side=request.side,
        )

        try:
            # Market orders only
            side = request.side.upper()

            # BUY uses quoteOrderQty (USDT notional). SELL uses quantity (base).
            if side == "BUY":
                # request.amount is interpreted as USDT notional for BUY
                resp = await client.place_market_order(
                    symbol=request.symbol,
                    side="BUY",
                    quote_order_qty=request.amount,
                )
            else:
                # request.amount is interpreted as base asset quantity for SELL
                resp = await client.place_market_order(
                    symbol=request.symbol,
                    side="SELL",
                    quantity=request.amount,
                )

            fills = resp.get("fills") or []
            executed_qty = float(resp.get("executedQty") or 0)
            quote_qty = float(resp.get("cummulativeQuoteQty") or 0)
            avg_price = (quote_qty / executed_qty) if executed_qty else 0

            # fees (commission) are reported per-fill in testnet/life; sum in quote asset when possible
            fees = 0.0
            for f in fills:
                try:
                    fees += float(f.get("commission") or 0)
                except Exception:
                    continue

            result.success = True
            result.status = "FILLED"
            result.fill_status = "FILLED"
            result.entry_price = avg_price
            result.executed_amount = executed_qty
            result.fees = fees

            result.venue = self.venue
            result.order_id = str(resp.get("orderId")) if resp.get("orderId") is not None else None
            result.executed_quote_qty = quote_qty
            result.avg_fill_price = avg_price

            result.metadata = {
                "venue": self.venue,
                "binance_order_id": resp.get("orderId"),
                "client_order_id": resp.get("clientOrderId"),
                "executedQty": resp.get("executedQty"),
                "cummulativeQuoteQty": resp.get("cummulativeQuoteQty"),
                "fills": fills,
            }

            return result

        except Exception as e:
            logger.exception(f"Binance order failed: {e}")
            result.success = False
            result.status = "REJECTED"
            result.fill_status = "REJECTED"

            # Include HTTP status when available (useful for geo-block / 451 diagnostics)
            if isinstance(e, httpx.HTTPStatusError):
                try:
                    body = (e.response.text or "")[:500]
                except Exception:
                    body = ""
                result.error_message = f"HTTP {e.response.status_code}: {body}".strip()
            else:
                result.error_message = str(e)

            return result
