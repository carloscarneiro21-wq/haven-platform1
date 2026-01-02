/**
 * GO-LIVE GATE Component
 * ======================
 * 
 * Displays the GO-LIVE Gate status and allows running evaluations.
 * 
 * HAVEN Design System - "Built to Survive Markets"
 * This component provides a clear visual representation of:
 * - Current gate status (GO / NO-GO)
 * - All evaluation criteria and their status
 * - Recommendations and constraints
 * - Historical evaluations
 */

import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../App";

// ============================================================
// 🎨 HAVEN DESIGN SYSTEM (Binance-inspired)
// ============================================================

const THEME = {
  bg: {
    primary: "#0B0E11",
    secondary: "#161A1E",
    card: "#1E2329",
    elevated: "#252A31",
    hover: "#2B3139",
    danger: "#1E2329",
    success: "#1E2329",
  },
  border: {
    default: "rgba(255, 255, 255, 0.08)",
    light: "rgba(255, 255, 255, 0.12)",
    danger: "rgba(246, 70, 93, 0.3)",
    success: "rgba(14, 203, 129, 0.3)",
  },
  text: {
    primary: "#EAECEF",
    secondary: "#B7BDC6",
    muted: "#848E9C",
    inverse: "#0B0E11",
  },
  state: {
    success: "#0ECB81",
    warning: "#F0B90B",
    error: "#F6465D",
    info: "#1E90FF",
  },
  accent: {
    primary: "#F0B90B",
    secondary: "#1E90FF",
  },
};

const FONT = {
  family: "'Inter', system-ui, -apple-system, sans-serif",
  size: {
    heading: "20px",
    body: "14px",
    small: "12px",
    tiny: "11px",
  },
  weight: {
    heading: 600,
    emphasis: 500,
    body: 400,
  },
};

// ============================================================
// 🧱 BASE COMPONENTS
// ============================================================

const Card = ({ title, subtitle, children, status, right }) => (
  <div
    style={{
      background: THEME.bg.card,
      border: `1px solid ${status === "GO" ? THEME.border.success : status === "NO_GO" ? THEME.border.danger : THEME.border.default}`,
      borderRadius: 6,
      padding: 20,
      marginBottom: 16,
    }}
  >
    {(title || right) && (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: subtitle ? 4 : 12 }}>
        <h3 style={{ margin: 0, fontSize: FONT.size.heading, fontWeight: FONT.weight.heading, color: THEME.text.primary }}>
          {title}
        </h3>
        {right}
      </div>
    )}
    {subtitle && (
      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, marginBottom: 16 }}>
        {subtitle}
      </div>
    )}
    {children}
  </div>
);

const Badge = ({ status, children }) => {
  const colors = {
    GO: { bg: "#4CAF5020", border: "#4CAF5050", text: "#4CAF50" },
    NO_GO: { bg: "#D32F2F20", border: "#D32F2F50", text: "#D32F2F" },
    PASSED: { bg: "#4CAF5020", border: "#4CAF5050", text: "#4CAF50" },
    FAILED: { bg: "#D32F2F20", border: "#D32F2F50", text: "#D32F2F" },
    WARNING: { bg: "#FFC10720", border: "#FFC10750", text: "#FFC107" },
    INSUFFICIENT_DATA: { bg: "#64B5F620", border: "#64B5F650", text: "#64B5F6" },
    INFO: { bg: "#64B5F620", border: "#64B5F650", text: "#64B5F6" },
    OK: { bg: "#4CAF5020", border: "#4CAF5050", text: "#4CAF50" },
  };
  const c = colors[status] || colors.INFO;
  
  return (
    <span
      style={{
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: 4,
        fontSize: FONT.size.small,
        fontWeight: FONT.weight.emphasis,
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.text,
      }}
    >
      {children}
    </span>
  );
};

const ButtonPrimary = ({ onClick, disabled, children }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    style={{
      padding: "10px 20px",
      background: disabled ? THEME.bg.hover : THEME.accent.primary,
      color: disabled ? THEME.text.muted : THEME.text.inverse,
      border: "none",
      borderRadius: 6,
      fontSize: FONT.size.body,
      fontWeight: FONT.weight.emphasis,
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.6 : 1,
      fontFamily: FONT.family,
      transition: "background 0.15s ease",
    }}
  >
    {children}
  </button>
);

const Stat = ({ label, value, color }) => (
  <div style={{ textAlign: "center" }}>
    <div style={{ fontSize: FONT.size.small, color: THEME.text.muted, marginBottom: 4 }}>{label}</div>
    <div style={{ fontSize: "24px", fontWeight: FONT.weight.heading, color: color || THEME.text.primary }}>{value}</div>
  </div>
);

// ============================================================
// 🎯 CRITERION ROW COMPONENT
// ============================================================

const CriterionRow = ({ criterion }) => {
  const [expanded, setExpanded] = useState(false);
  
  const statusIcon = {
    PASSED: "✓",
    FAILED: "✗",
    WARNING: "⚠",
    INSUFFICIENT_DATA: "?",
  };
  
  const statusColor = {
    PASSED: THEME.state.success,
    FAILED: THEME.state.error,
    WARNING: THEME.state.warning,
    INSUFFICIENT_DATA: THEME.state.info,
  };
  
  return (
    <div
      style={{
        borderBottom: `1px solid ${THEME.border.default}`,
        padding: "12px 0",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              width: 24,
              height: 24,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: FONT.size.body,
              fontWeight: FONT.weight.emphasis,
              background: `${statusColor[criterion.status]}20`,
              color: statusColor[criterion.status],
            }}
          >
            {statusIcon[criterion.status]}
          </span>
          <div>
            <div style={{ fontWeight: FONT.weight.emphasis, color: THEME.text.primary }}>
              [{criterion.criterion_id}] {criterion.name}
            </div>
            <div style={{ fontSize: FONT.size.small, color: THEME.text.secondary }}>
              {criterion.message}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Badge status={criterion.status}>{criterion.status}</Badge>
          {criterion.is_critical && (
            <span style={{ color: THEME.state.error, fontSize: FONT.size.tiny }}>CRITICAL</span>
          )}
          <span style={{ color: THEME.text.muted }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </div>
      
      {expanded && (
        <div
          style={{
            marginTop: 12,
            marginLeft: 36,
            padding: 12,
            background: THEME.bg.elevated,
            borderRadius: 6,
            fontSize: FONT.size.small,
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <span style={{ color: THEME.text.muted }}>Category:</span>{" "}
              <span style={{ color: THEME.text.primary }}>{criterion.category}</span>
            </div>
            <div>
              <span style={{ color: THEME.text.muted }}>Actual Value:</span>{" "}
              <span style={{ color: THEME.text.primary }}>{String(criterion.actual_value)}</span>
            </div>
            <div>
              <span style={{ color: THEME.text.muted }}>Required Value:</span>{" "}
              <span style={{ color: THEME.text.primary }}>{String(criterion.required_value)}</span>
            </div>
            <div>
              <span style={{ color: THEME.text.muted }}>Comparison:</span>{" "}
              <span style={{ color: THEME.text.primary }}>{criterion.comparison || "—"}</span>
            </div>
          </div>
          {criterion.recommendation && (
            <div style={{ marginTop: 12, padding: 8, background: THEME.bg.secondary, borderRadius: 4 }}>
              <div style={{ color: THEME.text.muted, marginBottom: 4 }}>Recommendation:</div>
              <div style={{ color: THEME.state.info }}>{criterion.recommendation}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================
// 🏛️ MAIN COMPONENT
// ============================================================

export function GoLiveGate() {
  const [status, setStatus] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  
  // Fetch current status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get("/go-live/status");
      setStatus(res.data);
    } catch (e) {
      console.error("Failed to fetch GO-LIVE status:", e);
    }
  }, []);
  
  // Fetch metrics
  const fetchMetrics = useCallback(async () => {
    try {
      const res = await api.get("/go-live/metrics");
      setMetrics(res.data);
    } catch (e) {
      console.error("Failed to fetch metrics:", e);
    }
  }, []);
  
  // Fetch history
  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get("/go-live/history?limit=5");
      setHistory(res.data);
    } catch (e) {
      console.error("Failed to fetch history:", e);
    }
  }, []);
  
  // Run evaluation
  const runEvaluation = async () => {
    setEvaluating(true);
    setError(null);
    
    try {
      const res = await api.post("/go-live/evaluate");
      setEvaluation(res.data);
      setStatus({
        decision: res.data.decision,
        timestamp: res.data.timestamp,
        evaluation_id: res.data.evaluation_id,
        criteria_passed: res.data.criteria_passed,
        criteria_failed: res.data.criteria_failed,
        recommendation: res.data.recommendation,
        risk_summary: res.data.risk_summary,
        constraints: res.data.constraints,
      });
      await fetchHistory();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to run evaluation");
    } finally {
      setEvaluating(false);
    }
  };
  
  // Initial load
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchStatus(), fetchMetrics(), fetchHistory()]);
      setLoading(false);
    };
    load();
  }, [fetchStatus, fetchMetrics, fetchHistory]);
  
  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: THEME.text.muted }}>
        Loading GO-LIVE Gate...
      </div>
    );
  }
  
  return (
    <div style={{ fontFamily: FONT.family }}>
      {/* ============================================================ */}
      {/* 🎯 GATE STATUS HEADER */}
      {/* ============================================================ */}
      <Card
        title="🔒 GO-LIVE GATE"
        subtitle="Objective determination of LIVE execution permission"
        status={status?.decision}
        right={
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <ButtonPrimary onClick={runEvaluation} disabled={evaluating}>
              {evaluating ? "Evaluating..." : "Run Evaluation"}
            </ButtonPrimary>
          </div>
        }
      >
        {/* Main Decision Display */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            background: status?.decision === "GO" ? `${THEME.state.success}15` : `${THEME.state.error}15`,
            borderRadius: 6,
            marginBottom: 16,
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: "64px",
                fontWeight: FONT.weight.heading,
                color: status?.decision === "GO" ? THEME.state.success : THEME.state.error,
                marginBottom: 8,
              }}
            >
              {status?.decision === "GO" ? "🟢 GO" : "🔴 NO-GO"}
            </div>
            <div style={{ fontSize: FONT.size.body, color: THEME.text.secondary, maxWidth: 500 }}>
              {status?.risk_summary || "No evaluation performed yet."}
            </div>
            {status?.timestamp && (
              <div style={{ fontSize: FONT.size.tiny, color: THEME.text.muted, marginTop: 8 }}>
                Last evaluation: {new Date(status.timestamp).toLocaleString("en-GB")}
              </div>
            )}
          </div>
        </div>
        
        {/* Stats */}
        {status && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
            <Stat label="Criteria Evaluated" value={status.criteria_passed + status.criteria_failed} />
            <Stat label="Passed" value={status.criteria_passed} color={THEME.state.success} />
            <Stat label="Failed" value={status.criteria_failed} color={THEME.state.error} />
            <Stat label="Evaluation ID" value={status.evaluation_id?.slice(0, 8) || "—"} />
          </div>
        )}
        
        {error && (
          <div style={{ marginTop: 16, padding: 12, background: `${THEME.state.error}20`, borderRadius: 6, color: THEME.state.error }}>
            {error}
          </div>
        )}
      </Card>
      
      {/* ============================================================ */}
      {/* 📋 RECOMMENDATION */}
      {/* ============================================================ */}
      {status?.recommendation && (
        <Card title="📋 Recommendation" subtitle="Recommended action based on evaluation">
          <pre
            style={{
              margin: 0,
              padding: 16,
              background: THEME.bg.elevated,
              borderRadius: 6,
              fontSize: FONT.size.small,
              color: THEME.text.primary,
              whiteSpace: "pre-wrap",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {status.recommendation}
          </pre>
        </Card>
      )}
      
      {/* ============================================================ */}
      {/* 🔒 CONSTRAINTS (if GO) */}
      {/* ============================================================ */}
      {status?.decision === "GO" && status?.constraints && (
        <Card title="🔒 LIVE Constraints" subtitle="LIVE is permitted only under these conditions">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Max Capital</div>
              <div style={{ fontSize: "20px", fontWeight: FONT.weight.emphasis }}>€{status.constraints.max_capital_eur}</div>
            </div>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Max Single Trade</div>
              <div style={{ fontSize: "20px", fontWeight: FONT.weight.emphasis }}>€{status.constraints.max_single_trade_eur}</div>
            </div>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Allowed Symbols</div>
              <div style={{ fontSize: FONT.size.body, fontWeight: FONT.weight.emphasis }}>
                {status.constraints.allowed_symbols?.join(", ") || "BTC/USDT"}
              </div>
            </div>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Daily Loss Limit</div>
              <div style={{ fontSize: "20px", fontWeight: FONT.weight.emphasis, color: THEME.state.error }}>
                {status.constraints.daily_loss_limit_pct}%
              </div>
            </div>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Trading Hours (UTC)</div>
              <div style={{ fontSize: FONT.size.body, fontWeight: FONT.weight.emphasis }}>
                {status.constraints.allowed_hours_utc_start}:00 - {status.constraints.allowed_hours_utc_end}:00
              </div>
            </div>
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.small }}>Guardian Mode</div>
              <div style={{ fontSize: FONT.size.body, fontWeight: FONT.weight.emphasis }}>
                {status.constraints.guardian_mode || "STRICT"}
              </div>
            </div>
          </div>
        </Card>
      )}
      
      {/* ============================================================ */}
      {/* ✅ CRITERIA DETAILS */}
      {/* ============================================================ */}
      {evaluation?.criteria_results && evaluation.criteria_results.length > 0 && (
        <Card
          title="✅ Evaluation Criteria"
          subtitle="Details of each evaluated criterion"
          right={<Badge status="INFO">{evaluation.criteria_results.length} criteria</Badge>}
        >
          {evaluation.criteria_results.map((c, i) => (
            <CriterionRow key={i} criterion={c} />
          ))}
        </Card>
      )}
      
      {/* ============================================================ */}
      {/* 📊 CURRENT METRICS */}
      {/* ============================================================ */}
      {metrics && (
        <Card title="📊 Current Metrics" subtitle="System data used in evaluation">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
            {/* Operational History */}
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ fontWeight: FONT.weight.emphasis, marginBottom: 8 }}>Operational History</div>
              <div style={{ display: "grid", gap: 4, fontSize: FONT.size.small }}>
                <div><span style={{ color: THEME.text.muted }}>Paper Runs:</span> {metrics.operational_history?.total_paper_runs || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Blocked Runs:</span> {metrics.operational_history?.total_runs_blocked_by_guardian || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Observation Days:</span> {metrics.operational_history?.observation_days || 0}</div>
              </div>
            </div>
            
            {/* Survival Metrics */}
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ fontWeight: FONT.weight.emphasis, marginBottom: 8 }}>Survival Metrics</div>
              <div style={{ display: "grid", gap: 4, fontSize: FONT.size.small }}>
                <div><span style={{ color: THEME.text.muted }}>Max Drawdown:</span> {(metrics.survival_metrics?.max_drawdown_pct || 0).toFixed(2)}%</div>
                <div><span style={{ color: THEME.text.muted }}>Kill Switches:</span> {metrics.survival_metrics?.kill_switch_activations || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Risks Avoided:</span> {metrics.survival_metrics?.total_risk_events_avoided || 0}</div>
              </div>
            </div>
            
            {/* Technical Stability */}
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ fontWeight: FONT.weight.emphasis, marginBottom: 8 }}>Technical Stability</div>
              <div style={{ display: "grid", gap: 4, fontSize: FONT.size.small }}>
                <div><span style={{ color: THEME.text.muted }}>Success Rate:</span> {((metrics.technical_stability?.execution_success_rate || 0) * 100).toFixed(1)}%</div>
                <div><span style={{ color: THEME.text.muted }}>Failures:</span> {metrics.technical_stability?.execution_failures || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Crashes:</span> {metrics.technical_stability?.system_crashes || 0}</div>
              </div>
            </div>
            
            {/* Guardian Behavior */}
            <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6 }}>
              <div style={{ fontWeight: FONT.weight.emphasis, marginBottom: 8 }}>Guardian Behavior</div>
              <div style={{ display: "grid", gap: 4, fontSize: FONT.size.small }}>
                <div><span style={{ color: THEME.text.muted }}>Interventions:</span> {metrics.guardian_behavior?.total_interventions || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Last 24h:</span> {metrics.guardian_behavior?.interventions_last_24_hours || 0}</div>
                <div><span style={{ color: THEME.text.muted }}>Stress Tests:</span> {metrics.guardian_behavior?.stress_tests_run || 0}</div>
              </div>
            </div>
          </div>
        </Card>
      )}
      
      {/* ============================================================ */}
      {/* 📜 HISTORY */}
      {/* ============================================================ */}
      <Card
        title="📜 Evaluation History"
        subtitle="Previous GO-LIVE Gate evaluations"
        right={
          <button
            onClick={() => setShowHistory(!showHistory)}
            style={{
              background: "transparent",
              border: "none",
              color: THEME.accent.primary,
              cursor: "pointer",
              fontSize: FONT.size.small,
            }}
          >
            {showHistory ? "Hide" : "Show"}
          </button>
        }
      >
        {showHistory && (
          history.length > 0 ? (
            <div>
              {history.map((h, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 0",
                    borderBottom: i < history.length - 1 ? `1px solid ${THEME.border.default}` : "none",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: FONT.weight.emphasis }}>
                      {h.evaluation_id?.slice(0, 12)}
                    </div>
                    <div style={{ fontSize: FONT.size.small, color: THEME.text.muted }}>
                      {new Date(h.timestamp).toLocaleString("en-GB")}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: FONT.size.small, color: THEME.text.secondary }}>
                      {h.criteria_passed}/{h.criteria_passed + h.criteria_failed} criteria
                    </span>
                    <Badge status={h.decision}>{h.decision}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: THEME.text.muted, textAlign: "center", padding: 20 }}>
              No previous evaluations.
            </div>
          )
        )}
      </Card>
      
      {/* ============================================================ */}
      {/* ⚠️ IMPORTANT NOTICE */}
      {/* ============================================================ */}
      <Card title="⚠️ Important Notice" subtitle="GO-LIVE Gate Principles">
        <div style={{ color: THEME.text.secondary, fontSize: FONT.size.small, lineHeight: 1.8 }}>
          <p style={{ marginTop: 0 }}>
            <strong style={{ color: THEME.text.primary }}>This gate does NOT optimize profits. This gate PREVENTS capital destruction.</strong>
          </p>
          <ul style={{ paddingLeft: 20, margin: "12px 0" }}>
            <li><strong>Survival &gt; Profit</strong> — HAVEN can lose trades, but cannot lose the account.</li>
            <li><strong>LIVE is permitted, not "activated"</strong> — The decision is binary: GO or NO-GO.</li>
            <li><strong>Absence of trades is valid</strong> — Not trading is a legitimate decision.</li>
            <li><strong>Guardian has maximum authority</strong> — No execution passes without Guardian approval.</li>
            <li><strong>If in doubt → NO-GO</strong> — Default is always to block.</li>
          </ul>
          <p style={{ margin: 0, fontStyle: "italic", color: THEME.state.warning }}>
            HAVEN can lose trades — but cannot lose the account.
          </p>
        </div>
      </Card>
    </div>
  );
}

export default GoLiveGate;
