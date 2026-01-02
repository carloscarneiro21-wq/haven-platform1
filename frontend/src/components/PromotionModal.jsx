import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/App";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowRight,
  Loader2,
  Shield,
  AlertTriangle,
  CheckCircle2,
  FileText,
  GitCompare,
  Send,
} from "lucide-react";

const PromotionModal = ({ open, onClose, runId, runReport }) => {
  const [loading, setLoading] = useState(false);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [loadingDiff, setLoadingDiff] = useState(false);
  
  // Form state
  const [agentId, setAgentId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [toProfileId, setToProfileId] = useState("");
  const [fromProfileId, setFromProfileId] = useState("");
  const [notes, setNotes] = useState("");
  
  // Data state
  const [agents, setAgents] = useState([]);
  const [runProfiles, setRunProfiles] = useState([]);
  const [currentProfile, setCurrentProfile] = useState(null);
  const [diff, setDiff] = useState(null);

  // Change type descriptions
  const CHANGE_TYPE_INFO = {
    added: { label: "New", icon: "➕", description: "Parameter added" },
    removed: { label: "Removed", icon: "➖", description: "Parameter removed" },
    modified: { label: "Changed", icon: "✏️", description: "Value changed" },
  };

  // Fetch agents on mount
  useEffect(() => {
    if (open) {
      fetchAgents();
      if (runId) {
        fetchRunProfiles(runId);
      }
    }
  }, [open, runId]);

  // Fetch current profile when agent changes
  useEffect(() => {
    if (agentId) {
      fetchCurrentProfile(agentId);
    }
  }, [agentId]);

  // Fetch diff when profiles change
  useEffect(() => {
    if (fromProfileId && toProfileId) {
      fetchDiff(fromProfileId, toProfileId);
    }
  }, [fromProfileId, toProfileId]);

  const fetchAgents = async () => {
    try {
      const response = await api.get("/agents");
      setAgents(response.data || []);
      // Auto-select first agent if available
      if (response.data?.length > 0 && !agentId) {
        const first = response.data[0];
        setAgentId(first.id || first.agent_id);
        setStrategyId(first.type || first.strategy_id || "");
      }
    } catch (error) {
      console.error("Failed to fetch agents:", error);
    }
  };

  const fetchRunProfiles = async (rid) => {
    setLoadingProfiles(true);
    try {
      const response = await api.get(`/profiles/by-run/${rid}`);
      setRunProfiles(response.data.profiles || []);
      // Auto-select first profile if available
      if (response.data.profiles?.length > 0) {
        setToProfileId(response.data.profiles[0].profile_id);
      }
    } catch (error) {
      console.error("Failed to fetch run profiles:", error);
      // If no profiles from run, show message
      setRunProfiles([]);
    } finally {
      setLoadingProfiles(false);
    }
  };

  const fetchCurrentProfile = async (aid) => {
    try {
      const response = await api.get(`/profiles/${aid}`);
      setCurrentProfile(response.data);
      if (response.data?.profile_active_id) {
        setFromProfileId(response.data.profile_active_id);
      }
    } catch (error) {
      console.error("Failed to fetch current profile:", error);
      setCurrentProfile(null);
      setFromProfileId("");
    }
  };

  const fetchDiff = async (from, to) => {
    setLoadingDiff(true);
    try {
      const params = new URLSearchParams();
      if (from) params.append("from_profile", from);
      if (to) params.append("to_profile", to);
      
      const response = await api.get(`/profiles/diff?${params.toString()}`);
      setDiff(response.data);
    } catch (error) {
      console.error("Failed to fetch diff:", error);
      setDiff(null);
    } finally {
      setLoadingDiff(false);
    }
  };

  const handleSubmit = async () => {
    if (!agentId || !strategyId || !toProfileId) {
      toast.error("Please fill all required fields");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        agent_id: agentId,
        strategy_id: strategyId,
        from_profile_id: fromProfileId || "",
        to_profile_id: toProfileId,
        target_env: "paper_live", // MVP only allows paper_live
        notes: notes,
      };

      const response = await api.post("/promotions/request", payload);
      toast.success(`Promotion request created: ${response.data.request_id}`);
      onClose(true); // Close with success flag
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create promotion request");
    } finally {
      setLoading(false);
    }
  };

  const getChangeTypeColor = (type) => {
    switch (type) {
      case "added": return "text-green-500 bg-green-500/10";
      case "removed": return "text-red-500 bg-red-500/10";
      case "modified": return "text-yellow-500 bg-yellow-500/10";
      default: return "text-[#848E9C]";
    }
  };

  const getSectionIcon = (section) => {
    switch (section) {
      case "params": return "⚙️";
      case "constraints": return "🛡️";
      case "dex_rules": return "💱";
      case "infra_rules": return "🖥️";
      default: return "📋";
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="bg-[#1E2329] border-white/8 text-[#EAECEF] max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <GitCompare className="w-5 h-5 text-[#F0B90B]" />
            Propose Profile Promotion
          </DialogTitle>
          <DialogDescription className="text-[#848E9C]">
            Promote a learned profile from Sandbox to Paper Trading environment
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 pr-4 -mr-4">
          <div className="space-y-6 py-4">
            {/* Safety Notice */}
            <div className="p-3 bg-[#F0B90B]/10 border border-[#F0B90B]/30 rounded-lg">
              <div className="flex items-start gap-2">
                <Shield className="w-4 h-4 text-[#F0B90B] mt-0.5 shrink-0" />
                <div className="text-sm">
                  <span className="font-medium text-[#F0B90B]">MVP Safety Mode:</span>
                  <span className="text-[#B7BDC6] ml-1">
                    Promotions are restricted to <Badge className="bg-[#2B3139] text-[#F0B90B] text-xs mx-1">paper_live</Badge> only.
                    LIVE trading remains disabled for protection.
                  </span>
                </div>
              </div>
            </div>

            {/* Promotion Flow Explanation */}
            <div className="flex items-center justify-center gap-2 text-sm text-[#848E9C]">
              <Badge variant="outline" className="border-white/20">Sandbox Profile</Badge>
              <ArrowRight className="w-4 h-4" />
              <Badge variant="outline" className="border-white/20">Review Diff</Badge>
              <ArrowRight className="w-4 h-4" />
              <Badge variant="outline" className="border-[#F0B90B]/30 text-[#F0B90B]">Paper Live</Badge>
            </div>

            {/* Agent Selection */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-[#B7BDC6]">Agent</Label>
                <Select value={agentId} onValueChange={(v) => {
                  setAgentId(v);
                  const agent = agents.find(a => (a.id || a.agent_id) === v);
                  if (agent) {
                    setStrategyId(agent.type || agent.strategy_id || "");
                  }
                }}>
                  <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                    <SelectValue placeholder="Select agent" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#2B3139] border-white/8">
                    {agents.map((agent) => (
                      <SelectItem key={agent.id || agent.agent_id} value={agent.id || agent.agent_id}>
                        {agent.id || agent.agent_id} ({agent.type || agent.strategy_id})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-[#B7BDC6]">Strategy</Label>
                <Input
                  value={strategyId}
                  onChange={(e) => setStrategyId(e.target.value)}
                  placeholder="e.g., grid, dca, sniper"
                  className="bg-[#2B3139] border-white/8 text-[#EAECEF]"
                />
              </div>
            </div>

            {/* Profile Selection */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-[#B7BDC6]">Current Profile (from)</Label>
                <div className="p-3 bg-[#2B3139] rounded-lg border border-white/8">
                  {currentProfile?.profile_active_id ? (
                    <div>
                      <code className="text-[#F0B90B] text-sm">{currentProfile.profile_active_id}</code>
                      {currentProfile.active_version && (
                        <div className="text-xs text-[#848E9C] mt-1">
                          v{currentProfile.active_version.version} • {currentProfile.active_version.source}
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-[#848E9C] text-sm">No active profile</span>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-[#B7BDC6]">New Profile (to) *</Label>
                {loadingProfiles ? (
                  <div className="p-3 bg-[#2B3139] rounded-lg border border-white/8 text-center">
                    <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                    Loading profiles...
                  </div>
                ) : runProfiles.length > 0 ? (
                  <Select value={toProfileId} onValueChange={setToProfileId}>
                    <SelectTrigger className="bg-[#2B3139] border-white/8 text-[#EAECEF]">
                      <SelectValue placeholder="Select profile" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#2B3139] border-white/8">
                      {runProfiles.map((profile) => (
                        <SelectItem key={profile.profile_id} value={profile.profile_id}>
                          {profile.profile_id} (v{profile.version})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <div className="space-y-2">
                    <Input
                      value={toProfileId}
                      onChange={(e) => setToProfileId(e.target.value)}
                      placeholder="Enter profile ID"
                      className="bg-[#2B3139] border-white/8 text-[#EAECEF]"
                    />
                    <p className="text-xs text-[#848E9C]">
                      No profiles found for this run. Enter a profile ID manually.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Target Environment */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Target Environment</Label>
              <div className="flex items-center gap-4">
                <div className="flex-1 flex items-center gap-2 p-3 bg-[#2B3139] rounded-lg border-2 border-[#F0B90B]/50">
                  <CheckCircle2 className="w-4 h-4 text-[#F0B90B]" />
                  <div>
                    <span className="text-[#EAECEF] font-medium">paper_live</span>
                    <p className="text-xs text-[#848E9C]">Paper trading with live market data</p>
                  </div>
                  <Badge className="bg-[#F0B90B]/20 text-[#F0B90B] text-xs ml-auto">Active</Badge>
                </div>
                <div className="flex-1 flex items-center gap-2 p-3 bg-[#2B3139]/50 rounded-lg border border-white/8 opacity-50 cursor-not-allowed">
                  <AlertTriangle className="w-4 h-4 text-[#848E9C]" />
                  <div>
                    <span className="text-[#848E9C]">live</span>
                    <p className="text-xs text-[#848E9C]">Real trading (restricted)</p>
                  </div>
                  <Badge className="bg-[#848E9C]/20 text-[#848E9C] text-xs ml-auto">Disabled</Badge>
                </div>
              </div>
            </div>

            {/* Diff Viewer */}
            {(fromProfileId || toProfileId) && (
              <div className="space-y-2">
                <Label className="text-[#B7BDC6] flex items-center gap-2">
                  <GitCompare className="w-4 h-4" />
                  Profile Diff
                </Label>
                <div className="bg-[#0B0E11] rounded-lg border border-white/8 overflow-hidden">
                  {loadingDiff ? (
                    <div className="p-4 text-center">
                      <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                      Loading diff...
                    </div>
                  ) : diff?.changes?.length > 0 ? (
                    <div>
                      {/* Summary */}
                      <div className="p-3 border-b border-white/8 bg-[#1E2329]">
                        <div className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-4">
                            <span className="text-[#848E9C]">Changes:</span>
                            <span className="text-[#EAECEF] font-medium">{diff.summary?.total_changes || 0}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {Object.entries(diff.summary?.by_section || {}).map(([section, count]) => (
                              <Badge key={section} variant="outline" className="border-white/20 text-[#B7BDC6]">
                                {getSectionIcon(section)} {section}: {count}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                      
                      {/* Changes List */}
                      <ScrollArea className="h-48">
                        <div className="p-2 space-y-1">
                          {diff.changes.map((change, idx) => (
                            <div key={idx} className="flex items-center gap-2 p-2 bg-[#1E2329] rounded text-sm font-mono">
                              <Badge variant="outline" className={`text-xs shrink-0 ${getChangeTypeColor(change.change_type)}`}>
                                {CHANGE_TYPE_INFO[change.change_type]?.icon} {CHANGE_TYPE_INFO[change.change_type]?.label || change.change_type}
                              </Badge>
                              <span className="text-[#848E9C] shrink-0">{change.section}</span>
                              <span className="text-[#B7BDC6] truncate">{change.field}</span>
                              <ArrowRight className="w-3 h-3 text-[#848E9C] shrink-0" />
                              <span className={`px-1.5 py-0.5 rounded text-xs ${getChangeTypeColor(change.change_type)}`}>
                                {change.from !== null && change.from !== undefined ? String(change.from) : "—"}
                              </span>
                              <span className="text-[#848E9C]">→</span>
                              <span className={`px-1.5 py-0.5 rounded text-xs ${getChangeTypeColor(change.change_type)}`}>
                                {change.to !== null && change.to !== undefined ? String(change.to) : "—"}
                              </span>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    </div>
                  ) : (
                    <div className="p-4 text-center text-[#848E9C]">
                      {!fromProfileId && !toProfileId ? (
                        "Select profiles to view diff"
                      ) : !fromProfileId ? (
                        "No current profile - showing new profile only"
                      ) : (
                        "No differences found"
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Notes */}
            <div className="space-y-2">
              <Label className="text-[#B7BDC6]">Notes (optional)</Label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add notes about this promotion request..."
                className="bg-[#2B3139] border-white/8 text-[#EAECEF] min-h-[80px]"
              />
            </div>
          </div>
        </ScrollArea>

        <DialogFooter className="border-t border-white/8 pt-4">
          <Button
            variant="outline"
            onClick={() => onClose(false)}
            className="border-white/10 text-[#848E9C]"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={loading || !agentId || !strategyId || !toProfileId}
            className="bg-[#F0B90B] hover:bg-[#D4A30A] text-[#0B0E11] font-semibold"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Send className="w-4 h-4 mr-2" />
            )}
            Submit Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PromotionModal;
