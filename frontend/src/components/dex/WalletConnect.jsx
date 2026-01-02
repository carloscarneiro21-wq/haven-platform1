/**
 * Wallet Connection Component for DEX Trading.
 * Supports MetaMask connection with chain switching.
 */

import React, { useMemo, useState } from 'react';
import { useWeb3 } from '../../context/Web3Context';
import { Wallet, ChevronDown, ExternalLink, Copy, Check, AlertCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';


const WalletConnect = ({ onConnect }) => {
  const {
    wallet,
    walletChooser,
    chooseWalletProvider,
    cancelWalletChooser,
    isWalletAvailable,
    isMetaMaskAvailable,
    formatAddress,
    connectWallet,
    disconnectWallet,
    switchChain,
    CHAIN_CONFIGS,
  } = useWeb3();

  const [showDropdown, setShowDropdown] = useState(false);
  const [copied, setCopied] = useState(false);
  const [selectedChain, setSelectedChain] = useState('ethereum_sepolia');

  const isEmbedded = useMemo(() => {
    try {
      return typeof window !== 'undefined' && window.top !== window.self;
    } catch {
      // If cross-origin frame access is blocked, assume embedded
      return true;
    }
  }, []);

  const framesDisallowed = useMemo(() => {
    const msg = (wallet.error || '').toLowerCase();
    return msg.includes('frames-disallowed') || msg.includes('frame') && msg.includes('disallow');
  }, [wallet.error]);

  const openInNewTab = () => {
    if (typeof window === 'undefined') return;
    window.open(window.location.href, '_blank', 'noopener,noreferrer');
  };

  const handleConnect = async () => {
    const success = await connectWallet(selectedChain);
    if (success && onConnect) {
      onConnect(wallet);
    }
  };

  const handleCopyAddress = () => {
    if (wallet.address) {
      navigator.clipboard.writeText(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSwitchChain = async (chain) => {
    await switchChain(chain);
    setSelectedChain(chain);
    setShowDropdown(false);
  };

  // Chain options (testnets first for safety)
  const chainOptions = [
    { id: 'ethereum_sepolia', name: 'Sepolia Testnet', symbol: 'ETH', testnet: true },
    { id: 'bsc_testnet', name: 'BSC Testnet', symbol: 'tBNB', testnet: true },
    { id: 'ethereum', name: 'Ethereum', symbol: 'ETH', testnet: false },
    { id: 'bsc', name: 'BSC', symbol: 'BNB', testnet: false },
  ];

  // Not connected state
  if (!wallet.isConnected) {
    return (
      <>
        <Dialog open={!!walletChooser?.isOpen} onOpenChange={(open) => { if (!open) cancelWalletChooser(); }}>
          <DialogContent className="bg-gray-900 border border-gray-700 text-white">
            <DialogHeader>
              <DialogTitle>Choose wallet</DialogTitle>
              <DialogDescription>
                Multiple wallet providers were detected. Select which wallet you want to use for this connection.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2">
              {(walletChooser?.providers || []).map((p, idx) => (
                <Button
                  key={`${p.label}-${idx}`}
                  variant="outline"
                  className="w-full justify-between bg-gray-800 border-gray-700 text-white hover:bg-gray-700"
                  onClick={() => chooseWalletProvider(p.provider)}
                >
                  <span>{p.label}</span>
                  <span className="text-xs text-gray-400">Select</span>
                </Button>
              ))}

              <Button
                variant="ghost"
                className="w-full text-gray-300 hover:bg-gray-800"
                onClick={cancelWalletChooser}
              >
                Cancel
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div className="flex items-center gap-2 mb-4">
          <Wallet className="w-5 h-5 text-yellow-500" />
          <h3 className="text-white font-medium">Connect Wallet</h3>
        </div>

        {!isMetaMaskAvailable && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
            <div className="flex items-center gap-2 text-red-400">
              <AlertCircle className="w-4 h-4" />
              <span className="text-sm">MetaMask not detected</span>
            </div>
            <a
              href="https://metamask.io/download/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:underline mt-1 inline-block"
            >
              Install MetaMask →
            </a>
          </div>
        )}

        {(isEmbedded || framesDisallowed) && (
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 mb-4">
            <div className="flex items-start gap-2 text-yellow-400">
              <AlertCircle className="w-4 h-4 mt-0.5" />
              <div>
                <div className="text-sm font-medium">Wallet blocked in embedded view</div>
                <div className="text-xs text-gray-400 mt-1">
                  Your wallet returned <span className="font-mono">dapp.frames-disallowed</span>. Open HAVEN in a new tab (not inside an embedded frame) to connect.
                </div>
                <button
                  type="button"
                  onClick={openInNewTab}
                  className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 rounded bg-yellow-500 text-black text-xs font-medium hover:bg-yellow-600 transition-colors"
                >
                  Open in new tab
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Chain selector - always visible */}
        <div className="mb-4">
          <label className="text-gray-400 text-xs mb-1 block">Select Network</label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowDropdown((v) => !v)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-left text-white flex items-center justify-between hover:border-gray-500 transition-colors relative z-20"
              data-testid="dex-network-selector"
            >
              <span>{chainOptions.find(c => c.id === selectedChain)?.name}</span>
              <ChevronDown className={`w-4 h-4 transition-transform ${showDropdown ? 'rotate-180' : ''}`} />
            </button>

            {showDropdown && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg overflow-hidden z-50 pointer-events-auto">
                {chainOptions.map(chain => (
                  <button
                    key={chain.id}
                    onClick={() => handleSwitchChain(chain.id)}
                    className={`w-full px-3 py-2 text-left hover:bg-gray-600 flex items-center justify-between ${
                      selectedChain === chain.id ? 'bg-gray-600' : ''
                    }`}
                  >
                    <span className="text-white">{chain.name}</span>
                    {chain.testnet && (
                      <span className="text-xs bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded">
                        Testnet
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Connect button */}
        <button
          type="button"
          onClick={handleConnect}
          disabled={wallet.isConnecting}
          className="w-full bg-yellow-500 hover:bg-yellow-600 disabled:bg-gray-600 disabled:text-gray-400 text-black font-medium py-2 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
          data-testid="dex-connect-wallet"
        >
          {wallet.isConnecting ? (
            <>
              <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
              Connecting...
            </>
          ) : !isWalletAvailable ? (
            'Wallet Required'
          ) : (
            <>
              <Wallet className="w-4 h-4" />
              Connect Wallet
            </>
          )}
        </button>

        {wallet.error && (
          <div className="mt-3 text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded p-2">
            {wallet.error}
          </div>
        )}
      </div>
      </>
    );
  }
  // Connected state
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          <span className="text-green-400 text-sm font-medium">Connected</span>
        </div>
        <button
          onClick={disconnectWallet}
          className="text-gray-400 hover:text-red-400 text-xs transition-colors"
        >
          Disconnect
        </button>
      </div>

      {/* Wallet provider */}
      {wallet.providerName && (
        <div className="bg-gray-700/50 rounded-lg p-3 mb-3">
          <p className="text-gray-400 text-xs mb-1">Wallet</p>
          <p className="text-white font-medium">{wallet.providerName}</p>
        </div>
      )}

      {/* Address */}
      <div className="bg-gray-700/50 rounded-lg p-3 mb-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-gray-400 text-xs mb-1">Address</p>
            <p className="text-white font-mono">{formatAddress(wallet.address)}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCopyAddress}
              className="p-1.5 bg-gray-600 rounded hover:bg-gray-500 transition-colors"
              title="Copy address"
            >
              {copied ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4 text-gray-300" />
              )}
            </button>
            <a
              href={`${CHAIN_CONFIGS[wallet.chain]?.blockExplorerUrls?.[0]}/address/${wallet.address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 bg-gray-600 rounded hover:bg-gray-500 transition-colors"
              title="View on explorer"
            >
              <ExternalLink className="w-4 h-4 text-gray-300" />
            </a>
          </div>
        </div>
      </div>

      {/* Balance and Chain */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-700/50 rounded-lg p-3">
          <p className="text-gray-400 text-xs mb-1">Balance</p>
          <p className="text-white font-medium">
            {wallet.balance} {chainOptions.find(c => c.id === wallet.chain)?.symbol || 'ETH'}
          </p>
        </div>
        <div className="bg-gray-700/50 rounded-lg p-3">
          <p className="text-gray-400 text-xs mb-1">Network</p>
          <div className="flex items-center gap-2">
            <p className="text-white font-medium truncate">
              {chainOptions.find(c => c.id === wallet.chain)?.name || 'Unknown'}
            </p>
            {chainOptions.find(c => c.id === wallet.chain)?.testnet && (
              <span className="text-xs bg-yellow-500/20 text-yellow-500 px-1.5 py-0.5 rounded">
                Test
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Chain switcher */}
      <div className="mt-3 pt-3 border-t border-gray-700">
        <p className="text-gray-400 text-xs mb-2">Switch Network</p>
        <div className="flex flex-wrap gap-2">
          {chainOptions.filter(c => c.testnet).map(chain => (
            <button
              key={chain.id}
              onClick={() => handleSwitchChain(chain.id)}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                wallet.chain === chain.id
                  ? 'bg-yellow-500 text-black'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {chain.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default WalletConnect;
