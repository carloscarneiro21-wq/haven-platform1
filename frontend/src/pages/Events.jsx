import { useState, useEffect, useCallback } from "react";
import { api } from "../App";
import { toast } from "sonner";
import { 
  Clock, AlertTriangle, AlertOctagon, Info, Bug, Zap,
  Activity, Wifi, Shield, Bot, FileText, Bell, Database,
  RefreshCw, Download, Filter, ChevronRight, X
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../components/ui/sheet";

const SeverityIcon = ({ severity }) => {
  switch (severity) {
    case 'CRITICAL':
      return <AlertOctagon className="w-4 h-4 text-[#EF4444]" />;
    case 'ERROR':
      return <AlertTriangle className="w-4 h-4 text-[#F97316]" />;
    case 'WARNING':
      return <AlertTriangle className="w-4 h-4 text-[#F59E0B]" />;
    case 'INFO':
      return <Info className="w-4 h-4 text-[#3B82F6]" />;
    case 'DEBUG':
      return <Bug className="w-4 h-4 text-zinc-500" />;
    default:
      return <Info className="w-4 h-4" />;
  }
};

const SeverityBadge = ({ severity }) => {
  const colors = {
    CRITICAL: 'bg-[#EF4444]/20 text-[#EF4444]',
    ERROR: 'bg-[#F97316]/20 text-[#F97316]',
    WARNING: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    INFO: 'bg-[#3B82F6]/20 text-[#3B82F6]',
    DEBUG: 'bg-zinc-700 text-zinc-400',
  };
  return <Badge className={colors[severity] || 'bg-zinc-700 text-zinc-400'}>{severity}</Badge>;
};

const CategoryIcon = ({ category }) => {
  switch (category) {
    case 'ENGINE':
      return <Activity className="w-4 h-4" />;
    case 'DATA':
      return <Wifi className="w-4 h-4" />;
    case 'RISK':
      return <Shield className="w-4 h-4" />;
    case 'AGENT':
      return <Bot className="w-4 h-4" />;
    case 'ORDER':
      return <FileText className="w-4 h-4" />;
    case 'NOTIFY':
      return <Bell className="w-4 h-4" />;
    case 'SYSTEM':
      return <Database className="w-4 h-4" />;
    default:
      return <Zap className="w-4 h-4" />;
  }
};

const CategoryBadge = ({ category }) => {
  const colors = {
    ENGINE: 'bg-[#8B5CF6]/20 text-[#8B5CF6]',
    DATA: 'bg-[#06B6D4]/20 text-[#06B6D4]',
    RISK: 'bg-[#EF4444]/20 text-[#EF4444]',
    AGENT: 'bg-[#10B981]/20 text-[#10B981]',
    ORDER: 'bg-[#F59E0B]/20 text-[#F59E0B]',
    NOTIFY: 'bg-[#EC4899]/20 text-[#EC4899]',
    SYSTEM: 'bg-zinc-600 text-zinc-300',
  };
  return (
    <Badge className={`${colors[category] || 'bg-zinc-700 text-zinc-400'} flex items-center gap-1`}>
      <CategoryIcon category={category} />
      {category}
    </Badge>
  );
};

const Events = () => {
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [correlatedEvents, setCorrelatedEvents] = useState([]);
  const [showCorrelated, setShowCorrelated] = useState(false);
  
  // Filters
  const [filters, setFilters] = useState({
    severity: '',
    category: '',
    limit: 100,
  });
  const [eventTypes, setEventTypes] = useState([]);

  const fetchEvents = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.append('limit', filters.limit.toString());
      if (filters.severity) params.append('severity', filters.severity);
      if (filters.category) params.append('category', filters.category);
      
      const [eventsRes, summaryRes, typesRes] = await Promise.all([
        api.get(`/events?${params.toString()}`),
        api.get('/events/summary'),
        api.get('/events/types'),
      ]);
      
      setEvents(eventsRes.data);
      setSummary(summaryRes.data);
      setEventTypes(typesRes.data);
    } catch (e) {
      console.error("Failed to fetch events");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  const handleExport = () => {
    const dataStr = JSON.stringify(events, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `events_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Events exported");
  };

  const handleCreateTestEvent = async () => {
    try {
      await api.post('/events/test', {
        severity: 'INFO',
        category: 'SYSTEM',
        type: 'TEST_EVENT',
        message: 'Manual test event from UI',
      });
      toast.success("Test event created");
      fetchEvents();
    } catch (e) {
      toast.error("Failed to create test event");
    }
  };

  const openEventDetail = (event) => {
    setSelectedEvent(event);
    setSheetOpen(true);
    setShowCorrelated(false);
    setCorrelatedEvents([]);
  };

  const loadCorrelatedEvents = async (correlationId) => {
    try {
      const res = await api.get(`/events/correlation/${correlationId}`);
      setCorrelatedEvents(res.data);
      setShowCorrelated(true);
    } catch (e) {
      toast.error("Failed to load correlated events");
    }
  };

  const clearFilters = () => {
    setFilters({ severity: '', category: '', limit: 100 });
  };

  const formatTime = (ts) => {
    const date = new Date(ts);
    return date.toLocaleTimeString();
  };

  const formatDate = (ts) => {
    const date = new Date(ts);
    return date.toLocaleDateString();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-rajdhani text-3xl font-bold tracking-tight text-white uppercase flex items-center gap-3">
            <Clock className="w-8 h-8 text-[#3B82F6]" />
            Event Timeline
          </h1>
          <p className="text-sm font-mono text-zinc-500 mt-1">
            System events and audit log • Run ID: {summary?.current_run_id || '—'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={fetchEvents} variant="outline" className="btn-outline" size="sm">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={handleExport} variant="outline" className="btn-outline" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-5 gap-4">
          <Card className="trading-card">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-zinc-500 mb-1">Events (24h)</p>
              <p className="font-mono text-2xl text-white">{summary.total_24h}</p>
            </CardContent>
          </Card>
          <Card className="trading-card">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-zinc-500 mb-1">Warnings (1h)</p>
              <p className={`font-mono text-2xl ${summary.warnings_1h > 0 ? 'text-[#F59E0B]' : 'text-white'}`}>
                {summary.warnings_1h}
              </p>
            </CardContent>
          </Card>
          <Card className="trading-card">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-zinc-500 mb-1">Errors (24h)</p>
              <p className={`font-mono text-2xl ${(summary.by_severity?.ERROR || 0) > 0 ? 'text-[#F97316]' : 'text-white'}`}>
                {summary.by_severity?.ERROR || 0}
              </p>
            </CardContent>
          </Card>
          <Card className="trading-card">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-zinc-500 mb-1">Critical (24h)</p>
              <p className={`font-mono text-2xl ${(summary.by_severity?.CRITICAL || 0) > 0 ? 'text-[#EF4444]' : 'text-white'}`}>
                {summary.by_severity?.CRITICAL || 0}
              </p>
            </CardContent>
          </Card>
          <Card className="trading-card">
            <CardContent className="p-4 text-center">
              <p className="text-xs text-zinc-500 mb-1">Cycle</p>
              <p className="font-mono text-2xl text-white">{summary.current_cycle}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Critical Events */}
      {summary?.recent_critical?.length > 0 && (
        <Card className="trading-card border-[#EF4444]/30">
          <CardHeader className="trading-card-header">
            <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-[#EF4444] flex items-center gap-2">
              <AlertOctagon className="w-4 h-4" />
              Recent Critical Events
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-2">
            {(summary.recent_critical || [])
              .filter((e) => ![
                'SECURITY_DEFAULT_CREDENTIALS_DETECTED',
                'SECURITY_DEFAULT_CREDENTIALS_REVOKED',
              ].includes(e.type))
              .slice(0, 3)
              .map((event, idx) => (
                <div 
                  key={idx} 
                  className="flex items-center justify-between p-3 bg-[#EF4444]/10 rounded-sm cursor-pointer hover:bg-[#EF4444]/20"
                  onClick={() => openEventDetail(event)}
                >
                  <div className="flex items-center gap-3">
                    <AlertOctagon className="w-4 h-4 text-[#EF4444]" />
                    <div>
                      <p className="text-sm text-white">{event.message}</p>
                      <p className="text-xs text-zinc-500">{event.type}</p>
                    </div>
                  </div>
                  <span className="text-xs text-zinc-500 font-mono">{formatTime(event.ts)}</span>
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card className="trading-card">
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <Filter className="w-4 h-4 text-zinc-500" />
            
            <Select value={filters.severity || "all"} onValueChange={(v) => setFilters({...filters, severity: v === "all" ? '' : v})}>
              <SelectTrigger className="w-[150px] bg-zinc-900 border-zinc-700">
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="CRITICAL">Critical</SelectItem>
                <SelectItem value="ERROR">Error</SelectItem>
                <SelectItem value="WARNING">Warning</SelectItem>
                <SelectItem value="INFO">Info</SelectItem>
                <SelectItem value="DEBUG">Debug</SelectItem>
              </SelectContent>
            </Select>
            
            <Select value={filters.category || "all"} onValueChange={(v) => setFilters({...filters, category: v === "all" ? '' : v})}>
              <SelectTrigger className="w-[150px] bg-zinc-900 border-zinc-700">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="ENGINE">Engine</SelectItem>
                <SelectItem value="DATA">Data</SelectItem>
                <SelectItem value="RISK">Risk</SelectItem>
                <SelectItem value="AGENT">Agent</SelectItem>
                <SelectItem value="ORDER">Order</SelectItem>
                <SelectItem value="NOTIFY">Notify</SelectItem>
                <SelectItem value="SYSTEM">System</SelectItem>
              </SelectContent>
            </Select>
            
            <Select value={filters.limit.toString()} onValueChange={(v) => setFilters({...filters, limit: parseInt(v)})}>
              <SelectTrigger className="w-[120px] bg-zinc-900 border-zinc-700">
                <SelectValue placeholder="Limit" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-700">
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
                <SelectItem value="200">200</SelectItem>
                <SelectItem value="500">500</SelectItem>
              </SelectContent>
            </Select>
            
            {(filters.severity || filters.category) && (
              <Button variant="ghost" size="sm" onClick={clearFilters} className="text-zinc-500 hover:text-white">
                <X className="w-4 h-4 mr-1" />
                Clear
              </Button>
            )}
            
            <div className="flex-1" />
            
            <Button variant="outline" size="sm" onClick={handleCreateTestEvent} className="btn-outline">
              Test Event
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Events List */}
      <Card className="trading-card">
        <CardHeader className="trading-card-header">
          <CardTitle className="font-rajdhani text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            <Clock className="w-4 h-4" />
            Events ({events.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw className="w-6 h-6 text-zinc-500 animate-spin" />
            </div>
          ) : events.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-zinc-500">
              No events found
            </div>
          ) : (
            <div className="divide-y divide-zinc-800 max-h-[600px] overflow-y-auto">
              {events.map((event, idx) => (
                <div 
                  key={idx}
                  className="flex items-center gap-4 p-4 hover:bg-zinc-800/50 cursor-pointer transition-colors"
                  onClick={() => openEventDetail(event)}
                >
                  <div className="flex-shrink-0">
                    <SeverityIcon severity={event.severity} />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-[#8B5CF6]">{event.type}</span>
                      {event.symbol && (
                        <Badge variant="outline" className="font-mono text-xs">{event.symbol}</Badge>
                      )}
                      {event.agent_id && (
                        <Badge variant="outline" className="font-mono text-xs">{event.agent_id.slice(0, 8)}</Badge>
                      )}
                    </div>
                    <p className="text-sm text-zinc-300 truncate">{event.message}</p>
                  </div>
                  
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <CategoryBadge category={event.category} />
                    <SeverityBadge severity={event.severity} />
                    <div className="text-right">
                      <p className="text-xs text-zinc-400 font-mono">{formatTime(event.ts)}</p>
                      <p className="text-xs text-zinc-600 font-mono">{formatDate(event.ts)}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-zinc-600" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Event Detail Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="bg-zinc-900 border-zinc-800 w-[500px] sm:max-w-[500px]">
          <SheetHeader>
            <SheetTitle className="font-rajdhani text-xl uppercase tracking-wider text-white flex items-center gap-2">
              <SeverityIcon severity={selectedEvent?.severity} />
              Event Details
            </SheetTitle>
            <SheetDescription className="text-zinc-500">
              {selectedEvent?.type}
            </SheetDescription>
          </SheetHeader>
          
          {selectedEvent && (
            <div className="mt-6 space-y-4">
              <div className="flex gap-2">
                <SeverityBadge severity={selectedEvent.severity} />
                <CategoryBadge category={selectedEvent.category} />
              </div>
              
              <div className="p-4 bg-zinc-800 rounded-sm">
                <p className="text-xs text-zinc-500 mb-1">Message</p>
                <p className="text-sm text-white">{selectedEvent.message}</p>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Timestamp</p>
                  <p className="text-sm text-white font-mono">{new Date(selectedEvent.ts).toLocaleString()}</p>
                </div>
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Run ID</p>
                  <p className="text-sm text-white font-mono">{selectedEvent.run_id || '—'}</p>
                </div>
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Cycle</p>
                  <p className="text-sm text-white font-mono">{selectedEvent.cycle_id ?? '—'}</p>
                </div>
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Source</p>
                  <p className="text-sm text-white font-mono">{selectedEvent.source || '—'}</p>
                </div>
              </div>
              
              {selectedEvent.symbol && (
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Symbol</p>
                  <p className="text-sm text-white font-mono">{selectedEvent.symbol}</p>
                </div>
              )}
              
              {selectedEvent.agent_id && (
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-1">Agent ID</p>
                  <p className="text-sm text-white font-mono">{selectedEvent.agent_id}</p>
                </div>
              )}
              
              {selectedEvent.tags?.length > 0 && (
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-2">Tags</p>
                  <div className="flex flex-wrap gap-1">
                    {selectedEvent.tags.map((tag, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs">{tag}</Badge>
                    ))}
                  </div>
                </div>
              )}
              
              {selectedEvent.context && Object.keys(selectedEvent.context).length > 0 && (
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <p className="text-xs text-zinc-500 mb-2">Context</p>
                  <pre className="text-xs text-zinc-300 font-mono overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(selectedEvent.context, null, 2)}
                  </pre>
                </div>
              )}
              
              {selectedEvent.correlation_id && (
                <div className="p-3 bg-zinc-800 rounded-sm">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs text-zinc-500">Correlation ID</p>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={() => loadCorrelatedEvents(selectedEvent.correlation_id)}
                      className="text-[#8B5CF6] hover:text-[#A78BFA] text-xs h-6"
                    >
                      Show Related →
                    </Button>
                  </div>
                  <p className="text-sm text-white font-mono">{selectedEvent.correlation_id}</p>
                </div>
              )}
              
              {/* Correlated Events Chain */}
              {showCorrelated && correlatedEvents.length > 0 && (
                <div className="p-3 bg-[#8B5CF6]/10 rounded-sm border border-[#8B5CF6]/30">
                  <p className="text-xs text-[#8B5CF6] mb-3 font-semibold">Related Events Chain ({correlatedEvents.length})</p>
                  <div className="space-y-2">
                    {correlatedEvents.map((evt, idx) => (
                      <div 
                        key={idx} 
                        className={`flex items-center gap-2 p-2 rounded-sm ${evt.id === selectedEvent.id ? 'bg-[#8B5CF6]/20' : 'bg-zinc-800/50'}`}
                      >
                        <div className="flex items-center gap-1">
                          {idx > 0 && <span className="text-zinc-600">↳</span>}
                          <SeverityIcon severity={evt.severity} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-mono text-[#8B5CF6]">{evt.type}</p>
                          <p className="text-xs text-zinc-400 truncate">{evt.message}</p>
                        </div>
                        <span className="text-xs text-zinc-600 font-mono">{formatTime(evt.ts)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default Events;
