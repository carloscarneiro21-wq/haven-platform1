import { Card, CardContent } from "@/components/ui/card";

function KpiCard({ label, value, tone = "neutral" }) {
  const valueClass =
    tone === "pos" ? "text-[#0ECB81]" : tone === "neg" ? "text-[#F6465D]" : "text-[#EAECEF]";

  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardContent className="p-4">
        <div className="text-[11px] text-[#848E9C] uppercase tracking-wider">{label}</div>
        <div className={`mt-1 text-xl font-semibold ${valueClass}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

export default function KpiStrip({ kpis }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
      {kpis.map((k) => (
        <KpiCard key={k.label} label={k.label} value={k.value} tone={k.tone} />
      ))}
    </div>
  );
}
