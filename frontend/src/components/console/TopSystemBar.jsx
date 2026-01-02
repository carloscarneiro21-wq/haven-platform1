import { useEffect, useMemo, useState } from "react";
import { api } from "@/App";

function Dot({ color }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

function Item({ label, children }) {
  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      <span className="text-[11px] text-[#848E9C] uppercase tracking-wider">{label}</span>
      <div className="text-[12px] text-[#EAECEF] font-mono">{children}</div>
    </div>
  );
}

export default function TopSystemBar({ wsConnected, usingPolling, lastEventIso }) {
  const [runtime, setRuntime] = useState(null);
  const [tradingStatus, setTradingStatus] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [rt, ts] = await Promise.all([
          api.get("/runtime/status").catch(() => ({ data: null })),
          api.get("/trading/status").catch(() => ({ data: null })),
        ]);
        setRuntime(rt.data);
        setTradingStatus(ts.data);
      } catch (_) {
        // silent
      }
    };

    fetch();
    const id = setInterval(fetch, 15000);
    return () => clearInterval(id);
  }, []);

  const runtimeState = runtime?.running ? "ACTIVE" : "OFFLINE";
  const runtimeDot = runtime?.running ? "bg-[#0ECB81]" : "bg-[#5E6673]";

  const mode = String(tradingStatus?.trading_mode || "paper").toUpperCase();

  const wsState = wsConnected ? "CONNECTED" : usingPolling ? "POLLING" : "DISCONNECTED";
  const wsDot = wsConnected ? "bg-[#0ECB81]" : usingPolling ? "bg-[#F0B90B]" : "bg-[#F6465D]";

  const lastEvent = lastEventIso ? new Date(lastEventIso).toLocaleTimeString() : "—";

  return (
    <div className="sticky top-0 z-40 h-10 bg-[#0B0E11] border-b border-white/10">
      <div className="h-full px-6 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Item label="Runtime">
            <span className="flex items-center gap-2">
              <Dot color={runtimeDot} /> {runtimeState}
            </span>
          </Item>
          <Item label="Mode">
            <span className="text-[#F0B90B]">{mode}</span>
          </Item>
          <Item label="WS">
            <span className="flex items-center gap-2">
              <Dot color={wsDot} /> {wsState}
            </span>
          </Item>
        </div>

        <div className="flex items-center gap-6">
          <Item label="Last Event">{lastEvent}</Item>
        </div>
      </div>
    </div>
  );
}
