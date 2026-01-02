import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Lock, Key, AlertTriangle, Eye, EyeOff } from "lucide-react";

const ChangePassword = () => {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [loading, setLoading] = useState(false);
  
  const { changePassword, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  
  const isRequired = location.state?.required || user?.force_password_change;

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast.error("Preencha todos os campos");
      return;
    }
    
    if (newPassword.length < 8) {
      toast.error("A nova password deve ter pelo menos 8 caracteres");
      return;
    }
    
    if (newPassword !== confirmPassword) {
      toast.error("As passwords não coincidem");
      return;
    }
    
    if (currentPassword === newPassword) {
      toast.error("A nova password deve ser diferente da atual");
      return;
    }
    
    setLoading(true);
    
    const result = await changePassword(currentPassword, newPassword);
    
    setLoading(false);
    
    if (result.success) {
      toast.success("Password alterada com sucesso!");
      navigate("/");
    } else {
      toast.error(result.error);
    }
  };

  const handleCancel = () => {
    if (isRequired) {
      // If password change is required, logout instead
      logout();
      navigate("/login");
    } else {
      navigate(-1);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.03)_1px,transparent_1px)] bg-[size:50px_50px]" />
      
      <div className="relative w-full max-w-md">
        <Card className="bg-zinc-900/80 border-zinc-800 backdrop-blur">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-xl text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-[#F59E0B]" />
              Alterar Password
            </CardTitle>
            <CardDescription className="text-zinc-400">
              {isRequired 
                ? "É necessário alterar a sua password temporária antes de continuar"
                : "Altere a sua password de acesso"
              }
            </CardDescription>
          </CardHeader>
          
          <CardContent>
            {isRequired && (
              <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 shrink-0" />
                <p className="text-sm text-yellow-400">
                  A sua conta foi criada com uma password temporária. 
                  Por segurança, deve alterá-la agora.
                </p>
              </div>
            )}
            
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="currentPassword" className="text-zinc-300">
                  Password Atual
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <Input
                    id="currentPassword"
                    type={showPasswords ? "text" : "password"}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Password atual ou temporária"
                    className="pl-10 bg-zinc-800 border-zinc-700 text-white"
                    disabled={loading}
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="newPassword" className="text-zinc-300">
                  Nova Password
                </Label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <Input
                    id="newPassword"
                    type={showPasswords ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres"
                    className="pl-10 bg-zinc-800 border-zinc-700 text-white"
                    disabled={loading}
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-zinc-300">
                  Confirmar Nova Password
                </Label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <Input
                    id="confirmPassword"
                    type={showPasswords ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repita a nova password"
                    className="pl-10 bg-zinc-800 border-zinc-700 text-white"
                    disabled={loading}
                  />
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="showPasswords"
                  checked={showPasswords}
                  onChange={(e) => setShowPasswords(e.target.checked)}
                  className="rounded border-zinc-600"
                />
                <Label htmlFor="showPasswords" className="text-sm text-zinc-400 cursor-pointer">
                  Mostrar passwords
                </Label>
              </div>

              <div className="flex gap-3 pt-2">
                <Button 
                  type="button"
                  variant="outline"
                  onClick={handleCancel}
                  className="flex-1"
                  disabled={loading}
                >
                  {isRequired ? "Sair" : "Cancelar"}
                </Button>
                <Button 
                  type="submit" 
                  className="flex-1 bg-[#10B981] hover:bg-[#10B981]/80 text-black font-semibold"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      A guardar...
                    </>
                  ) : (
                    "Alterar Password"
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ChangePassword;
