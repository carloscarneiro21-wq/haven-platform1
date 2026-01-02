import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/App";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";

export default function LiveModeBanner({ onOpenLiveReadiness }) {
  const [status, setStatus] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get("/trading/status");
      setStatus(res.data);
    } catch (_) {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      fetchStatus();
    }, 0);
    const interval = setInterval(fetchStatus, 30000);
    return () => {
      clearTimeout(t);
      clearInterval(interval);
    };
  }, [fetchStatus]);

  const banner = useMemo(() => {
    const mode = String(status?.trading_mode || "paper").toLowerCase();
    const liveCexEnabled = !!status?.live_cex_enabled;

    // Misconfig: PAPER + live_cex_enabled=true
    if (mode === "paper" && liveCexEnabled) {
      return {
        variant: "warning",
        title: "LIVE ENABLED (PAPER) ⚠️",
        subtitle: "Config inconsistente: não está a executar live, mas o live_cex_enabled=true aumenta risco se alguém trocar o mode.",
      };
    }

    if (mode === "binance_testnet") {
      return {
        variant: "testnet",
        title: "TESTNET MODE",
        subtitle: "Execução real no Binance Testnet (MARKET orders).",
      };
    }

    if (mode === "binance_live") {
      return {
        variant: "live",
        title: "LIVE MODE",
        subtitle: "Execução real no Binance LIVE (fundos reais em risco).",
      };
    }

    return null;
  }, [status]);

  if (!banner) return null;

  const styles =
    banner.variant === "live"
      ? {
          wrap: "bg-red-600/20 border-red-500/40",
          title: "text-red-200",
          sub: "text-red-200/80",
          btn: "border-red-200/30 text-red-100 hover:bg-red-500/20",
        }
      : {
          wrap: "bg-[#F0B90B]/20 border-[#F0B90B]/40",
          title: "text-[#F0B90B]",
          sub: "text-[#F0B90B]/80",
          btn: "border-[#F0B90B]/40 text-[#F0B90B] hover:bg-[#F0B90B]/20",
        };

  return (
    <div className={`sticky top-0 z-30 border-b ${styles.wrap}`}>
      <div className="px-6 py-3 flex items-start md:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5">
            <AlertTriangle className={`w-5 h-5 ${styles.title}`} />
          </div>
          <div>
            <div className={`text-sm font-semibold ${styles.title}`}>{banner.title}</div>
            <div className={`text-xs ${styles.sub}`}>{banner.subtitle}</div>
          </div>
        </div>

        <div className="shrink-0">
          <Button
            variant="outline"
            className={`bg-transparent ${styles.btn}`}
            onClick={onOpenLiveReadiness}
          >
            Open Live Readiness
          </Button>
        </div>
      </div>
    </div>
  );
}
