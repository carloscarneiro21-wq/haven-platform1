"""PancakeSwap integration for token swaps on BSC."""

import os
import time
import logging
from typing import Dict, Any, Optional, List
from web3 import Web3

from .providers import BlockchainProviders, Chain, CHAIN_CONFIGS

logger = logging.getLogger(__name__)

# PancakeSwap V2 Router ABI
PANCAKESWAP_ROUTER_ABI = [
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI for approvals
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]


class PancakeSwapTrader:
    """PancakeSwap V2 trading implementation for BSC."""
    
    def __init__(self, providers: BlockchainProviders, testnet: bool = True):
        self.providers = providers
        self.chain = Chain.BSC_TESTNET if testnet else Chain.BSC
        self.config = CHAIN_CONFIGS[self.chain]
        self._web3: Optional[Web3] = None
        self._router_contract = None
    
    @property
    def web3(self) -> Web3:
        """Lazy load Web3 provider."""
        if self._web3 is None:
            self._web3 = self.providers.get_provider(self.chain)
        return self._web3
    
    @property
    def router_contract(self):
        """Get PancakeSwap Router contract."""
        if self._router_contract is None:
            if not self.config.pancakeswap_router:
                raise ValueError(f"PancakeSwap not available on {self.config.name}")
            self._router_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.config.pancakeswap_router),
                abi=PANCAKESWAP_ROUTER_ABI
            )
        return self._router_contract
    
    def get_token_contract(self, token_address: str):
        """Get ERC20 token contract."""
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
    
    async def get_optimal_path(
        self,
        token_in: str,
        token_out: str,
        amount_in: int
    ) -> tuple[List[str], int]:
        """Calculate optimal swap path and output amount."""
        wbnb = self.config.weth_address  # WBNB address
        
        # Try direct path first
        direct_path = [
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out)
        ]
        
        try:
            direct_amounts = self.router_contract.functions.getAmountsOut(
                amount_in,
                direct_path
            ).call()
            direct_out = direct_amounts[-1]
        except Exception:
            direct_out = 0
        
        # Try path through WBNB
        wbnb_path = [
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(wbnb),
            Web3.to_checksum_address(token_out)
        ]
        
        try:
            wbnb_amounts = self.router_contract.functions.getAmountsOut(
                amount_in,
                wbnb_path
            ).call()
            wbnb_out = wbnb_amounts[-1]
        except Exception:
            wbnb_out = 0
        
        # Return best path
        if direct_out >= wbnb_out and direct_out > 0:
            return direct_path, direct_out
        elif wbnb_out > 0:
            return wbnb_path, wbnb_out
        else:
            # Fallback estimate
            return direct_path, int(amount_in * 0.995)
    
    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: int
    ) -> Dict[str, Any]:
        """Get swap quote with optimal path."""
        path, amount_out = await self.get_optimal_path(token_in, token_out, amount_in)
        
        return {
            "amount_in": amount_in,
            "amount_out": amount_out,
            "price_impact": 0.3,  # Estimated
            "route": path,
            "gas_estimate": 250000,
        }
    
    async def check_allowance(self, token_address: str, wallet_address: str) -> int:
        """Check token allowance for router."""
        contract = self.get_token_contract(token_address)
        return contract.functions.allowance(
            Web3.to_checksum_address(wallet_address),
            Web3.to_checksum_address(self.config.pancakeswap_router)
        ).call()
    
    async def approve_token(
        self,
        token_address: str,
        amount: int = 2**256 - 1
    ) -> str:
        """Approve token for router spending."""
        if not self.providers.account:
            raise ValueError("No account configured")
        
        contract = self.get_token_contract(token_address)
        
        tx = contract.functions.approve(
            Web3.to_checksum_address(self.config.pancakeswap_router),
            amount
        ).build_transaction({
            'from': self.providers.address,
            'nonce': self.providers.get_nonce(self.chain),
            'gas': 100000,
            'gasPrice': self.providers.get_gas_price(self.chain),
            'chainId': self.config.chain_id,
        })
        
        tx_hash = self.providers.sign_and_send_transaction(self.chain, tx)
        logger.info(f"Token approval tx: {tx_hash}")
        return tx_hash
    
    def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        recipient: str,
        path: Optional[List[str]] = None,
        deadline_minutes: int = 20
    ) -> Dict[str, Any]:
        """Build swap transaction."""
        deadline = int(time.time()) + (deadline_minutes * 60)
        
        # Use provided path or create direct path
        swap_path = path or [
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out)
        ]
        
        wbnb = self.config.weth_address
        is_bnb_in = token_in.lower() == wbnb.lower() if wbnb else False
        is_bnb_out = token_out.lower() == wbnb.lower() if wbnb else False
        
        if is_bnb_in:
            # BNB -> Token
            tx_data = self.router_contract.encodeABI(
                fn_name='swapExactETHForTokens',
                args=[
                    min_amount_out,
                    swap_path,
                    Web3.to_checksum_address(recipient),
                    deadline
                ]
            )
            value = amount_in
        elif is_bnb_out:
            # Token -> BNB
            tx_data = self.router_contract.encodeABI(
                fn_name='swapExactTokensForETH',
                args=[
                    amount_in,
                    min_amount_out,
                    swap_path,
                    Web3.to_checksum_address(recipient),
                    deadline
                ]
            )
            value = 0
        else:
            # Token -> Token
            tx_data = self.router_contract.encodeABI(
                fn_name='swapExactTokensForTokens',
                args=[
                    amount_in,
                    min_amount_out,
                    swap_path,
                    Web3.to_checksum_address(recipient),
                    deadline
                ]
            )
            value = 0
        
        return {
            'to': self.config.pancakeswap_router,
            'data': tx_data,
            'value': value,
            'chainId': self.config.chain_id,
        }
    
    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        slippage_pct: float = 0.5
    ) -> Dict[str, Any]:
        """Execute swap with backend wallet."""
        if not self.providers.account:
            raise ValueError("No account configured for automated trading")
        
        recipient = self.providers.address
        
        # Get optimal path and expected output
        path, expected_out = await self.get_optimal_path(token_in, token_out, amount_in)
        
        # Calculate minimum output with slippage
        min_amount_out = int(expected_out * (1 - slippage_pct / 100))
        
        # Check if token needs approval (not for native BNB)
        wbnb = self.config.weth_address
        if token_in.lower() != wbnb.lower() if wbnb else True:
            allowance = await self.check_allowance(token_in, recipient)
            if allowance < amount_in:
                logger.info(f"Approving token {token_in}...")
                approval_tx = await self.approve_token(token_in)
                await self.providers.wait_for_receipt(self.chain, approval_tx)
        
        # Build and send transaction
        tx_dict = self.build_swap_transaction(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            min_amount_out=min_amount_out,
            recipient=recipient,
            path=path
        )
        
        tx_dict['from'] = recipient
        tx_dict['nonce'] = self.providers.get_nonce(self.chain)
        tx_dict['gas'] = self.providers.estimate_gas(self.chain, tx_dict)
        tx_dict['gasPrice'] = self.providers.get_gas_price(self.chain)
        
        tx_hash = self.providers.sign_and_send_transaction(self.chain, tx_dict)
        logger.info(f"Swap transaction sent: {tx_hash}")
        
        receipt = await self.providers.wait_for_receipt(self.chain, tx_hash)
        
        return {
            'tx_hash': tx_hash,
            'status': 'success' if receipt.get('status') == 1 else 'failed',
            'gas_used': receipt.get('gasUsed'),
            'block_number': receipt.get('blockNumber'),
            'chain': self.chain.value,
            'path': path,
        }
