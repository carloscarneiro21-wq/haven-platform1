import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Shield,
  Target,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Activity,
  Zap,
  RefreshCw,
  Loader2,
  ArrowUpCircle,
  Ban,
  Clock,
  Gauge,
  FileText,
  Eye,
} from "lucide-react";

// Simple bar chart component
const SimpleBarChart = ({ data, labelKey, valueKey, maxValue, color = "#F0B90B" }) => {
  const max = maxValue || Math.max(...data.map(d => d[valueKey]), 1);
  
  return (
    <div className="space-y-2">
      {data.map((item, idx) => (
        <div key={idx} className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#B7BDC6] truncate max-w-[200px]" title={item[labelKey]}>
              {item[labelKey]}
            </span>
            <span className="text-[#EAECEF] font-medium">{item[valueKey]}</span>
          </div>
          <div className="h-2 bg-[#2B3139] rounded-full overflow-hidden">
            <div 
              className="h-full rounded-full transition-all duration-500"
              style={{ 
                width: `${(item[valueKey] / max) * 100}%`,
                backgroundColor: color
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
};

// Simple line indicator
const TrendLine = ({ data, valueKey, color = "#F0B90B" }) => {
  if (!data || data.length < 2) return null;
  
  const values = data.map(d => d[valueKey]);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  
  const points = values.map((v, i) => ({
    x: (i / (values.length - 1)) * 100,
    y: 100 - ((v - min) / range) * 100
  }));
  
  const pathD = points.map((p, i) => 
    `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`
  ).join(' ');
  
  return (
    <svg className="w-full h-16" viewBox="0 0 100 100" preserveAspectRatio="none">
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

// Distribution display
const DistributionBars = ({ distribution }) => {
  const items = [
    { label: "Low (0-25)", value: distribution.low_0_25 || 0, color: "#22c55e" },
    { label: "Medium (25-50)", value: distribution.medium_25_50 || 0, color: "#eab308" },
    { label: "High (50-75)", value: distribution.high_50_75 || 0, color: "#f97316" },
    { label: "Critical (75+)", value: distribution.critical_75_100 || 0, color: "#ef4444" },
  ];
  
  const total = items.reduce((sum, i) => sum + i.value, 0) || 1;
  
  return (
    <div className="space-y-2">
      {items.map((item, idx) => (
        <div key={idx} className="flex items-center gap-3">
          <div className="w-24 text-xs text-[#848E9C]">{item.label}</div>
          <div className="flex-1 h-4 bg-[#2B3139] rounded-full overflow-hidden">
            <div 
              className="h-full rounded-full transition-all"
              style={{ 
                width: `${(item.value / total) * 100}%`,
                backgroundColor: item.color
              }}
            />
          </div>
          <div className="w-10 text-xs text-[#EAECEF] text-right">{item.value}</div>
        </div>
      ))}
    </div>
  );
};

// Stat card component
const StatCard = ({ icon: Icon, label, value, subValue, trend, color = "text-[#F0B90B]" }) => (
  <div className="p-4 bg-[#2B3139] rounded-lg">
    <div className="flex items-center gap-2 mb-2">
      <Icon className={`w-4 h-4 ${color}`} />
      <span className="text-xs text-[#848E9C]">{label}</span>
    </div>
    <div className="text-2xl font-bold text-[#EAECEF]">{value}</div>
    {subValue && <div className="text-xs text-[#848E9C] mt-1">{subValue}</div>}
    {trend !== undefined && (
      <div className={`text-xs mt-1 flex items-center gap-1 ${trend >= 0 ? 'text-green-500' : 'text-red-500'}`}>
        {trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
        {Math.abs(trend)}%
      </div>
    )}
  </div>
);

const Analytics = () => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [timeRange, setTimeRange] = useState("30");
  const [activeTab, setActiveTab] = useState("sandbox");

  // Debug / diagnostics (shown in UI when analytics fails)
  const [analyticsError, setAnalyticsError] = useState(null);
  
  // Analytics data
  const [sandboxData, setSandboxData] = useState(null);
  const [guardianData, setGuardianData] = useState(null);
  const [sniperData, setSniperData] = useState(null);
  const [promotionsData, setPromotionsData] = useState(null);

  useEffect(() => {
    fetchAllAnalytics();
  }, [timeRange]);

  const fetchAllAnalytics = async () => {
    const endpoint = `/analytics/all?days=${timeRange}`;
    setLoading(true);
    setAnalyticsError(null);

    try {
      const response = await api.get(endpoint);
      setSandboxData(response.data.sandbox);
      setGuardianData(response.data.guardian);
      setSniperData(response.data.sniper);
      setPromotionsData(response.data.promotions);
    } catch (error) {
      const status = error?.response?.status ?? null;
      const detail = error?.response?.data?.detail ?? error?.message ?? "Unknown error";

      setAnalyticsError({
        endpoint,
        status,
        detail,
      });

      console.error("Failed to fetch analytics:", error);
      toast.error("Failed to load analytics data");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchAllAnalytics();
    setRefreshing(false);
    toast.success("Analytics refreshed");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-[#F0B90B]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {analyticsError && (
        <Card className="bg-[#1E2329] border border-[#EF4444]/40">
          <CardHeader>
            <CardTitle className="text-sm text-[#EAECEF] flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-[#EF4444]" />
              Analytics request failed
            </CardTitle>
            <CardDescription className="text-xs">
              This diagnostic block is enabled to help debug intermittent failures.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-xs">
              <span className="text-[#848E9C]">Endpoint: </span>
              <span className="font-mono text-[#EAECEF]">{analyticsError.endpoint}</span>
            </div>
            <div className="text-xs">
              <span className="text-[#848E9C]">Status: </span>
              <span className="font-mono text-[#EAECEF]">{String(analyticsError.status ?? "(no response)")}</span>
            </div>
            <div className="text-xs">
              <span className="text-[#848E9C]">Detail: </span>
              <div className="mt-1 p-2 rounded bg-black/20 border border-white/10">
                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-[#EAECEF]">{String(analyticsError.detail)}</pre>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#EAECEF] flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-[#F0B90B]" />
            Analytics
          </h1>
          <p className="text-[#848E9C] text-sm">System observability and performance insights</p>
        </div>
        
        <div className="flex items-center gap-3">
          <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] border border-[#F0B90B]/30">
            <Eye className="w-3 h-3 mr-1.5" />
            READ-ONLY
          </Badge>
          
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-32 bg-[#2B3139] border-white/8 text-[#EAECEF]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#2B3139] border-white/8">
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
          
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleRefresh}
            disabled={refreshing}
            className="border-white/10"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-[#1E2329] border border-white/8">
          <TabsTrigger value="sandbox" className="data-[state=active]:bg-[#2B3139]">
            <Activity className="w-4 h-4 mr-2" />
            Sandbox
          </TabsTrigger>
          <TabsTrigger value="guardian" className="data-[state=active]:bg-[#2B3139]">
            <Shield className="w-4 h-4 mr-2" />
            Guardian
          </TabsTrigger>
          <TabsTrigger value="sniper" className="data-[state=active]:bg-[#2B3139]">
            <Target className="w-4 h-4 mr-2" />
            Sniper Hardening
          </TabsTrigger>
          <TabsTrigger value="promotions" className="data-[state=active]:bg-[#2B3139]">
            <ArrowUpCircle className="w-4 h-4 mr-2" />
            Promotions
          </TabsTrigger>
        </TabsList>

        {/* Sandbox Analytics Tab */}
        <TabsContent value="sandbox" className="space-y-4">
          {sandboxData && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  icon={Activity}
                  label="Total Runs"
                  value={sandboxData.summary.total_runs}
                  color="text-blue-500"
                />
                <StatCard
                  icon={Gauge}
                  label="Avg Survival Score"
                  value={`${sandboxData.summary.avg_survival_score}/100`}
                  color="text-green-500"
                />
                <StatCard
                  icon={TrendingDown}
                  label="Avg Max Drawdown"
                  value={`${sandboxData.summary.avg_max_drawdown}%`}
                  color="text-red-500"
                />
                <StatCard
                  icon={Clock}
                  label="Avg Stabilization"
                  value={`${sandboxData.summary.avg_time_to_stabilize}s`}
                  color="text-yellow-500"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Survival Score Trend */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Survival Score Trend</CardTitle>
                    <CardDescription>Historical survival scores across runs</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <TrendLine 
                      data={sandboxData.survival_scores} 
                      valueKey="value" 
                      color="#22c55e"
                    />
                    <div className="flex items-center justify-between mt-4 text-xs text-[#848E9C]">
                      <span>Oldest</span>
                      <span>Most Recent</span>
                    </div>
                  </CardContent>
                </Card>

                {/* Runs by Severity */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Runs by Severity</CardTitle>
                    <CardDescription>Distribution of stress test intensities</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(sandboxData.summary.runs_by_severity).map(([severity, count]) => {
                        const colors = {
                          LOW: "#22c55e",
                          MED: "#eab308",
                          HIGH: "#f97316",
                          APOC: "#ef4444"
                        };
                        const total = sandboxData.summary.total_runs || 1;
                        return (
                          <div key={severity} className="flex items-center gap-3">
                            <Badge className={`w-16 justify-center ${
                              severity === "LOW" ? "bg-green-500/20 text-green-500" :
                              severity === "MED" ? "bg-yellow-500/20 text-yellow-500" :
                              severity === "HIGH" ? "bg-orange-500/20 text-orange-500" :
                              "bg-red-500/20 text-red-500"
                            }`}>
                              {severity}
                            </Badge>
                            <div className="flex-1 h-4 bg-[#2B3139] rounded-full overflow-hidden">
                              <div 
                                className="h-full rounded-full transition-all"
                                style={{ 
                                  width: `${(count / total) * 100}%`,
                                  backgroundColor: colors[severity]
                                }}
                              />
                            </div>
                            <span className="w-8 text-sm text-[#EAECEF] text-right">{count}</span>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>

                {/* Max Drawdown Distribution */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Max Drawdown Trend</CardTitle>
                    <CardDescription>Drawdown percentage per run</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <TrendLine 
                      data={sandboxData.max_drawdowns} 
                      valueKey="value" 
                      color="#ef4444"
                    />
                    <div className="flex items-center justify-between mt-4 text-xs text-[#848E9C]">
                      <span>Oldest</span>
                      <span>Most Recent</span>
                    </div>
                  </CardContent>
                </Card>

                {/* Time to Stabilize */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Time to Stabilize</CardTitle>
                    <CardDescription>Recovery time per scenario</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <TrendLine 
                      data={sandboxData.time_to_stabilize} 
                      valueKey="value" 
                      color="#3b82f6"
                    />
                    <div className="flex items-center justify-between mt-4 text-xs text-[#848E9C]">
                      <span>Oldest</span>
                      <span>Most Recent</span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        {/* Guardian Analytics Tab */}
        <TabsContent value="guardian" className="space-y-4">
          {guardianData && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  icon={Ban}
                  label="Total Blocked"
                  value={guardianData.summary.total_blocked}
                  color="text-red-500"
                />
                <StatCard
                  icon={AlertTriangle}
                  label="Total Warned"
                  value={guardianData.summary.total_warned}
                  color="text-yellow-500"
                />
                <StatCard
                  icon={XCircle}
                  label="Total Halts"
                  value={guardianData.summary.total_halts}
                  color="text-red-600"
                />
                <StatCard
                  icon={Gauge}
                  label="Block Ratio"
                  value={`${guardianData.summary.block_ratio_pct}%`}
                  subValue={`Warn: ${guardianData.summary.warn_ratio_pct}%`}
                  color="text-orange-500"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Top Block Reasons */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Top Block Reasons</CardTitle>
                    <CardDescription>Most common reasons for trade blocking</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {guardianData.top_block_reasons.length > 0 ? (
                      <SimpleBarChart 
                        data={guardianData.top_block_reasons}
                        labelKey="reason"
                        valueKey="count"
                        color="#ef4444"
                      />
                    ) : (
                      <div className="text-center py-8 text-[#848E9C]">
                        <CheckCircle2 className="w-12 h-12 mx-auto mb-2 text-green-500 opacity-50" />
                        <p>No blocked trades in this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Decisions Breakdown */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Decisions Breakdown</CardTitle>
                    <CardDescription>Distribution of guardian decisions</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {Object.entries(guardianData.decisions_breakdown).map(([decision, count]) => {
                        const total = Object.values(guardianData.decisions_breakdown).reduce((a, b) => a + b, 1);
                        const colors = {
                          BLOCK: "#ef4444",
                          WARN: "#eab308",
                          HALT: "#dc2626"
                        };
                        return (
                          <div key={decision} className="space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="text-sm text-[#B7BDC6]">{decision}</span>
                              <span className="text-sm text-[#EAECEF] font-medium">
                                {count} ({((count / total) * 100).toFixed(1)}%)
                              </span>
                            </div>
                            <Progress 
                              value={(count / total) * 100} 
                              className="h-2 bg-[#2B3139]"
                              style={{ '--progress-color': colors[decision] }}
                            />
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>

                {/* Top Warning Reasons */}
                <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Top Warning Reasons</CardTitle>
                    <CardDescription>Most common warning triggers</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {guardianData.top_warn_reasons.length > 0 ? (
                      <div className="grid grid-cols-2 gap-4">
                        <SimpleBarChart 
                          data={guardianData.top_warn_reasons.slice(0, 5)}
                          labelKey="reason"
                          valueKey="count"
                          color="#eab308"
                        />
                        {guardianData.top_warn_reasons.length > 5 && (
                          <SimpleBarChart 
                            data={guardianData.top_warn_reasons.slice(5, 10)}
                            labelKey="reason"
                            valueKey="count"
                            color="#eab308"
                          />
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-[#848E9C]">
                        <CheckCircle2 className="w-12 h-12 mx-auto mb-2 text-green-500 opacity-50" />
                        <p>No warnings in this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        {/* Sniper Hardening Analytics Tab */}
        <TabsContent value="sniper" className="space-y-4">
          {sniperData && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  icon={Target}
                  label="Total Evaluations"
                  value={sniperData.summary.total_evaluations}
                  color="text-blue-500"
                />
                <StatCard
                  icon={Ban}
                  label="Block Rate"
                  value={`${sniperData.summary.block_rate_pct}%`}
                  subValue={`${sniperData.summary.blocked_count} blocked`}
                  color="text-red-500"
                />
                <StatCard
                  icon={Zap}
                  label="Avg MEV Risk"
                  value={sniperData.summary.avg_mev_risk}
                  color="text-yellow-500"
                />
                <StatCard
                  icon={TrendingDown}
                  label="Avg Size Reduction"
                  value={`${sniperData.summary.avg_size_reduction_pct}%`}
                  color="text-orange-500"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Top Failing Gates */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Top Failing Gates</CardTitle>
                    <CardDescription>Gates that block the most entries</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {sniperData.top_failing_gates.length > 0 ? (
                      <SimpleBarChart 
                        data={sniperData.top_failing_gates}
                        labelKey="gate"
                        valueKey="count"
                        color="#ef4444"
                      />
                    ) : (
                      <div className="text-center py-8 text-[#848E9C]">
                        <CheckCircle2 className="w-12 h-12 mx-auto mb-2 text-green-500 opacity-50" />
                        <p>No gate failures in this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* MEV Risk Distribution */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">MEV Risk Distribution</CardTitle>
                    <CardDescription>Distribution of MEV attack risk scores</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <DistributionBars distribution={sniperData.mev_distribution} />
                  </CardContent>
                </Card>

                {/* Decisions Breakdown */}
                <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Evaluation Decisions</CardTitle>
                    <CardDescription>How sniper entries were evaluated</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4">
                      {Object.entries(sniperData.decisions_breakdown).map(([decision, count]) => {
                        const total = Object.values(sniperData.decisions_breakdown).reduce((a, b) => a + b, 1);
                        const colors = {
                          ALLOW: { bg: "bg-green-500/20", text: "text-green-500", icon: CheckCircle2 },
                          WARN: { bg: "bg-yellow-500/20", text: "text-yellow-500", icon: AlertTriangle },
                          BLOCK: { bg: "bg-red-500/20", text: "text-red-500", icon: XCircle }
                        };
                        const config = colors[decision] || colors.BLOCK;
                        const Icon = config.icon;
                        
                        return (
                          <div key={decision} className={`p-4 rounded-lg ${config.bg}`}>
                            <div className="flex items-center gap-2 mb-2">
                              <Icon className={`w-5 h-5 ${config.text}`} />
                              <span className={`font-medium ${config.text}`}>{decision}</span>
                            </div>
                            <div className="text-3xl font-bold text-[#EAECEF]">{count}</div>
                            <div className="text-xs text-[#848E9C]">
                              {((count / total) * 100).toFixed(1)}% of total
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        {/* Promotions Analytics Tab */}
        <TabsContent value="promotions" className="space-y-4">
          {promotionsData && (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  icon={FileText}
                  label="Total Requests"
                  value={promotionsData.summary.total_requests}
                  color="text-blue-500"
                />
                <StatCard
                  icon={CheckCircle2}
                  label="Promoted"
                  value={promotionsData.summary.promoted_count}
                  subValue={`${promotionsData.summary.approval_rate_pct}% rate`}
                  color="text-green-500"
                />
                <StatCard
                  icon={XCircle}
                  label="Rejected"
                  value={promotionsData.summary.rejected_count}
                  subValue={`${promotionsData.summary.rejection_rate_pct}% rate`}
                  color="text-red-500"
                />
                <StatCard
                  icon={Clock}
                  label="Pending"
                  value={promotionsData.summary.pending_count}
                  color="text-yellow-500"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Status Breakdown */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Status Breakdown</CardTitle>
                    <CardDescription>Promotion request statuses</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(promotionsData.status_breakdown).map(([status, count]) => {
                        const total = promotionsData.summary.total_requests || 1;
                        const colors = {
                          draft: "#6b7280",
                          pending: "#eab308",
                          approved: "#22c55e",
                          rejected: "#ef4444",
                          applied: "#3b82f6"
                        };
                        return (
                          <div key={status} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-[#B7BDC6] capitalize">{status}</span>
                              <span className="text-[#EAECEF]">{count}</span>
                            </div>
                            <div className="h-2 bg-[#2B3139] rounded-full overflow-hidden">
                              <div 
                                className="h-full rounded-full transition-all"
                                style={{ 
                                  width: `${(count / total) * 100}%`,
                                  backgroundColor: colors[status]
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>

                {/* Target Environment */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">By Target Environment</CardTitle>
                    <CardDescription>Promotion destinations</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-[#2B3139] rounded-lg text-center">
                        <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] mb-2">paper_live</Badge>
                        <div className="text-3xl font-bold text-[#EAECEF]">
                          {promotionsData.by_target_env.paper_live || 0}
                        </div>
                        <div className="text-xs text-[#848E9C]">Paper trading</div>
                      </div>
                      <div className="p-4 bg-[#2B3139]/50 rounded-lg text-center opacity-50">
                        <Badge className="bg-[#848E9C]/20 text-[#848E9C] mb-2">live</Badge>
                        <div className="text-3xl font-bold text-[#848E9C]">
                          {promotionsData.by_target_env.live || 0}
                        </div>
                        <div className="text-xs text-[#848E9C]">Disabled</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Top Rejection Reasons */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Rejection Reasons</CardTitle>
                    <CardDescription>Why promotions were rejected</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {promotionsData.top_rejected_reasons.length > 0 ? (
                      <SimpleBarChart 
                        data={promotionsData.top_rejected_reasons}
                        labelKey="reason"
                        valueKey="count"
                        color="#ef4444"
                      />
                    ) : (
                      <div className="text-center py-8 text-[#848E9C]">
                        <CheckCircle2 className="w-12 h-12 mx-auto mb-2 text-green-500 opacity-50" />
                        <p>No rejections in this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Average Improvement */}
                <Card className="bg-[#1E2329] border-white/8">
                  <CardHeader>
                    <CardTitle className="text-lg text-[#EAECEF]">Average Improvement</CardTitle>
                    <CardDescription>Profile metrics improvement after promotion</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="p-4 bg-green-500/10 rounded-lg">
                        <div className="flex items-center justify-between">
                          <span className="text-[#B7BDC6]">Survival Score</span>
                          <span className="text-green-500 font-bold">
                            +{promotionsData.avg_improvement.survival_score_delta} pts
                          </span>
                        </div>
                      </div>
                      <div className="p-4 bg-blue-500/10 rounded-lg">
                        <div className="flex items-center justify-between">
                          <span className="text-[#B7BDC6]">Drawdown Reduction</span>
                          <span className="text-blue-500 font-bold">
                            -{promotionsData.avg_improvement.drawdown_reduction_pct}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Recently Promoted */}
                {promotionsData.promoted_profiles.length > 0 && (
                  <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
                    <CardHeader>
                      <CardTitle className="text-lg text-[#EAECEF]">Recently Promoted Profiles</CardTitle>
                      <CardDescription>Profiles promoted to paper_live</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-48">
                        <div className="space-y-2">
                          {promotionsData.promoted_profiles.map((profile, idx) => (
                            <div key={idx} className="p-3 bg-[#2B3139] rounded-lg flex items-center justify-between">
                              <div>
                                <code className="text-[#F0B90B] text-sm">{profile.to_profile_id}</code>
                                <div className="text-xs text-[#848E9C]">
                                  Agent: {profile.agent_id}
                                </div>
                              </div>
                              <Badge className="bg-green-500/20 text-green-500">
                                {profile.target_env}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    </CardContent>
                  </Card>
                )}
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Analytics;
