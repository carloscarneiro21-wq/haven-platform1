/**
 * Trading Mode Badge - Global indicator for PAPER/LIVE mode
 * 
 * Displays prominently on all pages to indicate current trading mode.
 * PAPER MODE: Yellow/Gold badge - "Simulation only. No real funds at risk."
 * LIVE MODE: Red badge with warning - "REAL FUNDS AT RISK"
 */

import { useState, useEffect } from "react";
import { api } from "@/App";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Shield, AlertTriangle, Zap } from "lucide-react";

export function TradingModeBadge({ className = "" }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTradingStatus();
    // Poll every 30 seconds
    const interval = setInterval(fetchTradingStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchTradingStatus = async () => {
    try {
      const res = await api.get("/trading/status");
      setStatus(res.data);
    } catch (e) {
      // Default to paper mode if API fails
      setStatus({
        trading_mode: "paper",
        is_live_allowed: false,
        kill_switch: { active: false },
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Badge variant="outline" className={`animate-pulse ${className}`}>
        Loading...
      </Badge>
    );
  }

  const mode = String(status?.trading_mode || "paper").toLowerCase();
  const isPaper = mode === "paper";
  const isTestnet = mode === "binance_testnet";
  const isLive = mode === "binance_live";
  const killSwitchActive = status?.kill_switch?.active;

  // Kill switch takes priority
  if (killSwitchActive) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge 
              variant="destructive" 
              className={`bg-red-600 hover:bg-red-700 cursor-help flex items-center gap-1 ${className}`}
            >
              <AlertTriangle className="w-3 h-3" />
              KILL SWITCH
            </Badge>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs bg-red-900 border-red-700">
            <p className="font-semibold text-red-200">⚠️ Trading Halted</p>
            <p className="text-xs text-red-300 mt-1">
              {status?.kill_switch?.reason || "Emergency stop activated"}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // PAPER MODE (default)
  if (isPaper) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge 
              className={`bg-[#F0B90B]/20 text-[#F0B90B] hover:bg-[#F0B90B]/30 border border-[#F0B90B]/50 cursor-help flex items-center gap-1 ${className}`}
            >
              <Shield className="w-3 h-3" />
              PAPER MODE
            </Badge>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs bg-[#1E2026] border-[#F0B90B]/30">
            <p className="font-semibold text-[#F0B90B]">🛡️ Simulation Mode</p>
            <p className="text-xs text-[#848E9C] mt-1">
              No real funds at risk. All trades are simulated with realistic 
              prices, fees, and slippage.
            </p>
            <div className="mt-2 text-xs text-[#5E6673]">
              <p>• Real-time market prices</p>
              <p>• Simulated execution</p>
              <p>• Full PnL tracking</p>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // TESTNET MODE
  if (isTestnet) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              className={`bg-[#F0B90B]/25 text-[#F0B90B] hover:bg-[#F0B90B]/35 border border-[#F0B90B]/50 cursor-help flex items-center gap-1 ${className}`}
            >
              <Zap className="w-3 h-3" />
              TESTNET
            </Badge>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs bg-[#1E2026] border-[#F0B90B]/30">
            <p className="font-semibold text-[#F0B90B]">⚠️ BINANCE TESTNET</p>
            <p className="text-xs text-[#848E9C] mt-1">
              Real execution on Binance Testnet. No real funds, but real orders.
            </p>
            <div className="mt-2 text-xs text-[#5E6673]">
              <p>• CEX: {status?.live_cex_enabled ? "Enabled" : "Disabled"}</p>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // LIVE MODE
  if (isLive) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge 
              variant="destructive"
              className={`bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/50 cursor-help flex items-center gap-1 animate-pulse ${className}`}
            >
              <Zap className="w-3 h-3" />
              LIVE
            </Badge>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs bg-red-950 border-red-700">
            <p className="font-semibold text-red-400">⚠️ LIVE TRADING ACTIVE</p>
            <p className="text-xs text-red-300 mt-1">
              Real funds at risk. All trades execute on live exchanges.
            </p>
            <div className="mt-2 text-xs text-red-400/70">
              <p>• CEX: {status?.live_cex_enabled ? "Enabled" : "Disabled"}</p>
              <p>• DEX: {status?.live_dex_enabled ? "Enabled" : "Disabled"}</p>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Fallback - blocked or unknown state
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant="outline" 
            className={`text-[#848E9C] border-[#848E9C]/50 cursor-help flex items-center gap-1 ${className}`}
          >
            <Shield className="w-3 h-3" />
            PAPER MODE
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs">Trading mode: {status?.trading_mode || "unknown"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default TradingModeBadge;
