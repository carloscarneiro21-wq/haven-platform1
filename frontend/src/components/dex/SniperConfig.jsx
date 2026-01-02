/**
 * Token Sniper Configuration Component.
 * Configure automated sniping on new liquidity pools.
 */

import React, { useState, useEffect } from 'react';
import { Target, Play, Square, AlertTriangle, Settings, Shield, TrendingUp, Activity } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

const SniperConfig = () => {
  const [config, setConfig] = useState({
    enabled: false,
    chain: 'ethereum_sepolia',
    buy_amount_eth: 0.01,
    max_slippage_pct: 10.0,
    min_liquidity_usd: 1000,
    max_buy_tax_pct: 10.0,
    max_sell_tax_pct: 10.0,
    auto_sell_enabled: false,
    auto_sell_profit_pct: 100,
    auto_sell_loss_pct: 50,
    blacklisted_tokens: [],
  });

  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [detectedPools, setDetectedPools] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [walletStatus, setWalletStatus] = useState(null);
  const [error, setError] = useState(null);

  // Fetch initial config and status
  useEffect(() => {
    fetchConfig();
    fetchWalletStatus();
    fetchDetectedPools();
    fetchExecutions();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/dex/sniper/config`);
      setConfig(response.data);
      setIsRunning(response.data.enabled);
    } catch (err) {
      // Config might not exist yet
      console.log('No existing config');
    }
  };

  const fetchWalletStatus = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/dex/wallet/status`);
      setWalletStatus(response.data);
    } catch (err) {
      console.error('Failed to fetch wallet status');
    }
  };

  const fetchDetectedPools = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/dex/sniper/detected-pools?limit=10`);
      setDetectedPools(response.data.pools || []);
    } catch (err) {
      console.error('Failed to fetch pools');
    }
  };

  const fetchExecutions = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/dex/sniper/executions?limit=10`);
      setExecutions(response.data.executions || []);
    } catch (err) {
      console.error('Failed to fetch executions');
    }
  };

  const handleSaveConfig = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await axios.post(`${API_URL}/api/dex/sniper/config`, config);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save config');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartSniper = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await axios.post(`${API_URL}/api/dex/sniper/start`, null, {
        params: { chains: [config.chain] }
      });
      setIsRunning(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start sniper');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopSniper = async () => {
    setIsLoading(true);
    try {
      await axios.post(`${API_URL}/api/dex/sniper/stop`);
      setIsRunning(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to stop sniper');
    } finally {
      setIsLoading(false);
    }
  };

  const updateConfig = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Target className="w-6 h-6 text-yellow-500" />
          <h2 className="text-xl font-bold text-white">Token Sniper</h2>
          {isRunning && (
            <span className="flex items-center gap-1 bg-green-500/20 text-green-400 text-xs px-2 py-1 rounded">
              <Activity className="w-3 h-3 animate-pulse" />
              Monitoring
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {!isRunning ? (
            <button
              onClick={handleStartSniper}
              disabled={isLoading || !walletStatus?.configured}
              className="flex items-center gap-2 bg-green-500 hover:bg-green-600 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
            >
              <Play className="w-4 h-4" />
              Start Sniper
            </button>
          ) : (
            <button
              onClick={handleStopSniper}
              disabled={isLoading}
              className="flex items-center gap-2 bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg transition-colors"
            >
              <Square className="w-4 h-4" />
              Stop Sniper
            </button>
          )}
        </div>
      </div>

      {/* Wallet Warning */}
      {!walletStatus?.configured && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5" />
            <div>
              <h4 className="text-yellow-500 font-medium">Backend Wallet Required</h4>
              <p className="text-gray-400 text-sm mt-1">
                Token sniping requires a backend wallet with DEX_PRIVATE_KEY configured.
                This wallet will automatically execute trades when new pools are detected.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Backend Wallet Status */}
      {walletStatus?.configured && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-5 h-5 text-green-500" />
            <h3 className="text-white font-medium">Backend Wallet</h3>
            <span className="text-xs bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded ml-auto">
              {walletStatus.mode?.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-gray-400 text-xs">Address</p>
              <p className="text-white font-mono text-sm">
                {walletStatus.address?.slice(0, 10)}...{walletStatus.address?.slice(-8)}
              </p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Balances</p>
              <div className="text-white text-sm">
                {Object.entries(walletStatus.balances || {}).map(([chain, balance]) => (
                  <span key={chain} className="mr-3">
                    {balance.toFixed(4)} {chain.includes('bsc') ? 'BNB' : 'ETH'}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Configuration */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="flex items-center gap-2 p-4 border-b border-gray-700">
          <Settings className="w-5 h-5 text-gray-400" />
          <h3 className="text-white font-medium">Snipe Configuration</h3>
        </div>

        <div className="p-4 grid grid-cols-2 gap-4">
          {/* Chain */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Target Chain</label>
            <select
              value={config.chain}
              onChange={e => updateConfig('chain', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            >
              <option value="ethereum_sepolia">Ethereum Sepolia (Testnet)</option>
              <option value="bsc_testnet">BSC Testnet</option>
              <option value="ethereum">Ethereum Mainnet</option>
              <option value="bsc">BSC Mainnet</option>
            </select>
          </div>

          {/* Buy Amount */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Buy Amount (ETH/BNB)</label>
            <input
              type="number"
              value={config.buy_amount_eth}
              onChange={e => updateConfig('buy_amount_eth', parseFloat(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="0.001"
              min="0.001"
            />
          </div>

          {/* Max Slippage */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Max Slippage %</label>
            <input
              type="number"
              value={config.max_slippage_pct}
              onChange={e => updateConfig('max_slippage_pct', parseFloat(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="0.5"
              min="0.5"
              max="50"
            />
          </div>

          {/* Min Liquidity */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Min Liquidity (USD)</label>
            <input
              type="number"
              value={config.min_liquidity_usd}
              onChange={e => updateConfig('min_liquidity_usd', parseFloat(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="100"
              min="0"
            />
          </div>

          {/* Max Buy Tax */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Max Buy Tax %</label>
            <input
              type="number"
              value={config.max_buy_tax_pct}
              onChange={e => updateConfig('max_buy_tax_pct', parseFloat(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="1"
              min="0"
              max="100"
            />
          </div>

          {/* Max Sell Tax */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Max Sell Tax %</label>
            <input
              type="number"
              value={config.max_sell_tax_pct}
              onChange={e => updateConfig('max_sell_tax_pct', parseFloat(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="1"
              min="0"
              max="100"
            />
          </div>
        </div>

        {/* Auto-Sell Section */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <input
              type="checkbox"
              checked={config.auto_sell_enabled}
              onChange={e => updateConfig('auto_sell_enabled', e.target.checked)}
              className="w-4 h-4 rounded bg-gray-700 border-gray-600"
            />
            <TrendingUp className="w-4 h-4 text-green-500" />
            <span className="text-white">Enable Auto-Sell</span>
          </div>

          {config.auto_sell_enabled && (
            <div className="grid grid-cols-2 gap-4 ml-6">
              <div>
                <label className="text-gray-400 text-sm block mb-1">Take Profit %</label>
                <input
                  type="number"
                  value={config.auto_sell_profit_pct}
                  onChange={e => updateConfig('auto_sell_profit_pct', parseFloat(e.target.value))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  step="10"
                  min="10"
                />
              </div>
              <div>
                <label className="text-gray-400 text-sm block mb-1">Stop Loss %</label>
                <input
                  type="number"
                  value={config.auto_sell_loss_pct}
                  onChange={e => updateConfig('auto_sell_loss_pct', parseFloat(e.target.value))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  step="5"
                  min="5"
                  max="100"
                />
              </div>
            </div>
          )}
        </div>

        {/* Save Button */}
        <div className="p-4 border-t border-gray-700">
          <button
            onClick={handleSaveConfig}
            disabled={isLoading}
            className="w-full bg-yellow-500 hover:bg-yellow-600 text-black font-medium py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Detected Pools */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="p-4 border-b border-gray-700">
          <h3 className="text-white font-medium">Recently Detected Pools</h3>
        </div>
        <div className="p-4">
          {detectedPools.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No pools detected yet</p>
          ) : (
            <div className="space-y-2">
              {detectedPools.map((pool, idx) => (
                <div key={idx} className="bg-gray-700/50 rounded p-3 flex justify-between items-center">
                  <div>
                    <p className="text-white text-sm font-mono">
                      {pool.pool_address?.slice(0, 16)}...
                    </p>
                    <p className="text-gray-400 text-xs">{pool.chain}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded ${
                    pool.status === 'success' ? 'bg-green-500/20 text-green-400' :
                    pool.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                    'bg-yellow-500/20 text-yellow-400'
                  }`}>
                    {pool.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Snipe Executions */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="p-4 border-b border-gray-700">
          <h3 className="text-white font-medium">Snipe Executions</h3>
        </div>
        <div className="p-4">
          {executions.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No executions yet</p>
          ) : (
            <div className="space-y-2">
              {executions.map((exec, idx) => (
                <div key={idx} className="bg-gray-700/50 rounded p-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-white text-sm">Token: {exec.token_address?.slice(0, 16)}...</p>
                      <p className="text-gray-400 text-xs">
                        Amount: {exec.buy_amount} | {exec.executed_at}
                      </p>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded ${
                      exec.status === 'success' ? 'bg-green-500/20 text-green-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {exec.status}
                    </span>
                  </div>
                  {exec.tx_hash && (
                    <a
                      href={`https://sepolia.etherscan.io/tx/${exec.tx_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 text-xs hover:underline mt-1 inline-block"
                    >
                      View Transaction →
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SniperConfig;
