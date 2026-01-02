import { useState, useCallback } from "react";
import { api } from "@/App";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Search,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
  TrendingUp,
  TrendingDown,
  Zap,
  Info,
  Eye,
  DollarSign,
  Percent,
  Users,
  FileCheck,
  Target,
  Clock,
} from "lucide-react";

// Risk level colors
const RISK_COLORS = {
  conservative: {
    bg: "bg-green-500/10",
    border: "border-green-500/30",
    text: "text-green-400",
    badge: "bg-green-600",
  },
  moderate: {
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/30",
    text: "text-yellow-400",
    badge: "bg-yellow-600",
  },
  aggressive: {
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-400",
    badge: "bg-red-600",
  },
};

// Confidence colors
const CONFIDENCE_COLORS = {
  HIGH: "text-green-400",
  MEDIUM: "text-yellow-400",
  LOW: "text-orange-400",
  UNKNOWN: "text-red-400",
};

// Severity icons
const SEVERITY_ICONS = {
  info: <Info className="w-4 h-4 text-blue-400" />,
  warn: <AlertTriangle className="w-4 h-4 text-yellow-400" />,
  error: <XCircle className="w-4 h-4 text-red-400" />,
  critical: <AlertTriangle className="w-4 h-4 text-red-600" />,
};

export default function SniperAdvisor({ onApplyRecommendation }) {
  const [tokenAddress, setTokenAddress] = useState("");
  const [chain, setChain] = useState("bsc");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [applying, setApplying] = useState(false);
  const [appliedConfig, setAppliedConfig] = useState(null);
  const [reverting, setReverting] = useState(false);

  // Analyze token
  const handleAnalyze = useCallback(async () => {
    if (!tokenAddress || !tokenAddress.startsWith("0x") || tokenAddress.length !== 42) {
      toast.error("Endereço de token inválido");
      return;
    }

    try {
      setLoading(true);
      setAnalysis(null);

      const res = await api.post("/dex/sniper/advisor/analyze", {
        token_address: tokenAddress,
        chain,
      });

      setAnalysis(res.data);

      if (res.data.risk_assessment?.risk_score < 30) {
        toast.error("Token de ALTO RISCO identificado!");
      } else if (res.data.risk_assessment?.risk_score < 50) {
        toast.warning("Token arriscado. Cautela recomendada.");
      } else {
        toast.success("Análise completa!");
      }
    } catch (e) {
      console.error("Analysis failed:", e);
      toast.error(e.response?.data?.detail || "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, [tokenAddress, chain]);

  // Get preview
  const handlePreview = useCallback(async () => {
    if (!analysis) return;

    try {
      setLoadingPreview(true);
      const res = await api.post("/dex/sniper/advisor/preview", {
        analysis_result: analysis,
      });
      setPreview(res.data);
      setShowPreviewModal(true);
    } catch (e) {
      console.error("Preview failed:", e);
      toast.error("Failed to generate preview");
    } finally {
      setLoadingPreview(false);
    }
  }, [analysis]);

  // Apply recommendation
  const handleApply = useCallback(async () => {
    if (!analysis) return;

    try {
      setApplying(true);

      const res = await api.post("/dex/sniper/advisor/apply", {
        token: {
          address: tokenAddress,
          chain,
        },
        preset_id: analysis.recommended_preset?.preset_id,
        overrides: analysis.recommended_preset?.suggested_overrides || {},
        token_metrics: analysis.metrics,
        mode: "paper",
        dry_run: false,
      });

      if (res.data.status === "applied") {
        toast.success("Configuration applied successfully!");
        setShowPreviewModal(false);
        setAppliedConfig(res.data);
        
        if (onApplyRecommendation) {
          onApplyRecommendation(res.data);
        }
      }
    } catch (e) {
      console.error("Apply failed:", e);
      const detail = e.response?.data?.detail;
      if (typeof detail === 'object') {
        toast.error(`${detail.code}: ${detail.message}`);
      } else {
        toast.error(detail || "Failed to apply configuration");
      }
    } finally {
      setApplying(false);
    }
  }, [analysis, tokenAddress, chain, onApplyRecommendation]);

  // Revert/Clear config
  const handleRevert = useCallback(async () => {
    if (!tokenAddress) return;

    try {
      setReverting(true);

      await api.delete(`/dex/sniper/advisor/configs/${chain}/${tokenAddress}`);
      
      toast.success("Configuration reverted to default!");
      setAppliedConfig(null);
      
      if (onApplyRecommendation) {
        onApplyRecommendation(null);
      }
    } catch (e) {
      console.error("Revert failed:", e);
      toast.error("Failed to revert configuration");
    } finally {
      setReverting(false);
    }
  }, [tokenAddress, chain, onApplyRecommendation]);

  // Risk score visual
  const getRiskScoreColor = (score) => {
    if (score >= 70) return "text-green-400";
    if (score >= 50) return "text-yellow-400";
    if (score >= 30) return "text-orange-400";
    return "text-red-400";
  };

  const getRiskScoreBg = (score) => {
    if (score >= 70) return "bg-green-500";
    if (score >= 50) return "bg-yellow-500";
    if (score >= 30) return "bg-orange-500";
    return "bg-red-500";
  };

  return (
    <div className="space-y-4">
      {/* Search Section */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <Search className="w-4 h-4" />
            Sniper Advisor
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Endereço do token (0x...)"
              value={tokenAddress}
              onChange={(e) => setTokenAddress(e.target.value)}
              className="bg-zinc-800 border-zinc-700 font-mono text-sm"
            />
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-md px-3 text-sm"
            >
              <option value="bsc">BSC</option>
              <option value="ethereum">ETH</option>
            </select>
            <Button
              onClick={handleAnalyze}
              disabled={loading || !tokenAddress}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Analisando...
                </>
              ) : (
                <>
                  <Search className="w-4 h-4 mr-2" />
                  Analisar
                </>
              )}
            </Button>
          </div>
          <p className="text-xs text-zinc-500 mt-2">
            Analisa o token e recomenda o preset ideal com ajustes específicos.
          </p>
        </CardContent>
      </Card>

      {/* Analysis Results */}
      {analysis && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Risk Score Card */}
          <Card className={`${RISK_COLORS[analysis.risk_assessment?.risk_level]?.bg || "bg-zinc-900/50"} ${RISK_COLORS[analysis.risk_assessment?.risk_level]?.border || "border-zinc-800"} border-2`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
                Avaliação de Risco
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className={`text-4xl font-bold ${getRiskScoreColor(analysis.risk_assessment?.risk_score)}`}>
                    {analysis.risk_assessment?.risk_score}
                  </div>
                  <div className="text-xs text-zinc-500">Risk Score</div>
                </div>
                <div className="text-right">
                  <Badge className={`${RISK_COLORS[analysis.risk_assessment?.risk_level]?.badge} text-white mb-1`}>
                    {analysis.risk_assessment?.risk_level?.toUpperCase()}
                  </Badge>
                  <div className={`text-xs ${CONFIDENCE_COLORS[analysis.risk_assessment?.confidence]}`}>
                    Confiança: {analysis.risk_assessment?.confidence}
                  </div>
                </div>
              </div>

              {/* Score Bar */}
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full ${getRiskScoreBg(analysis.risk_assessment?.risk_score)} transition-all`}
                  style={{ width: `${analysis.risk_assessment?.risk_score}%` }}
                />
              </div>

              {/* Token Info */}
              {analysis.token && (
                <div className="mt-4 p-2 bg-zinc-800/50 rounded text-xs">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Token:</span>
                    <span className="text-zinc-300 font-mono">{analysis.token.symbol || "UNKNOWN"}</span>
                  </div>
                  {analysis.token.pair && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Par:</span>
                      <span className="text-zinc-300">{analysis.token.pair}</span>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Metrics Card */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
                Métricas
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <DollarSign className="w-3 h-3" /> Liquidez
                  </span>
                  <span className="text-zinc-300">
                    ${(analysis.metrics?.lp_liquidity_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" /> Buy Tax
                  </span>
                  <span className={analysis.metrics?.buy_tax_pct > 5 ? "text-red-400" : "text-zinc-300"}>
                    {analysis.metrics?.buy_tax_pct ?? "N/A"}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <TrendingDown className="w-3 h-3" /> Sell Tax
                  </span>
                  <span className={analysis.metrics?.sell_tax_pct > 5 ? "text-red-400" : "text-zinc-300"}>
                    {analysis.metrics?.sell_tax_pct ?? "N/A"}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <Users className="w-3 h-3" /> Top 10 Holders
                  </span>
                  <span className={analysis.metrics?.top10_holders_pct > 50 ? "text-yellow-400" : "text-zinc-300"}>
                    {analysis.metrics?.top10_holders_pct ?? "N/A"}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <FileCheck className="w-3 h-3" /> Verificado
                  </span>
                  <span>
                    {analysis.metrics?.contract_verified ? (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    ) : analysis.metrics?.contract_verified === false ? (
                      <XCircle className="w-4 h-4 text-red-400" />
                    ) : (
                      <span className="text-zinc-500">N/A</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 flex items-center gap-1">
                    <Shield className="w-3 h-3" /> Honeypot
                  </span>
                  <span>
                    {analysis.metrics?.is_honeypot === false ? (
                      <Badge variant="outline" className="text-green-400 border-green-600 text-xs">SAFE</Badge>
                    ) : analysis.metrics?.is_honeypot === true ? (
                      <Badge variant="outline" className="text-red-400 border-red-600 text-xs">DANGER</Badge>
                    ) : (
                      <span className="text-zinc-500">N/A</span>
                    )}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Recommendation Card */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
                Recomendação
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="p-3 bg-zinc-800/50 rounded">
                  <div className="text-xs text-zinc-500 mb-1">Preset Recomendado</div>
                  <div className="text-sm font-semibold text-white">
                    {analysis.recommended_preset?.preset_id?.replace("sniper_preset_", "").replace("_v1", "").toUpperCase()}
                  </div>
                </div>

                {/* Suggested Overrides */}
                {analysis.recommended_preset?.suggested_overrides && Object.keys(analysis.recommended_preset.suggested_overrides).length > 0 && (
                  <div className="p-3 bg-zinc-800/50 rounded">
                    <div className="text-xs text-zinc-500 mb-2">Ajustes Sugeridos</div>
                    <div className="space-y-1 text-xs">
                      {Object.entries(analysis.recommended_preset.suggested_overrides).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="text-zinc-400">{key.split(".").pop()}:</span>
                          <span className="text-yellow-400">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Preview Button */}
                <Button
                  onClick={handlePreview}
                  disabled={loadingPreview}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                >
                  {loadingPreview ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Eye className="w-4 h-4 mr-2" />
                  )}
                  Ver Preview
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Reason Codes & Warnings */}
      {analysis && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Reason Codes */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
                Análise Detalhada
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {analysis.reason_codes?.map((rc, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-xs">
                    {SEVERITY_ICONS[rc.severity] || SEVERITY_ICONS.info}
                    <span className="text-zinc-300">{rc.message}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Warnings */}
          {analysis.warnings?.length > 0 && (
            <Card className="bg-red-900/10 border-red-800/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-rajdhani text-red-400 uppercase tracking-wider flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  Avisos
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {analysis.warnings.map((w, idx) => (
                    <div key={idx} className="text-sm text-red-300">
                      {w}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Audit Info */}
      {analysis?.audit && (
        <div className="text-xs text-zinc-600 flex items-center gap-4">
          <span>Advisor: {analysis.audit.advisor_version}</span>
          <span>Sources: {analysis.audit.sources_used?.join(", ")}</span>
          <span>Hash: {analysis.audit.inputs_hash}</span>
        </div>
      )}

      {/* Applied Config Status */}
      {appliedConfig && (
        <Card className="bg-green-900/20 border-green-800/50">
          <CardContent className="py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-400" />
                <span className="text-sm text-green-400">
                  Configuração aplicada para {appliedConfig.scope?.key}
                </span>
              </div>
              <Button
                onClick={handleRevert}
                disabled={reverting}
                variant="outline"
                size="sm"
                className="border-red-800 text-red-400 hover:bg-red-900/50"
              >
                {reverting ? (
                  <>
                    <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                    Revertendo...
                  </>
                ) : (
                  <>
                    <XCircle className="w-3 h-3 mr-1" />
                    Reverter
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Preview Modal */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="bg-zinc-900 border-zinc-800 max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="w-5 h-5 text-blue-400" />
              Preview da Aplicação
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Verifique as configurações antes de aplicar. Nenhuma trade será executada.
            </DialogDescription>
          </DialogHeader>

          {preview && (
            <div className="space-y-4">
              {/* Config Summary Line */}
              {preview.overrides_applied?.length > 0 && (
                <div className="p-3 bg-blue-900/20 border border-blue-800/50 rounded-lg text-center">
                  <span className="text-sm text-blue-400">
                    <strong>{preview.preset_used?.name}</strong> + {preview.overrides_applied.length} override(s) = <strong>Config Final</strong>
                  </span>
                </div>
              )}

              {/* Preset Info */}
              <div className="p-4 bg-zinc-800/50 rounded-lg">
                <h4 className="text-sm font-semibold text-white mb-2">Preset Base</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <span className="text-zinc-500">ID:</span>
                  <span className="text-zinc-300">{preview.preset_used?.id}</span>
                  <span className="text-zinc-500">Nome:</span>
                  <span className="text-zinc-300">{preview.preset_used?.name}</span>
                  <span className="text-zinc-500">Nível:</span>
                  <span className="text-zinc-300">{preview.preset_used?.risk_level}</span>
                </div>
              </div>

              {/* Overrides Applied */}
              {preview.overrides_applied?.length > 0 && (
                <div className="p-4 bg-yellow-900/20 border border-yellow-800/50 rounded-lg">
                  <h4 className="text-sm font-semibold text-yellow-400 mb-2">Overrides Aplicados</h4>
                  <div className="space-y-1 text-xs">
                    {preview.overrides_applied.map((o, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="text-zinc-400">{o.path}:</span>
                        <span className="text-zinc-500 line-through">{o.old_value}</span>
                        <span className="text-yellow-400">→ {o.new_value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Hard Caps */}
              <div className="p-4 bg-zinc-800/50 rounded-lg">
                <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-400" />
                  Hard Caps Ativos
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(preview.hard_caps || {}).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-zinc-500">{key.replace(/_/g, " ")}:</span>
                      <span className="text-zinc-300">{typeof value === "number" ? value : String(value)}</span>
                    </div>
                  ))}
                </div>
                {preview.hard_cap_notes?.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {preview.hard_cap_notes.map((note, idx) => (
                      <div key={idx} className="text-xs text-yellow-400">
                        ⚠️ {note}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Safety Gates */}
              <div className="p-4 bg-green-900/20 border border-green-800/50 rounded-lg">
                <h4 className="text-sm font-semibold text-green-400 mb-2">Safety Gates (Sempre Ativos)</h4>
                <div className="space-y-1 text-xs">
                  {Object.entries(preview.safety_gates || {}).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-2">
                      <CheckCircle className="w-3 h-3 text-green-400" />
                      <span className="text-zinc-300">{key.replace(/_/g, " ")}: {String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Warnings */}
              {preview.warnings?.length > 0 && (
                <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
                  <h4 className="text-sm font-semibold text-red-400 mb-2">Avisos</h4>
                  {preview.warnings.map((w, idx) => (
                    <div key={idx} className="text-sm text-red-300">
                      {w}
                    </div>
                  ))}
                </div>
              )}

              {/* Apply Button */}
              <div className="flex gap-2 pt-4 border-t border-zinc-800">
                <Button
                  variant="outline"
                  onClick={() => setShowPreviewModal(false)}
                  className="flex-1 border-zinc-700"
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleApply}
                  disabled={applying || analysis?.risk_assessment?.risk_score < 30}
                  className="flex-1 bg-green-600 hover:bg-green-700"
                >
                  {applying ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Aplicando...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Aplicar Configuração
                    </>
                  )}
                </Button>
              </div>

              {/* Info */}
              {analysis?.risk_assessment?.risk_score < 30 && (
                <div className="text-xs text-red-400 text-center mt-2">
                  ⚠️ Não é possível aplicar configuração para tokens de alto risco (score &lt; 30)
                </div>
              )}
              <div className="text-xs text-zinc-500 text-center mt-2">
                A configuração será aplicada apenas para este token em modo PAPER.
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
