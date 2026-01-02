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
import { toast } from "sonner";
import { 
  Play, 
  Download,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Target,
  Clock,
  DollarSign,
  Activity,
  FileJson
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
  Bar
} from 'recharts';

const TIMEFRAMES = ["1m", "5m", "15m", "1h"];
const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"];

const MetricCard = ({ label, value, format = "number", trend = null }) => {
  const formatValue = (v, f) => {
    if (f === "percent") return `${v?.toFixed(2)}%`;
    if (f === "currency") return `$${v?.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    if (f === "ratio") return v === "∞" ? "∞" : v?.toFixed(2);
    return v?.toFixed?.(2) ?? v;
  };

  return (
    <div className="p-3 bg-secondary/30 border border-border">
      <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-mono font-bold mt-1 ${
        trend === "positive" ? "text-profit" : 
        trend === "negative" ? "text-loss" : ""
      }`}>
        {formatValue(value, format)}
      </p>
    </div>
  );
};

export default function Backtest() {
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [daysBack, setDaysBack] = useState(30);
  const [initialCapital, setInitialCapital] = useState(10000);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState([]);
  const [currentResult, setCurrentResult] = useState(null);
  
  useEffect(() => {
    fetchAgents();
    fetchResults();
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
      const response = await axios.get(`${API}/backtest/results`);
      setResults(response.data);
    } catch (e) {
      console.error(e);
    }
  };
  
  const runBacktest = async () => {
    if (!selectedAgent) {
      toast.error("Select an agent first");
      return;
    }
    
    setRunning(true);
    try {
      const response = await axios.post(`${API}/backtest/run`, {
        agent_id: selectedAgent,
        symbol,
        timeframe,
        days_back: daysBack,
        initial_capital: initialCapital
      });
      
      toast.success(`Backtest complete: ${response.data.trades_count} trades`);
      setCurrentResult(response.data);
      fetchResults();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Backtest failed");
    } finally {
      setRunning(false);
    }
  };
  
  const exportResult = async (backtestId) => {
    window.open(`${API}/backtest/export/${backtestId}?format=json`, "_blank");
  };
  
  const metrics = currentResult?.metrics || {};
  const pnlPositive = metrics.total_pnl >= 0;
  
  return (
    <div className="p-4 lg:p-6 space-y-6" data-testid="backtest-page">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-rajdhani font-bold tracking-wide">BACKTESTING</h1>
        <p className="text-sm text-muted-foreground">
          Test strategies with historical data
        </p>
      </div>
      
      {/* Config Panel */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Run Backtest</CardTitle>
          <CardDescription>Configure and run historical simulation</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <div className="space-y-2">
              <Label>Agent</Label>
              <Select value={selectedAgent} onValueChange={setSelectedAgent}>
                <SelectTrigger data-testid="select-agent">
                  <SelectValue placeholder="Select agent" />
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
                <SelectTrigger data-testid="select-symbol">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SYMBOLS.map(s => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>Timeframe</Label>
              <Select value={timeframe} onValueChange={setTimeframe}>
                <SelectTrigger data-testid="select-timeframe">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map(t => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>Days Back</Label>
              <Input 
                type="number" 
                value={daysBack} 
                onChange={(e) => setDaysBack(parseInt(e.target.value))}
                data-testid="input-days"
              />
            </div>
            
            <div className="space-y-2">
              <Label>Initial Capital</Label>
              <Input 
                type="number" 
                value={initialCapital} 
                onChange={(e) => setInitialCapital(parseFloat(e.target.value))}
                data-testid="input-capital"
              />
            </div>
            
            <div className="space-y-2 flex items-end">
              <Button 
                onClick={runBacktest} 
                disabled={running} 
                className="w-full btn-sharp"
                data-testid="btn-run-backtest"
              >
                <Play className="w-4 h-4 mr-2" />
                {running ? "Running..." : "Run Backtest"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      
      {/* Results */}
      {currentResult && (
        <div className="space-y-4">
          {/* Key Metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            <MetricCard 
              label="Total P&L" 
              value={metrics.total_pnl} 
              format="currency"
              trend={pnlPositive ? "positive" : "negative"}
            />
            <MetricCard 
              label="Win Rate" 
              value={metrics.win_rate} 
              format="percent"
              trend={metrics.win_rate >= 50 ? "positive" : "negative"}
            />
            <MetricCard 
              label="Profit Factor" 
              value={metrics.profit_factor} 
              format="ratio"
              trend={metrics.profit_factor >= 1 ? "positive" : "negative"}
            />
            <MetricCard 
              label="Sharpe Ratio" 
              value={metrics.sharpe_ratio} 
              format="ratio"
              trend={metrics.sharpe_ratio >= 1 ? "positive" : "negative"}
            />
            <MetricCard 
              label="Max Drawdown" 
              value={metrics.max_drawdown_pct} 
              format="percent"
              trend="negative"
            />
            <MetricCard 
              label="Total Trades" 
              value={metrics.total_trades} 
              format="number"
            />
          </div>
          
          {/* Detailed Metrics */}
          <Card className="border-border bg-background">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
                Detailed Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="returns">
                <TabsList>
                  <TabsTrigger value="returns">Returns</TabsTrigger>
                  <TabsTrigger value="risk">Risk</TabsTrigger>
                  <TabsTrigger value="trades">Trades</TabsTrigger>
                  <TabsTrigger value="fees">Fees</TabsTrigger>
                </TabsList>
                
                <TabsContent value="returns" className="mt-4">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <MetricCard label="Total P&L %" value={metrics.total_pnl_pct} format="percent" trend={pnlPositive ? "positive" : "negative"} />
                    <MetricCard label="Gross Profit" value={metrics.gross_profit} format="currency" trend="positive" />
                    <MetricCard label="Gross Loss" value={metrics.gross_loss} format="currency" trend="negative" />
                    <MetricCard label="Expectancy" value={metrics.expectancy} format="currency" />
                  </div>
                </TabsContent>
                
                <TabsContent value="risk" className="mt-4">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <MetricCard label="Max Drawdown $" value={metrics.max_drawdown} format="currency" trend="negative" />
                    <MetricCard label="Sharpe Ratio" value={metrics.sharpe_ratio} format="ratio" />
                    <MetricCard label="Sortino Ratio" value={metrics.sortino_ratio} format="ratio" />
                    <MetricCard label="Calmar Ratio" value={metrics.calmar_ratio} format="ratio" />
                  </div>
                </TabsContent>
                
                <TabsContent value="trades" className="mt-4">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <MetricCard label="Winning Trades" value={metrics.winning_trades} trend="positive" />
                    <MetricCard label="Losing Trades" value={metrics.losing_trades} trend="negative" />
                    <MetricCard label="Avg Win" value={metrics.avg_win} format="currency" />
                    <MetricCard label="Avg Loss" value={metrics.avg_loss} format="currency" />
                    <MetricCard label="Largest Win" value={metrics.largest_win} format="currency" trend="positive" />
                    <MetricCard label="Largest Loss" value={metrics.largest_loss} format="currency" trend="negative" />
                    <MetricCard label="Avg R-Multiple" value={metrics.avg_r_multiple} format="ratio" />
                    <MetricCard label="Trades/Day" value={metrics.trades_per_day} />
                  </div>
                </TabsContent>
                
                <TabsContent value="fees" className="mt-4">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <MetricCard label="Total Fees" value={metrics.total_fees} format="currency" />
                    <MetricCard label="Total Slippage" value={metrics.total_slippage} format="currency" />
                    <MetricCard label="Fees % of Profit" value={metrics.fees_as_pnl_pct} format="percent" />
                    <MetricCard label="Duration (days)" value={metrics.duration_days} />
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>
      )}
      
      {/* History */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
            Backtest History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full table-terminal">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2">Agent</th>
                  <th className="text-left py-2 px-2">Symbol</th>
                  <th className="text-left py-2 px-2">Timeframe</th>
                  <th className="text-right py-2 px-2">P&L</th>
                  <th className="text-right py-2 px-2">Win Rate</th>
                  <th className="text-right py-2 px-2">Trades</th>
                  <th className="text-right py-2 px-2">Date</th>
                  <th className="text-right py-2 px-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr key={r.id} className="border-b border-border/50 hover:bg-secondary/20">
                    <td className="py-2 px-2">{r.agent_name}</td>
                    <td className="py-2 px-2 font-mono">{r.symbol}</td>
                    <td className="py-2 px-2">{r.timeframe}</td>
                    <td className={`py-2 px-2 text-right font-mono ${r.metrics?.total_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                      ${r.metrics?.total_pnl?.toFixed(2)}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">{r.metrics?.win_rate?.toFixed(1)}%</td>
                    <td className="py-2 px-2 text-right font-mono">{r.trades_count}</td>
                    <td className="py-2 px-2 text-right text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 px-2 text-right">
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => {
                          setCurrentResult({ metrics: r.metrics });
                        }}
                      >
                        <BarChart3 className="w-4 h-4" />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => exportResult(r.id)}
                      >
                        <Download className="w-4 h-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {results.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-muted-foreground">
                      No backtest results yet
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
