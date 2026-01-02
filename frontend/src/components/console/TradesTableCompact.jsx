import { Card, CardContent, CardHeader } from "@/components/ui/card";

function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function TradesTableCompact({ trades }) {
  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardHeader className="py-3 px-4 border-b border-white/10">
        <div className="text-sm text-[#EAECEF] font-medium">Trades (last 20)</div>
      </CardHeader>
      <CardContent className="p-0">
        {(!trades || trades.length === 0) && (
          <div className="p-6 text-sm text-[#848E9C]">No trades yet.</div>
        )}
        {trades?.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] text-[#848E9C] uppercase tracking-wider border-b border-white/10 bg-white/[0.02]">
                  <th className="text-left px-4 py-2 font-medium">Time</th>
                  <th className="text-left px-4 py-2 font-medium">Symbol</th>
                  <th className="text-left px-4 py-2 font-medium">Side</th>
                  <th className="text-right px-4 py-2 font-medium">Qty</th>
                  <th className="text-right px-4 py-2 font-medium">Entry</th>
                  <th className="text-right px-4 py-2 font-medium">Exit</th>
                  <th className="text-right px-4 py-2 font-medium">PnL</th>
                  <th className="text-left px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((t) => {
                  const isOpen = String(t.status || "").toLowerCase() === "open";
                  const pnl = t.pnl ?? t.realized_pnl ?? 0;
                  const pnlTone = pnl > 0 ? "text-[#0ECB81]" : pnl < 0 ? "text-[#F6465D]" : "text-[#EAECEF]";

                  return (
                    <tr
                      key={t.id}
                      className={`border-b border-white/5 ${isOpen ? "bg-white/[0.03]" : ""}`}
                    >
                      <td className="px-4 py-2 font-mono text-xs text-[#EAECEF]">{fmtTime(t.executed_at || t.ts || t.open_time)}</td>
                      <td className="px-4 py-2 font-mono text-xs text-[#EAECEF]">{t.symbol}</td>
                      <td className="px-4 py-2 font-mono text-xs">
                        <span className={String(t.side).toLowerCase() === "buy" ? "text-[#0ECB81]" : "text-[#F6465D]"}>
                          {String(t.side || "").toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-[#EAECEF]">{fmt(t.amount ?? t.qty)}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-[#EAECEF]">{fmt(t.entry_price ?? t.price)}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-[#EAECEF]">{fmt(t.exit_price)}</td>
                      <td className={`px-4 py-2 text-right font-mono text-xs ${pnlTone}`}>{fmt(pnl)}</td>
                      <td className="px-4 py-2 font-mono text-xs text-[#EAECEF]">{String(t.status || "").toUpperCase()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
