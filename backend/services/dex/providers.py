"""Blockchain providers and configuration for multi-chain DEX trading."""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
from eth_account.signers.local import LocalAccount

logger = logging.getLogger(__name__)


class Chain(str, Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    ETHEREUM_SEPOLIA = "ethereum_sepolia"
    BSC = "bsc"
    BSC_TESTNET = "bsc_testnet"
    SOLANA = "solana"
    SOLANA_DEVNET = "solana_devnet"


@dataclass
class ChainConfig:
    """Configuration for a blockchain network."""
    chain_id: int
    name: str
    rpc_url: str
    ws_url: Optional[str] = None
    explorer_url: Optional[str] = None
    native_token: str = "ETH"
    is_testnet: bool = False
    
    # DEX Router addresses
    uniswap_v3_router: Optional[str] = None
    uniswap_v3_factory: Optional[str] = None
    uniswap_v3_quoter: Optional[str] = None
    pancakeswap_router: Optional[str] = None
    
    # Common token addresses
    weth_address: Optional[str] = None
    usdc_address: Optional[str] = None
    usdt_address: Optional[str] = None


# Chain configurations with FREE public RPCs for testnets
CHAIN_CONFIGS: Dict[Chain, ChainConfig] = {
    # Ethereum Mainnet
    Chain.ETHEREUM: ChainConfig(
        chain_id=1,
        name="Ethereum Mainnet",
        rpc_url=os.getenv("ETHEREUM_RPC", "https://eth.llamarpc.com"),
        ws_url=os.getenv("ETHEREUM_WS"),
        explorer_url="https://etherscan.io",
        native_token="ETH",
        is_testnet=False,
        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
        uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
        uniswap_v3_quoter="0x61fFE014bA17989E743be259ff6aeF693Bfd5f02",
        weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        usdc_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        usdt_address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
    ),
    
    # Ethereum Sepolia Testnet (FREE)
    Chain.ETHEREUM_SEPOLIA: ChainConfig(
        chain_id=11155111,
        name="Ethereum Sepolia",
        rpc_url=os.getenv("SEPOLIA_RPC", "https://rpc.sepolia.org"),
        ws_url=os.getenv("SEPOLIA_WS"),
        explorer_url="https://sepolia.etherscan.io",
        native_token="SepoliaETH",
        is_testnet=True,
        uniswap_v3_router="0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E",
        uniswap_v3_factory="0x0227628f3F023bb0B980b67D528571c95c6DaC1c",
        uniswap_v3_quoter="0xEd1f6473345F45b75F8179591dd5bA1888cf2FB3",
        weth_address="0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
    ),
    
    # BSC Mainnet
    Chain.BSC: ChainConfig(
        chain_id=56,
        name="BNB Smart Chain",
        rpc_url=os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org"),
        ws_url=os.getenv("BSC_WS"),
        explorer_url="https://bscscan.com",
        native_token="BNB",
        is_testnet=False,
        pancakeswap_router="0x10ED43C718714eb63d5aA57B78B985BB81d7d565",
        weth_address="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
        usdc_address="0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        usdt_address="0x55d398326f99059fF775485246999027B3197955",
    ),
    
    # BSC Testnet (FREE)
    Chain.BSC_TESTNET: ChainConfig(
        chain_id=97,
        name="BNB Smart Chain Testnet",
        rpc_url=os.getenv("BSC_TESTNET_RPC", "https://data-seed-prebsc-1-s1.binance.org:8545"),
        ws_url=os.getenv("BSC_TESTNET_WS"),
        explorer_url="https://testnet.bscscan.com",
        native_token="tBNB",
        is_testnet=True,
        pancakeswap_router="0xD99D1c33F9fC3444f8101754aBC46c52416550D1",
        weth_address="0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",  # WBNB Testnet
    ),
    
    # Solana Mainnet
    Chain.SOLANA: ChainConfig(
        chain_id=0,  # Solana doesn't use chain IDs
        name="Solana Mainnet",
        rpc_url=os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com"),
        ws_url=os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com"),
        explorer_url="https://solscan.io",
        native_token="SOL",
        is_testnet=False,
    ),
    
    # Solana Devnet (FREE)
    Chain.SOLANA_DEVNET: ChainConfig(
        chain_id=0,
        name="Solana Devnet",
        rpc_url=os.getenv("SOLANA_DEVNET_RPC", "https://api.devnet.solana.com"),
        ws_url=os.getenv("SOLANA_DEVNET_WS", "wss://api.devnet.solana.com"),
        explorer_url="https://solscan.io?cluster=devnet",
        native_token="SOL",
        is_testnet=True,
    ),
}


class BlockchainProviders:
    """Manager for blockchain providers across multiple chains."""
    
    def __init__(self):
        self._providers: Dict[Chain, Web3] = {}
        self._account: Optional[LocalAccount] = None
        self._solana_keypair = None
        
        # Initialize EVM account from private key if available
        private_key = os.getenv("DEX_PRIVATE_KEY")
        if private_key:
            try:
                self._account = Account.from_key(private_key)
                logger.info(f"DEX wallet initialized: {self._account.address}")
            except Exception as e:
                logger.warning(f"Failed to load DEX private key: {e}")
    
    def get_config(self, chain: Chain) -> ChainConfig:
        """Get configuration for a chain."""
        return CHAIN_CONFIGS[chain]
    
    def get_provider(self, chain: Chain) -> Web3:
        """Get or create Web3 provider for EVM chain."""
        if chain in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            raise ValueError("Use get_solana_client for Solana chains")
        
        if chain not in self._providers:
            config = CHAIN_CONFIGS[chain]
            provider = Web3(Web3.HTTPProvider(config.rpc_url))
            
            # Add POA middleware for BSC
            if chain in [Chain.BSC, Chain.BSC_TESTNET]:
                provider.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            
            if provider.is_connected():
                logger.info(f"Connected to {config.name} (Chain ID: {provider.eth.chain_id})")
                self._providers[chain] = provider
            else:
                raise ConnectionError(f"Failed to connect to {config.name}")
        
        return self._providers[chain]
    
    def get_solana_client(self, testnet: bool = True):
        """Get Solana RPC client."""
        from solana.rpc.async_api import AsyncClient
        
        chain = Chain.SOLANA_DEVNET if testnet else Chain.SOLANA
        config = CHAIN_CONFIGS[chain]
        return AsyncClient(config.rpc_url)
    
    @property
    def account(self) -> Optional[LocalAccount]:
        """Get the signing account."""
        return self._account
    
    @property
    def address(self) -> Optional[str]:
        """Get wallet address."""
        return self._account.address if self._account else None
    
    def get_nonce(self, chain: Chain) -> int:
        """Get current nonce for account."""
        if not self._account:
            raise ValueError("No account configured")
        provider = self.get_provider(chain)
        return provider.eth.get_transaction_count(self._account.address)
    
    def get_balance(self, chain: Chain, address: Optional[str] = None) -> float:
        """Get native token balance."""
        provider = self.get_provider(chain)
        addr = address or self.address
        if not addr:
            raise ValueError("No address provided")
        balance_wei = provider.eth.get_balance(addr)
        return float(Web3.from_wei(balance_wei, 'ether'))
    
    def estimate_gas(self, chain: Chain, tx_dict: Dict) -> int:
        """Estimate gas for transaction."""
        provider = self.get_provider(chain)
        try:
            estimated = provider.eth.estimate_gas(tx_dict)
            # Add 20% buffer
            return int(estimated * 1.2)
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}, using default")
            return 300000
    
    def get_gas_price(self, chain: Chain) -> int:
        """Get current gas price."""
        provider = self.get_provider(chain)
        return provider.eth.gas_price
    
    def sign_and_send_transaction(self, chain: Chain, tx_dict: Dict) -> str:
        """Sign and send a transaction."""
        if not self._account:
            raise ValueError("No account configured for signing")
        
        provider = self.get_provider(chain)
        
        # Ensure required fields
        if 'nonce' not in tx_dict:
            tx_dict['nonce'] = self.get_nonce(chain)
        if 'gas' not in tx_dict:
            tx_dict['gas'] = self.estimate_gas(chain, tx_dict)
        if 'gasPrice' not in tx_dict:
            tx_dict['gasPrice'] = self.get_gas_price(chain)
        if 'chainId' not in tx_dict:
            tx_dict['chainId'] = CHAIN_CONFIGS[chain].chain_id
        
        # Sign transaction
        signed_tx = self._account.sign_transaction(tx_dict)
        
        # Send transaction
        tx_hash = provider.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        return tx_hash.hex()
    
    async def wait_for_receipt(self, chain: Chain, tx_hash: str, timeout: int = 120) -> Dict:
        """Wait for transaction receipt."""
        provider = self.get_provider(chain)
        receipt = provider.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return dict(receipt)


# Global instance
blockchain_providers = BlockchainProviders()
