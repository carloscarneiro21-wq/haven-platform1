import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { toast } from "sonner";
import {
  RefreshCw,
  TrendingUp,
  Grid3X3,
  DollarSign,
  ChevronDown,
  ChevronUp,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Zap,
  BarChart3,
  Shield,
  Coins,
  Play,
  Save,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

// Agent icons
const AgentIcons = {
  DCA: DollarSign,
  GRID: Grid3X3,
  TREND: TrendingUp,
  MEAN_REVERSION: Zap,
  BREAKOUT: TrendingUp,
};

// Confidence badge styles
const confidenceStyles = {
  HIGH: "bg-green-600/20 text-green-400 border-green-600/30",
  MEDIUM: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  LOW: "bg-red-600/20 text-red-400 border-red-600/30",
};

// Confidence icons
const ConfidenceIcon = ({ level }) => {
  switch (level) {
    case "HIGH":
      return <CheckCircle2 className="w-4 h-4 text-green-400" />;
    case "MEDIUM":
      return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
    case "LOW":
      return <XCircle className="w-4 h-4 text-red-400" />;
    default:
      return null;
  }
};

// Score color
const getScoreColor = (score) => {
  if (score >= 80) return "text-green-400";
  if (score >= 60) return "text-yellow-400";
  return "text-red-400";
};

// Volume label translation
const volumeLabels = {
  very_high: "Muito Alto",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
};

// Reason code badges
const ReasonBadge = ({ code, explanation }) => {
  const isNegative = ["HIGH_SPREAD", "LOW_LIQUIDITY", "SPREAD_GATE_FAILED", 
                     "SLIPPAGE_GATE_FAILED", "HIGH_COST", "INSUFFICIENT_VOLUME",
                     "ERRATIC_BEHAVIOR"].includes(code);
  
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge 
            variant="outline" 
            className={`text-xs ${isNegative ? 'bg-red-600/10 text-red-400 border-red-600/30' : 'bg-blue-600/10 text-blue-400 border-blue-600/30'}`}
          >
            {code.replace(/_/g, " ")}
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="bg-zinc-800 border-zinc-700 text-white max-w-xs">
          <p>{explanation}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

// Single recommendation card
const RecommendationCard = ({ rec, rank, onApply }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <Card className="bg-zinc-900/50 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-lg font-bold text-zinc-400">
              {rank}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-white text-lg">{rec.pair}</span>
                <Badge variant="outline" className="text-xs bg-purple-600/20 text-purple-400 border-purple-600/30">
                  {rec.venue}
                </Badge>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <ConfidenceIcon level={rec.confidence} />
                <span className={`text-xs ${confidenceStyles[rec.confidence].split(" ")[1]}`}>
                  {rec.confidence === "HIGH" ? "High Confidence" : rec.confidence === "MEDIUM" ? "Medium Confidence" : "Low Confidence"}
                </span>
              </div>
            </div>
          </div>
          
          {/* Score + Apply Button */}
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className={`text-3xl font-bold font-mono ${getScoreColor(rec.score)}`}>
                {rec.score}
              </div>
              <div className="text-xs text-zinc-500">score</div>
            </div>
            <Button
              size="sm"
              onClick={() => onApply(rec)}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              <Play className="w-3 h-3 mr-1" />
              Aplicar
            </Button>
          </div>
        </div>
        
        {/* Key Metrics */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="bg-zinc-800/50 rounded p-2 text-center">
            <div className="text-xs text-zinc-500">Spread</div>
            <div className="font-mono text-sm text-white">{rec.metrics.spread_pct.toFixed(3)}%</div>
          </div>
          <div className="bg-zinc-800/50 rounded p-2 text-center">
            <div className="text-xs text-zinc-500">Slippage €10</div>
            <div className="font-mono text-sm text-white">{rec.metrics.slippage_10eur.toFixed(3)}%</div>
          </div>
          <div className="bg-zinc-800/50 rounded p-2 text-center">
            <div className="text-xs text-zinc-500">ATR 7d</div>
            <div className="font-mono text-sm text-white">{rec.metrics.atr_7d_pct.toFixed(1)}%</div>
          </div>
          <div className="bg-zinc-800/50 rounded p-2 text-center">
            <div className="text-xs text-zinc-500">Custo/Trade</div>
            <div className="font-mono text-sm text-white">{rec.metrics.estimated_cost_per_trade.toFixed(3)}%</div>
          </div>
        </div>
        
        {/* Reason Codes */}
        <div className="flex flex-wrap gap-1 mb-3">
          {rec.reasons_explained.slice(0, expanded ? undefined : 3).map((reason, idx) => (
            <ReasonBadge key={idx} code={reason.code} explanation={reason.explanation} />
          ))}
          {!expanded && rec.reasons_explained.length > 3 && (
            <Badge variant="outline" className="text-xs bg-zinc-800 text-zinc-400 border-zinc-700">
              +{rec.reasons_explained.length - 3}
            </Badge>
          )}
        </div>
        
        {/* Expandable Details */}
        <Collapsible open={expanded} onOpenChange={setExpanded}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full text-zinc-400 hover:text-white">
              {expanded ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}
              {expanded ? "Menos detalhes" : "Mais detalhes"}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3 space-y-3">
            {/* Volume & Trend */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-zinc-800/30 rounded p-3">
                <div className="flex items-center gap-2 text-xs text-zinc-500 mb-1">
                  <BarChart3 className="w-3 h-3" /> Volume 24h
                </div>
                <div className="font-mono text-sm text-white">
                  {volumeLabels[rec.metrics.volume_24h_label] || rec.metrics.volume_24h_label}
                </div>
                <div className="text-xs text-zinc-500">
                  ${(rec.metrics.volume_24h_usd / 1_000_000).toFixed(0)}M
                </div>
              </div>
              <div className="bg-zinc-800/30 rounded p-3">
                <div className="flex items-center gap-2 text-xs text-zinc-500 mb-1">
                  <Zap className="w-3 h-3" /> Trend Strength
                </div>
                <div className="font-mono text-sm text-white">
                  {rec.metrics.trend_strength.toFixed(0)} ADX
                </div>
                <Progress value={rec.metrics.trend_strength} className="h-1 mt-1" />
              </div>
            </div>
            
            {/* Fees */}
            <div className="bg-zinc-800/30 rounded p-3">
              <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
                <Coins className="w-3 h-3" /> Taxas {rec.venue}
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-zinc-400">Maker:</span>
                  <span className="font-mono text-white ml-2">{rec.metrics.fees.maker}</span>
                </div>
                <div>
                  <span className="text-zinc-400">Taker:</span>
                  <span className="font-mono text-white ml-2">{rec.metrics.fees.taker}</span>
                </div>
              </div>
            </div>
            
            {/* Venue Selection Reason */}
            <div className="bg-blue-600/10 border border-blue-600/30 rounded p-3">
              <div className="flex items-center gap-2 text-xs text-blue-400 mb-1">
                <Shield className="w-3 h-3" /> Seleção de Venue
              </div>
              <p className="text-sm text-zinc-300">{rec.venue_selection_reason}</p>
            </div>
            
            {/* All Reasons */}
            <div className="space-y-1">
              <div className="text-xs text-zinc-500 mb-2">Todas as razões:</div>
              {rec.reasons_explained.map((reason, idx) => (
                <div key={idx} className="text-xs text-zinc-400 flex items-start gap-2">
                  <span className="text-blue-400">•</span>
                  <span><strong>{reason.code}:</strong> {reason.explanation}</span>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
};

// Main component
export function PairRecommender() {
  const [recommendations, setRecommendations] = useState({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState("grid");
  const [lastUpdated, setLastUpdated] = useState(null);
  
  // Apply dialog state
  const [showApplyDialog, setShowApplyDialog] = useState(false);
  const [selectedRec, setSelectedRec] = useState(null);
  const [presetLevel, setPresetLevel] = useState("moderate");
  const [saveCustomPreset, setSaveCustomPreset] = useState(false);
  const [customPresetName, setCustomPresetName] = useState("");
  const [applying, setApplying] = useState(false);
  
  const fetchRecommendations = useCallback(async (forceRefresh = false) => {
    try {
      if (forceRefresh) setRefreshing(true);
      
      const response = await api.get("/pair-advisor/recommendations", {
        params: { top_n: 5, force_refresh: forceRefresh }
      });
      
      setRecommendations(response.data.recommendations || {});
      setLastUpdated(new Date(response.data.generated_at));
      
      if (forceRefresh) {
        toast.success("Recomendações atualizadas!");
      }
    } catch (error) {
      console.error("Failed to fetch recommendations:", error);
      toast.error("Error loading recommendations");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  
  useEffect(() => {
    fetchRecommendations();
    
    // Refresh every 5 minutes
    const interval = setInterval(() => fetchRecommendations(), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchRecommendations]);
  
  // Handle apply button click
  const handleApplyClick = useCallback((rec) => {
    setSelectedRec(rec);
    setPresetLevel("moderate");
    setSaveCustomPreset(false);
    setCustomPresetName(`${rec.agent}-${rec.pair.replace("/", "-")}`);
    setShowApplyDialog(true);
  }, []);
  
  // Apply recommendation to agent
  const handleApplyRecommendation = useCallback(async () => {
    if (!selectedRec) return;
    
    setApplying(true);
    try {
      const response = await api.post("/pair-advisor/apply", {
        pair: selectedRec.pair,
        venue: selectedRec.venue,
        preset_level: presetLevel,
        save_custom_preset: saveCustomPreset,
        custom_preset_name: saveCustomPreset ? customPresetName : null,
      }, {
        params: { agent_type: selectedRec.agent.toLowerCase() }
      });
      
      toast.success(response.data.message || `Recomendação aplicada ao agente ${selectedRec.agent}!`);
      setShowApplyDialog(false);
      setSelectedRec(null);
    } catch (error) {
      console.error("Failed to apply recommendation:", error);
      toast.error(error.response?.data?.detail || "Error applying recommendation");
    } finally {
      setApplying(false);
    }
  }, [selectedRec, presetLevel, saveCustomPreset, customPresetName]);
  
  const agentTabs = [
    { id: "grid", label: "GRID", icon: Grid3X3, description: "Range Trading" },
    { id: "dca", label: "DCA", icon: DollarSign, description: "Dollar Cost Avg" },
    { id: "trend", label: "TREND", icon: TrendingUp, description: "Trend Following" },
    { id: "mean_reversion", label: "MEAN REV", icon: Zap, description: "Mean Reversion" },
    { id: "breakout", label: "BREAKOUT", icon: TrendingUp, description: "Breakout/Momentum" },
  ];
  
  const presetOptions = [
    { value: "conservative", label: "🟢 Conservador", desc: "Baixo risco, menos trades" },
    { value: "moderate", label: "🟡 Moderado", desc: "Equilíbrio risco/retorno" },
    { value: "aggressive", label: "🔴 Agressivo", desc: "Alto risco, mais trades" },
  ];
  
  return (
    <>
    <Card className="bg-zinc-900/30 border-zinc-800">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <CardTitle className="text-lg font-rajdhani uppercase tracking-wider text-white">
                Pair Advisor
              </CardTitle>
              <p className="text-xs text-zinc-500 mt-0.5">
                Top 5 pares recomendados por estratégia
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            {lastUpdated && (
              <span className="text-xs text-zinc-500">
                Atualizado: {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => fetchRecommendations(true)}
              disabled={refreshing}
              className="bg-zinc-800 border-zinc-700 hover:bg-zinc-700"
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
        
        {/* Info Banner */}
        <div className="mt-3 p-3 bg-blue-600/10 border border-blue-600/30 rounded-lg flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
          <p className="text-xs text-zinc-300">
            <strong>Modo PAPER:</strong> Analise as recomendações antes de aplicar. 
            O sistema escolhe automaticamente o melhor venue (Kraken vs Binance) e 
            filtra pares inadequados para micro-capital (€5-€50).
          </p>
        </div>
      </CardHeader>
      
      <CardContent>
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="w-full bg-zinc-800/50 mb-4">
            {agentTabs.map((tab) => {
              const Icon = tab.icon;
              const count = recommendations[tab.id]?.length || 0;
              
              return (
                <TabsTrigger
                  key={tab.id}
                  value={tab.id}
                  className="flex-1 data-[state=active]:bg-zinc-700"
                >
                  <Icon className="w-4 h-4 mr-2" />
                  {tab.label}
                  {count > 0 && (
                    <Badge variant="secondary" className="ml-2 bg-zinc-600 text-xs">
                      {count}
                    </Badge>
                  )}
                </TabsTrigger>
              );
            })}
          </TabsList>
          
          {agentTabs.map((tab) => (
            <TabsContent key={tab.id} value={tab.id} className="space-y-3">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-8 h-8 animate-spin text-zinc-500" />
                </div>
              ) : recommendations[tab.id]?.length > 0 ? (
                recommendations[tab.id].map((rec, idx) => (
                  <RecommendationCard key={rec.pair} rec={rec} rank={idx + 1} onApply={handleApplyClick} />
                ))
              ) : (
                <div className="text-center py-12 text-zinc-500">
                  <Zap className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Nenhuma recomendação disponível</p>
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
        
        {/* Gates Info */}
        <div className="mt-4 pt-4 border-t border-zinc-800">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Shield className="w-3 h-3" />
            <span>Gates Micro-Capital: Spread ≤ 0.10% | Slippage ≤ 0.05% (€5-€10)</span>
          </div>
        </div>
      </CardContent>
    </Card>
    
    {/* Apply Recommendation Dialog */}
    <Dialog open={showApplyDialog} onOpenChange={setShowApplyDialog}>
      <DialogContent className="bg-zinc-900 border-zinc-800 max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Play className="w-5 h-5 text-green-400" />
            Aplicar Recomendação
          </DialogTitle>
          <DialogDescription className="text-zinc-400">
            Configurar o agente {selectedRec?.agent} com o par recomendado.
          </DialogDescription>
        </DialogHeader>
        
        {selectedRec && (
          <div className="space-y-4 py-4">
            {/* Recommendation Summary */}
            <div className="bg-zinc-800/50 rounded-lg p-4 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm">Par:</span>
                <span className="font-mono font-bold text-white">{selectedRec.pair}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm">Venue:</span>
                <Badge className="bg-purple-600/20 text-purple-400">{selectedRec.venue}</Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm">Score:</span>
                <span className={`font-mono font-bold ${getScoreColor(selectedRec.score)}`}>{selectedRec.score}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm">Custo/Trade:</span>
                <span className="font-mono text-white">{selectedRec.metrics.estimated_cost_per_trade.toFixed(3)}%</span>
              </div>
            </div>
            
            {/* Preset Selection */}
            <div className="space-y-2">
              <Label className="text-zinc-300">Nível de Preset</Label>
              <Select value={presetLevel} onValueChange={setPresetLevel}>
                <SelectTrigger className="bg-zinc-800 border-zinc-700 text-white">
                  <SelectValue placeholder="Selecione o preset" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-800 border-zinc-700">
                  {presetOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-white hover:bg-zinc-700">
                      <div className="flex flex-col">
                        <span>{opt.label}</span>
                        <span className="text-xs text-zinc-400">{opt.desc}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {/* Save Custom Preset Option */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-zinc-300">Guardar como preset personalizado</Label>
                <Switch 
                  checked={saveCustomPreset} 
                  onCheckedChange={setSaveCustomPreset}
                />
              </div>
              
              {saveCustomPreset && (
                <div className="space-y-2">
                  <Label className="text-zinc-400 text-xs">Nome do Preset</Label>
                  <Input
                    value={customPresetName}
                    onChange={(e) => setCustomPresetName(e.target.value)}
                    placeholder="Ex: GRID-ETH-USDT"
                    className="bg-zinc-800 border-zinc-700 text-white"
                  />
                </div>
              )}
            </div>
            
            {/* Warning */}
            <div className="bg-yellow-600/10 border border-yellow-600/30 rounded-lg p-3 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 shrink-0" />
              <p className="text-xs text-zinc-300">
                Isto irá atualizar o símbolo e configurações do agente <strong>{selectedRec.agent}</strong>.
                O agente começará a usar o par <strong>{selectedRec.pair}</strong> quando for iniciado.
              </p>
            </div>
          </div>
        )}
        
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => setShowApplyDialog(false)}
            className="bg-zinc-800 border-zinc-700 text-zinc-300"
          >
            Cancelar
          </Button>
          <Button
            onClick={handleApplyRecommendation}
            disabled={applying}
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            {applying ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                A aplicar...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Aplicar ao Agente
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

export default PairRecommender;
