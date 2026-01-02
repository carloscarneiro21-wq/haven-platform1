import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function PnlLineChart({ data }) {
  const hasData = Array.isArray(data) && data.length > 1;

  return (
    <Card className="bg-[#0B0E11] border border-white/10 rounded-md">
      <CardHeader className="py-3 px-4 border-b border-white/10">
        <div className="text-sm text-[#EAECEF] font-medium">Cumulative PnL</div>
      </CardHeader>
      <CardContent className="p-4">
        {!hasData && (
          <div className="text-sm text-[#848E9C]">No PnL history yet.</div>
        )}
        {hasData && (
          <div className="h-[180px] min-h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid stroke="#1E2329" />
                <XAxis dataKey="x" stroke="#5E6673" tick={{ fontSize: 10, fill: "#5E6673" }} />
                <YAxis stroke="#5E6673" tick={{ fontSize: 10, fill: "#5E6673" }} />
                <Tooltip
                  contentStyle={{ background: "#0B0E11", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6 }}
                  labelStyle={{ color: "#848E9C" }}
                />
                <Line type="monotone" dataKey="y" stroke="#0ECB81" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
