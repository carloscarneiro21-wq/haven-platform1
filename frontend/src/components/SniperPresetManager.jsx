import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Zap,
  Shield,
  TrendingUp,
  TrendingDown,
  Check,
  Info,
  ChevronDown,
  ChevronUp,
  Settings,
  Loader2,
  AlertTriangle,
  Clock,
  DollarSign,
  Percent,
  Target,
  Lock
} from "lucide-react";

const PRESET_COLORS = {
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

const PRESET_ICONS = {
  conservative: <Shield className="w-5 h-5" />,
  moderate: <TrendingUp className="w-5 h-5" />,
  aggressive: <Zap className="w-5 h-5" />,
};

export default function SniperPresetManager({ onPresetApplied }) {
  const [presets, setPresets] = useState({});
  const [comparison, setComparison] = useState([]);
  const [currentPreset, setCurrentPreset] = useState(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState(null);

  // Fetch presets
  const fetchPresets = useCallback(async () => {
    try {
      setLoading(true);
      const [presetsRes, currentRes] = await Promise.all([
        api.get("/dex/sniper/presets"),
        api.get("/dex/sniper/current-preset"),
      ]);
      setPresets(presetsRes.data.presets || {});
      setComparison(presetsRes.data.comparison || []);
      setCurrentPreset(currentRes.data.current_preset);
    } catch (e) {
      console.error("Failed to fetch sniper presets:", e);
      toast.error("Failed to load sniper presets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  // Apply preset
  const handleApplyPreset = async (level) => {
    try {
      setApplying(level);
      const res = await api.post(`/dex/sniper/apply-preset/${level}`);
      if (res.data.success) {
        toast.success(`Preset "${res.data.preset_name}" aplicado com sucesso!`);
        setCurrentPreset(level);
        setShowConfirmDialog(false);
        if (onPresetApplied) {
          onPresetApplied(res.data);
        }
      }
    } catch (e) {
      console.error("Failed to apply preset:", e);
      toast.error(e.response?.data?.detail || "Failed to apply preset");
    } finally {
      setApplying(null);
    }
  };

  // Open confirmation dialog
  const openConfirmDialog = (level) => {
    setSelectedPreset(level);
    setShowConfirmDialog(true);
  };

  if (loading) {
    return (
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-zinc-500" />
          <span className="ml-2 text-zinc-500">Carregando presets...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Settings className="w-5 h-5 text-zinc-400" />
            Presets do Sniper
          </h3>
          <p className="text-sm text-zinc-500 mt-1">
            Configurações pré-definidas para diferentes níveis de risco
          </p>
        </div>
        {currentPreset && (
          <Badge className={`${PRESET_COLORS[currentPreset]?.badge} text-white`}>
            Ativo: {presets[currentPreset]?.name || currentPreset}
          </Badge>
        )}
      </div>

      {/* Preset Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {["conservative", "moderate", "aggressive"].map((level) => {
          const preset = presets[level];
          if (!preset) return null;

          const colors = PRESET_COLORS[level];
          const isActive = currentPreset === level;
          const isExpanded = expanded === level;

          return (
            <Card
              key={level}
              className={`${colors.bg} ${colors.border} border-2 transition-all ${
                isActive ? "ring-2 ring-offset-2 ring-offset-zinc-950 ring-opacity-50" : ""
              } ${isActive && level === "conservative" ? "ring-green-500" : ""} ${
                isActive && level === "moderate" ? "ring-yellow-500" : ""
              } ${isActive && level === "aggressive" ? "ring-red-500" : ""}`}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={colors.text}>{PRESET_ICONS[level]}</span>
                    <CardTitle className={`text-base ${colors.text}`}>
                      {preset.emoji} {preset.name}
                    </CardTitle>
                  </div>
                  {isActive && (
                    <Badge variant="outline" className="text-xs border-green-500 text-green-400">
                      <Check className="w-3 h-3 mr-1" />
                      Ativo
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-zinc-400 mt-1">{preset.description}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Quick Stats */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="flex items-center gap-1 text-zinc-400">
                    <DollarSign className="w-3 h-3" />
                    <span>Max: €{preset.entry?.max_position_eur}</span>
                  </div>
                  <div className="flex items-center gap-1 text-zinc-400">
                    <Percent className="w-3 h-3" />
                    <span>Slip: {preset.entry?.max_slippage_pct}%</span>
                  </div>
                  <div className="flex items-center gap-1 text-zinc-400">
                    <TrendingDown className="w-3 h-3" />
                    <span>SL: {preset.exit?.stop_loss?.loss_pct}%</span>
                  </div>
                  <div className="flex items-center gap-1 text-zinc-400">
                    <Clock className="w-3 h-3" />
                    <span>{(preset.exit?.time_stop?.max_hold_seconds || 0) / 60}min</span>
                  </div>
                </div>

                {/* Expand/Collapse Button */}
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-zinc-500 hover:text-zinc-300"
                  onClick={() => setExpanded(isExpanded ? null : level)}
                >
                  {isExpanded ? (
                    <>
                      <ChevronUp className="w-3 h-3 mr-1" />
                      Menos detalhes
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3 h-3 mr-1" />
                      Ver detalhes
                    </>
                  )}
                </Button>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="space-y-3 pt-2 border-t border-zinc-800">
                    {/* Entry Config */}
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 mb-2 flex items-center gap-1">
                        <Target className="w-3 h-3" /> Entrada
                      </h4>
                      <div className="grid grid-cols-2 gap-1 text-xs">
                        <span className="text-zinc-500">Max Posição:</span>
                        <span className="text-zinc-300">€{preset.entry?.max_position_eur}</span>
                        <span className="text-zinc-500">Max Wallet:</span>
                        <span className="text-zinc-300">{preset.entry?.max_wallet_pct}%</span>
                        <span className="text-zinc-500">Slippage:</span>
                        <span className="text-zinc-300">{preset.entry?.max_slippage_pct}%</span>
                        <span className="text-zinc-500">Min Liquidez:</span>
                        <span className="text-zinc-300">${(preset.entry?.min_expected_liquidity_usd || 0).toLocaleString()}</span>
                      </div>
                    </div>

                    {/* Exit Config */}
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 mb-2 flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" /> Saída
                      </h4>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Take Profit:</span>
                          <span className="text-green-400">
                            {preset.exit?.take_profit?.ladder?.map(l => `${l.profit_pct}%`).join(" / ")}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Stop Loss:</span>
                          <span className="text-red-400">-{preset.exit?.stop_loss?.loss_pct}%</span>
                        </div>
                        {preset.exit?.trailing_stop?.enabled && (
                          <div className="flex justify-between">
                            <span className="text-zinc-500">Trailing:</span>
                            <span className="text-yellow-400">{preset.exit?.trailing_stop?.trail_pct}%</span>
                          </div>
                        )}
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Time Stop:</span>
                          <span className="text-zinc-300">{(preset.exit?.time_stop?.max_hold_seconds || 0) / 60} min</span>
                        </div>
                      </div>
                    </div>

                    {/* Safety Filters */}
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 mb-2 flex items-center gap-1">
                        <Shield className="w-3 h-3" /> Filtros de Segurança
                      </h4>
                      <div className="grid grid-cols-2 gap-1 text-xs">
                        <span className="text-zinc-500">Max Buy Tax:</span>
                        <span className="text-zinc-300">{preset.safety_filters?.max_buy_tax_pct}%</span>
                        <span className="text-zinc-500">Max Sell Tax:</span>
                        <span className="text-zinc-300">{preset.safety_filters?.max_sell_tax_pct}%</span>
                        <span className="text-zinc-500">Min Holders:</span>
                        <span className="text-zinc-300">{preset.safety_filters?.min_unique_holders}</span>
                        <span className="text-zinc-500">Verificado:</span>
                        <span className={preset.safety_filters?.require_verified_contract ? "text-green-400" : "text-zinc-500"}>
                          {preset.safety_filters?.require_verified_contract ? "Sim" : "Não"}
                        </span>
                      </div>
                    </div>

                    {/* Execution */}
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 mb-2 flex items-center gap-1">
                        <Zap className="w-3 h-3" /> Execution
                      </h4>
                      <div className="grid grid-cols-2 gap-1 text-xs">
                        <span className="text-zinc-500">Anti-MEV:</span>
                        <span className={preset.execution?.anti_mev?.enabled ? "text-green-400" : "text-zinc-500"}>
                          {preset.execution?.anti_mev?.enabled ? "Ativo" : "Desativado"}
                        </span>
                        {preset.execution?.anti_mev?.enabled && (
                          <>
                            <span className="text-zinc-500">Split Orders:</span>
                            <span className="text-zinc-300">{preset.execution?.anti_mev?.split_orders?.parts} partes</span>
                          </>
                        )}
                        <span className="text-zinc-500">Max Retries:</span>
                        <span className="text-zinc-300">{preset.execution?.retry?.max_retries}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Apply Button */}
                <Button
                  onClick={() => openConfirmDialog(level)}
                  disabled={isActive || applying === level}
                  className={`w-full ${
                    isActive
                      ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                      : level === "conservative"
                      ? "bg-green-600 hover:bg-green-700"
                      : level === "moderate"
                      ? "bg-yellow-600 hover:bg-yellow-700"
                      : "bg-red-600 hover:bg-red-700"
                  }`}
                >
                  {applying === level ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Aplicando...
                    </>
                  ) : isActive ? (
                    <>
                      <Check className="w-4 h-4 mr-2" />
                      Ativo
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4 mr-2" />
                      Aplicar Preset
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Comparison Table */}
      {comparison.length > 0 && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
              Comparação de Presets
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="py-2 text-left">Preset</th>
                    <th className="py-2 text-right">Max Posição</th>
                    <th className="py-2 text-right">Slippage</th>
                    <th className="py-2 text-right">Min Liquidez</th>
                    <th className="py-2 text-right">Stop Loss</th>
                    <th className="py-2 text-right">Take Profit</th>
                    <th className="py-2 text-right">Time Stop</th>
                    <th className="py-2 text-center">Anti-MEV</th>
                    <th className="py-2 text-right">Max Tax</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.map((row) => (
                    <tr
                      key={row.level}
                      className={`border-b border-zinc-800/50 ${
                        currentPreset === row.level ? "bg-zinc-800/30" : ""
                      }`}
                    >
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <span>{row.emoji}</span>
                          <span className={PRESET_COLORS[row.level]?.text}>{row.name}</span>
                          {currentPreset === row.level && (
                            <Check className="w-3 h-3 text-green-400" />
                          )}
                        </div>
                      </td>
                      <td className="py-2 text-right text-zinc-300">€{row.max_position_eur}</td>
                      <td className="py-2 text-right text-zinc-300">{row.max_slippage_pct}%</td>
                      <td className="py-2 text-right text-zinc-300">${row.min_liquidity_usd?.toLocaleString()}</td>
                      <td className="py-2 text-right text-red-400">-{row.stop_loss_pct}%</td>
                      <td className="py-2 text-right text-green-400">{row.tp_ladder}</td>
                      <td className="py-2 text-right text-zinc-300">{row.time_stop_min}min</td>
                      <td className="py-2 text-center">
                        {row.anti_mev ? (
                          <Badge variant="outline" className="text-green-400 border-green-600">
                            {row.split_orders}x
                          </Badge>
                        ) : (
                          <span className="text-zinc-500">—</span>
                        )}
                      </td>
                      <td className="py-2 text-right text-zinc-300">{row.max_buy_tax}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              Confirmar Aplicação de Preset
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              {selectedPreset && presets[selectedPreset] && (
                <>
                  Você está prestes a aplicar o preset{" "}
                  <span className={PRESET_COLORS[selectedPreset]?.text}>
                    &ldquo;{presets[selectedPreset].name}&rdquo;
                  </span>{" "}
                  ao DEX Sniper.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {selectedPreset && presets[selectedPreset] && (
              <div className="bg-zinc-800/50 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <span className={PRESET_COLORS[selectedPreset]?.text}>
                    {PRESET_ICONS[selectedPreset]}
                  </span>
                  <span className="font-semibold text-white">
                    {presets[selectedPreset].emoji} {presets[selectedPreset].name}
                  </span>
                </div>
                <p className="text-sm text-zinc-400">
                  {presets[selectedPreset].description}
                </p>
                <div className="grid grid-cols-2 gap-2 text-xs mt-2">
                  <div className="text-zinc-500">Max Posição:</div>
                  <div className="text-zinc-300">€{presets[selectedPreset].entry?.max_position_eur}</div>
                  <div className="text-zinc-500">Stop Loss:</div>
                  <div className="text-red-400">-{presets[selectedPreset].exit?.stop_loss?.loss_pct}%</div>
                  <div className="text-zinc-500">Take Profit:</div>
                  <div className="text-green-400">
                    {presets[selectedPreset].exit?.take_profit?.ladder?.map(l => `${l.profit_pct}%`).join(" / ")}
                  </div>
                </div>
              </div>
            )}
            <p className="text-sm text-zinc-500">
              <Info className="w-4 h-4 inline mr-1" />
              Esta ação irá alterar as configurações do sniper. O agente usará estas configurações para futuras operações.
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setShowConfirmDialog(false)}
              className="border-zinc-700"
            >
              Cancelar
            </Button>
            <Button
              onClick={() => handleApplyPreset(selectedPreset)}
              disabled={applying === selectedPreset}
              className={
                selectedPreset === "conservative"
                  ? "bg-green-600 hover:bg-green-700"
                  : selectedPreset === "moderate"
                  ? "bg-yellow-600 hover:bg-yellow-700"
                  : "bg-red-600 hover:bg-red-700"
              }
            >
              {applying === selectedPreset ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Aplicando...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Confirmar
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
