import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { 
  Play, 
  TrendingUp,
  TrendingDown,
  BarChart3,
  Target,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Zap,
  FileCheck
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell
} from 'recharts';

const TIMEFRAMES = ["1m", "5m", "15m", "1h"];
const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"];

const MetricCard = ({ label, value, format = "number", trend = null, small = false }) => {
  const formatValue = (v, f) => {
    if (v === undefined || v === null) return "-";
    if (f === "percent") return `${v?.toFixed(2)}%`;
    if (f === "currency") return `$${v?.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    if (f === "ratio") return v === "∞" ? "∞" : v?.toFixed(2);
    if (f === "score") return `${v}/100`;
    return v?.toFixed?.(2) ?? v;
  };

  return (
    <div className={`p-3 bg-secondary/30 border border-border ${small ? 'p-2' : ''}`}>
      <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className={`font-mono font-bold mt-1 ${small ? 'text-sm' : 'text-lg'} ${
        trend === "positive" ? "text-profit" : 
        trend === "negative" ? "text-loss" : ""
      }`}>
        {formatValue(value, format)}
      </p>
    </div>
  );
};

const GoLiveIndicator = ({ recommendation, score }) => {
  const config = {
    GO: { color: "text-profit", bg: "bg-profit/20", icon: CheckCircle, label: "GO LIVE" },
    CONDITIONAL_GO: { color: "text-yellow-500", bg: "bg-yellow-500/20", icon: AlertTriangle, label: "CONDITIONAL" },
    NO_GO: { color: "text-loss", bg: "bg-loss/20", icon: XCircle, label: "NO GO" }
  };
  
  const c = config[recommendation] || config.NO_GO;
  
  return (
    <div className={`p-4 ${c.bg} border border-border flex items-center justify-between`}>
      <div className="flex items-center gap-3">
        <c.icon className={`w-8 h-8 ${c.color}`} />
        <div>
          <p className={`text-xl font-rajdhani font-bold ${c.color}`}>{c.label}</p>
          <p className="text-sm text-muted-foreground">Recommendation</p>
        </div>
      </div>
      <div className="text-right">
        <p className="text-3xl font-mono font-bold">{score}</p>
        <p className="text-xs text-muted-foreground">/ 100</p>
      </div>
    </div>
  );
};

const WindowCard = ({ window }) => {
  const testPnl = window.test_metrics?.total_pnl || 0;
  const isPositive = testPnl >= 0;
  
  return (
    <div className="p-3 bg-secondary/20 border border-border">
      <div className="flex items-center justify-between mb-2">
        <Badge variant="outline" className="font-mono text-xs">Window {window.window_id}</Badge>
        <span className={`font-mono text-sm ${isPositive ? 'text-profit' : 'text-loss'}`}>
          {isPositive ? '+' : ''}${testPnl.toFixed(2)}
        </span>
      </div>
      <div className="text-xs text-muted-foreground space-y-1">
        <p>Train: {window.train_period}</p>
        <p>Test: {window.test_period}</p>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
        <div>
          <span className="text-muted-foreground">Sharpe</span>
          <p className="font-mono">{window.test_metrics?.sharpe_ratio?.toFixed(2) || '-'}</p>
        </div>
        <div>
          <span className="text-muted-foreground">WR</span>
          <p className="font-mono">{window.test_metrics?.win_rate?.toFixed(1)}%</p>
        </div>
        <div>
          <span className="text-muted-foreground">Trades</span>
          <p className="font-mono">{window.test_trades_count}</p>
        </div>
      </div>
    </div>
  );
};

export default function WalkForward() {
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [trainDays, setTrainDays] = useState(90);
  const [testDays, setTestDays] = useState(30);
  const [stepDays, setStepDays] = useState(30);
  const [initialCapital, setInitialCapital] = useState(10000);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState([]);
  const [currentResult, setCurrentResult] = useState(null);
  const [goLiveSummary, setGoLiveSummary] = useState(null);
  
  useEffect(() => {
    fetchAgents();
    fetchResults();
    fetchGoLiveSummary();
  }, []);
  
  const fetchAgents = async () => {
    try {
      const response = await axios.get(`${API}/agents`);
      setAgents(response.data);
      if (response.data.length > 0) {
        setSelectedAgent(response.data[0].id);
        setSymbol(response.data[0].symbol);
      }
    } catch (e) {
      console.error(e);
    }
  };
  
  const fetchResults = async () => {
    try {
      const response = await axios.get(`${API}/wfo/results`);
      setResults(response.data);
    } catch (e) {
      console.error(e);
    }
  };
  
  const fetchGoLiveSummary = async () => {
    try {
      const response = await axios.get(`${API}/go-live/summary`);
      setGoLiveSummary(response.data);
    } catch (e) {
      console.error(e);
    }
  };
  
  const runWFO = async () => {
    if (!selectedAgent) {
      toast.error("Select an agent first");
      return;
    }
    
    setRunning(true);
    try {
      const response = await axios.post(`${API}/wfo/run`, {
        agent_id: selectedAgent,
        symbol,
        timeframe,
        train_days: trainDays,
        test_days: testDays,
        step_days: stepDays,
        initial_capital: initialCapital
      });
      
      toast.success(`WFO complete: ${response.data.summary?.n_windows || 0} windows analyzed`);
      setCurrentResult(response.data);
      fetchResults();
      fetchGoLiveSummary();
    } catch (e) {
      toast.error(e.response?.data?.detail || "WFO analysis failed");
    } finally {
      setRunning(false);
    }
  };
  
  const decision = currentResult?.go_live_decision || {};
  const oosPerf = currentResult?.oos_performance || {};
  const distMetrics = currentResult?.distribution_metrics || {};
  const stability = currentResult?.stability_analysis || {};
  const monteCarlo = currentResult?.monte_carlo || {};
  const sensitivity = currentResult?.sensitivity || {};
  
  return (
    <div className="p-4 lg:p-6 space-y-6" data-testid="wfo-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-rajdhani font-bold tracking-wide">WALK-FORWARD OPTIMIZATION</h1>
          <p className="text-sm text-muted-foreground">
            Validate strategies with out-of-sample testing
          </p>
        </div>
        {goLiveSummary && (
          <Badge 
            variant={goLiveSummary.is_ready_for_live ? "default" : "secondary"}
            className="font-mono"
          >
            {goLiveSummary.strategies_ready} strategies ready
          </Badge>
        )}
      </div>
      
      {/* Config Panel */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg flex items-center gap-2">
            <Target className="w-5 h-5" />
            WFO Configuration
          </CardTitle>
          <CardDescription>
            Train: {trainDays}d → Test: {testDays}d → Step: {stepDays}d
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-8 gap-4">
            <div className="space-y-2">
              <Label>Agent</Label>
              <Select value={selectedAgent} onValueChange={setSelectedAgent}>
                <SelectTrigger data-testid="select-agent">
                  <SelectValue placeholder="Select" />
                </SelectTrigger>
                <SelectContent>
                  {agents.map(a => (
                    <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>Symbol</Label>
              <Select value={symbol} onValueChange={setSymbol}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SYMBOLS.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>Timeframe</Label>
              <Select value={timeframe} onValueChange={setTimeframe}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>Train (days)</Label>
              <Input type="number" value={trainDays} onChange={(e) => setTrainDays(parseInt(e.target.value))} />
            </div>
            
            <div className="space-y-2">
              <Label>Test (days)</Label>
              <Input type="number" value={testDays} onChange={(e) => setTestDays(parseInt(e.target.value))} />
            </div>
            
            <div className="space-y-2">
              <Label>Step (days)</Label>
              <Input type="number" value={stepDays} onChange={(e) => setStepDays(parseInt(e.target.value))} />
            </div>
            
            <div className="space-y-2">
              <Label>Capital</Label>
              <Input type="number" value={initialCapital} onChange={(e) => setInitialCapital(parseFloat(e.target.value))} />
            </div>
            
            <div className="space-y-2 flex items-end">
              <Button 
                onClick={runWFO} 
                disabled={running} 
                className="w-full btn-sharp"
                data-testid="btn-run-wfo"
              >
                <Play className="w-4 h-4 mr-2" />
                {running ? "Running..." : "Run WFO"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      
      {/* Results */}
      {currentResult && (
        <div className="space-y-4">
          {/* Go/No-Go Decision */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-1">
              <GoLiveIndicator 
                recommendation={decision.recommendation} 
                score={decision.score}
              />
            </div>
            
            <Card className="lg:col-span-2 border-border bg-background">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
                  Decision Factors
                </CardTitle>
              </CardHeader>
              <CardContent>
                {decision.issues?.length > 0 ? (
                  <div className="space-y-2">
                    {decision.issues.map((issue, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm text-loss">
                        <XCircle className="w-4 h-4" />
                        {issue}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-profit">
                    <CheckCircle className="w-5 h-5" />
                    <span>All checks passed!</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
          
          {/* OOS Performance */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <MetricCard 
              label="OOS Total P&L" 
              value={oosPerf.total_pnl} 
              format="currency"
              trend={oosPerf.total_pnl >= 0 ? "positive" : "negative"}
            />
            <MetricCard 
              label="OOS P&L %" 
              value={oosPerf.total_pnl_pct} 
              format="percent"
              trend={oosPerf.total_pnl_pct >= 0 ? "positive" : "negative"}
            />
            <MetricCard 
              label="OOS Win Rate" 
              value={oosPerf.win_rate} 
              format="percent"
              trend={oosPerf.win_rate >= 50 ? "positive" : "negative"}
            />
            <MetricCard 
              label="Stability Score" 
              value={stability.stability_score} 
              format="score"
              trend={stability.stability_score >= 60 ? "positive" : "negative"}
            />
            <MetricCard 
              label="Train→Test Degradation" 
              value={stability.train_vs_test_degradation_pct} 
              format="percent"
              trend={stability.train_vs_test_degradation_pct < 30 ? "positive" : "negative"}
            />
            <MetricCard 
              label="OOS Trades" 
              value={oosPerf.total_trades}
            />
          </div>
          
          {/* Detailed Metrics */}
          <Tabs defaultValue="distribution">
            <TabsList>
              <TabsTrigger value="distribution">Distribution</TabsTrigger>
              <TabsTrigger value="robustness">Robustness</TabsTrigger>
              <TabsTrigger value="windows">Windows ({currentResult?.windows?.length || 0})</TabsTrigger>
            </TabsList>
            
            <TabsContent value="distribution" className="mt-4">
              <Card className="border-border bg-background">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
                    Metrics Distribution Across Windows
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="space-y-2">
                      <Label className="text-xs">Sharpe Ratio</Label>
                      <div className="grid grid-cols-3 gap-2">
                        <MetricCard label="Min" value={distMetrics.min_sharpe} format="ratio" small />
                        <MetricCard label="Median" value={distMetrics.median_sharpe} format="ratio" small />
                        <MetricCard label="Max" value={distMetrics.max_sharpe} format="ratio" small />
                      </div>
                      <p className="text-xs text-muted-foreground">Std: {distMetrics.std_sharpe?.toFixed(3)}</p>
                    </div>
                    
                    <MetricCard 
                      label="Median Profit Factor" 
                      value={distMetrics.median_profit_factor} 
                      format="ratio"
                      trend={distMetrics.median_profit_factor >= 1.5 ? "positive" : distMetrics.median_profit_factor >= 1 ? null : "negative"}
                    />
                    <MetricCard 
                      label="Median Expectancy" 
                      value={distMetrics.median_expectancy} 
                      format="currency"
                      trend={distMetrics.median_expectancy >= 0 ? "positive" : "negative"}
                    />
                    <MetricCard 
                      label="Worst Drawdown" 
                      value={distMetrics.worst_drawdown} 
                      format="percent"
                      trend="negative"
                    />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
            
            <TabsContent value="robustness" className="mt-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Monte Carlo */}
                <Card className="border-border bg-background">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                      <Zap className="w-4 h-4" />
                      Monte Carlo Simulation
                    </CardTitle>
                    <CardDescription>1000 simulations with shuffled trades</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <MetricCard 
                        label="Median Max DD" 
                        value={monteCarlo.median_max_dd} 
                        format="percent"
                      />
                      <MetricCard 
                        label="95th Percentile DD" 
                        value={monteCarlo["95_percentile_dd"]} 
                        format="percent"
                        trend={monteCarlo["95_percentile_dd"] < 20 ? "positive" : "negative"}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      {monteCarlo["95_percentile_dd"] < 20 
                        ? "✓ Strategy robust to trade sequence variations"
                        : "⚠ High DD variance - strategy may be sensitive to trade order"}
                    </p>
                  </CardContent>
                </Card>
                
                {/* Sensitivity */}
                <Card className="border-border bg-background">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                      <Shield className="w-4 h-4" />
                      Fee Sensitivity Analysis
                    </CardTitle>
                    <CardDescription>P&L with ±20% fee variation</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <MetricCard 
                        label="P&L (+20% fees)" 
                        value={sensitivity.pnl_with_higher_fees} 
                        format="currency"
                        trend={sensitivity.pnl_with_higher_fees >= 0 ? "positive" : "negative"}
                      />
                      <MetricCard 
                        label="P&L (-20% fees)" 
                        value={sensitivity.pnl_with_lower_fees} 
                        format="currency"
                        trend="positive"
                      />
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      {sensitivity.is_robust ? (
                        <Badge variant="default" className="bg-profit">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          Robust to fees
                        </Badge>
                      ) : (
                        <Badge variant="destructive">
                          <XCircle className="w-3 h-3 mr-1" />
                          Not robust
                        </Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
            
            <TabsContent value="windows" className="mt-4">
              <Card className="border-border bg-background">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
                    Out-of-Sample Windows
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {currentResult?.windows?.map(window => (
                      <WindowCard key={window.window_id} window={window} />
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      )}
      
      {/* History */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
            WFO History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full table-terminal">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2">Agent</th>
                  <th className="text-left py-2 px-2">Symbol</th>
                  <th className="text-right py-2 px-2">Windows</th>
                  <th className="text-right py-2 px-2">OOS P&L</th>
                  <th className="text-right py-2 px-2">Stability</th>
                  <th className="text-right py-2 px-2">Score</th>
                  <th className="text-center py-2 px-2">Decision</th>
                  <th className="text-right py-2 px-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr 
                    key={r.id} 
                    className="border-b border-border/50 hover:bg-secondary/20 cursor-pointer"
                    onClick={() => setCurrentResult(r)}
                  >
                    <td className="py-2 px-2">{r.agent_name}</td>
                    <td className="py-2 px-2 font-mono">{r.summary?.symbol}</td>
                    <td className="py-2 px-2 text-right font-mono">{r.summary?.n_windows}</td>
                    <td className={`py-2 px-2 text-right font-mono ${r.oos_performance?.total_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                      ${r.oos_performance?.total_pnl?.toFixed(2)}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">{r.stability_analysis?.stability_score?.toFixed(0)}</td>
                    <td className="py-2 px-2 text-right font-mono">{r.go_live_decision?.score}</td>
                    <td className="py-2 px-2 text-center">
                      <Badge variant={
                        r.go_live_decision?.recommendation === "GO" ? "default" :
                        r.go_live_decision?.recommendation === "CONDITIONAL_GO" ? "secondary" : "destructive"
                      } className="font-mono text-xs">
                        {r.go_live_decision?.recommendation}
                      </Badge>
                    </td>
                    <td className="py-2 px-2 text-right text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
                {results.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-muted-foreground">
                      No WFO analyses yet. Run one to validate your strategy.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
