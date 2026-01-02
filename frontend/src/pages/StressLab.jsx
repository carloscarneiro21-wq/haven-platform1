import { useState, useEffect } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { 
  FlaskConical, Zap, TrendingDown, TrendingUp, Clock, Wifi, 
  RotateCcw, AlertTriangle, CheckCircle2, XCircle, Play, Loader2,
  Shield, Activity, AlertOctagon
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";

const ScenarioIcon = ({ type }) => {
  switch (type) {
    case 'flash_crash':
      return <TrendingDown className="w-5 h-5 text-[#EF4444]" />;
    case 'flash_pump':
      return <TrendingUp className="w-5 h-5 text-[#10B981]" />;
    case 'latency_spike':
      return <Clock className="w-5 h-5 text-[#F59E0B]" />;
    case 'partial_fills':
      return <Activity className="w-5 h-5 text-[#8B5CF6]" />;
    case 'data_stale':
      return <Wifi className="w-5 h-5 text-[#6366F1]" />;
    case 'restart_drill':
      return <RotateCcw className="w-5 h-5 text-[#06B6D4]" />;
    default:
      return <Zap className="w-5 h-5" />;
  }
};

const StressLab = () => {
  const [scenarios, setScenarios] = useState([]);
  const [labStatus, setLabStatus] = useState({ running: false, active_test: null });
  const [history, setHistory] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [confirmationCode, setConfirmationCode] = useState('');
  const [running, setRunning] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [scenariosRes, statusRes, historyRes] = await Promise.all([
        api.get("/stress-lab/scenarios"),
        api.get("/stress-lab/status"),
        api.get("/stress-lab/history"),
      ]);
      setScenarios(scenariosRes.data);
      setLabStatus(statusRes.data);
      setHistory(historyRes.data);
    } catch (e) {
      console.error("Failed to fetch stress lab data");
    }
  };

  const fetchStatus = async () => {
    try {
      const res = await api.get("/stress-lab/status");
      setLabStatus(res.data);
    } catch (e) {
      // Silently ignore status check errors
    }
  };

  const handleSelectScenario = (scenario) => {
    setSelectedScenario(scenario);
    setConfirmationCode('');
    setShowConfirmDialog(true);
  };

  const handleRunScenario = async () => {
    if (confirmationCode !== 'STRESS') {
      toast.error("Type 'STRESS' to confirm");
      return;
    }

    setRunning(true);
    setShowConfirmDialog(false);

    try {
      const res = await api.post("/stress-lab/run", {
        scenario_type: selectedScenario.type,
        confirmation_code: confirmationCode,
      });
      setTestResult(res.data);
      toast.success("Stress test completed!");
      fetchData();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to run stress test");
    } finally {
      setRunning(false);
      setConfirmationCode('');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase flex items-center gap-3">
            <FlaskConical className="w-8 h-8 text-[#8B5CF6]" />
            Stress Lab
          </h1>
          <p className="text-sm font-mono text-zinc-500 mt-1">
            Interactive stress testing • PAPER TRADING ONLY
          </p>
        </div>
        <Badge className={labStatus.running ? 'bg-[#F59E0B]/20 text-[#F59E0B]' : 'status-running'}>
          {labStatus.running ? 'TEST RUNNING' : 'READY'}
        </Badge>
      </div>

      {/* Warning Banner */}
      <Card className="trading-card border-[#F59E0B]/30">
        <CardContent className="p-4 flex items-center gap-4">
          <AlertTriangle className="w-8 h-8 text-[#F59E0B] flex-shrink-0" />
          <div>
            <p className="text-sm text-[#F59E0B] font-semibold">Paper Trading Mode Only</p>
            <p className="text-xs text-zinc-400">
              Stress tests simulate market conditions to test system resilience. All tests require confirmation code &quot;STRESS&quot; to prevent accidental execution.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Scenarios Grid */}
      <div className="grid grid-cols-3 gap-4">
        {scenarios.map((scenario) => (
          <Card key={scenario.type} className="trading-card hover:border-[#8B5CF6]/50 transition-colors cursor-pointer" onClick={() => handleSelectScenario(scenario)}>
            <CardHeader className="trading-card-header pb-2">
              <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                <ScenarioIcon type={scenario.type} />
                {scenario.name}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <p className="text-xs text-zinc-400 line-clamp-2">{scenario.description}</p>
              
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500 mb-1">Expected Outcome</p>
                <p className="text-xs text-[#10B981] line-clamp-2">{scenario.expected_outcome}</p>
              </div>
              
              <div className="flex items-center justify-between">
                <Badge variant="outline" className="font-mono text-xs">
                  {scenario.duration_seconds}s
                </Badge>
                <Button 
                  size="sm" 
                  className="btn-primary"
                  disabled={labStatus.running || running}
                >
                  <Play className="w-3 h-3 mr-1" />
                  Run
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Test Result Panel */}
      {testResult && (
        <Card className="trading-card border-[#8B5CF6]/30">
          <CardHeader className="trading-card-header">
            <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
              Latest Test Result
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            <div className="grid grid-cols-4 gap-4">
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500">Status</p>
                <Badge className={testResult.status === 'completed' ? 'status-running' : 'status-stopped'}>
                  {testResult.status?.toUpperCase()}
                </Badge>
              </div>
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500">Outcome Match</p>
                <div className="flex items-center gap-1">
                  {testResult.outcome_matched ? (
                    <><CheckCircle2 className="w-4 h-4 text-[#10B981]" /><span className="text-[#10B981] text-sm">YES</span></>
                  ) : (
                    <><XCircle className="w-4 h-4 text-[#EF4444]" /><span className="text-[#EF4444] text-sm">NO</span></>
                  )}
                </div>
              </div>
              <div className="p-3 bg-zinc-900 rounded-sm col-span-2">
                <p className="text-xs text-zinc-500">Actual Outcome</p>
                <p className="text-sm text-white">{testResult.actual_outcome || 'N/A'}</p>
              </div>
            </div>

            {/* State Comparison */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500 mb-2 flex items-center gap-1">
                  <Shield className="w-3 h-3" /> Pre-Test State
                </p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Positions:</span> <span className="text-white font-mono">{testResult.pre_state?.open_positions_count || 0}</span></div>
                  <div><span className="text-zinc-500">Risk:</span> <span className="text-white font-mono">{testResult.pre_state?.risk_state || 'OK'}</span></div>
                  <div><span className="text-zinc-500">Safe Mode:</span> <span className="text-white font-mono">{testResult.pre_state?.safe_mode ? 'ON' : 'OFF'}</span></div>
                  <div><span className="text-zinc-500">Kill Switch:</span> <span className="text-white font-mono">{testResult.pre_state?.kill_switch_active ? 'ON' : 'OFF'}</span></div>
                </div>
              </div>
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500 mb-2 flex items-center gap-1">
                  <AlertOctagon className="w-3 h-3" /> Post-Test State
                </p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Positions:</span> <span className="text-white font-mono">{testResult.post_state?.open_positions_count || 0}</span></div>
                  <div><span className="text-zinc-500">Risk:</span> <span className={`font-mono ${testResult.post_state?.risk_state === 'HALTED' ? 'text-[#EF4444]' : testResult.post_state?.risk_state === 'WARNING' ? 'text-[#F59E0B]' : 'text-white'}`}>{testResult.post_state?.risk_state || 'OK'}</span></div>
                  <div><span className="text-zinc-500">Safe Mode:</span> <span className={`font-mono ${testResult.post_state?.safe_mode ? 'text-[#F59E0B]' : 'text-white'}`}>{testResult.post_state?.safe_mode ? 'ON' : 'OFF'}</span></div>
                  <div><span className="text-zinc-500">Kill Switch:</span> <span className={`font-mono ${testResult.post_state?.kill_switch_active ? 'text-[#EF4444]' : 'text-white'}`}>{testResult.post_state?.kill_switch_active ? 'ON' : 'OFF'}</span></div>
                </div>
              </div>
            </div>

            {/* Events Timeline */}
            {testResult.events && testResult.events.length > 0 && (
              <div className="p-3 bg-zinc-900 rounded-sm">
                <p className="text-xs text-zinc-500 mb-2">Events Timeline</p>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {testResult.events.map((event, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs">
                      <span className="text-zinc-600 font-mono">{new Date(event.time).toLocaleTimeString()}</span>
                      <span className="text-[#8B5CF6]">{event.event}</span>
                      {event.circuit_breaker_triggered && <Badge className="bg-[#EF4444]/20 text-[#EF4444]">CIRCUIT BREAKER</Badge>}
                      {event.safe_mode_activated && <Badge className="bg-[#F59E0B]/20 text-[#F59E0B]">SAFE MODE</Badge>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Test History */}
      <Card className="trading-card">
        <CardHeader className="trading-card-header">
          <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            <Clock className="w-4 h-4" />
            Test History
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          {history.length === 0 ? (
            <p className="text-zinc-500 text-sm text-center py-4">No stress tests run yet</p>
          ) : (
            <div className="space-y-2">
              {history.slice(0, 10).map((run, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-zinc-900 rounded-sm">
                  <div className="flex items-center gap-3">
                    <ScenarioIcon type={run.scenario_type} />
                    <div>
                      <p className="text-sm text-white font-rajdhani uppercase">{run.scenario_type?.replace('_', ' ')}</p>
                      <p className="text-xs text-zinc-500 font-mono">{new Date(run.started_at).toLocaleString()}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={run.status === 'completed' ? 'status-running' : 'status-stopped'}>
                      {run.status}
                    </Badge>
                    {run.outcome_matched !== undefined && (
                      run.outcome_matched ? (
                        <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                      ) : (
                        <XCircle className="w-4 h-4 text-[#EF4444]" />
                      )
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="font-rajdhani text-xl uppercase tracking-wider text-white flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-[#F59E0B]" />
              Confirm Stress Test
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              You are about to run: <span className="text-white font-semibold">{selectedScenario?.name}</span>
            </DialogDescription>
          </DialogHeader>

          {selectedScenario && (
            <div className="space-y-4">
              <div className="p-4 bg-zinc-800 rounded-sm">
                <p className="text-xs text-zinc-500 mb-1">Description</p>
                <p className="text-sm text-zinc-300">{selectedScenario.description}</p>
              </div>
              
              <div className="p-4 bg-zinc-800 rounded-sm">
                <p className="text-xs text-zinc-500 mb-1">Expected Outcome</p>
                <p className="text-sm text-[#10B981]">{selectedScenario.expected_outcome}</p>
              </div>

              <div className="space-y-2">
                <p className="text-xs text-zinc-500">Type <span className="text-[#F59E0B] font-bold">STRESS</span> to confirm:</p>
                <Input
                  value={confirmationCode}
                  onChange={(e) => setConfirmationCode(e.target.value.toUpperCase())}
                  placeholder="Type STRESS"
                  className="bg-zinc-800 border-zinc-700 font-mono text-center text-lg"
                  autoFocus
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirmDialog(false)} className="btn-outline">
              Cancel
            </Button>
            <Button 
              onClick={handleRunScenario} 
              disabled={confirmationCode !== 'STRESS' || running}
              className="btn-primary"
            >
              {running ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Running...</>
              ) : (
                <><Play className="w-4 h-4 mr-2" />Run Test</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default StressLab;
