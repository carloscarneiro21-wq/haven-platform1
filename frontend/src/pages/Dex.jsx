import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { 
  Coins, 
  RefreshCw, 
  Play, 
  Square, 
  Search, 
  Shield, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  ExternalLink,
  Copy,
  Wallet,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Zap,
  Eye,
  Ban,
  Send,
  Settings
} from "lucide-react";

// Sniper Preset Manager
import SniperPresetManager from "@/components/SniperPresetManager";

// Sniper Advisor
import SniperAdvisor from "@/components/SniperAdvisor";

// Help components
import { InfoIcon, FieldTooltip } from "@/components/help";
import { 
  SniperHelpContent, SniperTooltips,
  WalletHelpContent, WalletTooltips,
  SwapsHelpContent, SwapsTooltips
} from "@/help/dex";

// BSC Chain Config
const BSC_CHAIN_ID = "0x38"; // 56 in hex
const BSC_CONFIG = {
  chainId: BSC_CHAIN_ID,
  chainName: "BNB Smart Chain",
  nativeCurrency: { name: "BNB", symbol: "BNB", decimals: 18 },
  rpcUrls: ["https://bsc-dataseed.binance.org/"],
  blockExplorerUrls: ["https://bscscan.com/"],
};

export default function DexPage() {
  // State
  const [dexStatus, setDexStatus] = useState(null);
  const [pairs, setPairs] = useState([]);
  const [swapPlans, setSwapPlans] = useState([]);
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [sniperRunning, setSniperRunning] = useState(false);
  
  // MetaMask
  const [walletConnected, setWalletConnected] = useState(false);
  const [walletAddress, setWalletAddress] = useState("");
  const [chainId, setChainId] = useState(null);
  
  // Swap Plan Form
  const [selectedToken, setSelectedToken] = useState(null);
  const [swapAmount, setSwapAmount] = useState("0.05");
  const [slippage, setSlippage] = useState("2.0");
  
  // Tab state
  const [activeTab, setActiveTab] = useState("pairs");

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, pairsRes, swapsRes, positionsRes] = await Promise.all([
        api.get("/dex/status"),
        api.get("/dex/pairs/new?limit=20"),
        api.get("/dex/swaps/pending"),
        api.get("/dex/positions?status=all&limit=20"),
      ]);
      setDexStatus(statusRes.data);
      // Handle new response format with items array
      setPairs(pairsRes.data?.items || pairsRes.data || []);
      setSwapPlans(swapsRes.data?.items || swapsRes.data || []);
      setPositions(positionsRes.data?.items || positionsRes.data || []);
      // Check if DEX is in simulation mode
      setSniperRunning(statusRes.data?.sniper_enabled || statusRes.data?.sniper?.running || false);
    } catch (e) {
      console.error("Failed to fetch DEX data:", e);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Check MetaMask connection on load
  useEffect(() => {
    checkWalletConnection();
    if (window.ethereum) {
      window.ethereum.on("accountsChanged", handleAccountsChanged);
      window.ethereum.on("chainChanged", handleChainChanged);
    }
    return () => {
      if (window.ethereum) {
        window.ethereum.removeListener("accountsChanged", handleAccountsChanged);
        window.ethereum.removeListener("chainChanged", handleChainChanged);
      }
    };
  }, []);

  const checkWalletConnection = async () => {
    if (window.ethereum) {
      try {
        const accounts = await window.ethereum.request({ method: "eth_accounts" });
        if (accounts.length > 0) {
          setWalletAddress(accounts[0]);
          setWalletConnected(true);
          const chain = await window.ethereum.request({ method: "eth_chainId" });
          setChainId(chain);
        }
      } catch (e) {
        console.error("Error checking wallet:", e);
      }
    }
  };

  const handleAccountsChanged = (accounts) => {
    if (accounts.length === 0) {
      setWalletConnected(false);
      setWalletAddress("");
    } else {
      setWalletAddress(accounts[0]);
      setWalletConnected(true);
    }
  };

  const handleChainChanged = (newChainId) => {
    setChainId(newChainId);
  };

  // Connect MetaMask
  const connectWallet = async () => {
    if (!window.ethereum) {
      toast.error("MetaMask not detected! Open this page directly in your browser (not in iframe/preview) to connect your wallet.", {
        duration: 6000,
      });
      return;
    }
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      setWalletAddress(accounts[0]);
      setWalletConnected(true);
      
      // Check/switch to BSC
      const currentChain = await window.ethereum.request({ method: "eth_chainId" });
      setChainId(currentChain);
      
      if (currentChain !== BSC_CHAIN_ID) {
        await switchToBSC();
      }
      
      toast.success("Wallet connected!");
    } catch (e) {
      if (e.code === 4001) {
        toast.error("Connection rejected by user");
      } else {
        toast.error("Failed to connect wallet: " + (e.message || "Unknown error"));
      }
    }
  };

  const switchToBSC = async () => {
    try {
      await window.ethereum.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: BSC_CHAIN_ID }],
      });
      setChainId(BSC_CHAIN_ID);
    } catch (switchError) {
      // Chain not added, add it
      if (switchError.code === 4902) {
        try {
          await window.ethereum.request({
            method: "wallet_addEthereumChain",
            params: [BSC_CONFIG],
          });
          setChainId(BSC_CHAIN_ID);
        } catch (addError) {
          toast.error("Failed to add BSC network");
        }
      }
    }
  };

  // Actions
  const scanPairs = async () => {
    setScanning(true);
    try {
      const res = await api.post("/dex/pairs/scan");
      toast.success(`Found ${res.data.count} new pairs`);
      fetchData();
    } catch (e) {
      toast.error("Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const runSniperOnce = async () => {
    setLoading(true);
    try {
      const res = await api.post("/dex/sniper/run-once");
      toast.success(`Scan complete: ${res.data.pairs_found} pairs, ${res.data.plans_created} plans`);
      fetchData();
    } catch (e) {
      toast.error("Sniper run failed");
    } finally {
      setLoading(false);
    }
  };

  const toggleSniper = async () => {
    try {
      if (sniperRunning) {
        const res = await api.post("/dex/sniper/stop");
        if (res.data?.status === "disabled") {
          toast.info(res.data?.note || "Sniper is in simulation mode");
        } else {
          toast.success("Sniper stopped");
        }
      } else {
        const res = await api.post("/dex/sniper/start");
        if (res.data?.status === "disabled") {
          toast.info(res.data?.note || "Sniper is disabled. Use Sandbox for simulations.", {
            duration: 5000,
          });
        } else {
          toast.success("Sniper started");
        }
      }
      fetchData();
    } catch (e) {
      toast.error("Failed to toggle sniper");
    }
  };

  const scoreToken = async (tokenAddress) => {
    try {
      const res = await api.post("/dex/token/score", { token: tokenAddress, chain: "bsc" });
      if (res.data?.status === "disabled") {
        toast.info(res.data?.note || "Token scoring disabled in simulation mode");
      } else {
        toast.success(`Score: ${res.data.score?.toFixed(1) || 0}/100 (${res.data.risk_level || 'N/A'})`);
      }
      fetchData();
    } catch (e) {
      toast.error("Scoring failed");
    }
  };

  const createSwapPlan = async (tokenAddress, symbol) => {
    try {
      const res = await api.post("/dex/swap/plan", {
        token_address: tokenAddress,
        amount_bnb: parseFloat(swapAmount),
        slippage_pct: parseFloat(slippage),
      });
      if (res.data?.status === "disabled") {
        toast.info(res.data?.note || "Swap creation disabled in simulation mode");
      } else {
        toast.success(`Swap plan created for ${symbol}`);
      }
      setSelectedToken(null);
      setActiveTab("swaps");
      fetchData();
    } catch (e) {
      toast.error("Failed to create swap plan");
    }
  };

  const approveSwap = async (planId) => {
    try {
      await api.post(`/dex/swap/${planId}/approve`);
      toast.success("Swap approved");
      fetchData();
    } catch (e) {
      toast.error("Approval failed");
    }
  };

  const rejectSwap = async (planId) => {
    try {
      await api.post(`/dex/swap/${planId}/reject`, { reason: "User rejected" });
      toast.success("Swap rejected");
      fetchData();
    } catch (e) {
      toast.error("Rejection failed");
    }
  };

  const simulateSwap = async (planId) => {
    try {
      const res = await api.post(`/dex/swap/${planId}/simulate`);
      toast.success(`Simulated: ${res.data.success ? "Success" : "Failed"}`);
      fetchData();
    } catch (e) {
      toast.error("Simulation failed");
    }
  };

  const sendViaMetaMask = async (plan) => {
    if (!walletConnected) {
      toast.error("Connect wallet first");
      return;
    }
    if (chainId !== BSC_CHAIN_ID) {
      await switchToBSC();
      return;
    }
    
    try {
      // Send transaction via MetaMask
      const txHash = await window.ethereum.request({
        method: "eth_sendTransaction",
        params: [{
          from: walletAddress,
          to: plan.tx_to,
          data: plan.tx_data,
          value: plan.tx_value,
          gas: "0x" + plan.tx_gas_limit.toString(16),
        }],
      });
      
      // Record submission
      await api.post("/dex/tx/submitted", { plan_id: plan.id, tx_hash: txHash });
      toast.success(`TX submitted: ${txHash.slice(0, 10)}...`);
      
      // Start monitoring
      monitorTransaction(txHash, plan.id);
      fetchData();
    } catch (e) {
      toast.error("Transaction failed: " + (e.message || "Unknown error"));
    }
  };

  const sellPosition = async (positionId) => {
    if (!walletConnected) {
      toast.error("Connect wallet first");
      return;
    }
    if (chainId !== BSC_CHAIN_ID) {
      await switchToBSC();
      return;
    }
    
    try {
      // Get sell transaction data
      const sellRes = await api.get(`/dex/position/${positionId}/sell-tx?wallet_address=${walletAddress}`);
      const sellTx = sellRes.data;
      
      // If approval needed, send approval first
      if (sellTx.requires_approval && sellTx.approval_tx) {
        toast.info("Sending approval transaction...");
        const approvalHash = await window.ethereum.request({
          method: "eth_sendTransaction",
          params: [{
            from: walletAddress,
            to: sellTx.approval_tx.to,
            data: sellTx.approval_tx.data,
            value: sellTx.approval_tx.value,
            gas: sellTx.approval_tx.gas,
          }],
        });
        toast.success("Approval sent, waiting for confirmation...");
        
        // Wait for approval to confirm
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
      
      // Send sell transaction
      toast.info("Sending sell transaction...");
      const txHash = await window.ethereum.request({
        method: "eth_sendTransaction",
        params: [{
          from: walletAddress,
          to: sellTx.to,
          data: sellTx.data,
          value: sellTx.value,
          gas: sellTx.gas,
        }],
      });
      
      toast.success(`Sell TX submitted: ${txHash.slice(0, 10)}...`);
      
      // Close position in backend
      await api.post(`/dex/position/${positionId}/close`, {
        tx_hash: txHash,
        realized_bnb: sellTx.expected_bnb,
      });
      
      fetchData();
    } catch (e) {
      toast.error("Sell failed: " + (e.message || "Unknown error"));
    }
  };

  const monitorTransaction = async (txHash, planId) => {
    // Poll for transaction receipt
    const maxAttempts = 30;
    for (let i = 0; i < maxAttempts; i++) {
      try {
        const res = await api.get(`/dex/tx/monitor/${txHash}`);
        if (res.data.confirmed) {
          if (res.data.success) {
            toast.success(`Transaction confirmed in block ${res.data.block_number}`);
          } else {
            toast.error("Transaction failed on-chain");
          }
          fetchData();
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 3000));
      } catch (e) {
        console.error("Monitor error:", e);
      }
    }
    toast.warning("Transaction monitoring timed out. Check BSCScan.");
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied!");
  };

  const formatAddress = (addr) => {
    if (!addr) return "???";
    return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
  };

  const formatUSD = (val) => {
    if (!val) return "$0";
    return `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  };

  const getRiskColor = (level) => {
    const colors = {
      SAFE: "text-green-400",
      LOW: "text-green-400",
      MEDIUM: "text-yellow-400",
      HIGH: "text-orange-400",
      CRITICAL: "text-red-400",
      SCAM: "text-red-500",
      UNKNOWN: "text-zinc-400",
    };
    return colors[level] || "text-zinc-400";
  };

  const getStatusBadge = (status) => {
    const configs = {
      pending: { color: "bg-yellow-500/20 text-yellow-400", icon: Clock },
      approved: { color: "bg-green-500/20 text-green-400", icon: CheckCircle },
      rejected: { color: "bg-red-500/20 text-red-400", icon: XCircle },
      submitted: { color: "bg-blue-500/20 text-blue-400", icon: Send },
      confirmed: { color: "bg-green-500/20 text-green-400", icon: CheckCircle },
      failed: { color: "bg-red-500/20 text-red-400", icon: XCircle },
    };
    const config = configs[status] || configs.pending;
    const Icon = config.icon;
    return (
      <Badge className={`${config.color} border-0 gap-1`}>
        <Icon className="w-3 h-3" />
        {status.toUpperCase()}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      {/* SIMULATION ONLY Banner */}
      {dexStatus?.mode === "SIMULATION_ONLY" && (
        <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5 shrink-0" />
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-semibold text-yellow-500">SIMULATION MODE</span>
                <Badge className="bg-yellow-500/20 text-yellow-500 border-0 text-xs">READ-ONLY</Badge>
              </div>
              <p className="text-sm text-[#B7BDC6]">
                {dexStatus?.note || "DEX trading is disabled in production. Use Sandbox and Sniper Hardening for simulated token evaluation."}
              </p>
              <div className="flex items-center gap-4 mt-2 text-xs text-[#848E9C]">
                <span>• Real trading disabled</span>
                <span>• No blockchain transactions</span>
                <span>• Use Sandbox for simulations</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="text-2xl font-rajdhani font-bold text-white tracking-wide">
              DEX SNIPER
            </h1>
            <p className="text-sm text-zinc-500">PancakeSwap V2 • BSC</p>
          </div>
          <InfoIcon title="Ajuda: DEX Sniper" content={<SniperHelpContent />} />
        </div>
        
        {/* Wallet Connection */}
        <div className="flex items-center gap-3">
          <InfoIcon title="Ajuda: MetaMask & Carteira" content={<WalletHelpContent />} />
          {walletConnected ? (
            <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800 rounded-sm">
              <Wallet className="w-4 h-4 text-green-400" />
              <span className="font-mono text-sm text-zinc-300">{formatAddress(walletAddress)}</span>
              {chainId === BSC_CHAIN_ID ? (
                <Badge className="bg-green-500/20 text-green-400 border-0 text-xs">BSC</Badge>
              ) : (
                <FieldTooltip text={WalletTooltips.switch_bsc}>
                  <Button size="sm" variant="outline" onClick={switchToBSC} className="h-6 text-xs">
                    Switch to BSC
                  </Button>
                </FieldTooltip>
              )}
            </div>
          ) : (
            <FieldTooltip text={WalletTooltips.connect}>
              <Button onClick={connectWallet} className="gap-2 bg-[#F0B90B] hover:bg-[#F0B90B]/80 text-black">
                <Wallet className="w-4 h-4" />
                Connect MetaMask
              </Button>
            </FieldTooltip>
          )}
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider">Pair Monitor</p>
                <p className="text-lg font-mono text-white">
                  {dexStatus?.pair_monitor?.cached_pairs || 0} pairs
                </p>
              </div>
              <Coins className="w-8 h-8 text-zinc-600" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider">Sniper Status</p>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${sniperRunning ? 'bg-green-400 animate-pulse' : 'bg-zinc-600'}`} />
                  <span className={`font-mono ${sniperRunning ? 'text-green-400' : 'text-zinc-500'}`}>
                    {sniperRunning ? "RUNNING" : "STOPPED"}
                  </span>
                </div>
              </div>
              <Zap className="w-8 h-8 text-zinc-600" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider">Pending Swaps</p>
                <p className="text-lg font-mono text-yellow-400">
                  {swapPlans.filter(p => p.status === "pending").length}
                </p>
              </div>
              <Clock className="w-8 h-8 text-zinc-600" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider">Mode</p>
                <Badge className={`${dexStatus?.pancakeswap?.paper_mode ? 'bg-blue-500/20 text-blue-400' : 'bg-red-500/20 text-red-400'} border-0`}>
                  {dexStatus?.pancakeswap?.paper_mode ? "PAPER" : "LIVE"}
                </Badge>
              </div>
              <Shield className="w-8 h-8 text-zinc-600" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-3">
        <FieldTooltip text={SniperTooltips.scan_pairs}>
          <Button onClick={scanPairs} disabled={scanning} className="gap-2 bg-zinc-800 hover:bg-zinc-700">
            <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
            Scan Pairs
          </Button>
        </FieldTooltip>
        <FieldTooltip text={SniperTooltips.run_once}>
          <Button onClick={runSniperOnce} disabled={loading} className="gap-2 bg-zinc-800 hover:bg-zinc-700">
            <Search className={`w-4 h-4`} />
            Run Once
          </Button>
        </FieldTooltip>
        <FieldTooltip text={SniperTooltips.start_sniper}>
          <Button 
            onClick={toggleSniper} 
            className={`gap-2 ${sniperRunning ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'}`}
          >
            {sniperRunning ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            {sniperRunning ? "Stop Sniper" : "Start Sniper"}
          </Button>
        </FieldTooltip>
        <Button onClick={fetchData} variant="outline" size="icon">
          <RefreshCw className="w-4 h-4" />
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-800">
        {[
          { id: "pairs", label: "New Pairs", count: pairs.length },
          { id: "swaps", label: "Swap Plans", count: swapPlans.length, helpTitle: "Ajuda: Swap Plans", helpContent: <SwapsHelpContent /> },
          { id: "positions", label: "Positions", count: positions.length },
          { id: "advisor", label: "Advisor", icon: <Search className="w-3 h-3" /> },
          { id: "presets", label: "Presets", icon: <Settings className="w-3 h-3" /> },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === tab.id 
                ? "text-white border-b-2 border-green-500" 
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {tab.icon && tab.icon}
            {tab.label} {tab.count !== undefined && <span className="text-xs text-zinc-600">({tab.count})</span>}
            {tab.helpContent && activeTab === tab.id && (
              <InfoIcon title={tab.helpTitle} content={tab.helpContent} className="ml-1" />
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "pairs" && (
        <div className="space-y-4">
          {/* Swap Plan Form */}
          {selectedToken && (
            <Card className="bg-green-500/10 border-green-500/30">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-zinc-400">Create Swap Plan for</span>
                    <span className="font-mono text-green-400">{selectedToken.symbol}</span>
                    <FieldTooltip text={SniperTooltips.trade_size}>
                      <Input
                        type="number"
                        value={swapAmount}
                        onChange={(e) => setSwapAmount(e.target.value)}
                        className="w-24 h-8 bg-zinc-800 border-zinc-700"
                        placeholder="BNB"
                      />
                    </FieldTooltip>
                    <span className="text-xs text-zinc-500">BNB</span>
                    <FieldTooltip text={SniperTooltips.slippage}>
                      <Input
                        type="number"
                        value={slippage}
                        onChange={(e) => setSlippage(e.target.value)}
                        className="w-20 h-8 bg-zinc-800 border-zinc-700"
                        placeholder="%"
                      />
                    </FieldTooltip>
                    <span className="text-xs text-zinc-500">% slippage</span>
                  </div>
                  <div className="flex gap-2">
                    <FieldTooltip text={SniperTooltips.create_plan}>
                      <Button 
                        onClick={() => createSwapPlan(selectedToken.address, selectedToken.symbol)}
                        className="bg-green-600 hover:bg-green-700"
                      >
                        Create Plan
                      </Button>
                    </FieldTooltip>
                    <Button variant="outline" onClick={() => setSelectedToken(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Pairs Table */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-zinc-800/50">
                <tr className="text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Pair</th>
                  <th className="px-4 py-3 text-left">Token Address</th>
                  <th className="px-4 py-3 text-right">Liquidity</th>
                  <th className="px-4 py-3 text-right">Volume 24h</th>
                  <th className="px-4 py-3 text-right">Age</th>
                  <th className="px-4 py-3 text-center">Score</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {pairs.map((pair) => (
                  <tr key={pair.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <span className="font-mono text-white">{pair.base_token_symbol || "???"}</span>
                        <span className="text-zinc-500">/{pair.quote_token_symbol}</span>
                      </div>
                      <div className="text-xs text-zinc-600">{pair.base_token_name?.slice(0, 30)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-zinc-400">
                          {formatAddress(pair.base_token_address)}
                        </span>
                        {pair.base_token_address && (
                          <button 
                            onClick={() => copyToClipboard(pair.base_token_address)}
                            className="text-zinc-500 hover:text-white"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-zinc-300">
                      {formatUSD(pair.liquidity_usd)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm text-zinc-300">
                      {formatUSD(pair.volume_24h_usd)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="font-mono text-xs text-zinc-400">
                        {pair.age_hours?.toFixed(1) || "?"}h
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {pair.risk_score !== null ? (
                        <span className={`font-mono text-sm ${getRiskColor(pair.risk_level || "UNKNOWN")}`}>
                          {pair.risk_score?.toFixed(0)}/100
                        </span>
                      ) : (
                        <span className="text-xs text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {pair.is_honeypot === true ? (
                        <Badge className="bg-red-500/20 text-red-400 border-0 gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          HONEYPOT
                        </Badge>
                      ) : pair.is_honeypot === false ? (
                        <Badge className="bg-green-500/20 text-green-400 border-0 gap-1">
                          <CheckCircle className="w-3 h-3" />
                          SAFE
                        </Badge>
                      ) : (
                        <Badge className="bg-zinc-500/20 text-zinc-400 border-0">
                          UNKNOWN
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => scoreToken(pair.base_token_address)}
                          className="h-7 text-xs"
                          disabled={!pair.base_token_address}
                        >
                          <Shield className="w-3 h-3 mr-1" />
                          Score
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => setSelectedToken({ 
                            address: pair.base_token_address, 
                            symbol: pair.base_token_symbol 
                          })}
                          className="h-7 text-xs bg-green-600 hover:bg-green-700"
                          disabled={!pair.base_token_address}
                        >
                          <ArrowRight className="w-3 h-3 mr-1" />
                          Plan
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {pairs.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                      No pairs detected yet. Click &quot;Scan Pairs&quot; to fetch new pairs.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "swaps" && (
        <div className="space-y-4">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-zinc-800/50">
                <tr className="text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Token</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                  <th className="px-4 py-3 text-center">Risk</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-left">TX Hash</th>
                  <th className="px-4 py-3 text-left">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {swapPlans.map((plan) => (
                  <tr key={plan.id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-white">{plan.token_out_symbol || "???"}</span>
                        <span className="text-zinc-500">/WBNB</span>
                      </div>
                      <div className="font-mono text-xs text-zinc-600">
                        {formatAddress(plan.token_out)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="font-mono text-white">{plan.amount_in}</span>
                      <span className="text-zinc-500 ml-1">BNB</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`font-mono text-sm ${getRiskColor(plan.token_risk_level)}`}>
                        {plan.token_risk_score?.toFixed(0) || "?"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {getStatusBadge(plan.status)}
                    </td>
                    <td className="px-4 py-3">
                      {plan.tx_hash ? (
                        <a 
                          href={`https://bscscan.com/tx/${plan.tx_hash}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 font-mono text-xs text-blue-400 hover:text-blue-300"
                        >
                          {formatAddress(plan.tx_hash)}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        <span className="text-xs text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">
                      {new Date(plan.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {plan.status === "pending" && (
                          <>
                            <Button
                              size="sm"
                              onClick={() => approveSwap(plan.id)}
                              className="h-7 text-xs bg-green-600 hover:bg-green-700"
                            >
                              <CheckCircle className="w-3 h-3 mr-1" />
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => rejectSwap(plan.id)}
                              className="h-7 text-xs text-red-400 hover:text-red-300"
                            >
                              <XCircle className="w-3 h-3 mr-1" />
                              Reject
                            </Button>
                          </>
                        )}
                        {plan.status === "approved" && (
                          <>
                            <Button
                              size="sm"
                              onClick={() => simulateSwap(plan.id)}
                              className="h-7 text-xs bg-blue-600 hover:bg-blue-700"
                            >
                              <Eye className="w-3 h-3 mr-1" />
                              Simulate
                            </Button>
                            {walletConnected && !dexStatus?.pancakeswap?.paper_mode && (
                              <Button
                                size="sm"
                                onClick={() => sendViaMetaMask(plan)}
                                className="h-7 text-xs bg-[#F0B90B] hover:bg-[#F0B90B]/80 text-black"
                              >
                                <Send className="w-3 h-3 mr-1" />
                                Send TX
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {swapPlans.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                      No swap plans yet. Create one from the Pairs tab.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "positions" && (
        <div className="space-y-4">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-zinc-800/50">
                <tr className="text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Token</th>
                  <th className="px-4 py-3 text-right">Entry Price</th>
                  <th className="px-4 py-3 text-right">Current Price</th>
                  <th className="px-4 py-3 text-right">PnL</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-left">TX Hash</th>
                  <th className="px-4 py-3 text-left">Entry Time</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {positions.map((pos) => {
                  const pnl = pos.unrealized_pnl_pct || 0;
                  const isPositive = pnl >= 0;
                  return (
                    <tr key={pos.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="px-4 py-3">
                        <span className="font-mono text-white">{pos.token_symbol || "???"}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-zinc-300">
                        ${pos.entry_price_usd?.toFixed(8) || "0"}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-zinc-300">
                        ${pos.current_price_usd?.toFixed(8) || "0"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {isPositive ? (
                            <TrendingUp className="w-4 h-4 text-green-400" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-red-400" />
                          )}
                          <span className={`font-mono text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                            {isPositive ? '+' : ''}{pnl.toFixed(2)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getStatusBadge(pos.status)}
                      </td>
                      <td className="px-4 py-3">
                        {pos.entry_tx_hash ? (
                          <a 
                            href={`https://bscscan.com/tx/${pos.entry_tx_hash}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 font-mono text-xs text-blue-400 hover:text-blue-300"
                          >
                            {formatAddress(pos.entry_tx_hash)}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ) : (
                          <span className="text-xs text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-zinc-400">
                        {pos.entry_time ? new Date(pos.entry_time).toLocaleString() : "—"}
                      </td>
                      <td className="px-4 py-3">
                        {pos.status === "open" && walletConnected && (
                          <Button
                            size="sm"
                            onClick={() => sellPosition(pos.id)}
                            className="h-7 text-xs bg-red-600 hover:bg-red-700"
                          >
                            <ArrowRight className="w-3 h-3 mr-1 rotate-90" />
                            Sell
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {positions.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                      No positions yet. Simulate or execute a swap to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Advisor Tab */}
      {activeTab === "advisor" && (
        <SniperAdvisor 
          onApplyRecommendation={(result) => {
            fetchData();
          }} 
        />
      )}

      {/* Presets Tab */}
      {activeTab === "presets" && (
        <SniperPresetManager 
          onPresetApplied={(result) => {
            fetchData();
            toast.success(`Configurações do sniper atualizadas!`);
          }} 
        />
      )}

      {/* Sniper Config Card */}
      {dexStatus?.sniper?.config && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-rajdhani text-zinc-400 uppercase tracking-wider">
              Sniper Configuration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-5 gap-4 text-sm">
              <div>
                <p className="text-xs text-zinc-500">Min Liquidity</p>
                <p className="font-mono text-zinc-300">{formatUSD(dexStatus.sniper.config.min_liquidity_usd)}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Min Volume 24h</p>
                <p className="font-mono text-zinc-300">{formatUSD(dexStatus.sniper.config.min_volume_24h_usd)}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Max Age</p>
                <p className="font-mono text-zinc-300">{dexStatus.sniper.config.max_age_hours}h</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Min Score</p>
                <p className="font-mono text-zinc-300">{dexStatus.sniper.config.min_risk_score}/100</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Amount/Trade</p>
                <p className="font-mono text-zinc-300">{dexStatus.sniper.config.amount_per_trade_bnb} BNB</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
