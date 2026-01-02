import * as React from "react";
import { Info } from "lucide-react";
import { HelpDrawer } from "./HelpDrawer";

export function InfoIcon({ title, content, className = "" }) {
  const [open, setOpen] = React.useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={`inline-flex items-center justify-center w-5 h-5 rounded-full bg-zinc-700/50 hover:bg-zinc-600 text-zinc-400 hover:text-white transition-colors ${className}`}
        title="Ajuda"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      <HelpDrawer open={open} onClose={() => setOpen(false)} title={title}>
        {content}
      </HelpDrawer>
    </>
  );
}

export default InfoIcon;
