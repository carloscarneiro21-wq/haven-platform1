import * as React from "react";
import { Button } from "@/components/ui/button";
import { FieldTooltip } from "./FieldTooltip";

const presetStyles = {
  conservative: "bg-green-600/20 hover:bg-green-600/30 text-green-400 border-green-600/30",
  moderate: "bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400 border-yellow-600/30",
  aggressive: "bg-red-600/20 hover:bg-red-600/30 text-red-400 border-red-600/30",
};

const presetLabels = {
  conservative: "🟢 Conservador",
  moderate: "🟡 Moderado",
  aggressive: "🔴 Arriscado",
};

export function PresetButtons({ presets, onSelect, baseCapital = 50 }) {
  const calculatePercentage = (value) => {
    return ((value / baseCapital) * 100).toFixed(0);
  };

  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(presets).map(([key, preset]) => (
        <FieldTooltip
          key={key}
          text={preset.tooltip}
          side="bottom"
        >
          <Button
            variant="outline"
            size="sm"
            className={`text-xs ${presetStyles[key]} border`}
            onClick={() => onSelect(preset.values)}
          >
            {presetLabels[key]}
            {preset.values.trade_size_eur && (
              <span className="ml-1 opacity-70">
                ({calculatePercentage(preset.values.trade_size_eur)}% · €{preset.values.trade_size_eur})
              </span>
            )}
          </Button>
        </FieldTooltip>
      ))}
    </div>
  );
}

export default PresetButtons;
