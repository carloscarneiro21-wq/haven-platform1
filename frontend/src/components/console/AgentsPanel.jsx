import { Card, CardContent, CardHeader } from "@/components/ui/card";

function AgentRow({ a }) {
  const tone = a.state === "ACTIVE" ? "text-[#0ECB81]" : "text-[#848E9C]";
  return (
    <div className="py-2 border-b border-white/5 last:border-b-0">
      <div className="flex items-center justify-between">
        <div className="text-sm text-[#EAECEF] font-medium">{a.name}</div>
        <div className={`text-xs font-mono ${tone}`}>{a.state}</div>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <div className="text-[11px] text-[#5E6673]">Last action</div>
        <div className="text-[11px] font-mono text-[#EAECEF] truncate max-w-[240px] text-right">
          {a.lastAction || "—"}
        </div>
      </div>
      <div className="mt-1 text-[10px] text-[#5E6673] uppercase tracking-wider">inferred</div>
    </div>
  );
}

export default function AgentsPanel({ agents }) {
  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardHeader className="py-3 px-4 border-b border-white/10">
        <div className="text-sm text-[#EAECEF] font-medium">Agents</div>
      </CardHeader>
      <CardContent className="p-4">
        {(!agents || agents.length === 0) && (
          <div className="text-sm text-[#848E9C]">No agent activity yet.</div>
        )}
        {agents?.length > 0 && (
          <div className="divide-y divide-white/5">
            {agents.map((a) => (
              <AgentRow key={a.key} a={a} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
