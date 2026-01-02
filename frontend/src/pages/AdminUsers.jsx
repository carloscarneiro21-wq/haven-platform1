import { useState, useEffect } from "react";
import { api } from "@/App";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Users,
  UserPlus,
  Shield,
  Eye,
  TestTube,
  Crown,
  RefreshCw,
  Key,
  Ban,
  CheckCircle,
  Copy,
  AlertTriangle,
} from "lucide-react";

const ROLES = [
  { value: "owner", label: "Owner", icon: Crown, color: "text-yellow-400", bgColor: "bg-yellow-500/20" },
  { value: "admin", label: "Admin", icon: Shield, color: "text-blue-400", bgColor: "bg-blue-500/20" },
  { value: "tester", label: "Tester", icon: TestTube, color: "text-green-400", bgColor: "bg-green-500/20" },
  { value: "viewer", label: "Viewer", icon: Eye, color: "text-zinc-400", bgColor: "bg-zinc-500/20" },
];

const getRoleInfo = (role) => ROLES.find(r => r.value === role) || ROLES[3];

const RoleBadge = ({ role }) => {
  const roleInfo = getRoleInfo(role);
  const Icon = roleInfo.icon;
  
  return (
    <Badge className={`${roleInfo.bgColor} ${roleInfo.color} border-0 gap-1`}>
      <Icon className="w-3 h-3" />
      {roleInfo.label}
    </Badge>
  );
};

const AdminUsers = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [tempPassword, setTempPassword] = useState(null);
  
  // Form state
  const [newUser, setNewUser] = useState({
    username: "",
    email: "",
    role: "tester",
  });

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const response = await api.get("/admin/users");
      setUsers(response.data);
    } catch (error) {
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreateUser = async () => {
    if (!newUser.username || newUser.username.length < 3) {
      toast.error("Username deve ter pelo menos 3 caracteres");
      return;
    }
    
    try {
      const response = await api.post("/admin/users", newUser);
      setTempPassword(response.data.temporary_password);
      toast.success(`Utilizador ${newUser.username} criado!`);
      setNewUser({ username: "", email: "", role: "tester" });
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar utilizador");
    }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      await api.patch(`/admin/users/${userId}`, { role: newRole });
      toast.success("Role atualizado!");
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar role");
    }
  };

  const handleToggleActive = async (userId, currentActive) => {
    try {
      await api.patch(`/admin/users/${userId}`, { is_active: !currentActive });
      toast.success(currentActive ? "Utilizador desativado" : "Utilizador ativado");
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar estado");
    }
  };

  const handleResetPassword = async (userId) => {
    try {
      const response = await api.post(`/admin/users/${userId}/reset-password`);
      setTempPassword(response.data.temporary_password);
      setResetDialogOpen(true);
      toast.success("Password resetada!");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao resetar password");
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copiado para clipboard!");
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-rajdhani font-bold text-white tracking-wide flex items-center gap-2">
            <Users className="w-6 h-6 text-blue-400" />
            GESTÃO DE UTILIZADORES
          </h1>
          <p className="text-sm text-zinc-500">Administração de contas e permissões (RBAC)</p>
        </div>
        
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchUsers} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 bg-blue-600 hover:bg-blue-700">
                <UserPlus className="w-4 h-4" />
                Novo Utilizador
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle className="text-white">Criar Novo Utilizador</DialogTitle>
                <DialogDescription className="text-zinc-400">
                  O utilizador receberá uma password temporária que deve ser alterada no primeiro login.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label className="text-zinc-300">Username</Label>
                  <Input
                    value={newUser.username}
                    onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                    placeholder="nome.apelido"
                    className="bg-zinc-800 border-zinc-700"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label className="text-zinc-300">Email (opcional)</Label>
                  <Input
                    type="email"
                    value={newUser.email}
                    onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                    placeholder="email@exemplo.com"
                    className="bg-zinc-800 border-zinc-700"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label className="text-zinc-300">Role</Label>
                  <Select value={newUser.role} onValueChange={(value) => setNewUser({ ...newUser, role: value })}>
                    <SelectTrigger className="bg-zinc-800 border-zinc-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-800 border-zinc-700">
                      {ROLES.filter(r => r.value !== "owner").map(role => (
                        <SelectItem key={role.value} value={role.value}>
                          <div className="flex items-center gap-2">
                            <role.icon className={`w-4 h-4 ${role.color}`} />
                            {role.label}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                  Cancelar
                </Button>
                <Button onClick={handleCreateUser} className="bg-blue-600 hover:bg-blue-700">
                  Criar Utilizador
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Temporary Password Dialog */}
      <Dialog open={!!tempPassword} onOpenChange={() => setTempPassword(null)}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-yellow-400" />
              Password Temporária
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Guarde esta password - não será possível vê-la novamente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="py-4">
            <div className="flex items-center gap-2 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
              <code className="flex-1 text-lg font-mono text-yellow-400">{tempPassword}</code>
              <Button 
                variant="ghost" 
                size="icon"
                onClick={() => copyToClipboard(tempPassword)}
              >
                <Copy className="w-4 h-4" />
              </Button>
            </div>
            
            <div className="mt-4 flex items-start gap-2 text-sm text-zinc-400">
              <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 shrink-0" />
              <p>O utilizador será obrigado a alterar esta password no primeiro login.</p>
            </div>
          </div>
          
          <DialogFooter>
            <Button onClick={() => setTempPassword(null)} className="bg-blue-600 hover:bg-blue-700">
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Role Legend */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4">
          <div className="flex items-center gap-6 text-sm">
            <span className="text-zinc-500">Permissões:</span>
            {ROLES.map(role => (
              <div key={role.value} className="flex items-center gap-2">
                <RoleBadge role={role.value} />
                <span className="text-zinc-500">
                  {role.value === "owner" && "- Tudo + Hard Caps"}
                  {role.value === "admin" && "- Tudo exceto Hard Caps"}
                  {role.value === "tester" && "- Leitura + Credenciais"}
                  {role.value === "viewer" && "- Apenas leitura"}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Users className="w-5 h-5" />
            Utilizadores ({users.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800">
                <TableHead className="text-zinc-400">Username</TableHead>
                <TableHead className="text-zinc-400">Email</TableHead>
                <TableHead className="text-zinc-400">Role</TableHead>
                <TableHead className="text-zinc-400">Estado</TableHead>
                <TableHead className="text-zinc-400">Criado</TableHead>
                <TableHead className="text-zinc-400">Último Login</TableHead>
                <TableHead className="text-zinc-400 text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id} className="border-zinc-800">
                  <TableCell className="font-mono text-white">{user.username}</TableCell>
                  <TableCell className="text-zinc-400">{user.email || "-"}</TableCell>
                  <TableCell>
                    <Select 
                      value={user.role} 
                      onValueChange={(value) => handleUpdateRole(user.id, value)}
                      disabled={user.role === "owner"}
                    >
                      <SelectTrigger className="w-32 h-8 bg-transparent border-0">
                        <RoleBadge role={user.role} />
                      </SelectTrigger>
                      <SelectContent className="bg-zinc-800 border-zinc-700">
                        {ROLES.map(role => (
                          <SelectItem key={role.value} value={role.value}>
                            <div className="flex items-center gap-2">
                              <role.icon className={`w-4 h-4 ${role.color}`} />
                              {role.label}
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    {user.is_active ? (
                      <Badge className="bg-green-500/20 text-green-400 border-0 gap-1">
                        <CheckCircle className="w-3 h-3" />
                        Ativo
                      </Badge>
                    ) : (
                      <Badge className="bg-red-500/20 text-red-400 border-0 gap-1">
                        <Ban className="w-3 h-3" />
                        Inativo
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-zinc-500 text-sm">
                    {user.created_at ? new Date(user.created_at).toLocaleDateString('pt-PT') : "-"}
                  </TableCell>
                  <TableCell className="text-zinc-500 text-sm">
                    {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString('pt-PT') : "Nunca"}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleResetPassword(user.id)}
                        title="Resetar Password"
                      >
                        <Key className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleActive(user.id, user.is_active)}
                        title={user.is_active ? "Desativar" : "Ativar"}
                        disabled={user.role === "owner"}
                      >
                        {user.is_active ? (
                          <Ban className="w-4 h-4 text-red-400" />
                        ) : (
                          <CheckCircle className="w-4 h-4 text-green-400" />
                        )}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          
          {users.length === 0 && !loading && (
            <div className="text-center py-8 text-zinc-500">
              Nenhum utilizador encontrado
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminUsers;
