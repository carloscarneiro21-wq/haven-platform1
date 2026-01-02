import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Mail, Shield, ArrowLeft, CheckCircle2, Copy, FileText, AlertTriangle } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const ForgotPassword = () => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [demoToken, setDemoToken] = useState(null);
  const [isDemoMode, setIsDemoMode] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!email) {
      toast.error("Please enter your email");
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(`${API_URL}/api/auth/recover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });

      const data = await response.json();
      
      if (response.ok) {
        setSubmitted(true);
        if (data.status === 'demo' && data.token) {
          setDemoToken(data.token);
          setIsDemoMode(true);
        }
        toast.success("Reset instructions sent!");
      } else if (response.status === 429) {
        toast.error("Too many reset requests. Please wait an hour and try again.");
      } else {
        // Always show success to not reveal if account exists
        setSubmitted(true);
      }
    } catch (error) {
      // Check for rate limit in error response
      if (error?.response?.status === 429) {
        toast.error("Too many reset requests. Please wait an hour and try again.");
      } else if (error?.response?.data?.detail) {
        toast.error(error.response.data.detail);
      } else {
        toast.error("Connection error. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const copyToken = () => {
    if (demoToken) {
      navigator.clipboard.writeText(demoToken);
      toast.success("Token copied to clipboard");
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
        
        <div className="relative w-full max-w-md">
          <Card className="bg-[#1E2329] border-white/8">
            <CardContent className="pt-8 pb-8">
              <div className="text-center mb-6">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-green-500/20 rounded-full mb-4">
                  <CheckCircle2 className="w-8 h-8 text-green-500" />
                </div>
                <h2 className="text-xl font-semibold text-[#EAECEF] mb-2">Check Your Email</h2>
                <p className="text-[#848E9C] text-sm">
                  If an account exists with that email, you will receive a password reset link.
                </p>
              </div>

              {/* Production mode - just show instructions */}
              {!isDemoMode && (
                <div className="p-4 bg-[#2B3139] rounded-lg border border-white/8">
                  <p className="text-sm text-[#B7BDC6] text-center">
                    The reset link will be valid for <strong className="text-[#F0B90B]">15 minutes</strong>.
                    <br />
                    <span className="text-xs text-[#848E9C]">Check your spam folder if you don&apos;t see the email.</span>
                  </p>
                </div>
              )}

              {/* Demo mode - show token (only when email not configured) */}
              {isDemoMode && demoToken && (
                <div className="space-y-3">
                  <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs text-yellow-500 font-medium">Demo Mode</p>
                      <p className="text-xs text-[#B7BDC6]">Email service not configured. Use the token below.</p>
                    </div>
                  </div>
                  
                  <div className="p-4 bg-[#2B3139] rounded-lg border border-[#F0B90B]/30">
                    <p className="text-xs text-[#848E9C] mb-2 flex items-center gap-1">
                      <FileText className="w-3 h-3" />
                      Reset Token:
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 text-xs text-[#EAECEF] bg-[#0B0E11] p-2 rounded font-mono break-all">
                        {demoToken}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={copyToken}
                        className="shrink-0 border-white/10 hover:bg-white/5"
                      >
                        <Copy className="w-3 h-3" />
                      </Button>
                    </div>
                    <Link 
                      to={`/reset-password?token=${demoToken}`}
                      className="mt-3 block"
                    >
                      <Button className="w-full bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold">
                        Reset Password Now
                      </Button>
                    </Link>
                  </div>
                </div>
              )}

              <div className="mt-6 text-center">
                <Link 
                  to="/login" 
                  className="inline-flex items-center gap-2 text-sm text-[#F0B90B] hover:text-[#D4A30A]"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Login
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
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
              <Mail className="w-5 h-5 text-[#F0B90B]" />
              Forgot Password
            </CardTitle>
            <CardDescription className="text-[#848E9C]">
              Enter your email to receive a reset link
            </CardDescription>
          </CardHeader>
          
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-[#B7BDC6]">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    className="pl-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50"
                    disabled={loading}
                  />
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
                    Sending...
                  </>
                ) : (
                  "Send Reset Link"
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
          <span>Reset links expire in 15 minutes</span>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
