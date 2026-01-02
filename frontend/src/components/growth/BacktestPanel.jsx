/**
 * HAVEN Backtest Panel — P5/P6
 * ============================
 * 
 * Lightweight backtesting/replay tool UI.
 * 
 * Features:
 * - Symbol/strategy/date range selection
 * - Run backtest simulation
 * - Display performance metrics
 * - Equity curve visualization
 * - Backtest history list
 * - OPTIMIZE: Walk-forward parameter optimization with overfit detection
 * - SUGGESTED AGENT: Strategy-to-agent mapping with reasoning
 * - SAVE AS PRESET: Export optimized params (audit logged, no base overwrite)
 * 
 * READ-ONLY: No interaction with LIVE trading or presets.
 */

import React, { useState, useEffect, useCallback } from "react";
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
  },
  state: {
    safe: "#0ECB81",
    caution: "#F0B90B",
    blocked: "#F6465D",
    info: "#1E90FF",
    purple: "#9B59B6",
  },
};

const FONT = {
  size: {
    xs: "11px",
    sm: "12px",
    base: "14px",
    lg: "16px",
    xl: "20px",
  },
};

// ============================================================
// 🧱 BASE COMPONENTS
// ============================================================

const Card = ({ title, subtitle, children, right, noPadding, accent }) => (
  <div
    style={{
      background: THEME.bg.card,
      border: `1px solid ${accent ? `${accent}40` : THEME.border.default}`,
      borderRadius: 6,
      padding: noPadding ? 0 : 16,
      marginBottom: 12,
    }}
  >
    {(title || right) && (
      <div style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center", 
        marginBottom: noPadding ? 0 : 12,
        padding: noPadding ? 16 : 0,
        paddingBottom: noPadding ? 12 : 0,
      }}>
        <div>
          <h3 style={{ margin: 0, fontSize: FONT.size.base, fontWeight: 600, color: accent || THEME.text.primary }}>
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

const MetricCard = ({ label, value, subValue, color, icon }) => (
  <div
    style={{
      padding: 12,
      background: THEME.bg.elevated,
      borderRadius: 6,
      textAlign: "center",
      minWidth: 100,
    }}
  >
    {icon && <div style={{ fontSize: "18px", marginBottom: 4 }}>{icon}</div>}
    <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>
      {label}
    </div>
    <div style={{ fontSize: FONT.size.lg, fontWeight: 600, color: color || THEME.text.primary }}>
      {value}
    </div>
    {subValue && (
      <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginTop: 2 }}>
        {subValue}
      </div>
    )}
  </div>
);

const Button = ({ children, onClick, disabled, variant = "primary", loading, size = "md" }) => {
  const styles = {
    primary: { background: THEME.state.info, color: "#fff" },
    secondary: { background: THEME.bg.elevated, color: THEME.text.primary },
    success: { background: THEME.state.safe, color: "#fff" },
    purple: { background: THEME.state.purple, color: "#fff" },
  };
  const sizes = {
    sm: { padding: "6px 12px", fontSize: FONT.size.xs },
    md: { padding: "10px 20px", fontSize: FONT.size.sm },
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        border: "none",
        borderRadius: 4,
        cursor: disabled || loading ? "not-allowed" : "pointer",
        opacity: disabled || loading ? 0.6 : 1,
        fontWeight: 500,
        transition: "all 0.2s",
        ...styles[variant],
        ...sizes[size],
      }}
    >
      {loading ? "Running..." : children}
    </button>
  );
};

const Select = ({ label, value, onChange, options }) => (
  <div style={{ marginBottom: 12 }}>
    <label style={{ display: "block", fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>
      {label}
    </label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: "100%",
        padding: "8px 12px",
        background: THEME.bg.elevated,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 4,
        color: THEME.text.primary,
        fontSize: FONT.size.sm,
        cursor: "pointer",
      }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  </div>
);

const Input = ({ label, type = "text", value, onChange, min, max, step, placeholder }) => (
  <div style={{ marginBottom: 12 }}>
    <label style={{ display: "block", fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>
      {label}
    </label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      style={{
        width: "100%",
        padding: "8px 12px",
        background: THEME.bg.elevated,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 4,
        color: THEME.text.primary,
        fontSize: FONT.size.sm,
        boxSizing: "border-box",
      }}
    />
  </div>
);

const Badge = ({ children, color }) => (
  <span style={{
    padding: "3px 8px",
    background: `${color}20`,
    color: color,
    fontSize: FONT.size.xs,
    fontWeight: 500,
    borderRadius: 4,
  }}>
    {children}
  </span>
);

const Tabs = ({ tabs, activeTab, onChange }) => (
  <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
    {tabs.map((tab) => (
      <button
        key={tab.id}
        onClick={() => onChange(tab.id)}
        style={{
          padding: "8px 16px",
          background: activeTab === tab.id ? THEME.state.info : THEME.bg.elevated,
          border: "none",
          borderRadius: 4,
          color: activeTab === tab.id ? "#fff" : THEME.text.secondary,
          fontSize: FONT.size.sm,
          cursor: "pointer",
          fontWeight: activeTab === tab.id ? 600 : 400,
        }}
      >
        {tab.icon} {tab.label}
      </button>
    ))}
  </div>
);

// ============================================================
// 📈 EQUITY CURVE CHART (Simple SVG)
// ============================================================

const EquityCurve = ({ data, height = 180 }) => {
  if (!data || data.length < 2) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: THEME.text.muted, fontSize: FONT.size.sm }}>
        No data available
      </div>
    );
  }

  const padding = { top: 20, right: 20, bottom: 30, left: 60 };
  const width = 600;
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const equities = data.map(d => d.equity);
  const minEquity = Math.min(...equities) * 0.98;
  const maxEquity = Math.max(...equities) * 1.02;

  const scaleX = (i) => padding.left + (i / (data.length - 1)) * chartWidth;
  const scaleY = (val) => padding.top + chartHeight - ((val - minEquity) / (maxEquity - minEquity)) * chartHeight;

  const pathD = data.map((d, i) => `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(d.equity)}`).join(" ");
  const areaD = pathD + ` L ${scaleX(data.length - 1)} ${scaleY(minEquity)} L ${scaleX(0)} ${scaleY(minEquity)} Z`;

  const isPositive = data[data.length - 1].equity >= data[0].equity;
  const lineColor = isPositive ? THEME.state.safe : THEME.state.blocked;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <path d={areaD} fill={lineColor} fillOpacity={0.1} />
      <path d={pathD} fill="none" stroke={lineColor} strokeWidth={2} />
      <circle cx={scaleX(0)} cy={scaleY(data[0].equity)} r={4} fill={lineColor} />
      <circle cx={scaleX(data.length - 1)} cy={scaleY(data[data.length - 1].equity)} r={4} fill={lineColor} />
      <text x={padding.left - 8} y={scaleY(maxEquity)} fill={THEME.text.muted} fontSize="10" textAnchor="end" dominantBaseline="middle">${maxEquity.toFixed(0)}</text>
      <text x={padding.left - 8} y={scaleY(minEquity)} fill={THEME.text.muted} fontSize="10" textAnchor="end" dominantBaseline="middle">${minEquity.toFixed(0)}</text>
    </svg>
  );
};

// ============================================================
// 🎯 SUGGESTED AGENT PANEL
// ============================================================

const SuggestedAgentPanel = ({ result, onSavePreset }) => {
  const [suggestion, setSuggestion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!result || !result.metrics) return;

    async function fetchSuggestion() {
      setLoading(true);
      try {
        const res = await api.post("/mapping/suggest-agent-from-result", {
          strategy: result.strategy,
          symbol: result.symbol,
          metrics: result.metrics,
        });
        setSuggestion(res.data);
      } catch (e) {
        console.error("Failed to get agent suggestion:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchSuggestion();
  }, [result]);

  const handleSavePreset = async () => {
    if (!presetName.trim()) return;
    setSaving(true);
    try {
      await api.post("/backtest/save-as-preset", {
        name: presetName,
        description: `Optimized ${result.strategy} for ${result.symbol}`,
        strategy: result.strategy,
        params: result.best_result?.params || {},
        metrics_summary: result.best_result ? {
          test_return_pct: result.best_result.test?.return_pct,
          overfit_risk: result.best_result.overfit_risk,
        } : result.metrics,
      });
      setSaved(true);
      setPresetName("");
      onSavePreset?.();
    } catch (e) {
      console.error("Failed to save preset:", e);
    } finally {
      setSaving(false);
    }
  };

  if (!result) return null;

  return (
    <Card title="🤖 Suggested Agent" subtitle="Based on backtest results" accent={THEME.state.purple}>
      {loading ? (
        <div style={{ textAlign: "center", padding: 20, color: THEME.text.muted }}>Loading...</div>
      ) : suggestion ? (
        <div>
          {/* Primary Agent */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 8,
              background: `${THEME.state.purple}20`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: "24px",
            }}>
              {suggestion.primary_agent === "GRID" ? "📊" : suggestion.primary_agent === "TREND" ? "📈" : "💰"}
            </div>
            <div>
              <div style={{ fontWeight: 600, color: THEME.text.primary, fontSize: FONT.size.lg }}>
                {suggestion.primary_agent}
              </div>
              <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>
                Confidence: {suggestion.confidence}%
              </div>
            </div>
            {suggestion.secondary_agent && (
              <Badge color={THEME.state.caution}>+ {suggestion.secondary_agent} hedge</Badge>
            )}
          </div>

          {/* Metrics Analysis */}
          <div style={{ background: THEME.bg.elevated, borderRadius: 4, padding: 12, marginBottom: 12 }}>
            <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 8 }}>ANALYSIS</div>
            {Object.entries(suggestion.metrics_analysis || {}).map(([key, value]) => (
              <div key={key} style={{ fontSize: FONT.size.xs, color: THEME.text.secondary, marginBottom: 4 }}>
                • {value}
              </div>
            ))}
          </div>

          {/* Warnings */}
          {suggestion.warnings?.length > 0 && (
            <div style={{ background: `${THEME.state.caution}10`, borderRadius: 4, padding: 12, marginBottom: 12 }}>
              <div style={{ fontSize: FONT.size.xs, color: THEME.state.caution, marginBottom: 4 }}>⚠️ WARNINGS</div>
              {suggestion.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: FONT.size.xs, color: THEME.text.secondary }}>• {w}</div>
              ))}
            </div>
          )}

          {/* Reasons */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>WHY {suggestion.primary_agent}?</div>
            {suggestion.reasons?.slice(0, 3).map((r, i) => (
              <div key={i} style={{ fontSize: FONT.size.xs, color: THEME.text.secondary, marginBottom: 2 }}>• {r}</div>
            ))}
          </div>

          {/* Save as Custom Preset */}
          <div style={{ borderTop: `1px solid ${THEME.border.default}`, paddingTop: 12, marginTop: 12 }}>
            <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 8 }}>
              💾 Save as Custom Preset (audit logged, requires activation)
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="text"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                placeholder="Preset name..."
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: THEME.bg.card,
                  border: `1px solid ${THEME.border.default}`,
                  borderRadius: 4,
                  color: THEME.text.primary,
                  fontSize: FONT.size.sm,
                }}
              />
              <Button
                variant="purple"
                size="sm"
                onClick={handleSavePreset}
                disabled={!presetName.trim() || saving}
              >
                {saving ? "Saving..." : saved ? "✓ Saved" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: 20, color: THEME.text.muted }}>
          Run a backtest to get agent suggestions
        </div>
      )}
    </Card>
  );
};

// ============================================================
// ⚡ OPTIMIZATION PANEL
// ============================================================

const OptimizationPanel = ({ symbol, strategy, startDate, endDate, initialCapital, onComplete }) => {
  const [numVariations, setNumVariations] = useState("20");
  const [trainRatio, setTrainRatio] = useState("0.7");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const runOptimization = async () => {
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post(
        "/backtest/optimize",
        {
          strategy,
          symbol,
          start_date: startDate,
          end_date: endDate,
          initial_capital: parseFloat(initialCapital),
          num_variations: parseInt(numVariations),
          train_ratio: parseFloat(trainRatio),
        },
        {
          // Optimization can take longer than regular API calls.
          timeout: 120000,
        }
      );

      if (res.data.status === "failed") {
        setError(res.data.error || "Optimization failed");
      } else {
        setResult(res.data);
        onComplete?.(res.data);
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to run optimization");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card title="⚡ Parameter Optimization" subtitle="Walk-forward validation with overfit detection" accent={THEME.state.caution}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <Input
          label="Variations"
          type="number"
          value={numVariations}
          onChange={setNumVariations}
          min="5"
          max="50"
        />
        <Input
          label="Train Ratio"
          type="number"
          value={trainRatio}
          onChange={setTrainRatio}
          min="0.5"
          max="0.9"
          step="0.1"
        />
      </div>

      <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 12 }}>
        📊 Using: {symbol} • {strategy} • {startDate} to {endDate}
      </div>

      <Button variant="primary" onClick={runOptimization} loading={running} disabled={running}>
        ⚡ Run Optimization ({numVariations} variations)
      </Button>

      {error && (
        <div style={{ marginTop: 12, padding: 12, background: `${THEME.state.blocked}15`, borderRadius: 4, color: THEME.state.blocked, fontSize: FONT.size.xs }}>
          ⚠️ {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontWeight: 600, color: THEME.text.primary }}>
              {result.results?.length || 0} Valid Results
            </div>
            <Badge color={result.status === "completed" ? THEME.state.safe : THEME.state.blocked}>
              {result.status?.toUpperCase()}
            </Badge>
          </div>

          {/* Best Result */}
          {result.best_result && (
            <div style={{ background: `${THEME.state.safe}10`, border: `1px solid ${THEME.state.safe}40`, borderRadius: 6, padding: 12, marginBottom: 12 }}>
              <div style={{ fontSize: FONT.size.xs, color: THEME.state.safe, marginBottom: 8 }}>🏆 BEST RESULT (Rank #1)</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 12 }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>Test Return</div>
                  <div style={{ fontWeight: 600, color: result.best_result.test?.return_pct >= 0 ? THEME.state.safe : THEME.state.blocked }}>
                    {result.best_result.test?.return_pct?.toFixed(1)}%
                  </div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>Test Sharpe</div>
                  <div style={{ fontWeight: 600, color: THEME.text.primary }}>{result.best_result.test?.sharpe?.toFixed(2)}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>Win Rate</div>
                  <div style={{ fontWeight: 600, color: THEME.text.primary }}>{result.best_result.test?.win_rate?.toFixed(0)}%</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>Overfit Risk</div>
                  <div style={{ fontWeight: 600, color: result.best_result.overfit_risk > 50 ? THEME.state.blocked : result.best_result.overfit_risk > 25 ? THEME.state.caution : THEME.state.safe }}>
                    {result.best_result.overfit_risk?.toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Params */}
              <div style={{ background: THEME.bg.elevated, borderRadius: 4, padding: 8, fontSize: FONT.size.xs }}>
                <span style={{ color: THEME.text.muted }}>Params: </span>
                <span style={{ color: THEME.text.primary, fontFamily: "monospace" }}>
                  {JSON.stringify(result.best_result.params)}
                </span>
              </div>

              {/* Overfit reasons */}
              {result.best_result.overfit_reasons?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: FONT.size.xs, color: THEME.text.muted }}>
                  {result.best_result.overfit_reasons.map((r, i) => (
                    <div key={i}>• {r}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Other Results */}
          {result.results?.slice(1, 5).map((r, i) => (
            <div key={r.variation_id} style={{ background: THEME.bg.elevated, borderRadius: 4, padding: 10, marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>#{r.rank} </span>
                <span style={{ fontSize: FONT.size.xs, color: THEME.text.primary, fontFamily: "monospace" }}>
                  {JSON.stringify(r.params)}
                </span>
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: FONT.size.xs }}>
                <span style={{ color: r.test?.return_pct >= 0 ? THEME.state.safe : THEME.state.blocked }}>
                  {r.test?.return_pct?.toFixed(1)}%
                </span>
                <span style={{ color: THEME.text.muted }}>
                  Risk: {r.overfit_risk?.toFixed(0)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

// ============================================================
// 📜 BACKTEST HISTORY LIST
// ============================================================

const HistoryItem = ({ item, onClick }) => {
  const returnColor = item.metrics?.total_return_pct >= 0 ? THEME.state.safe : THEME.state.blocked;
  const date = item.created_at ? new Date(item.created_at).toLocaleDateString("en-GB") : "N/A";

  return (
    <div
      onClick={onClick}
      style={{
        padding: "12px 16px",
        background: THEME.bg.elevated,
        borderRadius: 4,
        marginBottom: 8,
        cursor: "pointer",
        transition: "background 0.2s",
      }}
      onMouseEnter={(e) => e.currentTarget.style.background = THEME.bg.hover}
      onMouseLeave={(e) => e.currentTarget.style.background = THEME.bg.elevated}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontWeight: 500, color: THEME.text.primary, fontSize: FONT.size.sm }}>
            {item.symbol} • {item.strategy}
          </div>
          <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginTop: 2 }}>
            {date} • {item.metrics?.total_trades || 0} trades
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontWeight: 600, color: returnColor, fontSize: FONT.size.base }}>
            {item.metrics?.total_return_pct >= 0 ? "+" : ""}{item.metrics?.total_return_pct?.toFixed(2) || 0}%
          </div>
          <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>
            SR: {item.metrics?.sharpe_ratio?.toFixed(2) || "N/A"}
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================
// 🎯 MAIN BACKTEST PANEL COMPONENT
// ============================================================

export function BacktestPanel() {
  // Tab state
  const [activeTab, setActiveTab] = useState("backtest");

  // Form state
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [strategy, setStrategy] = useState("momentum");
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 2);
    return d.toISOString().split("T")[0];
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [initialCapital, setInitialCapital] = useState("10000");

  // Data state
  const [strategies, setStrategies] = useState([]);
  const [result, setResult] = useState(null);
  const [optimizationResult, setOptimizationResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const symbols = [
    { value: "BTC/USDT", label: "BTC/USDT" },
    { value: "ETH/USDT", label: "ETH/USDT" },
    { value: "SOL/USDT", label: "SOL/USDT" },
    { value: "BTC/USD", label: "BTC/USD" },
    { value: "ETH/USD", label: "ETH/USD" },
  ];

  // Fetch strategies on mount
  useEffect(() => {
    async function fetchStrategies() {
      try {
        const res = await api.get("/backtest/strategies");
        setStrategies(res.data.strategies || []);
      } catch (e) {
        console.error("Failed to fetch strategies:", e);
      }
    }
    fetchStrategies();
  }, []);

  // Fetch history
  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get("/backtest/history?limit=10");
      setHistory(res.data.results || []);
    } catch (e) {
      console.error("Failed to fetch history:", e);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Run backtest
  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post("/backtest/run", {
        symbol, strategy, start_date: startDate, end_date: endDate,
        initial_capital: parseFloat(initialCapital),
      });

      if (res.data.status === "failed") {
        setError(res.data.error || "Backtest failed");
      } else {
        setResult(res.data);
        fetchHistory();
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to run backtest");
    } finally {
      setLoading(false);
    }
  };

  const loadHistoricalResult = async (item) => {
    try {
      const res = await api.get(`/backtest/${item.id}`);
      setResult(res.data);
    } catch (e) {
      console.error("Failed to load result:", e);
    }
  };

  const metrics = result?.metrics || {};
  const returnColor = metrics.total_return_pct >= 0 ? THEME.state.safe : THEME.state.blocked;

  return (
    <div>
      {/* Header */}
      <div style={{ 
        display: "flex", alignItems: "center", gap: 12, marginBottom: 16,
        padding: "12px 16px",
        background: `${THEME.state.info}10`,
        border: `1px solid ${THEME.state.info}30`,
        borderRadius: 6,
      }}>
        <span style={{ fontSize: "24px" }}>📊</span>
        <div>
          <div style={{ fontWeight: 600, color: THEME.text.primary }}>Backtest / Replay Tool</div>
          <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>
            Simulate strategies on historical data • READ-ONLY mode • No LIVE execution
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          { id: "backtest", icon: "📈", label: "Backtest" },
          { id: "optimize", icon: "⚡", label: "Optimize" },
        ]}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr 300px", gap: 16 }}>
        {/* Left Panel - Configuration */}
        <div>
          <Card title="⚙️ Configuration" subtitle="Set backtest parameters">
            <Select label="Symbol" value={symbol} onChange={setSymbol} options={symbols} />
            <Select
              label="Strategy"
              value={strategy}
              onChange={setStrategy}
              options={strategies.map(s => ({
                value: s.name,
                label: `${s.name}`,
              }))}
            />
            <Input label="Start Date" type="date" value={startDate} onChange={setStartDate} />
            <Input label="End Date" type="date" value={endDate} onChange={setEndDate} />
            <Input label="Initial Capital ($)" type="number" value={initialCapital} onChange={setInitialCapital} min="100" step="100" />

            {activeTab === "backtest" && (
              <Button onClick={runBacktest} loading={loading} disabled={!strategy || !startDate || !endDate}>
                ▶ Run Backtest
              </Button>
            )}

            {error && (
              <div style={{ marginTop: 12, padding: 12, background: `${THEME.state.blocked}15`, borderRadius: 4, color: THEME.state.blocked, fontSize: FONT.size.xs }}>
                ⚠️ {error}
              </div>
            )}
          </Card>

          {/* History */}
          <Card title="📜 History" subtitle="Recent backtests">
            {history.length === 0 ? (
              <div style={{ textAlign: "center", padding: 20, color: THEME.text.muted, fontSize: FONT.size.sm }}>No backtests yet</div>
            ) : (
              <div style={{ maxHeight: 250, overflow: "auto" }}>
                {history.map((item, i) => (
                  <HistoryItem key={item.id || i} item={item} onClick={() => loadHistoricalResult(item)} />
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Middle Panel - Results / Optimization */}
        <div>
          {activeTab === "backtest" && (
            <>
              {!result && !loading && (
                <Card>
                  <div style={{ textAlign: "center", padding: 60, color: THEME.text.muted }}>
                    <div style={{ fontSize: "48px", marginBottom: 16 }}>📈</div>
                    <div style={{ fontSize: FONT.size.base }}>Configure parameters and run a backtest</div>
                  </div>
                </Card>
              )}

              {loading && (
                <Card>
                  <div style={{ textAlign: "center", padding: 60, color: THEME.text.muted }}>
                    <div style={{ fontSize: "48px", marginBottom: 16 }}>⏳</div>
                    <div>Running backtest simulation...</div>
                  </div>
                </Card>
              )}

              {result && !loading && (
                <>
                  {/* Summary Header */}
                  <Card>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontSize: FONT.size.lg, fontWeight: 600, color: THEME.text.primary }}>
                          {result.symbol} • {result.strategy}
                        </div>
                        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginTop: 4 }}>
                          {result.start_date?.split("T")[0]} → {result.end_date?.split("T")[0]} • {result.candles_processed} candles
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "28px", fontWeight: 700, color: returnColor }}>
                          {metrics.total_return_pct >= 0 ? "+" : ""}{metrics.total_return_pct?.toFixed(2)}%
                        </div>
                        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>
                          ${metrics.total_return?.toFixed(2)} return
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Metrics Grid */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, marginBottom: 12 }}>
                    <MetricCard icon="💰" label="Final Capital" value={`$${result.final_capital?.toFixed(0)}`} />
                    <MetricCard icon="📉" label="Max Drawdown" value={`${metrics.max_drawdown_pct?.toFixed(1)}%`} color={metrics.max_drawdown_pct > 20 ? THEME.state.blocked : THEME.text.primary} />
                    <MetricCard icon="📊" label="Sharpe" value={metrics.sharpe_ratio?.toFixed(2)} color={metrics.sharpe_ratio > 1 ? THEME.state.safe : THEME.text.primary} />
                    <MetricCard icon="🎯" label="Win Rate" value={`${metrics.win_rate?.toFixed(1)}%`} color={metrics.win_rate > 50 ? THEME.state.safe : THEME.state.caution} />
                    <MetricCard icon="⚖️" label="Profit Factor" value={metrics.profit_factor?.toFixed(2)} />
                    <MetricCard icon="🔄" label="Trades" value={metrics.total_trades} />
                  </div>

                  {/* Equity Curve */}
                  <Card title="📈 Equity Curve">
                    <EquityCurve data={result.equity_curve} height={180} />
                  </Card>
                </>
              )}
            </>
          )}

          {activeTab === "optimize" && (
            <OptimizationPanel
              symbol={symbol}
              strategy={strategy}
              startDate={startDate}
              endDate={endDate}
              initialCapital={initialCapital}
              onComplete={(res) => {
                setOptimizationResult(res);
                // Also set as result for agent suggestion
                if (res.best_result) {
                  setResult({
                    ...res,
                    metrics: res.best_result.test,
                    best_result: res.best_result,
                  });
                }
              }}
            />
          )}
        </div>

        {/* Right Panel - Suggested Agent */}
        <div>
          <SuggestedAgentPanel
            result={result || optimizationResult}
            onSavePreset={fetchHistory}
          />

          {/* Strategy Mappings Info */}
          <Card title="📚 Strategy → Agent Mappings" subtitle="Reference guide">
            <div style={{ fontSize: FONT.size.xs }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${THEME.border.default}` }}>
                <span style={{ color: THEME.text.muted }}>mean_reversion</span>
                <Badge color={THEME.state.info}>GRID</Badge>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${THEME.border.default}` }}>
                <span style={{ color: THEME.text.muted }}>breakout</span>
                <Badge color={THEME.state.safe}>TREND</Badge>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${THEME.border.default}` }}>
                <span style={{ color: THEME.text.muted }}>sma_crossover</span>
                <Badge color={THEME.state.safe}>TREND</Badge>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${THEME.border.default}` }}>
                <span style={{ color: THEME.text.muted }}>momentum</span>
                <Badge color={THEME.state.safe}>TREND</Badge>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0" }}>
                <span style={{ color: THEME.text.muted }}>baseline</span>
                <Badge color={THEME.state.caution}>DCA</Badge>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default BacktestPanel;
