import { useState, useEffect } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, NavLink, useNavigate, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";

import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { SidebarProvider, useSidebar } from "./contexts/SidebarContext";
import { SystemStatusProvider, useSystemStatus } from "./contexts/SystemStatusContext";

import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import Positions from "./pages/Positions";
import RiskManager from "./pages/RiskManager";
import TradeLogs from "./pages/TradeLogs";
import Settings from "./pages/Settings";
import StressLab from "./pages/StressLab";
import Monitoring from "./pages/Monitoring";
import Events from "./pages/Events";
import Validation from "./pages/Validation";
import Dex from "./pages/Dex";
import AdminUsers from "./pages/AdminUsers";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import ChangePassword from "./pages/ChangePassword";
import Sandbox from "./pages/Sandbox";
import Promotions from "./pages/Promotions";
import Analytics from "./pages/Analytics";
import DexTrading from "./pages/DexTrading";
import Trades from "./pages/Trades";

import GrowthModule from "./components/GrowthModule";
import AuthGuard from "./components/AuthGuard";
import TradingModeBadge from "./components/TradingModeBadge";
import LiveModeBanner from "./components/LiveModeBanner";
import LiveReadinessModal from "./components/LiveReadinessModal";
import TopSystemBar from "./components/console/TopSystemBar";
import { Button } from "./components/ui/button";

import {
  LayoutDashboard,
  Bot,
  TrendingUp,
  Shield,
  ScrollText,
  Settings as SettingsIcon,
  Activity,
  Zap,
  FlaskConical,
  Eye,
  Clock,
  ClipboardCheck,
  Coins,
  Users,
  Crown,
  TestTube,
  LogOut,
  Key,
  ChevronUp,
  User,
  PanelLeftClose,
  PanelLeft,
  Menu,
  LineChart,
  GitCompare,
  Globe,
  BarChart3,
  FileCheck
} from "lucide-react";


const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
// Expose for smoke tests
window.__HAVEN_API_BASE__ = API;

// Create axios instance with interceptors
export const api = axios.create({
  baseURL: API,
  timeout: 30000,
});

// Build version for deployment verification
export const BUILD_VERSION = "2026.01.01.auth";
export const BUILD_DATE = new Date().toISOString().split('T')[0];

// Attach Authorization header (JWT in localStorage)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token_v2");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const message = error.response?.data?.detail || error.message || "An error occurred";
    const url = error.config?.url || "";

    // Handle authentication errors - clear token and redirect
    if (status === 401) {
      localStorage.removeItem("auth_token_v2");
      // Avoid redirect loops
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }

    // Suppress toast for non-critical API errors (candles, metrics that may not be available)
    const silentEndpoints = ["/market/candles", "/trades/metrics"];
    const shouldSilence = silentEndpoints.some(ep => url.includes(ep));
    
    if (!shouldSilence) {
      // For auth flows we show inline errors; keep toast for non-auth generic errors
      toast.error(message);
    }
    return Promise.reject(error);
  }
);

import AuthGuard from "@/components/AuthGuard";
import TradingModeBadge from "@/components/TradingModeBadge";
import LiveModeBanner from "@/components/LiveModeBanner";
import LiveReadinessModal from "@/components/LiveReadinessModal";
import TopSystemBar from "@/components/console/TopSystemBar";
import { Button } from "@/components/ui/button";

const ProtectedRoute = ({ children, requiredRoles = null }) => {
  return <AuthGuard>{children}</AuthGuard>;
};

const SystemStatusBar = () => {
  const { wsConnected, usingPolling, lastEventIso } = useSystemStatus();
  return <TopSystemBar wsConnected={wsConnected} usingPolling={usingPolling} lastEventIso={lastEventIso} />;
};


const Navigation = ({ onOpenLiveReadiness }) => {
  const [runtimeStatus, setRuntimeStatus] = useState({ running: false });
  const [riskStatus, setRiskStatus] = useState({ kill_switch_active: false });
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { isExpanded: sidebarOpen, toggle: toggleSidebar } = useSidebar();
  const { user, isAdmin, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [runtime, risk] = await Promise.all([
          api.get("/runtime/status"),
          api.get("/risk")
        ]);
        setRuntimeStatus(runtime.data);
        setRiskStatus(risk.data);
      } catch (e) {
        console.error("Failed to fetch status");
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
    toast.success("Session ended");
  };

  const getRoleIcon = (role) => {
    switch (role) {
      case "owner": return <Crown className="w-3 h-3 text-[#F0B90B]" />;
      case "admin": return <Shield className="w-3 h-3 text-[#1E90FF]" />;
      case "tester": return <TestTube className="w-3 h-3 text-[#0ECB81]" />;
      default: return <Eye className="w-3 h-3 text-[#848E9C]" />;
    }
  };

  const getRoleColor = (role) => {
    switch (role) {
      case "owner": return "text-[#F0B90B]";
      case "admin": return "text-[#1E90FF]";
      case "tester": return "text-[#0ECB81]";
      default: return "text-[#848E9C]";
    }
  };

  // Check if user can see admin menu
  const canSeeAdmin = isAdmin();

  const navItems = [
    { path: "/", icon: LayoutDashboard, label: "DASHBOARD" },
    { path: "/trades", icon: Activity, label: "TRADES" },
    { path: "/agents", icon: Bot, label: "AGENTS" },
    { path: "/growth", icon: LineChart, label: "GROWTH" },
    { path: "/dex", icon: Coins, label: "DEX SNIPER" },
    { path: "/dex-trading", icon: Globe, label: "DEX TRADING" },
    { path: "/positions", icon: TrendingUp, label: "POSITIONS" },
    { path: "/risk", icon: Shield, label: "RISK" },
    { path: "/logs", icon: ScrollText, label: "LOGS" },
    { path: "/events", icon: Clock, label: "EVENTS" },
    { path: "/stress-lab", icon: FlaskConical, label: "STRESS LAB" },
    { path: "/sandbox", icon: TestTube, label: "SANDBOX" },
    { path: "/promotions", icon: GitCompare, label: "PROMOTIONS" },
    { path: "/analytics", icon: BarChart3, label: "ANALYTICS" },
    { path: "/monitoring", icon: Eye, label: "MONITORING" },
    { path: "/validation", icon: ClipboardCheck, label: "VALIDATION" },
    { path: "/settings", icon: SettingsIcon, label: "SETTINGS" },
  ];

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={toggleSidebar}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-[#1E2329] rounded-md"
      >
        <Menu className="w-5 h-5 text-[#EAECEF]" />
      </button>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div 
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={toggleSidebar}
        />
      )}

      {/* Sidebar */}
      <nav className={`
        fixed left-0 top-0 h-full bg-[#161A1E] border-r border-white/8 flex flex-col z-50
        transition-all duration-300 ease-in-out
        ${sidebarOpen ? 'w-[220px]' : 'w-[70px]'}
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* HAVEN Logo & Branding */}
        <div className="p-4 border-b border-white/8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-[#F0B90B] rounded-md flex items-center justify-center shrink-0">
                <Shield className="w-6 h-6 text-[#0B0E11]" />
              </div>
              {sidebarOpen && (
                <div className="overflow-hidden">
                  <h1 className="font-rajdhani font-bold text-lg tracking-wider text-[#EAECEF]">HAVEN</h1>
                  <p className="text-[10px] font-normal text-[#848E9C] tracking-wide">Built to Survive Markets</p>
                </div>
              )}
            </div>
            <button
              onClick={toggleSidebar}
              className="hidden lg:flex p-1.5 hover:bg-[#2B3139] rounded transition-colors"
              title={sidebarOpen ? "Collapse" : "Expand"}
            >
              {sidebarOpen ? (
                <PanelLeftClose className="w-4 h-4 text-[#848E9C]" />
              ) : (
                <PanelLeft className="w-4 h-4 text-[#848E9C]" />
              )}
            </button>
          </div>
        </div>

        {/* Status Indicators */}
        <div className={`px-3 py-3 border-b border-white/8 ${!sidebarOpen && 'flex flex-col items-center gap-2'}`}>
          {sidebarOpen ? (
            <>
              {/* Trading Mode Badge */}
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="font-rajdhani text-[#848E9C] uppercase tracking-wider">Mode</span>
                <TradingModeBadge />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="font-rajdhani text-[#848E9C] uppercase tracking-wider">Runtime</span>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${runtimeStatus.running ? 'bg-[#0ECB81] animate-pulse' : 'bg-[#848E9C]'}`} />
                  <span className={`font-mono ${runtimeStatus.running ? 'text-[#0ECB81]' : 'text-[#848E9C]'}`}>
                    {runtimeStatus.running ? 'ACTIVE' : 'STOPPED'}
                  </span>
                </div>
              </div>

              {/* Live Readiness quick access (discreet in PAPER) */}
              <div className="mt-2">
                <Button
                  variant="outline"
                  className="w-full h-8 text-xs border-white/10 bg-[#1E2329] hover:bg-[#2B3139] text-[#EAECEF]"
                  onClick={() => onOpenLiveReadiness?.()}
                >
                  <FileCheck className="w-3.5 h-3.5 mr-2 text-[#F0B90B]" />
                  Live Readiness
                </Button>
              </div>

              {riskStatus.kill_switch_active && (
                <div className="mt-2 px-2 py-1 bg-[#F6465D]/20 border border-[#F6465D]/50 rounded">
                  <span className="text-[10px] font-mono text-[#F6465D] uppercase tracking-wider">
                    KILL SWITCH ACTIVE
                  </span>
                </div>
              )}
            </>
          ) : (
            <>
              <TradingModeBadge className="text-[10px] px-1 py-0.5" />
              <div className={`w-3 h-3 rounded-full ${runtimeStatus.running ? 'bg-[#0ECB81] animate-pulse' : 'bg-[#848E9C]'}`} title={runtimeStatus.running ? 'Runtime Active' : 'Runtime Stopped'} />
              <button
                onClick={() => onOpenLiveReadiness?.()}
                className="mt-1 w-8 h-8 rounded bg-[#1E2329] hover:bg-[#2B3139] flex items-center justify-center"
                title="Live Readiness"
              >
                <FileCheck className="w-4 h-4 text-[#F0B90B]" />
              </button>
            </>
          )}
        </div>

        {/* Navigation Links */}
        <div className="flex-1 py-4 overflow-y-auto">
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              title={!sidebarOpen ? label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 py-3 mx-2 rounded transition-all duration-200 ${
                  sidebarOpen ? 'px-4' : 'px-0 justify-center'
                } ${
                  isActive
                    ? "bg-white/10 text-[#EAECEF] border-l-2 border-[#F0B90B]"
                    : "text-[#848E9C] hover:text-[#EAECEF] hover:bg-white/5"
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {sidebarOpen && (
                <span className="font-rajdhani font-medium text-sm tracking-wider whitespace-nowrap">{label}</span>
              )}
            </NavLink>
          ))}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-white/8">
          <div className="space-y-2">
            {/* User Info Display */}
            <div className={`w-full flex items-center gap-2 py-2 bg-[#1E2329] rounded ${sidebarOpen ? 'px-2' : 'px-0 justify-center'}`}>
              <div className="w-7 h-7 bg-[#2B3139] rounded-full flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-[#F0B90B]" />
              </div>
              {sidebarOpen && (
                <div className="flex-1 text-left overflow-hidden">
                  <span className="text-xs font-mono text-[#F0B90B] block">{(user?.role || 'USER').toUpperCase()}</span>
                  <span className="text-xs text-[#848E9C] truncate block">{user?.username || user?.email || '—'}</span>
                </div>
              )}
            </div>

            {/* Logout */}
            {isAuthenticated && (
              <button
                onClick={handleLogout}
                className={`w-full flex items-center gap-2 py-2 bg-[#1E2329] hover:bg-[#2B3139] rounded transition-colors ${sidebarOpen ? 'px-2' : 'px-0 justify-center'}`}
              >
                <LogOut className="w-4 h-4 text-[#848E9C]" />
                {sidebarOpen && <span className="text-xs text-[#EAECEF]">Logout</span>}
              </button>
            )}
          </div>
          {sidebarOpen && (
            <div className="text-[10px] font-mono text-[#848E9C] text-center mt-3 space-y-0.5">
              <div>PAPER TRADING MODE</div>
              <div className="text-[#4A5568]">v{BUILD_VERSION}</div>
            </div>
          )}
        </div>
      </nav>
    </>
  );
};

// Main Layout with dynamic margin based on sidebar state
const MainLayout = ({ children }) => {
  const { isExpanded } = useSidebar();
  const [liveReadinessOpen, setLiveReadinessOpen] = useState(false);
  
  return (
    <div className="flex h-screen bg-[#0B0E11]">
      <Navigation onOpenLiveReadiness={() => setLiveReadinessOpen(true)} />
      <main 
        className={`flex-1 overflow-auto bg-[#0B0E11] transition-all duration-300 ${
          isExpanded ? 'lg:ml-[220px]' : 'lg:ml-[70px]'
        }`}
      >
        <SystemStatusBar />
        <LiveModeBanner onOpenLiveReadiness={() => setLiveReadinessOpen(true)} />
        <div className="p-6 pb-16 pt-14">
          {children}
        </div>
        <LiveReadinessModal open={liveReadinessOpen} onOpenChange={setLiveReadinessOpen} />
        {/* Footer with version */}
        <footer className="fixed bottom-0 right-0 left-0 lg:left-[70px] h-8 bg-[#0B0E11] border-t border-white/5 flex items-center justify-between px-4 text-[10px] text-[#4A5568] font-mono z-10">
          <span>HAVEN Trading System</span>
          <span>Build: {BUILD_VERSION}</span>
        </footer>
      </main>
    </div>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <SystemStatusProvider>
          <SidebarProvider>
            <Toaster position="top-right" richColors />
            <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<SignUp />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/change-password" element={<ChangePassword />} />

            {/* Protected routes */}
            <Route path="/*" element={
              <ProtectedRoute>
                <MainLayout>
                  <Routes>
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/trades" element={<Trades />} />
                    <Route path="/agents" element={<Agents />} />
                    <Route path="/growth" element={<GrowthModule />} />
                    <Route path="/dex" element={<Dex />} />
                    <Route path="/dex-trading" element={<DexTrading />} />
                    <Route path="/positions" element={<Positions />} />
                    <Route path="/risk" element={<RiskManager />} />
                    <Route path="/logs" element={<TradeLogs />} />
                    <Route path="/events" element={<Events />} />
                    <Route path="/stress-lab" element={<StressLab />} />
                    <Route path="/sandbox" element={<Sandbox />} />
                    <Route path="/promotions" element={<Promotions />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="/monitoring" element={<Monitoring />} />
                    <Route path="/validation" element={<Validation />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/admin/users" element={
                      <ProtectedRoute requiredRoles={["admin", "owner"]}>
                        <AdminUsers />
                      </ProtectedRoute>
                    } />
                  </Routes>
                </MainLayout>
              </ProtectedRoute>
            } />
          </Routes>
        </SidebarProvider>
        </SystemStatusProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
