import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Target,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info,
  Zap,
  Droplets,
  Receipt,
  Bug,
  TrendingDown,
  Activity,
  Server,
  Gauge,
  Ban,
  Sparkles,
  ArrowUpCircle,
  HelpCircle,
  Layers,
  Lock,
  Radio,
} from "lucide-react";
import PromotionModal from "@/components/PromotionModal";

// Gate status colors with consistent naming
const STATUS_COLORS = {
  PASS: "bg-green-500/20 text-green-500 border-green-500/30",
  WARN: "bg-yellow-500/20 text-yellow-500 border-yellow-500/30",
  FAIL: "bg-red-500/20 text-red-500 border-red-500/30",
};

const STATUS_ICONS = {
  PASS: CheckCircle2,
  WARN: AlertTriangle,
  FAIL: XCircle,
};

const STATUS_LABELS = {
  PASS: "SAFE",
  WARN: "CAUTION",
  FAIL: "BLOCKED",
};

// Gate icons
const GATE_ICONS = {
  LIQUIDITY_GATE: Droplets,
  TAX_GATE: Receipt,
  HONEYPOT_GATE: Bug,
  PRICE_IMPACT_GATE: TrendingDown,
  MEV_GATE: Zap,
  INFRA_STABILITY_GATE: Server,
  VOLATILITY_GATE: Activity,
  TOKEN_TRAP_GATE: Ban,
};

// Gate categories for grouping
const GATE_CATEGORIES = {
  "Liquidity & Market": ["LIQUIDITY_GATE", "PRICE_IMPACT_GATE", "VOLATILITY_GATE"],
  "Token Safety": ["TAX_GATE", "HONEYPOT_GATE", "TOKEN_TRAP_GATE"],
  "MEV & Slippage": ["MEV_GATE"],
  "Infrastructure": ["INFRA_STABILITY_GATE"],
};

const CATEGORY_ICONS = {
  "Liquidity & Market": Droplets,
  "Token Safety": Lock,
  "MEV & Slippage": Zap,
  "Infrastructure": Server,
};

const GATE_DESCRIPTIONS = {
  LIQUIDITY_GATE: "Checks pool liquidity depth and trade size ratio",
  TAX_GATE: "Detects fee-on-transfer tokens with excessive tax",
  HONEYPOT_GATE: "Verifies sell simulation passes (not a honeypot)",
  PRICE_IMPACT_GATE: "Evaluates estimated price impact",
  MEV_GATE: "Computes MEV/sandwich attack risk score",
  INFRA_STABILITY_GATE: "Checks WS stability, latency, and data freshness",
  VOLATILITY_GATE: "Detects volatility regime shifts and wide spreads",
  TOKEN_TRAP_GATE: "Checks for blacklist, maxTx/maxWallet, and trading toggles",
};

// Human-readable explanations for reason codes
const REASON_EXPLANATIONS = {
  // Liquidity
  INSUFFICIENT_LIQUIDITY: "Pool liquidity is too low for safe execution",
  TRADE_SIZE_TOO_LARGE: "Trade size is too large relative to pool depth",
  LIQUIDITY_OK: "Sufficient liquidity available",
  // Tax
  TAX_TOO_HIGH: "Token has excessive fee-on-transfer tax",
  TAX_APPROACHING_LIMIT: "Tax is close to the safety threshold",
  TAX_OK: "No excessive tax detected",
  // Honeypot
  SELL_SIMULATION_FAILED: "Token appears to be a honeypot (sell blocked)",
  SELL_SIMULATION_NOT_RUN: "Sell simulation was not performed",
  HONEYPOT_CHECK_OK: "Sell simulation passed successfully",
  // Price Impact
  PRICE_IMPACT_TOO_HIGH: "Trade would cause excessive price slippage",
  PRICE_IMPACT_HIGH: "Price impact is elevated but acceptable",
  PRICE_IMPACT_OK: "Price impact within safe limits",
  // MEV
  MEV_RISK_TOO_HIGH: "High risk of MEV/sandwich attacks",
  MEV_RISK_ELEVATED: "Moderate MEV risk detected",
  MEV_RISK_OK: "MEV risk is low",
  // Infra
  INFRA_UNSTABLE: "Infrastructure issues detected (WS drops, latency)",
  INFRA_DEGRADED: "Minor infrastructure degradation",
  INFRA_OK: "Infrastructure is stable",
  // Volatility
  VOLATILITY_REGIME_SHIFT_WITH_WIDE_SPREAD: "High volatility with wide spreads",
  VOLATILITY_REGIME_SHIFT: "Market volatility regime change detected",
  SPREAD_WIDE: "Bid-ask spread is wider than normal",
  VOLATILITY_OK: "Market conditions are stable",
  // Token Trap
  TOKEN_TRAP_DETECTED: "Token has dangerous restrictions or signals",
  TOKEN_RESTRICTIONS_DETECTED: "Token has maxTx/maxWallet limits",
  NO_TRAP_SIGNALS: "No token trap signals detected",
};

// Decision colors and explanations
const DECISION_COLORS = {
  ALLOW: "bg-green-500/20 text-green-500 border-green-500/30",
  WARN: "bg-yellow-500/20 text-yellow-500 border-yellow-500/30",
  BLOCK: "bg-red-500/20 text-red-500 border-red-500/30",
};

const DECISION_LABELS = {
  ALLOW: "SAFE TO PROCEED",
  WARN: "PROCEED WITH CAUTION",
  BLOCK: "TRADE BLOCKED",
};

const DECISION_ICONS = {
  ALLOW: CheckCircle2,
  WARN: AlertTriangle,
  BLOCK: XCircle,
};

const SniperHardening = ({ recentRuns = [], agents = [] }) => {
  // Form state
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [severity, setSeverity] = useState("MED");
  const [hardenedMode, setHardenedMode] = useState(true);
  
  // Mode selection: "dedicated_sniper" (Mode A) or "sniper_mode" (Mode B)
  const [mode, setMode] = useState("dedicated_sniper");
  const [strategyId, setStrategyId] = useState("sniper");
  
  // Simulation context (can be manually adjusted or loaded from run)
  const [context, setContext] = useState({
    pool_liquidity_usd: 100000,
    trade_size_usd: 500,
    detected_tax_pct: 0,
    sell_simulation_passed: true,
    estimated_price_impact_pct: 0.5,
    mev_events_count: 0,
    avg_slippage_pct: 0.1,
    ws_drops_per_hour: 0,
    api_latency_ms: 100,
    stale_data_detected: false,
    volatility_regime_shift: false,
    spread_pct: 0.1,
    blacklist_signals: false,
    trading_toggle_risk: false,
    max_tx_limit: false,
    max_wallet_limit: false,
  });
  
  // Results state
  const [evaluation, setEvaluation] = useState(null);
  const [generatedProfile, setGeneratedProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  
  // Promotion modal
  const [promotionModalOpen, setPromotionModalOpen] = useState(false);

  // Auto-select first run and agent
  useEffect(() => {
    if (recentRuns.length > 0 && !selectedRunId) {
      setSelectedRunId(recentRuns[0].run_id);
    }
  }, [recentRuns]);

  useEffect(() => {
    if (agents.length > 0 && !selectedAgentId) {
      const firstAgent = agents[0];
      setSelectedAgentId(firstAgent.id || firstAgent.agent_id || "sniper-agent-1");
      // Auto-set strategy based on agent type
      if (firstAgent.type && firstAgent.type !== "sniper") {
        setMode("sniper_mode");
        setStrategyId(firstAgent.type);
      }
    }
  }, [agents]);

  // Update strategy when agent changes
  const handleAgentChange = (agentId) => {
    setSelectedAgentId(agentId);
    const agent = agents.find(a => (a.id || a.agent_id) === agentId);
    if (agent && agent.type) {
      if (agent.type === "sniper") {
        setMode("dedicated_sniper");
        setStrategyId("sniper");
      } else {
        setMode("sniper_mode");
        setStrategyId(agent.type);
      }
    }
  };

  const handleEvaluate = async () => {
    if (!selectedRunId || !selectedAgentId || !symbol) {
      toast.error("Please fill all required fields");
      return;
    }

    setLoading(true);
    setEvaluation(null);
    setGeneratedProfile(null);

    try {
      const payload = {
        run_id: selectedRunId,
        agent_id: selectedAgentId,
        symbol: symbol,
        strategy_id: strategyId,
        severity: severity,
        mode: mode,
        venue_type: "SIM_SANDBOX",
        packs: { crash: true, dex: true, infra: true },
        ...context,
      };

      const response = await api.post("/sniper/hardening/evaluate", payload);
      setEvaluation(response.data);
      
      const decisionEmoji = response.data.decision === "ALLOW" ? "✅" : 
                           response.data.decision === "WARN" ? "⚠️" : "🛑";
      toast.success(`${decisionEmoji} Decision: ${response.data.decision}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Evaluation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateProfile = async () => {
    if (!evaluation) {
      toast.error("Run evaluation first");
      return;
    }

    setGenerating(true);

    try {
      const modeLabel = mode === "dedicated_sniper" ? "Sniper" : "SniperMode";
      const payload = {
        evaluation_id: evaluation.evaluation_id,
        strategy_id: strategyId,
        label: `${modeLabel} ${severity} - ${symbol}`,
        severity: severity,
      };

      const response = await api.post("/sniper/hardening/generate-profile", payload);
      setGeneratedProfile(response.data);
      toast.success(`Profile generated: ${response.data.profile_id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Profile generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const getRiskColor = (score) => {
    if (score < 30) return "text-green-500";
    if (score < 60) return "text-yellow-500";
    return "text-red-500";
  };

  const getRiskLabel = (score) => {
    if (score < 30) return "Low Risk";
    if (score < 60) return "Medium Risk";
    if (score < 80) return "High Risk";
    return "Critical Risk";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-[#EAECEF] flex items-center gap-2">
            <Shield className="w-5 h-5 text-[#F0B90B]" />
            Sniper Hardening Mode
          </h2>
          <p className="text-[#848E9C] text-sm">
            Evaluate and harden sniper entries against DEX/MEV/infra risks
          </p>
        </div>
        <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] border border-[#F0B90B]/30">
          SIMULATION ONLY
        </Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <Card className="bg-[#1E2329] border-white/8">
          <CardHeader>
            <CardTitle className="text-lg text-[#EAECEF]">Configuration</CardTitle>
            <CardDescription>Set up evaluation parameters</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Run Selection */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Sandbox Run</Label>
              <Select value={selectedRunId} onValueChange={setSelectedRunId}>
                <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                  <SelectValue placeholder="Select run" />
                </SelectTrigger>
                <SelectContent className="bg-[#2B3139] border-white/8">
                  {recentRuns.map((run) => (
                    <SelectItem key={run.run_id} value={run.run_id}>
                      {run.run_id} ({run.status})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Agent Selection */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Agent</Label>
              <Select value={selectedAgentId} onValueChange={handleAgentChange}>
                <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                  <SelectValue placeholder="Select agent" />
                </SelectTrigger>
                <SelectContent className="bg-[#2B3139] border-white/8">
                  {agents.length > 0 ? (
                    agents.map((agent) => (
                      <SelectItem key={agent.id || agent.agent_id} value={agent.id || agent.agent_id}>
                        {agent.id || agent.agent_id} ({agent.type || "sniper"})
                      </SelectItem>
                    ))
                  ) : (
                    <SelectItem value="sniper-agent-1">sniper-agent-1</SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>

            {/* Mode Selection */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Hardening Mode</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    setMode("dedicated_sniper");
                    setStrategyId("sniper");
                  }}
                  className={`p-3 rounded-lg border text-left transition-colors ${
                    mode === "dedicated_sniper"
                      ? "bg-[#F0B90B]/10 border-[#F0B90B]/50 text-[#EAECEF]"
                      : "bg-[#2B3139] border-white/8 text-[#848E9C] hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Target className="w-4 h-4" />
                    <span className="text-sm font-medium">Mode A</span>
                  </div>
                  <div className="text-xs mt-1 opacity-70">Dedicated Sniper</div>
                </button>
                <button
                  onClick={() => setMode("sniper_mode")}
                  className={`p-3 rounded-lg border text-left transition-colors ${
                    mode === "sniper_mode"
                      ? "bg-[#F0B90B]/10 border-[#F0B90B]/50 text-[#EAECEF]"
                      : "bg-[#2B3139] border-white/8 text-[#848E9C] hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4" />
                    <span className="text-sm font-medium">Mode B</span>
                  </div>
                  <div className="text-xs mt-1 opacity-70">Sniper Mode (Any Agent)</div>
                </button>
              </div>
            </div>

            {/* Strategy ID (for Mode B) */}
            {mode === "sniper_mode" && (
              <div className="space-y-2">
                <Label className="text-[#B7BDC6]">Strategy ID</Label>
                <Select value={strategyId} onValueChange={setStrategyId}>
                  <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#2B3139] border-white/8">
                    <SelectItem value="grid">Grid</SelectItem>
                    <SelectItem value="dca">DCA</SelectItem>
                    <SelectItem value="momentum">Momentum</SelectItem>
                    <SelectItem value="arbitrage">Arbitrage</SelectItem>
                    <SelectItem value="scalper">Scalper</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Symbol */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Symbol</Label>
              <Select value={symbol} onValueChange={setSymbol}>
                <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2B3139] border-white/8">
                  <SelectItem value="BTCUSDT">BTCUSDT</SelectItem>
                  <SelectItem value="ETHUSDT">ETHUSDT</SelectItem>
                  <SelectItem value="BNBUSDT">BNBUSDT</SelectItem>
                  <SelectItem value="SOLUSDT">SOLUSDT</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Severity */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Severity</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2B3139] border-white/8">
                  <SelectItem value="LOW">LOW - More lenient</SelectItem>
                  <SelectItem value="MED">MED - Balanced</SelectItem>
                  <SelectItem value="HIGH">HIGH - Stricter</SelectItem>
                  <SelectItem value="APOC">APOC - Maximum safety</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Hardened Mode Toggle */}
            <div className="flex items-center justify-between p-3 bg-[#2B3139] rounded-lg">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#F0B90B]" />
                <span className="text-sm text-[#EAECEF]">Hardened Mode</span>
              </div>
              <Switch
                checked={hardenedMode}
                onCheckedChange={setHardenedMode}
              />
            </div>

            {/* Context Inputs (collapsible) */}
            <div className="space-y-2 pt-2 border-t border-white/8">
              <Label className="text-[#848E9C] text-xs uppercase">Simulation Context</Label>
              
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs text-[#848E9C]">Pool Liquidity ($)</Label>
                  <Input
                    type="number"
                    value={context.pool_liquidity_usd}
                    onChange={(e) => setContext({ ...context, pool_liquidity_usd: parseFloat(e.target.value) || 0 })}
                    className="bg-[#2B3139] border-white/8 text-[#EAECEF] text-sm h-8"
                  />
                </div>
                <div>
                  <Label className="text-xs text-[#848E9C]">Trade Size ($)</Label>
                  <Input
                    type="number"
                    value={context.trade_size_usd}
                    onChange={(e) => setContext({ ...context, trade_size_usd: parseFloat(e.target.value) || 0 })}
                    className="bg-[#2B3139] border-white/8 text-[#EAECEF] text-sm h-8"
                  />
                </div>
                <div>
                  <Label className="text-xs text-[#848E9C]">Tax %</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={context.detected_tax_pct}
                    onChange={(e) => setContext({ ...context, detected_tax_pct: parseFloat(e.target.value) || 0 })}
                    className="bg-[#2B3139] border-white/8 text-[#EAECEF] text-sm h-8"
                  />
                </div>
                <div>
                  <Label className="text-xs text-[#848E9C]">Price Impact %</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={context.estimated_price_impact_pct}
                    onChange={(e) => setContext({ ...context, estimated_price_impact_pct: parseFloat(e.target.value) || 0 })}
                    className="bg-[#2B3139] border-white/8 text-[#EAECEF] text-sm h-8"
                  />
                </div>
              </div>
            </div>

            {/* Evaluate Button */}
            <Button
              onClick={handleEvaluate}
              disabled={loading || !selectedRunId}
              className="w-full bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Target className="w-4 h-4 mr-2" />
              )}
              Evaluate Gates
            </Button>
          </CardContent>
        </Card>

        {/* Results Panel */}
        <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
          <CardHeader>
            <CardTitle className="text-lg text-[#EAECEF]">Gate Results</CardTitle>
            <CardDescription>
              {evaluation ? `Evaluation: ${evaluation.evaluation_id}` : "Run evaluation to see results"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {evaluation ? (
              <div className="space-y-6">
                {/* Decision Banner */}
                <div className={`p-4 rounded-lg border ${DECISION_COLORS[evaluation.decision]}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {(() => {
                        const DecisionIcon = DECISION_ICONS[evaluation.decision];
                        return <DecisionIcon className="w-6 h-6" />;
                      })()}
                      <div>
                        <div className="font-bold text-lg flex items-center gap-2">
                          {DECISION_LABELS[evaluation.decision]}
                          <Badge className={`${DECISION_COLORS[evaluation.decision]} text-xs`}>
                            {evaluation.decision}
                          </Badge>
                        </div>
                        <div className="text-sm opacity-80 mt-1">
                          {evaluation.decision === "ALLOW" && "All safety gates passed. Entry conditions are favorable."}
                          {evaluation.decision === "WARN" && "Some gates raised concerns. Review before proceeding."}
                          {evaluation.decision === "BLOCK" && "Critical safety gate failed. Entry blocked for protection."}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <Badge variant="outline" className="border-white/20 text-[#848E9C] mb-1">
                        {evaluation.mode === "dedicated_sniper" ? "Mode A: Dedicated Sniper" : "Mode B: Sniper Mode"}
                      </Badge>
                      {evaluation.top_failing_gate && (
                        <div className="text-xs text-red-400 mt-1">
                          ⚠ Top Issue: {evaluation.top_failing_gate.replace(/_/g, " ")}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Summary Row */}
                <div className="grid grid-cols-4 gap-4">
                  <div className="p-3 bg-[#2B3139] rounded-lg text-center">
                    <div className={`text-2xl font-bold ${getRiskColor(evaluation.risk_score)}`}>
                      {evaluation.risk_score.toFixed(0)}
                    </div>
                    <div className="text-xs text-[#848E9C]">Risk Score</div>
                    <div className={`text-xs ${getRiskColor(evaluation.risk_score)}`}>
                      {getRiskLabel(evaluation.risk_score)}
                    </div>
                  </div>
                  <div className="p-3 bg-[#2B3139] rounded-lg text-center">
                    <div className={`text-2xl font-bold ${getRiskColor(evaluation.mev_risk)}`}>
                      {evaluation.mev_risk.toFixed(0)}
                    </div>
                    <div className="text-xs text-[#848E9C]">MEV Risk</div>
                  </div>
                  <div className="p-3 bg-[#2B3139] rounded-lg text-center">
                    <div className="text-2xl font-bold text-[#EAECEF]">
                      {evaluation.recommended_position_size_pct}%
                    </div>
                    <div className="text-xs text-[#848E9C]">Rec. Size</div>
                  </div>
                  <div className="p-3 bg-[#2B3139] rounded-lg text-center">
                    <Badge className={STATUS_COLORS[evaluation.overall_status]}>
                      {STATUS_LABELS[evaluation.overall_status] || evaluation.overall_status}
                    </Badge>
                    <div className="text-xs text-[#848E9C] mt-1">
                      <span className="text-green-500">{evaluation.passed_count}✓</span>
                      {" "}<span className="text-yellow-500">{evaluation.warn_count}⚠</span>
                      {" "}<span className="text-red-500">{evaluation.failed_count}✗</span>
                    </div>
                  </div>
                </div>

                {/* Gates List - Grouped by Category */}
                <ScrollArea className="h-[300px]">
                  <div className="space-y-4">
                    <TooltipProvider>
                      {Object.entries(GATE_CATEGORIES).map(([category, gateNames]) => {
                        const categoryGates = evaluation.gates.filter(g => gateNames.includes(g.name));
                        if (categoryGates.length === 0) return null;
                        
                        const CategoryIcon = CATEGORY_ICONS[category] || Shield;
                        const categoryPassed = categoryGates.filter(g => g.status === "PASS").length;
                        const categoryTotal = categoryGates.length;
                        
                        return (
                          <div key={category} className="space-y-2">
                            {/* Category Header */}
                            <div className="flex items-center justify-between px-2">
                              <div className="flex items-center gap-2">
                                <CategoryIcon className="w-4 h-4 text-[#F0B90B]" />
                                <span className="text-sm font-medium text-[#B7BDC6]">{category}</span>
                              </div>
                              <span className="text-xs text-[#848E9C]">
                                {categoryPassed}/{categoryTotal} passed
                              </span>
                            </div>
                            
                            {/* Gates in Category */}
                            <div className="space-y-1">
                              {categoryGates.map((gate, idx) => {
                                const GateIcon = GATE_ICONS[gate.name] || Shield;
                                const StatusIcon = STATUS_ICONS[gate.status];
                                const explanation = REASON_EXPLANATIONS[gate.reason_code] || gate.reason_code;
                                
                                return (
                                  <div
                                    key={idx}
                                    className="p-3 bg-[#2B3139] rounded-lg"
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-3">
                                        <GateIcon className="w-4 h-4 text-[#848E9C]" />
                                        <div>
                                          <div className="text-sm font-medium text-[#EAECEF]">
                                            {gate.name.replace(/_/g, " ").replace("GATE", "").trim()}
                                          </div>
                                          <div className="text-xs text-[#848E9C]">
                                            {GATE_DESCRIPTIONS[gate.name]}
                                          </div>
                                        </div>
                                      </div>
                                      <Badge className={`${STATUS_COLORS[gate.status]} border`}>
                                        <StatusIcon className="w-3 h-3 mr-1" />
                                        {STATUS_LABELS[gate.status] || gate.status}
                                      </Badge>
                                    </div>
                                    
                                    {/* Human-readable explanation */}
                                    <div className={`mt-2 p-2 rounded text-xs ${
                                      gate.status === "PASS" ? "bg-green-500/10 text-green-400" :
                                      gate.status === "WARN" ? "bg-yellow-500/10 text-yellow-400" :
                                      "bg-red-500/10 text-red-400"
                                    }`}>
                                      {gate.status === "PASS" && "✓ "}
                                      {gate.status === "WARN" && "⚠ "}
                                      {gate.status === "FAIL" && "✗ "}
                                      {explanation}
                                      {gate.threshold !== null && gate.actual_value !== null && (
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <span className="ml-2 cursor-help underline decoration-dotted">
                                              (details)
                                            </span>
                                          </TooltipTrigger>
                                          <TooltipContent className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                                            <p className="text-xs">Threshold: {gate.threshold}</p>
                                            <p className="text-xs">Actual: {gate.actual_value}</p>
                                          </TooltipContent>
                                        </Tooltip>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </TooltipProvider>
                  </div>
                </ScrollArea>

                {/* Action Buttons */}
                <div className="flex items-center gap-3 pt-4 border-t border-white/8">
                  <Button
                    onClick={handleGenerateProfile}
                    disabled={generating || !evaluation}
                    className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                  >
                    {generating ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4 mr-2" />
                    )}
                    Generate Hardened Profile
                  </Button>
                  
                  {generatedProfile && (
                    <Button
                      onClick={() => setPromotionModalOpen(true)}
                      variant="outline"
                      className="border-white/10"
                    >
                      <ArrowUpCircle className="w-4 h-4 mr-2" />
                      Propose Promotion
                    </Button>
                  )}
                </div>

                {/* Generated Profile Info */}
                {generatedProfile && (
                  <div className="p-4 bg-[#0B0E11] rounded-lg border border-green-500/30">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="w-5 h-5 text-green-500" />
                        <span className="font-medium text-[#EAECEF]">Hardened Profile Generated</span>
                      </div>
                      <Badge className="bg-[#F0B90B]/20 text-[#F0B90B]">
                        {generatedProfile.mode === "dedicated_sniper" ? "Mode A: Sniper" : "Mode B: Sniper Mode"}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-[#848E9C]">Profile ID:</span>
                        <code className="ml-2 text-[#F0B90B]">{generatedProfile.profile_id}</code>
                      </div>
                      <div>
                        <span className="text-[#848E9C]">Strategy:</span>
                        <span className="ml-2 text-[#EAECEF]">{generatedProfile.strategy_id}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C]">Version:</span>
                        <span className="ml-2 text-[#EAECEF]">{generatedProfile.version}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C]">Risk Score:</span>
                        <span className={`ml-2 ${getRiskColor(generatedProfile.risk_score)}`}>
                          {generatedProfile.risk_score.toFixed(0)}
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-[#848E9C]">Params stored in:</span>
                        <code className="ml-2 text-[#EAECEF]">
                          {generatedProfile.mode === "dedicated_sniper" ? "params.sniper" : "params.sniper_mode"}
                        </code>
                      </div>
                      <div className="col-span-2">
                        <span className="text-[#848E9C]">Tags:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {generatedProfile.tags.slice(0, 5).map((tag, i) => (
                            <Badge key={i} variant="outline" className="text-xs border-white/20">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-16 text-center text-[#848E9C]">
                <Shield className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p className="text-lg">No evaluation yet</p>
                <p className="text-sm">Configure parameters and click &quot;Evaluate Gates&quot;</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Promotion Modal */}
      <PromotionModal
        open={promotionModalOpen}
        onClose={(success) => {
          setPromotionModalOpen(false);
          if (success) {
            toast.success("Promotion request created from hardened profile");
          }
        }}
        runId={selectedRunId}
        runReport={null}
      />
    </div>
  );
};

export default SniperHardening;
