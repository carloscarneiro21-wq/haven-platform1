import { useEffect, useMemo, useState } from "react";
import { api } from "../App";
import KpiStrip from "@/components/console/KpiStrip";
import TradesTableCompact from "@/components/console/TradesTableCompact";
import SystemPanel from "@/components/console/SystemPanel";
import AgentsPanel from "@/components/console/AgentsPanel";
import ActivityLog from "@/components/console/ActivityLog";
import PnlLineChart from "@/components/console/PnlLineChart";
import { Skeleton } from "../components/ui/skeleton";

const Dashboard = () => {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [engineStatus, setEngineStatus] = useState(null);
  const [tradingStatus, setTradingStatus] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [dashResponse, engineResponse, tradingResponse] = await Promise.all([
          api.get("/dashboard"),
          api.get("/engine/status").catch(() => ({ data: null })),
          api.get("/trading/status").catch(() => ({ data: null })),
        ]);

        setDashboard(dashResponse.data);
        setEngineStatus(engineResponse.data);
        setTradingStatus(tradingResponse.data);
      } catch (_) {
        // calm fail
      } finally {
        setLoading(false);
      }
    };

    fetch();
    const id = setInterval(fetch, 15000);
    return () => clearInterval(id);
  }, []);

  const portfolio = useMemo(() => dashboard?.portfolio || {}, [dashboard?.portfolio]);
  const recentTrades = useMemo(() => dashboard?.recent_trades || [], [dashboard?.recent_trades]);
  const tradeLogs = useMemo(() => dashboard?.trade_logs || [], [dashboard?.trade_logs]);

  const fmtMoney = (v) => {
    const n = Number(v || 0);
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const kpis = useMemo(() => [
    {
      label: "Cumulative PnL",
      value: fmtMoney(portfolio.total_pnl),
      tone: portfolio.total_pnl > 0 ? "pos" : portfolio.total_pnl < 0 ? "neg" : "neutral",
    },
    {
      label: "Today PnL",
      value: fmtMoney(portfolio.daily_pnl),
      tone: portfolio.daily_pnl > 0 ? "pos" : portfolio.daily_pnl < 0 ? "neg" : "neutral",
    },
    { label: "Open Positions", value: String(portfolio.open_positions || 0), tone: "neutral" },
    { label: "Win Rate", value: `${(portfolio.win_rate || 0).toFixed(1)}%`, tone: "neutral" },
    { label: "Trades (24h)", value: String(portfolio.trades_24h || recentTrades.length || 0), tone: "neutral" },
  ], [portfolio, recentTrades.length]);

  const inferredAgents = useMemo(() => {
    const byKey = new Map();
    const now = Date.now();
    const twoHours = 2 * 60 * 60 * 1000;

    for (const t of recentTrades) {
      const key = `${t.agent_type || t.strategy || "agent"}`;
      const ts = t.executed_at ? new Date(t.executed_at).getTime() : 0;
      const prev = byKey.get(key);
      if (!prev || ts > prev.lastTs) {
        byKey.set(key, {
          key,
          name: String(t.agent_type || t.strategy || "AGENT").toUpperCase(),
          lastTs: ts,
          state: now - ts <= twoHours ? "ACTIVE" : "IDLE",
          lastAction: `${String(t.side || "").toUpperCase()} ${t.symbol}`.trim(),
        });
      }
    }

    return Array.from(byKey.values()).sort((a, b) => b.lastTs - a.lastTs);
  }, [recentTrades]);

  const activityItems = useMemo(() => {
    const items = [];
    for (const t of recentTrades.slice(0, 10)) {
      items.push({
        ts: t.executed_at ? new Date(t.executed_at).toLocaleTimeString() : "—",
        message: `Trade ${String(t.side || "").toUpperCase()} ${t.symbol} (PnL ${fmtMoney(t.pnl)})`,
      });
    }

    for (const l of tradeLogs.slice(0, 10)) {
      items.push({
        ts: l.ts ? new Date(l.ts).toLocaleTimeString() : "—",
        message: String(l.message || l.event || "Event"),
      });
    }

    return items.slice(0, 25);
  }, [recentTrades, tradeLogs]);

  const pnlSeries = useMemo(() => {
    let acc = 0;
    const out = [];
    const trades = [...recentTrades].reverse();
    trades.forEach((t, idx) => {
      acc += Number(t.pnl || 0);
      out.push({ x: String(idx + 1), y: acc });
    });
    return out;
  }, [recentTrades]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48 bg-zinc-800" />
        <div className="grid grid-cols-5 gap-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-20 bg-zinc-800" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-96 bg-zinc-800 col-span-2" />
          <Skeleton className="h-96 bg-zinc-800" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <KpiStrip kpis={kpis} />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 space-y-4">
          <TradesTableCompact trades={recentTrades} />
          <PnlLineChart data={pnlSeries} />
        </div>

        <div className="lg:col-span-2 space-y-4">
          <AgentsPanel agents={inferredAgents} />
          <SystemPanel engineStatus={engineStatus} tradingStatus={tradingStatus} />
          <ActivityLog items={activityItems} />
        </div>
      </div>

      <div className="text-xs text-[#5E6673]">
        PAPER / SIMULATION mode is clearly indicated in the top system bar and sidebar. Empty states are explicit.
      </div>
    </div>
  );
};

export default Dashboard;
