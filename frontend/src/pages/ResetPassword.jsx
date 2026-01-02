import { useState, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Lock, Shield, Eye, EyeOff, CheckCircle2, XCircle, ArrowLeft, AlertTriangle } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [tokenInvalid, setTokenInvalid] = useState(false);

  useEffect(() => {
    const tokenFromUrl = searchParams.get("token");
    if (tokenFromUrl) {
      setToken(tokenFromUrl);
    }
  }, [searchParams]);

  // Password validation
  const passwordValidation = {
    minLength: newPassword.length >= 8,
    hasMatch: newPassword === confirmPassword && confirmPassword.length > 0
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!token) {
      toast.error("Invalid reset link");
      return;
    }

    if (!passwordValidation.minLength) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    if (!passwordValidation.hasMatch) {
      toast.error("Passwords do not match");
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_URL}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: token,
          new_password: newPassword,
          confirm_password: confirmPassword
        })
      });

      const data = await response.json();
      
      if (response.ok) {
        setSuccess(true);
        toast.success("Password reset successfully!");
        
        // Redirect to login after 2 seconds
        setTimeout(() => {
          navigate("/login");
        }, 2000);
      } else {
        const errorMsg = data.detail || "Failed to reset password";
        setError(errorMsg);
        toast.error(errorMsg);
        
        // Check if token is invalid/expired
        if (errorMsg.toLowerCase().includes("invalid") || 
            errorMsg.toLowerCase().includes("expired") ||
            errorMsg.toLowerCase().includes("not found")) {
          setTokenInvalid(true);
        }
      }
    } catch (error) {
      if (error?.response?.data?.detail) {
        const errorMsg = error.response.data.detail;
        setError(errorMsg);
        toast.error(errorMsg);
        
        if (errorMsg.toLowerCase().includes("invalid") || 
            errorMsg.toLowerCase().includes("expired")) {
          setTokenInvalid(true);
        }
      } else {
        setError("Connection error. Please try again.");
        toast.error("Connection error. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Show invalid token page if token missing or verified as invalid
  if ((!token && !searchParams.get("token")) || tokenInvalid) {
    return (
      <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear_gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
        
        <Card className="relative w-full max-w-md bg-[#1E2329] border-white/8">
          <CardContent className="pt-8 pb-8 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-red-500/20 rounded-full mb-4">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-semibold text-[#EAECEF] mb-2">Invalid Reset Link</h2>
            <p className="text-[#848E9C] mb-4">
              This password reset link is invalid or has expired.
            </p>
            <Link 
              to="/forgot-password" 
              className="inline-flex items-center gap-2 text-sm text-[#F0B90B] hover:text-[#D4A30A]"
            >
              Request a new reset link
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
        
        <Card className="relative w-full max-w-md bg-[#1E2329] border-white/8">
          <CardContent className="pt-8 pb-8 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-green-500/20 rounded-full mb-4">
              <CheckCircle2 className="w-8 h-8 text-green-500" />
            </div>
            <h2 className="text-xl font-semibold text-[#EAECEF] mb-2">Password Reset!</h2>
            <p className="text-[#848E9C] mb-4">
              Your password has been reset successfully. Redirecting to login...
            </p>
            <Loader2 className="w-5 h-5 animate-spin mx-auto text-[#F0B90B]" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
      
      <div className="relative w-full max-w-md">
        {/* HAVEN Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-[#F0B90B] rounded-lg mb-3">
            <Shield className="w-7 h-7 text-[#0B0E11]" />
          </div>
          <h1 className="text-2xl font-rajdhani font-bold text-[#EAECEF] tracking-wider">
            HAVEN
          </h1>
        </div>

        {/* Card */}
        <Card className="bg-[#1E2329] border-white/8 backdrop-blur">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-xl text-[#EAECEF] flex items-center gap-2">
              <Lock className="w-5 h-5 text-[#F0B90B]" />
              Reset Password
            </CardTitle>
            <CardDescription className="text-[#848E9C]">
              Enter your new password below
            </CardDescription>
          </CardHeader>
          
          <CardContent>
            {error && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                <p className="text-sm text-red-500 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  {error}
                </p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* New Password */}
              <div className="space-y-2">
                <Label htmlFor="newPassword" className="text-[#B7BDC6]">New Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="newPassword"
                    type={showPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password"
                    className="pl-10 pr-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50"
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
                {newPassword && (
                  <div className="flex items-center gap-2 text-xs">
                    {passwordValidation.minLength ? (
                      <CheckCircle2 className="w-3 h-3 text-green-500" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-500" />
                    )}
                    <span className={passwordValidation.minLength ? "text-green-500" : "text-[#848E9C]"}>
                      At least 8 characters
                    </span>
                  </div>
                )}
              </div>

              {/* Confirm Password */}
              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-[#B7BDC6]">Confirm Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="confirmPassword"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm new password"
                    className="pl-10 pr-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50"
                    disabled={loading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#848E9C] hover:text-[#B7BDC6]"
                  >
                    {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {confirmPassword && (
                  <div className="flex items-center gap-2 text-xs">
                    {passwordValidation.hasMatch ? (
                      <CheckCircle2 className="w-3 h-3 text-green-500" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-500" />
                    )}
                    <span className={passwordValidation.hasMatch ? "text-green-500" : "text-red-500"}>
                      {passwordValidation.hasMatch ? "Passwords match" : "Passwords do not match"}
                    </span>
                  </div>
                )}
              </div>

              <Button 
                type="submit" 
                className="w-full bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                disabled={loading || !passwordValidation.minLength || !passwordValidation.hasMatch}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Resetting...
                  </>
                ) : (
                  "Reset Password"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <Link 
                to="/login" 
                className="inline-flex items-center gap-2 text-sm text-[#848E9C] hover:text-[#F0B90B]"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Login
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Security note */}
        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-[#848E9C]">
          <Shield className="w-3 h-3" />
          <span>Secure password reset</span>
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
