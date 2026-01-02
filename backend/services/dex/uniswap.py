"""Uniswap V3 integration for token swaps on Ethereum."""

import os
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal
from web3 import Web3
from eth_account.signers.local import LocalAccount

from .providers import BlockchainProviders, Chain, CHAIN_CONFIGS

logger = logging.getLogger(__name__)

# Uniswap V3 Router ABI (simplified)
ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountOut", "type": "uint256"},
                    {"name": "amountInMaximum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactOutputSingle",
        "outputs": [{"name": "amountIn", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

# ERC20 ABI for token operations
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
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

# Fee tiers available in Uniswap V3
FEE_TIERS = {
    "lowest": 100,    # 0.01%
    "low": 500,       # 0.05%
    "medium": 3000,   # 0.3%
    "high": 10000     # 1%
}


class UniswapV3Trader:
    """Uniswap V3 trading implementation."""
    
    def __init__(self, providers: BlockchainProviders, chain: Chain = Chain.ETHEREUM_SEPOLIA):
        self.providers = providers
        self.chain = chain
        self.config = CHAIN_CONFIGS[chain]
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
        """Get Uniswap V3 Router contract."""
        if self._router_contract is None:
            if not self.config.uniswap_v3_router:
                raise ValueError(f"Uniswap V3 not available on {self.config.name}")
            self._router_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.config.uniswap_v3_router),
                abi=ROUTER_ABI
            )
        return self._router_contract
    
    def get_token_contract(self, token_address: str):
        """Get ERC20 token contract."""
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
    
    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Get token information."""
        contract = self.get_token_contract(token_address)
        try:
            return {
                "address": token_address,
                "symbol": contract.functions.symbol().call(),
                "decimals": contract.functions.decimals().call(),
            }
        except Exception as e:
            logger.error(f"Failed to get token info: {e}")
            return {"address": token_address, "symbol": "UNKNOWN", "decimals": 18}
    
    async def get_token_balance(self, token_address: str, wallet_address: str) -> int:
        """Get token balance for wallet."""
        contract = self.get_token_contract(token_address)
        return contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    
    async def check_allowance(self, token_address: str, wallet_address: str) -> int:
        """Check token allowance for router."""
        contract = self.get_token_contract(token_address)
        return contract.functions.allowance(
            Web3.to_checksum_address(wallet_address),
            Web3.to_checksum_address(self.config.uniswap_v3_router)
        ).call()
    
    async def approve_token(
        self,
        token_address: str,
        amount: int = 2**256 - 1  # Max approval
    ) -> str:
        """Approve token for router spending."""
        if not self.providers.account:
            raise ValueError("No account configured")
        
        contract = self.get_token_contract(token_address)
        
        tx = contract.functions.approve(
            Web3.to_checksum_address(self.config.uniswap_v3_router),
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
    
    async def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        fee: int = 3000
    ) -> Dict[str, Any]:
        """Get swap quote (estimated output amount).
        
        Note: For production, use Uniswap Quoter V2 contract.
        This is a simplified estimation.
        """
        # In production, call the Quoter contract
        # For now, return a mock quote with fee estimation
        
        # Simulate 0.3% fee + 0.1% slippage
        estimated_fee_pct = fee / 1_000_000  # Convert basis points
        estimated_out = int(amount_in * (1 - estimated_fee_pct - 0.001))
        
        return {
            "amount_in": amount_in,
            "amount_out": estimated_out,
            "price_impact": 0.1,  # Mock value
            "fee_tier": fee,
            "route": [token_in, token_out],
            "gas_estimate": 200000,
        }
    
    def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        recipient: str,
        fee: int = 3000,
        deadline_minutes: int = 20
    ) -> Dict[str, Any]:
        """Build swap transaction (unsigned).
        
        Returns transaction data for frontend signing or backend execution.
        """
        deadline = int(time.time()) + (deadline_minutes * 60)
        
        swap_params = {
            'tokenIn': Web3.to_checksum_address(token_in),
            'tokenOut': Web3.to_checksum_address(token_out),
            'fee': fee,
            'recipient': Web3.to_checksum_address(recipient),
            'deadline': deadline,
            'amountIn': amount_in,
            'amountOutMinimum': min_amount_out,
            'sqrtPriceLimitX96': 0,
        }
        
        # Build transaction data
        tx_data = self.router_contract.encodeABI(
            fn_name='exactInputSingle',
            args=[tuple(swap_params.values())]
        )
        
        # Check if native ETH swap (token_in is WETH)
        is_eth_swap = token_in.lower() == self.config.weth_address.lower() if self.config.weth_address else False
        
        return {
            'to': self.config.uniswap_v3_router,
            'data': tx_data,
            'value': amount_in if is_eth_swap else 0,
            'chainId': self.config.chain_id,
        }
    
    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        fee: int = 3000,
        slippage_pct: float = 0.5
    ) -> Dict[str, Any]:
        """Execute swap with backend wallet (full automation mode)."""
        if not self.providers.account:
            raise ValueError("No account configured for automated trading")
        
        recipient = self.providers.address
        
        # Check and approve token if needed
        if token_in.lower() != self.config.weth_address.lower() if self.config.weth_address else True:
            allowance = await self.check_allowance(token_in, recipient)
            if allowance < amount_in:
                logger.info(f"Approving token {token_in}...")
                approval_tx = await self.approve_token(token_in)
                # Wait for approval
                await self.providers.wait_for_receipt(self.chain, approval_tx)
        
        # Build transaction
        tx_dict = self.build_swap_transaction(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            min_amount_out=min_amount_out,
            recipient=recipient,
            fee=fee
        )
        
        # Add gas parameters
        tx_dict['from'] = recipient
        tx_dict['nonce'] = self.providers.get_nonce(self.chain)
        tx_dict['gas'] = self.providers.estimate_gas(self.chain, tx_dict)
        tx_dict['gasPrice'] = self.providers.get_gas_price(self.chain)
        
        # Sign and send
        tx_hash = self.providers.sign_and_send_transaction(self.chain, tx_dict)
        logger.info(f"Swap transaction sent: {tx_hash}")
        
        # Wait for receipt
        receipt = await self.providers.wait_for_receipt(self.chain, tx_hash)
        
        return {
            'tx_hash': tx_hash,
            'status': 'success' if receipt.get('status') == 1 else 'failed',
            'gas_used': receipt.get('gasUsed'),
            'block_number': receipt.get('blockNumber'),
            'chain': self.chain.value,
        }
