import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import PromotionModal from "@/components/PromotionModal";
import SniperHardening from "@/components/SniperHardening";
import {
  Play,
  Square,
  Download,
  RefreshCw,
  FileText,
  Shield,
  Zap,
  Server,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Activity,
  TrendingDown,
  Gauge,
  History,
  Loader2,
  Wifi,
  WifiOff,
  Flame,
  Bug,
  Target,
  BarChart3,
  ListOrdered,
  GitCompare,
  ArrowUpCircle,
  ShieldCheck,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// Severity colors and labels
const SEVERITY_COLORS = {
  LOW: "bg-green-500/20 text-green-500 border-green-500/30",
  MED: "bg-yellow-500/20 text-yellow-500 border-yellow-500/30",
  HIGH: "bg-orange-500/20 text-orange-500 border-orange-500/30",
  APOC: "bg-red-500/20 text-red-500 border-red-500/30",
};

const SEVERITY_LABELS = {
  LOW: "Mild Stress",
  MED: "Moderate Chaos",
  HIGH: "Severe Conditions",
  APOC: "Apocalyptic",
};

const GUARDIAN_COLORS = {
  SAFE: "bg-green-500/20 text-green-500",
  WARN: "bg-yellow-500/20 text-yellow-500",
  HALT: "bg-red-500/20 text-red-500",
};

const GUARDIAN_LABELS = {
  SAFE: "System Healthy",
  WARN: "Caution Advised", 
  HALT: "Trading Halted",
};

const Sandbox = () => {
  // Config state
  const [config, setConfig] = useState({
    symbols: ["BTCUSDT", "ETHUSDT"],
    packs: { crash: true, dex: true, infra: true },
    severity: "MED",
    duration_min: 30,
    seed: "",
  });

  // Run state
  const [isRunning, setIsRunning] = useState(false);
  const [currentRun, setCurrentRun] = useState(null);
  const [status, setStatus] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [recentRuns, setRecentRuns] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pollInterval, setPollInterval] = useState(null);
  const [activeTab, setActiveTab] = useState("config");
  
  // Promotion modal state
  const [promotionModalOpen, setPromotionModalOpen] = useState(false);
  
  // Agents for sniper hardening
  const [agents, setAgents] = useState([]);

  // Available symbols
  const availableSymbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"];

  // Fetch scenarios on mount
  useEffect(() => {
    fetchScenarios();
    fetchRecentRuns();
    fetchStatus();
    fetchAgents();
  }, []);

  // Polling for status during run
  useEffect(() => {
    if (isRunning && !pollInterval) {
      const interval = setInterval(() => {
        fetchStatus();
      }, 1500);
      setPollInterval(interval);
    } else if (!isRunning && pollInterval) {
      clearInterval(pollInterval);
      setPollInterval(null);
    }

    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [isRunning]);

  const fetchAgents = async () => {
    try {
      const response = await api.get("/agents");
      setAgents(response.data || []);
    } catch (error) {
      console.error("Failed to fetch agents:", error);
    }
  };

  const fetchScenarios = async () => {
    try {
      const response = await api.get("/sandbox/scenarios");
      setScenarios(response.data.scenarios || []);
    } catch (error) {
      console.error("Failed to fetch scenarios:", error);
    }
  };

  const fetchRecentRuns = async () => {
    try {
      const response = await api.get("/sandbox/runs?limit=10");
      setRecentRuns(response.data.runs || []);
    } catch (error) {
      console.error("Failed to fetch recent runs:", error);
    }
  };

  const fetchStatus = async () => {
    try {
      const response = await api.get("/sandbox/status");
      setStatus(response.data);
      
      if (response.data.run) {
        setCurrentRun(response.data.run);
        setIsRunning(response.data.run.status === "running");
        
        // Auto-switch to status tab when running
        if (response.data.run.status === "running" && activeTab === "config") {
          setActiveTab("status");
        }
        
        // Refresh runs list when completed
        if (response.data.run.status === "completed") {
          fetchRecentRuns();
        }
      } else {
        setIsRunning(false);
      }
    } catch (error) {
      console.error("Failed to fetch status:", error);
    }
  };

  const startRun = async () => {
    setLoading(true);
    try {
      const payload = {
        ...config,
        seed: config.seed ? parseInt(config.seed) : undefined,
      };
      
      const response = await api.post("/sandbox/run", payload);
      setCurrentRun(response.data);
      setIsRunning(true);
      setActiveTab("status");
      toast.success(`Sandbox run started: ${response.data.run_id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to start sandbox");
    } finally {
      setLoading(false);
    }
  };

  const stopRun = async () => {
    try {
      await api.post("/sandbox/stop");
      setIsRunning(false);
      toast.info("Sandbox run stopped");
      fetchStatus();
      fetchRecentRuns();
    } catch (error) {
      toast.error("Failed to stop sandbox");
    }
  };

  const loadReport = async (runId) => {
    try {
      const response = await api.get(`/sandbox/report/${runId}`);
      setSelectedReport(response.data);
      setActiveTab("report");
    } catch (error) {
      toast.error("Failed to load report");
    }
  };

  const exportReport = () => {
    if (!selectedReport) return;
    
    const blob = new Blob([JSON.stringify(selectedReport, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sandbox_report_${selectedReport.run_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Report exported");
  };

  const applyPreset = (preset) => {
    setConfig({
      ...config,
      packs: preset.packs,
      severity: preset.severity,
      duration_min: preset.duration_min,
    });
    toast.info(`Applied preset: ${preset.name}`);
  };

  const toggleSymbol = (symbol) => {
    const newSymbols = config.symbols.includes(symbol)
      ? config.symbols.filter((s) => s !== symbol)
      : [...config.symbols, symbol];
    
    if (newSymbols.length > 0) {
      setConfig({ ...config, symbols: newSymbols });
    }
  };

  const metrics = currentRun?.metrics || status?.run?.metrics || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#EAECEF]">Stress Sandbox</h1>
          <p className="text-[#848E9C] text-sm">Simulate extreme market conditions in PAPER mode</p>
        </div>
        
        {/* SIMULATION Badge */}
        <div className="flex items-center gap-3">
          <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] border border-[#F0B90B]/30 px-3 py-1">
            <FileText className="w-3 h-3 mr-1.5" />
            SIMULATION • PAPER
          </Badge>
          
          {isRunning && (
            <Badge className="bg-green-500/20 text-green-500 border border-green-500/30 animate-pulse">
              <Activity className="w-3 h-3 mr-1.5" />
              RUNNING
            </Badge>
          )}
        </div>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-[#1E2329] border border-white/8">
          <TabsTrigger value="config" className="data-[state=active]:bg-[#2B3139]">
            <Target className="w-4 h-4 mr-2" />
            Configure
          </TabsTrigger>
          <TabsTrigger value="status" className="data-[state=active]:bg-[#2B3139]">
            <Activity className="w-4 h-4 mr-2" />
            Status
          </TabsTrigger>
          <TabsTrigger value="report" className="data-[state=active]:bg-[#2B3139]">
            <BarChart3 className="w-4 h-4 mr-2" />
            Report
          </TabsTrigger>
          <TabsTrigger value="history" className="data-[state=active]:bg-[#2B3139]">
            <History className="w-4 h-4 mr-2" />
            History
          </TabsTrigger>
          <TabsTrigger value="sniper" className="data-[state=active]:bg-[#2B3139]">
            <ShieldCheck className="w-4 h-4 mr-2" />
            Sniper Hardening
          </TabsTrigger>
        </TabsList>

        {/* Configuration Tab */}
        <TabsContent value="config" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left: Config Panel */}
            <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
              <CardHeader>
                <CardTitle className="text-lg text-[#EAECEF]">Scenario Configuration</CardTitle>
                <CardDescription>Configure the stress test parameters</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Event Packs */}
                <div className="space-y-3">
                  <Label className="text-[#B7BDC6]">Event Packs</Label>
                  <div className="flex flex-wrap gap-4">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="crash"
                        checked={config.packs.crash}
                        onCheckedChange={(checked) =>
                          setConfig({ ...config, packs: { ...config.packs, crash: checked } })
                        }
                      />
                      <label htmlFor="crash" className="text-sm text-[#EAECEF] flex items-center gap-2 cursor-pointer">
                        <Flame className="w-4 h-4 text-red-500" />
                        Crash Events
                      </label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="dex"
                        checked={config.packs.dex}
                        onCheckedChange={(checked) =>
                          setConfig({ ...config, packs: { ...config.packs, dex: checked } })
                        }
                      />
                      <label htmlFor="dex" className="text-sm text-[#EAECEF] flex items-center gap-2 cursor-pointer">
                        <Zap className="w-4 h-4 text-yellow-500" />
                        DEX Events
                      </label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="infra"
                        checked={config.packs.infra}
                        onCheckedChange={(checked) =>
                          setConfig({ ...config, packs: { ...config.packs, infra: checked } })
                        }
                      />
                      <label htmlFor="infra" className="text-sm text-[#EAECEF] flex items-center gap-2 cursor-pointer">
                        <Server className="w-4 h-4 text-blue-500" />
                        Infra Events
                      </label>
                    </div>
                  </div>
                </div>

                {/* Severity & Duration */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-[#B7BDC6]">Severity</Label>
                    <Select value={config.severity} onValueChange={(v) => setConfig({ ...config, severity: v })}>
                      <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#2B3139] border-white/8">
                        <SelectItem value="LOW">
                          <span className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-green-500"></span>
                            LOW - Mild stress
                          </span>
                        </SelectItem>
                        <SelectItem value="MED">
                          <span className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                            MED - Moderate chaos
                          </span>
                        </SelectItem>
                        <SelectItem value="HIGH">
                          <span className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-orange-500"></span>
                            HIGH - Severe conditions
                          </span>
                        </SelectItem>
                        <SelectItem value="APOC">
                          <span className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-red-500"></span>
                            APOC - Apocalyptic
                          </span>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[#B7BDC6]">Duration</Label>
                    <Select 
                      value={config.duration_min.toString()} 
                      onValueChange={(v) => setConfig({ ...config, duration_min: parseInt(v) })}
                    >
                      <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#2B3139] border-white/8">
                        <SelectItem value="1">1 min (quick test)</SelectItem>
                        <SelectItem value="5">5 min</SelectItem>
                        <SelectItem value="30">30 min</SelectItem>
                        <SelectItem value="120">2 hours</SelectItem>
                        <SelectItem value="1440">24 hours</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Symbols */}
                <div className="space-y-2">
                  <Label className="text-[#B7BDC6]">Symbols</Label>
                  <div className="flex flex-wrap gap-2">
                    {availableSymbols.map((symbol) => (
                      <Button
                        key={symbol}
                        variant={config.symbols.includes(symbol) ? "default" : "outline"}
                        size="sm"
                        onClick={() => toggleSymbol(symbol)}
                        className={config.symbols.includes(symbol) 
                          ? "bg-[#F0B90B] text-[#0B0E11] hover:bg-[#D4A30A]" 
                          : "border-white/10 text-[#848E9C] hover:bg-white/5"
                        }
                      >
                        {symbol}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Seed */}
                <div className="space-y-2">
                  <Label className="text-[#B7BDC6]">Seed (optional, for reproducibility)</Label>
                  <Input
                    type="number"
                    placeholder="Leave empty for random"
                    value={config.seed}
                    onChange={(e) => setConfig({ ...config, seed: e.target.value })}
                    className="bg-[#2B3139] border-white/8 text-[#EAECEF] w-48"
                  />
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3 pt-4 border-t border-white/8">
                  <Button
                    onClick={startRun}
                    disabled={loading || isRunning || config.symbols.length === 0}
                    className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                  >
                    {loading ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 mr-2" />
                    )}
                    Run Sandbox
                  </Button>
                  
                  <Button
                    onClick={stopRun}
                    disabled={!isRunning}
                    variant="outline"
                    className="border-red-500/30 text-red-500 hover:bg-red-500/10"
                  >
                    <Square className="w-4 h-4 mr-2" />
                    Stop
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Right: Presets */}
            <Card className="bg-[#1E2329] border-white/8">
              <CardHeader>
                <CardTitle className="text-lg text-[#EAECEF]">Quick Presets</CardTitle>
                <CardDescription>Apply pre-configured scenarios</CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px] pr-4">
                  <div className="space-y-2">
                    {scenarios.map((preset) => (
                      <button
                        key={preset.id}
                        onClick={() => applyPreset(preset)}
                        className="w-full p-3 bg-[#2B3139] hover:bg-[#3B4149] rounded-lg text-left transition-colors"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-[#EAECEF] text-sm">{preset.name}</span>
                          <Badge className={`text-xs ${SEVERITY_COLORS[preset.severity]}`}>
                            {preset.severity}
                          </Badge>
                        </div>
                        <p className="text-xs text-[#848E9C]">{preset.description}</p>
                        <div className="flex gap-2 mt-2">
                          {preset.packs.crash && <Badge variant="outline" className="text-xs border-red-500/30 text-red-400">Crash</Badge>}
                          {preset.packs.dex && <Badge variant="outline" className="text-xs border-yellow-500/30 text-yellow-400">DEX</Badge>}
                          {preset.packs.infra && <Badge variant="outline" className="text-xs border-blue-500/30 text-blue-400">Infra</Badge>}
                        </div>
                      </button>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Status Tab */}
        <TabsContent value="status" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Metrics Panel */}
            <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg text-[#EAECEF]">Live Metrics</CardTitle>
                  <CardDescription>
                    {currentRun ? `Run: ${currentRun.run_id} | Seed: ${currentRun.seed}` : "No active run"}
                  </CardDescription>
                </div>
                <Button variant="ghost" size="sm" onClick={fetchStatus} className="text-[#848E9C]">
                  <RefreshCw className="w-4 h-4" />
                </Button>
              </CardHeader>
              <CardContent>
                {currentRun ? (
                  <div className="space-y-6">
                    {/* Survival Score */}
                    <div className="p-4 bg-[#2B3139] rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[#848E9C]">Survival Score</span>
                        <span className="text-2xl font-bold text-[#EAECEF]">
                          {metrics.survival_score?.toFixed(1) || "—"}/100
                        </span>
                      </div>
                      <Progress 
                        value={metrics.survival_score || 0} 
                        className="h-2 bg-[#0B0E11]"
                      />
                    </div>

                    {/* Key Metrics Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <MetricCard
                        icon={TrendingDown}
                        label="Max Drawdown"
                        value={`${metrics.max_dd_pct?.toFixed(2) || 0}%`}
                        color="text-red-500"
                      />
                      <MetricCard
                        icon={ListOrdered}
                        label="Events"
                        value={currentRun.events_processed || 0}
                        color="text-blue-500"
                      />
                      <MetricCard
                        icon={Gauge}
                        label="Slippage P95"
                        value={`${metrics.slippage_p95?.toFixed(2) || 0}%`}
                        color="text-yellow-500"
                      />
                      <MetricCard
                        icon={WifiOff}
                        label="WS Downtime"
                        value={`${metrics.ws_downtime_sec?.toFixed(0) || 0}s`}
                        color="text-orange-500"
                      />
                    </div>

                    {/* Guardian Status */}
                    <div className="flex items-center justify-between p-3 bg-[#2B3139] rounded-lg">
                      <span className="text-[#848E9C]">Guardian Status</span>
                      <div className="flex items-center gap-2">
                        <Badge className={GUARDIAN_COLORS[metrics.guardian_status] || GUARDIAN_COLORS.SAFE}>
                          <Shield className="w-3 h-3 mr-1.5" />
                          {metrics.guardian_status || "SAFE"}
                        </Badge>
                        <span className="text-xs text-[#848E9C]">
                          {GUARDIAN_LABELS[metrics.guardian_status] || GUARDIAN_LABELS.SAFE}
                        </span>
                      </div>
                    </div>

                    {/* Additional Stats */}
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div className="p-3 bg-[#2B3139] rounded-lg">
                        <div className="text-xl font-semibold text-[#EAECEF]">{metrics.total_trades || 0}</div>
                        <div className="text-xs text-[#848E9C]">Trades</div>
                      </div>
                      <div className="p-3 bg-[#2B3139] rounded-lg">
                        <div className="text-xl font-semibold text-green-500">{metrics.filled_trades || 0}</div>
                        <div className="text-xs text-[#848E9C]">Filled</div>
                      </div>
                      <div className="p-3 bg-[#2B3139] rounded-lg">
                        <div className="text-xl font-semibold text-red-500">{metrics.rejected_trades || 0}</div>
                        <div className="text-xs text-[#848E9C]">Rejected</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-[#848E9C]">
                    <Activity className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No active run. Configure and start a sandbox run.</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Status Panel */}
            <Card className="bg-[#1E2329] border-white/8">
              <CardHeader>
                <CardTitle className="text-lg text-[#EAECEF]">Run Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <StatusRow label="Status" value={
                    <Badge className={isRunning ? "bg-green-500/20 text-green-500" : "bg-[#2B3139] text-[#848E9C]"}>
                      {isRunning ? "Running" : currentRun?.status || "Idle"}
                    </Badge>
                  } />
                  <StatusRow label="Run ID" value={currentRun?.run_id || "—"} />
                  <StatusRow label="Seed" value={currentRun?.seed || "—"} />
                  <StatusRow label="Duration" value={`${currentRun?.duration_sec || 0}s`} />
                  <StatusRow label="Halts" value={metrics.halt_count || 0} />
                  <StatusRow label="Warns" value={metrics.warn_count || 0} />
                  <StatusRow label="MEV Hits" value={metrics.mev_hits_est || 0} />
                  <StatusRow label="Rate Limits" value={metrics.rate_limit_hits || 0} />
                </div>

                {currentRun && (
                  <Button
                    onClick={() => loadReport(currentRun.run_id)}
                    variant="outline"
                    className="w-full mt-4 border-white/10"
                  >
                    <BarChart3 className="w-4 h-4 mr-2" />
                    View Full Report
                  </Button>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Report Tab */}
        <TabsContent value="report" className="space-y-4">
          {selectedReport ? (
            <Card className="bg-[#1E2329] border-white/8">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg text-[#EAECEF]">
                    Report: {selectedReport.run_id}
                  </CardTitle>
                  <CardDescription>
                    Seed: {selectedReport.seed} | Duration: {selectedReport.duration_sec}s | 
                    Status: {selectedReport.status}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button 
                    onClick={() => setPromotionModalOpen(true)}
                    className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                  >
                    <ArrowUpCircle className="w-4 h-4 mr-2" />
                    Propose Promotion
                  </Button>
                  <Button onClick={exportReport} variant="outline" className="border-white/10">
                    <Download className="w-4 h-4 mr-2" />
                    Export JSON
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* Summary */}
                <div className="p-4 bg-[#0B0E11] rounded-lg mb-6 font-mono text-sm text-[#848E9C] whitespace-pre-wrap">
                  {selectedReport.summary}
                </div>

                {/* Events */}
                <div className="mb-6">
                  <h3 className="text-[#EAECEF] font-semibold mb-3 flex items-center gap-2">
                    <ListOrdered className="w-4 h-4" />
                    Events Injected ({selectedReport.events_injected?.length || 0})
                  </h3>
                  <ScrollArea className="h-[200px]">
                    <div className="space-y-2">
                      {selectedReport.events_injected?.slice(0, 50).map((event, idx) => (
                        <div key={idx} className="p-2 bg-[#2B3139] rounded text-xs">
                          <div className="flex items-center justify-between">
                            <span className="text-[#F0B90B] font-medium">{event.event_type}</span>
                            <span className="text-[#848E9C]">{event.timestamp?.split("T")[1]?.split(".")[0]}</span>
                          </div>
                          <div className="text-[#848E9C] truncate">{event.message}</div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>

                {/* Guardian Decisions */}
                {selectedReport.guardian_decisions?.length > 0 && (
                  <div>
                    <h3 className="text-[#EAECEF] font-semibold mb-3 flex items-center gap-2">
                      <Shield className="w-4 h-4" />
                      Guardian Decisions
                    </h3>
                    <div className="space-y-2">
                      {selectedReport.guardian_decisions.map((dec, idx) => (
                        <div key={idx} className="p-2 bg-[#2B3139] rounded flex items-center justify-between">
                          <Badge className={GUARDIAN_COLORS[dec.decision]}>{dec.decision}</Badge>
                          <span className="text-xs text-[#848E9C]">{dec.reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card className="bg-[#1E2329] border-white/8">
              <CardContent className="py-12 text-center text-[#848E9C]">
                <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Select a run from History to view its report</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-4">
          <Card className="bg-[#1E2329] border-white/8">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg text-[#EAECEF]">Recent Runs</CardTitle>
              <Button variant="ghost" size="sm" onClick={fetchRecentRuns} className="text-[#848E9C]">
                <RefreshCw className="w-4 h-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {recentRuns.length > 0 ? (
                  recentRuns.map((run) => (
                    <button
                      key={run.run_id}
                      onClick={() => loadReport(run.run_id)}
                      className="w-full p-3 bg-[#2B3139] hover:bg-[#3B4149] rounded-lg text-left transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <code className="text-[#F0B90B] text-sm">{run.run_id}</code>
                          <Badge className={
                            run.status === "completed" ? "bg-green-500/20 text-green-500" :
                            run.status === "running" ? "bg-blue-500/20 text-blue-500 animate-pulse" :
                            "bg-red-500/20 text-red-500"
                          }>
                            {run.status === "completed" && <CheckCircle2 className="w-3 h-3 mr-1" />}
                            {run.status === "running" && <Activity className="w-3 h-3 mr-1" />}
                            {run.status !== "completed" && run.status !== "running" && <AlertTriangle className="w-3 h-3 mr-1" />}
                            {run.status}
                          </Badge>
                        </div>
                        <span className="text-xs text-[#848E9C]">Seed: {run.seed}</span>
                      </div>
                      {run.config && (
                        <div className="flex items-center gap-2 mt-2 text-xs">
                          <Badge className={`${SEVERITY_COLORS[run.config.severity]} text-xs`}>
                            {run.config.severity}
                          </Badge>
                          <span className="text-[#848E9C]">•</span>
                          <span className="text-[#848E9C]">Duration: {run.config.duration_min}m</span>
                          {run.config.packs && (
                            <>
                              <span className="text-[#848E9C]">•</span>
                              <span className="text-[#848E9C]">
                                {[
                                  run.config.packs.crash && "Crash",
                                  run.config.packs.dex && "DEX",
                                  run.config.packs.infra && "Infra"
                                ].filter(Boolean).join(", ")}
                              </span>
                            </>
                          )}
                        </div>
                      )}
                    </button>
                  ))
                ) : (
                  <div className="text-center py-8 text-[#848E9C]">
                    <History className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No runs yet. Start a sandbox run to see history.</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Sniper Hardening Tab */}
        <TabsContent value="sniper" className="space-y-4">
          <SniperHardening recentRuns={recentRuns} agents={agents} />
        </TabsContent>
      </Tabs>

      {/* Promotion Modal */}
      <PromotionModal
        open={promotionModalOpen}
        onClose={(success) => {
          setPromotionModalOpen(false);
          if (success) {
            toast.success("Promotion request submitted. View in Promotions page.");
          }
        }}
        runId={selectedReport?.run_id}
        runReport={selectedReport}
      />
    </div>
  );
};

// Helper Components
const MetricCard = ({ icon: Icon, label, value, color }) => (
  <div className="p-3 bg-[#2B3139] rounded-lg">
    <div className="flex items-center gap-2 mb-1">
      <Icon className={`w-4 h-4 ${color}`} />
      <span className="text-xs text-[#848E9C]">{label}</span>
    </div>
    <div className="text-lg font-semibold text-[#EAECEF]">{value}</div>
  </div>
);

const StatusRow = ({ label, value }) => (
  <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
    <span className="text-[#848E9C] text-sm">{label}</span>
    <span className="text-[#EAECEF] text-sm font-medium">{typeof value === 'object' ? value : value}</span>
  </div>
);

export default Sandbox;
