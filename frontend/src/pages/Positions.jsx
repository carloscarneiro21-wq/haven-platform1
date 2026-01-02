import { useState, useEffect, useCallback } from "react";
import { api } from "../App";
import { TrendingUp, TrendingDown, X, RefreshCw, AlertTriangle } from "lucide-react";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

const Positions = () => {
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("positions");
  const [lastError, setLastError] = useState(null);

  const fetchData = useCallback(async () => {
    setLastError(null);
    try {
      const [positionsRes, ordersRes, tradesRes] = await Promise.all([
        api.get("/positions", { params: { open_only: false } }),
        api.get("/orders"),
        api.get("/trades", { params: { limit: 50 } }),
      ]);
      setPositions(positionsRes.data);
      setOrders(ordersRes.data);
      setTrades(tradesRes.data);
    } catch (e) {
      console.error("Failed to fetch data", e);
      setLastError({
        status: e?.response?.status,
        detail: e?.response?.data?.detail || e?.message || "Unknown error",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); const interval = setInterval(fetchData, 5000); return () => clearInterval(interval); }, [fetchData]);

  const handleCancelOrder = async (orderId) => { try { await api.delete(`/orders/${orderId}`); fetchData(); } catch (e) { console.error("Failed to cancel order"); } };

  const formatCurrency = (value) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(value || 0);
  const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString() : '-';

  const openPositions = positions.filter(p => p.is_open);

  return (
    <div className="space-y-6" data-testid="positions-page">
      <div className="flex items-center justify-between">
        <div><h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase">Positions & Orders</h1><p className="text-sm font-mono text-zinc-500 mt-1">{openPositions.length} open positions • {orders.length} pending orders</p></div>
        <Button onClick={fetchData} variant="outline" className="btn-outline"><RefreshCw className="w-4 h-4 mr-2" />Refresh</Button>
      </div>

      {lastError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5" />
            <div>
              <div className="text-sm text-red-300 font-medium">Failed to refresh Positions</div>
              <div className="text-xs text-zinc-400 mt-1 font-mono">Status: {String(lastError.status ?? '(no response)')}</div>
              <div className="text-xs text-zinc-400 mt-1 whitespace-pre-wrap break-words">{String(lastError.detail)}</div>
            </div>
          </div>
        </div>
      )}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="positions" className="font-rajdhani uppercase tracking-wider data-[state=active]:bg-zinc-800">Open Positions ({openPositions.length})</TabsTrigger>
          <TabsTrigger value="orders" className="font-rajdhani uppercase tracking-wider data-[state=active]:bg-zinc-800">Pending Orders ({orders.length})</TabsTrigger>
          <TabsTrigger value="history" className="font-rajdhani uppercase tracking-wider data-[state=active]:bg-zinc-800">Trade History</TabsTrigger>
        </TabsList>
        <TabsContent value="positions">
          <Card className="trading-card"><CardContent className="p-0">
            <Table className="data-table"><TableHeader><TableRow><TableHead>Symbol</TableHead><TableHead>Side</TableHead><TableHead>Size</TableHead><TableHead>Entry Price</TableHead><TableHead>Current Price</TableHead><TableHead>Unrealized P&L</TableHead><TableHead>Agent</TableHead><TableHead>Opened</TableHead></TableRow></TableHeader>
            <TableBody>{openPositions.map((position) => (<TableRow key={position.id}><TableCell className="font-semibold">{position.symbol}</TableCell><TableCell><Badge className={position.side === 'buy' ? 'status-running' : 'status-stopped'}>{position.side === 'buy' ? <><TrendingUp className="w-3 h-3 mr-1" /> LONG</> : <><TrendingDown className="w-3 h-3 mr-1" /> SHORT</>}</Badge></TableCell><TableCell>{position.amount?.toFixed(6)}</TableCell><TableCell>{formatCurrency(position.entry_price)}</TableCell><TableCell>{formatCurrency(position.current_price)}</TableCell><TableCell><span className={position.unrealized_pnl >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}>{formatCurrency(position.unrealized_pnl)}<span className="text-xs ml-1">({position.unrealized_pnl_pct?.toFixed(2) || 0}%)</span></span></TableCell><TableCell><Badge variant="outline" className="text-xs">{position.agent_type?.toUpperCase()}</Badge></TableCell><TableCell className="text-zinc-500 text-xs">{formatDate(position.opened_at)}</TableCell></TableRow>))}{openPositions.length === 0 && (<TableRow><TableCell colSpan={8} className="text-center py-12 text-zinc-500">No open positions</TableCell></TableRow>)}</TableBody></Table>
          </CardContent></Card>
        </TabsContent>
        <TabsContent value="orders">
          <Card className="trading-card"><CardContent className="p-0">
            <Table className="data-table"><TableHeader><TableRow><TableHead>Symbol</TableHead><TableHead>Type</TableHead><TableHead>Side</TableHead><TableHead>Amount</TableHead><TableHead>Price</TableHead><TableHead>Status</TableHead><TableHead>Agent</TableHead><TableHead>Actions</TableHead></TableRow></TableHeader>
            <TableBody>{orders.map((order) => (<TableRow key={order.id}><TableCell className="font-semibold">{order.symbol}</TableCell><TableCell className="uppercase text-xs">{order.order_type}</TableCell><TableCell><Badge className={order.side === 'buy' ? 'status-running' : 'status-stopped'}>{order.side?.toUpperCase()}</Badge></TableCell><TableCell>{order.amount?.toFixed(6)}</TableCell><TableCell>{formatCurrency(order.price)}</TableCell><TableCell><Badge className="status-paused">{order.status}</Badge></TableCell><TableCell><Badge variant="outline" className="text-xs">{order.agent_type?.toUpperCase()}</Badge></TableCell><TableCell><Button size="sm" variant="ghost" onClick={() => handleCancelOrder(order.id)} className="h-7 w-7 p-0 text-zinc-500 hover:text-[#EF4444]"><X className="w-4 h-4" /></Button></TableCell></TableRow>))}{orders.length === 0 && (<TableRow><TableCell colSpan={8} className="text-center py-12 text-zinc-500">No pending orders</TableCell></TableRow>)}</TableBody></Table>
          </CardContent></Card>
        </TabsContent>
        <TabsContent value="history">
          <Card className="trading-card"><CardContent className="p-0">
            <Table className="data-table"><TableHeader><TableRow><TableHead>Time</TableHead><TableHead>Symbol</TableHead><TableHead>Side</TableHead><TableHead>Amount</TableHead><TableHead>Price</TableHead><TableHead>Value</TableHead><TableHead>P&L</TableHead><TableHead>Agent</TableHead></TableRow></TableHeader>
            <TableBody>{trades.map((trade) => (<TableRow key={trade.id}><TableCell className="text-xs text-zinc-500">{formatDate(trade.executed_at)}</TableCell><TableCell className="font-semibold">{trade.symbol}</TableCell><TableCell><Badge className={trade.side === 'buy' ? 'status-running' : 'status-stopped'}>{trade.side?.toUpperCase()}</Badge></TableCell><TableCell>{trade.amount?.toFixed(6)}</TableCell><TableCell>{formatCurrency(trade.price)}</TableCell><TableCell>{formatCurrency(trade.value)}</TableCell><TableCell><span className={trade.pnl >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}>{formatCurrency(trade.pnl)}</span></TableCell><TableCell><Badge variant="outline" className="text-xs">{trade.agent_type?.toUpperCase()}</Badge></TableCell></TableRow>))}{trades.length === 0 && (<TableRow><TableCell colSpan={8} className="text-center py-12 text-zinc-500">No trades yet</TableCell></TableRow>)}</TableBody></Table>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Positions;
