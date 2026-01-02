"""Jupiter Aggregator integration for Solana token swaps."""

import os
import logging
import httpx
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Jupiter API endpoints
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6"
JUPITER_SWAP_API = "https://api.jup.ag/swap/v1"

# Common Solana token mints
SOLANA_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",  # Wrapped SOL
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # Raydium
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
}

# Devnet tokens for testing
SOLANA_DEVNET_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr",  # Devnet USDC
}


class JupiterAggregator:
    """Jupiter aggregator for optimal Solana token swaps."""
    
    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.rpc_url = os.getenv(
            "SOLANA_DEVNET_RPC" if testnet else "SOLANA_RPC",
            "https://api.devnet.solana.com" if testnet else "https://api.mainnet-beta.solana.com"
        )
        self.tokens = SOLANA_DEVNET_TOKENS if testnet else SOLANA_TOKENS
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    async def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    def get_token_mint(self, symbol: str) -> Optional[str]:
        """Get token mint address from symbol."""
        return self.tokens.get(symbol.upper())
    
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50  # 0.5%
    ) -> Dict[str, Any]:
        """Get swap quote from Jupiter.
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Input amount in lamports/smallest unit
            slippage_bps: Slippage tolerance in basis points
        """
        client = await self.client
        
        try:
            response = await client.get(
                f"{JUPITER_QUOTE_API}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(amount),
                    "slippageBps": slippage_bps,
                    "onlyDirectRoutes": False,
                    "asLegacyTransaction": False,
                }
            )
            response.raise_for_status()
            quote_data = response.json()
            
            return {
                "success": True,
                "input_mint": input_mint,
                "output_mint": output_mint,
                "amount_in": amount,
                "amount_out": int(quote_data.get("outAmount", 0)),
                "price_impact_pct": float(quote_data.get("priceImpactPct", 0)),
                "route_plan": quote_data.get("routePlan", []),
                "slippage_bps": slippage_bps,
                "raw_quote": quote_data,
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Jupiter quote error: {e.response.text}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except Exception as e:
            logger.error(f"Jupiter quote failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_swap_transaction(
        self,
        quote: Dict[str, Any],
        user_public_key: str,
        wrap_unwrap_sol: bool = True
    ) -> Dict[str, Any]:
        """Get serialized swap transaction from Jupiter.
        
        Args:
            quote: Quote response from get_quote
            user_public_key: User's Solana public key
            wrap_unwrap_sol: Auto wrap/unwrap SOL
        """
        if not quote.get("success") or "raw_quote" not in quote:
            return {"success": False, "error": "Invalid quote"}
        
        client = await self.client
        
        try:
            response = await client.post(
                f"{JUPITER_SWAP_API}/swap",
                json={
                    "quoteResponse": quote["raw_quote"],
                    "userPublicKey": user_public_key,
                    "wrapAndUnwrapSol": wrap_unwrap_sol,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": "auto",
                }
            )
            response.raise_for_status()
            swap_data = response.json()
            
            return {
                "success": True,
                "swap_transaction": swap_data.get("swapTransaction"),
                "last_valid_block_height": swap_data.get("lastValidBlockHeight"),
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Jupiter swap error: {e.response.text}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Jupiter swap failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        user_public_key: str,
        private_key_bytes: Optional[bytes] = None,
        slippage_bps: int = 50
    ) -> Dict[str, Any]:
        """Execute full swap flow.
        
        For frontend: Returns unsigned transaction for wallet signing.
        For backend automation: Signs and sends if private_key provided.
        """
        # Get quote
        quote = await self.get_quote(input_mint, output_mint, amount, slippage_bps)
        if not quote.get("success"):
            return quote
        
        # Get swap transaction
        swap_result = await self.get_swap_transaction(quote, user_public_key)
        if not swap_result.get("success"):
            return swap_result
        
        result = {
            "success": True,
            "quote": quote,
            "swap_transaction": swap_result.get("swap_transaction"),
            "requires_signing": True,
        }
        
        # If private key provided, sign and send (backend automation)
        if private_key_bytes:
            try:
                from solders.keypair import Keypair
                from solders.transaction import VersionedTransaction
                from solana.rpc.async_api import AsyncClient
                
                # Decode transaction
                tx_bytes = base64.b64decode(swap_result["swap_transaction"])
                tx = VersionedTransaction.from_bytes(tx_bytes)
                
                # Sign transaction
                keypair = Keypair.from_bytes(private_key_bytes)
                tx.sign([keypair])
                
                # Send transaction
                async with AsyncClient(self.rpc_url) as rpc_client:
                    sig = await rpc_client.send_transaction(tx)
                    
                    result["requires_signing"] = False
                    result["signature"] = str(sig.value)
                    result["explorer_url"] = f"https://solscan.io/tx/{sig.value}" + \
                        ("?cluster=devnet" if self.testnet else "")
                    
            except Exception as e:
                logger.error(f"Solana transaction signing failed: {e}")
                result["signing_error"] = str(e)
        
        return result
    
    async def get_token_price(
        self,
        token_mint: str
    ) -> Optional[float]:
        """Get token price in USD."""
        client = await self.client
        
        try:
            response = await client.get(
                f"https://price.jup.ag/v4/price",
                params={"ids": token_mint}
            )
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and token_mint in data["data"]:
                return float(data["data"][token_mint].get("price", 0))
            return None
            
        except Exception as e:
            logger.error(f"Price fetch failed: {e}")
            return None
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
