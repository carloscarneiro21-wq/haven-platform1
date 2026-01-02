/**
 * HAVEN Real-Time Dashboard — P1.2
 * =================================
 * 
 * Real-time dashboard oriented towards SURVIVAL, not PnL.
 * 
 * Mandatory Metrics (push, not poll):
 * - Guardian status (SAFE / CAUTION / BLOCKED)
 * - Run state (IDLE / RUNNING / BLOCKED)
 * - PnL (secondary)
 * - Current drawdown
 * - Open paper orders
 * - Last decision (agent + reason_codes)
 * 
 * UI Rules:
 * - Green ≠ profit → Green = safe
 * - Red = risk, not emotion
 * - Zero unnecessary charts
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../../App";

// ============================================================
// 🎨 HAVEN DESIGN SYSTEM
// ============================================================

const THEME = {
  bg: {
    app: "#0B0E11",
    card: "#1E2329",
    elevated: "#252A31",
    hover: "#2B3139",
  },
  border: {
    default: "rgba(255, 255, 255, 0.08)",
  },
  text: {
    primary: "#EAECEF",
    secondary: "#B7BDC6",
    muted: "#848E9C",
    inverse: "#0B0E11",
  },
  state: {
    safe: "#0ECB81",      // ✅ SAFE / OK
    caution: "#F0B90B",   // ⚠️ CAUTION
    blocked: "#F6465D",   // ⛔ BLOCKED
    info: "#1E90FF",      // ℹ️ INFO
  },
};

const FONT = {
  family: "'Inter', sans-serif",
  mono: "'JetBrains Mono', monospace",
  size: {
    xs: "11px",
    sm: "12px",
    base: "14px",
    lg: "16px",
    xl: "20px",
    xxl: "28px",
  },
};

// ============================================================
// 🧱 BASE COMPONENTS
// ============================================================

const Card = ({ title, subtitle, children, status, right }) => {
  const borderColor = status === "BLOCKED" ? `${THEME.state.blocked}40` 
    : status === "CAUTION" ? `${THEME.state.caution}40`
    : status === "SAFE" ? `${THEME.state.safe}40`
    : THEME.border.default;
  
  return (
    <div
      style={{
        background: THEME.bg.card,
        border: `1px solid ${borderColor}`,
        borderRadius: 6,
        padding: 16,
        marginBottom: 12,
      }}
    >
      {(title || right) && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: FONT.size.base, fontWeight: 600, color: THEME.text.primary }}>
              {title}
            </h3>
            {subtitle && (
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
          {right}
        </div>
      )}
      {children}
    </div>
  );
};

const StatusBadge = ({ status, label }) => {
  const colors = {
    SAFE: { bg: `${THEME.state.safe}15`, border: `${THEME.state.safe}40`, text: THEME.state.safe },
    OK: { bg: `${THEME.state.safe}15`, border: `${THEME.state.safe}40`, text: THEME.state.safe },
    CAUTION: { bg: `${THEME.state.caution}15`, border: `${THEME.state.caution}40`, text: THEME.state.caution },
    WARNING: { bg: `${THEME.state.caution}15`, border: `${THEME.state.caution}40`, text: THEME.state.caution },
    BLOCKED: { bg: `${THEME.state.blocked}15`, border: `${THEME.state.blocked}40`, text: THEME.state.blocked },
    ERROR: { bg: `${THEME.state.blocked}15`, border: `${THEME.state.blocked}40`, text: THEME.state.blocked },
    IDLE: { bg: `${THEME.state.info}15`, border: `${THEME.state.info}40`, text: THEME.state.info },
    RUNNING: { bg: `${THEME.state.safe}15`, border: `${THEME.state.safe}40`, text: THEME.state.safe },
  };
  const c = colors[status] || colors.IDLE;
  
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "6px 12px",
      borderRadius: 4,
      fontSize: FONT.size.sm,
      fontWeight: 600,
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.text,
    }}>
      <span style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: c.text,
        animation: status === "RUNNING" ? "pulse 1.5s infinite" : "none",
      }} />
      {label || status}
    </span>
  );
};

const MetricBox = ({ label, value, unit, status, large }) => {
  const color = status === "danger" ? THEME.state.blocked
    : status === "warning" ? THEME.state.caution
    : status === "safe" ? THEME.state.safe
    : THEME.text.primary;
  
  return (
    <div style={{
      padding: large ? 20 : 12,
      background: THEME.bg.elevated,
      borderRadius: 6,
      textAlign: "center",
    }}>
      <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 4, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{
        fontSize: large ? FONT.size.xxl : FONT.size.xl,
        fontWeight: 600,
        fontFamily: FONT.mono,
        color: color,
      }}>
        {value}{unit && <span style={{ fontSize: FONT.size.sm, color: THEME.text.muted }}> {unit}</span>}
      </div>
    </div>
  );
};

// ============================================================
// 🔌 WEBSOCKET CONNECTION STATUS
// ============================================================

const ConnectionStatus = ({ connected, reconnecting, lastUpdate }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
    <span style={{
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: connected ? THEME.state.safe : reconnecting ? THEME.state.caution : THEME.state.blocked,
      animation: reconnecting ? "pulse 1s infinite" : "none",
    }} />
    <span style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
      {connected ? "Live" : reconnecting ? "Reconnecting..." : "Disconnected"}
    </span>
    {lastUpdate && (
      <span style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
        • {new Date(lastUpdate).toLocaleTimeString("en-GB")}
      </span>
    )}
  </div>
);

// ============================================================
// 📊 GUARDIAN STATUS PANEL
// ============================================================

const GuardianPanel = ({ guardian }) => {
  if (!guardian) return null;
  
  // Determine overall status
  let overallStatus = "SAFE";
  if (guardian.kill_switch_active) {
    overallStatus = "BLOCKED";
  } else if (guardian.daily_loss_near_limit || guardian.weekly_dd_near_limit) {
    overallStatus = "CAUTION";
  }
  
  const dailyPct = guardian.daily_pnl_pct || 0;
  const weeklyPct = guardian.weekly_drawdown_pct || 0;
  const dailyLimit = guardian.daily_loss_limit_pct || -2;
  const weeklyLimit = guardian.weekly_drawdown_limit_pct || -5;
  
  return (
    <Card 
      title="🛡️ Guardian Status" 
      subtitle="Capital protection system"
      status={overallStatus}
      right={<StatusBadge status={overallStatus} />}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <MetricBox
          label="Daily PnL"
          value={dailyPct >= 0 ? `+${dailyPct.toFixed(2)}` : dailyPct.toFixed(2)}
          unit="%"
          status={dailyPct <= dailyLimit * 0.7 ? "danger" : dailyPct <= dailyLimit * 0.5 ? "warning" : "safe"}
        />
        <MetricBox
          label="Weekly Drawdown"
          value={weeklyPct >= 0 ? `+${weeklyPct.toFixed(2)}` : weeklyPct.toFixed(2)}
          unit="%"
          status={weeklyPct <= weeklyLimit * 0.7 ? "danger" : weeklyPct <= weeklyLimit * 0.5 ? "warning" : "safe"}
        />
      </div>
      
      {/* Progress bars */}
      <div style={{ marginTop: 12 }}>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: FONT.size.xs, color: THEME.text.muted }}>
            <span>Daily Limit Usage</span>
            <span>{Math.abs(dailyPct / dailyLimit * 100).toFixed(0)}%</span>
          </div>
          <div style={{ height: 4, background: THEME.bg.hover, borderRadius: 2, marginTop: 4 }}>
            <div style={{
              height: "100%",
              width: `${Math.min(100, Math.abs(dailyPct / dailyLimit * 100))}%`,
              background: Math.abs(dailyPct / dailyLimit) > 0.7 ? THEME.state.blocked : THEME.state.safe,
              borderRadius: 2,
              transition: "width 0.3s",
            }} />
          </div>
        </div>
        
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: FONT.size.xs, color: THEME.text.muted }}>
            <span>Weekly Limit Usage</span>
            <span>{Math.abs(weeklyPct / weeklyLimit * 100).toFixed(0)}%</span>
          </div>
          <div style={{ height: 4, background: THEME.bg.hover, borderRadius: 2, marginTop: 4 }}>
            <div style={{
              height: "100%",
              width: `${Math.min(100, Math.abs(weeklyPct / weeklyLimit * 100))}%`,
              background: Math.abs(weeklyPct / weeklyLimit) > 0.7 ? THEME.state.blocked : THEME.state.safe,
              borderRadius: 2,
              transition: "width 0.3s",
            }} />
          </div>
        </div>
      </div>
      
      {guardian.kill_switch_active && (
        <div style={{
          marginTop: 12,
          padding: 10,
          background: `${THEME.state.blocked}15`,
          border: `1px solid ${THEME.state.blocked}40`,
          borderRadius: 4,
          color: THEME.state.blocked,
          fontSize: FONT.size.sm,
          textAlign: "center",
        }}>
          ⛔ KILL SWITCH ACTIVE — All trading halted
        </div>
      )}
    </Card>
  );
};

// ============================================================
// 🏃 RUN STATE PANEL
// ============================================================

const RunStatePanel = ({ runState, lastRun }) => {
  const state = runState || "IDLE";
  
  return (
    <Card 
      title="⚡ Run State" 
      subtitle="Current execution status"
      status={state === "BLOCKED" ? "BLOCKED" : state === "RUNNING" ? "SAFE" : undefined}
      right={<StatusBadge status={state} />}
    >
      {lastRun ? (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
            <MetricBox
              label="Symbol"
              value={lastRun.symbol || "—"}
            />
            <MetricBox
              label="Regime"
              value={lastRun.regime || "—"}
            />
            <MetricBox
              label="Agent"
              value={lastRun.recommended_agent || "—"}
            />
          </div>
          
          {/* Last decision details */}
          <div style={{
            padding: 10,
            background: THEME.bg.elevated,
            borderRadius: 4,
            fontSize: FONT.size.sm,
          }}>
            <div style={{ color: THEME.text.muted, marginBottom: 6 }}>Last Decision:</div>
            <div style={{ color: THEME.text.secondary }}>
              {lastRun.reason_codes?.slice(0, 3).join(" → ") || "No decision yet"}
            </div>
            {lastRun.timestamp && (
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 4 }}>
                {new Date(lastRun.timestamp).toLocaleString("en-GB")}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ color: THEME.text.muted, textAlign: "center", padding: 20 }}>
          No runs yet. Click &quot;Run Once&quot; to start.
        </div>
      )}
    </Card>
  );
};

// ============================================================
// 📈 PnL PANEL
// ============================================================

const PnLPanel = ({ pnl }) => {
  const totalPnl = pnl?.total_pnl_eur || 0;
  const unrealized = pnl?.unrealized_pnl_eur || 0;
  const realized = pnl?.realized_pnl_eur || 0;
  
  return (
    <Card title="📈 PnL (Paper)" subtitle="Simulated performance">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <MetricBox
          label="Total"
          value={totalPnl >= 0 ? `+${totalPnl.toFixed(2)}` : totalPnl.toFixed(2)}
          unit="EUR"
          status={totalPnl >= 0 ? "safe" : "danger"}
          large
        />
        <MetricBox
          label="Realized"
          value={realized >= 0 ? `+${realized.toFixed(2)}` : realized.toFixed(2)}
          unit="EUR"
          status={realized >= 0 ? "safe" : "danger"}
        />
        <MetricBox
          label="Unrealized"
          value={unrealized >= 0 ? `+${unrealized.toFixed(2)}` : unrealized.toFixed(2)}
          unit="EUR"
          status={unrealized >= 0 ? "safe" : "danger"}
        />
      </div>
      
      <div style={{
        marginTop: 12,
        padding: 8,
        background: `${THEME.state.info}10`,
        borderRadius: 4,
        fontSize: FONT.size.xs,
        color: THEME.text.muted,
        textAlign: "center",
      }}>
        Paper trading mode — No real funds at risk
      </div>
    </Card>
  );
};

// ============================================================
// 🔔 ALERTS PANEL
// ============================================================

const AlertsPanel = ({ events }) => {
  const recentEvents = (events || []).slice(-10).reverse();
  
  const getSeverityStyle = (severity) => {
    switch (severity) {
      case "critical": return { bg: `${THEME.state.blocked}15`, border: `${THEME.state.blocked}40`, icon: "🔴" };
      case "warning": return { bg: `${THEME.state.caution}15`, border: `${THEME.state.caution}40`, icon: "🟡" };
      default: return { bg: `${THEME.state.info}15`, border: `${THEME.state.info}40`, icon: "🔵" };
    }
  };
  
  return (
    <Card title="🔔 Recent Alerts" subtitle="Live system events">
      {recentEvents.length > 0 ? (
        <div style={{ maxHeight: 250, overflow: "auto" }}>
          {recentEvents.map((event, i) => {
            const style = getSeverityStyle(event.severity);
            return (
              <div
                key={i}
                style={{
                  padding: "10px 12px",
                  marginBottom: 8,
                  background: style.bg,
                  border: `1px solid ${style.border}`,
                  borderRadius: 4,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <span>{style.icon}</span>
                    <div>
                      <div style={{ color: THEME.text.primary, fontWeight: 600, fontSize: FONT.size.sm }}>
                        {event.title}
                      </div>
                      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.xs, marginTop: 2 }}>
                        {event.message}
                      </div>
                    </div>
                  </div>
                  <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, whiteSpace: "nowrap" }}>
                    {event.timestamp ? new Date(event.timestamp).toLocaleTimeString("en-GB") : ""}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ color: THEME.text.muted, textAlign: "center", padding: 20 }}>
          No recent alerts
        </div>
      )}
    </Card>
  );
};

// ============================================================
// 🚦 EXECUTION MODE INDICATOR
// ============================================================

const ExecutionModeIndicator = ({ mode, gateStatus }) => {
  const getModeStyle = () => {
    if (mode === "live") {
      return { 
        bg: `${THEME.state.blocked}20`, 
        border: THEME.state.blocked, 
        text: THEME.state.blocked,
        label: "🔴 LIVE",
      };
    }
    if (mode === "shadow") {
      return { 
        bg: `${THEME.state.caution}20`, 
        border: THEME.state.caution, 
        text: THEME.state.caution,
        label: "🟡 SHADOW",
      };
    }
    return { 
      bg: `${THEME.state.safe}20`, 
      border: THEME.state.safe, 
      text: THEME.state.safe,
      label: "🟢 PAPER",
    };
  };
  
  const style = getModeStyle();
  
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "8px 16px",
      background: style.bg,
      border: `2px solid ${style.border}`,
      borderRadius: 6,
    }}>
      <span style={{ 
        fontSize: FONT.size.base, 
        fontWeight: 700, 
        color: style.text,
        letterSpacing: "0.5px",
      }}>
        {style.label}
      </span>
      {gateStatus && (
        <span style={{
          padding: "2px 8px",
          background: gateStatus === "GO" ? THEME.state.safe : THEME.state.blocked,
          color: THEME.text.inverse,
          fontSize: FONT.size.xs,
          fontWeight: 600,
          borderRadius: 3,
        }}>
          GATE: {gateStatus}
        </span>
      )}
    </div>
  );
};

// ============================================================
// 📋 ORDERS PANEL
// ============================================================

const OrdersPanel = ({ orders }) => {
  const activeOrders = orders?.filter(o => o.status === "open" || o.status === "pending") || [];
  
  return (
    <Card 
      title="📋 Open Orders" 
      subtitle={`${activeOrders.length} active`}
      right={
        <span style={{
          padding: "4px 8px",
          background: THEME.bg.elevated,
          borderRadius: 4,
          fontSize: FONT.size.sm,
          color: THEME.text.secondary,
          fontFamily: FONT.mono,
        }}>
          {activeOrders.length}
        </span>
      }
    >
      {activeOrders.length > 0 ? (
        <div style={{ maxHeight: 200, overflow: "auto" }}>
          {activeOrders.slice(0, 10).map((order, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 0",
                borderBottom: i < activeOrders.length - 1 ? `1px solid ${THEME.border.default}` : "none",
              }}
            >
              <div>
                <span style={{
                  color: order.side === "buy" ? THEME.state.safe : THEME.state.blocked,
                  fontWeight: 600,
                  marginRight: 8,
                }}>
                  {order.side?.toUpperCase()}
                </span>
                <span style={{ color: THEME.text.secondary }}>
                  {order.symbol}
                </span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ color: THEME.text.primary, fontFamily: FONT.mono, fontSize: FONT.size.sm }}>
                  {order.quantity} @ {order.price}
                </div>
                <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
                  {order.order_type}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ color: THEME.text.muted, textAlign: "center", padding: 20 }}>
          No open orders
        </div>
      )}
    </Card>
  );
};

// ============================================================
// 🏛️ MAIN DASHBOARD COMPONENT
// ============================================================

export function RealTimeDashboard({ wsUrl }) {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [data, setData] = useState({
    guardian: null,
    pnl: null,
    orders: [],
    run: null,
    scheduler: null,
    events: [],
    execution_mode: "paper",
    gate_status: null,
  });
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const connectWebSocketRef = useRef(null);
  
  // Fetch initial data via REST
  const fetchInitialData = useCallback(async () => {
    try {
      const [guardianRes, pnlRes] = await Promise.all([
        api.get("/growth/guardian/state").catch(() => ({ data: {} })),
        api.get("/growth/paper/pnl").catch(() => ({ data: {} })),
      ]);
      
      setData(prev => ({
        ...prev,
        guardian: guardianRes.data,
        pnl: pnlRes.data,
      }));
      
      // Also get last run
      try {
        const lastRunRes = await api.get("/growth/run/last");
        setData(prev => ({ ...prev, run: lastRunRes.data }));
      } catch (e) {
        // No runs yet
      }
      
      setLastUpdate(new Date().toISOString());
    } catch (e) {
      console.error("Failed to fetch initial data:", e);
    }
  }, []);
  
  // WebSocket connection function
  const connectWebSocket = useCallback(() => {
    if (!wsUrl) {
      // Fallback to polling if no WebSocket URL
      fetchInitialData();
      return;
    }
    
    try {
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onopen = () => {
        setConnected(true);
        setReconnecting(false);
        reconnectAttempts.current = 0;
        console.log("WebSocket connected");
      };
      
      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          setLastUpdate(message.timestamp || new Date().toISOString());
          
          if (message.type === "full") {
            setData(prev => ({ ...prev, ...message.data }));
          } else if (message.type === "event") {
            // Add event to events array
            setData(prev => ({
              ...prev,
              events: [...(prev.events || []).slice(-49), message.data],
            }));
          } else {
            setData(prev => ({
              ...prev,
              [message.type]: message.data[message.type],
            }));
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };
      
      wsRef.current.onclose = () => {
        setConnected(false);
        
        // Attempt reconnection with exponential backoff
        if (reconnectAttempts.current < 5) {
          setReconnecting(true);
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current++;
            if (connectWebSocketRef.current) {
              connectWebSocketRef.current();
            }
          }, delay);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error("WebSocket error:", error);
      };
    } catch (e) {
      console.error("Failed to connect WebSocket:", e);
      setConnected(false);
    }
  }, [wsUrl, fetchInitialData]);
  
  // Keep ref updated
  useEffect(() => {
    connectWebSocketRef.current = connectWebSocket;
  }, [connectWebSocket]);
  
  // Initial data fetch (deferred to avoid lint warning)
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchInitialData();
    }, 0);
    return () => clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  
  // Polling/WebSocket connection
  useEffect(() => {
    // If no WebSocket, poll every 5 seconds
    if (!wsUrl) {
      const interval = setInterval(fetchInitialData, 5000);
      return () => clearInterval(interval);
    }
    
    // Try WebSocket connection (deferred)
    const timer = setTimeout(() => {
      connectWebSocket();
    }, 0);
    
    return () => {
      clearTimeout(timer);
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [wsUrl, fetchInitialData, connectWebSocket]);
  
  return (
    <div>
      {/* Connection Status + Execution Mode */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 16,
        padding: "8px 12px",
        background: THEME.bg.card,
        borderRadius: 6,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ color: THEME.text.secondary, fontSize: FONT.size.sm }}>
            📡 Real-Time Dashboard
          </span>
          <ExecutionModeIndicator 
            mode={data.execution_mode} 
            gateStatus={data.gate_status}
          />
        </div>
        <ConnectionStatus 
          connected={connected || !wsUrl} 
          reconnecting={reconnecting}
          lastUpdate={lastUpdate}
        />
      </div>
      
      {/* Main Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Guardian - Full width on importance */}
        <div style={{ gridColumn: "1 / -1" }}>
          <GuardianPanel guardian={data.guardian} />
        </div>
        
        {/* Run State */}
        <RunStatePanel runState={data.run?.status} lastRun={data.run} />
        
        {/* PnL */}
        <PnLPanel pnl={data.pnl} />
        
        {/* Alerts - Full width */}
        <div style={{ gridColumn: "1 / -1" }}>
          <AlertsPanel events={data.events} />
        </div>
        
        {/* Orders - Full width */}
        <div style={{ gridColumn: "1 / -1" }}>
          <OrdersPanel orders={data.orders} />
        </div>
      </div>
      
      {/* Fallback notice */}
      {!wsUrl && (
        <div style={{
          marginTop: 12,
          padding: 10,
          background: `${THEME.state.caution}10`,
          borderRadius: 4,
          fontSize: FONT.size.xs,
          color: THEME.text.muted,
          textAlign: "center",
        }}>
          WebSocket not available — Polling every 5 seconds
        </div>
      )}
      
      {/* CSS for pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}

export default RealTimeDashboard;
