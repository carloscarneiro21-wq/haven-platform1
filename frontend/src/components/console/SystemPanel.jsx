import { Card, CardContent, CardHeader } from "@/components/ui/card";

function Row({ label, value, tone = "neutral" }) {
  const valueClass =
    tone === "pos" ? "text-[#0ECB81]" : tone === "neg" ? "text-[#F6465D]" : tone === "warn" ? "text-[#F0B90B]" : "text-[#EAECEF]";
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-b-0">
      <div className="text-xs text-[#848E9C] uppercase tracking-wider">{label}</div>
      <div className={`text-sm font-mono ${valueClass}`}>{value}</div>
    </div>
  );
}

export default function SystemPanel({ engineStatus, tradingStatus }) {
  const killSwitchActive = !!tradingStatus?.router?.kill_switch?.active;
  const mode = String(tradingStatus?.trading_mode || "paper");

  const feed = engineStatus?.data_feed;
  const feedStatus = feed?.status || feed?.initialized ? "LIVE" : "OFFLINE";

  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardHeader className="py-3 px-4 border-b border-white/10">
        <div className="text-sm text-[#EAECEF] font-medium">System</div>
      </CardHeader>
      <CardContent className="p-4">
        <Row label="Kill Switch" value={killSwitchActive ? "ACTIVE" : "OK"} tone={killSwitchActive ? "neg" : "pos"} />
        <Row label="Execution Mode" value={mode.toUpperCase()} tone={mode === "paper" ? "warn" : mode.includes("live") ? "neg" : "warn"} />
        <Row label="Feed" value={String(feedStatus).toUpperCase()} tone={String(feedStatus).toLowerCase() === "offline" ? "warn" : "pos"} />
      </CardContent>
    </Card>
  );
}
