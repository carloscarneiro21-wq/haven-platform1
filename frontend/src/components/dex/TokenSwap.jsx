/**
 * Token Swap Component for DEX Trading.
 * Supports swapping tokens on multiple chains.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useWeb3 } from '../../context/Web3Context';
import { ArrowDownUp, Settings, Loader2, AlertTriangle, CheckCircle, ExternalLink } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

// Common tokens per chain
const CHAIN_TOKENS = {
  ethereum_sepolia: [
    { symbol: 'ETH', name: 'Ethereum', address: '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14', decimals: 18, isNative: true },
    { symbol: 'WETH', name: 'Wrapped ETH', address: '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14', decimals: 18 },
  ],
  bsc_testnet: [
    { symbol: 'BNB', name: 'BNB', address: '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd', decimals: 18, isNative: true },
    { symbol: 'WBNB', name: 'Wrapped BNB', address: '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd', decimals: 18 },
  ],
  solana_devnet: [
    { symbol: 'SOL', name: 'Solana', address: 'So11111111111111111111111111111111111111112', decimals: 9, isNative: true },
    { symbol: 'USDC', name: 'USD Coin', address: 'Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr', decimals: 6 },
  ],
};

const TokenSwap = ({ mode = 'semi-auto' }) => {
  const { wallet, sendTransaction } = useWeb3();
  
  const [tokenIn, setTokenIn] = useState(null);
  const [tokenOut, setTokenOut] = useState(null);
  const [amountIn, setAmountIn] = useState('');
  const [amountOut, setAmountOut] = useState('');
  const [slippage, setSlippage] = useState(0.5);
  const [showSettings, setShowSettings] = useState(false);
  
  const [quote, setQuote] = useState(null);
  const [isLoadingQuote, setIsLoadingQuote] = useState(false);
  const [isSwapping, setIsSwapping] = useState(false);
  const [swapResult, setSwapResult] = useState(null);
  const [error, setError] = useState(null);

  // Get tokens for current chain
  const tokens = CHAIN_TOKENS[wallet.chain] || CHAIN_TOKENS.ethereum_sepolia;

  // Set default tokens when chain changes
  useEffect(() => {
    if (tokens.length >= 2) {
      setTokenIn(tokens[0]);
      setTokenOut(tokens[1] || tokens[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallet.chain]);

  // Fetch quote when amount changes
  const fetchQuote = useCallback(async () => {
    if (!amountIn || parseFloat(amountIn) <= 0 || !tokenIn || !tokenOut) {
      setQuote(null);
      setAmountOut('');
      return;
    }

    setIsLoadingQuote(true);
    setError(null);

    try {
      const response = await axios.post(`${API_URL}/api/dex/swap/quote`, {
        chain: wallet.chain || 'ethereum_sepolia',
        token_in: tokenIn.address,
        token_out: tokenOut.address,
        amount_in: amountIn,
        slippage_pct: slippage,
      });

      if (response.data.success) {
        setQuote(response.data);
        setAmountOut(response.data.amount_out);
      } else {
        setError(response.data.error || 'Failed to get quote');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch quote');
    } finally {
      setIsLoadingQuote(false);
    }
  }, [amountIn, tokenIn, tokenOut, wallet.chain, slippage]);

  // Debounce quote fetching
  useEffect(() => {
    const timer = setTimeout(fetchQuote, 500);
    return () => clearTimeout(timer);
  }, [fetchQuote]);

  // Switch tokens
  const handleSwitchTokens = () => {
    setTokenIn(tokenOut);
    setTokenOut(tokenIn);
    setAmountIn(amountOut);
    setAmountOut(amountIn);
  };

  // Execute swap
  const handleSwap = async () => {
    if (!wallet.isConnected) {
      setError('Please connect your wallet first');
      return;
    }

    if (!quote) {
      setError('Please wait for quote');
      return;
    }

    setIsSwapping(true);
    setError(null);
    setSwapResult(null);

    try {
      if (mode === 'semi-auto') {
        // Get unsigned transaction from backend
        const txResponse = await axios.post(`${API_URL}/api/dex/swap/build-transaction`, {
          chain: wallet.chain,
          token_in: tokenIn.address,
          token_out: tokenOut.address,
          amount_in: amountIn,
          min_amount_out: (parseFloat(amountOut) * (1 - slippage / 100)).toString(),
          recipient: wallet.address,
          slippage_pct: slippage,
        });

        if (!txResponse.data.success) {
          throw new Error(txResponse.data.error || 'Failed to build transaction');
        }

        // Sign and send with MetaMask
        const txHash = await sendTransaction(txResponse.data.transaction);
        
        setSwapResult({
          success: true,
          tx_hash: txHash,
          message: 'Transaction submitted!',
        });
      } else {
        // Full auto mode - backend executes
        const response = await axios.post(`${API_URL}/api/dex/swap/execute`, {
          chain: wallet.chain,
          token_in: tokenIn.address,
          token_out: tokenOut.address,
          amount_in: amountIn,
          min_amount_out: (parseFloat(amountOut) * (1 - slippage / 100)).toString(),
          recipient: wallet.address,
          slippage_pct: slippage,
        });

        setSwapResult(response.data);
      }

      // Clear form on success
      setAmountIn('');
      setAmountOut('');
      setQuote(null);

    } catch (err) {
      setError(err.message || 'Swap failed');
    } finally {
      setIsSwapping(false);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <h3 className="text-white font-medium">Swap Tokens</h3>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
        >
          <Settings className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="p-4 border-b border-gray-700 bg-gray-700/30">
          <label className="text-gray-400 text-sm">Slippage Tolerance</label>
          <div className="flex gap-2 mt-2">
            {[0.1, 0.5, 1.0, 3.0].map(val => (
              <button
                key={val}
                onClick={() => setSlippage(val)}
                className={`px-3 py-1 rounded text-sm ${
                  slippage === val
                    ? 'bg-yellow-500 text-black'
                    : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                }`}
              >
                {val}%
              </button>
            ))}
            <input
              type="number"
              value={slippage}
              onChange={e => setSlippage(parseFloat(e.target.value) || 0.5)}
              className="w-20 bg-gray-600 border border-gray-500 rounded px-2 py-1 text-white text-sm"
              step="0.1"
              min="0.1"
              max="50"
            />
          </div>
        </div>
      )}

      <div className="p-4 space-y-3">
        {/* Token In */}
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex justify-between mb-2">
            <span className="text-gray-400 text-sm">From</span>
            <span className="text-gray-400 text-sm">
              Balance: {wallet.balance || '0'} {tokenIn?.symbol}
            </span>
          </div>
          <div className="flex gap-3">
            <input
              type="number"
              value={amountIn}
              onChange={e => setAmountIn(e.target.value)}
              placeholder="0.0"
              className="flex-1 bg-transparent text-white text-2xl outline-none"
            />
            <select
              value={tokenIn?.symbol || ''}
              onChange={e => setTokenIn(tokens.find(t => t.symbol === e.target.value))}
              className="bg-gray-600 border border-gray-500 rounded-lg px-3 py-2 text-white"
            >
              {tokens.map(token => (
                <option key={token.symbol} value={token.symbol}>
                  {token.symbol}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Switch button */}
        <div className="flex justify-center">
          <button
            onClick={handleSwitchTokens}
            className="p-2 bg-gray-700 hover:bg-gray-600 rounded-full transition-colors"
          >
            <ArrowDownUp className="w-5 h-5 text-gray-300" />
          </button>
        </div>

        {/* Token Out */}
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex justify-between mb-2">
            <span className="text-gray-400 text-sm">To</span>
          </div>
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <input
                type="text"
                value={amountOut}
                readOnly
                placeholder="0.0"
                className="w-full bg-transparent text-white text-2xl outline-none"
              />
              {isLoadingQuote && (
                <Loader2 className="absolute right-0 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 animate-spin" />
              )}
            </div>
            <select
              value={tokenOut?.symbol || ''}
              onChange={e => setTokenOut(tokens.find(t => t.symbol === e.target.value))}
              className="bg-gray-600 border border-gray-500 rounded-lg px-3 py-2 text-white"
            >
              {tokens.map(token => (
                <option key={token.symbol} value={token.symbol}>
                  {token.symbol}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Quote details */}
        {quote && (
          <div className="bg-gray-700/30 rounded-lg p-3 space-y-1">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Price Impact</span>
              <span className={`${
                quote.price_impact > 3 ? 'text-red-400' : 
                quote.price_impact > 1 ? 'text-yellow-400' : 'text-green-400'
              }`}>
                {quote.price_impact?.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Min. Received</span>
              <span className="text-white">
                {(parseFloat(amountOut) * (1 - slippage / 100)).toFixed(6)} {tokenOut?.symbol}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Gas Estimate</span>
              <span className="text-white">{quote.gas_estimate?.toLocaleString()} units</span>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}

        {/* Success */}
        {swapResult?.success && (
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-400 font-medium">Swap Successful!</span>
            </div>
            {swapResult.tx_hash && (
              <a
                href={`https://sepolia.etherscan.io/tx/${swapResult.tx_hash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 text-sm hover:underline flex items-center gap-1"
              >
                View transaction <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        )}

        {/* Swap button */}
        <button
          onClick={handleSwap}
          disabled={!wallet.isConnected || !quote || isSwapping || !amountIn}
          className="w-full bg-yellow-500 hover:bg-yellow-600 disabled:bg-gray-600 disabled:text-gray-400 text-black font-medium py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {isSwapping ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              {mode === 'semi-auto' ? 'Confirm in Wallet...' : 'Swapping...'}
            </>
          ) : !wallet.isConnected ? (
            'Connect Wallet First'
          ) : !amountIn ? (
            'Enter Amount'
          ) : !quote ? (
            'Loading Quote...'
          ) : (
            `Swap ${tokenIn?.symbol} → ${tokenOut?.symbol}`
          )}
        </button>

        {/* Mode indicator */}
        <div className="text-center">
          <span className={`text-xs px-2 py-1 rounded ${
            mode === 'semi-auto' 
              ? 'bg-blue-500/20 text-blue-400' 
              : 'bg-purple-500/20 text-purple-400'
          }`}>
            {mode === 'semi-auto' ? 'Semi-Auto: You sign transactions' : 'Full-Auto: Bot executes'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default TokenSwap;
