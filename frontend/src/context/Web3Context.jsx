/**
 * Web3 Context for wallet connection and blockchain state management.
 * Supports MetaMask and WalletConnect for EVM chains.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

// Chain configurations
const CHAIN_CONFIGS = {
  ethereum_sepolia: {
    chainId: '0xaa36a7', // 11155111
    chainName: 'Sepolia Testnet',
    nativeCurrency: { name: 'SepoliaETH', symbol: 'ETH', decimals: 18 },
    rpcUrls: ['https://rpc.sepolia.org'],
    blockExplorerUrls: ['https://sepolia.etherscan.io'],
  },
  bsc_testnet: {
    chainId: '0x61', // 97
    chainName: 'BSC Testnet',
    nativeCurrency: { name: 'tBNB', symbol: 'tBNB', decimals: 18 },
    rpcUrls: ['https://data-seed-prebsc-1-s1.binance.org:8545'],
    blockExplorerUrls: ['https://testnet.bscscan.com'],
  },
  ethereum: {
    chainId: '0x1', // 1
    chainName: 'Ethereum Mainnet',
    nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
    rpcUrls: ['https://eth.llamarpc.com'],
    blockExplorerUrls: ['https://etherscan.io'],
  },
  bsc: {
    chainId: '0x38', // 56
    chainName: 'BNB Smart Chain',
    nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
    rpcUrls: ['https://bsc-dataseed1.binance.org'],
    blockExplorerUrls: ['https://bscscan.com'],
  },
};

const Web3Context = createContext(null);

export const useWeb3 = () => {
  const context = useContext(Web3Context);
  if (!context) {
    throw new Error('useWeb3 must be used within a Web3Provider');
  }
  return context;
};

export const Web3Provider = ({ children }) => {
  const [wallet, setWallet] = useState({
    address: null,
    chain: null,
    chainId: null,
    balance: '0',
    isConnected: false,
    isConnecting: false,
    error: null,
    providerName: null,
  });

  const [walletChooser, setWalletChooser] = useState({
    isOpen: false,
    targetChain: 'ethereum_sepolia',
    providers: [],
  });

  const activeProviderRef = useRef(null);

  // Provider identity helpers
  const getProviderName = useCallback((provider) => {
    if (!provider) return 'Wallet';
    if (provider.isMetaMask) return 'MetaMask';
    if (provider.isTrust || provider.isTrustWallet) return 'Trust Wallet';
    return 'Wallet';
  }, []);



  const getCandidateProviders = useCallback(() => {
    if (typeof window === 'undefined') return [];
    const eth = window.ethereum;
    if (!eth) return [];

    const raw = (Array.isArray(eth.providers) && eth.providers.length > 0)
      ? eth.providers
      : [eth];

    // Dedupe by reference (providers arrays can contain duplicates)
    const seen = new Set();
    const unique = [];
    for (const p of raw) {
      if (!p) continue;
      if (seen.has(p)) continue;
      seen.add(p);
      unique.push(p);
    }

    return unique;
  }, []);

  // Get injected EIP-1193 provider (MetaMask, Trust Wallet, etc.)
  // NOTE: When multiple providers exist we DO NOT auto-pick (per user requirement).
  // We will prompt the user to choose.
  const getInjectedProvider = useCallback(() => {
    if (activeProviderRef.current) return activeProviderRef.current;

    const providers = getCandidateProviders();
    if (providers.length === 0) return null;
    if (providers.length === 1) return providers[0];

    // Multiple providers: wait for user selection
    return null;
  }, [getCandidateProviders]);

  const injectedProvider = getInjectedProvider();
  const isWalletAvailable = getCandidateProviders().length > 0;
  const isMetaMaskAvailable = !!injectedProvider?.isMetaMask;

  // Format address for display
  const formatAddress = (address) => {
    if (!address) return '';
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  // Get balance
  const fetchBalance = useCallback(async (address) => {
    const provider = getInjectedProvider();
    if (!provider || !address) return '0';
    try {
      const balance = await provider.request({
        method: 'eth_getBalance',
        params: [address, 'latest'],
      });
      // Convert from hex wei to ETH
      const balanceInEth = parseInt(balance, 16) / 1e18;
      return balanceInEth.toFixed(4);
    } catch (error) {
      console.error('Failed to fetch balance:', error);
      return '0';
    }
  }, [getInjectedProvider]);

  const connectWithProvider = useCallback(async (provider, targetChain = 'ethereum_sepolia') => {
    if (!provider) return false;

    setWalletChooser({ isOpen: false, targetChain, providers: [] });
    activeProviderRef.current = provider;
    setWallet(prev => ({
      ...prev,
      isConnecting: true,
      error: null,
      providerName: getProviderName(provider),
    }));

    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' });
      if (!accounts || accounts.length === 0) throw new Error('No accounts found');

      const address = accounts[0];
      const chainId = await provider.request({ method: 'eth_chainId' });
      const balance = await fetchBalance(address);

      let chain = null;
      for (const [key, config] of Object.entries(CHAIN_CONFIGS)) {
        if (config.chainId.toLowerCase() === String(chainId).toLowerCase()) {
          chain = key;
          break;
        }
      }

      setWallet({
        address,
        chain,
        chainId,
        balance,
        isConnected: true,
        isConnecting: false,
        error: null,
        providerName: getProviderName(provider),
      });

      if (targetChain && chain !== targetChain) {
        const config = CHAIN_CONFIGS[targetChain];
        if (config) {
          try {
            await provider.request({
              method: 'wallet_switchEthereumChain',
              params: [{ chainId: config.chainId }],
            });
          } catch (switchError) {
            if (switchError.code === 4902) {
              try {
                await provider.request({
                  method: 'wallet_addEthereumChain',
                  params: [config],
                });
              } catch (addError) {
                console.error('Failed to add chain:', addError);
              }
            } else {
              console.error('Failed to switch chain:', switchError);
            }
          }

          try {
            const newChainId = await provider.request({ method: 'eth_chainId' });
            let newChain = null;
            for (const [key, cfg] of Object.entries(CHAIN_CONFIGS)) {
              if (cfg.chainId.toLowerCase() === String(newChainId).toLowerCase()) {
                newChain = key;
                break;
              }
            }
            setWallet(prev => ({
              ...prev,
              chainId: newChainId,
              chain: newChain,
            }));
          } catch (_) {
            // ignore
          }
        }
      }

      return true;
    } catch (error) {
      console.error('Wallet connection failed:', error);
      const rawMessage = error?.message || '';
      const messageLower = rawMessage.toLowerCase();

      const friendlyMessage = messageLower.includes('frames-disallowed')
        ? 'Wallet blocked in embedded frame (dapp.frames-disallowed). Open this app in a new tab and try again.'
        : (rawMessage || 'Failed to connect wallet');

      setWallet(prev => ({
        ...prev,
        isConnecting: false,
        error: friendlyMessage,
      }));
      return false;
    }
  }, [fetchBalance, getProviderName]);

  // Connect wallet
  const connectWallet = useCallback(async (targetChain = 'ethereum_sepolia') => {
    const providers = getCandidateProviders();

    if (providers.length === 0) {
      setWallet(prev => ({
        ...prev,
        error: 'No EVM wallet detected. Please install MetaMask or Trust Wallet extension.',
      }));
      return false;
    }

    if (providers.length > 1) {
      // Group options by detected name. If we can't detect, show Injected Wallet #n.
      const named = providers.map((p) => ({
        provider: p,
        name: getProviderName(p),
      }));

      const groups = new Map();
      for (const item of named) {
        const arr = groups.get(item.name) || [];
        arr.push(item);
        groups.set(item.name, arr);
      }

      const options = [];
      for (const [name, arr] of groups.entries()) {
        if (name === 'Wallet' && arr.length > 1) {
          arr.forEach((it, i) => options.push({
            label: `Injected Wallet #${i + 1}`,
            provider: it.provider,
          }));
        } else {
          options.push({
            label: name,
            provider: arr[0].provider,
          });
        }
      }

      setWalletChooser({
        isOpen: true,
        targetChain,
        providers: options,
      });
      return false;
    }

    return connectWithProvider(providers[0], targetChain);
  }, [connectWithProvider, getCandidateProviders, getProviderName]);

  const chooseWalletProvider = useCallback(async (provider) => {
    if (!provider) return false;
    return connectWithProvider(provider, walletChooser.targetChain);
  }, [connectWithProvider, walletChooser.targetChain]);

  const cancelWalletChooser = useCallback(() => {
    setWalletChooser({ isOpen: false, targetChain: 'ethereum_sepolia', providers: [] });
  }, []);

  // Disconnect wallet
  const disconnectWallet = useCallback(() => {
    activeProviderRef.current = null;
    setWallet({
      address: null,
      chain: null,
      chainId: null,
      balance: '0',
      isConnected: false,
      isConnecting: false,
      error: null,
      providerName: null,
    });
  }, []);

  // Switch chain
  const switchChain = useCallback(async (targetChain) => {
    const provider = activeProviderRef.current || getInjectedProvider();
    if (!provider) return false;

    const config = CHAIN_CONFIGS[targetChain];
    if (!config) {
      console.error('Unknown chain:', targetChain);
      return false;
    }

    try {
      await provider.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: config.chainId }],
      });
      return true;
    } catch (switchError) {
      // Chain not added, try to add it
      if (switchError.code === 4902) {
        try {
          await provider.request({
            method: 'wallet_addEthereumChain',
            params: [config],
          });
          return true;
        } catch (addError) {
          console.error('Failed to add chain:', addError);
          return false;
        }
      }
      console.error('Failed to switch chain:', switchError);
      return false;
    }
  }, [getInjectedProvider]);

  // Sign message (for authentication)
  const signMessage = useCallback(async (message) => {
    const provider = getInjectedProvider();
    if (!wallet.address || !provider) {
      throw new Error('Wallet not connected');
    }

    try {
      const signature = await provider.request({
        method: 'personal_sign',
        params: [message, wallet.address],
      });
      return signature;
    } catch (error) {
      console.error('Failed to sign message:', error);
      throw error;
    }
  }, [wallet.address, getInjectedProvider]);

  // Send transaction
  const sendTransaction = useCallback(async (txData) => {
    const provider = getInjectedProvider();
    if (!wallet.address || !provider) {
      throw new Error('Wallet not connected');
    }

    try {
      const txHash = await provider.request({
        method: 'eth_sendTransaction',
        params: [{
          from: wallet.address,
          ...txData,
        }],
      });
      return txHash;
    } catch (error) {
      console.error('Transaction failed:', error);
      throw error;
    }
  }, [wallet.address, getInjectedProvider]);

  // Listen for account/chain changes
  useEffect(() => {
    const provider = activeProviderRef.current || getInjectedProvider();
    if (!provider) return;

    const handleAccountsChanged = async (accounts) => {
      if (accounts.length === 0) {
        disconnectWallet();
      } else if (accounts[0] !== wallet.address) {
        const balance = await fetchBalance(accounts[0]);
        setWallet(prev => ({
          ...prev,
          address: accounts[0],
          balance,
        }));
      }
    };

    const handleChainChanged = (chainId) => {
      let chain = null;
      for (const [key, config] of Object.entries(CHAIN_CONFIGS)) {
        if (config.chainId.toLowerCase() === chainId.toLowerCase()) {
          chain = key;
          break;
        }
      }
      setWallet(prev => ({
        ...prev,
        chain,
        chainId,
      }));
    };

    provider.on('accountsChanged', handleAccountsChanged);
    provider.on('chainChanged', handleChainChanged);

    return () => {
      provider.removeListener('accountsChanged', handleAccountsChanged);
      provider.removeListener('chainChanged', handleChainChanged);
    };
  }, [wallet.address, disconnectWallet, fetchBalance, getInjectedProvider]);

  // Check for existing connection on mount
  useEffect(() => {
    const checkExistingConnection = async () => {
      const provider = activeProviderRef.current || getInjectedProvider();
      if (!provider) return;

      try {
        const accounts = await provider.request({ method: 'eth_accounts' });
        if (accounts && accounts.length > 0) {
          const address = accounts[0];
          const chainId = await provider.request({ method: 'eth_chainId' });
          const balance = await fetchBalance(address);

          let chain = null;
          for (const [key, config] of Object.entries(CHAIN_CONFIGS)) {
            if (config.chainId.toLowerCase() === chainId.toLowerCase()) {
              chain = key;
              break;
            }
          }

          setWallet({
            address,
            chain,
            chainId,
            balance,
            isConnected: true,
            isConnecting: false,
            error: null,
          });
        }
      } catch (error) {
        console.error('Failed to check existing connection:', error);
      }
    };

    checkExistingConnection();
  }, [fetchBalance, getInjectedProvider]);

  const value = {
    wallet,
    isWalletAvailable,
    isMetaMaskAvailable,
    walletChooser,
    chooseWalletProvider,
    cancelWalletChooser,
    formatAddress,
    connectWallet,
    disconnectWallet,
    switchChain,
    signMessage,
    sendTransaction,
    CHAIN_CONFIGS,
  };

  return (
    <Web3Context.Provider value={value}>
      {children}
    </Web3Context.Provider>
  );
};

export default Web3Context;
