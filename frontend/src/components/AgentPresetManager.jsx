import * as React from "react";
import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { 
  Save, 
  RotateCcw, 
  Download, 
  Upload, 
  ArrowUp, 
  ArrowDown,
  Check,
  X
} from "lucide-react";
import { api } from "@/App";

const presetStyles = {
  conservative: "bg-green-600/20 hover:bg-green-600/30 text-green-400 border-green-600/30",
  moderate: "bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400 border-yellow-600/30",
  aggressive: "bg-red-600/20 hover:bg-red-600/30 text-red-400 border-red-600/30",
  custom: "bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 border-purple-600/30",
};

const presetLabels = {
  conservative: "🟢 Conservador",
  moderate: "🟡 Moderado",
  aggressive: "🔴 Arriscado",
};

// Diff indicator component
const DiffIndicator = ({ from, to }) => {
  if (from === to) return null;
  
  const isIncrease = parseFloat(to) > parseFloat(from);
  const Icon = isIncrease ? ArrowUp : ArrowDown;
  const color = isIncrease ? "text-green-400" : "text-red-400";
  
  return (
    <span className={`inline-flex items-center gap-1 ${color} text-xs`}>
      <Icon className="w-3 h-3" />
      {typeof from === 'number' ? from.toFixed(2) : from} → {typeof to === 'number' ? to.toFixed(2) : to}
    </span>
  );
};

// Diff preview component
const DiffPreview = ({ diff, presetName }) => {
  const hasChanges = diff && (
    Object.keys(diff.changed || {}).length > 0 ||
    Object.keys(diff.added || {}).length > 0
  );
  
  if (!hasChanges) {
    return (
      <div className="text-zinc-400 text-sm py-4 text-center">
        Nenhuma alteração detectada
      </div>
    );
  }
  
  return (
    <div className="space-y-3 max-h-[300px] overflow-y-auto">
      {Object.entries(diff.changed || {}).map(([key, change]) => (
        <div key={key} className="flex justify-between items-center py-2 px-3 bg-zinc-800/50 rounded-lg">
          <span className="text-zinc-300 text-sm font-medium">{formatParamName(key)}</span>
          <DiffIndicator from={change.from} to={change.to} />
        </div>
      ))}
      {Object.entries(diff.added || {}).map(([key, value]) => (
        <div key={key} className="flex justify-between items-center py-2 px-3 bg-green-900/20 rounded-lg border border-green-600/30">
          <span className="text-green-400 text-sm font-medium">+ {formatParamName(key)}</span>
          <span className="text-green-300 text-xs">{typeof value === 'number' ? value.toFixed(2) : value}</span>
        </div>
      ))}
    </div>
  );
};

// Format parameter names for display
const formatParamName = (key) => {
  return key
    .replace(/_/g, ' ')
    .replace(/pct/gi, '%')
    .replace(/mult/gi, 'multiplier')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

export function AgentPresetManager({ 
  agentId,
  agentType, 
  currentConfig,
  onConfigChange,
  onApply,
  presets,
  userRole = "viewer"
}) {
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [previewDiff, setPreviewDiff] = useState(null);
  const [showDiffDialog, setShowDiffDialog] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [customPresetName, setCustomPresetName] = useState("");
  const [customPresetDesc, setCustomPresetDesc] = useState("");
  const [importJson, setImportJson] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [pendingConfig, setPendingConfig] = useState(null);
  
  const canSaveGlobal = ["owner", "admin"].includes(userRole);
  const canSaveCustom = ["owner", "admin", "tester"].includes(userRole);
  
  // Handle preset selection
  const handlePresetSelect = useCallback(async (presetKey) => {
    setIsLoading(true);
    try {
      // Get diff preview from API
      const response = await api.post(`/api/agents/${agentId}/preview-preset`, {
        preset_key: presetKey
      });
      
      setSelectedPreset({
        key: presetKey,
        name: presets?.[presetKey]?.name || presetLabels[presetKey],
        emoji: presets?.[presetKey]?.emoji || "",
      });
      setPreviewDiff(response.data.diff);
      setPendingConfig(response.data.preset_params);
      setShowDiffDialog(true);
    } catch (error) {
      console.error("Error previewing preset:", error);
      // Fallback to local preview
      const preset = presets?.[presetKey];
      if (preset) {
        const localDiff = calculateLocalDiff(currentConfig, preset.values || preset.params);
        setSelectedPreset({
          key: presetKey,
          name: preset.name || presetLabels[presetKey],
          emoji: preset.emoji || "",
        });
        setPreviewDiff(localDiff);
        setPendingConfig(preset.values || preset.params);
        setShowDiffDialog(true);
      } else {
        toast.error("Error loading preset preview");
      }
    } finally {
      setIsLoading(false);
    }
  }, [agentId, currentConfig, presets]);
  
  // Calculate local diff
  const calculateLocalDiff = (current, preset) => {
    const diff = { changed: {}, added: {}, removed: {}, unchanged: {} };
    const allKeys = new Set([...Object.keys(current || {}), ...Object.keys(preset || {})]);
    
    allKeys.forEach(key => {
      const currentVal = current?.[key];
      const presetVal = preset?.[key];
      
      if (currentVal === undefined && presetVal !== undefined) {
        diff.added[key] = presetVal;
      } else if (currentVal !== undefined && presetVal === undefined) {
        diff.removed[key] = currentVal;
      } else if (currentVal !== presetVal) {
        diff.changed[key] = { from: currentVal, to: presetVal };
      } else {
        diff.unchanged[key] = currentVal;
      }
    });
    
    return diff;
  };
  
  // Apply preset
  const handleApplyPreset = useCallback(async () => {
    if (!selectedPreset || !pendingConfig) return;
    
    setIsLoading(true);
    try {
      await api.post(`/api/agents/${agentId}/apply-preset`, {
        preset_key: selectedPreset.key
      });
      
      toast.success(`Preset "${selectedPreset.name}" applied successfully!`);
      setShowDiffDialog(false);
      setSelectedPreset(null);
      setPendingConfig(null);
      setPreviewDiff(null);
      
      // Trigger refresh
      if (onApply) onApply();
    } catch (error) {
      console.error("Error applying preset:", error);
      toast.error(error.response?.data?.detail || "Error applying preset");
    } finally {
      setIsLoading(false);
    }
  }, [agentId, selectedPreset, pendingConfig, onApply]);
  
  // Save custom preset
  const handleSavePreset = useCallback(async (isGlobal = false) => {
    if (!customPresetName.trim()) {
      toast.error("Preset name is required");
      return;
    }
    
    setIsLoading(true);
    try {
      await api.post("/api/presets/save", {
        name: customPresetName,
        agent_type: agentType,
        params: currentConfig,
        description: customPresetDesc,
        is_global: isGlobal
      });
      
      toast.success(`Preset "${customPresetName}" saved!`);
      setShowSaveDialog(false);
      setCustomPresetName("");
      setCustomPresetDesc("");
    } catch (error) {
      console.error("Error saving preset:", error);
      toast.error(error.response?.data?.detail || "Error saving preset");
    } finally {
      setIsLoading(false);
    }
  }, [agentType, currentConfig, customPresetName, customPresetDesc]);
  
  // Reset to defaults
  const handleReset = useCallback(() => {
    if (presets?.moderate) {
      handlePresetSelect("moderate");
    }
  }, [presets, handlePresetSelect]);
  
  // Export JSON
  const handleExport = useCallback(() => {
    const exportData = {
      agent_type: agentType,
      exported_at: new Date().toISOString(),
      config: currentConfig
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${agentType}_config_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    toast.success("Configuration exported!");
  }, [agentType, currentConfig]);
  
  // Import JSON
  const handleImport = useCallback(() => {
    try {
      const data = JSON.parse(importJson);
      
      if (data.agent_type && data.agent_type !== agentType) {
        toast.error(`This file is for ${data.agent_type}, not ${agentType}`);
        return;
      }
      
      const config = data.config || data;
      const diff = calculateLocalDiff(currentConfig, config);
      
      setSelectedPreset({
        key: "imported",
        name: "Imported Configuration",
        emoji: "📥"
      });
      setPreviewDiff(diff);
      setPendingConfig(config);
      setShowImportDialog(false);
      setShowDiffDialog(true);
      setImportJson("");
    } catch (error) {
      toast.error("Invalid JSON");
    }
  }, [agentType, currentConfig, importJson]);
  
  return (
    <div className="space-y-4">
      {/* Preset Buttons */}
      <div className="flex flex-wrap gap-2">
        {["conservative", "moderate", "aggressive"].map((key) => (
          <Button
            key={key}
            variant="outline"
            size="sm"
            className={`text-xs ${presetStyles[key]} border`}
            onClick={() => handlePresetSelect(key)}
            disabled={isLoading}
          >
            {presetLabels[key]}
          </Button>
        ))}
        
        {canSaveCustom && (
          <Button
            variant="outline"
            size="sm"
            className={`text-xs ${presetStyles.custom} border`}
            onClick={() => setShowSaveDialog(true)}
            disabled={isLoading}
          >
            <Save className="w-3 h-3 mr-1" />
            Guardar
          </Button>
        )}
      </div>
      
      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-zinc-400 hover:text-zinc-200"
          onClick={handleReset}
          disabled={isLoading}
        >
          <RotateCcw className="w-3 h-3 mr-1" />
          Reset
        </Button>
        
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-zinc-400 hover:text-zinc-200"
          onClick={handleExport}
          disabled={isLoading}
        >
          <Download className="w-3 h-3 mr-1" />
          Export JSON
        </Button>
        
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-zinc-400 hover:text-zinc-200"
          onClick={() => setShowImportDialog(true)}
          disabled={isLoading}
        >
          <Upload className="w-3 h-3 mr-1" />
          Import JSON
        </Button>
      </div>
      
      {/* Diff Preview Dialog */}
      <AlertDialog open={showDiffDialog} onOpenChange={setShowDiffDialog}>
        <AlertDialogContent className="bg-zinc-900 border-zinc-800 max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-white flex items-center gap-2">
              {selectedPreset?.emoji} Aplicar {selectedPreset?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              As seguintes alterações serão aplicadas:
            </AlertDialogDescription>
          </AlertDialogHeader>
          
          <div className="py-2">
            <DiffPreview diff={previewDiff} presetName={selectedPreset?.name} />
          </div>
          
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-zinc-800 text-zinc-300 border-zinc-700 hover:bg-zinc-700">
              <X className="w-4 h-4 mr-1" />
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction 
              className="bg-blue-600 hover:bg-blue-700"
              onClick={handleApplyPreset}
              disabled={isLoading}
            >
              <Check className="w-4 h-4 mr-1" />
              Aplicar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      
      {/* Save Preset Dialog */}
      <Dialog open={showSaveDialog} onOpenChange={setShowSaveDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="text-white">⭐ Guardar Preset Personalizado</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Guarde a configuração atual como um preset reutilizável.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label className="text-zinc-300">Nome do Preset</Label>
              <Input
                value={customPresetName}
                onChange={(e) => setCustomPresetName(e.target.value)}
                placeholder="Ex: Minha estratégia conservadora"
                className="bg-zinc-800 border-zinc-700 text-white"
              />
            </div>
            
            <div className="space-y-2">
              <Label className="text-zinc-300">Description (optional)</Label>
              <Input
                value={customPresetDesc}
                onChange={(e) => setCustomPresetDesc(e.target.value)}
                placeholder="E.g.: Configuration optimized for low volatility"
                className="bg-zinc-800 border-zinc-700 text-white"
              />
            </div>
          </div>
          
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => handleSavePreset(false)}
              disabled={isLoading || !customPresetName.trim()}
              className="bg-zinc-800 text-zinc-300 border-zinc-700"
            >
              <Save className="w-4 h-4 mr-1" />
              Save Personal
            </Button>
            
            {canSaveGlobal && (
              <Button
                onClick={() => handleSavePreset(true)}
                disabled={isLoading || !customPresetName.trim()}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Save className="w-4 h-4 mr-1" />
                Save Global
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      {/* Import JSON Dialog */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="text-white">📥 Import Configuration</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Paste the previously exported configuration JSON.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <textarea
              value={importJson}
              onChange={(e) => setImportJson(e.target.value)}
              placeholder='{"agent_type": "dca", "config": {...}}'
              className="w-full h-40 p-3 bg-zinc-800 border border-zinc-700 rounded-md text-white font-mono text-xs"
            />
          </div>
          
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowImportDialog(false)}
              className="bg-zinc-800 text-zinc-300 border-zinc-700"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleImport}
              disabled={!importJson.trim()}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Upload className="w-4 h-4 mr-1" />
              Importar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default AgentPresetManager;
