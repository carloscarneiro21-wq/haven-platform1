import { useState } from "react";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { Loader2, Lock, User, Shield, Eye, EyeOff } from "lucide-react";

const Login = () => {
  const navigate = useNavigate();
  const { login, loading: authLoading, isAuthenticated } = useAuth();

  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!authLoading && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!usernameOrEmail || !password) {
      setError("Please enter username/email and password");
      toast.error("Please enter username/email and password");
      return;
    }

    setLoading(true);
    const result = await login(usernameOrEmail, password);
    setLoading(false);

    if (!result.success) {
      setError(result.error || "Invalid email or password");
      return;
    }

    toast.success("Logged in");
    navigate("/dashboard");
  };

  return (
    <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-[#F0B90B] rounded-lg mb-3">
            <Shield className="w-7 h-7 text-[#0B0E11]" />
          </div>
          <h1 className="text-2xl font-rajdhani font-bold text-[#EAECEF] tracking-wider">HAVEN</h1>
          <p className="text-xs text-[#848E9C] mt-1">LIVE (PAPER / SIMULATION)</p>
        </div>

        <Card className="bg-[#1E2329] border-white/8 backdrop-blur">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-xl text-[#EAECEF]">Login</CardTitle>
            <CardDescription className="text-[#848E9C]">Sign in to access the dashboard</CardDescription>
          </CardHeader>

          <CardContent>
            {error && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username" className="text-[#B7BDC6]">Username or Email</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="username"
                    type="text"
                    value={usernameOrEmail}
                    onChange={(e) => setUsernameOrEmail(e.target.value)}
                    placeholder="Enter username or email"
                    className="pl-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50 focus:ring-[#F0B90B]/20"
                    autoComplete="username"
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-[#B7BDC6]">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="pl-10 pr-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50 focus:ring-[#F0B90B]/20"
                    autoComplete="current-password"
                    disabled={loading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#848E9C] hover:text-[#B7BDC6]"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                className="w-full bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign In"
                )}
              </Button>

              <div className="flex items-center justify-between text-sm">
                <Link to="/forgot-password" className="text-[#F0B90B] hover:text-[#D4A30A]">Forgot password?</Link>
                <Link to="/signup" className="text-[#F0B90B] hover:text-[#D4A30A]">Create account</Link>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Login;
