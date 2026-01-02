import { createContext, useContext, useState, useEffect } from "react";
import { api } from "@/App";

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  // Decode JWT to get user info (moved before initFromStorage to avoid hoisting issue)
  const decodeToken = (token) => {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return {
        id: payload.sub,
        username: payload.username,
        role: payload.role,
        exp: payload.exp,
      };
    } catch (e) {
      return null;
    }
  };

  const initFromStorage = () => {
    try {
      const stored = localStorage.getItem("auth_token_v2");
      if (!stored) return { token: null, user: null };
      const decoded = decodeToken(stored);
      // Use current time for expiry check, not module load time
      const now = Date.now();
      const expired = !decoded || decoded.exp * 1000 < now;
      if (expired) {
        localStorage.removeItem("auth_token_v2");
        return { token: null, user: null };
      }
      return {
        token: stored,
        user: {
          id: decoded.sub,
          username: decoded.username,
          role: decoded.role,
          email: decoded.username,
        },
      };
    } catch {
      return { token: null, user: null };
    }
  };

  const initial = initFromStorage();
  const [user, setUser] = useState(initial.user);
  const [token, setToken] = useState(initial.token);
  const [loading, setLoading] = useState(false);



  const login = async (usernameOrEmail, password) => {
    try {
      const res = await api.post("/auth/login", { username_or_email: usernameOrEmail, password });
      const accessToken = res.data.access_token;
      localStorage.setItem("auth_token_v2", accessToken);
      const decoded = decodeToken(accessToken);
      setToken(accessToken);
      setUser({
        id: decoded?.sub,
        username: decoded?.username,
        role: decoded?.role,
        email: null,
      });
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.detail || "Invalid credentials";
      return { success: false, error: message };
    }
  };

  const logout = () => {
    localStorage.removeItem("auth_token_v2");
    setToken(null);
    setUser(null);
  };

  const changePassword = async (currentPassword, newPassword) => {
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      
      // Update user state to remove force_password_change
      setUser(prev => ({ ...prev, force_password_change: false }));
      
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.detail || "Erro ao alterar password";
      return { success: false, error: message };
    }
  };

  // Check permissions
  const hasRole = (requiredRoles) => {
    if (!user) return false;
    const roles = Array.isArray(requiredRoles) ? requiredRoles : [requiredRoles];
    return roles.includes(user.role);
  };

  const isAdmin = () => hasRole(["admin", "owner"]);
  const isOwner = () => hasRole(["owner"]);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!token,
    login,
    logout,
    changePassword,
    hasRole,
    isAdmin,
    isOwner,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
