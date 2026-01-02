/**
 * HAVEN Config Editor — P1.1
 * ==========================
 * 
 * Secure configuration editor with:
 * - Form mode (validated fields)
 * - JSON mode (power users)
 * - Visual diff before saving
 * - Mandatory reason field
 * - Guardian validation
 * - Full audit trail
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
    error: "rgba(246, 70, 93, 0.4)",
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

const Card = ({ title, subtitle, children, status, right }) => (
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: subtitle ? 4 : 12 }}>
        <h3 style={{ margin: 0, fontSize: FONT.size.lg, fontWeight: 600, color: THEME.text.primary }}>
          {title}
        </h3>
        {right}
      </div>
    )}
    {subtitle && (
      <div style={{ color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 16 }}>
        {subtitle}
      </div>
    )}
    {children}
  </div>
);

const Badge = ({ type, children }) => {
  const colors = {
    low: { bg: `${THEME.state.success}15`, border: `${THEME.state.success}40`, text: THEME.state.success },
    medium: { bg: `${THEME.state.warning}15`, border: `${THEME.state.warning}40`, text: THEME.state.warning },
    high: { bg: `${THEME.state.error}15`, border: `${THEME.state.error}40`, text: THEME.state.error },
    critical: { bg: `${THEME.state.error}25`, border: THEME.state.error, text: THEME.state.error },
    info: { bg: `${THEME.state.info}15`, border: `${THEME.state.info}40`, text: THEME.state.info },
  };
  const c = colors[type] || colors.info;
  
  return (
    <span style={{
      display: "inline-block",
      padding: "4px 8px",
      borderRadius: 4,
      fontSize: FONT.size.xs,
      fontWeight: 500,
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.text,
      textTransform: "uppercase",
    }}>
      {children}
    </span>
  );
};

const Button = ({ onClick, disabled, variant = "primary", children, style = {} }) => {
  const variants = {
    primary: {
      background: disabled ? THEME.bg.hover : THEME.accent,
      color: disabled ? THEME.text.muted : THEME.text.inverse,
    },
    secondary: {
      background: THEME.bg.hover,
      color: THEME.text.primary,
    },
    danger: {
      background: THEME.state.error,
      color: THEME.text.primary,
    },
  };
  const v = variants[variant];
  
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "10px 20px",
        background: v.background,
        color: v.color,
        border: "none",
        borderRadius: 6,
        fontSize: FONT.size.base,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        fontFamily: FONT.family,
        transition: "all 0.15s",
        ...style,
      }}
    >
      {children}
    </button>
  );
};

const TabButton = ({ active, onClick, children }) => (
  <button
    onClick={onClick}
    style={{
      padding: "8px 16px",
      background: active ? THEME.accent : "transparent",
      color: active ? THEME.text.inverse : THEME.text.secondary,
      border: "none",
      borderRadius: 4,
      fontSize: FONT.size.sm,
      fontWeight: 500,
      cursor: "pointer",
      transition: "all 0.15s",
    }}
  >
    {children}
  </button>
);

const Input = ({ label, value, onChange, type = "text", disabled, placeholder, description, error }) => (
  <div style={{ marginBottom: 16 }}>
    {label && (
      <label style={{ display: "block", color: THEME.text.secondary, fontSize: FONT.size.sm, marginBottom: 6 }}>
        {label}
      </label>
    )}
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(type === "number" ? parseFloat(e.target.value) : e.target.value)}
      disabled={disabled}
      placeholder={placeholder}
      style={{
        width: "100%",
        padding: "10px 12px",
        background: THEME.bg.input,
        border: `1px solid ${error ? THEME.border.error : THEME.border.default}`,
        borderRadius: 6,
        color: THEME.text.primary,
        fontSize: FONT.size.base,
        fontFamily: FONT.family,
        outline: "none",
        boxSizing: "border-box",
      }}
    />
    {description && (
      <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 4 }}>
        {description}
      </div>
    )}
    {error && (
      <div style={{ color: THEME.state.error, fontSize: FONT.size.xs, marginTop: 4 }}>
        {error}
      </div>
    )}
  </div>
);

const Toggle = ({ label, checked, onChange, description }) => (
  <div style={{ marginBottom: 16, display: "flex", alignItems: "flex-start", gap: 12 }}>
    <button
      onClick={() => onChange(!checked)}
      style={{
        width: 44,
        height: 24,
        borderRadius: 12,
        background: checked ? THEME.state.success : THEME.bg.hover,
        border: "none",
        cursor: "pointer",
        position: "relative",
        padding: 0,
        flexShrink: 0,
        transition: "background 0.15s",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2,
          left: checked ? 22 : 2,
          width: 20,
          height: 20,
          borderRadius: 10,
          background: "#fff",
          transition: "left 0.15s",
        }}
      />
    </button>
    <div>
      <div style={{ color: THEME.text.primary, fontSize: FONT.size.base }}>{label}</div>
      {description && (
        <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 2 }}>
          {description}
        </div>
      )}
    </div>
  </div>
);

// ============================================================
// 📊 DIFF VIEW COMPONENT
// ============================================================

const DiffView = ({ diffs, guardianValidation }) => {
  if (!diffs || diffs.length === 0) return null;
  
  return (
    <Card title="📊 Change Preview" subtitle="Review changes before saving">
      {/* Guardian Validation */}
      {guardianValidation && (
        <div style={{
          padding: 12,
          marginBottom: 16,
          borderRadius: 6,
          background: guardianValidation.allowed ? `${THEME.state.success}10` : `${THEME.state.error}10`,
          border: `1px solid ${guardianValidation.allowed ? `${THEME.state.success}40` : `${THEME.state.error}40`}`,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 18 }}>{guardianValidation.allowed ? "✓" : "⛔"}</span>
            <span style={{ 
              fontWeight: 600, 
              color: guardianValidation.allowed ? THEME.state.success : THEME.state.error 
            }}>
              Guardian Validation: {guardianValidation.allowed ? "ALLOWED" : "BLOCKED"}
            </span>
            <Badge type={guardianValidation.risk_level}>{guardianValidation.risk_level}</Badge>
          </div>
          {guardianValidation.blocked_reason && (
            <div style={{ color: THEME.state.error, fontSize: FONT.size.sm }}>
              {guardianValidation.blocked_reason}
            </div>
          )}
          {guardianValidation.warnings?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {guardianValidation.warnings.map((w, i) => (
                <div key={i} style={{ color: THEME.state.warning, fontSize: FONT.size.sm }}>
                  ⚠ {w}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Changes Table */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${THEME.border.default}` }}>
            <th style={{ textAlign: "left", padding: 8, color: THEME.text.muted, fontSize: FONT.size.sm }}>Field</th>
            <th style={{ textAlign: "left", padding: 8, color: THEME.text.muted, fontSize: FONT.size.sm }}>Current</th>
            <th style={{ textAlign: "left", padding: 8, color: THEME.text.muted, fontSize: FONT.size.sm }}>New</th>
            <th style={{ textAlign: "center", padding: 8, color: THEME.text.muted, fontSize: FONT.size.sm }}>Risk</th>
          </tr>
        </thead>
        <tbody>
          {diffs.map((diff, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${THEME.border.default}` }}>
              <td style={{ padding: 8, fontFamily: FONT.mono, fontSize: FONT.size.sm, color: THEME.text.secondary }}>
                {diff.field}
              </td>
              <td style={{ padding: 8, fontFamily: FONT.mono, fontSize: FONT.size.sm, color: THEME.state.error }}>
                {JSON.stringify(diff.current_value)}
              </td>
              <td style={{ padding: 8, fontFamily: FONT.mono, fontSize: FONT.size.sm, color: THEME.state.success }}>
                {JSON.stringify(diff.new_value)}
              </td>
              <td style={{ padding: 8, textAlign: "center" }}>
                <Badge type={diff.risk_level}>{diff.risk_level}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
};

// ============================================================
// 📝 REASON INPUT COMPONENT
// ============================================================

const ReasonInput = ({ value, onChange, error }) => (
  <Card title="📝 Change Reason (Required)" subtitle="Why are you making this change? This will be recorded in the audit log.">
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Explain why you are making these changes (min 10 characters)..."
      style={{
        width: "100%",
        minHeight: 80,
        padding: 12,
        background: THEME.bg.input,
        border: `1px solid ${error ? THEME.border.error : THEME.border.default}`,
        borderRadius: 6,
        color: THEME.text.primary,
        fontSize: FONT.size.base,
        fontFamily: FONT.family,
        resize: "vertical",
        outline: "none",
        boxSizing: "border-box",
      }}
    />
    {error && (
      <div style={{ color: THEME.state.error, fontSize: FONT.size.xs, marginTop: 4 }}>
        {error}
      </div>
    )}
    <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginTop: 4 }}>
      {value.length}/500 characters (minimum 10)
    </div>
  </Card>
);

// ============================================================
// 🏛️ MAIN CONFIG EDITOR
// ============================================================

export function ConfigEditor({ config, onSave, loading }) {
  const [mode, setMode] = useState("form"); // "form" | "json"
  const [formData, setFormData] = useState({});
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState(null);
  const [pendingChanges, setPendingChanges] = useState({});
  const [diffs, setDiffs] = useState([]);
  const [guardianValidation, setGuardianValidation] = useState(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  
  // Initialize form data from config
  useEffect(() => {
    if (config) {
      setFormData({
        // Risk Budget
        risk_budget_core_pct: config.risk_budget?.core_pct || 60,
        risk_budget_edge_pct: config.risk_budget?.edge_pct || 40,
        
        // Guardian
        guardian_daily_loss_limit_pct: config.guardian?.daily_loss_limit_pct || -2,
        guardian_weekly_drawdown_limit_pct: config.guardian?.weekly_drawdown_limit_pct || -5,
        guardian_max_spread_pct: config.guardian?.max_spread_pct || 0.15,
        guardian_max_slippage_pct: config.guardian?.max_slippage_pct || 0.10,
        guardian_cooldown_after_loss_minutes: config.guardian?.cooldown_after_loss_minutes || 30,
        guardian_pause_on_spread_widening: config.guardian?.pause_on_spread_widening ?? true,
        guardian_pause_on_high_latency: config.guardian?.pause_on_high_latency ?? true,
        
        // Concurrency
        concurrency_allow_only_one_primary: config.concurrency?.allow_only_one_primary ?? true,
        concurrency_max_concurrent_agents: config.concurrency?.max_concurrent_agents || 1,
        
        // Defaults
        defaults_default_capital_eur: config.defaults?.default_capital_eur || 100,
        defaults_default_mode: config.defaults?.default_mode || "paper",
      });
      setJsonText(JSON.stringify(config, null, 2));
    }
  }, [config]);
  
  // Track changes
  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    
    // Map form field to config path
    const pathMap = {
      risk_budget_core_pct: "risk_budget.core_pct",
      risk_budget_edge_pct: "risk_budget.edge_pct",
      guardian_daily_loss_limit_pct: "guardian.daily_loss_limit_pct",
      guardian_weekly_drawdown_limit_pct: "guardian.weekly_drawdown_limit_pct",
      guardian_max_spread_pct: "guardian.max_spread_pct",
      guardian_max_slippage_pct: "guardian.max_slippage_pct",
      guardian_cooldown_after_loss_minutes: "guardian.cooldown_after_loss_minutes",
      guardian_pause_on_spread_widening: "guardian.pause_on_spread_widening",
      guardian_pause_on_high_latency: "guardian.pause_on_high_latency",
      concurrency_allow_only_one_primary: "concurrency.allow_only_one_primary",
      concurrency_max_concurrent_agents: "concurrency.max_concurrent_agents",
      defaults_default_capital_eur: "defaults.default_capital_eur",
      defaults_default_mode: "defaults.default_mode",
    };
    
    const path = pathMap[field];
    if (path) {
      setPendingChanges(prev => ({ ...prev, [path]: value }));
    }
    
    // Clear success message
    setSaveSuccess(false);
  };
  
  // Preview changes
  const previewChanges = useCallback(async () => {
    if (Object.keys(pendingChanges).length === 0) {
      setDiffs([]);
      setGuardianValidation(null);
      return;
    }
    
    try {
      const res = await api.post("/config/system/diff", { updates: pendingChanges });
      setDiffs(res.data.diffs || []);
      setGuardianValidation(res.data.guardian_validation || null);
    } catch (e) {
      console.error("Failed to preview changes:", e);
    }
  }, [pendingChanges]);
  
  useEffect(() => {
    previewChanges();
  }, [previewChanges]);
  
  // JSON mode validation
  const handleJsonChange = (text) => {
    setJsonText(text);
    setJsonError(null);
    
    try {
      const parsed = JSON.parse(text);
      // Calculate diff from original
      const changes = {};
      // Deep comparison would go here
      setPendingChanges(changes);
    } catch (e) {
      setJsonError("Invalid JSON");
    }
  };
  
  // Save changes
  const handleSave = async () => {
    // Validate reason
    if (!reason || reason.length < 10) {
      setReasonError("Reason must be at least 10 characters");
      return;
    }
    
    // Check Guardian
    if (guardianValidation && !guardianValidation.allowed) {
      setSaveError("Guardian has blocked these changes");
      return;
    }
    
    setSaving(true);
    setSaveError(null);
    
    try {
      await api.put("/config/system", {
        updates: pendingChanges,
        reason: reason,
        reason_code: "MANUAL_ADJUSTMENT",
      });
      
      setSaveSuccess(true);
      setPendingChanges({});
      setDiffs([]);
      setReason("");
      
      // Refresh config
      if (onSave) {
        onSave();
      }
    } catch (e) {
      setSaveError(e.response?.data?.detail?.message || e.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };
  
  const hasChanges = Object.keys(pendingChanges).length > 0;
  
  return (
    <div>
      <Card
        title="⚙ System Configuration"
        subtitle="Configure risk limits, Guardian thresholds, and trading parameters"
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <TabButton active={mode === "form"} onClick={() => setMode("form")}>Form</TabButton>
            <TabButton active={mode === "json"} onClick={() => setMode("json")}>JSON</TabButton>
          </div>
        }
      >
        {mode === "form" ? (
          <div>
            {/* Risk Budget Section */}
            <div style={{ marginBottom: 24 }}>
              <h4 style={{ color: THEME.text.primary, marginBottom: 12, fontSize: FONT.size.base }}>
                Risk Budget Allocation
              </h4>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Input
                  label="Core Bucket %"
                  type="number"
                  value={formData.risk_budget_core_pct || 60}
                  onChange={(v) => handleFormChange("risk_budget_core_pct", v)}
                  description="Steady gains (Market Maker)"
                />
                <Input
                  label="Edge Bucket %"
                  type="number"
                  value={formData.risk_budget_edge_pct || 40}
                  onChange={(v) => handleFormChange("risk_budget_edge_pct", v)}
                  description="Acceleration (Momentum)"
                />
              </div>
            </div>
            
            {/* Guardian Section */}
            <div style={{ marginBottom: 24 }}>
              <h4 style={{ color: THEME.text.primary, marginBottom: 12, fontSize: FONT.size.base }}>
                Guardian Limits (Capital Protection)
              </h4>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Input
                  label="Daily Loss Limit %"
                  type="number"
                  value={formData.guardian_daily_loss_limit_pct || -2}
                  onChange={(v) => handleFormChange("guardian_daily_loss_limit_pct", v)}
                  description="Kill switch trigger (e.g., -2%)"
                />
                <Input
                  label="Weekly Drawdown Limit %"
                  type="number"
                  value={formData.guardian_weekly_drawdown_limit_pct || -5}
                  onChange={(v) => handleFormChange("guardian_weekly_drawdown_limit_pct", v)}
                  description="Weekly cap (e.g., -5%)"
                />
                <Input
                  label="Max Spread %"
                  type="number"
                  value={formData.guardian_max_spread_pct || 0.15}
                  onChange={(v) => handleFormChange("guardian_max_spread_pct", v)}
                  description="Block if spread exceeds"
                />
                <Input
                  label="Max Slippage %"
                  type="number"
                  value={formData.guardian_max_slippage_pct || 0.10}
                  onChange={(v) => handleFormChange("guardian_max_slippage_pct", v)}
                  description="Expected slippage estimate"
                />
                <Input
                  label="Cooldown After Loss (min)"
                  type="number"
                  value={formData.guardian_cooldown_after_loss_minutes || 30}
                  onChange={(v) => handleFormChange("guardian_cooldown_after_loss_minutes", v)}
                  description="Pause after hitting daily limit"
                />
              </div>
              <div style={{ marginTop: 16 }}>
                <Toggle
                  label="Pause on Spread Widening"
                  checked={formData.guardian_pause_on_spread_widening ?? true}
                  onChange={(v) => handleFormChange("guardian_pause_on_spread_widening", v)}
                  description="Pause trading if spread widens suddenly"
                />
                <Toggle
                  label="Pause on High Latency"
                  checked={formData.guardian_pause_on_high_latency ?? true}
                  onChange={(v) => handleFormChange("guardian_pause_on_high_latency", v)}
                  description="Pause if data quality drops"
                />
              </div>
            </div>
            
            {/* Concurrency Section */}
            <div style={{ marginBottom: 24 }}>
              <h4 style={{ color: THEME.text.primary, marginBottom: 12, fontSize: FONT.size.base }}>
                Agent Concurrency
              </h4>
              <Toggle
                label="Single Agent Only"
                checked={formData.concurrency_allow_only_one_primary ?? true}
                onChange={(v) => handleFormChange("concurrency_allow_only_one_primary", v)}
                description="Allow MM OR MOM, not both simultaneously"
              />
              <Input
                label="Max Concurrent Agents"
                type="number"
                value={formData.concurrency_max_concurrent_agents || 1}
                onChange={(v) => handleFormChange("concurrency_max_concurrent_agents", v)}
                description="Maximum agents running at once"
              />
            </div>
            
            {/* Defaults Section */}
            <div>
              <h4 style={{ color: THEME.text.primary, marginBottom: 12, fontSize: FONT.size.base }}>
                Default Settings
              </h4>
              <Input
                label="Default Capital (EUR)"
                type="number"
                value={formData.defaults_default_capital_eur || 100}
                onChange={(v) => handleFormChange("defaults_default_capital_eur", v)}
                description="Starting capital for new runs"
              />
            </div>
          </div>
        ) : (
          <div>
            <textarea
              value={jsonText}
              onChange={(e) => handleJsonChange(e.target.value)}
              style={{
                width: "100%",
                minHeight: 400,
                padding: 12,
                background: THEME.bg.input,
                border: `1px solid ${jsonError ? THEME.border.error : THEME.border.default}`,
                borderRadius: 6,
                color: THEME.text.primary,
                fontSize: FONT.size.sm,
                fontFamily: FONT.mono,
                resize: "vertical",
                outline: "none",
                boxSizing: "border-box",
              }}
            />
            {jsonError && (
              <div style={{ color: THEME.state.error, fontSize: FONT.size.xs, marginTop: 4 }}>
                {jsonError}
              </div>
            )}
          </div>
        )}
      </Card>
      
      {/* Diff Preview */}
      {hasChanges && (
        <DiffView diffs={diffs} guardianValidation={guardianValidation} />
      )}
      
      {/* Reason Input */}
      {hasChanges && (
        <ReasonInput 
          value={reason} 
          onChange={(v) => { setReason(v); setReasonError(null); }} 
          error={reasonError}
        />
      )}
      
      {/* Save Actions */}
      {hasChanges && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <span style={{ color: THEME.text.secondary }}>
                {Object.keys(pendingChanges).length} change(s) pending
              </span>
              {saveError && (
                <div style={{ color: THEME.state.error, fontSize: FONT.size.sm, marginTop: 4 }}>
                  {saveError}
                </div>
              )}
              {saveSuccess && (
                <div style={{ color: THEME.state.success, fontSize: FONT.size.sm, marginTop: 4 }}>
                  ✓ Configuration saved successfully
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <Button
                variant="secondary"
                onClick={() => {
                  setPendingChanges({});
                  setDiffs([]);
                  setReason("");
                  // Reset form to original
                  if (config) {
                    setFormData({
                      risk_budget_core_pct: config.risk_budget?.core_pct || 60,
                      risk_budget_edge_pct: config.risk_budget?.edge_pct || 40,
                      guardian_daily_loss_limit_pct: config.guardian?.daily_loss_limit_pct || -2,
                      guardian_weekly_drawdown_limit_pct: config.guardian?.weekly_drawdown_limit_pct || -5,
                      guardian_max_spread_pct: config.guardian?.max_spread_pct || 0.15,
                      guardian_max_slippage_pct: config.guardian?.max_slippage_pct || 0.10,
                      guardian_cooldown_after_loss_minutes: config.guardian?.cooldown_after_loss_minutes || 30,
                      guardian_pause_on_spread_widening: config.guardian?.pause_on_spread_widening ?? true,
                      guardian_pause_on_high_latency: config.guardian?.pause_on_high_latency ?? true,
                      concurrency_allow_only_one_primary: config.concurrency?.allow_only_one_primary ?? true,
                      concurrency_max_concurrent_agents: config.concurrency?.max_concurrent_agents || 1,
                      defaults_default_capital_eur: config.defaults?.default_capital_eur || 100,
                    });
                  }
                }}
              >
                Discard Changes
              </Button>
              <Button
                onClick={handleSave}
                disabled={saving || (guardianValidation && !guardianValidation.allowed)}
              >
                {saving ? "Saving..." : "Save Configuration"}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ============================================================
// 🎛️ PRESET EDITOR MODAL
// ============================================================

export function PresetEditor({ preset, type, onSave, onClose, loading }) {
  const [mode, setMode] = useState("form");
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [editedPreset, setEditedPreset] = useState(null);
  
  useEffect(() => {
    if (preset) {
      setEditedPreset({ ...preset });
      setJsonText(JSON.stringify(preset, null, 2));
    }
  }, [preset]);
  
  const handleSave = async () => {
    if (!reason || reason.length < 10) {
      setReasonError("Reason must be at least 10 characters");
      return;
    }
    
    if (mode === "json") {
      try {
        const parsed = JSON.parse(jsonText);
        setEditedPreset(parsed);
      } catch (e) {
        setJsonError("Invalid JSON");
        return;
      }
    }
    
    setSaving(true);
    
    try {
      await api.put(`/config/presets/${type.toLowerCase()}/${preset.id}`, {
        preset_data: editedPreset,
        reason: reason,
        reason_code: "PRESET_ADJUSTMENT",
      });
      onSave(editedPreset);
    } catch (e) {
      setReasonError(e.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };
  
  if (!preset) return null;
  
  const isSystem = preset.preset_type === "system";
  
  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.8)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }}>
      <div style={{
        background: THEME.bg.app,
        borderRadius: 8,
        width: "90%",
        maxWidth: 700,
        maxHeight: "90vh",
        overflow: "auto",
        padding: 24,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <h2 style={{ margin: 0, color: THEME.text.primary }}>
              Edit Preset: {preset.name}
            </h2>
            <div style={{ color: THEME.text.muted, fontSize: FONT.size.sm, marginTop: 4 }}>
              {type.toUpperCase()} • {preset.id}
            </div>
          </div>
          <Button variant="secondary" onClick={onClose}>✕</Button>
        </div>
        
        {isSystem && (
          <div style={{
            padding: 12,
            marginBottom: 16,
            background: `${THEME.state.warning}15`,
            border: `1px solid ${THEME.state.warning}40`,
            borderRadius: 6,
            color: THEME.state.warning,
            fontSize: FONT.size.sm,
          }}>
            ⚠ This is a system preset. To modify it, please clone it first to create a custom version.
          </div>
        )}
        
        <div style={{ marginBottom: 16 }}>
          <TabButton active={mode === "form"} onClick={() => setMode("form")}>Form</TabButton>
          <TabButton active={mode === "json"} onClick={() => setMode("json")}>JSON</TabButton>
        </div>
        
        {mode === "json" ? (
          <textarea
            value={jsonText}
            onChange={(e) => { setJsonText(e.target.value); setJsonError(null); }}
            disabled={isSystem}
            style={{
              width: "100%",
              minHeight: 300,
              padding: 12,
              background: THEME.bg.input,
              border: `1px solid ${jsonError ? THEME.border.error : THEME.border.default}`,
              borderRadius: 6,
              color: THEME.text.primary,
              fontSize: FONT.size.sm,
              fontFamily: FONT.mono,
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
              opacity: isSystem ? 0.6 : 1,
            }}
          />
        ) : (
          <div style={{ color: THEME.text.secondary, padding: 20, textAlign: "center" }}>
            Form editor for presets coming soon. Use JSON mode for now.
          </div>
        )}
        
        {!isSystem && (
          <>
            <div style={{ marginTop: 16 }}>
              <ReasonInput 
                value={reason} 
                onChange={(v) => { setReason(v); setReasonError(null); }}
                error={reasonError}
              />
            </div>
            
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 16 }}>
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : "Save Preset"}
              </Button>
            </div>
          </>
        )}
        
        {isSystem && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={onClose}>Close</Button>
            <Button onClick={async () => {
              try {
                const res = await api.post(`/config/presets/${type.toLowerCase()}/clone/${preset.id}`, null, {
                  params: { new_name: `${preset.name} (Custom)` }
                });
                onClose();
                // Could trigger a refresh here
              } catch (e) {
                console.error("Clone failed:", e);
              }
            }}>
              Clone to Custom
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ConfigEditor;
