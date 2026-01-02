import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { 
  Bot, Play, Pause, Settings, ChevronDown, ChevronUp,
  TrendingUp, Grid3X3, DollarSign, Zap, Edit2, Save
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Progress } from "../components/ui/progress";
import { Slider } from "../components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../components/ui/collapsible";

// Help components
import { InfoIcon, FieldTooltip } from "../components/help";
import AgentPresetManager from "../components/AgentPresetManager";
import PairRecommender from "../components/PairRecommender";
import GrowthModule from "../components/GrowthModule";
import { useAuth } from "../contexts/AuthContext";
import { 
  DcaHelpContent, DcaPresets, DcaTooltips,
  GridHelpContent, GridPresets, GridTooltips,
  TrendHelpContent, TrendPresets, TrendTooltips,
  MeanReversionHelpContent, MeanReversionPresets, MeanReversionTooltips,
  BreakoutHelpContent, BreakoutPresets, BreakoutTooltips
} from "../help/agents";

const AgentIcon = ({ type }) => {
  switch (type) {
    case 'dca':
      return <DollarSign className="w-5 h-5" />;
    case 'grid':
      return <Grid3X3 className="w-5 h-5" />;
    case 'trend':
      return <TrendingUp className="w-5 h-5" />;
    case 'mean_reversion':
      return <Zap className="w-5 h-5" />;
    case 'breakout':
      return <TrendingUp className="w-5 h-5 rotate-45" />;
    default:
      return <Bot className="w-5 h-5" />;
  }
};

// Get help content based on agent type
const getAgentHelp = (type) => {
  switch (type) {
    case 'dca':
      return { content: <DcaHelpContent />, presets: DcaPresets, tooltips: DcaTooltips, title: "Ajuda: DCA Agent" };
    case 'grid':
      return { content: <GridHelpContent />, presets: GridPresets, tooltips: GridTooltips, title: "Ajuda: Grid Trading Agent" };
    case 'trend':
      return { content: <TrendHelpContent />, presets: TrendPresets, tooltips: TrendTooltips, title: "Ajuda: Trend Following Agent" };
    case 'mean_reversion':
      return { content: <MeanReversionHelpContent />, presets: MeanReversionPresets, tooltips: MeanReversionTooltips, title: "Ajuda: Mean Reversion Agent" };
    case 'breakout':
      return { content: <BreakoutHelpContent />, presets: BreakoutPresets, tooltips: BreakoutTooltips, title: "Ajuda: Breakout Agent" };
    default:
      return null;
  }
};

const AgentCard = ({ agent, onControl, onUpdate, onRefresh }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [config, setConfig] = useState({});
  const { user } = useAuth();
  
  const agentHelp = getAgentHelp(agent.type);

  // Initialize config based on agent type
  const initialConfig = useMemo(() => {
    if (agent.type === 'dca') {
      return {
        interval_hours: agent.interval_hours || 24,
        base_amount: agent.base_amount || 100,
        dip_threshold_pct: agent.dip_threshold_pct || 5,
      };
    } else if (agent.type === 'grid') {
      return {
        num_grids: agent.num_grids || 10,
        amount_per_grid: agent.amount_per_grid || 50,
        auto_adjust: agent.auto_adjust ?? true,
      };
    } else if (agent.type === 'trend') {
      return {
        stop_loss_pct: agent.stop_loss_pct || 3,
        take_profit_pct: agent.take_profit_pct || 6,
        position_size_pct: agent.position_size_pct || 5,
      };
    } else if (agent.type === 'mean_reversion') {
      return {
        bb_window: agent.bb_window || 20,
        bb_std: agent.bb_std || 2.0,
        rsi_oversold: agent.rsi_oversold || 30,
        rsi_overbought: agent.rsi_overbought || 70,
        position_size_pct: agent.position_size_pct || 5,
      };
    } else if (agent.type === 'breakout') {
      return {
        lookback_periods: agent.lookback_periods || 20,
        breakout_threshold_pct: agent.breakout_threshold_pct || 2.0,
        volume_multiplier: agent.volume_multiplier || 1.5,
        stop_loss_pct: agent.stop_loss_pct || 3,
      };
    }
    return {};
  }, [agent]);

  // Sync config when agent changes
  useEffect(() => {
    setConfig(initialConfig);
  }, [initialConfig]);

  const handleSave = async () => {
    await onUpdate(agent.id, config);
    setEditing(false);
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value || 0);
  };

  return (
    <Card className={`trading-card ${agent.status === 'running' ? 'running' : 'stopped'}`} data-testid={`agent-card-${agent.type}`}>
      <CardHeader className="trading-card-header">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-sm flex items-center justify-center ${agent.status === 'running' ? 'bg-[#10B981]/20 text-[#10B981]' : 'bg-zinc-800 text-zinc-500'}`}>
              <AgentIcon type={agent.type} />
            </div>
            <div className="flex items-center gap-2">
              <div>
                <h3 className="font-rajdhani font-bold text-lg uppercase tracking-wider text-white">{agent.type} Agent</h3>
                <p className="text-xs font-mono text-zinc-500">{agent.symbol || 'BTC/USDT'}</p>
              </div>
              {agentHelp && (
                <InfoIcon title={agentHelp.title} content={agentHelp.content} />
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={`status-badge status-${agent.status}`}>{agent.status}</Badge>
            <Button size="sm" variant="ghost" onClick={() => onControl(agent.id, agent.status === 'running' ? 'stop' : 'start')} className="h-8 w-8 p-0" data-testid={`agent-control-${agent.type}`}>
              {agent.status === 'running' ? <Pause className="w-4 h-4 text-[#F59E0B]" /> : <Play className="w-4 h-4 text-[#10B981]" />}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-4">
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div><p className="text-xs text-zinc-500 mb-1">Allocated</p><p className="font-mono text-sm text-white">{formatCurrency(agent.allocated_capital)}</p></div>
          <div><p className="text-xs text-zinc-500 mb-1">Used</p><p className="font-mono text-sm text-white">{formatCurrency(agent.used_capital)}</p></div>
          <div><p className="text-xs text-zinc-500 mb-1">Total P&L</p><p className={`font-mono text-sm ${agent.total_pnl >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>{formatCurrency(agent.total_pnl)}</p></div>
          <div><p className="text-xs text-zinc-500 mb-1">Win Rate</p><p className="font-mono text-sm text-white">{(agent.win_rate || 0).toFixed(1)}%</p></div>
        </div>
        <div className="mb-4">
          <div className="flex justify-between text-xs mb-1"><span className="text-zinc-500">Capital Usage</span><span className="font-mono text-zinc-400">{((agent.used_capital / agent.allocated_capital) * 100 || 0).toFixed(0)}%</span></div>
          <Progress value={(agent.used_capital / agent.allocated_capital) * 100 || 0} className="h-1.5 bg-zinc-800" />
        </div>
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between text-zinc-400 hover:text-white">
              <span className="flex items-center gap-2 text-xs font-rajdhani uppercase tracking-wider"><Settings className="w-3 h-3" />Configuration</span>
              {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-4 space-y-4">
            {agent.type === 'dca' && (
              <>
                {editing && (
                  <div className="col-span-full mb-4 p-3 bg-zinc-800/50 rounded-lg">
                    <Label className="text-xs text-zinc-400 mb-2 block">Presets & Ferramentas</Label>
                    <AgentPresetManager 
                      agentId={agent.id}
                      agentType={agent.type}
                      currentConfig={config}
                      onConfigChange={setConfig}
                      onApply={onRefresh}
                      presets={agentHelp?.presets}
                      userRole={user?.role || "viewer"}
                    />
                  </div>
                )}
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Interval (hours)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.interval} />}
                  </div>
                  <Input type="number" value={config.interval_hours} onChange={(e) => setConfig({...config, interval_hours: parseInt(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Base Amount (USDT)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.trade_size} />}
                  </div>
                  <Input type="number" value={config.base_amount} onChange={(e) => setConfig({...config, base_amount: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Dip Trigger (%)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.dip_percent} />}
                  </div>
                  <Input type="number" value={config.dip_threshold_pct} onChange={(e) => setConfig({...config, dip_threshold_pct: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
              </>
            )}
            {agent.type === 'grid' && (
              <>
                {editing && (
                  <div className="col-span-full mb-4 p-3 bg-zinc-800/50 rounded-lg">
                    <Label className="text-xs text-zinc-400 mb-2 block">Presets & Ferramentas</Label>
                    <AgentPresetManager 
                      agentId={agent.id}
                      agentType={agent.type}
                      currentConfig={config}
                      onConfigChange={setConfig}
                      onApply={onRefresh}
                      presets={agentHelp?.presets}
                      userRole={user?.role || "viewer"}
                    />
                  </div>
                )}
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Number of Grids</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.grids} />}
                  </div>
                  <Input type="number" value={config.num_grids} onChange={(e) => setConfig({...config, num_grids: parseInt(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Amount per Grid (USDT)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.capital} />}
                  </div>
                  <Input type="number" value={config.amount_per_grid} onChange={(e) => setConfig({...config, amount_per_grid: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
                <div className="flex items-center justify-between"><Label className="text-xs text-zinc-500">Auto-adjust Grid</Label><Switch checked={config.auto_adjust} onCheckedChange={(v) => setConfig({...config, auto_adjust: v})} disabled={!editing} /></div>
              </>
            )}
            {agent.type === 'trend' && (
              <>
                {editing && (
                  <div className="col-span-full mb-4 p-3 bg-zinc-800/50 rounded-lg">
                    <Label className="text-xs text-zinc-400 mb-2 block">Presets & Ferramentas</Label>
                    <AgentPresetManager 
                      agentId={agent.id}
                      agentType={agent.type}
                      currentConfig={config}
                      onConfigChange={setConfig}
                      onApply={onRefresh}
                      presets={agentHelp?.presets}
                      userRole={user?.role || "viewer"}
                    />
                  </div>
                )}
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Stop Loss (%)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.stop_loss} />}
                  </div>
                  <div className="flex items-center gap-4"><Slider value={[config.stop_loss_pct]} onValueChange={([v]) => setConfig({...config, stop_loss_pct: v})} max={10} step={0.5} disabled={!editing} className="flex-1" /><span className="font-mono text-sm text-white w-12">{config.stop_loss_pct}%</span></div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Take Profit (%)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.take_profit} />}
                  </div>
                  <div className="flex items-center gap-4"><Slider value={[config.take_profit_pct]} onValueChange={([v]) => setConfig({...config, take_profit_pct: v})} max={20} step={0.5} disabled={!editing} className="flex-1" /><span className="font-mono text-sm text-white w-12">{config.take_profit_pct}%</span></div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-1">
                    <Label className="text-xs text-zinc-500">Position Size (% of capital)</Label>
                    {agentHelp && <FieldTooltip text={agentHelp.tooltips.position_size} />}
                  </div>
                  <Input type="number" value={config.position_size_pct} onChange={(e) => setConfig({...config, position_size_pct: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" />
                </div>
              </>
            )}
            {agent.type === 'mean_reversion' && (
              <>
                {editing && (
                  <div className="col-span-full mb-4 p-3 bg-zinc-800/50 rounded-lg">
                    <Label className="text-xs text-zinc-400 mb-2 block">Presets & Ferramentas</Label>
                    <AgentPresetManager 
                      agentId={agent.id}
                      agentType={agent.type}
                      currentConfig={config}
                      onConfigChange={setConfig}
                      onApply={onRefresh}
                      presets={agentHelp?.presets}
                      userRole={user?.role || "viewer"}
                    />
                  </div>
                )}
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Bollinger Window</Label><Input type="number" value={config.bb_window} onChange={(e) => setConfig({...config, bb_window: parseInt(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Bollinger Std Dev</Label><Input type="number" step="0.1" value={config.bb_std} onChange={(e) => setConfig({...config, bb_std: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">RSI Oversold</Label><div className="flex items-center gap-4"><Slider value={[config.rsi_oversold]} onValueChange={([v]) => setConfig({...config, rsi_oversold: v})} max={50} step={1} disabled={!editing} className="flex-1" /><span className="font-mono text-sm text-white w-12">{config.rsi_oversold}</span></div></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">RSI Overbought</Label><div className="flex items-center gap-4"><Slider value={[config.rsi_overbought]} onValueChange={([v]) => setConfig({...config, rsi_overbought: v})} min={50} max={100} step={1} disabled={!editing} className="flex-1" /><span className="font-mono text-sm text-white w-12">{config.rsi_overbought}</span></div></div>
              </>
            )}
            {agent.type === 'breakout' && (
              <>
                {editing && (
                  <div className="col-span-full mb-4 p-3 bg-zinc-800/50 rounded-lg">
                    <Label className="text-xs text-zinc-400 mb-2 block">Presets & Ferramentas</Label>
                    <AgentPresetManager 
                      agentId={agent.id}
                      agentType={agent.type}
                      currentConfig={config}
                      onConfigChange={setConfig}
                      onApply={onRefresh}
                      presets={agentHelp?.presets}
                      userRole={user?.role || "viewer"}
                    />
                  </div>
                )}
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Lookback Periods</Label><Input type="number" value={config.lookback_periods} onChange={(e) => setConfig({...config, lookback_periods: parseInt(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Breakout Threshold (%)</Label><Input type="number" step="0.1" value={config.breakout_threshold_pct} onChange={(e) => setConfig({...config, breakout_threshold_pct: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Volume Multiplier</Label><Input type="number" step="0.1" value={config.volume_multiplier} onChange={(e) => setConfig({...config, volume_multiplier: parseFloat(e.target.value)})} disabled={!editing} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
                <div className="space-y-2"><Label className="text-xs text-zinc-500">Stop Loss (%)</Label><div className="flex items-center gap-4"><Slider value={[config.stop_loss_pct]} onValueChange={([v]) => setConfig({...config, stop_loss_pct: v})} max={10} step={0.5} disabled={!editing} className="flex-1" /><span className="font-mono text-sm text-white w-12">{config.stop_loss_pct}%</span></div></div>
              </>
            )}
            <div className="flex gap-2 pt-2">
              {editing ? (<><Button size="sm" onClick={handleSave} className="btn-primary flex-1"><Save className="w-3 h-3 mr-2" />Save</Button><Button size="sm" variant="outline" onClick={() => setEditing(false)} className="btn-outline">Cancel</Button></>) : (<Button size="sm" variant="outline" onClick={() => setEditing(true)} className="btn-outline flex-1"><Edit2 className="w-3 h-3 mr-2" />Edit Config</Button>)}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
};

const Agents = () => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("agents");

  const fetchAgents = useCallback(async () => {
    try { const response = await api.get("/agents"); setAgents(response.data); } catch (e) { console.error("Failed to fetch agents"); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAgents(); const interval = setInterval(fetchAgents, 5000); return () => clearInterval(interval); }, [fetchAgents]);

  const handleControl = async (agentId, action) => { try { await api.post(`/agents/${agentId}/control`, { action }); toast.success(`Agent ${action}ed successfully`); fetchAgents(); } catch (e) { console.error("Failed to control agent"); } };
  const handleUpdate = async (agentId, updates) => { try { await api.put(`/agents/${agentId}/config`, { updates }); toast.success("Configuration updated"); fetchAgents(); } catch (e) { console.error("Failed to update agent"); } };
  const handleStartAll = async () => { try { await api.post("/agents/start-all"); toast.success("All agents started"); fetchAgents(); } catch (e) { console.error("Failed to start all agents"); } };
  const handleStopAll = async () => { try { await api.post("/agents/stop-all"); toast.success("All agents stopped"); fetchAgents(); } catch (e) { console.error("Failed to stop all agents"); } };

  const runningCount = agents.filter(a => a.status === 'running').length;

  return (
    <div className="space-y-6" data-testid="agents-page">
      <div className="flex items-center justify-between">
        <div><h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase">Trading Agents</h1><p className="text-sm font-mono text-zinc-500 mt-1">{runningCount} of {agents.length} agents running</p></div>
        {activeTab === "agents" && (
          <div className="flex items-center gap-3"><Button onClick={handleStartAll} className="btn-primary" data-testid="start-all-btn"><Play className="w-4 h-4 mr-2" />Start All</Button><Button onClick={handleStopAll} className="btn-outline" data-testid="stop-all-btn"><Pause className="w-4 h-4 mr-2" />Stop All</Button></div>
        )}
      </div>
      
      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2 h-10 mb-4">
          <TabsTrigger value="agents" className="text-sm">
            <Bot className="w-4 h-4 mr-2" /> Spot Agents
          </TabsTrigger>
          <TabsTrigger value="growth" className="text-sm">
            <TrendingUp className="w-4 h-4 mr-2" /> Growth Module
          </TabsTrigger>
        </TabsList>
        
        {/* Spot Agents Tab */}
        <TabsContent value="agents" className="space-y-6">
          {/* Pair Advisor Section */}
          <PairRecommender />
          
          {/* Agents Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">{agents.map((agent) => (<AgentCard key={agent.id} agent={agent} onControl={handleControl} onUpdate={handleUpdate} onRefresh={fetchAgents} />))}</div>
          {agents.length === 0 && !loading && (<Card className="trading-card"><CardContent className="py-12 text-center"><Bot className="w-12 h-12 mx-auto mb-4 text-zinc-600" /><p className="text-zinc-500">No agents configured</p><p className="text-xs text-zinc-600 mt-2">Agents will be created automatically on first runtime start</p></CardContent></Card>)}
        </TabsContent>
        
        {/* Growth Module Tab */}
        <TabsContent value="growth">
          <GrowthModule />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Agents;
