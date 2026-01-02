import { useState, useEffect } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { Settings as SettingsIcon, DollarSign, RefreshCw, Save, Bell, Send, Wifi, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Slider } from "../components/ui/slider";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";

// Help components
import { InfoIcon, FieldTooltip } from "../components/help";
import { LiveModeHelpContent, LiveModeTooltips } from "../help/live";

const Settings = () => {
  const [agents, setAgents] = useState([]);
  const [totalCapital, setTotalCapital] = useState(10000);
  const [allocations, setAllocations] = useState({});
  const [saving, setSaving] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState({});
  const [dataFeedHealth, setDataFeedHealth] = useState(null);
  const [notificationConfig, setNotificationConfig] = useState({
    enabled: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
    notify_on_trade: true,
    notify_on_stop_loss: true,
    notify_on_take_profit: true,
    notify_on_kill_switch: true,
    notify_on_agent_error: true,
    notify_on_risk_warning: true,
  });
  const [testingNotification, setTestingNotification] = useState(false);

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    try {
      const [agentsRes, runtimeRes, healthRes, notifRes] = await Promise.all([
        api.get("/agents"), 
        api.get("/runtime/status"),
        api.get("/market/health").catch(() => ({ data: null })),
        api.get("/notifications/config").catch(() => ({ data: null }))
      ]);
      setAgents(agentsRes.data); setRuntimeStatus(runtimeRes.data);
      if (healthRes.data) setDataFeedHealth(healthRes.data);
      if (notifRes.data) setNotificationConfig(prev => ({ ...prev, ...notifRes.data }));
      const allocs = {}; let total = 0;
      agentsRes.data.forEach(agent => { total += agent.allocated_capital || 0; });
      agentsRes.data.forEach(agent => { const pct = total > 0 ? ((agent.allocated_capital || 0) / total) * 100 : 33.33; allocs[agent.id] = pct; });
      setAllocations(allocs); setTotalCapital(total || 10000);
    } catch (e) { console.error("Failed to fetch data"); }
  };

  const handleUpdateCapital = async () => { setSaving(true); try { await api.put(`/capital/total?total=${totalCapital}`); toast.success("Total capital updated"); fetchData(); } catch (e) { console.error("Failed to update capital"); } finally { setSaving(false); } };
  const handleUpdateAllocations = async () => { setSaving(true); try { await api.post("/capital/allocate", { allocations }); toast.success("Capital allocation updated"); fetchData(); } catch (e) { console.error("Failed to update allocations"); } finally { setSaving(false); } };
  
  const handleUpdateNotifications = async () => {
    setSaving(true);
    try {
      await api.put("/notifications/config", notificationConfig);
      toast.success("Notification settings updated");
      fetchData();
    } catch (e) {
      console.error("Failed to update notification settings");
    } finally {
      setSaving(false);
    }
  };

  const handleTestNotification = async () => {
    setTestingNotification(true);
    try {
      const response = await api.post("/notifications/test");
      if (response.data.success) {
        toast.success("Test notification sent successfully!");
      } else {
        toast.error(response.data.message || "Failed to send test notification");
      }
    } catch (e) {
      toast.error("Failed to send test notification");
    } finally {
      setTestingNotification(false);
    }
  };

  const totalAllocation = Object.values(allocations).reduce((sum, v) => sum + v, 0);
  const formatCurrency = (value) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value || 0);

  return (
    <div className="space-y-6" data-testid="settings-page">
      <div className="flex items-center justify-between">
        <div><h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase">Settings</h1><p className="text-sm font-mono text-zinc-500 mt-1">Configure trading capital and system settings</p></div>
        <Button onClick={fetchData} variant="outline" className="btn-outline"><RefreshCw className="w-4 h-4 mr-2" />Refresh</Button>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Card className="trading-card">
          <CardHeader className="trading-card-header"><CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><DollarSign className="w-4 h-4" />Capital Management</CardTitle></CardHeader>
          <CardContent className="p-6 space-y-6">
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Total Trading Capital ($)</Label><div className="flex gap-3"><Input type="number" value={totalCapital} onChange={(e) => setTotalCapital(parseFloat(e.target.value))} className="bg-zinc-900 border-zinc-700 font-mono flex-1" /><Button onClick={handleUpdateCapital} className="btn-primary" disabled={saving}>Update</Button></div></div>
            <div className="h-px bg-zinc-800" />
            <div className="space-y-4">
              <div className="flex justify-between items-center"><Label className="text-xs text-zinc-500">Agent Capital Allocation</Label><Badge className={totalAllocation === 100 ? 'status-running' : 'status-paused'}>Total: {totalAllocation.toFixed(1)}%</Badge></div>
              {agents.map((agent) => (<div key={agent.id} className="space-y-2"><div className="flex justify-between text-sm"><span className="font-rajdhani uppercase tracking-wider text-zinc-300">{agent.type} Agent</span><span className="font-mono text-zinc-400">{formatCurrency(totalCapital * (allocations[agent.id] || 0) / 100)}</span></div><div className="flex items-center gap-4"><Slider value={[allocations[agent.id] || 0]} onValueChange={([v]) => setAllocations({...allocations, [agent.id]: v})} max={100} step={1} className="flex-1" /><span className="font-mono text-sm text-white w-14 text-right">{(allocations[agent.id] || 0).toFixed(0)}%</span></div></div>))}
              <Button onClick={handleUpdateAllocations} className="btn-primary w-full" disabled={saving || Math.abs(totalAllocation - 100) > 0.1}><Save className="w-4 h-4 mr-2" />Save Allocation</Button>
              {Math.abs(totalAllocation - 100) > 0.1 && (<p className="text-xs text-[#F59E0B] text-center">Total allocation must equal 100%</p>)}
            </div>
          </CardContent>
        </Card>
        <Card className="trading-card">
          <CardHeader className="trading-card-header"><CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><SettingsIcon className="w-4 h-4" />System Information</CardTitle></CardHeader>
          <CardContent className="p-6 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-1">Runtime Status</p><Badge className={runtimeStatus.running ? 'status-running' : 'status-stopped'}>{runtimeStatus.running ? 'RUNNING' : 'STOPPED'}</Badge></div>
              <div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-1">Cycle Interval</p><p className="font-mono text-lg text-white">{runtimeStatus.interval || 60}s</p></div>
              <div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-1">Total Cycles</p><p className="font-mono text-lg text-white">{runtimeStatus.cycle_count || 0}</p></div>
              <div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-1">Active Agents</p><p className="font-mono text-lg text-white">{agents.filter(a => a.status === 'running').length} / {agents.length}</p></div>
            </div>
            <div className="h-px bg-zinc-800" />
            <div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-2">Monitored Symbols</p><div className="flex flex-wrap gap-2">{(runtimeStatus.symbols || ['BTC/USDT', 'ETH/USDT']).map((symbol) => (<Badge key={symbol} variant="outline" className="font-mono">{symbol}</Badge>))}</div></div>
            <div className="p-4 bg-zinc-900 rounded-sm">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-zinc-500">Trading Mode</p>
                <InfoIcon title="Ajuda: Modo de Trading" content={<LiveModeHelpContent />} />
              </div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#F59E0B]" /><span className="font-rajdhani uppercase tracking-wider text-[#F59E0B]">Paper Trading</span></div><p className="text-xs text-zinc-600 mt-2">All trades are simulated. No real funds at risk.</p></div>
            {runtimeStatus.last_cycle && (<div className="p-4 bg-zinc-900 rounded-sm"><p className="text-xs text-zinc-500 mb-1">Last Cycle</p><p className="font-mono text-sm text-zinc-400">{new Date(runtimeStatus.last_cycle).toLocaleString()}</p></div>)}
          </CardContent>
        </Card>
      </div>

      {/* Data Feed Health */}
      <Card className="trading-card" data-testid="data-feed-health">
        <CardHeader className="trading-card-header">
          <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            <Wifi className="w-4 h-4" />
            Data Feed Health
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6">
          {dataFeedHealth ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 bg-zinc-900 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-2">Primary Source</p>
                  <div className="flex items-center gap-2">
                    <Badge className={
                      (dataFeedHealth.health?.primary_source || dataFeedHealth.active_source) === 'kraken' ? 'bg-[#5741D9]/20 text-[#7B68EE]' :
                      (dataFeedHealth.health?.primary_source || dataFeedHealth.active_source) === 'binance' ? 'bg-[#F0B90B]/20 text-[#F0B90B]' : 
                      'bg-[#8DC63F]/20 text-[#8DC63F]'
                    }>
                      {(dataFeedHealth.health?.primary_source || dataFeedHealth.active_source || 'UNKNOWN').toUpperCase()}
                    </Badge>
                  </div>
                </div>
                <div className="p-4 bg-zinc-900 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-2">Safe Mode</p>
                  <div className="flex items-center gap-2">
                    {dataFeedHealth.safe_mode ? (
                      <><AlertTriangle className="w-4 h-4 text-[#F59E0B]" /><span className="text-[#F59E0B] text-sm">ACTIVE</span></>
                    ) : (
                      <><CheckCircle2 className="w-4 h-4 text-[#10B981]" /><span className="text-[#10B981] text-sm">OFF</span></>
                    )}
                  </div>
                  {dataFeedHealth.safe_mode_reason && (
                    <p className="text-xs text-zinc-500 mt-1">{dataFeedHealth.safe_mode_reason}</p>
                  )}
                </div>
                <div className="p-4 bg-zinc-900 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-2">Data Status</p>
                  <div className="flex items-center gap-2">
                    {dataFeedHealth.health?.is_stale ? (
                      <><XCircle className="w-4 h-4 text-[#EF4444]" /><span className="text-[#EF4444] text-sm">STALE</span></>
                    ) : (
                      <><CheckCircle2 className="w-4 h-4 text-[#10B981]" /><span className="text-[#10B981] text-sm">FRESH</span></>
                    )}
                  </div>
                </div>
              </div>
              <div className="h-px bg-zinc-800" />
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(dataFeedHealth.health?.sources || {}).map(([source, info]) => (
                  <div key={source} className="p-4 bg-zinc-900 rounded-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-rajdhani uppercase tracking-wider text-zinc-300">{source}</span>
                      <Badge className={
                        info.status === 'healthy' ? 'status-running' :
                        info.status === 'degraded' ? 'status-paused' : 'status-stopped'
                      }>
                        {info.status?.toUpperCase()}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-zinc-500">Failures</span>
                        <p className="font-mono text-white">{info.failures || 0}</p>
                      </div>
                      <div>
                        <span className="text-zinc-500">Latency</span>
                        <p className="font-mono text-white">{(info.latency_ms || 0).toFixed(0)}ms</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-zinc-500 text-sm">Loading data feed health...</p>
          )}
        </CardContent>
      </Card>

      {/* Telegram Notifications */}
      <Card className="trading-card" data-testid="telegram-notifications">
        <CardHeader className="trading-card-header">
          <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            <Bell className="w-4 h-4" />
            Telegram Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="flex items-center justify-between p-4 bg-zinc-900 rounded-sm">
            <div>
              <p className="text-sm text-white">Enable Notifications</p>
              <p className="text-xs text-zinc-500">Receive alerts via Telegram</p>
            </div>
            <Switch 
              checked={notificationConfig.enabled} 
              onCheckedChange={(v) => setNotificationConfig({...notificationConfig, enabled: v})}
            />
          </div>
          
          {notificationConfig.enabled && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs text-zinc-500">Bot Token</Label>
                  <Input 
                    type="password"
                    placeholder="Enter your Telegram bot token"
                    value={notificationConfig.telegram_bot_token === '***configured***' ? '' : notificationConfig.telegram_bot_token}
                    onChange={(e) => setNotificationConfig({...notificationConfig, telegram_bot_token: e.target.value})}
                    className="bg-zinc-900 border-zinc-700 font-mono"
                  />
                  <p className="text-xs text-zinc-600">Get from @BotFather on Telegram</p>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-zinc-500">Chat ID</Label>
                  <Input 
                    type="text"
                    placeholder="Enter your chat ID"
                    value={notificationConfig.telegram_chat_id || ''}
                    onChange={(e) => setNotificationConfig({...notificationConfig, telegram_chat_id: e.target.value})}
                    className="bg-zinc-900 border-zinc-700 font-mono"
                  />
                  <p className="text-xs text-zinc-600">Get from @userinfobot on Telegram</p>
                </div>
              </div>
              
              <div className="h-px bg-zinc-800" />
              
              <div className="space-y-3">
                <p className="text-xs text-zinc-500 uppercase tracking-wider">Notification Events</p>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { key: 'notify_on_trade', label: 'Trade Executed' },
                    { key: 'notify_on_stop_loss', label: 'Stop Loss Triggered' },
                    { key: 'notify_on_take_profit', label: 'Take Profit Triggered' },
                    { key: 'notify_on_kill_switch', label: 'Kill Switch Activated' },
                    { key: 'notify_on_agent_error', label: 'Agent Errors' },
                    { key: 'notify_on_risk_warning', label: 'Risk Warnings' },
                  ].map(({ key, label }) => (
                    <div key={key} className="flex items-center justify-between p-3 bg-zinc-900 rounded-sm">
                      <span className="text-sm text-zinc-300">{label}</span>
                      <Switch 
                        checked={notificationConfig[key]} 
                        onCheckedChange={(v) => setNotificationConfig({...notificationConfig, [key]: v})}
                      />
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="flex gap-3">
                <Button onClick={handleUpdateNotifications} className="btn-primary flex-1" disabled={saving}>
                  <Save className="w-4 h-4 mr-2" />
                  Save Settings
                </Button>
                <Button 
                  onClick={handleTestNotification} 
                  variant="outline" 
                  className="btn-outline"
                  disabled={testingNotification || !notificationConfig.telegram_bot_token || !notificationConfig.telegram_chat_id}
                >
                  <Send className="w-4 h-4 mr-2" />
                  {testingNotification ? 'Sending...' : 'Test'}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Settings;
