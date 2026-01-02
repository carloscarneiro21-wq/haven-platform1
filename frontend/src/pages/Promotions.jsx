import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  RefreshCw,
  GitCompare,
  Check,
  X,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Shield,
  FileText,
  User,
  ArrowRight,
  Loader2,
  ListOrdered,
  Bot,
  Zap,
} from "lucide-react";

const STATUS_CONFIG = {
  draft: { color: "bg-[#848E9C]/20 text-[#848E9C] border-[#848E9C]/30", icon: FileText },
  pending: { color: "bg-yellow-500/20 text-yellow-500 border-yellow-500/30", icon: Clock },
  approved: { color: "bg-blue-500/20 text-blue-500 border-blue-500/30", icon: Check },
  rejected: { color: "bg-red-500/20 text-red-500 border-red-500/30", icon: XCircle },
  applied: { color: "bg-green-500/20 text-green-500 border-green-500/30", icon: CheckCircle2 },
};

const Promotions = () => {
  const { user, hasRole } = useAuth();
  const isOwner = hasRole(["owner"]);

  const [promotions, setPromotions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPromotion, setSelectedPromotion] = useState(null);
  const [diff, setDiff] = useState(null);
  const [loadingDiff, setLoadingDiff] = useState(false);
  const [activeTab, setActiveTab] = useState("all");
  
  // Action modals
  const [approveModalOpen, setApproveModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [applyConfirmOpen, setApplyConfirmOpen] = useState(false);
  const [actionNotes, setActionNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const fetchPromotions = useCallback(async (status = null) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (status && status !== "all") {
        params.append("status", status);
      }
      const response = await api.get(`/promotions?${params.toString()}`);
      setPromotions(response.data.promotions || []);
    } catch (error) {
      console.error("Failed to fetch promotions:", error);
      toast.error("Failed to load promotions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPromotions(activeTab);
  }, [activeTab, fetchPromotions]);

  const fetchDiff = async (fromProfile, toProfile) => {
    setLoadingDiff(true);
    try {
      const params = new URLSearchParams();
      if (fromProfile) params.append("from_profile", fromProfile);
      if (toProfile) params.append("to_profile", toProfile);
      
      const response = await api.get(`/profiles/diff?${params.toString()}`);
      setDiff(response.data);
    } catch (error) {
      console.error("Failed to fetch diff:", error);
      setDiff(null);
    } finally {
      setLoadingDiff(false);
    }
  };

  const selectPromotion = async (promo) => {
    setSelectedPromotion(promo);
    setDiff(null);
    if (promo.from_profile_id || promo.to_profile_id) {
      await fetchDiff(promo.from_profile_id, promo.to_profile_id);
    }
  };

  const handleApprove = async () => {
    if (!selectedPromotion) return;
    setActionLoading(true);
    try {
      await api.post("/promotions/approve", {
        request_id: selectedPromotion.request_id,
        approve: true,
        notes: actionNotes,
      });
      toast.success("Promotion approved");
      setApproveModalOpen(false);
      setActionNotes("");
      fetchPromotions(activeTab);
      setSelectedPromotion(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to approve");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedPromotion) return;
    setActionLoading(true);
    try {
      await api.post("/promotions/approve", {
        request_id: selectedPromotion.request_id,
        approve: false,
        notes: actionNotes,
      });
      toast.success("Promotion rejected");
      setRejectModalOpen(false);
      setActionNotes("");
      fetchPromotions(activeTab);
      setSelectedPromotion(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to reject");
    } finally {
      setActionLoading(false);
    }
  };

  const handleApply = async () => {
    if (!selectedPromotion) return;
    setActionLoading(true);
    try {
      await api.post("/promotions/apply", {
        request_id: selectedPromotion.request_id,
      });
      toast.success("Profile promoted successfully!");
      setApplyConfirmOpen(false);
      fetchPromotions(activeTab);
      setSelectedPromotion(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to apply promotion");
    } finally {
      setActionLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusBadge = (status) => {
    const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
    const Icon = config.icon;
    return (
      <Badge className={`${config.color} border`}>
        <Icon className="w-3 h-3 mr-1" />
        {status.toUpperCase()}
      </Badge>
    );
  };

  const getChangeTypeColor = (type) => {
    switch (type) {
      case "added": return "text-green-500 bg-green-500/10";
      case "removed": return "text-red-500 bg-red-500/10";
      case "modified": return "text-yellow-500 bg-yellow-500/10";
      default: return "text-[#848E9C]";
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#EAECEF]">Profile Promotions</h1>
          <p className="text-[#848E9C] text-sm">Manage learned profile promotions from Sandbox</p>
        </div>
        
        <div className="flex items-center gap-3">
          <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] border border-[#F0B90B]/30 px-3 py-1">
            <Shield className="w-3 h-3 mr-1.5" />
            PAPER MODE ONLY
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchPromotions(activeTab)}
            className="border-white/10 text-[#848E9C]"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Promotions List */}
        <Card className="lg:col-span-1 bg-[#1E2329] border-white/8">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-[#EAECEF]">Requests</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full bg-[#0B0E11] rounded-none border-b border-white/8">
                <TabsTrigger value="all" className="flex-1 data-[state=active]:bg-[#2B3139]">All</TabsTrigger>
                <TabsTrigger value="pending" className="flex-1 data-[state=active]:bg-[#2B3139]">Pending</TabsTrigger>
                <TabsTrigger value="approved" className="flex-1 data-[state=active]:bg-[#2B3139]">Approved</TabsTrigger>
              </TabsList>
            </Tabs>

            <ScrollArea className="h-[500px]">
              <div className="p-2 space-y-2">
                {loading ? (
                  <div className="p-4 text-center text-[#848E9C]">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
                    Loading...
                  </div>
                ) : promotions.length === 0 ? (
                  <div className="p-8 text-center text-[#848E9C]">
                    <ListOrdered className="w-12 h-12 mx-auto mb-4 opacity-50" />
                    <p>No promotion requests found</p>
                  </div>
                ) : (
                  promotions.map((promo) => (
                    <button
                      key={promo.request_id}
                      onClick={() => selectPromotion(promo)}
                      className={`w-full p-3 rounded-lg text-left transition-colors ${
                        selectedPromotion?.request_id === promo.request_id
                          ? "bg-[#F0B90B]/10 border border-[#F0B90B]/30"
                          : "bg-[#2B3139] hover:bg-[#3B4149] border border-transparent"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <code className="text-[#F0B90B] text-sm">{promo.request_id}</code>
                        {getStatusBadge(promo.status)}
                      </div>
                      <div className="flex items-center gap-2 text-sm text-[#848E9C]">
                        <Bot className="w-3 h-3" />
                        <span>{promo.agent_id}</span>
                        <span className="text-[#3B4149]">•</span>
                        <span>{promo.strategy_id}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-[#848E9C]">
                        <User className="w-3 h-3" />
                        <span>by {promo.requested_by}</span>
                      </div>
                      <div className="text-xs text-[#848E9C] mt-1">
                        {formatDate(promo.created_at)}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Detail Panel */}
        <Card className="lg:col-span-2 bg-[#1E2329] border-white/8">
          <CardHeader>
            <CardTitle className="text-lg text-[#EAECEF]">
              {selectedPromotion ? `Request: ${selectedPromotion.request_id}` : "Select a Request"}
            </CardTitle>
            {selectedPromotion && (
              <CardDescription>
                {formatDate(selectedPromotion.created_at)}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {selectedPromotion ? (
              <div className="space-y-6">
                {/* Request Info */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">Agent</span>
                    <div className="p-2 bg-[#2B3139] rounded text-[#EAECEF] font-mono">
                      {selectedPromotion.agent_id}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">Strategy</span>
                    <div className="p-2 bg-[#2B3139] rounded text-[#EAECEF] font-mono">
                      {selectedPromotion.strategy_id}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">From Profile</span>
                    <div className="p-2 bg-[#2B3139] rounded text-[#848E9C] font-mono text-sm">
                      {selectedPromotion.from_profile_id || "—"}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">To Profile</span>
                    <div className="p-2 bg-[#2B3139] rounded text-[#F0B90B] font-mono text-sm">
                      {selectedPromotion.to_profile_id}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">Target Env</span>
                    <div className="p-2 bg-[#2B3139] rounded">
                      <Badge className="bg-[#F0B90B]/20 text-[#F0B90B]">
                        {selectedPromotion.target_env}
                      </Badge>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">Status</span>
                    <div className="p-2 bg-[#2B3139] rounded">
                      {getStatusBadge(selectedPromotion.status)}
                    </div>
                  </div>
                </div>

                {/* Notes */}
                {selectedPromotion.approval_notes && (
                  <div className="space-y-1">
                    <span className="text-xs text-[#848E9C] uppercase">Notes</span>
                    <div className="p-3 bg-[#2B3139] rounded text-[#B7BDC6] text-sm">
                      {selectedPromotion.approval_notes}
                    </div>
                  </div>
                )}

                {selectedPromotion.rejection_reason && (
                  <div className="space-y-1">
                    <span className="text-xs text-red-500 uppercase">Rejection Reason</span>
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
                      {selectedPromotion.rejection_reason}
                    </div>
                  </div>
                )}

                {/* Diff Viewer */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <GitCompare className="w-4 h-4 text-[#F0B90B]" />
                    <span className="text-sm font-medium text-[#EAECEF]">Profile Diff</span>
                  </div>
                  <div className="bg-[#0B0E11] rounded-lg border border-white/8">
                    {loadingDiff ? (
                      <div className="p-4 text-center text-[#848E9C]">
                        <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                        Loading diff...
                      </div>
                    ) : diff?.changes?.length > 0 ? (
                      <ScrollArea className="h-48">
                        <div className="p-2 space-y-1">
                          {diff.changes.map((change, idx) => (
                            <div key={idx} className="flex items-center gap-2 p-2 bg-[#1E2329] rounded text-xs font-mono">
                              <span className="text-[#848E9C] w-20 shrink-0">{change.section}</span>
                              <span className="text-[#B7BDC6] flex-1">{change.field}</span>
                              <span className={`px-1.5 py-0.5 rounded ${getChangeTypeColor(change.change_type)}`}>
                                {change.from !== null && change.from !== undefined ? String(change.from) : "∅"}
                              </span>
                              <ArrowRight className="w-3 h-3 text-[#848E9C]" />
                              <span className={`px-1.5 py-0.5 rounded ${getChangeTypeColor(change.change_type)}`}>
                                {change.to !== null && change.to !== undefined ? String(change.to) : "∅"}
                              </span>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    ) : (
                      <div className="p-4 text-center text-[#848E9C]">
                        No differences or profiles not found
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {isOwner && (
                  <div className="flex items-center gap-3 pt-4 border-t border-white/8">
                    {selectedPromotion.status === "pending" && (
                      <>
                        <Button
                          onClick={() => setApproveModalOpen(true)}
                          className="bg-green-600 hover:bg-green-700 text-white"
                        >
                          <Check className="w-4 h-4 mr-2" />
                          Approve
                        </Button>
                        <Button
                          onClick={() => setRejectModalOpen(true)}
                          variant="outline"
                          className="border-red-500/30 text-red-500 hover:bg-red-500/10"
                        >
                          <X className="w-4 h-4 mr-2" />
                          Reject
                        </Button>
                      </>
                    )}
                    {selectedPromotion.status === "approved" && (
                      <Button
                        onClick={() => setApplyConfirmOpen(true)}
                        className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
                      >
                        <Zap className="w-4 h-4 mr-2" />
                        Apply Promotion
                      </Button>
                    )}
                    {selectedPromotion.status === "applied" && (
                      <div className="flex items-center gap-2 text-green-500">
                        <CheckCircle2 className="w-5 h-5" />
                        <span>Profile has been activated</span>
                      </div>
                    )}
                    {selectedPromotion.status === "rejected" && (
                      <div className="flex items-center gap-2 text-red-500">
                        <XCircle className="w-5 h-5" />
                        <span>Request was rejected</span>
                      </div>
                    )}
                  </div>
                )}

                {!isOwner && selectedPromotion.status === "pending" && (
                  <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-500 text-sm">
                    <AlertTriangle className="w-4 h-4 inline mr-2" />
                    Only the Owner can approve or reject promotion requests.
                  </div>
                )}
              </div>
            ) : (
              <div className="py-12 text-center text-[#848E9C]">
                <GitCompare className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Select a promotion request to view details</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Approve Modal */}
      <Dialog open={approveModalOpen} onOpenChange={setApproveModalOpen}>
        <DialogContent className="bg-[#1E2329] border-white/8 text-[#EAECEF]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Check className="w-5 h-5 text-green-500" />
              Approve Promotion
            </DialogTitle>
            <DialogDescription className="text-[#848E9C]">
              Approve this profile promotion request. The profile can then be applied.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm text-[#B7BDC6]">Approval Notes (optional)</label>
              <Textarea
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                placeholder="Add notes about this approval..."
                className="bg-[#2B3139] border-white/8 text-[#EAECEF]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveModalOpen(false)} className="border-white/10">
              Cancel
            </Button>
            <Button
              onClick={handleApprove}
              disabled={actionLoading}
              className="bg-green-600 hover:bg-green-700"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Check className="w-4 h-4 mr-2" />}
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Modal */}
      <Dialog open={rejectModalOpen} onOpenChange={setRejectModalOpen}>
        <DialogContent className="bg-[#1E2329] border-white/8 text-[#EAECEF]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <X className="w-5 h-5 text-red-500" />
              Reject Promotion
            </DialogTitle>
            <DialogDescription className="text-[#848E9C]">
              Reject this profile promotion request. Please provide a reason.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm text-[#B7BDC6]">Rejection Reason *</label>
              <Textarea
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                placeholder="Explain why this promotion is being rejected..."
                className="bg-[#2B3139] border-white/8 text-[#EAECEF]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectModalOpen(false)} className="border-white/10">
              Cancel
            </Button>
            <Button
              onClick={handleReject}
              disabled={actionLoading || !actionNotes.trim()}
              className="bg-red-600 hover:bg-red-700"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <X className="w-4 h-4 mr-2" />}
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Apply Confirmation */}
      <AlertDialog open={applyConfirmOpen} onOpenChange={setApplyConfirmOpen}>
        <AlertDialogContent className="bg-[#1E2329] border-white/8 text-[#EAECEF]">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-[#F0B90B]" />
              Apply Profile Promotion
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[#848E9C]">
              This will activate the new profile for the agent in <strong className="text-[#F0B90B]">paper_live</strong> mode.
              The agent will start using the new profile parameters.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-[#2B3139] border-white/10 text-[#EAECEF] hover:bg-[#3B4149]">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleApply}
              disabled={actionLoading}
              className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Zap className="w-4 h-4 mr-2" />}
              Apply Now
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default Promotions;
