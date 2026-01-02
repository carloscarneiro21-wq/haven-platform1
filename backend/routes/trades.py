"""Trades API Routes - Real-time trade monitoring endpoints.

Endpoints:
- POST /api/trades/paper - Create a paper trade
- GET /api/trades - List trades with filters
- GET /api/trades/summary - Trade statistics
- GET /api/market/candles - OHLC candles for charts
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from services.trades_report import TradesReportService
import httpx

from uuid import uuid4

from services.trades_service import get_trades_service, TradesService, AgentTrade

from server import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trades"])

# Dependency to get trades service
async def get_service() -> TradesService:
    service = get_trades_service()
    if not service:
        raise HTTPException(status_code=503, detail="Trades service not available")
    return service


class CreatePaperTradeRequest(BaseModel):
    """Request to create a paper trade."""
    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    side: str = Field(..., description="BUY or SELL")
    qty: float = Field(..., gt=0, description="Quantity")
    entry_price: float = Field(..., gt=0, description="Entry price")
    exit_price: Optional[float] = Field(None, description="Exit price (for closed trades)")
    strategy: str = Field("MANUAL", description="Strategy (MM, MOM, SNIPER, DEX, MANUAL)")
    agent_id: str = Field("manual_user", description="Agent ID")
    agent_name: str = Field("Manual Trade", description="Agent name")
    fees: float = Field(0.0, ge=0, description="Trading fees")
    meta: dict = Field(default_factory=dict, description="Additional metadata")


class ClosePaperTradeRequest(BaseModel):
    """Request to close a paper trade."""
    exit_price: float = Field(..., gt=0, description="Exit price")
    fees: float = Field(0.0, ge=0, description="Additional fees")


class TradeResponse(BaseModel):
    id: str
    ts: str
    agent_id: str
    agent_name: str
    strategy: str
    mode: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: Optional[float]
    status: str
    fees: float
    slippage: float
    pnl: float
    pnl_pct: float
    meta: dict


@router.post("/trades/paper")
async def create_paper_trade(
    request: CreatePaperTradeRequest,
    service: TradesService = Depends(get_service),
):
    """Create a new paper trade.
    
    Creates a simulated trade record in the database.
    If exit_price is provided, the trade is created as CLOSED with PnL calculated.
    Otherwise, it's created as OPEN.
    """
    # Validate side
    side = request.side.upper()
    if side not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Side must be BUY or SELL")
    
    # Normalize symbol
    symbol = request.symbol.upper()
    if "/" not in symbol:
        if symbol.endswith("USDT"):
            symbol = symbol[:-4] + "/USDT"
        elif symbol.endswith("USD"):
            symbol = symbol[:-3] + "/USD"
    
    # Calculate PnL if exit price provided
    pnl = 0.0
    pnl_pct = 0.0
    status = "OPEN"
    
    if request.exit_price:
        status = "CLOSED"
        if side == "BUY":
            pnl = (request.exit_price - request.entry_price) * request.qty - request.fees
        else:
            pnl = (request.entry_price - request.exit_price) * request.qty - request.fees
        
        entry_value = request.entry_price * request.qty
        pnl_pct = (pnl / entry_value) * 100 if entry_value > 0 else 0
    
    # Create trade
    trade = AgentTrade(
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        strategy=request.strategy.upper(),
        mode="paper",
        symbol=symbol,
        side=side,
        qty=request.qty,
        entry_price=request.entry_price,
        exit_price=request.exit_price,
        status=status,
        fees=request.fees,
        slippage=0.0,
        pnl=pnl,
        pnl_pct=pnl_pct,
        meta=request.meta,
    )
    
    result = await service.create_trade(trade)
    
    logger.info(f"Paper trade created: {result.id} - {symbol} {side} {request.qty} @ {request.entry_price}")
    
    return {
        "success": True,
        "trade": result.model_dump(),
        "message": f"Paper trade created: {side} {request.qty} {symbol} @ {request.entry_price}",
    }


class AgentExecutionRequest(BaseModel):
    """Request for agent to open a position."""
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_name: str = Field(..., description="Human-readable agent name")
    strategy: str = Field(..., description="Strategy (MM, MOM, SNIPER, DEX, etc.)")
    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    side: str = Field(..., description="BUY or SELL")
    qty: float = Field(..., gt=0, description="Quantity")
    price: Optional[float] = Field(None, description="Target price (uses market if not provided)")
    reason: str = Field("", description="Reason for the trade")
    meta: dict = Field(default_factory=dict, description="Additional metadata")


class AgentCloseRequest(BaseModel):
    """Request for agent to close a position."""
    trade_id: Optional[str] = Field(None, description="Specific trade ID to close")
    agent_id: Optional[str] = Field(None, description="Agent ID (if trade_id not provided)")
    strategy: Optional[str] = Field(None, description="Strategy (if trade_id not provided)")
    symbol: Optional[str] = Field(None, description="Symbol (if trade_id not provided)")
    exit_price: float = Field(..., gt=0, description="Exit price")
    fees: float = Field(0.0, ge=0, description="Additional closing fees")
    reason: str = Field("", description="Reason for closing")


@router.post("/agent/execute")
async def agent_execute(
    request: AgentExecutionRequest,
    user=Depends(require_auth),
):
    """Agent opens a new position through ExecutionRouter.
    
    This endpoint:
    1. Validates against kill switch and trading limits
    2. Simulates execution (fees, slippage, latency)
    3. Creates trade in database with WS event
    4. Returns trade_id for later close operation
    
    Use for automated agent trading in PAPER mode.
    """
    from services.execution.agent_bridge import get_agent_bridge
    
    bridge = get_agent_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Agent execution bridge not available")
    
    result = await bridge.open_position(
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        strategy=request.strategy,
        symbol=request.symbol,
        side=request.side,
        qty=request.qty,
        price=request.price,
        reason=request.reason,
        metadata=request.meta,
    )
    
    if not result["success"]:
        if result.get("blocked"):
            raise HTTPException(status_code=403, detail=result.get("reason", "Execution blocked"))
        raise HTTPException(status_code=400, detail=result.get("reason", "Execution failed"))
    
    return result



# ---------------------------------------------------------------------------
# Backwards-compatible Agent Trade endpoints (preferred by PRD)
# ---------------------------------------------------------------------------

@router.post("/agent/trade/open")
async def agent_trade_open(
    request: AgentExecutionRequest,
    user=Depends(require_auth),
):
    """Alias for POST /api/agent/execute.

    Kept for backwards compatibility with agent integrations that expect:
    POST /api/agent/trade/open
    """
    return await agent_execute(request)


@router.post("/agent/close")
async def agent_close(
    request: AgentCloseRequest,
    user=Depends(require_auth),
):
    """Agent closes an open position.
    
    Provide either:
    - trade_id: Direct reference to the trade to close
    - agent_id + strategy + symbol: Will find the last OPEN trade matching
    
    Returns PnL and trade details.
    """
    from services.execution.agent_bridge import get_agent_bridge
    
    bridge = get_agent_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Agent execution bridge not available")
    
    result = await bridge.close_position(
        trade_id=request.trade_id,
        agent_id=request.agent_id,
        strategy=request.strategy,
        symbol=request.symbol,
        exit_price=request.exit_price,
        fees=request.fees,
        reason=request.reason,
    )
    
    if not result["success"]:
        if result.get("blocked"):
            raise HTTPException(status_code=403, detail=result.get("reason", "Close blocked"))
        raise HTTPException(status_code=400, detail=result.get("reason", "Close failed"))
    
    return result



@router.post("/agent/trade/{trade_id}/close")
async def agent_trade_close_by_id(
    trade_id: str,
    request: ClosePaperTradeRequest,
    user=Depends(require_auth),
):
    """Alias for closing a trade by ID.

    Endpoint:
      POST /api/agent/trade/{trade_id}/close

    Body:
      {"exit_price": 123.45, "fees": 0.0}
    """
    from services.execution.agent_bridge import get_agent_bridge

    bridge = get_agent_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Agent execution bridge not available")

    result = await bridge.close_position(
        trade_id=trade_id,
        exit_price=request.exit_price,
        fees=request.fees,
        reason="",
    )

    if not result["success"]:
        if result.get("blocked"):
            raise HTTPException(status_code=403, detail=result.get("reason", "Close blocked"))
        raise HTTPException(status_code=400, detail=result.get("reason", "Close failed"))

    return result


@router.get("/agent/positions")
async def agent_positions(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    user=Depends(require_auth),
):
    """Get all open positions for agents."""
    from services.execution.agent_bridge import get_agent_bridge
    
    bridge = get_agent_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Agent execution bridge not available")
    
    positions = await bridge.get_open_positions(agent_id=agent_id)
    return {
        "positions": positions,
        "count": len(positions),
    }


@router.post("/trades/{trade_id}/close")
async def close_paper_trade(
    trade_id: str,
    request: ClosePaperTradeRequest,
    service: TradesService = Depends(get_service),
):
    """Close an open paper trade with exit price."""
    result = await service.close_trade(
        trade_id=trade_id,
        exit_price=request.exit_price,
        fees=request.fees,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    return {
        "success": True,
        "trade": result,
        "message": f"Trade closed at {request.exit_price}",
    }


@router.get("/trades")
async def get_trades(
    from_ts: Optional[str] = Query(None, description="Start timestamp (ISO format)"),
    to_ts: Optional[str] = Query(None, description="End timestamp (ISO format)"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy: Optional[str] = Query(None, description="Filter by strategy (MM, MOM, SNIPER, DEX)"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, FILLED, PARTIAL, REJECTED, CLOSED)"),
    mode: Optional[str] = Query(None, description="Filter by mode (paper, live)"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of trades to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    service: TradesService = Depends(get_service),
):
    """Get trades with optional filters.
    
    Default: Returns last 200 trades sorted by timestamp descending.
    """
    # Parse timestamps
    from_datetime = None
    to_datetime = None
    
    if from_ts:
        try:
            from_datetime = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_ts format")
    
    if to_ts:
        try:
            to_datetime = datetime.fromisoformat(to_ts.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_ts format")
    
    trades = await service.get_trades(
        from_ts=from_datetime,
        to_ts=to_datetime,
        agent_id=agent_id,
        symbol=symbol,
        strategy=strategy,
        status=status,
        mode=mode,
        limit=limit,
        offset=offset,
    )
    
    return {
        "trades": trades,
        "count": len(trades),
        "limit": limit,
        "offset": offset,
        "has_more": len(trades) == limit,
    }


@router.get("/trades/summary")
async def get_trades_summary(
    window: str = Query("24h", description="Time window (1h, 24h, 7d)"),
    group_by: str = Query("agent", description="Group by (agent, symbol)"),
    mode: Optional[str] = Query(None, description="Filter by mode (paper, live)"),
    service: TradesService = Depends(get_service),
):
    """Get trade summary statistics.
    
    Returns:
    - Cumulative PnL
    - Win rate
    - Average trade
    - Exposure by symbol
    - Stats grouped by agent or symbol
    """
    if window not in ["1h", "24h", "7d"]:
        raise HTTPException(status_code=400, detail="Invalid window. Use: 1h, 24h, 7d")
    
    if group_by not in ["agent", "symbol"]:
        raise HTTPException(status_code=400, detail="Invalid group_by. Use: agent, symbol")
    
    summary = await service.get_summary(
        window=window,
        group_by=group_by,
        mode=mode,
    )
    
    return summary


@router.get("/trades/report")
async def get_trades_report(
    window: str = Query("24h", description="Time window (1h, 24h, 7d, 30d)"),
    mode: str = Query("paper", description="Mode (paper, live)"),
    strategy: str = Query("ALL", description="Strategy filter: ALL|MM|MOM|SNIPER|MANUAL"),
    agent_id: str = Query("ALL", description="Agent filter: ALL|<agent_id>"),
    service: TradesService = Depends(get_service),
):
    """Generate a daily/period trade report.

    Notes:
    - Does NOT require candles.
    - Uses agent_execution_logs for 'failed' section, but works if logs are empty.
    - Normalizes strategy and agent_id in-memory for consistent filtering.
    """
    if window not in ["1h", "24h", "7d", "30d"]:
        raise HTTPException(status_code=400, detail="Invalid window. Use: 1h, 24h, 7d, 30d")

    if mode not in ["paper", "live"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Use: paper, live")

    if strategy not in ["ALL", "MM", "MOM", "SNIPER", "MANUAL"]:
        raise HTTPException(status_code=400, detail="Invalid strategy. Use: ALL, MM, MOM, SNIPER, MANUAL")

    # IMPORTANT: agent_id=ALL is a sentinel, not a literal
    report_service = TradesReportService(db=service.db)
    report = await report_service.get_report(
        mode=mode,
        window=window,
        strategy=strategy,
        agent_id=agent_id,
    )
    return report


@router.get("/market/price")
async def get_market_price(
    symbol: str = Query(..., description="Trading symbol (e.g. BTCUSDT)"),
):
    """Get latest spot price from Binance /api/v3/ticker/price."""
    try:
        from services.binance_spot_client import get_binance_client

        client = get_binance_client()
        data = await client.get_price(symbol=symbol)
        return {
            "symbol": data.get("symbol"),
            "price": float(data.get("price")),
            "feed_status": client.get_feed_status().__dict__,
        }
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Feed OFFLINE")


@router.get("/market/exchangeInfo")
async def get_market_exchange_info(
    symbol: Optional[str] = Query(None, description="Optional symbol (e.g. BTCUSDT)"),
):
    """Get Binance exchangeInfo (filters LOT_SIZE/MIN_NOTIONAL, etc.)."""
    try:
        from services.binance_spot_client import get_binance_client

        client = get_binance_client()
        data = await client.get_exchange_info(symbol=symbol.upper() if symbol else None)
        return {
            "data": data,
            "feed_status": client.get_feed_status().__dict__,
        }
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Feed OFFLINE")



@router.get("/market/candles")
async def get_market_candles(
    symbol: str = Query(..., description="Trading symbol (e.g. BTCUSDT)"),
    interval: str = Query("1m", description="Time interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(500, description="Number of candles to fetch"),
):
    """Get OHLCV candlestick data for charts.

    Uses Binance Spot REST /api/v3/klines.
    """
    interval_map = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}
    if interval not in interval_map:
        raise HTTPException(status_code=400, detail="Invalid interval")

    try:
        from services.binance_spot_client import get_binance_client

        client = get_binance_client()
        raw = await client.get_klines(symbol=symbol, interval=interval, limit=limit)

        candles = []
        for k in raw:
            candles.append({
                "t": int(k[0]),
                "o": float(k[1]),
                "h": float(k[2]),
                "l": float(k[3]),
                "c": float(k[4]),
                "v": float(k[5]),
            })

        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "candles": candles,
            "count": len(candles),
            "feed_status": client.get_feed_status().__dict__,
        }

    except httpx.HTTPError:
        # Never return UNKNOWN
        raise HTTPException(status_code=503, detail="Feed OFFLINE")
    except Exception as e:
        logger.error(f"Error fetching candles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch candles")


@router.get("/trades/metrics")
async def get_trades_metrics(
    service: TradesService = Depends(get_service),
):
    """Get current trading metrics for dashboard.
    
    Returns real-time metrics including:
    - Cumulative PnL
    - PnL by agent
    - Exposure by symbol
    - Trade counts
    """
    metrics = await service.get_metrics()
    return metrics
