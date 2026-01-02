import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { 
  Database, 
  Download,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Activity,
  Clock
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
  Area
} from 'recharts';

const TIMEFRAMES = ["1m", "5m", "15m", "1h"];
const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"];

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-background border border-border p-3">
        <p className="font-mono text-xs text-muted-foreground">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="font-mono text-sm" style={{ color: entry.color }}>
            {entry.name}: ${entry.value?.toLocaleString()}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function MarketDataPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [candles, setCandles] = useState([]);
  const [regime, setRegime] = useState(null);
  const [livePrice, setLivePrice] = useState(null);
  const [fetching, setFetching] = useState(false);
  const [daysBack, setDaysBack] = useState(7);
  
  const fetchCandles = async () => {
    try {
      const response = await axios.get(`${API}/data/candles/${symbol.replace("/", "-")}`, {
        params: { timeframe, limit: 200 }
      });
      
      // Format for chart
      const formatted = response.data.map(c => ({
        time: new Date(c.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume
      }));
      
      setCandles(formatted);
    } catch (e) {
      console.error(e);
    }
  };
  
  const fetchRegime = async () => {
    try {
      const response = await axios.get(`${API}/data/regime/${symbol.replace("/", "-")}`, {
        params: { timeframe }
      });
      setRegime(response.data);
    } catch (e) {
      console.error(e);
    }
  };
  
  const fetchLivePrice = async () => {
    try {
      const response = await axios.get(`${API}/data/price/${symbol.replace("/", "-")}`);
      setLivePrice(response.data);
    } catch (e) {
      console.error(e);
    }
  };
  
  const fetchHistorical = async () => {
    setFetching(true);
    try {
      const response = await axios.post(`${API}/data/fetch-historical`, {
        symbol,
        timeframe,
        days_back: daysBack
      });
      toast.success(response.data.message);
      fetchCandles();
    } catch (e) {
      toast.error("Failed to fetch historical data");
    } finally {
      setFetching(false);
    }
  };
  
  useEffect(() => {
    fetchCandles();
    fetchRegime();
    fetchLivePrice();
    
    const interval = setInterval(fetchLivePrice, 5000);
    return () => clearInterval(interval);
  }, [symbol, timeframe]);
  
  const regimeColor = {
    trending: "text-profit",
    ranging: "text-yellow-500",
    volatile: "text-destructive",
    unknown: "text-muted-foreground"
  };
  
  return (
    <div className="p-4 lg:p-6 space-y-6" data-testid="market-data-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-rajdhani font-bold tracking-wide">MARKET DATA</h1>
          <p className="text-sm text-muted-foreground">
            Real-time Binance data pipeline
          </p>
        </div>
        <Badge variant="outline" className="font-mono">
          <Activity className="w-3 h-3 mr-1 animate-pulse text-profit" />
          BINANCE
        </Badge>
      </div>
      
      {/* Controls */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
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
          <Label>Days to Fetch</Label>
          <Input 
            type="number" 
            value={daysBack} 
            onChange={(e) => setDaysBack(parseInt(e.target.value))}
            data-testid="input-days"
          />
        </div>
        
        <div className="space-y-2 flex items-end">
          <Button 
            onClick={fetchHistorical} 
            disabled={fetching}
            variant="outline"
            className="w-full btn-sharp"
            data-testid="btn-fetch"
          >
            <Download className="w-4 h-4 mr-2" />
            {fetching ? "Fetching..." : "Fetch Historical"}
          </Button>
        </div>
        
        <div className="space-y-2 flex items-end">
          <Button 
            onClick={() => { fetchCandles(); fetchRegime(); fetchLivePrice(); }}
            variant="outline"
            className="w-full btn-sharp"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>
      
      {/* Live Price & Regime */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Live Price Card */}
        <Card className="border-border bg-background lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              {symbol}
              <Badge variant="secondary" className="font-mono text-xs">LIVE</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {livePrice ? (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Last Price</p>
                  <p className="text-3xl font-mono font-bold">${livePrice.last?.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">24h Change</p>
                  <p className={`text-xl font-mono ${livePrice.change_24h_percent >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {livePrice.change_24h_percent >= 0 ? '+' : ''}{livePrice.change_24h_percent?.toFixed(2)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">24h High/Low</p>
                  <p className="text-sm font-mono">
                    <span className="text-profit">${livePrice.high_24h?.toLocaleString()}</span>
                    {" / "}
                    <span className="text-loss">${livePrice.low_24h?.toLocaleString()}</span>
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">24h Volume</p>
                  <p className="text-sm font-mono">${(livePrice.volume_24h / 1000000)?.toFixed(2)}M</p>
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>
        
        {/* Market Regime Card */}
        <Card className="border-border bg-background">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <BarChart3 className="w-5 h-5" />
              Market Regime
            </CardTitle>
          </CardHeader>
          <CardContent>
            {regime ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Regime</span>
                  <Badge variant="outline" className={`font-mono uppercase ${regimeColor[regime.regime]}`}>
                    {regime.regime}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Confidence</span>
                  <span className="font-mono">{(regime.confidence * 100)?.toFixed(0)}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Trend Direction</span>
                  <Badge variant={regime.trend_direction === "bullish" ? "default" : "destructive"} className="font-mono text-xs">
                    {regime.trend_direction?.toUpperCase()}
                  </Badge>
                </div>
                {regime.details && (
                  <>
                    <div className="flex items-center justify-between pt-2 border-t border-border">
                      <span className="text-muted-foreground text-xs">ADX</span>
                      <span className="font-mono text-xs">{regime.details.adx}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground text-xs">Volatility</span>
                      <span className="font-mono text-xs">{regime.details.volatility_pct}%</span>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">Loading regime data...</p>
            )}
          </CardContent>
        </Card>
      </div>
      
      {/* Price Chart */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
            Price Chart ({timeframe})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={candles}>
                <defs>
                  <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis 
                  dataKey="time" 
                  stroke="rgba(255,255,255,0.3)"
                  tick={{ fill: 'hsl(240 5% 64.9%)', fontSize: 10 }}
                />
                <YAxis 
                  stroke="rgba(255,255,255,0.3)"
                  tick={{ fill: 'hsl(240 5% 64.9%)', fontSize: 10 }}
                  domain={['auto', 'auto']}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area 
                  type="monotone" 
                  dataKey="close" 
                  stroke="#10B981" 
                  strokeWidth={2}
                  fill="url(#priceGradient)"
                  name="Close"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
      
      {/* Candles Table */}
      <Card className="border-border bg-background">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-rajdhani uppercase tracking-wider text-muted-foreground">
            Recent Candles ({candles.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto max-h-[300px]">
            <table className="w-full table-terminal">
              <thead className="sticky top-0 bg-background">
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2">Time</th>
                  <th className="text-right py-2 px-2">Open</th>
                  <th className="text-right py-2 px-2">High</th>
                  <th className="text-right py-2 px-2">Low</th>
                  <th className="text-right py-2 px-2">Close</th>
                  <th className="text-right py-2 px-2">Volume</th>
                </tr>
              </thead>
              <tbody>
                {candles.slice(-20).reverse().map((c, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2 px-2 text-muted-foreground">{c.time}</td>
                    <td className="py-2 px-2 text-right font-mono">${c.open?.toLocaleString()}</td>
                    <td className="py-2 px-2 text-right font-mono text-profit">${c.high?.toLocaleString()}</td>
                    <td className="py-2 px-2 text-right font-mono text-loss">${c.low?.toLocaleString()}</td>
                    <td className={`py-2 px-2 text-right font-mono ${c.close >= c.open ? 'text-profit' : 'text-loss'}`}>
                      ${c.close?.toLocaleString()}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-muted-foreground">
                      {(c.volume / 1000)?.toFixed(1)}K
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
