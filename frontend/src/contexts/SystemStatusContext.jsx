import { createContext, useContext, useMemo, useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useTradesWebSocket } from "@/hooks/useTradesWebSocket";

const SystemStatusContext = createContext(null);

export function SystemStatusProvider({ children }) {
  const { token } = useAuth();
  const [lastEventIso, setLastEventIso] = useState(null);

  const { connected, usingPolling, lastMessage } = useTradesWebSocket(token, {
    autoConnect: true,
    onTrade: () => setTimeout(() => setLastEventIso(new Date().toISOString()), 0),
    onMetrics: () => setTimeout(() => setLastEventIso(new Date().toISOString()), 0),
  });

  // Update last event time for any non-noise message
  useEffect(() => {
    const t = lastMessage?.type;
    if (!t) return;
    if (["ping", "pong", "pong.ack", "heartbeat", "connected", "subscribed"].includes(t)) return;

    const id = setTimeout(() => {
      setLastEventIso(new Date().toISOString());
    }, 0);

    return () => clearTimeout(id);
  }, [lastMessage]);

  const value = useMemo(
    () => ({
      wsConnected: connected,
      usingPolling,
      lastEventIso,
      lastMessage,
    }),
    [connected, usingPolling, lastEventIso, lastMessage]
  );

  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}

export function useSystemStatus() {
  const ctx = useContext(SystemStatusContext);
  if (!ctx) throw new Error("useSystemStatus must be used within SystemStatusProvider");
  return ctx;
}
