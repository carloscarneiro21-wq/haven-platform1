import { useState, useEffect, useCallback } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { Shield, AlertTriangle, Zap, Clock, DollarSign, TrendingDown, AlertCircle, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Progress } from "../components/ui/progress";
import { Slider } from "../components/ui/slider";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "../components/ui/alert-dialog";

const RiskManager = () => {
  const [risk, setRisk] = useState({});
  const [settings, setSettings] = useState({ max_daily_loss: 500, max_daily_loss_pct: 5, max_position_size: 5000, max_total_exposure: 20000, max_drawdown_pct: 15, max_consecutive_losses: 5 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchRisk = useCallback(async () => {
    try { const response = await api.get("/risk"); setRisk(response.data); setSettings({ max_daily_loss: response.data.max_daily_loss || 500, max_daily_loss_pct: response.data.max_daily_loss_pct || 5, max_position_size: response.data.max_position_size || 5000, max_total_exposure: response.data.max_total_exposure || 20000, max_drawdown_pct: response.data.max_drawdown_pct || 15, max_consecutive_losses: response.data.max_consecutive_losses || 5 }); } catch (e) { console.error("Failed to fetch risk status"); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRisk(); const interval = setInterval(fetchRisk, 5000); return () => clearInterval(interval); }, [fetchRisk]);

  const handleSaveSettings = async () => { setSaving(true); try { await api.put("/risk/settings", settings); toast.success("Risk settings updated"); fetchRisk(); } catch (e) { console.error("Failed to save settings"); } finally { setSaving(false); } };
  const handleKillSwitch = async (activate) => { try { await api.post("/risk/kill-switch", { activate, reason: activate ? "Manual activation" : undefined }); toast.success(activate ? "Kill switch activated!" : "Kill switch deactivated"); fetchRisk(); } catch (e) { console.error("Failed to toggle kill switch"); } };

  const formatCurrency = (value) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value || 0);
  const dailyLossProgress = Math.min(100, Math.abs(risk.current_daily_pnl || 0) / (risk.max_daily_loss || 500) * 100);
  const exposureProgress = (risk.current_total_exposure || 0) / (risk.max_total_exposure || 20000) * 100;
  const drawdownProgress = (risk.current_drawdown_pct || 0) / (risk.max_drawdown_pct || 15) * 100;

  return (
    <div className="space-y-6" data-testid="risk-manager-page">
      <div className="flex items-center justify-between">
        <div><h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase">Risk Manager</h1><p className="text-sm font-mono text-zinc-500 mt-1">Global risk controls and circuit breakers</p></div>
        <Badge className={risk.trading_allowed ? 'status-running' : 'status-stopped'}>{risk.trading_allowed ? 'TRADING ALLOWED' : 'TRADING BLOCKED'}</Badge>
      </div>
      <Card className={`trading-card ${risk.kill_switch_active ? 'border-[#EF4444]' : ''}`}>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`w-16 h-16 rounded-sm flex items-center justify-center ${risk.kill_switch_active ? 'bg-[#EF4444]/20' : 'bg-zinc-800'}`}><Zap className={`w-8 h-8 ${risk.kill_switch_active ? 'text-[#EF4444]' : 'text-zinc-500'}`} /></div>
              <div><h2 className="font-rajdhani text-xl font-bold uppercase tracking-wider text-white">Emergency Kill Switch</h2><p className="text-sm text-zinc-500 mt-1">{risk.kill_switch_active ? "All trading is halted. Click to resume." : "Click to immediately stop all trading activity."}</p></div>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild><button className={`kill-switch ${risk.kill_switch_active ? 'active' : ''}`} data-testid="kill-switch-btn">{risk.kill_switch_active ? 'RESUME TRADING' : 'STOP ALL TRADING'}</button></AlertDialogTrigger>
              <AlertDialogContent className="bg-[#18181B] border-zinc-800">
                <AlertDialogHeader><AlertDialogTitle className="font-rajdhani text-xl uppercase tracking-wider">{risk.kill_switch_active ? 'Resume Trading?' : 'Activate Kill Switch?'}</AlertDialogTitle><AlertDialogDescription className="text-zinc-400">{risk.kill_switch_active ? "This will allow agents to resume trading. Make sure conditions are safe." : "This will immediately stop all trading agents and cancel pending orders."}</AlertDialogDescription></AlertDialogHeader>
                <AlertDialogFooter><AlertDialogCancel className="btn-outline">Cancel</AlertDialogCancel><AlertDialogAction onClick={() => handleKillSwitch(!risk.kill_switch_active)} className={risk.kill_switch_active ? 'btn-primary' : 'btn-danger'}>Confirm</AlertDialogAction></AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>
      <div className="grid grid-cols-2 gap-6">
        <Card className="trading-card">
          <CardHeader className="trading-card-header"><CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><Shield className="w-4 h-4" />Current Risk Status</CardTitle></CardHeader>
          <CardContent className="p-6 space-y-6">
            <div><div className="flex justify-between items-center mb-2"><div className="flex items-center gap-2"><TrendingDown className="w-4 h-4 text-zinc-500" /><span className="text-sm text-zinc-400">Daily Loss</span></div><span className={`font-mono text-sm ${risk.current_daily_pnl >= 0 ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>{formatCurrency(risk.current_daily_pnl)} / {formatCurrency(risk.max_daily_loss)}</span></div><Progress value={dailyLossProgress} className={`h-2 ${dailyLossProgress > 80 ? 'bg-[#EF4444]/20' : 'bg-zinc-800'}`} />{dailyLossProgress > 80 && <p className="text-xs text-[#EF4444] mt-1 flex items-center gap-1"><AlertCircle className="w-3 h-3" />Approaching daily loss limit</p>}</div>
            <div><div className="flex justify-between items-center mb-2"><div className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-zinc-500" /><span className="text-sm text-zinc-400">Drawdown</span></div><span className="font-mono text-sm text-[#F59E0B]">{(risk.current_drawdown_pct || 0).toFixed(2)}% / {risk.max_drawdown_pct}%</span></div><Progress value={drawdownProgress} className={`h-2 ${drawdownProgress > 80 ? 'bg-[#F59E0B]/20' : 'bg-zinc-800'}`} /></div>
            <div><div className="flex justify-between items-center mb-2"><div className="flex items-center gap-2"><DollarSign className="w-4 h-4 text-zinc-500" /><span className="text-sm text-zinc-400">Total Exposure</span></div><span className="font-mono text-sm text-white">{formatCurrency(risk.current_total_exposure)} / {formatCurrency(risk.max_total_exposure)}</span></div><Progress value={exposureProgress} className="h-2 bg-zinc-800" /></div>
            <div className="flex justify-between items-center p-3 bg-zinc-900 rounded-sm"><span className="text-sm text-zinc-400">Consecutive Losses</span><span className={`font-mono text-lg ${risk.consecutive_losses >= 3 ? 'text-[#EF4444]' : 'text-white'}`}>{risk.consecutive_losses || 0} / {risk.max_consecutive_losses}</span></div>
            {risk.cooldown_until && (<div className="p-4 bg-[#F59E0B]/10 border border-[#F59E0B]/30 rounded-sm"><div className="flex items-center gap-2 mb-2"><Clock className="w-4 h-4 text-[#F59E0B]" /><span className="text-sm text-[#F59E0B] font-semibold">Cooldown Active</span></div><p className="text-xs font-mono text-zinc-400">Until: {new Date(risk.cooldown_until).toLocaleString()}</p></div>)}
          </CardContent>
        </Card>
        <Card className="trading-card">
          <CardHeader className="trading-card-header"><CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400">Risk Limits Configuration</CardTitle></CardHeader>
          <CardContent className="p-6 space-y-5">
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Daily Loss ($)</Label><Input type="number" value={settings.max_daily_loss} onChange={(e) => setSettings({...settings, max_daily_loss: parseFloat(e.target.value)})} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Daily Loss (%)</Label><div className="flex items-center gap-4"><Slider value={[settings.max_daily_loss_pct]} onValueChange={([v]) => setSettings({...settings, max_daily_loss_pct: v})} max={20} step={0.5} className="flex-1" /><span className="font-mono text-sm text-white w-12">{settings.max_daily_loss_pct}%</span></div></div>
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Position Size ($)</Label><Input type="number" value={settings.max_position_size} onChange={(e) => setSettings({...settings, max_position_size: parseFloat(e.target.value)})} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Total Exposure ($)</Label><Input type="number" value={settings.max_total_exposure} onChange={(e) => setSettings({...settings, max_total_exposure: parseFloat(e.target.value)})} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Drawdown (%)</Label><div className="flex items-center gap-4"><Slider value={[settings.max_drawdown_pct]} onValueChange={([v]) => setSettings({...settings, max_drawdown_pct: v})} max={30} step={1} className="flex-1" /><span className="font-mono text-sm text-white w-12">{settings.max_drawdown_pct}%</span></div></div>
            <div className="space-y-2"><Label className="text-xs text-zinc-500">Max Consecutive Losses</Label><Input type="number" value={settings.max_consecutive_losses} onChange={(e) => setSettings({...settings, max_consecutive_losses: parseInt(e.target.value)})} className="bg-zinc-900 border-zinc-700 font-mono" /></div>
            <Button onClick={handleSaveSettings} className="btn-primary w-full" disabled={saving} data-testid="save-risk-settings-btn"><Save className="w-4 h-4 mr-2" />{saving ? 'Saving...' : 'Save Settings'}</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default RiskManager;
