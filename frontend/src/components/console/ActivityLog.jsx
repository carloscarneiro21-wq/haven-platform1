import { Card, CardContent, CardHeader } from "@/components/ui/card";

export default function ActivityLog({ items }) {
  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardHeader className="py-3 px-4 border-b border-white/10">
        <div className="text-sm text-[#EAECEF] font-medium">Activity</div>
      </CardHeader>
      <CardContent className="p-4">
        {(!items || items.length === 0) && (
          <div className="text-sm text-[#848E9C]">No recent activity.</div>
        )}
        {items?.length > 0 && (
          <div className="space-y-2 max-h-[260px] overflow-auto">
            {items.slice(0, 30).map((it, idx) => (
              <div key={idx} className="text-sm">
                <div className="flex items-center justify-between">
                  <div className="text-[#EAECEF]">{it.message}</div>
                  <div className="text-xs font-mono text-[#5E6673]">{it.ts}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
