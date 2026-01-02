/**
 * HAVEN Scheduler Panel — P1.3
 * ============================
 * 
 * Restrictive and predictable scheduler, never aggressive.
 * 
 * Controls:
 * - On/Off toggle
 * - Interval (5m / 15m / 30m / 1h)
 * - Allowed symbols
 * - Active hours (e.g., 08:00–22:00 UTC)
 * 
 * Hard Limits (not configurable via UI):
 * - Max runs per day
 * - Cooldown after block
 * - Guardian override total
 * - Scheduler never forces execution
 * 
 * Behavior:
 * - Scheduler requests run
 * - Growth Module decides
 * - Guardian approves or blocks
 * - Block does not auto-retry
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
    input: "#2B3139",
  },
  border: {
    default: "rgba(255, 255, 255, 0.08)",
    active: "rgba(240, 185, 11, 0.4)",
  },
  text: {
    primary: "#EAECEF",
    secondary: "#B7BDC6",
    muted: "#848E9C",
    inverse: "#0B0E11",
  },
  state: {
    safe: "#0ECB81",
    caution: "#F0B90B",
    blocked: "#F6465D",
    info: "#1E90FF",
  },
  accent: "#F0B90B",
};

const FONT = {
  family: "'Inter', sans-serif",
  mono: "'JetBrains Mono', monospace",
  size: {
    xs: "11px",
    sm: "12px",
    base: "14px",
    lg: "16px",
  },
};

// ============================================================
// 🧱 BASE COMPONENTS
// ============================================================

const Card = ({ title, subtitle, children, right }) => (
  <div
    style={{
      background: THEME.bg.card,
      border: `1px solid ${THEME.border.default}`,
      borderRadius: 6,
      padding: 20,
      marginBottom: 16,
    }}
  >
    {(title || right) && (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: FONT.size.lg, fontWeight: 600, color: THEME.text.primary }}>
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

const PowerToggle = ({ enabled, onChange, loading }) => (
  <button
    onClick={() => !loading && onChange(!enabled)}
    disabled={loading}
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "8px 16px",
      background: enabled ? THEME.state.safe : THEME.bg.hover,
      color: enabled ? THEME.text.inverse : THEME.text.secondary,
      border: `2px solid ${enabled ? THEME.state.safe : THEME.border.default}`,
      borderRadius: 6,
      fontSize: FONT.size.sm,
      fontWeight: 600,
      cursor: loading ? "wait" : "pointer",
      transition: "all 0.2s",
      opacity: loading ? 0.6 : 1,
    }}
  >
    <span style={{
      width: 12,
      height: 12,
      borderRadius: "50%",
      background: enabled ? "#fff" : THEME.text.muted,
      border: enabled ? "none" : `2px solid ${THEME.text.muted}`,
    }} />
    {enabled ? "ON" : "OFF"}
  </button>
);

const IntervalButton = ({ value, selected, onClick, disabled }) => (
  <button
    onClick={() => !disabled && onClick(value)}
    disabled={disabled}
    style={{
      padding: "10px 16px",
      background: selected ? THEME.accent : THEME.bg.hover,
      color: selected ? THEME.text.inverse : THEME.text.secondary,
      border: "none",
      borderRadius: 4,
      fontSize: FONT.size.sm,
      fontWeight: selected ? 600 : 400,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "all 0.15s",
      opacity: disabled ? 0.5 : 1,
    }}
  >
    {value}
  </button>
);

const SymbolChip = ({ symbol, selected, onClick, disabled }) => (
  <button
    onClick={() => !disabled && onClick(symbol)}
    disabled={disabled}
    style={{
      padding: "6px 12px",
      background: selected ? `${THEME.accent}20` : THEME.bg.elevated,
      color: selected ? THEME.accent : THEME.text.secondary,
      border: `1px solid ${selected ? THEME.accent : THEME.border.default}`,
      borderRadius: 4,
      fontSize: FONT.size.sm,
      fontWeight: selected ? 500 : 400,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "all 0.15s",
      opacity: disabled ? 0.5 : 1,
    }}
  >
    {symbol}
  </button>
);

const DayButton = ({ day, label, selected, onClick, disabled }) => (
  <button
    onClick={() => !disabled && onClick(day)}
    disabled={disabled}
    style={{
      width: 40,
      height: 40,
      background: selected ? THEME.accent : THEME.bg.hover,
      color: selected ? THEME.text.inverse : THEME.text.secondary,
      border: "none",
      borderRadius: 4,
      fontSize: FONT.size.xs,
      fontWeight: selected ? 600 : 400,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "all 0.15s",
      opacity: disabled ? 0.5 : 1,
    }}
  >
    {label}
  </button>
);

const HourSelect = ({ value, onChange, disabled, label }) => (
  <div>
    <label style={{ display: "block", color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 4 }}>
      {label}
    </label>
    <select
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value))}
      disabled={disabled}
      style={{
        padding: "8px 12px",
        background: THEME.bg.input,
        color: THEME.text.primary,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 4,
        fontSize: FONT.size.sm,
        width: 80,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {Array.from({ length: 24 }, (_, i) => (
        <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
      ))}
    </select>
  </div>
);

// ============================================================
// 🏛️ MAIN SCHEDULER PANEL
// ============================================================

export function SchedulerPanel({ scheduler: initialScheduler, onUpdate, loading: externalLoading }) {
  const [scheduler, setScheduler] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  
  // Available options
  const intervals = ["5 min", "15 min", "30 min", "1 hour"];
  const symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "BTC/EUR", "ETH/EUR"];
  const days = [
    { day: 0, label: "Mon" },
    { day: 1, label: "Tue" },
    { day: 2, label: "Wed" },
    { day: 3, label: "Thu" },
    { day: 4, label: "Fri" },
    { day: 5, label: "Sat" },
    { day: 6, label: "Sun" },
  ];
  
  // Hard limits (display only)
  const hardLimits = {
    maxRunsPerDay: 20,
    cooldownAfterBlockMinutes: 30,
    guardianOverride: true,
  };
  
  // Fetch scheduler config
  const fetchScheduler = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/growth/schedule/config");
      setScheduler(res.data);
    } catch (e) {
      // Use defaults
      setScheduler({
        enabled: false,
        interval_minutes: 15,
        symbols: ["BTC/USDT"],
        active_hours_start: 8,
        active_hours_end: 22,
        active_days: [0, 1, 2, 3, 4],
      });
    }
    setLoading(false);
  }, []);
  
  // Fetch scheduler stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get("/growth/schedule/stats");
      setStats(res.data);
    } catch (e) {
      // Stats not available
    }
  }, []);
  
  useEffect(() => {
    if (initialScheduler) {
      setScheduler(initialScheduler);
    } else {
      fetchScheduler();
    }
    fetchStats();
  }, [initialScheduler, fetchScheduler, fetchStats]);
  
  // Update scheduler
  const updateScheduler = async (updates) => {
    const newConfig = { ...scheduler, ...updates };
    setScheduler(newConfig);
    setSaving(true);
    setError(null);
    
    try {
      const res = await api.put("/growth/schedule/config", newConfig);
      setScheduler(res.data);
      if (onUpdate) onUpdate(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to update scheduler");
      // Revert
      fetchScheduler();
    } finally {
      setSaving(false);
    }
  };
  
  // Toggle enabled
  const toggleEnabled = async () => {
    await updateScheduler({ enabled: !scheduler.enabled });
  };
  
  // Set interval
  const setInterval = (intervalStr) => {
    const map = {
      "5 min": 5,
      "15 min": 15,
      "30 min": 30,
      "1 hour": 60,
    };
    updateScheduler({ interval_minutes: map[intervalStr] || 15 });
  };
  
  // Toggle symbol
  const toggleSymbol = (symbol) => {
    const current = scheduler.symbols || [];
    const newSymbols = current.includes(symbol)
      ? current.filter(s => s !== symbol)
      : [...current, symbol];
    
    if (newSymbols.length > 0) {
      updateScheduler({ symbols: newSymbols });
    }
  };
  
  // Toggle day
  const toggleDay = (day) => {
    const current = scheduler.active_days || [];
    const newDays = current.includes(day)
      ? current.filter(d => d !== day)
      : [...current, day].sort((a, b) => a - b);
    
    if (newDays.length > 0) {
      updateScheduler({ active_days: newDays });
    }
  };
  
  // Get interval string
  const getIntervalString = () => {
    const min = scheduler?.interval_minutes || 15;
    if (min >= 60) return "1 hour";
    return `${min} min`;
  };
  
  if (loading || !scheduler) {
    return (
      <Card title="🕐 Scheduler">
        <div style={{ color: THEME.text.muted, textAlign: "center", padding: 20 }}>
          Loading scheduler configuration...
        </div>
      </Card>
    );
  }
  
  const isDisabled = saving || externalLoading;
  
  return (
    <div>
      {/* Main Scheduler Card */}
      <Card
        title="🕐 Automated Scheduler"
        subtitle="Restrictive and predictable execution"
        right={<PowerToggle enabled={scheduler.enabled} onChange={toggleEnabled} loading={isDisabled} />}
      >
        {/* Status */}
        <div style={{
          padding: 12,
          marginBottom: 16,
          background: scheduler.enabled ? `${THEME.state.safe}10` : THEME.bg.elevated,
          borderRadius: 6,
          border: `1px solid ${scheduler.enabled ? `${THEME.state.safe}40` : THEME.border.default}`,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ color: scheduler.enabled ? THEME.state.safe : THEME.text.muted }}>
              {scheduler.enabled ? "Scheduler is ACTIVE" : "Scheduler is PAUSED"}
            </span>
            {stats && (
              <span style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
                Today: {stats.runs_today || 0}/{hardLimits.maxRunsPerDay} runs
              </span>
            )}
          </div>
          {scheduler.enabled && scheduler.next_run && (
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 4 }}>
              Next run: {new Date(scheduler.next_run).toLocaleString("en-GB")}
            </div>
          )}
        </div>
        
        {/* Interval Selection */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 8 }}>
            Run Interval
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {intervals.map(interval => (
              <IntervalButton
                key={interval}
                value={interval}
                selected={getIntervalString() === interval}
                onClick={setInterval}
                disabled={isDisabled || !scheduler.enabled}
              />
            ))}
          </div>
        </div>
        
        {/* Symbol Selection */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 8 }}>
            Allowed Symbols
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {symbols.map(symbol => (
              <SymbolChip
                key={symbol}
                symbol={symbol}
                selected={scheduler.symbols?.includes(symbol)}
                onClick={toggleSymbol}
                disabled={isDisabled || !scheduler.enabled}
              />
            ))}
          </div>
        </div>
        
        {/* Active Hours */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 8 }}>
            Active Hours (UTC)
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <HourSelect
              label="Start"
              value={scheduler.active_hours_start || 8}
              onChange={(v) => updateScheduler({ active_hours_start: v })}
              disabled={isDisabled || !scheduler.enabled}
            />
            <span style={{ color: THEME.text.muted }}>to</span>
            <HourSelect
              label="End"
              value={scheduler.active_hours_end || 22}
              onChange={(v) => updateScheduler({ active_hours_end: v })}
              disabled={isDisabled || !scheduler.enabled}
            />
          </div>
        </div>
        
        {/* Active Days */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 8 }}>
            Active Days
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {days.map(({ day, label }) => (
              <DayButton
                key={day}
                day={day}
                label={label}
                selected={scheduler.active_days?.includes(day)}
                onClick={toggleDay}
                disabled={isDisabled || !scheduler.enabled}
              />
            ))}
          </div>
        </div>
        
        {error && (
          <div style={{
            padding: 10,
            background: `${THEME.state.blocked}15`,
            borderRadius: 4,
            color: THEME.state.blocked,
            fontSize: FONT.size.sm,
          }}>
            {error}
          </div>
        )}
      </Card>
      
      {/* Hard Limits Card (Read-only) */}
      <Card title="🔒 Hard Limits (System-Enforced)" subtitle="These limits cannot be changed via UI">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6, textAlign: "center" }}>
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 4 }}>
              Max Runs / Day
            </div>
            <div style={{ color: THEME.text.primary, fontSize: FONT.size.lg, fontWeight: 600, fontFamily: FONT.mono }}>
              {hardLimits.maxRunsPerDay}
            </div>
          </div>
          <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6, textAlign: "center" }}>
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 4 }}>
              Cooldown After Block
            </div>
            <div style={{ color: THEME.text.primary, fontSize: FONT.size.lg, fontWeight: 600, fontFamily: FONT.mono }}>
              {hardLimits.cooldownAfterBlockMinutes}m
            </div>
          </div>
          <div style={{ padding: 12, background: THEME.bg.elevated, borderRadius: 6, textAlign: "center" }}>
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 4 }}>
              Guardian Override
            </div>
            <div style={{ color: THEME.state.safe, fontSize: FONT.size.lg, fontWeight: 600 }}>
              ALWAYS
            </div>
          </div>
        </div>
        
        <div style={{
          marginTop: 12,
          padding: 10,
          background: `${THEME.state.caution}10`,
          borderRadius: 4,
          fontSize: FONT.size.xs,
          color: THEME.text.muted,
        }}>
          ⚠️ Scheduler never forces execution. Guardian has final say on all runs.
        </div>
      </Card>
      
      {/* Scheduler Behavior Info */}
      <Card title="ℹ️ Scheduler Behavior" subtitle="How the automated scheduler works">
        <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, lineHeight: 1.8 }}>
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            <li><strong>Scheduler requests</strong> a run at the configured interval</li>
            <li><strong>Growth Module decides</strong> based on market conditions</li>
            <li><strong>Guardian validates</strong> risk limits and capital protection</li>
            <li><strong>If blocked</strong>, the run is skipped (no auto-retry)</li>
          </ol>
          <div style={{ 
            marginTop: 12, 
            padding: 10, 
            background: THEME.bg.elevated, 
            borderRadius: 4,
            fontStyle: "italic",
          }}>
            The scheduler amplifies decisions — in HAVEN, automation comes after control.
          </div>
        </div>
      </Card>
    </div>
  );
}

export default SchedulerPanel;
