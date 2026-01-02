import * as React from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { HelpCircle } from "lucide-react";

export function FieldTooltip({ text, children, side = "top" }) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          {children || (
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full text-zinc-500 hover:text-zinc-300 cursor-help">
              <HelpCircle className="w-3.5 h-3.5" />
            </span>
          )}
        </TooltipTrigger>
        <TooltipContent 
          side={side} 
          className="bg-zinc-800 border-zinc-700 text-zinc-200 max-w-xs text-sm"
        >
          <p>{text}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default FieldTooltip;
