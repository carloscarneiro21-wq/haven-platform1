import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "@/App";

const AuthGuard = ({ children }) => {
  const token = localStorage.getItem("auth_token_v2");
  const [checked, setChecked] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!token) {
        setChecked(true);
        setOk(false);
        return;
      }

      try {
        await api.get("/auth/me");
        if (!cancelled) {
          setOk(true);
          setChecked(true);
        }
      } catch (_) {
        // Axios interceptor will handle 401 (clear token + redirect)
        if (!cancelled) {
          setOk(false);
          setChecked(true);
        }
      }
    };

    setChecked(false);
    run();

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (!checked) {
    return null;
  }

  if (!ok) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

export default AuthGuard;
