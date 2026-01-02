import { useState, useEffect } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { 
  Activity, Clock, DollarSign, AlertTriangle, CheckCircle2, XCircle,
  Shield, Wifi, Zap, Eye, Bot, TrendingDown, TrendingUp, RefreshCw,
  AlertOctagon, Heart, Radio
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";

// Feed mode badge - NEVER shows UNKNOWN
const FeedModeBadge = ({ mode }) => {
  const config = {
    SYNTHETIC_SANDBOX: { color: 'bg-[#8B5CF6]/20 text-[#8B5CF6]', label: 'SANDBOX' },
    CEX_PAPER: { color: 'bg-[#F0B90B]/20 text-[#F0B90B]', label: 'CEX PAPER' },
    OFFLINE: { color: 'bg-zinc-700 text-zinc-400', label: 'OFFLINE' },
  };
  const { color, label } = config[mode] || config.OFFLINE;
  return <Badge className={color}>{label}</Badge>;
};

// Guardian status badge - uses SAFE/WARN/HALT
const GuardianBadge = ({ status }) => {
  const colors = {
    SAFE: 'status-running',
    OK: 'status-running',
    WARN: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    WARNING: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    HALT: 'bg-[#EF4444]/20 text-[#EF4444]',
    HALTED: 'bg-[#EF4444]/20 text-[#EF4444]',
    OFFLINE: 'bg-zinc-700 text-zinc-400',
  };
  return <Badge className={colors[status] || colors.OFFLINE}>{status || 'OFFLINE'}</Badge>;
};

const RiskStateBadge = ({ state }) => {
  const colors = {
    OK: 'status-running',
    WARNING: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    HALTED: 'bg-[#EF4444]/20 text-[#EF4444]',
    OFFLINE: 'bg-zinc-700 text-zinc-400',
  };
  // NEVER return UNKNOWN - fallback to OFFLINE
  return <Badge className={colors[state] || colors.OFFLINE}>{state || 'OFFLINE'}</Badge>;
};

const WatchdogBadge = ({ status }) => {
  const colors = {
    healthy: 'status-running',
    degraded: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    unhealthy: 'bg-[#EF4444]/20 text-[#EF4444]',
    halted: 'bg-[#EF4444]/20 text-[#EF4444]',
    recovering: 'bg-[#8B5CF6]/20 text-[#8B5CF6]',
  };
  return <Badge className={colors[status] || 'bg-zinc-700 text-zinc-400'}>{status?.toUpperCase()}</Badge>;
};

const Monitoring = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await api.get("/monitoring/status");
      setStatus(res.data);
      setLastUpdate(new Date());
    } catch (e) {
      console.error("Failed to fetch monitoring status:", e);
      // On failure, show OFFLINE state instead of UNKNOWN
      setStatus({
        feed: { mode: "OFFLINE", source: "offline", note: "Unable to fetch status" },
        scheduler: { scheduled_jobs: 0, last_run_at: null, note: "Unavailable" },
        risk: { guardian_status: "OFFLINE", weekly_drawdown_pct: 0, daily_pnl_pct: 0 },
        engine_running: false,
        engine_healthy: false,
        data_source: "offline",
        data_stale: true,
        risk_state: "OFFLINE",
        watchdog_status: "offline",
        watchdog_warnings: ["Unable to connect to monitoring service"],
        open_positions_count: 0,
        total_exposure: 0,
        daily_pnl: 0,
        daily_pnl_pct: 0,
        agents_total: 0,
        agents_running: 0,
        agents_in_error: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleEnterSafeMode = async () => {
    try {
      await api.post("/monitoring/safe-mode/enter", null, { params: { reason: "Manual trigger from UI" } });
      toast.success("Safe mode activated");
      fetchStatus();
    } catch (e) {
      toast.error("Failed to enter safe mode");
    }
  };

  const handleExitSafeMode = async () => {
    try {
      await api.post("/monitoring/safe-mode/exit");
      toast.success("Safe mode deactivated");
      fetchStatus();
    } catch (e) {
      toast.error("Failed to exit safe mode");
    }
  };

  const handleReconcile = async () => {
    try {
      const res = await api.post("/runtime/reconcile");
      toast.success(`Reconciliation complete. ${res.data.idempotency_keys_loaded} keys loaded.`);
      fetchStatus();
    } catch (e) {
      toast.error("Failed to reconcile");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-zinc-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase flex items-center gap-3">
            <Eye className="w-8 h-8 text-[#06B6D4]" />
            Monitoring Panel
          </h1>
          <p className="text-sm font-mono text-zinc-500 mt-1">
            24/7 System Health • Last update: {lastUpdate?.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <WatchdogBadge status={status?.watchdog_status} />
          <Button onClick={fetchStatus} variant="outline" className="btn-outline" size="sm">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Watchdog Warnings */}
      {status?.watchdog_warnings && status.watchdog_warnings.length > 0 && (
        <Card className="trading-card border-[#F59E0B]/50">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-[#F59E0B] flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm text-[#F59E0B] font-semibold">Watchdog Warnings</p>
                {status.watchdog_warnings.map((warning, idx) => (
                  <p key={idx} className="text-xs text-zinc-400">• {warning}</p>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Status Grid */}
      <div className="grid grid-cols-4 gap-4">
        {/* Engine Status */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Engine</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Running</span>
              {status?.engine_running ? (
                <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
              ) : (
                <XCircle className="w-4 h-4 text-[#EF4444]" />
              )}
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Healthy</span>
              {status?.engine_healthy ? (
                <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-[#F59E0B]" />
              )}
            </div>
            <div className="pt-2 border-t border-zinc-800">
              <p className="text-xs text-zinc-500">Last Tick</p>
              <p className="font-mono text-lg text-white">
                {status?.engine_tick_age_seconds?.toFixed(0) || '—'}s ago
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Data Feed */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Radio className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Data Feed</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Mode</span>
              <FeedModeBadge mode={status?.feed?.mode || 'OFFLINE'} />
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Source</span>
              <Badge className="bg-zinc-700 text-zinc-300">
                {(status?.feed?.source || status?.data_source || 'offline').toUpperCase()}
              </Badge>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Status</span>
              {status?.data_stale ? (
                <XCircle className="w-4 h-4 text-[#EF4444]" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
              )}
            </div>
            <div className="pt-2 border-t border-zinc-800">
              <p className="text-xs text-zinc-500">Freshness</p>
              <p className="font-mono text-lg text-white">
                {status?.data_freshness_seconds?.toFixed(0) || '—'}s
              </p>
              {status?.feed?.note && (
                <p className="text-xs text-zinc-500 mt-1">{status.feed.note}</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Risk State */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Guardian</span>
            </div>
            <div className="mb-3">
              <GuardianBadge status={status?.risk?.guardian_status || status?.risk_state || 'OFFLINE'} />
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Kill Switch</span>
              {status?.kill_switch_active ? (
                <Badge className="bg-[#EF4444]/20 text-[#EF4444]">ACTIVE</Badge>
              ) : (
                <Badge className="bg-zinc-700 text-zinc-400">OFF</Badge>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-400">Safe Mode</span>
              {status?.safe_mode ? (
                <Badge className="bg-[#F59E0B]/20 text-[#F59E0B]">ON</Badge>
              ) : (
                <Badge className="bg-zinc-700 text-zinc-400">OFF</Badge>
              )}
            </div>
            {status?.risk?.note && (
              <p className="text-xs text-zinc-500 mt-2 pt-2 border-t border-zinc-800">{status.risk.note}</p>
            )}
          </CardContent>
        </Card>

        {/* Agents */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Bot className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Agents</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">Running</span>
              <span className="font-mono text-white">{status?.agents_running || 0} / {status?.agents_total || 0}</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-zinc-400">In Error</span>
              <span className={`font-mono ${status?.agents_in_error > 0 ? 'text-[#EF4444]' : 'text-white'}`}>
                {status?.agents_in_error || 0}
              </span>
            </div>
            <div className="pt-2 border-t border-zinc-800">
              <p className="text-xs text-zinc-500">Cycles</p>
              <p className="font-mono text-lg text-white">{status?.cycle_count || 0}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Scheduler & Risk Details */}
      <div className="grid grid-cols-2 gap-4">
        {/* Scheduler */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Clock className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Scheduler</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Scheduled Jobs</p>
                <p className="font-mono text-2xl text-white">{status?.scheduler?.scheduled_jobs || 0}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Last Run</p>
                <p className="font-mono text-sm text-zinc-400">
                  {status?.scheduler?.last_run_at 
                    ? new Date(status.scheduler.last_run_at).toLocaleTimeString() 
                    : 'Never'}
                </p>
              </div>
            </div>
            {status?.scheduler?.note && (
              <p className="text-xs text-zinc-500 mt-2 pt-2 border-t border-zinc-800">{status.scheduler.note}</p>
            )}
          </CardContent>
        </Card>

        {/* Risk Details */}
        <Card className="trading-card">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendingDown className="w-4 h-4 text-zinc-500" />
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Risk Metrics</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Weekly Drawdown</p>
                <p className={`font-mono text-2xl ${(status?.risk?.weekly_drawdown_pct || 0) > 5 ? 'text-[#F59E0B]' : 'text-white'}`}>
                  {(status?.risk?.weekly_drawdown_pct || status?.daily_drawdown_pct || 0).toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Daily P&L</p>
                <p className={`font-mono text-2xl ${(status?.risk?.daily_pnl_pct || 0) >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>
                  {(status?.risk?.daily_pnl_pct || status?.daily_pnl_pct || 0).toFixed(2)}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* P&L and Positions */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="trading-card">
          <CardHeader className="trading-card-header">
            <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <DollarSign className="w-4 h-4" />
              Daily P&L
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-4">
              {(status?.daily_pnl || 0) >= 0 ? (
                <TrendingUp className="w-6 h-6 text-[#10B981]" />
              ) : (
                <TrendingDown className="w-6 h-6 text-[#EF4444]" />
              )}
              <span className={`font-mono text-2xl ${(status?.daily_pnl || 0) >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>
                ${status?.daily_pnl?.toFixed(2) || '0.00'}
              </span>
              <span className={`text-sm ${(status?.daily_pnl_pct || 0) >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>
                ({status?.daily_pnl_pct?.toFixed(2) || '0.00'}%)
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Drawdown</p>
                <p className={`font-mono text-lg ${(status?.daily_drawdown_pct || 0) > 5 ? 'text-[#F59E0B]' : 'text-white'}`}>
                  {status?.daily_drawdown_pct?.toFixed(2) || '0.00'}%
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Consecutive Losses</p>
                <p className={`font-mono text-lg ${(status?.consecutive_losses || 0) >= 3 ? 'text-[#F59E0B]' : 'text-white'}`}>
                  {status?.consecutive_losses || 0}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="trading-card">
          <CardHeader className="trading-card-header">
            <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <Zap className="w-4 h-4" />
              Positions & Exposure
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Open Positions</p>
                <p className="font-mono text-2xl text-white">{status?.open_positions_count || 0}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Total Exposure</p>
                <p className="font-mono text-2xl text-white">${status?.total_exposure?.toFixed(0) || '0'}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="trading-card">
          <CardHeader className="trading-card-header">
            <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <Heart className="w-4 h-4" />
              Alerts
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Sent Today</p>
                <p className="font-mono text-2xl text-white">{status?.alerts_sent_today || 0}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Last Sent</p>
                <p className="font-mono text-sm text-zinc-400">
                  {status?.alerts_last_sent_at ? new Date(status.alerts_last_sent_at).toLocaleTimeString() : 'Never'}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 mt-4">
              <div>
                <p className="text-xs text-zinc-500">Errors</p>
                <p className={`font-mono text-lg ${(status?.error_count || 0) > 0 ? 'text-[#F59E0B]' : 'text-white'}`}>
                  {status?.error_count || 0}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Recovery Attempts</p>
                <p className={`font-mono text-lg ${(status?.recovery_attempts || 0) > 0 ? 'text-[#8B5CF6]' : 'text-white'}`}>
                  {status?.recovery_attempts || 0}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Safe Mode Info */}
      {status?.safe_mode && (
        <Card className="trading-card border-[#F59E0B]/50">
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertOctagon className="w-6 h-6 text-[#F59E0B]" />
              <div>
                <p className="text-sm text-[#F59E0B] font-semibold">Safe Mode Active</p>
                <p className="text-xs text-zinc-400">{status.safe_mode_reason || 'Managing exits only, no new entries'}</p>
              </div>
            </div>
            <Button onClick={handleExitSafeMode} variant="outline" className="btn-outline">
              Exit Safe Mode
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <Card className="trading-card">
        <CardHeader className="trading-card-header">
          <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            <Shield className="w-4 h-4" />
            Manual Controls
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="flex gap-4">
            {!status?.safe_mode && (
              <Button onClick={handleEnterSafeMode} variant="outline" className="btn-outline">
                <AlertTriangle className="w-4 h-4 mr-2" />
                Enter Safe Mode
              </Button>
            )}
            <Button onClick={handleReconcile} variant="outline" className="btn-outline">
              <RefreshCw className="w-4 h-4 mr-2" />
              Force Reconciliation
            </Button>
          </div>
          <p className="text-xs text-zinc-500 mt-3">
            Safe Mode: Blocks new entries, manages exits only. Reconciliation: Reloads state, checks for duplicates.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Monitoring;
