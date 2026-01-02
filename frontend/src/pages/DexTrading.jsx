/**
 * DEX Trading Page - Multi-chain decentralized exchange trading.
 * Supports Ethereum, BSC, and Solana networks with manual and automated trading.
 */

import React, { useState, useEffect } from 'react';
import { Repeat, Target, Wallet, Activity, Globe, Shield, Zap } from 'lucide-react';
import { Web3Provider, useWeb3 } from '../context/Web3Context';
import WalletConnect from '../components/dex/WalletConnect';
import TokenSwap from '../components/dex/TokenSwap';
import SniperConfig from '../components/dex/SniperConfig';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

// Main content component (needs Web3 context)
const DexTradingContent = () => {
  const { wallet } = useWeb3();
  const [activeTab, setActiveTab] = useState('swap');
  const [chains, setChains] = useState([]);
  const [tradingMode, setTradingMode] = useState('semi-auto');

  // Fetch supported chains
  useEffect(() => {
    const fetchChains = async () => {
      try {
        const response = await axios.get(`${API_URL}/api/dex/chains`);
        setChains(response.data);
      } catch (err) {
        console.error('Failed to fetch chains:', err);
      }
    };
    fetchChains();
  }, []);

  const tabs = [
    { id: 'swap', label: 'Swap', icon: Repeat },
    { id: 'sniper', label: 'Sniper', icon: Target },
  ];

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <Globe className="w-7 h-7 text-yellow-500" />
              DEX Trading
            </h1>
            <p className="text-gray-400 mt-1">
              Multi-chain decentralized exchange trading
            </p>
          </div>
          
          {/* Mode Selector */}
          <div className="flex items-center gap-4">
            <div className="bg-gray-800 rounded-lg p-1 flex">
              <button
                onClick={() => setTradingMode('semi-auto')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                  tradingMode === 'semi-auto'
                    ? 'bg-yellow-500 text-black'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Wallet className="w-4 h-4" />
                Semi-Auto
              </button>
              <button
                onClick={() => setTradingMode('full-auto')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                  tradingMode === 'full-auto'
                    ? 'bg-purple-500 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Zap className="w-4 h-4" />
                Full-Auto
              </button>
            </div>
            
            <span className="bg-yellow-500/20 text-yellow-500 text-xs px-3 py-1 rounded-full">
              TESTNET MODE
            </span>
          </div>
        </div>

        {/* Mode Description */}
        <div className={`mb-6 p-4 rounded-lg border ${
          tradingMode === 'semi-auto' 
            ? 'bg-blue-500/10 border-blue-500/30' 
            : 'bg-purple-500/10 border-purple-500/30'
        }`}>
          <div className="flex items-start gap-3">
            {tradingMode === 'semi-auto' ? (
              <>
                <Wallet className="w-5 h-5 text-blue-400 mt-0.5" />
                <div>
                  <h3 className="text-blue-400 font-medium">Semi-Automatic Mode</h3>
                  <p className="text-gray-400 text-sm mt-1">
                    Connect your MetaMask wallet. You approve and sign each transaction manually.
                    Safer for larger trades and full control over your funds.
                  </p>
                </div>
              </>
            ) : (
              <>
                <Zap className="w-5 h-5 text-purple-400 mt-0.5" />
                <div>
                  <h3 className="text-purple-400 font-medium">Full-Automatic Mode</h3>
                  <p className="text-gray-400 text-sm mt-1">
                    Uses backend wallet (DEX_PRIVATE_KEY) for instant execution.
                    Required for sniping. Only use with small amounts on testnets.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6 border-b border-gray-700 pb-2">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                activeTab === tab.id
                  ? 'bg-gray-800 text-yellow-500 border-b-2 border-yellow-500'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Wallet */}
          <div className="lg:col-span-1 space-y-6">
            <WalletConnect />
            
            {/* Supported Chains */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                <Globe className="w-4 h-4 text-gray-400" />
                Supported Networks
              </h3>
              <div className="space-y-2">
                {chains.filter(c => c.is_testnet).map(chain => (
                  <div 
                    key={chain.chain_id}
                    className="flex items-center justify-between bg-gray-700/50 rounded p-2"
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        wallet.chain === chain.chain_id ? 'bg-green-500' : 'bg-gray-500'
                      }`} />
                      <span className="text-white text-sm">{chain.name}</span>
                    </div>
                    <div className="flex gap-1">
                      {chain.dex_available?.map(dex => (
                        <span 
                          key={dex}
                          className="text-xs bg-gray-600 text-gray-300 px-2 py-0.5 rounded"
                        >
                          {dex.replace('_', ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="mt-3 pt-3 border-t border-gray-700">
                <p className="text-gray-500 text-xs">
                  💡 Get testnet tokens from faucets to test trading
                </p>
              </div>
            </div>

            {/* Safety Notice */}
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-yellow-500 mt-0.5" />
                <div>
                  <h3 className="text-yellow-500 font-medium">Safety First</h3>
                  <ul className="text-gray-400 text-sm mt-2 space-y-1">
                    <li>• Always verify token contracts</li>
                    <li>• Use testnets for learning</li>
                    <li>• Never share private keys</li>
                    <li>• Set reasonable slippage limits</li>
                    <li>• Be aware of MEV/sandwich attacks</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - Trading */}
          <div className="lg:col-span-2">
            {activeTab === 'swap' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <TokenSwap mode={tradingMode} />
                
                {/* Quick Stats */}
                <div className="space-y-4">
                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-gray-400" />
                      Trading Stats
                    </h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-gray-700/50 rounded p-3">
                        <p className="text-gray-400 text-xs">Total Swaps</p>
                        <p className="text-white text-xl font-bold">0</p>
                      </div>
                      <div className="bg-gray-700/50 rounded p-3">
                        <p className="text-gray-400 text-xs">Volume (24h)</p>
                        <p className="text-white text-xl font-bold">$0.00</p>
                      </div>
                      <div className="bg-gray-700/50 rounded p-3">
                        <p className="text-gray-400 text-xs">Gas Saved</p>
                        <p className="text-white text-xl font-bold">0 ETH</p>
                      </div>
                      <div className="bg-gray-700/50 rounded p-3">
                        <p className="text-gray-400 text-xs">Best Rate %</p>
                        <p className="text-green-400 text-xl font-bold">+0.00%</p>
                      </div>
                    </div>
                  </div>

                  {/* Recent Transactions */}
                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <h3 className="text-white font-medium mb-3">Recent Transactions</h3>
                    <div className="text-center py-8 text-gray-500">
                      <Repeat className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p>No transactions yet</p>
                      <p className="text-sm">Execute a swap to see history</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'sniper' && (
              <SniperConfig />
            )}
          </div>
        </div>

        {/* Faucet Links */}
        <div className="mt-8 bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h3 className="text-white font-medium mb-3">🚰 Testnet Faucets</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <a
              href="https://sepoliafaucet.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-700/50 rounded p-3 hover:bg-gray-700 transition-colors"
            >
              <p className="text-white font-medium">Sepolia ETH</p>
              <p className="text-gray-400 text-sm">sepoliafaucet.com</p>
            </a>
            <a
              href="https://testnet.bnbchain.org/faucet-smart"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-700/50 rounded p-3 hover:bg-gray-700 transition-colors"
            >
              <p className="text-white font-medium">BSC Testnet BNB</p>
              <p className="text-gray-400 text-sm">bnbchain.org</p>
            </a>
            <a
              href="https://faucet.solana.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-700/50 rounded p-3 hover:bg-gray-700 transition-colors"
            >
              <p className="text-white font-medium">Solana Devnet</p>
              <p className="text-gray-400 text-sm">faucet.solana.com</p>
            </a>
            <a
              href="https://chainlist.org/?testnets=true"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-gray-700/50 rounded p-3 hover:bg-gray-700 transition-colors"
            >
              <p className="text-white font-medium">Add Networks</p>
              <p className="text-gray-400 text-sm">chainlist.org</p>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

// Main component with provider
const DexTrading = () => {
  return (
    <Web3Provider>
      <DexTradingContent />
    </Web3Provider>
  );
};

export default DexTrading;
