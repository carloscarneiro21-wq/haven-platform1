import { useState, useEffect, useCallback } from "react";
import { api } from "../App";
import { ScrollText, Search, Bot, AlertTriangle, Info, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

const LogIcon = ({ level }) => {
  switch (level) { case 'error': case 'critical': return <AlertCircle className="w-4 h-4 text-[#EF4444]" />; case 'warning': return <AlertTriangle className="w-4 h-4 text-[#F59E0B]" />; default: return <Info className="w-4 h-4 text-[#3B82F6]" />; }
};

const TradeLogs = () => {
  const [tradeLogs, setTradeLogs] = useState([]);
  const [systemLogs, setSystemLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("trades");
  const [agentFilter, setAgentFilter] = useState("all");
  const [levelFilter, setLevelFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchLogs = useCallback(async () => { try { const [tradeRes, systemRes] = await Promise.all([api.get("/logs/trades?limit=200"), api.get("/logs/system?limit=200")]); setTradeLogs(tradeRes.data); setSystemLogs(systemRes.data); } catch (e) { console.error("Failed to fetch logs"); } finally { setLoading(false); } }, []);
  useEffect(() => { fetchLogs(); const interval = setInterval(fetchLogs, 10000); return () => clearInterval(interval); }, [fetchLogs]);

  const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString() : '-';
  const filteredTradeLogs = tradeLogs.filter(log => { if (agentFilter !== "all" && log.agent_type !== agentFilter) return false; if (searchQuery && !log.reason?.toLowerCase().includes(searchQuery.toLowerCase())) return false; return true; });
  const filteredSystemLogs = systemLogs.filter(log => { if (levelFilter !== "all" && log.level !== levelFilter) return false; if (searchQuery && !log.message?.toLowerCase().includes(searchQuery.toLowerCase())) return false; return true; });

  return (
    <div className="space-y-6" data-testid="trade-logs-page">
      <div className="flex items-center justify-between">
        <div><h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase">Trade Logs</h1><p className="text-sm font-mono text-zinc-500 mt-1">{tradeLogs.length} trade decisions • {systemLogs.length} system events</p></div>
        <Button onClick={fetchLogs} variant="outline" className="btn-outline">Refresh</Button>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md"><Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-zinc-500" /><Input placeholder="Search logs..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-10 bg-zinc-900 border-zinc-700 font-mono text-sm" /></div>
        <Select value={agentFilter} onValueChange={setAgentFilter}><SelectTrigger className="w-40 bg-zinc-900 border-zinc-700"><SelectValue placeholder="Agent" /></SelectTrigger><SelectContent className="bg-zinc-900 border-zinc-700"><SelectItem value="all">All Agents</SelectItem><SelectItem value="dca">DCA</SelectItem><SelectItem value="grid">Grid</SelectItem><SelectItem value="trend">Trend</SelectItem></SelectContent></Select>
        <Select value={levelFilter} onValueChange={setLevelFilter}><SelectTrigger className="w-40 bg-zinc-900 border-zinc-700"><SelectValue placeholder="Level" /></SelectTrigger><SelectContent className="bg-zinc-900 border-zinc-700"><SelectItem value="all">All Levels</SelectItem><SelectItem value="info">Info</SelectItem><SelectItem value="warning">Warning</SelectItem><SelectItem value="error">Error</SelectItem><SelectItem value="critical">Critical</SelectItem></SelectContent></Select>
      </div>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800"><TabsTrigger value="trades" className="font-rajdhani uppercase tracking-wider data-[state=active]:bg-zinc-800"><Bot className="w-4 h-4 mr-2" />Trade Decisions ({filteredTradeLogs.length})</TabsTrigger><TabsTrigger value="system" className="font-rajdhani uppercase tracking-wider data-[state=active]:bg-zinc-800"><ScrollText className="w-4 h-4 mr-2" />System Logs ({filteredSystemLogs.length})</TabsTrigger></TabsList>
        <TabsContent value="trades">
          <Card className="trading-card"><CardContent className="p-0"><div className="max-h-[600px] overflow-y-auto">
            {filteredTradeLogs.map((log, i) => (
              <div key={log.id || i} className="p-4 border-b border-zinc-800 hover:bg-white/5 transition-colors">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3"><Badge variant="outline" className="text-xs font-mono">{log.agent_type?.toUpperCase()}</Badge><span className="text-xs font-mono text-zinc-500">{log.symbol}</span><Badge className={`status-badge ${log.action?.includes('buy') ? 'status-running' : log.action?.includes('sell') ? 'status-stopped' : log.action?.includes('close') ? 'status-paused' : ''}`}>{log.action?.toUpperCase()}</Badge></div>
                  <span className="text-xs font-mono text-zinc-600">{formatDate(log.timestamp)}</span>
                </div>
                <p className="text-sm text-zinc-300 mb-2">{log.reason}</p>
                {log.market_conditions && Object.keys(log.market_conditions).length > 0 && (<div className="flex flex-wrap gap-2 mt-2">{Object.entries(log.market_conditions).map(([key, value]) => (<span key={key} className="text-xs font-mono px-2 py-1 bg-zinc-800 rounded-sm text-zinc-400">{key}: {typeof value === 'number' ? value.toFixed(2) : String(value)}</span>))}</div>)}
                {log.signal_strength > 0 && (<div className="mt-2 flex items-center gap-2"><span className="text-xs text-zinc-500">Signal Strength:</span><div className="flex-1 max-w-[100px] h-1.5 bg-zinc-800 rounded-full"><div className="h-full bg-[#8B5CF6] rounded-full" style={{ width: `${log.signal_strength * 100}%` }} /></div><span className="text-xs font-mono text-zinc-400">{(log.signal_strength * 100).toFixed(0)}%</span></div>)}
              </div>
            ))}
            {filteredTradeLogs.length === 0 && (<div className="py-12 text-center text-zinc-500"><ScrollText className="w-8 h-8 mx-auto mb-2 opacity-50" /><p>No trade logs found</p></div>)}
          </div></CardContent></Card>
        </TabsContent>
        <TabsContent value="system">
          <Card className="trading-card"><CardContent className="p-0"><div className="max-h-[600px] overflow-y-auto">
            {filteredSystemLogs.map((log, i) => (
              <div key={log.id || i} className={`p-4 border-b border-zinc-800 hover:bg-white/5 transition-colors ${log.level === 'error' || log.level === 'critical' ? 'bg-[#EF4444]/5' : log.level === 'warning' ? 'bg-[#F59E0B]/5' : ''}`}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-3"><LogIcon level={log.level} /><Badge className={`status-badge ${log.level === 'error' || log.level === 'critical' ? 'status-stopped' : log.level === 'warning' ? 'status-paused' : 'status-running'}`}>{log.level?.toUpperCase()}</Badge><span className="text-xs font-mono text-zinc-500">{log.component}</span></div>
                  <span className="text-xs font-mono text-zinc-600">{formatDate(log.timestamp)}</span>
                </div>
                <p className="text-sm text-zinc-300">{log.message}</p>
                {log.details && Object.keys(log.details).length > 0 && (<div className="mt-2 p-2 bg-zinc-900 rounded-sm"><pre className="text-xs font-mono text-zinc-500 overflow-x-auto">{JSON.stringify(log.details, null, 2)}</pre></div>)}
              </div>
            ))}
            {filteredSystemLogs.length === 0 && (<div className="py-12 text-center text-zinc-500"><ScrollText className="w-8 h-8 mx-auto mb-2 opacity-50" /><p>No system logs found</p></div>)}
          </div></CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default TradeLogs;
