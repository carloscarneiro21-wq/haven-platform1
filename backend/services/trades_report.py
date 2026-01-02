"""Trades Report Service

Generates a human-readable daily/period report using:
- agent_trades (paper trades)
- agent_execution_logs (blocked/error/success attempts)

This service is designed to work even if execution logs are empty.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


_ALLOWED_STRATEGIES = {"MM", "MOM", "SNIPER", "MANUAL"}


def normalize_strategy(value: Optional[str]) -> str:
    v = (value or "MANUAL").strip().upper()
    if v in _ALLOWED_STRATEGIES:
        return v
    if v in {"DEX", "GRID", "DCA", "TREND", "BREAKOUT", "MEAN_REVERSION"}:
        return "MANUAL"
    return "MANUAL"


def normalize_agent_id(value: Optional[str]) -> str:
    v = (value or "").strip()
    return v if v else "manual"


def parse_window(window: str) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if window == "24h":
        return now - timedelta(hours=24), now
    if window == "7d":
        return now - timedelta(days=7), now
    if window == "30d":
        return now - timedelta(days=30), now
    if window == "1h":
        return now - timedelta(hours=1), now
    # default
    return now - timedelta(hours=24), now


def safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def bps_from_slippage(slippage: Any) -> Optional[float]:
    s = safe_float(slippage)
    if s is None:
        return None
    # slippage is stored as percent (e.g. 0.01 means 0.01%)
    return s * 100.0


class TradesReportService:
    def __init__(self, db):
        self.db = db

    async def get_report(
        self,
        *,
        mode: str,
        window: str,
        strategy: str,
        agent_id: str,
    ) -> Dict[str, Any]:
        from_ts, to_ts = parse_window(window)

        # Trades query
        tq: Dict[str, Any] = {"ts": {"$gte": from_ts.isoformat(), "$lte": to_ts.isoformat()}}
        if mode:
            tq["mode"] = mode

        if strategy and strategy != "ALL":
            tq["strategy"] = strategy
        if agent_id and agent_id != "ALL":
            tq["agent_id"] = agent_id

        trades: List[Dict[str, Any]] = await self.db.agent_trades.find(tq, {"_id": 0}).to_list(2000)

        # Normalize trades (strategy, agent_id)
        for t in trades:
            t["strategy"] = normalize_strategy(t.get("strategy"))
            t["agent_id"] = normalize_agent_id(t.get("agent_id"))

        # If normalization changed values, filters should apply on normalized values.
        # We re-apply filters in-memory to keep behavior consistent without rewriting stored data.
        if strategy and strategy != "ALL":
            trades = [t for t in trades if normalize_strategy(t.get("strategy")) == strategy]
        if agent_id and agent_id != "ALL":
            trades = [t for t in trades if normalize_agent_id(t.get("agent_id")) == agent_id]

        total = len(trades)
        buys = sum(1 for t in trades if (t.get("side") or "").upper() == "BUY")
        sells = sum(1 for t in trades if (t.get("side") or "").upper() == "SELL")
        open_count = sum(1 for t in trades if (t.get("status") or "").upper() == "OPEN")
        closed_trades = [t for t in trades if (t.get("status") or "").upper() == "CLOSED"]
        closed_count = len(closed_trades)
        wins = sum(1 for t in closed_trades if (safe_float(t.get("pnl")) or 0) > 0)
        losses = sum(1 for t in closed_trades if (safe_float(t.get("pnl")) or 0) < 0)

        net_pnl = sum((safe_float(t.get("pnl")) or 0) for t in closed_trades)
        avg_per_trade = (net_pnl / closed_count) if closed_count else 0

        best_trade = None
        worst_trade = None
        if closed_trades:
            best_trade = max(closed_trades, key=lambda t: safe_float(t.get("pnl")) or 0)
            worst_trade = min(closed_trades, key=lambda t: safe_float(t.get("pnl")) or 0)

        # Execution quality
        hold_times: List[float] = []
        slippages: List[float] = []
        for t in closed_trades:
            try:
                opened = datetime.fromisoformat((t.get("ts") or "").replace("Z", "+00:00"))
                closed = datetime.fromisoformat((t.get("closed_at") or "").replace("Z", "+00:00"))
                hold_times.append(max(0.0, (closed - opened).total_seconds()))
            except Exception:
                pass
            bps = bps_from_slippage(t.get("slippage"))
            if bps is not None:
                slippages.append(bps)

        avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0
        avg_slippage_bps = sum(slippages) / len(slippages) if slippages else None

        # Worked well heuristics (must work even without logs)
        worked_well: List[Dict[str, Any]] = []
        if wins > 0:
            top_win_ids = [t.get("id") for t in sorted(closed_trades, key=lambda x: safe_float(x.get("pnl")) or 0, reverse=True)[:5]]
            worked_well.append({
                "title": "Profitable closes",
                "evidence": f"{wins} winning trades out of {closed_count} closed trades",
                "trades": [i for i in top_win_ids if i],
            })
        if closed_count > 0 and net_pnl > 0:
            worked_well.append({
                "title": "Positive net PnL",
                "evidence": f"Net PnL is positive over the window: {net_pnl:.2f}",
                "trades": [best_trade.get("id")] if best_trade else [],
            })
        if avg_slippage_bps is not None and avg_slippage_bps <= 5:
            worked_well.append({
                "title": "Low slippage execution",
                "evidence": f"Average slippage ~{avg_slippage_bps:.2f} bps",
                "trades": [],
            })
        if not worked_well and total > 0:
            worked_well.append({
                "title": "Trades executed",
                "evidence": f"{total} trades recorded in the period",
                "trades": [t.get("id") for t in trades[:5] if t.get("id")],
            })

        # Failures from logs (fallback: may be empty)
        failed: List[Dict[str, Any]] = []
        lq: Dict[str, Any] = {"ts": {"$gte": from_ts.isoformat(), "$lte": to_ts.isoformat()}}
        if strategy and strategy != "ALL":
            lq["strategy"] = strategy
        if agent_id and agent_id != "ALL":
            lq["agent_id"] = agent_id

        logs = await self.db.agent_execution_logs.find(lq, {"_id": 0}).to_list(2000)
        # Normalize logs (so filtering/aggregation is consistent)
        for log_item in logs:
            log_item["strategy"] = normalize_strategy(log_item.get("strategy"))
            log_item["agent_id"] = normalize_agent_id(log_item.get("agent_id"))

        if strategy and strategy != "ALL":
            logs = [log_item for log_item in logs if log_item.get("strategy") == strategy]
        if agent_id and agent_id != "ALL":
            logs = [log_item for log_item in logs if log_item.get("agent_id") == agent_id]

        bad_logs = [log_item for log_item in logs if log_item.get("status") in ["blocked", "error"]]
        by_code: Dict[str, List[Dict[str, Any]]] = {}
        for log_item in bad_logs:
            code = (log_item.get("code") or "OTHER").upper()
            by_code.setdefault(code, []).append(log_item)

        for code, items in sorted(by_code.items(), key=lambda kv: len(kv[1]), reverse=True):
            # Most recent first
            items = sorted(items, key=lambda i: i.get("ts") or "", reverse=True)
            reason_code = code
            allowed_reason_codes = {
                "BLOCKED_RATE_LIMIT",
                "BLOCKED_ALREADY_OPEN",
                "BLOCKED_KILL_SWITCH",
                "BLOCKED_MAX_OPEN",
                "MISSING_PRICE",
                "WS_DISCONNECTED",
                "BINANCE_OFFLINE",
                "BINANCE_UNAVAILABLE",
                "BINANCE_ERROR",
                "VALIDATION_ERROR",
                "OTHER",
            }
            if reason_code not in allowed_reason_codes:
                reason_code = "OTHER"

            examples = [
                {
                    "ts": i.get("ts"),
                    "agent_id": i.get("agent_id"),
                    "strategy": i.get("strategy"),
                    "symbol": i.get("symbol"),
                    "action": i.get("action"),
                    "code": i.get("code"),
                    "message": i.get("message"),
                    "details": i.get("details", {}),
                }
                for i in items[:3]
            ]
            failed.append({
                "title": f"{reason_code}",
                "reason_code": reason_code,
                "count": len(items),
                "evidence": items[0].get("message") if items else "",
                "examples": examples,
            })

        # Recommendations
        recommendations: List[Dict[str, Any]] = []
        code_counts = {f.get("reason_code"): f.get("count", 0) for f in failed}

        if code_counts.get("BLOCKED_KILL_SWITCH"):
            recommendations.append({
                "priority": "P0",
                "action": "Kill switch is active or has been triggered recently — review the reason and only resume agents after mitigation.",
                "expected_impact": "Prevents unintended execution and clarifies incident response.",
            })
        if code_counts.get("BLOCKED_ALREADY_OPEN") or code_counts.get("BLOCKED_MAX_OPEN"):
            recommendations.append({
                "priority": "P0",
                "action": "Agents are attempting to open positions while one is already OPEN — verify close conditions and ensure signals don’t spam the same symbol.",
                "expected_impact": "Reduces duplicate attempts and improves signal hygiene.",
            })
        if code_counts.get("BLOCKED_RATE_LIMIT"):
            recommendations.append({
                "priority": "P1",
                "action": "Open rate limit is being hit — reduce signal frequency or increase the minimum interval between opens per agent.",
                "expected_impact": "Avoids missed opportunities due to throttling.",
            })

        win_rate = (wins / closed_count * 100) if closed_count else 0
        if closed_count >= 5 and win_rate < 40:
            recommendations.append({
                "priority": "P1",
                "action": "Win rate is low — review entry/exit rules, risk sizing, and symbol selection.",
                "expected_impact": "Improves profitability and reduces drawdown.",
            })

        if not recommendations and total > 0:
            recommendations.append({
                "priority": "P2",
                "action": "No major blockers detected — continue monitoring and consider expanding the window for more signal confidence.",
                "expected_impact": "Improves analysis confidence over a larger sample.",
            })

        return {
            "window": window,
            "mode": mode,
            "counts": {
                "total": total,
                "buys": buys,
                "sells": sells,
                "open": open_count,
                "closed": closed_count,
                "wins": wins,
                "losses": losses,
            },
            "pnl": {
                "net": net_pnl,
                "avg_per_trade": avg_per_trade,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
            },
            "execution_quality": {
                "avg_hold_time_sec": avg_hold,
                "avg_slippage_bps": avg_slippage_bps,
                "avg_mfe": None,
                "avg_mae": None,
            },
            "worked_well": worked_well,
            "failed": failed,
            "recommendations": recommendations,
        }
