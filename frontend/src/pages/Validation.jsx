import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { 
  Play, 
  Eye, 
  Clock, 
  CheckCircle, 
  AlertTriangle, 
  XCircle,
  RefreshCw,
  Pause,
  Activity,
  Calendar,
  Timer
} from 'lucide-react';
import { api } from "../App";

const Validation = () => {
  const [history, setHistory] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [watchStatus, setWatchStatus] = useState(null);
  const [scheduleStatus, setScheduleStatus] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [currentRunId, setCurrentRunId] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await api.get('/validation/history?limit=10');
      setHistory(response.data);
    } catch (error) {
      console.error('Error fetching history:', error);
    }
  }, []);

  const fetchWatchStatus = useCallback(async () => {
    try {
      const response = await api.get('/validation/watch/status');
      setWatchStatus(response.data);
    } catch (error) {
      console.error('Error fetching watch status:', error);
    }
  }, []);

  const fetchScheduleStatus = useCallback(async () => {
    try {
      const response = await api.get('/validation/schedule/status');
      setScheduleStatus(response.data);
    } catch (error) {
      console.error('Error fetching schedule status:', error);
    }
  }, []);

  const pollStatus = useCallback(async (runId) => {
    try {
      const response = await api.get(`/validation/status/${runId}`);
      if (response.data.status === 'completed' || response.data.status === 'failed') {
        setIsRunning(false);
        setCurrentRunId(null);
        fetchHistory();
        fetchScheduleStatus();
        const resultResponse = await api.get(`/validation/result/${runId}`);
        setSelectedRun(resultResponse.data);
      }
    } catch (error) {
      console.error('Error polling status:', error);
    }
  }, [fetchHistory, fetchScheduleStatus]);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchHistory(), fetchWatchStatus(), fetchScheduleStatus()]).finally(() => setLoading(false));
  }, [fetchHistory, fetchWatchStatus, fetchScheduleStatus]);

  useEffect(() => {
    let interval;
    if (isRunning && currentRunId) {
      interval = setInterval(() => pollStatus(currentRunId), 2000);
    }
    return () => clearInterval(interval);
  }, [isRunning, currentRunId, pollStatus]);

  const startValidation = async () => {
    try {
      setIsRunning(true);
      const response = await api.post('/validation/run');
      setCurrentRunId(response.data.run_id);
    } catch (error) {
      console.error('Error starting validation:', error);
      setIsRunning(false);
      alert(error.response?.data?.detail || 'Failed to start validation');
    }
  };

  const toggleWatchMode = async () => {
    try {
      if (watchStatus?.running) {
        await api.post('/validation/watch/stop');
      } else {
        await api.post('/validation/watch/start');
      }
      fetchWatchStatus();
    } catch (error) {
      console.error('Error toggling watch mode:', error);
      alert(error.response?.data?.detail || 'Failed to toggle watch mode');
    }
  };

  const toggleScheduler = async () => {
    try {
      if (scheduleStatus?.enabled) {
        await api.post('/validation/schedule/stop');
      } else {
        await api.post('/validation/schedule/start');
      }
      fetchScheduleStatus();
    } catch (error) {
      console.error('Error toggling scheduler:', error);
      alert(error.response?.data?.detail || 'Failed to toggle scheduler');
    }
  };

  const selectRun = async (runId) => {
    try {
      const response = await api.get(`/validation/result/${runId}`);
      setSelectedRun(response.data);
    } catch (error) {
      console.error('Error fetching run:', error);
    }
  };

  const getResultIcon = (result) => {
    switch (result) {
      case 'PASS': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'WARNING': return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'FAIL': return <XCircle className="h-4 w-4 text-red-500" />;
      default: return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getResultBadge = (result) => {
    const variants = {
      'PASS': 'bg-green-500/20 text-green-400 border-green-500/30',
      'WARNING': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      'FAIL': 'bg-red-500/20 text-red-400 border-red-500/30',
    };
    return variants[result] || 'bg-gray-500/20 text-gray-400';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Production Validation Pack</h1>
          <p className="text-gray-400 text-sm">E2E validation for 24/7 readiness</p>
        </div>
        <div className="flex gap-3">
          <Button 
            onClick={toggleWatchMode}
            variant={watchStatus?.running ? 'destructive' : 'outline'}
            className="gap-2"
          >
            {watchStatus?.running ? (
              <><Pause className="h-4 w-4" /> Stop Watch</>
            ) : (
              <><Activity className="h-4 w-4" /> Start Watch</>
            )}
          </Button>
          <Button 
            onClick={startValidation} 
            disabled={isRunning}
            className="gap-2 bg-blue-600 hover:bg-blue-700"
          >
            {isRunning ? (
              <><RefreshCw className="h-4 w-4 animate-spin" /> Running...</>
            ) : (
              <><Play className="h-4 w-4" /> Run Validation</>
            )}
          </Button>
        </div>
      </div>

      {/* Watch Mode Status */}
      {watchStatus && (
        <Card className="bg-gray-900/50 border-gray-800">
          <CardContent className="py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className={`h-3 w-3 rounded-full ${watchStatus.running ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
                <span className="text-sm">
                  Watch Mode: <strong>{watchStatus.running ? 'Active' : 'Inactive'}</strong>
                </span>
                {watchStatus.running && (
                  <>
                    <span className="text-gray-500">|</span>
                    <span className="text-sm text-gray-400">
                      Interval: {watchStatus.interval_seconds / 60}min
                    </span>
                    <span className="text-gray-500">|</span>
                    <span className="text-sm text-gray-400">
                      Checks: {watchStatus.check_count}
                    </span>
                  </>
                )}
              </div>
              <Badge variant="outline" className="text-xs">
                Mode: {watchStatus.trading_mode?.toUpperCase()}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Daily Auto-Validation Scheduler */}
      <Card className="bg-gray-900/50 border-gray-800">
        <CardContent className="py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Calendar className="h-5 w-5 text-blue-400" />
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">Daily Auto-Validation</span>
                  <Switch
                    checked={scheduleStatus?.enabled || false}
                    onCheckedChange={toggleScheduler}
                    className="data-[state=checked]:bg-blue-600"
                  />
                </div>
                <div className="text-xs text-gray-500">
                  Runs at {scheduleStatus?.schedule_time || '09:00'} ({scheduleStatus?.timezone || 'Europe/Lisbon'})
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {scheduleStatus?.next_run_at && (
                <div className="text-right">
                  <div className="text-xs text-gray-500">Next Run</div>
                  <div className="text-sm font-mono">
                    {new Date(scheduleStatus.next_run_at).toLocaleString('pt-PT', { 
                      month: 'short', 
                      day: 'numeric',
                      hour: '2-digit', 
                      minute: '2-digit' 
                    })}
                  </div>
                </div>
              )}
              {scheduleStatus?.last_run_at && (
                <div className="text-right">
                  <div className="text-xs text-gray-500">Last Run</div>
                  <div className="text-sm font-mono text-green-400">
                    {new Date(scheduleStatus.last_run_at).toLocaleString('pt-PT', { 
                      month: 'short', 
                      day: 'numeric',
                      hour: '2-digit', 
                      minute: '2-digit' 
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* History Panel */}
        <Card className="bg-gray-900/50 border-gray-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <Clock className="h-5 w-5" /> History
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {history.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-4">No validation runs yet</p>
            ) : (
              history.map((run) => (
                <div 
                  key={run.id}
                  onClick={() => selectRun(run.id)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selectedRun?.id === run.id 
                      ? 'border-blue-500 bg-blue-500/10' 
                      : 'border-gray-800 hover:border-gray-700 bg-gray-800/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {getResultIcon(run.overall_result)}
                      <span className="text-sm font-mono">{run.id.slice(0, 8)}</span>
                    </div>
                    <Badge className={getResultBadge(run.overall_result)}>
                      {run.passed}/{run.total_checks}
                    </Badge>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {new Date(run.started_at).toLocaleString()}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Result Detail Panel */}
        <Card className="lg:col-span-2 bg-gray-900/50 border-gray-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <Eye className="h-5 w-5" /> Validation Result
            </CardTitle>
          </CardHeader>
          <CardContent>
            {selectedRun ? (
              <div className="space-y-4">
                {/* Summary */}
                <div className="grid grid-cols-4 gap-3">
                  <div className="bg-gray-800/50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-green-400">{selectedRun.passed}</div>
                    <div className="text-xs text-gray-500">Passed</div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-yellow-400">{selectedRun.warnings}</div>
                    <div className="text-xs text-gray-500">Warnings</div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-red-400">{selectedRun.failed}</div>
                    <div className="text-xs text-gray-500">Failed</div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold">{selectedRun.total_checks}</div>
                    <div className="text-xs text-gray-500">Total</div>
                  </div>
                </div>

                {/* Warning Details */}
                {selectedRun.warning_checks?.length > 0 && (
                  <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                    <h4 className="text-sm font-semibold text-yellow-400 mb-2">⚠️ Warnings</h4>
                    {selectedRun.warning_checks.map((w, i) => (
                      <div key={i} className="text-sm text-gray-300">
                        <strong>{w.name}</strong>: {w.message}
                        {w.recommended_action && (
                          <div className="text-xs text-gray-500 ml-4">→ {w.recommended_action}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Checks List */}
                <div className="space-y-1 max-h-96 overflow-y-auto">
                  {selectedRun.checks?.map((check, idx) => (
                    <div 
                      key={idx}
                      className={`flex items-center gap-2 p-2 rounded text-sm ${
                        check.result === 'FAIL' ? 'bg-red-500/10' :
                        check.result === 'WARNING' ? 'bg-yellow-500/10' :
                        'bg-gray-800/30'
                      }`}
                    >
                      {getResultIcon(check.result)}
                      <Badge variant="outline" className="text-xs font-mono">
                        {check.category}
                      </Badge>
                      <span className="font-medium">{check.name}</span>
                      <span className="text-gray-500 text-xs truncate flex-1">
                        {check.message}
                      </span>
                      <span className="text-xs text-gray-600">
                        {check.duration_ms?.toFixed(0)}ms
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                <Eye className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>Select a validation run to see details</p>
                <p className="text-sm">or run a new validation</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Validation;
