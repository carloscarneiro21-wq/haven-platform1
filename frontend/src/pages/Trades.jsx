/**
 * Trades Page - Real-time trade monitoring with WebSocket streaming
 * 
 * Features:
 * - Live trades table with infinite scroll
 * - Create Paper Trade button/modal
 * - Real-time WebSocket updates (fallback to polling)
 * - Cumulative PnL chart (from trades data)
 * - Exposure by symbol
 * - Debug status line (API, WS, last event)
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { api } from "@/App";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { useTradesWebSocket } from "@/hooks/useTradesWebSocket";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Activity,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Wifi,
  WifiOff,
  Filter,
  ChevronDown,
  BarChart3,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Loader2,
  AlertCircle,
  Plus,
  Server,
  Radio,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

// Strategy colors
const STRATEGY_COLORS = {
  MM: "#F0B90B",
  MOM: "#0ECB81",
  SNIPER: "#F6465D",
  DEX: "#1E90FF",
  DCA: "#9B59B6",
  GRID: "#E67E22",
  TREND: "#1ABC9C",
  BREAKOUT: "#E74C3C",
  MANUAL: "#848E9C",
};

// Status colors
const STATUS_COLORS = {
  OPEN: "bg-blue-500/20 text-blue-400 border-blue-500/50",
  FILLED: "bg-green-500/20 text-green-400 border-green-500/50",
  PARTIAL: "bg-yellow-500/20 text-yellow-400 border-yellow-500/50",
  REJECTED: "bg-red-500/20 text-red-400 border-red-500/50",
  CLOSED: "bg-gray-500/20 text-gray-400 border-gray-500/50",
};

export default function Trades() {
  const { token } = useAuth();
  
  // Debug: log token availability
  useEffect(() => {
    console.log("[Trades] Token available:", !!token, token ? `(length=${token.length})` : "");
  }, [token]);
  
  // State
  const [trades, setTrades] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  // Close trade modal
  const [closingTrade, setClosingTrade] = useState(null);
  const [closing, setClosing] = useState(false);
  const [closePrice, setClosePrice] = useState("");

  const [apiConnected, setApiConnected] = useState(true);
  const [lastEventTime, setLastEventTime] = useState(null);
  
  // Create trade modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTrade, setNewTrade] = useState({
    symbol: "BTC/USDT",
    side: "BUY",
    qty: "0.01",
    entry_price: "",
    exit_price: "",
    strategy: "MANUAL",
  });
  
  // Filters
  const [filters, setFilters] = useState({
    agent_id: "",
    symbol: "",
    strategy: "",
    status: "",
    mode: "paper",
    timeframe: "24h",
  });

  // Report tab state
  const [activeTab, setActiveTab] = useState("trades");
  const [reportWindow, setReportWindow] = useState("24h");
  const [reportStrategy, setReportStrategy] = useState("ALL");
  const [reportAgentId, setReportAgentId] = useState("ALL");
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState(null);

  // Failed examples expansion state (Report tab)
  const [expandedFailures, setExpandedFailures] = useState({});

  const [searchTerm, setSearchTerm] = useState("");
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const [hasMore, setHasMore] = useState(true);
  
  // Polling fallback
  const pollingRef = useRef(null);
  const inFlightRef = useRef({ trades: false, summary: false, report: false });
  const backoffRef = useRef({ currentMs: 20000 });
  const cacheRef = useRef({
    trades: { ts: 0, data: null },
    summary: { ts: 0, data: null },
    report: { ts: 0, data: null },
  });
  
  // WebSocket handlers (do not depend on functions declared later)
  const handleTrade = useCallback((message) => {
    setLastEventTime(new Date().toISOString());
    
    if (message.type === "trade.created") {
      setTrades(prev => [message.data, ...prev.slice(0, 199)]);
    } else if (message.type === "trade.updated") {
      setTrades(prev => 
        prev.map(t => t.id === message.data.id ? { ...t, ...message.data } : t)
      );
    } else if (message.type === "trades.polled") {
      // Polling fallback - replace all trades
      setTrades(message.data || []);
    }
  }, []);
  
  const handleMetrics = useCallback((message) => {
    setLastEventTime(new Date().toISOString());

    if (message.type === "metrics.updated") {
      setMetrics(message.data);
    }

    if (message.type === "pong" || message.type === "pong.ack" || message.type === "ping" || message.type === "heartbeat") {
      // Keepalive/liveness messages - no state update besides lastEventTime
      return;
    }
  }, []);
  
  // WebSocket connection
  const {
    connected: wsConnected,
    connecting: wsConnecting,
    usingPolling,
    subscribe,
    error: wsError,
  } = useTradesWebSocket(token, {
    onTrade: handleTrade,
    onMetrics: handleMetrics,
    autoConnect: true,
  });
  
  // Subscribe to topics when connected
  useEffect(() => {
    if (wsConnected) {
      subscribe(["trades", "metrics"], {
        mode: "paper",
      });
    }
  }, [wsConnected, subscribe]);
  
  // Polling fallback when WS is down (rate-limit safe)
  useEffect(() => {
    const stop = () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
    };

    // If WS is connected, polling must be OFF
    if (!usingPolling) {
      stop();
      backoffRef.current.currentMs = 20000;
      return;
    }

    const safeGet = async (key, fn) => {
      const now = Date.now();
      const cached = cacheRef.current[key];
      if (cached?.data && now - cached.ts < 8000) {
        return cached.data;
      }

      if (inFlightRef.current[key]) return null;
      inFlightRef.current[key] = true;

      try {
        const data = await fn();
        cacheRef.current[key] = { ts: Date.now(), data };
        backoffRef.current.currentMs = 20000; // reset backoff on success
        return data;
      } catch (e) {
        const status = e?.response?.status;
        if (status === 429) {
          backoffRef.current.currentMs = Math.min(backoffRef.current.currentMs * 2, 180000);
        }
        return null;
      } finally {
        inFlightRef.current[key] = false;
      }
    };

    const tick = async () => {
      // Trades
      const t = await safeGet("trades", async () => {
        const res = await api.get("/trades", {
          params: {
            limit: 50,
            offset: 0,
            mode: "paper",
            ...(filters.agent_id ? { agent_id: filters.agent_id } : {}),
            ...(filters.symbol ? { symbol: filters.symbol } : {}),
            ...(filters.strategy && filters.strategy !== "all" ? { strategy: filters.strategy } : {}),
            ...(filters.status && filters.status !== "all" ? { status: filters.status } : {}),
          },
        });
        return res.data;
      });
      if (t?.trades) setTrades(t.trades);

      // Summary
      const s = await safeGet("summary", async () => {
        const res = await api.get("/trades/summary", {
          params: { window: filters.timeframe, group_by: "agent", mode: "paper" },
        });
        return res.data;
      });
      if (s) setSummary(s);

      // Report (only when tab active)
      if (activeTab === "report") {
        const r = await safeGet("report", async () => {
          const res = await api.get("/trades/report", {
            params: { mode: "paper", window: reportWindow, strategy: reportStrategy, agent_id: reportAgentId },
          });
          return res.data;
        });
        if (r) setReport(r);
      }

      // schedule next tick
      const waitMs = Math.max(15000, backoffRef.current.currentMs);
      pollingRef.current = setTimeout(tick, waitMs);
    };

    // start immediately, then schedule
    stop();
    tick();

    return stop;
  }, [usingPolling, filters, reportWindow, reportStrategy, reportAgentId, activeTab]);
  
  // Fetch trades from API
  const fetchTrades = useCallback(async (reset = false) => {
    try {
      if (reset) {
        setLoading(true);
        setOffset(0);
        offsetRef.current = 0;
      } else {
        setLoadingMore(true);
      }
      
      const params = {
        limit: 50,
        offset: reset ? 0 : offsetRef.current,
        mode: "paper", // Always fetch paper trades
      };

      if (filters.agent_id) params.agent_id = filters.agent_id;
      if (filters.symbol) params.symbol = filters.symbol;
      if (filters.strategy && filters.strategy !== "all") params.strategy = filters.strategy;
      if (filters.status && filters.status !== "all") params.status = filters.status;
      
      const res = await api.get("/trades", { params });
      
      if (reset) {
        setTrades(res.data.trades || []);
      } else {
        setTrades(prev => [...prev, ...(res.data.trades || [])]);
      }
      
      setHasMore(res.data.has_more);
      const nextOffset = reset ? 50 : offsetRef.current + 50;
      offsetRef.current = nextOffset;
      setOffset(nextOffset);

      setError(null);
      setApiConnected(true);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to fetch trades");
      setApiConnected(false);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [filters]);
  
  // Fetch summary
  const fetchSummary = useCallback(async () => {
    try {
      const res = await api.get("/trades/summary", {
        params: {
          window: filters.timeframe,
          group_by: "agent",
          mode: "paper",
        },
      });
      setSummary(res.data);
      setApiConnected(true);
    } catch (e) {
      console.error("Failed to fetch summary:", e);
    }
  }, [filters.timeframe]);
  

  const fetchReport = useCallback(async () => {
    try {
      setReportLoading(true);
      setReportError(null);
      const params = {
        mode: "paper",
        window: reportWindow,
        strategy: reportStrategy,
        agent_id: reportAgentId,
      };
      const res = await api.get("/trades/report", { params });
      setReport(res.data);
    } catch (e) {
      setReportError(e.response?.data?.detail || "Failed to load report");
    } finally {
      setReportLoading(false);
    }
  }, [reportWindow, reportStrategy, reportAgentId]);

  const downloadReportJson = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trades_report_${report?.mode || 'paper'}_${report?.window || reportWindow}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Create paper trade
  const createPaperTrade = async () => {
    try {
      setCreating(true);
      
      const payload = {
        symbol: newTrade.symbol,
        side: newTrade.side,
        qty: parseFloat(newTrade.qty),
        entry_price: parseFloat(newTrade.entry_price),
        strategy: newTrade.strategy,
        agent_id: "manual_user",
        agent_name: "Manual Trade",
      };

      
      // Add exit price if provided (closed trade)
      if (newTrade.exit_price) {
        payload.exit_price = parseFloat(newTrade.exit_price);
      }
      
      const res = await api.post("/trades/paper", payload);
      
      if (res.data.success) {
        // Add trade to list
        const createdTrade = res.data.trade;
        // Convert ts to proper format if needed
        if (createdTrade.ts && typeof createdTrade.ts === "object") {
          createdTrade.ts = new Date().toISOString();
        }
        setTrades(prev => [createdTrade, ...prev]);
        
        // Refresh summary
        await fetchSummary();
        
        // Reset form and close modal
        setShowCreateModal(false);
        setNewTrade({
          symbol: "BTC/USDT",
          side: "BUY",
          qty: "0.01",
          entry_price: "",
          exit_price: "",
          strategy: "MANUAL",
        });
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to create trade");
    } finally {
      setCreating(false);
    }
  };
  
  const closeTrade = async () => {
    if (!closingTrade) return;
    try {
      setClosing(true);
      const exitPrice = parseFloat(closePrice);
      if (!exitPrice || exitPrice <= 0) {
        toast.error("Exit price is required");
        return;
      }

      await api.post(`/agent/trade/${closingTrade.id}/close`, {
        exit_price: exitPrice,
        reason: "manual",
        meta: { source: "ui" },
      });

      setClosingTrade(null);
      setClosePrice("");
      // Force refresh in case WS is down
      fetchTrades(true);
      fetchSummary();
    } catch (e) {
      // axios interceptor toasts
    } finally {
      setClosing(false);
    }
  };

  // Initial load (avoid duplicate fetches when WS is down and polling kicks in)
  useEffect(() => {
    if (usingPolling) return;
    fetchTrades(true);
    fetchSummary();
  }, [fetchTrades, fetchSummary, usingPolling]);

  // When user opens the Report tab, fetch report once (only if WS is connected; otherwise polling handles it)
  useEffect(() => {
    if (usingPolling) return;
    if (activeTab === "report") {
      fetchReport();
    }
  }, [activeTab, fetchReport, usingPolling]);

  // Report refresh when report filters change (debounced; only while on Report tab)
  useEffect(() => {
    if (usingPolling) return;
    if (activeTab !== "report") return;

    const t = setTimeout(() => {
      fetchReport();
    }, 500);

    return () => clearTimeout(t);
  }, [activeTab, reportWindow, reportStrategy, reportAgentId, fetchReport, usingPolling]);
  
  // Refetch trades/summary on filter change (debounced; only when not polling)
  useEffect(() => {
    if (usingPolling) return;

    const t = setTimeout(() => {
      fetchTrades(true);
      fetchSummary();
    }, 400);

    return () => clearTimeout(t);
  }, [filters.strategy, filters.status, filters.timeframe, fetchTrades, fetchSummary, usingPolling]);
  
  // Filter trades by search term
  const filteredTrades = useMemo(() => {
    if (!searchTerm) return trades;
    const term = searchTerm.toLowerCase();
    return trades.filter(t => 
      t.symbol?.toLowerCase().includes(term) ||
      t.agent_name?.toLowerCase().includes(term) ||
      t.strategy?.toLowerCase().includes(term)
    );

  }, [trades, searchTerm]);
  
  // Calculate PnL chart data from trades
  const pnlChartData = useMemo(() => {
    if (!trades.length) return [];
    
    // Sort by timestamp and calculate cumulative PnL
    const sorted = [...trades]
      .filter(t => t.ts)
      .sort((a, b) => new Date(a.ts) - new Date(b.ts));
    
    let cumulative = 0;
    return sorted.slice(-50).map(t => {
      cumulative += t.pnl || 0;
      return {
        ts: new Date(t.ts).toLocaleTimeString(),
        pnl: t.pnl || 0,
        cumulative,
        symbol: t.symbol,
      };
    });
  }, [trades]);
  
  // Format currency
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return "—";
    const sign = value >= 0 ? "+" : "";
    return `${sign}€${Math.abs(value).toFixed(2)}`;
  };
  
  // Format percentage
  const formatPercent = (value) => {
    if (value === null || value === undefined) return "—";
    const sign = value >= 0 ? "+" : "";
    return `${sign}${value.toFixed(2)}%`;
  };
  
  return (
    <div className="min-h-screen bg-[#0B0E11] text-[#EAECEF] p-4 lg:p-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold font-rajdhani flex items-center gap-2">
            <Activity className="w-6 h-6 text-[#F0B90B]" />
            Trade Monitor
          </h1>
          <p className="text-sm text-[#848E9C]">
            Real-time view of paper trades and performance
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-6">
        <div className="flex items-center justify-between gap-3">
          <TabsList className="bg-[#161A1E] border border-[#2B3139]">
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="report">Report</TabsTrigger>
          </TabsList>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
          {/* Create Trade Button */}
          <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
            <DialogTrigger asChild>
              <Button className="bg-[#F0B90B] hover:bg-[#F0B90B]/90 text-black">
                <Plus className="w-4 h-4 mr-2" />
                Create Paper Trade
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-[#1E2329] border-[#2B3139] text-[#EAECEF]">
              <DialogHeader>
                <DialogTitle>Create Paper Trade</DialogTitle>
                <DialogDescription className="text-[#848E9C]">
                  Add a simulated trade for testing. Leave exit price empty for open trades.
                </DialogDescription>
              </DialogHeader>
              
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-[#848E9C]">Symbol</Label>
                    <Select
                      value={newTrade.symbol}
                      onValueChange={(v) => setNewTrade(p => ({ ...p, symbol: v }))}
                    >
                      <SelectTrigger className="bg-[#161A1E] border-[#2B3139]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                        <SelectItem value="BTC/USDT">BTC/USDT</SelectItem>
                        <SelectItem value="ETH/USDT">ETH/USDT</SelectItem>
                        <SelectItem value="SOL/USDT">SOL/USDT</SelectItem>
                        <SelectItem value="BNB/USDT">BNB/USDT</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-[#848E9C]">Side</Label>
                    <Select
                      value={newTrade.side}
                      onValueChange={(v) => setNewTrade(p => ({ ...p, side: v }))}
                    >
                      <SelectTrigger className="bg-[#161A1E] border-[#2B3139]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                        <SelectItem value="BUY">BUY</SelectItem>
                        <SelectItem value="SELL">SELL</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-[#848E9C]">Quantity</Label>
                    <Input
                      type="number"
                      step="0.001"
                      value={newTrade.qty}
                      onChange={(e) => setNewTrade(p => ({ ...p, qty: e.target.value }))}
                      className="bg-[#161A1E] border-[#2B3139]"
                      placeholder="0.01"
                    />
                  </div>
                  <div>
                    <Label className="text-[#848E9C]">Strategy</Label>
                    <Select
                      value={newTrade.strategy}
                      onValueChange={(v) => setNewTrade(p => ({ ...p, strategy: v }))}
                    >
                      <SelectTrigger className="bg-[#161A1E] border-[#2B3139]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                        <SelectItem value="MANUAL">MANUAL</SelectItem>
                        <SelectItem value="MM">MM</SelectItem>
                        <SelectItem value="MOM">MOM</SelectItem>
                        <SelectItem value="DCA">DCA</SelectItem>
                        <SelectItem value="SNIPER">SNIPER</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-[#848E9C]">Entry Price *</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={newTrade.entry_price}
                      onChange={(e) => setNewTrade(p => ({ ...p, entry_price: e.target.value }))}
                      className="bg-[#161A1E] border-[#2B3139]"
                      placeholder="65000.00"
                    />
                  </div>
                  <div>
                    <Label className="text-[#848E9C]">Exit Price (optional)</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={newTrade.exit_price}
                      onChange={(e) => setNewTrade(p => ({ ...p, exit_price: e.target.value }))}
                      className="bg-[#161A1E] border-[#2B3139]"
                      placeholder="Leave empty for OPEN"
                    />
                  </div>
                </div>
              </div>
              
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setShowCreateModal(false)}
                  className="border-[#2B3139]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={createPaperTrade}
                  disabled={creating || !newTrade.entry_price || !newTrade.qty}
                  className="bg-[#F0B90B] hover:bg-[#F0B90B]/90 text-black"
                >
                  {creating ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4 mr-2" />
                  )}
                  Create Trade
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchTrades(true)}
            className="border-[#2B3139] hover:bg-[#2B3139]"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          </div>
        </div>
      
      {/* Debug Status Line */}
      <div className="flex flex-wrap items-center gap-4 mb-4 px-3 py-2 bg-[#161A1E] rounded-lg border border-[#2B3139] text-xs">
        <div className="flex items-center gap-2">
          <Server className="w-3 h-3 text-[#848E9C]" />
          <span className="text-[#848E9C]">API:</span>
          <span className={apiConnected ? "text-[#0ECB81]" : "text-[#F6465D]"}>
            {apiConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          <Radio className="w-3 h-3 text-[#848E9C]" />
          <span className="text-[#848E9C]">WS:</span>
          {wsConnecting ? (
            <span className="text-yellow-400">Connecting...</span>
          ) : wsConnected ? (
            <span className="text-[#0ECB81]">Connected</span>
          ) : wsError ? (
            <span className="text-[#F6465D]">Auth Failed</span>
          ) : (
            <span className="text-[#F6465D]">Disconnected</span>
          )}
          {usingPolling && (
            <Badge className="bg-yellow-500/20 text-yellow-400 text-[10px] px-1">
              Polling
            </Badge>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          <Clock className="w-3 h-3 text-[#848E9C]" />
          <span className="text-[#848E9C]">Last Event:</span>
          <span className="text-[#EAECEF]">
            {lastEventTime ? new Date(lastEventTime).toLocaleTimeString() : "—"}
          </span>

        </div>
      </div>

      {/* Close Trade Modal */}
      <Dialog open={!!closingTrade} onOpenChange={(open) => !open && setClosingTrade(null)}>
        <DialogContent className="bg-[#1E2329] border-[#2B3139] text-[#EAECEF]">
          <DialogHeader>
            <DialogTitle>Close Trade</DialogTitle>
            <DialogDescription className="text-[#848E9C]">
              Close an OPEN trade by providing an exit price.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="text-sm text-[#848E9C]">
              <span className="text-[#EAECEF] font-mono">{closingTrade?.symbol}</span>
              <span className="mx-2">•</span>
              <span className="font-mono">{closingTrade?.id}</span>
            </div>

            <div>
              <label className="block text-sm text-[#848E9C] mb-1">Exit Price</label>
              <Input
                value={closePrice}
                onChange={(e) => setClosePrice(e.target.value)}
                placeholder="e.g. 66000"
                className="bg-[#161A1E] border-[#2B3139] text-[#EAECEF]"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              className="border-[#2B3139] bg-transparent text-[#EAECEF] hover:bg-[#2B3139]"
              onClick={() => setClosingTrade(null)}
            >
              Cancel
            </Button>
            <Button
              className="bg-[#F0B90B] text-black hover:bg-[#F0B90B]/90"
              disabled={closing || !closePrice}
              onClick={closeTrade}
            >
              {closing ? "Closing..." : "Close Trade"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      
      {/* Filters Bar */}
      <Card className="bg-[#161A1E] border-[#2B3139] mb-6">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <Filter className="w-4 h-4 text-[#848E9C]" />
            
            <Select
              value={filters.strategy || "all"}
              onValueChange={(v) => setFilters(f => ({ ...f, strategy: v === "all" ? "" : v }))}
            >
              <SelectTrigger className="w-[130px] bg-[#1E2329] border-[#2B3139]">
                <SelectValue placeholder="Strategy" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                <SelectItem value="all">All Strategies</SelectItem>
                <SelectItem value="MM">MM</SelectItem>
                <SelectItem value="MOM">MOM</SelectItem>
                <SelectItem value="SNIPER">SNIPER</SelectItem>
                <SelectItem value="DEX">DEX</SelectItem>
                <SelectItem value="DCA">DCA</SelectItem>
                <SelectItem value="MANUAL">MANUAL</SelectItem>
              </SelectContent>
            </Select>
            
            <Select
              value={filters.status || "all"}
              onValueChange={(v) => setFilters(f => ({ ...f, status: v === "all" ? "" : v }))}
            >
              <SelectTrigger className="w-[120px] bg-[#1E2329] border-[#2B3139]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="OPEN">Open</SelectItem>
                <SelectItem value="CLOSED">Closed</SelectItem>
                <SelectItem value="FILLED">Filled</SelectItem>
              </SelectContent>
            </Select>
            
            <Select
              value={filters.timeframe}
              onValueChange={(v) => setFilters(f => ({ ...f, timeframe: v }))}
            >
              <SelectTrigger className="w-[100px] bg-[#1E2329] border-[#2B3139]">
                <SelectValue placeholder="Time" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                <SelectItem value="1h">1 Hour</SelectItem>
                <SelectItem value="24h">24 Hours</SelectItem>
                <SelectItem value="7d">7 Days</SelectItem>
              </SelectContent>
            </Select>
            
            <Input
              placeholder="Search symbol, agent..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-[200px] bg-[#1E2329] border-[#2B3139]"
            />
            
            {(filters.strategy || filters.status || searchTerm) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilters(f => ({ ...f, strategy: "", status: "" }));
                  setSearchTerm("");
                }}
                className="text-[#848E9C] hover:text-[#EAECEF]"
              >
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
      
      {/* Summary Stats */}


      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <Card className="bg-[#161A1E] border-[#2B3139]">
          <CardContent className="p-4">
            <p className="text-xs text-[#848E9C] uppercase tracking-wider mb-1">Cumulative PnL</p>
            <p className={`text-2xl font-bold ${(summary?.overall?.cumulative_pnl || 0) >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>
              {formatCurrency(summary?.overall?.cumulative_pnl || 0)}
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-[#161A1E] border-[#2B3139]">
          <CardContent className="p-4">
            <p className="text-xs text-[#848E9C] uppercase tracking-wider mb-1">Total Trades</p>
            <p className="text-2xl font-bold text-[#EAECEF]">
              {summary?.overall?.total_trades || trades.length || 0}
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-[#161A1E] border-[#2B3139]">
          <CardContent className="p-4">
            <p className="text-xs text-[#848E9C] uppercase tracking-wider mb-1">Win Rate</p>
            <p className={`text-2xl font-bold ${(summary?.overall?.win_rate || 0) >= 50 ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>
              {(summary?.overall?.win_rate || 0).toFixed(1)}%
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-[#161A1E] border-[#2B3139]">
          <CardContent className="p-4">
            <p className="text-xs text-[#848E9C] uppercase tracking-wider mb-1">Wins / Losses</p>
            <p className="text-2xl font-bold">
              <span className="text-[#0ECB81]">{summary?.overall?.wins || 0}</span>
              <span className="text-[#848E9C]"> / </span>
              <span className="text-[#F6465D]">{summary?.overall?.losses || 0}</span>
            </p>
          </CardContent>
        </Card>
        
        <Card className="bg-[#161A1E] border-[#2B3139]">
          <CardContent className="p-4">
            <p className="text-xs text-[#848E9C] uppercase tracking-wider mb-1">Avg Trade</p>
            <p className={`text-2xl font-bold ${(summary?.overall?.avg_trade || 0) >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>
              {formatCurrency(summary?.overall?.avg_trade || 0)}
            </p>
          </CardContent>
        </Card>
      </div>
      
      {/* Main Content */}

      <TabsContent value="trades">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Trades Table */}
          <Card className="lg:col-span-2 bg-[#161A1E] border-[#2B3139]">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-rajdhani flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[#F0B90B]" />
              Paper Trades
              <Badge variant="outline" className="ml-auto text-[#848E9C]">
                {filteredTrades.length} trades
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[500px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-[#161A1E]">
                  <TableRow className="border-[#2B3139] hover:bg-transparent">
                    <TableHead className="text-[#848E9C] w-[140px]">Time</TableHead>
                    <TableHead className="text-[#848E9C]">Symbol</TableHead>
                    <TableHead className="text-[#848E9C]">Agent</TableHead>
                    <TableHead className="text-[#848E9C]">Strategy</TableHead>
                    <TableHead className="text-[#848E9C]">Side</TableHead>
                    <TableHead className="text-[#848E9C] text-right">Entry</TableHead>
                    <TableHead className="text-[#848E9C] text-right">PnL</TableHead>
                    <TableHead className="text-[#848E9C]">Venue</TableHead>
                    <TableHead className="text-[#848E9C]">Order ID</TableHead>
                    <TableHead className="text-[#848E9C]">Status</TableHead>
                    <TableHead className="text-[#848E9C]">Actions</TableHead>

                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-8">
                        <Loader2 className="w-6 h-6 animate-spin mx-auto text-[#F0B90B]" />
                        <p className="text-sm text-[#848E9C] mt-2">Loading trades...</p>
                      </TableCell>
                    </TableRow>
                  ) : filteredTrades.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-8">
                        <Activity className="w-8 h-8 mx-auto text-[#848E9C] mb-2" />
                        <p className="text-sm text-[#848E9C]">No paper trades yet</p>
                        <p className="text-xs text-[#5E6673] mt-1">Click “Create Paper Trade” to add one</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredTrades.map((trade) => (
                      <TableRow 
                        key={trade.id}
                        className="border-[#2B3139] hover:bg-[#1E2329]"
                      >
                        <TableCell className="text-xs text-[#848E9C]">
                          <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {trade.ts ? new Date(trade.ts).toLocaleString() : "—"}
                          </div>
                        </TableCell>
                        <TableCell className="font-mono font-medium">
                          {trade.symbol}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <span title={trade.agent_id || ""}>
                            {(trade.agent_id || "—").slice(0, 10)}{(trade.agent_id || "").length > 10 ? "…" : ""}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge 
                            style={{ 
                              backgroundColor: `${STRATEGY_COLORS[trade.strategy] || '#848E9C'}20`,
                              color: STRATEGY_COLORS[trade.strategy] || '#848E9C',
                              borderColor: `${STRATEGY_COLORS[trade.strategy] || '#848E9C'}50`,
                            }}
                            className="border text-xs"
                          >
                            {trade.strategy || "—"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge className={
                            trade.side?.toUpperCase() === "BUY" 
                              ? "bg-green-500/20 text-green-400 border border-green-500/50"
                              : "bg-red-500/20 text-red-400 border border-red-500/50"
                          }>
                            {trade.side?.toUpperCase() === "BUY" ? (
                              <ArrowUpRight className="w-3 h-3 mr-1" />
                            ) : (
                              <ArrowDownRight className="w-3 h-3 mr-1" />
                            )}
                            {trade.side?.toUpperCase() || "—"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          €{(trade.entry_price || trade.price || 0).toFixed(2)}
                        </TableCell>
                        <TableCell className={`text-right font-mono font-medium ${
                          (trade.pnl || 0) >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'
                        }`}>
                          {formatCurrency(trade.pnl || 0)}
                          {trade.pnl_pct !== undefined && (
                            <span className="text-xs ml-1 opacity-70">
                              ({formatPercent(trade.pnl_pct)})
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-[#B7BDC6]">
                          {trade.venue || (trade.mode === 'binance_testnet' ? 'BINANCE_TESTNET' : trade.mode === 'binance_live' ? 'BINANCE_LIVE' : 'PAPER')}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-[#B7BDC6]">
                          {trade.order_id || '—'}
                        </TableCell>
                        <TableCell>
                          <Badge className={`${STATUS_COLORS[trade.status] || STATUS_COLORS.OPEN} border text-xs`}>
                            {trade.status || "OPEN"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {trade.status === "OPEN" ? (
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2 border-[#2B3139] bg-[#1E2329] text-[#EAECEF] hover:bg-[#2B3139]"
                              onClick={() => {
                                setClosingTrade(trade);
                                setClosePrice(String((trade.entry_price || trade.price || 0).toFixed(2)));
                              }}
                            >
                              Close
                            </Button>
                          ) : (
                            <span className="text-xs text-[#5E6673]">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
            
            {/* Load More */}
            {hasMore && !loading && filteredTrades.length > 0 && (
              <div className="p-4 border-t border-[#2B3139]">
                <Button
                  variant="outline"
                  className="w-full border-[#2B3139] hover:bg-[#2B3139]"
                  onClick={() => fetchTrades(false)}
                  disabled={loadingMore}
                >
                  {loadingMore ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <ChevronDown className="w-4 h-4 mr-2" />
                  )}
                  Load More
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
        
        {/* Charts Column */}
        <div className="space-y-6">
          {/* Cumulative PnL Chart */}
          <Card className="bg-[#161A1E] border-[#2B3139]">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-rajdhani flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-[#0ECB81]" />
                Cumulative PnL
              </CardTitle>
            </CardHeader>
            <CardContent>
              {pnlChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={pnlChartData}>
                    <defs>
                      <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0ECB81" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#0ECB81" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2B3139" />
                    <XAxis 
                      dataKey="ts" 
                      stroke="#848E9C" 
                      fontSize={10}
                      tickLine={false}
                    />
                    <YAxis 
                      stroke="#848E9C" 
                      fontSize={10}
                      tickLine={false}
                      tickFormatter={(v) => `€${v}`}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#1E2329",
                        border: "1px solid #2B3139",
                        borderRadius: "8px",
                      }}
                      labelStyle={{ color: "#848E9C" }}
                    />
                    <ReferenceLine y={0} stroke="#848E9C" strokeDasharray="3 3" />
                    <Area
                      type="monotone"
                      dataKey="cumulative"
                      stroke="#0ECB81"
                      fill="url(#pnlGradient)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-[#848E9C]">
                  <p className="text-sm">Create trades to see PnL chart</p>
                </div>
              )}
            </CardContent>
          </Card>
          
          {/* PnL by Agent */}
          {summary?.by_agent && summary.by_agent.length > 0 && (
            <Card className="bg-[#161A1E] border-[#2B3139]">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-rajdhani flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#F0B90B]" />
                  PnL by Strategy
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {summary.by_agent.slice(0, 5).map((agent, i) => (
                    <div key={agent.id || i} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div 
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: Object.values(STRATEGY_COLORS)[i % Object.values(STRATEGY_COLORS).length] }}
                        />
                        <span className="text-sm text-[#848E9C]">
                          {agent.name || agent.id || `Agent ${i + 1}`}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className={`text-sm font-mono font-medium ${
                          agent.total_pnl >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'
                        }`}>
                          {formatCurrency(agent.total_pnl)}
                        </span>
                        <span className="text-xs text-[#848E9C] ml-2">
                          ({agent.total_trades} trades)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* Quick Stats */}
          <Card className="bg-[#161A1E] border-[#2B3139]">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-rajdhani flex items-center gap-2">
                <PieChart className="w-4 h-4 text-[#F0B90B]" />
                Trade Breakdown
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#848E9C]">Open Trades</span>
                  <span className="text-sm font-mono text-[#EAECEF]">
                    {trades.filter(t => t.status === "OPEN").length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#848E9C]">Closed Trades</span>
                  <span className="text-sm font-mono text-[#EAECEF]">
                    {trades.filter(t => t.status === "CLOSED").length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#848E9C]">Total Fees</span>
                  <span className="text-sm font-mono text-[#F6465D]">
                    €{trades.reduce((sum, t) => sum + (t.fees || 0), 0).toFixed(2)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </TabsContent>

    <TabsContent value="report">
      <Card className="bg-[#161A1E] border-[#2B3139]">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="text-base font-rajdhani">Trade Report — last {reportWindow} (paper)</CardTitle>
              <p className="text-xs text-[#848E9C] mt-1">Buys vs sells, what worked, what failed, and recommendations.</p>
            </div>
            <Button variant="outline" size="sm" className="border-[#2B3139] hover:bg-[#2B3139]" onClick={downloadReportJson} disabled={!report}>
              Download JSON
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <Select value={reportWindow} onValueChange={setReportWindow}>
              <SelectTrigger className="w-[110px] bg-[#1E2329] border-[#2B3139]">
                <SelectValue placeholder="Window" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                <SelectItem value="24h">24h</SelectItem>
                <SelectItem value="7d">7d</SelectItem>
                <SelectItem value="30d">30d</SelectItem>
              </SelectContent>
            </Select>

            <Select value={reportStrategy} onValueChange={setReportStrategy}>
              <SelectTrigger className="w-[140px] bg-[#1E2329] border-[#2B3139]">
                <SelectValue placeholder="Strategy" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E2329] border-[#2B3139]">
                <SelectItem value="ALL">All</SelectItem>
                <SelectItem value="MM">MM</SelectItem>
                <SelectItem value="MOM">MOM</SelectItem>
                <SelectItem value="SNIPER">SNIPER</SelectItem>
                <SelectItem value="MANUAL">MANUAL</SelectItem>
              </SelectContent>
            </Select>

            <Input
              value={reportAgentId === "ALL" ? "" : reportAgentId}
              onChange={(e) => setReportAgentId(e.target.value ? e.target.value : "ALL")}
              placeholder="Agent id (empty = ALL)"
              className="w-[220px] bg-[#1E2329] border-[#2B3139]"
            />

            <Button variant="outline" size="sm" className="border-[#2B3139] hover:bg-[#2B3139]" onClick={fetchReport}>
              Refresh report
            </Button>
          </div>

          {reportLoading ? (
            <div className="py-10 text-center text-sm text-[#848E9C]">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-[#F0B90B]" />
              <div className="mt-2">Loading report...</div>
            </div>
          ) : reportError ? (
            <div className="py-6 text-sm text-[#F6465D]">{reportError}</div>
          ) : !report ? (
            <div className="py-6 text-sm text-[#848E9C]">No report data yet.</div>
          ) : (
            <div className="space-y-6">
              {/* Quick cards */}
              <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Total</div><div className="text-lg font-mono">{report.counts.total}</div></CardContent></Card>
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Buys</div><div className="text-lg font-mono">{report.counts.buys}</div></CardContent></Card>
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Sells</div><div className="text-lg font-mono">{report.counts.sells}</div></CardContent></Card>
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Open</div><div className="text-lg font-mono">{report.counts.open}</div></CardContent></Card>
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Closed</div><div className="text-lg font-mono">{report.counts.closed}</div></CardContent></Card>
                <Card className="bg-[#1E2329] border-[#2B3139]"><CardContent className="p-3"><div className="text-xs text-[#848E9C]">Net PnL</div><div className={`text-lg font-mono ${report.pnl.net >= 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'}`}>{formatCurrency(report.pnl.net)}</div></CardContent></Card>
              </div>

              {/* Worked well */}
              <div>
                <h3 className="text-sm font-semibold mb-2">What worked well</h3>
                <div className="space-y-2">
                  {report.worked_well?.length ? report.worked_well.map((w, idx) => (
                    <div key={idx} className="p-3 rounded border border-[#2B3139] bg-[#1E2329]">
                      <div className="text-sm text-[#EAECEF]">{w.title}</div>
                      <div className="text-xs text-[#848E9C] mt-1">{w.evidence}</div>
                    </div>
                  )) : (
                    <div className="text-sm text-[#848E9C]">No highlights yet.</div>
                  )}
                </div>
              </div>

              {/* Failed */}
              <div>
                <h3 className="text-sm font-semibold mb-2">What failed</h3>
                <div className="space-y-2">
                  {report.failed?.length ? report.failed.map((f, idx) => {
                    const isOpen = !!expandedFailures[f.reason_code];
                    const exCount = (f.examples || []).length;
                    return (
                      <div key={idx} className="p-3 rounded border border-[#2B3139] bg-[#1E2329]">
                        <div className="flex items-center justify-between">
                          <div className="text-sm text-[#EAECEF]">{f.title}</div>
                          <Badge variant="outline" className="text-[#848E9C]">{f.reason_code} • {f.count}</Badge>
                        </div>
                        <div className="text-xs text-[#848E9C] mt-1">{f.evidence}</div>

                        {exCount > 0 && (
                          <div className="mt-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-[#B7BDC6] hover:bg-[#2B3139]"
                              onClick={() => setExpandedFailures((prev) => ({ ...prev, [f.reason_code]: !isOpen }))}
                            >
                              {isOpen ? "Hide examples" : `Show examples (${exCount})`}
                            </Button>

                            {isOpen && (
                              <div className="mt-2 space-y-2">
                                {(f.examples || []).slice(0, 3).map((ex, i) => (
                                  <div key={i} className="p-2 rounded border border-[#2B3139] bg-[#161A1E] text-xs">
                                    <div className="flex items-center justify-between gap-2">
                                      <div className="text-[#848E9C] font-mono">
                                        {(ex.ts || "").slice(11, 19)}
                                      </div>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-6 px-2 border-[#2B3139] hover:bg-[#2B3139]"
                                        onClick={() => {
                                          try {
                                            navigator.clipboard.writeText(JSON.stringify(ex, null, 2));
                                            toast.success("Copied");
                                          } catch (e) {
                                            // ignore
                                          }
                                        }}
                                      >
                                        Copy JSON
                                      </Button>
                                    </div>
                                    <div className="mt-1 text-[#EAECEF]">
                                      <span className="font-mono">{ex.agent_id}</span>
                                      <span className="text-[#848E9C]"> • </span>
                                      <span className="font-mono">{ex.strategy}</span>
                                      <span className="text-[#848E9C]"> • </span>
                                      <span className="font-mono">{ex.symbol}</span>
                                    </div>
                                    <div className="mt-1 text-[#848E9C]">
                                      <span className="font-mono">{ex.action}</span>
                                      <span className="text-[#848E9C]"> • </span>
                                      <span className="font-mono">{ex.code || f.reason_code}</span>
                                    </div>
                                    <div className="mt-1 text-[#B7BDC6] line-clamp-2">{ex.message}</div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  }) : (
                    <div className="text-sm text-[#848E9C]">No failures captured (logs may be empty for manual trades).</div>
                  )}
                </div>
              </div>

              {/* Recommendations */}
              <div>
                <h3 className="text-sm font-semibold mb-2">Recommendations</h3>
                <div className="space-y-2">
                  {report.recommendations?.length ? report.recommendations.map((r, idx) => (
                    <div key={idx} className="p-3 rounded border border-[#2B3139] bg-[#1E2329]">
                      <div className="flex items-center gap-2">
                        <Badge className={r.priority === 'P0' ? 'bg-[#F6465D]/20 text-[#F6465D]' : r.priority === 'P1' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-[#0ECB81]/20 text-[#0ECB81]'}>
                          {r.priority}
                        </Badge>
                        <div className="text-sm text-[#EAECEF]">{r.action}</div>
                      </div>
                      <div className="text-xs text-[#848E9C] mt-1">Expected impact: {r.expected_impact}</div>
                    </div>
                  )) : (
                    <div className="text-sm text-[#848E9C]">No recommendations.</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>
      </Tabs>

    </div>
  );
}
