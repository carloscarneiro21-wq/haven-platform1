import React, { useEffect, useMemo, useState } from "react";
import { api } from "../App";
import { ConfigEditor, PresetEditor } from "./growth/ConfigEditor";
import { SchedulerPanel } from "./growth/SchedulerPanel";
import { RealTimeDashboard } from "./growth/RealTimeDashboard";
import { GoLiveGate } from "./growth/GoLiveGate";
import { AuditDashboard } from "./growth/AuditDashboard";
import { BacktestPanel } from "./growth/BacktestPanel";

// ====================================================
// 🎨 HAVEN DESIGN SYSTEM (Binance-inspired)
// ====================================================
// "Built to Survive Markets"
// Color = functional state, never decoration
// Minimal, institutional, information > aesthetics
// ====================================================

const THEME = {
  // Backgrounds
  bg: {
    primary: "#0B0E11",    // App background
    secondary: "#161A1E",   // Cards level 1
    card: "#1E2329",        // Cards level 2
    elevated: "#252A31",    // Elevated surfaces
    hover: "#2B3139",       // Hover states
  },
  border: {
    default: "rgba(255, 255, 255, 0.08)",
    light: "rgba(255, 255, 255, 0.12)",
  },
  // Text Colors
  text: {
    primary: "#EAECEF",     // Main text
    secondary: "#B7BDC6",   // Secondary text
    muted: "#848E9C",       // Muted / explanations
    inverse: "#0B0E11",     // Text on light backgrounds
  },
  // State Colors (Color = functional state, never decoration)
  state: {
    success: "#0ECB81",  // ✅ OK / Safe / Allowed
    warning: "#F0B90B",  // ⚠️ Warning / Caution
    error: "#F6465D",    // ⛔ Blocked / Error / Risk
    info: "#1E90FF",     // ℹ️ Info / Neutral
  },
  // Brand / Accent
  accent: {
    primary: "#F0B90B",    // HAVEN primary (actions)
    secondary: "#1E90FF",  // Info accent
  },
};

// Typography
const FONT = {
  family: "'Inter', system-ui, sans-serif",
  weight: {
    title: 600,
    body: 400,
    emphasis: 500,
  },
  size: {
    h1: "20px",
    h2: "16px",
    body: "14px",
    small: "12px",
    tiny: "11px",
  },
};

// Spacing
const SPACING = {
  unit: 8,
  cardPadding: 20,
  sectionGap: 24,
  cardGap: 16,
  iconText: 8,
};

// Radius
const RADIUS = {
  card: "6px",
  button: "6px",
  pill: "4px",
};

// ---------- Reason code mapping (human + technical) ----------
const REASON_MAP = {
  // Router / Market
  REGIME_RANGE: { title: "Market consolidating", detail: "RANGE regime: price oscillating without clear trend." },
  REGIME_TREND: { title: "Trending market", detail: "TREND regime: consistent directional movement detected." },
  REGIME_HIGH_VOL: { title: "High volatility", detail: "HIGH_VOL regime: elevated ATR% + rapid price changes." },
  REGIME_CHOP: { title: "Choppy market", detail: "CHOP regime: contradictory signals and high noise." },

  ATR_LOW: { title: "Low volatility", detail: "ATR% below threshold. Fewer opportunities for short-term trades." },
  ATR_HIGH: { title: "High volatility", detail: "ATR% above threshold. More opportunity, but higher risk." },
  SLOPE_NEUTRAL: { title: "No significant trend", detail: "MA/EMA slope near zero." },
  SLOPE_STRONG: { title: "Strong trend", detail: "MA/EMA slope above threshold." },
  VOLUME_SPIKE: { title: "Volume spike", detail: "Current volume above baseline (spike detected)." },

  SPREAD_OK: { title: "Spread costs acceptable", detail: "Spread within defined threshold for micro-capital." },
  SPREAD_WIDE: { title: "Spread too wide", detail: "Spread above threshold; reduces probability of net profit." },

  // Guardian / Safety
  GUARDIAN_OK: { title: "Within safety limits", detail: "Guardian detected no limit violations." },
  DAILY_KILL_SWITCH: { title: "Daily protection triggered", detail: "Daily PnL below limit. System blocks new actions." },
  WEEKLY_DRAWDOWN_LIMIT: { title: "Weekly limit reached", detail: "Weekly drawdown exceeded maximum allowed." },
  DATA_UNSTABLE: { title: "Unstable data", detail: "Data source unstable or inconsistency detected." },
  LATENCY_HIGH: { title: "High latency", detail: "High latency may cause slippage and poor execution." },

  // Viability / Costs
  VIABLE: { title: "Viable", detail: "Expected return covers costs with margin." },
  COST_TOO_HIGH: { title: "Costs too high", detail: "Fees+spread+slippage make the operation unfavorable." },
  EDGE_TOO_LOW: { title: "Expected return insufficient", detail: "Expected edge does not cover costs × multiplier." },

  // Concurrency / budgets
  ONE_PRIMARY_ENFORCED: { title: "Single agent only", detail: "With low capital, system allows MM OR MOM, not both." },
  BUDGET_EXCEEDED: { title: "Risk budget exceeded", detail: "Operation exceeds permitted bucket (Core/Edge/Reserve)." },
};

// ---------- Helpers ----------
function getStateColor(level) {
  if (!level) return THEME.text.muted;
  const upper = String(level).toUpperCase();
  if (["OK", "OPERATIONAL", "ALLOWED", "SAFE", "VIABLE", "SUCCESS", "GO", "ACTIVE", "PASSED"].includes(upper)) return THEME.state.success;
  if (["WARN", "CAUTION", "WARNING", "MARGINAL"].includes(upper)) return THEME.state.warning;
  if (["BLOCKED", "ERROR", "PAUSED", "RISK", "NOT_VIABLE", "NO_GO", "NOGO", "FAILED", "DANGER"].includes(upper)) return THEME.state.error;
  if (["INFO", "NEUTRAL", "INSUFFICIENT"].includes(upper)) return THEME.state.info;
  return THEME.text.muted;
}

function safeJson(obj) {
  try {
    return JSON.stringify(obj ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function mapReasons(reasonCodes = []) {
  return (reasonCodes || []).map((code) => ({
    code,
    ...(REASON_MAP[code] || { title: code, detail: "No description available." }),
  }));
}

// ---------- UI Components ----------

// Badge component (transparent bg, border = state color)
function Badge({ status, children }) {
  const color = getStateColor(status);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "4px 12px",
        borderRadius: 4,
        border: `1px solid ${color}`,
        color: color,
        fontSize: FONT.size.small,
        fontFamily: FONT.family,
        fontWeight: FONT.weight.emphasis,
        lineHeight: "16px",
        background: "transparent",
      }}
    >
      {children}
    </span>
  );
}

// Card component
function Card({ title, subtitle, right, children }) {
  return (
    <div
      style={{
        background: THEME.bg.secondary,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 8,
        padding: SPACING.cardPadding,
        marginBottom: SPACING.cardGap,
        fontFamily: FONT.family,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div
            style={{
              color: THEME.text.primary,
              fontSize: FONT.size.h2,
              fontWeight: FONT.weight.title,
              lineHeight: "24px",
            }}
          >
            {title}
          </div>
          {subtitle && (
            <div
              style={{
                color: THEME.text.secondary,
                fontSize: FONT.size.small,
                fontWeight: FONT.weight.body,
                marginTop: 4,
              }}
            >
              {subtitle}
            </div>
          )}
        </div>
        {right && <div>{right}</div>}
      </div>
      <div style={{ marginTop: 16 }}>{children}</div>
    </div>
  );
}

// Section title
function SectionTitle({ children }) {
  return (
    <div
      style={{
        color: THEME.text.primary,
        fontSize: FONT.size.body,
        fontWeight: FONT.weight.emphasis,
        fontFamily: FONT.family,
        margin: "16px 0 8px",
      }}
    >
      {children}
    </div>
  );
}

// Two column layout
function TwoCol({ left, right }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: SPACING.cardGap }}>
      <div>{left}</div>
      <div>{right}</div>
    </div>
  );
}

// Button - Primary (info color border)
function ButtonPrimary({ onClick, disabled, children }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? THEME.bg.elevated : "transparent",
        color: THEME.text.primary,
        border: `1px solid ${THEME.accent.primary}`,
        borderRadius: 6,
        padding: "8px 16px",
        fontSize: FONT.size.body,
        fontFamily: FONT.family,
        fontWeight: FONT.weight.emphasis,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background 0.15s ease",
      }}
    >
      {children}
    </button>
  );
}

// Button - Secondary
function ButtonSecondary({ onClick, disabled, children }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? THEME.bg.elevated : "transparent",
        color: THEME.text.secondary,
        border: `1px solid ${THEME.border.strong}`,
        borderRadius: 6,
        padding: "8px 16px",
        fontSize: FONT.size.body,
        fontFamily: FONT.family,
        fontWeight: FONT.weight.body,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background 0.15s ease",
      }}
    >
      {children}
    </button>
  );
}

// Select input
function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={onChange}
      style={{
        background: THEME.bg.tertiary,
        color: THEME.text.primary,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: FONT.size.body,
        fontFamily: FONT.family,
        cursor: "pointer",
      }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

// Input field
function Input({ value, onChange, placeholder, type = "text" }) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      style={{
        background: THEME.bg.tertiary,
        color: THEME.text.primary,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 6,
        padding: "10px 12px",
        fontSize: FONT.size.body,
        fontFamily: FONT.family,
        width: "100%",
        boxSizing: "border-box",
      }}
    />
  );
}

// Stat display
function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{ color: THEME.text.muted, fontSize: FONT.size.small, fontFamily: FONT.family }}>
        {label}
      </div>
      <div
        style={{
          marginTop: 4,
          fontWeight: FONT.weight.title,
          fontSize: FONT.size.body,
          fontFamily: FONT.family,
          color: color || THEME.text.primary,
        }}
      >
        {value}
      </div>
    </div>
  );
}

// Helper to translate viability status
function translateViabilityStatus(status, viable) {
  if (viable === true) return "Viable";
  const statusMap = {
    "VIABLE": "Viable",
    "MARGINAL": "Marginal",
    "NOT_VIABLE": "Not Viable",
  };
  return statusMap[status] || (viable === false ? "Not Viable" : status);
}

// Helper to get viability badge status
function getViabilityBadgeStatus(status, viable) {
  if (viable === true || status === "VIABLE") return "OK";
  if (status === "MARGINAL") return "WARNING";
  return "BLOCKED";
}

// ============================================================
// 🧭 Run View Component - Minimal P1 UI
// ============================================================
// Estado geral (cor) | PnL | Estratégia | Botão "Porquê?"
// ============================================================

function RunView({ result, onClose }) {
  const [showWhy, setShowWhy] = useState(false);
  
  if (!result) return null;
  
  // Determine overall state color
  const getOverallState = () => {
    if (result.status === "success") return { color: THEME.state.success, label: "Success", icon: "✓" };
    if (result.status === "paused") return { color: THEME.state.warning, label: "Paused", icon: "⏸" };
    if (result.status === "blocked") return { color: THEME.state.error, label: "Blocked", icon: "✗" };
    if (result.status === "replayed") return { color: THEME.state.info, label: "Replay", icon: "↺" };
    return { color: THEME.state.error, label: "Error", icon: "!" };
  };
  
  const state = getOverallState();
  const pnl = result.pnl_delta_eur || 0;
  const pnlColor = pnl > 0 ? THEME.state.success : pnl < 0 ? THEME.state.error : THEME.text.primary;
  
  // Why explanations
  const whyExplanations = {
    regime: {
      label: "Market Regime",
      value: result.regime || "—",
      detail: getRegimeExplanation(result.regime),
    },
    agent: {
      label: "Selected Agent",
      value: result.recommended_agent || "—",
      detail: getAgentExplanation(result.recommended_agent, result.regime),
    },
    whyNotOthers: {
      label: "Why not other agents?",
      value: result.recommended_agent === "MM" ? "MOM discarded" : result.recommended_agent === "MOM" ? "MM discarded" : "—",
      detail: getWhyNotOthersExplanation(result.recommended_agent, result.regime, result.confidence),
    },
    costs: {
      label: "Costs vs Edge",
      value: result.viability_result ? 
        `${(result.viability_result.total_cost_pct || 0).toFixed(2)}% vs ${(result.viability_result.expected_edge_pct || 0).toFixed(2)}%` : "—",
      detail: getCostsExplanation(result.viability_result),
    },
    guardian: {
      label: "Guardian",
      value: result.guardian_result ? (result.guardian_result.allowed ? "Approved" : "Blocked") : "N/A",
      detail: getGuardianExplanation(result.guardian_result),
    },
  };
  
  return (
    <div
      style={{
        background: THEME.bg.secondary,
        border: `2px solid ${state.color}`,
        borderRadius: 12,
        padding: 20,
        marginBottom: 20,
      }}
    >
      {/* Header with state indicator */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* State circle */}
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: "50%",
              background: state.color + "20",
              border: `2px solid ${state.color}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
              color: state.color,
            }}
          >
            {state.icon}
          </div>
          <div>
            <div style={{ fontSize: FONT.size.h2, fontWeight: FONT.weight.title, color: THEME.text.primary }}>
              {state.label}
            </div>
            <div style={{ fontSize: FONT.size.small, color: THEME.text.muted }}>
              {result.symbol} • {result.run_id?.slice(0, 8)}
            </div>
          </div>
        </div>
        
        {onClose && (
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: THEME.text.muted,
              fontSize: 20,
              cursor: "pointer",
              padding: 8,
            }}
          >
            ×
          </button>
        )}
      </div>
      
      {/* Main stats row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          gap: 20,
          padding: 16,
          background: THEME.bg.tertiary,
          borderRadius: 8,
          marginBottom: 16,
        }}
      >
        <div>
          <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>PnL</div>
          <div style={{ fontSize: 24, fontWeight: FONT.weight.title, color: pnlColor, marginTop: 4 }}>
            {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}€
          </div>
        </div>
        <div>
          <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Estratégia</div>
          <div style={{ fontSize: 18, fontWeight: FONT.weight.title, color: THEME.text.primary, marginTop: 4 }}>
            {result.recommended_agent || "—"}
          </div>
          <div style={{ fontSize: FONT.size.small, color: THEME.text.muted }}>
            {result.recommended_preset_id?.replace(/_/g, " ") || ""}
          </div>
        </div>
        <div>
          <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Orders</div>
          <div style={{ fontSize: 18, fontWeight: FONT.weight.title, color: THEME.text.primary, marginTop: 4 }}>
            {result.orders_created || 0}
          </div>
          <div style={{ fontSize: FONT.size.small, color: THEME.text.muted }}>
            {result.orders_filled || 0} executed
          </div>
        </div>
        <div>
          <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Confidence</div>
          <div style={{ fontSize: 18, fontWeight: FONT.weight.title, color: THEME.text.primary, marginTop: 4 }}>
            {result.confidence || "—"}
          </div>
        </div>
      </div>
      
      {/* Why button */}
      <button
        onClick={() => setShowWhy(!showWhy)}
        style={{
          width: "100%",
          padding: "12px 16px",
          background: showWhy ? THEME.bg.elevated : "transparent",
          border: `1px solid ${THEME.accent.primary}`,
          borderRadius: 8,
          color: THEME.text.primary,
          fontSize: FONT.size.body,
          fontWeight: FONT.weight.emphasis,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
        }}
      >
        <span style={{ color: THEME.accent.primary }}>?</span>
        {showWhy ? "Hide explanation" : "Why this decision?"}
        <span style={{ color: THEME.text.muted }}>{showWhy ? "▲" : "▼"}</span>
      </button>
      
      {/* Expanded explanation */}
      {showWhy && (
        <div
          style={{
            marginTop: 16,
            padding: 16,
            background: THEME.bg.tertiary,
            borderRadius: 8,
            border: `1px solid ${THEME.border.default}`,
          }}
        >
          <div style={{ fontSize: FONT.size.body, fontWeight: FONT.weight.title, color: THEME.text.primary, marginBottom: 16 }}>
            Decision Explanation
          </div>
          
          {Object.entries(whyExplanations).map(([key, item]) => (
            <div
              key={key}
              style={{
                padding: "12px 0",
                borderBottom: `1px solid ${THEME.border.default}`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>
                  {item.label}
                </div>
                <div
                  style={{
                    color: key === "guardian" 
                      ? (result.guardian_result ? (result.guardian_result.allowed ? THEME.state.success : THEME.state.error) : THEME.text.muted)
                      : THEME.text.primary,
                    fontWeight: FONT.weight.emphasis,
                    fontSize: FONT.size.body,
                  }}
                >
                  {item.value}
                </div>
              </div>
              <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 6, lineHeight: 1.5 }}>
                {item.detail}
              </div>
            </div>
          ))}
          
          {/* Reason codes */}
          {result.reason_codes && result.reason_codes.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small, marginBottom: 8 }}>
                Reason Codes
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {result.reason_codes.slice(0, 6).map((code, idx) => (
                  <span
                    key={idx}
                    style={{
                      padding: "4px 8px",
                      background: THEME.bg.elevated,
                      border: `1px solid ${THEME.border.default}`,
                      borderRadius: 4,
                      fontSize: 11,
                      color: THEME.text.secondary,
                    }}
                  >
                    {code.length > 50 ? code.slice(0, 47) + "..." : code}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* Block reason if present */}
      {result.block_reason && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: THEME.state.error + "15",
            border: `1px solid ${THEME.state.error}`,
            borderRadius: 8,
          }}
        >
          <div style={{ color: THEME.state.error, fontWeight: FONT.weight.emphasis, fontSize: FONT.size.small }}>
            Block Reason
          </div>
          <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 4 }}>
            {result.block_reason}
          </div>
        </div>
      )}
    </div>
  );
}

// Explanation helpers
function getRegimeExplanation(regime) {
  const explanations = {
    "RANGE": "The market is moving sideways with no clear direction. Good for Market Making.",
    "TREND": "The market has a defined trend. Favorable for Momentum.",
    "HIGH_VOL": "High volatility detected. Requires additional caution.",
    "CHOP": "Irregular market with contradictory signals. System paused.",
  };
  return explanations[regime] || "Analysis of current market behavior.";
}

function getAgentExplanation(agent, regime) {
  if (agent === "MM") {
    return "Market Making selected because the market is sideways (RANGE). Places symmetric buy and sell orders to capture the spread.";
  }
  if (agent === "MOM") {
    return "Momentum selected because a trend was detected. Follows the direction of the move to capture directional gains.";
  }
  if (agent === "PAUSE") {
    return "System paused because conditions do not favor any strategy. Capital protection active.";
  }
  return "Strategy selected based on current market conditions.";
}

function getWhyNotOthersExplanation(agent, regime, confidence) {
  if (agent === "MM") {
    return "MOM was not selected because there is no clear trend (low ADX). In sideways markets, following trends results in whipsaw losses.";
  }
  if (agent === "MOM") {
    return "MM was not selected because there is a strong trend. Placing symmetric orders in a trend results in unfavorable fills.";
  }
  return "Other strategies discarded as not suitable for current conditions.";
}

function getCostsExplanation(viability) {
  if (!viability) return "Cost analysis not available.";
  
  const cost = viability.total_cost_pct || 0;
  const edge = viability.expected_edge_pct || 0;
  const surplus = edge - cost;
  
  if (surplus > 0.2) {
    return `Expected edge (${edge.toFixed(2)}%) exceeds costs (${cost.toFixed(2)}%) with comfortable margin. Operation viable.`;
  }
  if (surplus > 0) {
    return `Edge (${edge.toFixed(2)}%) covers costs (${cost.toFixed(2)}%) but margin is reduced. Marginal operation.`;
  }
  return `Costs (${cost.toFixed(2)}%) exceed expected edge (${edge.toFixed(2)}%). Operation not viable.`;
}

function getGuardianExplanation(guardian) {
  if (!guardian) return "Guardian status not available.";
  
  if (guardian.allowed) {
    return "All risk controls passed. Daily/weekly limits within parameters. Operation permitted.";
  }
  
  if (guardian.kill_switch_active) {
    return "Kill switch active. System blocked operations to protect capital after significant losses.";
  }
  
  return guardian.block_reason || "Operation blocked due to risk rule violation.";
}

// ---------- Main Component ----------
export default function GrowthModule() {
  const [loadingAll, setLoadingAll] = useState(false);
  const [errorAll, setErrorAll] = useState("");
  const [showTech, setShowTech] = useState(false);

  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [presetsMM, setPresetsMM] = useState([]);
  const [presetsMOM, setPresetsMOM] = useState([]);

  // Router
  const symbols = useMemo(() => ["BTC/USDT", "ETH/USDT", "BNB/USDT", "BTC/EUR", "ETH/EUR"], []);
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [routerResult, setRouterResult] = useState(null);
  const [routerError, setRouterError] = useState("");

  // Guardian
  const [guardianInput, setGuardianInput] = useState({
    agent_id: "test-agent",
    agent_type: "MM",
    symbol: "BTC/USDT",
    venue: "binance",
    side: "buy",
    amount_eur: 10,
    spread_pct: 0.03,
    estimated_slippage_pct: 0.02,
    data_age_seconds: 5,
    data_quality: 0.98,
    expected_edge_pct: 0.5,
    total_cost_pct: 0.1,
  });
  const [guardianResult, setGuardianResult] = useState(null);
  const [guardianError, setGuardianError] = useState("");

  // Viability
  const [viabilityInput, setViabilityInput] = useState({
    agent_type: "MM",
    preset_id: "MM_2_NORMAL_RANGE",
    symbol: "BTC/USDT",
    venue: "binance",
    order_size_eur: 10,
    expected_move_pct: 0.5,
    current_spread_pct: 0.03,
    bid_price: 94995,
    ask_price: 95005,
    expect_maker: true,
  });
  const [viabilityResult, setViabilityResult] = useState(null);
  const [viabilityError, setViabilityError] = useState("");

  // Run Once / Pipeline
  const [runOnceSymbol, setRunOnceSymbol] = useState("BTC/USDT");
  const [runOnceLoading, setRunOnceLoading] = useState(false);
  const [runOnceResult, setRunOnceResult] = useState(null);
  const [runOnceError, setRunOnceError] = useState("");
  const [lastRun, setLastRun] = useState(null);
  
  // Active Run View (P1 minimal UI)
  const [activeRun, setActiveRun] = useState(null);
  const [viewMode, setViewMode] = useState("dashboard"); // "dashboard" | "run"

  // Tabs navigation
  const [activeTab, setActiveTab] = useState("execucao"); // "execucao" | "config" | "dashboard" | "scheduler"
  
  // Scheduler state
  const [schedulerConfig, setSchedulerConfig] = useState(null);
  const [schedulerLoading, setSchedulerLoading] = useState(false);
  
  // Config/Preset editing state
  const [configSaving, setConfigSaving] = useState(false);
  const [editingPreset, setEditingPreset] = useState(null); // { preset, type: "MM" | "MOM" }
  const [presetSaving, setPresetSaving] = useState(false);

  // ---------- API Calls ----------
  async function refreshAll() {
    setLoadingAll(true);
    setErrorAll("");
    try {
      const [s, c, mm, mom] = await Promise.all([
        api.get("/growth/status"),
        api.get("/growth/config"),
        api.get("/growth/presets/mm"),
        api.get("/growth/presets/mom"),
      ]);
      setStatus(s.data);
      setConfig(c.data?.config || c.data);
      setPresetsMM(mm.data?.presets || mm.data?.items || mm.data || []);
      setPresetsMOM(mom.data?.presets || mom.data?.items || mom.data || []);
    } catch (e) {
      setErrorAll(e?.response?.data?.detail || e.message || "Error loading Growth Module.");
    } finally {
      setLoadingAll(false);
    }
  }

  async function runRouterAnalyze() {
    setRouterError("");
    setRouterResult(null);
    try {
      const metrics = {
        symbol,
        venue: "binance",
        last_price: 95000,
        bid: 94995,
        ask: 95005,
        spread_pct: 0.01,
        atr_pct: 0.8,
        atr_14: 760,
        bollinger_width_pct: 2.5,
        adx: 20,
        ma_slope_pct: 0.02,
        trend_direction: 0,
        volume_24h: 2000000000,
        volume_ratio: 1.0,
        data_age_seconds: 5,
        data_quality: 1.0,
      };
      const res = await api.post("/growth/router/analyze", { symbol, venue: "binance", metrics });
      setRouterResult(res.data?.decision || res.data);
    } catch (e) {
      setRouterError(e?.response?.data?.detail || e.message || "Erro no Router.");
    }
  }

  async function runGuardianValidate() {
    setGuardianError("");
    setGuardianResult(null);
    try {
      const res = await api.post("/growth/guardian/validate", guardianInput);
      setGuardianResult(res.data);
    } catch (e) {
      setGuardianError(e?.response?.data?.detail || e.message || "Erro no Guardian.");
    }
  }

  async function runViabilityCheck() {
    setViabilityError("");
    setViabilityResult(null);
    try {
      const res = await api.post("/growth/viability/check", viabilityInput);
      setViabilityResult(res.data);
    } catch (e) {
      setViabilityError(e?.response?.data?.detail || e.message || "Viability check error.");
    }
  }

  // Run Once - Execute full pipeline
  async function executeRunOnce(simulate = false) {
    setRunOnceLoading(true);
    setRunOnceError("");
    setRunOnceResult(null);
    try {
      const endpoint = simulate ? "/growth/run/simulate" : "/growth/run/once";
      const res = await api.post(endpoint, null, {
        params: { symbol: runOnceSymbol, venue: "auto" }
      });
      setRunOnceResult(res.data);
      // Auto-show RunView for new runs
      if (!res.data.is_replay) {
        setActiveRun(res.data);
        setViewMode("run");
      }
    } catch (e) {
      setRunOnceError(e?.response?.data?.detail || e.message || "Erro ao executar ciclo.");
    } finally {
      setRunOnceLoading(false);
    }
  }

  // Fetch last run
  async function fetchLastRun() {
    try {
      const res = await api.get("/growth/run/last");
      setLastRun(res.data);
      // Show last run on load if it was recent
      if (res.data && !activeRun) {
        setActiveRun(res.data);
      }
    } catch (e) {
      // No runs yet, ignore
    }
  }

  // Fetch scheduler config
  async function fetchSchedulerConfig() {
    try {
      const res = await api.get("/growth/schedule/config");
      setSchedulerConfig(res.data);
    } catch (e) {
      // Scheduler not configured yet, use defaults
      setSchedulerConfig({
        enabled: false,
        interval_minutes: 15,
        symbols: ["BTC/USDT"],
        active_hours_start: 8,
        active_hours_end: 22,
        active_days: [0, 1, 2, 3, 4],
      });
    }
  }

  // Update scheduler config
  async function updateSchedulerConfig(newConfig) {
    setSchedulerLoading(true);
    try {
      const res = await api.put("/growth/schedule/config", newConfig);
      setSchedulerConfig(res.data);
    } catch (e) {
      console.error("Failed to update scheduler:", e);
    } finally {
      setSchedulerLoading(false);
    }
  }

  // Save system config
  async function saveConfig(newConfig) {
    setConfigSaving(true);
    try {
      await api.put("/growth/config", newConfig);
      setConfig(newConfig);
    } catch (e) {
      console.error("Failed to save config:", e);
    } finally {
      setConfigSaving(false);
    }
  }

  // Save preset
  async function savePreset(editedPreset) {
    if (!editingPreset) return;
    setPresetSaving(true);
    try {
      const type = editingPreset.type.toLowerCase();
      const presetId = editedPreset.preset_id || editedPreset.id;
      await api.put(`/growth/presets/${type}/${presetId}`, editedPreset);
      // Refresh presets
      await refreshAll();
      setEditingPreset(null);
    } catch (e) {
      console.error("Failed to save preset:", e);
    } finally {
      setPresetSaving(false);
    }
  }

  useEffect(() => {
    refreshAll();
    fetchLastRun();
    fetchSchedulerConfig();
  }, []);

  // ---------- Derived State ----------
  const assisted = useMemo(() => {
    const servicesObj = status?.services || status?.initialized || {};
    const servicesOk = Object.keys(servicesObj).length > 0
      ? Object.values(servicesObj).every((x) => x === true || x?.ok === true || x?.initialized === true)
      : null;

    const operational = servicesOk !== false;
    const strategy = routerResult?.recommended_agent || routerResult?.selected_agent || "—";
    const risk = guardianResult?.allowed === false ? "BLOCKED" : "OK";

    let headline = "The system is operational and protecting your capital.";
    if (!operational) headline = "The system has operational limitations.";
    if (risk !== "OK") headline = "The system blocked operations to protect capital.";

    return { operational, strategy, risk, headline };
  }, [status, routerResult, guardianResult]);

  // ---------- Render ----------
  return (
    <div
      style={{
        background: THEME.bg.primary,
        borderRadius: 8,
        padding: 20,
        color: THEME.text.primary,
        fontFamily: FONT.family,
        minHeight: "100%",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: SPACING.sectionGap,
        }}
      >
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: FONT.size.h1,
              fontWeight: FONT.weight.title,
              color: THEME.text.primary,
              fontFamily: FONT.family,
            }}
          >
            Growth Module
          </h1>
          <p
            style={{
              margin: "8px 0 0",
              fontSize: FONT.size.small,
              color: THEME.text.secondary,
              fontFamily: FONT.family,
            }}
          >
            Assisted Mode — Professional Assistant + Technical Translation
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {activeRun && (
            <ButtonSecondary onClick={() => setViewMode(viewMode === "run" ? "dashboard" : "run")}>
              {viewMode === "run" ? "View Dashboard" : "View Last Run"}
            </ButtonSecondary>
          )}
          <ButtonSecondary onClick={() => setShowTech((v) => !v)}>
            {showTech ? "Hide Technical" : "View Technical"}
          </ButtonSecondary>
          <ButtonPrimary onClick={refreshAll} disabled={loadingAll}>
            {loadingAll ? "Loading..." : "Refresh"}
          </ButtonPrimary>
        </div>
      </div>

      {/* Error display */}
      {errorAll && (
        <Card title="Error" subtitle="Failed to load module" right={<Badge status="ERROR">ERROR</Badge>}>
          <div style={{ color: THEME.text.secondary, whiteSpace: "pre-wrap" }}>{String(errorAll)}</div>
        </Card>
      )}

      {/* ============================================================ */}
      {/* 🧭 RUN VIEW - Minimal P1 UI */}
      {/* ============================================================ */}
      {activeRun && viewMode === "run" && (
        <RunView 
          result={activeRun} 
          onClose={() => {
            setViewMode("dashboard");
          }}
        />
      )}

      {/* Quick Run Controls (always visible) */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: 16,
          background: THEME.bg.secondary,
          borderRadius: 8,
          border: `1px solid ${THEME.border.default}`,
          marginBottom: 20,
        }}
      >
        <Select
          value={runOnceSymbol}
          onChange={(e) => setRunOnceSymbol(e.target.value)}
          options={symbols.map((s) => ({ value: s, label: s }))}
        />
        <ButtonPrimary onClick={() => executeRunOnce(false)} disabled={runOnceLoading}>
          {runOnceLoading ? "Executing..." : "▶ Run Once"}
        </ButtonPrimary>
        <ButtonSecondary onClick={() => executeRunOnce(true)} disabled={runOnceLoading}>
          Simulate
        </ButtonSecondary>
        {runOnceError && (
          <span style={{ color: THEME.state.error, fontSize: FONT.size.small }}>{runOnceError}</span>
        )}
      </div>

      {/* ============================================================ */}
      {/* 🗂 TABS NAVIGATION */}
      {/* ============================================================ */}
      {viewMode !== "run" && (
        <div
          style={{
            display: "flex",
            gap: 4,
            marginBottom: 20,
            borderBottom: `1px solid ${THEME.border.default}`,
            paddingBottom: 4,
          }}
        >
          {[
            { id: "execucao", label: "Execution", icon: "▶" },
            { id: "dashboard", label: "Dashboard", icon: "📊" },
            { id: "config", label: "Config", icon: "⚙" },
            { id: "scheduler", label: "Scheduler", icon: "🕐" },
            { id: "golive", label: "GO-LIVE Gate", icon: "🔒" },
            { id: "backtest", label: "Backtest", icon: "📈" },
            { id: "audit", label: "Audit", icon: "📋" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "10px 20px",
                background: activeTab === tab.id ? THEME.bg.elevated : "transparent",
                border: "none",
                borderBottom: activeTab === tab.id ? `2px solid ${THEME.accent.primary}` : "2px solid transparent",
                color: activeTab === tab.id ? THEME.text.primary : THEME.text.secondary,
                fontSize: FONT.size.body,
                fontFamily: FONT.family,
                fontWeight: activeTab === tab.id ? FONT.weight.emphasis : FONT.weight.body,
                cursor: "pointer",
                borderRadius: "6px 6px 0 0",
                transition: "all 0.15s ease",
              }}
            >
              <span style={{ marginRight: 8 }}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Preset Editor Modal */}
      {editingPreset && (
        <PresetEditor
          preset={editingPreset.preset}
          type={editingPreset.type}
          onSave={savePreset}
          onClose={() => setEditingPreset(null)}
          loading={presetSaving}
        />
      )}

      {/* Show dashboard content only when not in run view */}
      {viewMode !== "run" && activeTab === "execucao" && (
        <>
      {/* Main Status Card */}
      <Card
        title="System Status"
        subtitle={assisted.headline}
        right={<Badge status={assisted.operational ? "OK" : "WARNING"}>{assisted.operational ? "Operational" : "Limited"}</Badge>}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          <Stat label="Active Strategy" value={assisted.strategy} />
          <Stat
            label="Current Risk"
            value={assisted.risk === "OK" ? "Controlled" : "Blocked"}
            color={getStateColor(assisted.risk)}
          />
          <Stat label="Modo" value="Paper Trading" />
          <Stat label="Interface" value="Assisted Mode" />
        </div>

        {showTech && (
          <>
            <SectionTitle>Technical Data</SectionTitle>
            <pre
              style={{
                background: THEME.bg.tertiary,
                border: `1px solid ${THEME.border.default}`,
                borderRadius: 6,
                padding: 12,
                color: THEME.text.secondary,
                overflowX: "auto",
                margin: 0,
                fontSize: FONT.size.small,
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {safeJson({ status, config, routerResult, guardianResult, viabilityResult })}
            </pre>
          </>
        )}
      </Card>

      {/* Services + Config */}
      <TwoCol
        left={
          <Card title="Services" subtitle="System components status">
            {status?.services || status?.initialized ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {Object.entries(status?.services || status?.initialized || {}).map(([k, v]) => {
                  const isOk = v === true || v?.ok === true || v?.initialized === true;
                  return (
                    <Badge key={k} status={isOk ? "OK" : "ERROR"}>
                      {k}: {isOk ? "OK" : "NOK"}
                    </Badge>
                  );
                })}
              </div>
            ) : (
              <div style={{ color: THEME.text.muted }}>No services data.</div>
            )}
          </Card>
        }
        right={
          <Card title="Configuration" subtitle="Current system configuration (read-only)">
            <pre
              style={{
                background: THEME.bg.tertiary,
                border: `1px solid ${THEME.border.default}`,
                borderRadius: 6,
                padding: 12,
                color: THEME.text.secondary,
                overflowX: "auto",
                margin: 0,
                maxHeight: 200,
                overflowY: "auto",
                fontSize: FONT.size.small,
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {safeJson(config)}
            </pre>
          </Card>
        }
      />

      {/* Budget State */}
      {status?.budget_state && (
        <Card title="Budget State" subtitle={`Total capital: ${status.budget_state.total_capital_eur}€`}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
            <Stat label="Total Capital" value={`${status.budget_state.total_capital_eur}€`} />
            <Stat
              label="Available"
              value={`${status.budget_state.available_capital_eur}€`}
              color={THEME.state.success}
            />
            <Stat label="In Use" value={`${status.budget_state.deployed_capital_eur}€`} />
            <Stat
              label="Multi-Agent"
              value={status.budget_state.allow_multi_agent ? "Yes" : "No"}
              color={status.budget_state.allow_multi_agent ? THEME.state.success : THEME.state.warning}
            />
          </div>
          {status.budget_state.buckets && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {Object.entries(status.budget_state.buckets).map(([k, b]) => (
                <div
                  key={k}
                  style={{
                    flex: "1 1 150px",
                    background: THEME.bg.tertiary,
                    borderRadius: 6,
                    padding: 12,
                    border: `1px solid ${THEME.border.default}`,
                  }}
                >
                  <div style={{ color: THEME.text.muted, fontSize: FONT.size.small, textTransform: "uppercase" }}>
                    {k}
                  </div>
                  <div style={{ fontWeight: FONT.weight.title, marginTop: 4 }}>
                    {b.available_eur}€ / {b.allocated_pct}%
                  </div>
                  <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>
                    Max trade: {b.max_single_trade_eur}€
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Presets */}
      <TwoCol
        left={
          <Card title="Presets — Market Maker" subtitle="Pre-defined configurations">
            {Array.isArray(presetsMM) && presetsMM.length ? (
              presetsMM.map((p) => (
                <div
                  key={p.preset_id || p.id}
                  style={{ padding: "12px 0", borderBottom: `1px solid ${THEME.border.default}` }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div>
                      <div style={{ fontWeight: FONT.weight.emphasis }}>{p.preset_id || p.id}</div>
                      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 4 }}>
                        {p.description || p.name || "No description."}
                      </div>
                    </div>
                    <Badge status={p.enabled === false ? "WARNING" : "OK"}>
                      {p.enabled === false ? "Inactive" : "Active"}
                    </Badge>
                  </div>
                  {showTech && (
                    <pre
                      style={{
                        color: THEME.text.muted,
                        fontSize: FONT.size.small,
                        marginTop: 8,
                        overflowX: "auto",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      {safeJson(p)}
                    </pre>
                  )}
                </div>
              ))
            ) : (
              <div style={{ color: THEME.text.muted }}>No MM presets.</div>
            )}
          </Card>
        }
        right={
          <Card title="Presets — Momentum" subtitle="Pre-defined configurations">
            {Array.isArray(presetsMOM) && presetsMOM.length ? (
              presetsMOM.map((p) => (
                <div
                  key={p.preset_id || p.id}
                  style={{ padding: "12px 0", borderBottom: `1px solid ${THEME.border.default}` }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div>
                      <div style={{ fontWeight: FONT.weight.emphasis }}>{p.preset_id || p.id}</div>
                      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 4 }}>
                        {p.description || p.name || "No description."}
                      </div>
                    </div>
                    <Badge status={p.enabled === false ? "WARNING" : "OK"}>
                      {p.enabled === false ? "Inactive" : "Active"}
                    </Badge>
                  </div>
                  {showTech && (
                    <pre
                      style={{
                        color: THEME.text.muted,
                        fontSize: FONT.size.small,
                        marginTop: 8,
                        overflowX: "auto",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      {safeJson(p)}
                    </pre>
                  )}
                </div>
              ))
            ) : (
              <div style={{ color: THEME.text.muted }}>No MOM presets.</div>
            )}
          </Card>
        }
      />

      {/* Router + Guardian/Viability */}
      <TwoCol
        left={
          <Card
            title="Router — Market Analysis"
            subtitle="Decisão automática com explicação"
            right={
              <Select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                options={symbols.map((s) => ({ value: s, label: s }))}
              />
            }
          >
            <div style={{ marginBottom: 16 }}>
              <ButtonPrimary onClick={runRouterAnalyze}>Analyze</ButtonPrimary>
            </div>

            {routerError && (
              <div style={{ color: THEME.state.error, marginBottom: 12 }}>{routerError}</div>
            )}

            {routerResult && (
              <div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                  <Badge status="OK">
                    Agent: {routerResult.recommended_agent || routerResult.selected_agent}
                  </Badge>
                  <Badge status="INFO">
                    Set: {routerResult.recommended_preset_id || routerResult.selected_set_id || "—"}
                  </Badge>
                  <Badge status="WARNING">
                    Confidence: {routerResult.regime_confidence || routerResult.confidence || "—"}
                  </Badge>
                  <Badge status="INFO">
                    Regime: {routerResult.regime || "—"}
                  </Badge>
                </div>

                <SectionTitle>Explanation</SectionTitle>
                <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small }}>
                  {(routerResult.all_reason_codes || routerResult.regime_reasons || routerResult.reason_codes || [])
                    .slice(0, 4)
                    .map((r, idx) => {
                      const mapped = typeof r === "string" ? mapReasons([r])[0] : { code: r, title: r, detail: "" };
                      return (
                        <div key={mapped.code + idx} style={{ marginBottom: 8 }}>
                          <div style={{ color: THEME.text.primary, fontWeight: FONT.weight.emphasis }}>
                            {mapped.title}
                          </div>
                          {showTech && (
                            <div style={{ marginTop: 2, color: THEME.text.muted }}>
                              {mapped.detail} ({mapped.code})
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>

                {showTech && (
                  <>
                    <SectionTitle>Resposta técnica</SectionTitle>
                    <pre
                      style={{
                        color: THEME.text.muted,
                        fontSize: FONT.size.small,
                        overflowX: "auto",
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      {safeJson(routerResult)}
                    </pre>
                  </>
                )}
              </div>
            )}
          </Card>
        }
        right={
          <Card title="Guardian + Viability" subtitle="Security validations">
            {/* Guardian Section */}
            <SectionTitle>Guardian — Risk Validation</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <Input
                value={guardianInput.amount_eur}
                onChange={(e) => setGuardianInput((x) => ({ ...x, amount_eur: Number(e.target.value) }))}
                placeholder="Posição €"
                type="number"
              />
              <Input
                value={guardianInput.spread_pct}
                onChange={(e) => setGuardianInput((x) => ({ ...x, spread_pct: Number(e.target.value) }))}
                placeholder="Spread %"
                type="number"
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <ButtonPrimary onClick={runGuardianValidate}>Validate Risk</ButtonPrimary>
            </div>

            {guardianError && (
              <div style={{ color: THEME.state.error, marginBottom: 12 }}>{guardianError}</div>
            )}

            {guardianResult && (
              <div style={{ marginBottom: 20 }}>
                <Badge status={guardianResult.allowed ? "OK" : "BLOCKED"}>
                  {guardianResult.allowed ? "Allowed" : "Blocked"}
                </Badge>

                <div style={{ marginTop: 12, color: THEME.text.secondary, fontSize: FONT.size.small }}>
                  {(guardianResult.reasons || []).slice(0, 4).map((r, idx) => {
                    const mapped = typeof r === "string" ? { code: r, title: r, detail: "" } : r;
                    return (
                      <div key={idx} style={{ marginBottom: 6 }}>
                        <div style={{ color: THEME.text.primary, fontWeight: FONT.weight.emphasis }}>
                          {mapped.title || mapped}
                        </div>
                        {showTech && mapped.detail && (
                          <div style={{ marginTop: 2, color: THEME.text.muted }}>{mapped.detail}</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {showTech && (
                  <pre
                    style={{
                      color: THEME.text.muted,
                      fontSize: FONT.size.small,
                      overflowX: "auto",
                      marginTop: 8,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {safeJson(guardianResult)}
                  </pre>
                )}
              </div>
            )}

            {/* Viability Section */}
            <SectionTitle>Viability — Cost Analysis</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <Input
                value={viabilityInput.expected_move_pct}
                onChange={(e) => setViabilityInput((x) => ({ ...x, expected_move_pct: Number(e.target.value) }))}
                placeholder="Edge %"
                type="number"
              />
              <Input
                value={viabilityInput.order_size_eur}
                onChange={(e) => setViabilityInput((x) => ({ ...x, order_size_eur: Number(e.target.value) }))}
                placeholder="Tamanho €"
                type="number"
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <ButtonPrimary onClick={runViabilityCheck}>Check Viability</ButtonPrimary>
            </div>

            {viabilityError && (
              <div style={{ color: THEME.state.error, marginBottom: 12 }}>{viabilityError}</div>
            )}

            {viabilityResult && (
              <div>
                <Badge status={getViabilityBadgeStatus(viabilityResult.status, viabilityResult.viable)}>
                  {translateViabilityStatus(viabilityResult.status, viabilityResult.viable)}
                </Badge>

                <div style={{ marginTop: 12, color: THEME.text.secondary, fontSize: FONT.size.small }}>
                  {(viabilityResult.reasons || []).slice(0, 4).map((r, idx) => {
                    const mapped = typeof r === "string" ? { code: r, title: r, detail: "" } : r;
                    return (
                      <div key={idx} style={{ marginBottom: 6 }}>
                        <div style={{ color: THEME.text.primary, fontWeight: FONT.weight.emphasis }}>
                          {mapped.title || mapped}
                        </div>
                        {showTech && mapped.detail && (
                          <div style={{ marginTop: 2, color: THEME.text.muted }}>{mapped.detail}</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {showTech && (
                  <pre
                    style={{
                      color: THEME.text.muted,
                      fontSize: FONT.size.small,
                      overflowX: "auto",
                      marginTop: 8,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    {safeJson(viabilityResult)}
                  </pre>
                )}
              </div>
            )}
          </Card>
        }
      />

      {/* Pipeline Execution Section */}
      <Card
        title="Pipeline Execution"
        subtitle="Complete paper trading cycle"
      >
        {/* Pipeline Visual */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {[
              { step: "Start", status: runOnceResult ? "done" : "pending" },
              { step: "Config", status: runOnceResult ? "done" : "pending" },
              { step: "Snapshot", status: runOnceResult ? "done" : "pending" },
              { step: "Router", status: runOnceResult?.router_decision ? "done" : "pending" },
              { step: "Intent", status: runOnceResult?.intent_plan ? "done" : "pending" },
              { step: "Viability", status: runOnceResult?.viability_check ? (runOnceResult.viability_viable ? "done" : "blocked") : "pending" },
              { step: "Guardian", status: runOnceResult?.guardian_check ? (runOnceResult.guardian_allowed ? "done" : "blocked") : "pending" },
              { step: "Execute", status: runOnceResult?.orders_created > 0 ? "done" : (runOnceResult?.status === "blocked" || runOnceResult?.status === "paused" ? "blocked" : "pending") },
              { step: "Audit", status: runOnceResult?.cycle_id ? "done" : "pending" },
              { step: "End", status: runOnceResult ? "done" : "pending" },
            ].map((item, idx, arr) => (
              <React.Fragment key={item.step}>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "50%",
                      border: `2px solid ${
                        item.status === "done" ? THEME.state.success :
                        item.status === "blocked" ? THEME.state.error :
                        THEME.border.strong
                      }`,
                      background: item.status === "done" ? THEME.state.success + "20" : "transparent",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 10,
                      fontWeight: FONT.weight.emphasis,
                      color: item.status === "done" ? THEME.state.success :
                             item.status === "blocked" ? THEME.state.error :
                             THEME.text.muted,
                    }}
                  >
                    {item.status === "done" ? "✓" : item.status === "blocked" ? "✗" : idx + 1}
                  </div>
                  <div style={{ fontSize: 10, color: THEME.text.muted }}>{item.step}</div>
                </div>
                {idx < arr.length - 1 && (
                  <div
                    style={{
                      width: 20,
                      height: 2,
                      background: item.status === "done" ? THEME.state.success : THEME.border.default,
                      marginBottom: 16,
                    }}
                  />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <Select
            value={runOnceSymbol}
            onChange={(e) => setRunOnceSymbol(e.target.value)}
            options={symbols.map((s) => ({ value: s, label: s }))}
          />
          <ButtonPrimary onClick={() => executeRunOnce(false)} disabled={runOnceLoading}>
            {runOnceLoading ? "Executing..." : "Run Once"}
          </ButtonPrimary>
          <ButtonSecondary onClick={() => executeRunOnce(true)} disabled={runOnceLoading}>
            Simulate (Dry Run)
          </ButtonSecondary>
          <ButtonSecondary onClick={fetchLastRun}>
            Last Execution
          </ButtonSecondary>
        </div>

        {runOnceError && (
          <div style={{ color: THEME.state.error, marginBottom: 12 }}>{runOnceError}</div>
        )}

        {/* Result Display */}
        {runOnceResult && (
          <div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
              <Badge status={runOnceResult.status === "success" ? "OK" : runOnceResult.status === "dry_run" ? "INFO" : "BLOCKED"}>
                Status: {runOnceResult.status}
              </Badge>
              <Badge status="INFO">
                Cycle: {runOnceResult.cycle_id}
              </Badge>
              <Badge status={runOnceResult.recommended_agent === "PAUSE" ? "WARNING" : "OK"}>
                Agent: {runOnceResult.recommended_agent || "—"}
              </Badge>
              <Badge status="INFO">
                Regime: {runOnceResult.regime || "—"}
              </Badge>
              <Badge status={runOnceResult.orders_created > 0 ? "OK" : "WARNING"}>
                Orders: {runOnceResult.orders_created || 0}
              </Badge>
            </div>

            {runOnceResult.block_reason && (
              <div style={{ 
                padding: 12, 
                background: THEME.state.error + "10", 
                border: `1px solid ${THEME.state.error}`,
                borderRadius: 6,
                marginBottom: 12,
              }}>
                <div style={{ color: THEME.state.error, fontWeight: FONT.weight.emphasis }}>
                  Blocked: {runOnceResult.block_reason}
                </div>
              </div>
            )}

            <SectionTitle>Execution Summary</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
              <Stat label="Symbol" value={runOnceResult.symbol} />
              <Stat label="Confidence" value={runOnceResult.confidence || "—"} />
              <Stat label="Preset" value={runOnceResult.recommended_preset_id || "—"} />
              <Stat 
                label="PnL Delta" 
                value={`${runOnceResult.pnl_delta_eur?.toFixed(2) || 0}€`}
                color={runOnceResult.pnl_delta_eur > 0 ? THEME.state.success : runOnceResult.pnl_delta_eur < 0 ? THEME.state.error : THEME.text.primary}
              />
            </div>

            {runOnceResult.reason_codes && runOnceResult.reason_codes.length > 0 && (
              <>
                <SectionTitle>Reasons</SectionTitle>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {runOnceResult.reason_codes.slice(0, 8).map((code, idx) => (
                    <Badge key={idx} status="INFO">{code}</Badge>
                  ))}
                </div>
              </>
            )}

            {showTech && (
              <>
                <SectionTitle>Cycle Technical Data</SectionTitle>
                <pre
                  style={{
                    background: THEME.bg.tertiary,
                    border: `1px solid ${THEME.border.default}`,
                    borderRadius: 6,
                    padding: 12,
                    color: THEME.text.secondary,
                    overflowX: "auto",
                    margin: 0,
                    fontSize: FONT.size.small,
                    fontFamily: "'JetBrains Mono', monospace",
                    maxHeight: 300,
                    overflowY: "auto",
                  }}
                >
                  {safeJson(runOnceResult)}
                </pre>
              </>
            )}
          </div>
        )}

        {/* Last Run Display */}
        {lastRun && !runOnceResult && (
          <div style={{ borderTop: `1px solid ${THEME.border.default}`, paddingTop: 16, marginTop: 16 }}>
            <SectionTitle>Last Execution</SectionTitle>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              <Badge status={lastRun.status === "success" ? "OK" : "BLOCKED"}>
                {lastRun.status}
              </Badge>
              <Badge status="INFO">
                {lastRun.cycle_id}
              </Badge>
              <Badge status="INFO">
                {lastRun.recommended_agent || "—"}
              </Badge>
            </div>
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>
              Symbol: {lastRun.symbol} | Regime: {lastRun.regime} | Orders: {lastRun.orders_created || 0}
            </div>
          </div>
        )}
      </Card>
      </>
      )}

      {/* ============================================================ */}
      {/* 📊 DASHBOARD TAB - Real-time data */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "dashboard" && (
        <div>
          <Card title="Real-Time Dashboard" subtitle="Track PnL, orders and system status">
            <RealTimeDashboard 
              wsUrl={`${process.env.REACT_APP_BACKEND_URL?.replace('https://', 'wss://').replace('http://', 'ws://')}/api/ws/growth`}
            />
          </Card>
          
          {/* Quick Stats from last run */}
          {lastRun && (
            <Card title="Last Execution" subtitle={`Cycle: ${lastRun.cycle_id || "—"}`}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
                <Stat label="Symbol" value={lastRun.symbol || "—"} />
                <Stat label="Regime" value={lastRun.regime || "—"} />
                <Stat label="Agent" value={lastRun.recommended_agent || "—"} />
                <Stat 
                  label="Orders" 
                  value={lastRun.orders_created || 0}
                  color={lastRun.orders_created > 0 ? THEME.state.success : THEME.text.primary}
                />
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ============================================================ */}
      {/* ⚙ CONFIG TAB - System config and presets */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "config" && (
        <div>
          {/* System Config Editor */}
          <ConfigEditor 
            config={config} 
            onSave={saveConfig} 
            loading={configSaving}
          />
          
          {/* MM Presets */}
          <Card 
            title="Presets — Market Maker" 
            subtitle="Clique num preset para editar"
            right={<Badge status="INFO">{presetsMM.length} presets</Badge>}
          >
            {Array.isArray(presetsMM) && presetsMM.length ? (
              presetsMM.map((p) => (
                <div
                  key={p.preset_id || p.id}
                  onClick={() => setEditingPreset({ preset: p, type: "MM" })}
                  style={{ 
                    padding: "12px 0", 
                    borderBottom: `1px solid ${THEME.border.default}`,
                    cursor: "pointer",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = THEME.bg.elevated}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div>
                      <div style={{ fontWeight: FONT.weight.emphasis }}>{p.preset_id || p.id}</div>
                      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 4 }}>
                        {p.description || p.name || "No description."}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Badge status={p.enabled === false ? "WARNING" : "OK"}>
                        {p.enabled === false ? "Inactive" : "Active"}
                      </Badge>
                      <span style={{ color: THEME.accent.primary, fontSize: FONT.size.small }}>Editar →</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ color: THEME.text.muted }}>No MM presets.</div>
            )}
          </Card>

          {/* MOM Presets */}
          <Card 
            title="Presets — Momentum" 
            subtitle="Clique num preset para editar"
            right={<Badge status="INFO">{presetsMOM.length} presets</Badge>}
          >
            {Array.isArray(presetsMOM) && presetsMOM.length ? (
              presetsMOM.map((p) => (
                <div
                  key={p.preset_id || p.id}
                  onClick={() => setEditingPreset({ preset: p, type: "MOM" })}
                  style={{ 
                    padding: "12px 0", 
                    borderBottom: `1px solid ${THEME.border.default}`,
                    cursor: "pointer",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = THEME.bg.elevated}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    <div>
                      <div style={{ fontWeight: FONT.weight.emphasis }}>{p.preset_id || p.id}</div>
                      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginTop: 4 }}>
                        {p.description || p.name || "No description."}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Badge status={p.enabled === false ? "WARNING" : "OK"}>
                        {p.enabled === false ? "Inactive" : "Active"}
                      </Badge>
                      <span style={{ color: THEME.accent.primary, fontSize: FONT.size.small }}>Editar →</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ color: THEME.text.muted }}>No MOM presets.</div>
            )}
          </Card>
        </div>
      )}

      {/* ============================================================ */}
      {/* 🕐 SCHEDULER TAB - Automated execution config */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "scheduler" && (
        <div>
          <SchedulerPanel 
            scheduler={schedulerConfig}
            onUpdate={updateSchedulerConfig}
            loading={schedulerLoading}
          />
          
          {/* Scheduler Info */}
          <Card title="Sobre o Agendador" subtitle="Como funciona a execução automática">
            <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, lineHeight: 1.6 }}>
              <p style={{ marginBottom: 12 }}>
                O agendador automático executa ciclos de paper trading nos intervalos definidos.
                Cada ciclo analisa o mercado, seleciona a estratégia adequada (MM ou MOM), e executa ordens simuladas.
              </p>
              <p style={{ marginBottom: 12 }}>
                <strong style={{ color: THEME.text.primary }}>Symbols:</strong> Pode selecionar múltiplos símbolos para executar em paralelo.
              </p>
              <p style={{ marginBottom: 12 }}>
                <strong style={{ color: THEME.text.primary }}>Horário Activo:</strong> O scheduler só executa durante o horário definido (UTC).
                Fora deste horário, o sistema permanece em pausa.
              </p>
              <p style={{ margin: 0 }}>
                <strong style={{ color: THEME.text.primary }}>Protecção:</strong> O Guardian continua activo durante execuções automáticas,
                bloqueando operações se os limites de risco forem atingidos.
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* ============================================================ */}
      {/* 🔒 GO-LIVE GATE TAB - Capital preservation gate */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "golive" && (
        <GoLiveGate />
      )}

      {/* ============================================================ */}
      {/* 📈 BACKTEST TAB - Strategy backtesting / replay */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "backtest" && (
        <BacktestPanel />
      )}

      {/* ============================================================ */}
      {/* 📋 AUDIT TAB - System audit logs and security events */}
      {/* ============================================================ */}
      {viewMode !== "run" && activeTab === "audit" && (
        <AuditDashboard />
      )}
    </div>
  );
}
