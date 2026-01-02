/**
 * HAVEN Audit Dashboard — P3.3
 * =============================
 * 
 * Displays audit logs for all system actions:
 * - Configuration changes
 * - User actions (login, role changes)
 * - Trading actions (kill switch, mode changes)
 * - Preset modifications
 * 
 * Features:
 * - Filterable by action type, user, date range
 * - Paginated results
 * - Color-coded severity
 * - Expandable details for before/after diff
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
    inverse: "#0B0E11",
  },
  state: {
    safe: "#0ECB81",
    caution: "#F0B90B",
    blocked: "#F6465D",
    info: "#1E90FF",
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
  },
};

// ============================================================
// 🏷️ ACTION CATEGORIES & STYLING
// ============================================================

const ACTION_CATEGORIES = {
  // Security - Critical actions
  "user.login_failed": { category: "security", severity: "warning", icon: "🔐", label: "Failed Login" },
  "user.role_change": { category: "security", severity: "critical", icon: "👤", label: "Role Changed" },
  "user.password_reset": { category: "security", severity: "warning", icon: "🔑", label: "Password Reset" },
  "system.kill_switch_activate": { category: "security", severity: "critical", icon: "⛔", label: "Kill Switch ON" },
  "system.kill_switch_deactivate": { category: "security", severity: "info", icon: "✅", label: "Kill Switch OFF" },
  
  // User management
  "user.create": { category: "user", severity: "info", icon: "➕", label: "User Created" },
  "user.update": { category: "user", severity: "info", icon: "✏️", label: "User Updated" },
  "user.delete": { category: "user", severity: "warning", icon: "🗑️", label: "User Deleted" },
  "user.login": { category: "user", severity: "info", icon: "🔓", label: "Login" },
  "user.activate": { category: "user", severity: "info", icon: "✅", label: "User Activated" },
  "user.deactivate": { category: "user", severity: "warning", icon: "⏸️", label: "User Deactivated" },
  
  // Settings
  "settings.update": { category: "config", severity: "info", icon: "⚙️", label: "Settings Updated" },
  "settings.trading_mode_change": { category: "config", severity: "critical", icon: "🔄", label: "Trading Mode Changed" },
  "settings.risk_update": { category: "config", severity: "warning", icon: "⚠️", label: "Risk Settings" },
  
  // Presets
  "preset.save": { category: "preset", severity: "info", icon: "💾", label: "Preset Saved" },
  "preset.delete": { category: "preset", severity: "warning", icon: "🗑️", label: "Preset Deleted" },
  "preset.apply": { category: "preset", severity: "info", icon: "📋", label: "Preset Applied" },
  
  // Agent management
  "agent.create": { category: "agent", severity: "info", icon: "🤖", label: "Agent Created" },
  "agent.update": { category: "agent", severity: "info", icon: "✏️", label: "Agent Updated" },
  "agent.delete": { category: "agent", severity: "warning", icon: "🗑️", label: "Agent Deleted" },
  "agent.start": { category: "agent", severity: "info", icon: "▶️", label: "Agent Started" },
  "agent.stop": { category: "agent", severity: "info", icon: "⏹️", label: "Agent Stopped" },
  
  // Trading actions
  "swap.plan_create": { category: "trading", severity: "info", icon: "📝", label: "Plan Created" },
  "swap.approve": { category: "trading", severity: "info", icon: "✅", label: "Swap Approved" },
  "swap.reject": { category: "trading", severity: "warning", icon: "❌", label: "Swap Rejected" },
  "swap.execute": { category: "trading", severity: "info", icon: "💱", label: "Swap Executed" },
  "position.close": { category: "trading", severity: "info", icon: "📊", label: "Position Closed" },
  
  // System
  "system.runtime_start": { category: "system", severity: "info", icon: "🚀", label: "Runtime Started" },
  "system.runtime_stop": { category: "system", severity: "warning", icon: "⏹️", label: "Runtime Stopped" },
  
  // Scheduler
  "schedule.start": { category: "system", severity: "info", icon: "⏰", label: "Schedule Started" },
  "schedule.stop": { category: "system", severity: "info", icon: "⏹️", label: "Schedule Stopped" },
  
  // Sniper
  "sniper.start": { category: "sniper", severity: "info", icon: "🎯", label: "Sniper Started" },
  "sniper.stop": { category: "sniper", severity: "info", icon: "⏹️", label: "Sniper Stopped" },
  "sniper.config_update": { category: "sniper", severity: "info", icon: "⚙️", label: "Sniper Config" },
  
  // Credentials
  "credential.store": { category: "security", severity: "warning", icon: "🔐", label: "Credential Stored" },
  "credential.delete": { category: "security", severity: "warning", icon: "🗑️", label: "Credential Deleted" },
};

const SEVERITY_STYLES = {
  critical: { bg: `${THEME.state.blocked}15`, border: `${THEME.state.blocked}40`, text: THEME.state.blocked },
  warning: { bg: `${THEME.state.caution}15`, border: `${THEME.state.caution}40`, text: THEME.state.caution },
  info: { bg: `${THEME.state.info}15`, border: `${THEME.state.info}40`, text: THEME.state.info },
};

const CATEGORY_COLORS = {
  security: THEME.state.blocked,
  user: THEME.state.info,
  config: THEME.state.caution,
  preset: "#9B59B6",
  agent: "#3498DB",
  trading: THEME.state.safe,
  system: "#95A5A6",
  sniper: "#E67E22",
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

const FilterSelect = ({ label, value, onChange, options }) => (
  <div style={{ marginRight: 12 }}>
    <label style={{ display: "block", fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>
      {label}
    </label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        padding: "6px 10px",
        background: THEME.bg.elevated,
        border: `1px solid ${THEME.border.default}`,
        borderRadius: 4,
        color: THEME.text.primary,
        fontSize: FONT.size.sm,
        minWidth: 150,
        cursor: "pointer",
      }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  </div>
);

// ============================================================
// 📝 AUDIT LOG ENTRY
// ============================================================

const AuditLogEntry = ({ log, expanded, onToggle }) => {
  const actionInfo = ACTION_CATEGORIES[log.action] || {
    category: "unknown",
    severity: "info",
    icon: "📋",
    label: log.action,
  };
  
  const severityStyle = SEVERITY_STYLES[actionInfo.severity] || SEVERITY_STYLES.info;
  const categoryColor = CATEGORY_COLORS[actionInfo.category] || THEME.text.muted;
  
  const timestamp = new Date(log.ts).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  
  return (
    <div
      style={{
        marginBottom: 8,
        background: severityStyle.bg,
        border: `1px solid ${severityStyle.border}`,
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      {/* Header row - clickable */}
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          padding: "12px 16px",
          cursor: "pointer",
          gap: 12,
        }}
      >
        {/* Icon */}
        <span style={{ fontSize: "18px" }}>{actionInfo.icon}</span>
        
        {/* Main content */}
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontWeight: 600, color: THEME.text.primary, fontSize: FONT.size.sm }}>
              {actionInfo.label}
            </span>
            <span
              style={{
                padding: "2px 6px",
                background: `${categoryColor}20`,
                color: categoryColor,
                fontSize: FONT.size.xs,
                borderRadius: 3,
                fontWeight: 500,
              }}
            >
              {actionInfo.category.toUpperCase()}
            </span>
            {!log.success && (
              <span
                style={{
                  padding: "2px 6px",
                  background: `${THEME.state.blocked}20`,
                  color: THEME.state.blocked,
                  fontSize: FONT.size.xs,
                  borderRadius: 3,
                  fontWeight: 500,
                }}
              >
                FAILED
              </span>
            )}
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: FONT.size.xs, color: THEME.text.muted }}>
            <span>👤 {log.username} ({log.role})</span>
            {log.resource_type && (
              <span>📁 {log.resource_type}{log.resource_id ? `/${log.resource_id}` : ""}</span>
            )}
            <span>🌐 {log.ip}</span>
          </div>
        </div>
        
        {/* Timestamp */}
        <div style={{ textAlign: "right" }}>
          <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
            {timestamp}
          </div>
        </div>
        
        {/* Expand indicator */}
        <span style={{ color: THEME.text.muted, fontSize: FONT.size.sm }}>
          {expanded ? "▼" : "▶"}
        </span>
      </div>
      
      {/* Expanded details */}
      {expanded && (
        <div
          style={{
            padding: "0 16px 16px",
            borderTop: `1px solid ${THEME.border.default}`,
            marginTop: 0,
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 12 }}>
            {/* Before */}
            {log.before && Object.keys(log.before).length > 0 && (
              <div>
                <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 8 }}>
                  BEFORE
                </div>
                <pre
                  style={{
                    margin: 0,
                    padding: 12,
                    background: THEME.bg.elevated,
                    borderRadius: 4,
                    fontSize: FONT.size.xs,
                    fontFamily: FONT.mono,
                    color: THEME.text.secondary,
                    overflow: "auto",
                    maxHeight: 200,
                  }}
                >
                  {JSON.stringify(log.before, null, 2)}
                </pre>
              </div>
            )}
            
            {/* After */}
            {log.after && Object.keys(log.after).length > 0 && (
              <div>
                <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 8 }}>
                  AFTER
                </div>
                <pre
                  style={{
                    margin: 0,
                    padding: 12,
                    background: THEME.bg.elevated,
                    borderRadius: 4,
                    fontSize: FONT.size.xs,
                    fontFamily: FONT.mono,
                    color: THEME.text.secondary,
                    overflow: "auto",
                    maxHeight: 200,
                  }}
                >
                  {JSON.stringify(log.after, null, 2)}
                </pre>
              </div>
            )}
          </div>
          
          {/* Error message if failed */}
          {log.error && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: `${THEME.state.blocked}10`,
                borderRadius: 4,
                color: THEME.state.blocked,
                fontSize: FONT.size.sm,
              }}
            >
              <strong>Error:</strong> {log.error}
            </div>
          )}
          
          {/* Metadata */}
          {log.metadata && Object.keys(log.metadata).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs, marginBottom: 8 }}>
                METADATA
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  background: THEME.bg.elevated,
                  borderRadius: 4,
                  fontSize: FONT.size.xs,
                  fontFamily: FONT.mono,
                  color: THEME.text.secondary,
                  overflow: "auto",
                  maxHeight: 150,
                }}
              >
                {JSON.stringify(log.metadata, null, 2)}
              </pre>
            </div>
          )}
          
          {/* Correlation ID */}
          {log.correlation_id && (
            <div style={{ marginTop: 12, fontSize: FONT.size.xs, color: THEME.text.muted }}>
              <strong>Correlation ID:</strong> {log.correlation_id}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================
// 📊 STATS PANEL
// ============================================================

const StatsPanel = ({ logs }) => {
  // Calculate stats
  const stats = {
    total: logs.length,
    byCategory: {},
    bySeverity: { critical: 0, warning: 0, info: 0 },
    failed: 0,
    uniqueUsers: new Set(),
  };
  
  logs.forEach((log) => {
    const actionInfo = ACTION_CATEGORIES[log.action] || { category: "unknown", severity: "info" };
    stats.byCategory[actionInfo.category] = (stats.byCategory[actionInfo.category] || 0) + 1;
    stats.bySeverity[actionInfo.severity] = (stats.bySeverity[actionInfo.severity] || 0) + 1;
    if (!log.success) stats.failed++;
    stats.uniqueUsers.add(log.user_id);
  });
  
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 16 }}>
      <div
        style={{
          padding: 12,
          background: THEME.bg.elevated,
          borderRadius: 6,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>TOTAL</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: THEME.text.primary }}>{stats.total}</div>
      </div>
      
      <div
        style={{
          padding: 12,
          background: `${THEME.state.blocked}10`,
          borderRadius: 6,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>CRITICAL</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: THEME.state.blocked }}>{stats.bySeverity.critical}</div>
      </div>
      
      <div
        style={{
          padding: 12,
          background: `${THEME.state.caution}10`,
          borderRadius: 6,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>WARNING</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: THEME.state.caution }}>{stats.bySeverity.warning}</div>
      </div>
      
      <div
        style={{
          padding: 12,
          background: `${THEME.state.blocked}10`,
          borderRadius: 6,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>FAILED</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: THEME.state.blocked }}>{stats.failed}</div>
      </div>
      
      <div
        style={{
          padding: 12,
          background: `${THEME.state.info}10`,
          borderRadius: 6,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>USERS</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: THEME.state.info }}>{stats.uniqueUsers.size}</div>
      </div>
    </div>
  );
};

// ============================================================
// 🏛️ MAIN AUDIT DASHBOARD COMPONENT
// ============================================================

export function AuditDashboard() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  
  // Filters
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterAction, setFilterAction] = useState("all");
  const [filterUser, setFilterUser] = useState("");
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  
  const LIMIT = 50;
  
  // Fetch audit logs
  const fetchLogs = useCallback(async (reset = false) => {
    try {
      setLoading(true);
      setError(null);
      
      const skip = reset ? 0 : page * LIMIT;
      const params = new URLSearchParams();
      params.append("limit", LIMIT);
      params.append("skip", skip);
      
      if (filterAction !== "all") {
        params.append("action", filterAction);
      }
      
      const res = await api.get(`/admin/audit?${params.toString()}`);
      
      if (reset) {
        setLogs(res.data);
        setPage(0);
      } else {
        setLogs((prev) => [...prev, ...res.data]);
      }
      
      setHasMore(res.data.length === LIMIT);
    } catch (e) {
      console.error("Failed to fetch audit logs:", e);
      setError(e.response?.data?.detail || "Failed to fetch audit logs");
    } finally {
      setLoading(false);
    }
  }, [filterAction, page]);
  
  // Initial fetch
  useEffect(() => {
    fetchLogs(true);
  }, [filterAction]); // eslint-disable-line react-hooks/exhaustive-deps
  
  // Filter logs by category (client-side)
  const filteredLogs = logs.filter((log) => {
    if (filterCategory === "all") return true;
    const actionInfo = ACTION_CATEGORIES[log.action] || { category: "unknown" };
    return actionInfo.category === filterCategory;
  }).filter((log) => {
    if (!filterUser) return true;
    return log.username.toLowerCase().includes(filterUser.toLowerCase());
  });
  
  // Get unique categories from current logs
  const categories = ["all", ...new Set(
    Object.values(ACTION_CATEGORIES).map((a) => a.category)
  )];
  
  // Get unique actions
  const actions = ["all", ...new Set(
    Object.keys(ACTION_CATEGORIES)
  )];
  
  const loadMore = () => {
    setPage((prev) => prev + 1);
    fetchLogs(false);
  };
  
  return (
    <div>
      <Card
        title="📋 Audit Dashboard"
        subtitle="Track all system actions and configuration changes"
        right={
          <button
            onClick={() => fetchLogs(true)}
            style={{
              padding: "6px 12px",
              background: THEME.bg.elevated,
              border: `1px solid ${THEME.border.default}`,
              borderRadius: 4,
              color: THEME.text.secondary,
              fontSize: FONT.size.sm,
              cursor: "pointer",
            }}
          >
            🔄 Refresh
          </button>
        }
      >
        {/* Stats */}
        <StatsPanel logs={filteredLogs} />
        
        {/* Filters */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            marginBottom: 16,
            padding: 12,
            background: THEME.bg.elevated,
            borderRadius: 6,
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <FilterSelect
            label="Category"
            value={filterCategory}
            onChange={setFilterCategory}
            options={categories.map((c) => ({
              value: c,
              label: c === "all" ? "All Categories" : c.charAt(0).toUpperCase() + c.slice(1),
            }))}
          />
          
          <FilterSelect
            label="Action"
            value={filterAction}
            onChange={(v) => {
              setFilterAction(v);
              setPage(0);
            }}
            options={actions.map((a) => ({
              value: a,
              label: a === "all" ? "All Actions" : (ACTION_CATEGORIES[a]?.label || a),
            }))}
          />
          
          <div style={{ marginRight: 12 }}>
            <label style={{ display: "block", fontSize: FONT.size.xs, color: THEME.text.muted, marginBottom: 4 }}>
              Username
            </label>
            <input
              type="text"
              value={filterUser}
              onChange={(e) => setFilterUser(e.target.value)}
              placeholder="Filter by user..."
              style={{
                padding: "6px 10px",
                background: THEME.bg.card,
                border: `1px solid ${THEME.border.default}`,
                borderRadius: 4,
                color: THEME.text.primary,
                fontSize: FONT.size.sm,
                minWidth: 150,
              }}
            />
          </div>
          
          <div style={{ flex: 1 }} />
          
          <div style={{ fontSize: FONT.size.xs, color: THEME.text.muted }}>
            Showing {filteredLogs.length} of {logs.length} entries
          </div>
        </div>
        
        {/* Error message */}
        {error && (
          <div
            style={{
              padding: 12,
              marginBottom: 16,
              background: `${THEME.state.blocked}15`,
              border: `1px solid ${THEME.state.blocked}40`,
              borderRadius: 6,
              color: THEME.state.blocked,
            }}
          >
            ⚠️ {error}
          </div>
        )}
        
        {/* Loading state */}
        {loading && logs.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: THEME.text.muted }}>
            Loading audit logs...
          </div>
        )}
        
        {/* Empty state */}
        {!loading && filteredLogs.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: THEME.text.muted }}>
            No audit logs found
          </div>
        )}
        
        {/* Log entries */}
        <div style={{ maxHeight: 600, overflow: "auto" }}>
          {filteredLogs.map((log) => (
            <AuditLogEntry
              key={log.id}
              log={log}
              expanded={expandedId === log.id}
              onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
            />
          ))}
        </div>
        
        {/* Load more button */}
        {hasMore && !loading && (
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <button
              onClick={loadMore}
              style={{
                padding: "10px 24px",
                background: THEME.bg.elevated,
                border: `1px solid ${THEME.border.default}`,
                borderRadius: 6,
                color: THEME.text.primary,
                fontSize: FONT.size.sm,
                cursor: "pointer",
              }}
            >
              Load More
            </button>
          </div>
        )}
        
        {/* Loading indicator for pagination */}
        {loading && logs.length > 0 && (
          <div style={{ textAlign: "center", padding: 16, color: THEME.text.muted }}>
            Loading more...
          </div>
        )}
      </Card>
      
      {/* Security Events Quick Panel */}
      <SecurityEventsPanel />
    </div>
  );
}

// ============================================================
// 🔐 SECURITY EVENTS QUICK PANEL
// ============================================================

function SecurityEventsPanel() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    async function fetchSecurityEvents() {
      try {
        const res = await api.get("/admin/audit/security?limit=10");
        setEvents(res.data);
      } catch (e) {
        console.error("Failed to fetch security events:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchSecurityEvents();
  }, []);
  
  if (loading) {
    return (
      <Card title="🔐 Security Events" subtitle="Recent security-related actions">
        <div style={{ textAlign: "center", padding: 20, color: THEME.text.muted }}>
          Loading...
        </div>
      </Card>
    );
  }
  
  if (events.length === 0) {
    return (
      <Card title="🔐 Security Events" subtitle="Recent security-related actions">
        <div style={{ textAlign: "center", padding: 20, color: THEME.text.muted }}>
          No recent security events
        </div>
      </Card>
    );
  }
  
  return (
    <Card title="🔐 Security Events" subtitle="Recent security-related actions (last 10)">
      <div style={{ maxHeight: 300, overflow: "auto" }}>
        {events.map((event, i) => {
          const actionInfo = ACTION_CATEGORIES[event.action] || {
            icon: "🔐",
            label: event.action,
            severity: "warning",
          };
          const severityStyle = SEVERITY_STYLES[actionInfo.severity] || SEVERITY_STYLES.warning;
          
          return (
            <div
              key={event.id || i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 12px",
                marginBottom: 6,
                background: severityStyle.bg,
                border: `1px solid ${severityStyle.border}`,
                borderRadius: 4,
              }}
            >
              <span style={{ fontSize: "16px" }}>{actionInfo.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ color: THEME.text.primary, fontSize: FONT.size.sm, fontWeight: 500 }}>
                  {actionInfo.label}
                </div>
                <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
                  {event.username} • {event.ip}
                </div>
              </div>
              <div style={{ color: THEME.text.muted, fontSize: FONT.size.xs }}>
                {new Date(event.ts).toLocaleTimeString("en-GB")}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export default AuditDashboard;
