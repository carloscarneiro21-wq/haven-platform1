import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, ClipboardCopy, RefreshCw } from "lucide-react";

function CheckRow({ label, ok }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="text-sm text-[#EAECEF]">{label}</div>
      {ok ? (
        <div className="flex items-center gap-2 text-[#0ECB81]">
          <CheckCircle2 className="w-4 h-4" />
          <span className="text-xs font-mono">OK</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-[#F6465D]">
          <XCircle className="w-4 h-4" />
          <span className="text-xs font-mono">FAIL</span>
        </div>
      )}
    </div>
  );
}

function ModeBadge({ mode }) {
  const m = (mode || "paper").toLowerCase();
  const isLive = m === "binance_live";
  const isTestnet = m === "binance_testnet";

  if (isLive) return <Badge className="bg-red-500/20 text-red-300 border border-red-500/40">BINANCE_LIVE</Badge>;
  if (isTestnet) return <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] border border-[#F0B90B]/40">BINANCE_TESTNET</Badge>;
  return <Badge className="bg-[#F0B90B]/10 text-[#F0B90B] border border-[#F0B90B]/30">PAPER</Badge>;
}

export default function LiveReadinessModal({ open, onOpenChange }) {
  const [readiness, setReadiness] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastError, setLastError] = useState(null);

  const fetchReadiness = async () => {
    setLoading(true);
    try {
      const res = await api.get("/system/live_readiness");
      setReadiness(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Failed to load live readiness");
    } finally {
      setLoading(false);
    }
  };

  const fetchLastLiveErrorOptional = async () => {
    try {
      const rep = await api.get("/trades/report", {
        params: { window: "24h", mode: "paper", strategy: "ALL", agent_id: "ALL" },
      });
      const failed = rep?.data?.failed || [];
      const examples = failed.flatMap((f) => (f.examples || []).map((ex) => ({
        ...ex,
        reason_code: f.reason_code,
      })));

      const liveExamples = examples
        .filter((ex) => {
          const tm = ex?.details?.trading_mode;
          return tm === "binance_testnet" || tm === "binance_live";
        })
        .sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || "")));

      setLastError(liveExamples[0] || null);
    } catch (_) {
      // optional; ignore
      setLastError(null);
    }
  };

  useEffect(() => {
    if (open) {
      fetchReadiness();
      fetchLastLiveErrorOptional();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const checklist = useMemo(() => {
    if (!readiness) return [];
    return [
      { key: "keys_present", label: "keys_present", ok: !!readiness.keys_present },
      { key: "allowed_symbols_configured", label: "allowed_symbols_configured", ok: !!readiness.allowed_symbols_configured },
      { key: "limits_configured", label: "limits_configured", ok: !!readiness.limits_configured },
      { key: "kill_switch_ok", label: "kill_switch_ok", ok: !!readiness.kill_switch_ok },
      { key: "testnet_smoke_passed", label: "testnet_smoke_passed", ok: !!readiness.testnet_smoke_passed },
      { key: "ready_for_live", label: "ready_for_live", ok: !!readiness.ready_for_live },
    ];
  }, [readiness]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(readiness || {}, null, 2));
      toast.success("Readiness JSON copied");
    } catch (e) {
      toast.error("Failed to copy");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#0B0E11] border border-white/10 text-[#EAECEF] max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg text-[#EAECEF]">Live Readiness</DialogTitle>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#848E9C]">execution_mode</span>
            <ModeBadge mode={readiness?.current?.trading_mode} />
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="border-white/15 bg-transparent hover:bg-white/5"
              onClick={() => {
                fetchReadiness();
                fetchLastLiveErrorOptional();
              }}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>

            <Button
              variant="outline"
              className="border-white/15 bg-transparent hover:bg-white/5"
              onClick={handleCopy}
              disabled={!readiness}
            >
              <ClipboardCopy className="w-4 h-4 mr-2" />
              Copy readiness JSON
            </Button>
          </div>
        </div>

        <Separator className="bg-white/10" />

        <div>
          <div className="text-xs font-mono text-[#848E9C] uppercase tracking-wider">Checklist</div>
          <div className="mt-2 rounded-lg border border-white/10 bg-white/[0.03] px-4">
            {checklist.map((row) => (
              <CheckRow key={row.key} label={row.label} ok={row.ok} />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
            <div className="text-xs font-mono text-[#848E9C] uppercase tracking-wider">Current</div>
            <div className="mt-2 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[#848E9C]">execution_mode</span>
                <span className="font-mono">{readiness?.current?.trading_mode || "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#848E9C]">live_cex_enabled</span>
                <span className="font-mono">{String(!!readiness?.current?.live_cex_enabled)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#848E9C]">allowed_symbols</span>
                <span className="font-mono truncate max-w-[240px] text-right">
                  {(readiness?.current?.allowed_symbols || []).join(", ") || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#848E9C]">max_order_notional_usdt</span>
                <span className="font-mono">{readiness?.current?.max_order_notional_usdt ?? "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#848E9C]">daily_loss_limit_usdt</span>
                <span className="font-mono">{readiness?.current?.daily_loss_limit_usdt ?? "—"}</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
            <div className="text-xs font-mono text-[#848E9C] uppercase tracking-wider">Last live/testnet error (optional)</div>
            <div className="mt-2 text-sm">
              {!lastError ? (
                <div className="text-[#5E6673]">No recent live/testnet errors detected.</div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[#848E9C]">ts</span>
                    <span className="font-mono text-xs">{lastError.ts}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[#848E9C]">code</span>
                    <span className="font-mono">{lastError.code || lastError.reason_code || "—"}</span>
                  </div>
                  <div className="text-xs text-[#EAECEF] whitespace-pre-wrap break-words max-h-28 overflow-auto border border-white/10 rounded p-2 bg-black/20">
                    {lastError.message || "—"}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="text-xs text-[#5E6673]">
          {readiness?.withdrawals_disabled_warning ? readiness.withdrawals_disabled_warning : ""}
        </div>
      </DialogContent>
    </Dialog>
  );
}
