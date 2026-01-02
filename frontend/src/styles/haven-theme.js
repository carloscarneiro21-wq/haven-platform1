/**
 * HAVEN Design System
 * ====================
 * 
 * Binance-inspired design system for HAVEN
 * "Built to Survive Markets"
 * 
 * Core Principles:
 * - Minimal & Institutional
 * - Zero aggressive animations
 * - Information > Aesthetics
 * - Color = Functional State (never decoration)
 */

// ============================================================
// 🎨 COLOR PALETTE
// ============================================================

export const HAVEN_COLORS = {
  // Backgrounds
  bg: {
    app: "#0B0E11",        // App background
    sidebar: "#161A1E",     // Sidebar / Topbar
    card: "#1E2329",        // Cards / Panels
    hover: "#2B3139",       // Hover states
    elevated: "#252A31",    // Elevated surfaces
  },
  
  // Text
  text: {
    primary: "#EAECEF",     // Main text
    secondary: "#B7BDC6",   // Secondary text
    muted: "#848E9C",       // Muted / explanations
    inverse: "#0B0E11",     // Text on light backgrounds
  },
  
  // States (Color = functional state, never decoration)
  state: {
    ok: "#0ECB81",          // ✅ OK / Safe / Success
    warning: "#F0B90B",     // ⚠️ Warning / Caution
    block: "#F6465D",       // ⛔ Block / Risk / Error
    info: "#1E90FF",        // ℹ️ Info
  },
  
  // Borders
  border: {
    default: "rgba(255, 255, 255, 0.08)",
    light: "rgba(255, 255, 255, 0.12)",
    active: "rgba(255, 255, 255, 0.16)",
  },
  
  // Brand
  brand: {
    primary: "#F0B90B",     // HAVEN primary (Binance yellow)
    secondary: "#B7BDC6",   // Secondary brand
  },
};

// ============================================================
// 📝 TYPOGRAPHY
// ============================================================

export const HAVEN_TYPOGRAPHY = {
  family: {
    primary: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    mono: "'JetBrains Mono', 'SF Mono', monospace",
    heading: "'Rajdhani', 'Inter', sans-serif",
  },
  
  size: {
    xs: "11px",
    sm: "12px",
    base: "14px",
    lg: "16px",
    xl: "18px",
    "2xl": "20px",
    "3xl": "24px",
    "4xl": "32px",
  },
  
  weight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  
  lineHeight: {
    tight: 1.2,
    normal: 1.5,
    relaxed: 1.6,
  },
};

// ============================================================
// 📐 SPACING & LAYOUT
// ============================================================

export const HAVEN_SPACING = {
  xs: "4px",
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "20px",
  "2xl": "24px",
  "3xl": "32px",
  "4xl": "48px",
};

export const HAVEN_RADIUS = {
  none: "0px",
  sm: "4px",
  md: "6px",
  lg: "8px",
  full: "9999px",
};

// ============================================================
// 🧱 COMPONENT STYLES
// ============================================================

export const HAVEN_COMPONENTS = {
  // Cards
  card: {
    background: HAVEN_COLORS.bg.card,
    border: "none",
    borderRadius: HAVEN_RADIUS.md,
    padding: HAVEN_SPACING.xl,
    shadow: "none",
  },
  
  // Buttons
  button: {
    primary: {
      background: HAVEN_COLORS.brand.primary,
      color: HAVEN_COLORS.text.inverse,
      hover: "#D4A30A",
    },
    secondary: {
      background: HAVEN_COLORS.bg.hover,
      color: HAVEN_COLORS.text.primary,
      hover: "#353C47",
    },
    danger: {
      background: HAVEN_COLORS.state.block,
      color: HAVEN_COLORS.text.primary,
      hover: "#D93A4D",
    },
  },
  
  // Status Pills
  pill: {
    safe: {
      background: `${HAVEN_COLORS.state.ok}15`,
      border: `${HAVEN_COLORS.state.ok}40`,
      color: HAVEN_COLORS.state.ok,
    },
    caution: {
      background: `${HAVEN_COLORS.state.warning}15`,
      border: `${HAVEN_COLORS.state.warning}40`,
      color: HAVEN_COLORS.state.warning,
    },
    blocked: {
      background: `${HAVEN_COLORS.state.block}15`,
      border: `${HAVEN_COLORS.state.block}40`,
      color: HAVEN_COLORS.state.block,
    },
    info: {
      background: `${HAVEN_COLORS.state.info}15`,
      border: `${HAVEN_COLORS.state.info}40`,
      color: HAVEN_COLORS.state.info,
    },
  },
};

// ============================================================
// 📋 UI COPY (English)
// ============================================================

export const HAVEN_COPY = {
  // Brand
  brand: {
    name: "HAVEN",
    tagline: "Built to Survive Markets",
  },
  
  // States
  states: {
    inactive: {
      title: "HAVEN is inactive",
      description: "Market conditions do not currently justify exposure.",
    },
    allowed: {
      title: "HAVEN allowed this run",
      description: "Risk and cost conditions were acceptable.",
    },
    blocked: {
      title: "Blocked by HAVEN Guardian",
      description: "Capital protection rules were triggered.",
    },
  },
  
  // Run Modes
  modes: {
    dry: {
      label: "Dry Run",
      description: "Decisions only. No exposure.",
    },
    paper: {
      label: "Paper Trading",
      description: "Simulated execution under real market conditions.",
    },
    live: {
      label: "LIVE",
      description: "Real execution. Guardian always active.",
    },
  },
  
  // GO-LIVE Gate
  gate: {
    noGo: {
      title: "NO-GO",
      description: "LIVE execution is blocked. HAVEN has insufficient evidence of survival.",
    },
    go: {
      title: "GO",
      description: "LIVE execution permitted under strict constraints.",
    },
  },
  
  // Panic
  panic: {
    title: "All executions stopped",
    description: "HAVEN is now in a safe state.",
  },
  
  // Actions
  actions: {
    viewExplanation: "View Explanation",
    runOnce: "Run Once",
    simulate: "Simulate",
    evaluate: "Run Evaluation",
  },
};

// ============================================================
// 🎯 THEME OBJECT (for inline styles)
// ============================================================

export const HAVEN_THEME = {
  colors: HAVEN_COLORS,
  typography: HAVEN_TYPOGRAPHY,
  spacing: HAVEN_SPACING,
  radius: HAVEN_RADIUS,
  components: HAVEN_COMPONENTS,
  copy: HAVEN_COPY,
};

// ============================================================
// 🔧 HELPER FUNCTIONS
// ============================================================

/**
 * Get status color based on state
 */
export const getStatusColor = (status) => {
  const statusMap = {
    // Success states
    ok: HAVEN_COLORS.state.ok,
    safe: HAVEN_COLORS.state.ok,
    success: HAVEN_COLORS.state.ok,
    passed: HAVEN_COLORS.state.ok,
    allowed: HAVEN_COLORS.state.ok,
    active: HAVEN_COLORS.state.ok,
    go: HAVEN_COLORS.state.ok,
    
    // Warning states
    warning: HAVEN_COLORS.state.warning,
    caution: HAVEN_COLORS.state.warning,
    marginal: HAVEN_COLORS.state.warning,
    
    // Error/Block states
    block: HAVEN_COLORS.state.block,
    blocked: HAVEN_COLORS.state.block,
    error: HAVEN_COLORS.state.block,
    failed: HAVEN_COLORS.state.block,
    danger: HAVEN_COLORS.state.block,
    "no-go": HAVEN_COLORS.state.block,
    nogo: HAVEN_COLORS.state.block,
    
    // Info states
    info: HAVEN_COLORS.state.info,
    insufficient: HAVEN_COLORS.state.info,
  };
  
  return statusMap[status?.toLowerCase()] || HAVEN_COLORS.text.muted;
};

/**
 * Get pill style based on status
 */
export const getPillStyle = (status) => {
  const pillMap = {
    ok: HAVEN_COMPONENTS.pill.safe,
    safe: HAVEN_COMPONENTS.pill.safe,
    success: HAVEN_COMPONENTS.pill.safe,
    passed: HAVEN_COMPONENTS.pill.safe,
    allowed: HAVEN_COMPONENTS.pill.safe,
    go: HAVEN_COMPONENTS.pill.safe,
    
    warning: HAVEN_COMPONENTS.pill.caution,
    caution: HAVEN_COMPONENTS.pill.caution,
    marginal: HAVEN_COMPONENTS.pill.caution,
    
    block: HAVEN_COMPONENTS.pill.blocked,
    blocked: HAVEN_COMPONENTS.pill.blocked,
    error: HAVEN_COMPONENTS.pill.blocked,
    failed: HAVEN_COMPONENTS.pill.blocked,
    "no-go": HAVEN_COMPONENTS.pill.blocked,
    nogo: HAVEN_COMPONENTS.pill.blocked,
    
    info: HAVEN_COMPONENTS.pill.info,
    insufficient: HAVEN_COMPONENTS.pill.info,
  };
  
  return pillMap[status?.toLowerCase()] || HAVEN_COMPONENTS.pill.info;
};

export default HAVEN_THEME;
