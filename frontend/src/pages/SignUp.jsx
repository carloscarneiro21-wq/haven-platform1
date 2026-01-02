import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Lock, User, Mail, Shield, Eye, EyeOff, UserPlus, CheckCircle2, XCircle, FileText } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const SignUp = () => {
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: ""
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  // Password validation
  const passwordValidation = {
    minLength: formData.password.length >= 8,
    hasMatch: formData.password === formData.confirmPassword && formData.confirmPassword.length > 0
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate all fields
    if (!formData.username || !formData.email || !formData.password || !formData.confirmPassword) {
      toast.error("Please fill in all fields");
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
    
    try {
      const response = await fetch(`${API_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: formData.username,
          email: formData.email,
          password: formData.password,
          confirm_password: formData.confirmPassword
        })
      });

      const data = await response.json();
      
      if (response.ok) {
        setSuccess(true);
        toast.success("Account created successfully!");
        
        // Redirect to login after 2 seconds
        setTimeout(() => {
          navigate("/login");
        }, 2000);
      } else {
        toast.error(data.detail || "Registration failed");
      }
    } catch (error) {
      toast.error("Connection error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-[#0B0E11] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(240,185,11,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(240,185,11,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
        
        <Card className="relative w-full max-w-md bg-[#1E2329] border-white/8">
          <CardContent className="pt-8 pb-8 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-green-500/20 rounded-full mb-4">
              <CheckCircle2 className="w-8 h-8 text-green-500" />
            </div>
            <h2 className="text-xl font-semibold text-[#EAECEF] mb-2">Account Created!</h2>
            <p className="text-[#848E9C] mb-4">
              Your account has been created successfully. Redirecting to login...
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
        {/* HAVEN Logo/Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-[#F0B90B] rounded-lg mb-3">
            <Shield className="w-7 h-7 text-[#0B0E11]" />
          </div>
          <h1 className="text-2xl font-rajdhani font-bold text-[#EAECEF] tracking-wider">
            HAVEN
          </h1>
        </div>

        {/* PAPER MODE Badge */}
        <div className="flex justify-center mb-4">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-[#2B3139] border border-[#F0B90B]/30 rounded-full">
            <FileText className="w-3.5 h-3.5 text-[#F0B90B]" />
            <span className="text-xs font-medium text-[#F0B90B]">PAPER MODE</span>
          </div>
        </div>

        {/* Sign Up Card */}
        <Card className="bg-[#1E2329] border-white/8 backdrop-blur">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-xl text-[#EAECEF] flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-[#F0B90B]" />
              Create Account
            </CardTitle>
            <CardDescription className="text-[#848E9C]">
              Sign up to start paper trading
            </CardDescription>
          </CardHeader>
          
          <CardContent>
              {/* Username */}
              <div className="space-y-2">
                <Label htmlFor="username" className="text-[#B7BDC6]">Username</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="username"
                    name="username"
                    type="text"
                    value={formData.username}
                    onChange={handleChange}
                    placeholder="Choose a username"
                    className="pl-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50"
                    disabled={loading}
                    minLength={3}
                    maxLength={50}
                  />
                </div>
              </div>


            <form onSubmit={handleSubmit} className="space-y-4">
              

              {/* Email */}
              <div className="space-y-2">
                <Label htmlFor="email" className="text-[#B7BDC6]">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="Enter your email"
                    className="pl-10 bg-[#2B3139] border-white/8 text-[#EAECEF] placeholder:text-[#848E9C] focus:border-[#F0B90B]/50"
                    disabled={loading}
                  />
                </div>
              </div>

              {/* Password */}
              <div className="space-y-2">
                <Label htmlFor="password" className="text-[#B7BDC6]">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848E9C]" />
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Create a password"
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
                {/* Password requirements */}
                {formData.password && (
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
                    name="confirmPassword"
                    type={showConfirmPassword ? "text" : "password"}
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    placeholder="Confirm your password"
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
                {/* Match indicator */}
                {formData.confirmPassword && (
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
                    Creating account...
                  </>
                ) : (
                  "Create Account"
                )}
              </Button>
            </form>

            {/* Login Link */}
            <div className="mt-6 text-center">
              <span className="text-[#848E9C] text-sm">Already have an account? </span>
              <Link 
                to="/login" 
                className="text-sm text-[#F0B90B] hover:text-[#D4A30A] font-medium"
              >
                Sign in
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Security note */}
        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-[#848E9C]">
          <Shield className="w-3 h-3" />
          <span>Secure connection • Your data is encrypted</span>
        </div>
      </div>
    </div>
  );
};

export default SignUp;
