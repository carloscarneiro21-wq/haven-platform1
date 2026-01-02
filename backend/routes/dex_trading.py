"""DEX Trading API routes for multi-chain swaps and sniping."""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from services.dex.providers import BlockchainProviders, Chain, CHAIN_CONFIGS, blockchain_providers
from services.dex.uniswap import UniswapV3Trader
from services.dex.pancakeswap import PancakeSwapTrader
from services.dex.jupiter import JupiterAggregator, SOLANA_TOKENS, SOLANA_DEVNET_TOKENS
from services.dex.sniper import TokenSniper, LiquidityMonitor, SnipeConfig, SnipeStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dex", tags=["dex"])

# Global instances (initialized on startup)
_uniswap_trader: Optional[UniswapV3Trader] = None
_pancakeswap_trader: Optional[PancakeSwapTrader] = None
_jupiter: Optional[JupiterAggregator] = None
_sniper: Optional[TokenSniper] = None
_liquidity_monitor: Optional[LiquidityMonitor] = None


# ============ Request/Response Models ============

class ChainInfo(BaseModel):
    chain_id: str
    name: str
    native_token: str
    is_testnet: bool
    explorer_url: Optional[str]
    dex_available: List[str]


class SwapQuoteRequest(BaseModel):
    chain: str = Field(..., description="Chain ID: ethereum_sepolia, bsc_testnet, solana_devnet")
    token_in: str = Field(..., description="Input token address or symbol")
    token_out: str = Field(..., description="Output token address or symbol")
    amount_in: str = Field(..., description="Input amount in human-readable format (e.g., '0.1')")
    slippage_pct: float = Field(default=0.5, description="Slippage tolerance percentage")


class SwapQuoteResponse(BaseModel):
    success: bool
    chain: str
    token_in: str
    token_out: str
    amount_in: str
    amount_out: str
    price_impact: float
    route: List[str]
    gas_estimate: int
    error: Optional[str] = None


class SwapExecuteRequest(BaseModel):
    chain: str
    token_in: str
    token_out: str
    amount_in: str
    min_amount_out: str
    recipient: str
    slippage_pct: float = 0.5


class SwapExecuteResponse(BaseModel):
    success: bool
    tx_hash: Optional[str] = None
    status: str
    chain: str
    gas_used: Optional[int] = None
    block_number: Optional[int] = None
    error: Optional[str] = None


class SnipeConfigRequest(BaseModel):
    enabled: bool = False
    chain: str = "ethereum_sepolia"
    buy_amount_eth: float = 0.01
    max_slippage_pct: float = 10.0
    min_liquidity_usd: float = 1000.0
    max_buy_tax_pct: float = 10.0
    max_sell_tax_pct: float = 10.0
    auto_sell_enabled: bool = False
    auto_sell_profit_pct: float = 100.0
    auto_sell_loss_pct: float = 50.0
    blacklisted_tokens: List[str] = []


class WalletBalanceRequest(BaseModel):
    chain: str
    address: str


class TokenInfo(BaseModel):
    address: str
    symbol: str
    decimals: int
    balance: Optional[str] = None


# ============ Initialization ============

def get_db():
    """Get database instance from main app."""
    from server import db
    return db


def init_dex_services(db):
    """Initialize DEX services with database."""
    global _uniswap_trader, _pancakeswap_trader, _jupiter, _sniper, _liquidity_monitor
    
    # Initialize traders (testnet by default)
    _uniswap_trader = UniswapV3Trader(blockchain_providers, Chain.ETHEREUM_SEPOLIA)
    _pancakeswap_trader = PancakeSwapTrader(blockchain_providers, testnet=True)
    _jupiter = JupiterAggregator(testnet=True)
    
    # Initialize sniper
    _sniper = TokenSniper(blockchain_providers, db)
    
    # Initialize liquidity monitor
    _liquidity_monitor = LiquidityMonitor(blockchain_providers, db)
    
    logger.info("DEX services initialized (testnet mode)")


# ============ Chain Info Endpoints ============

@router.get("/chains", response_model=List[ChainInfo])
async def get_supported_chains():
    """Get list of supported blockchain networks."""
    chains = []
    
    for chain, config in CHAIN_CONFIGS.items():
        dex_list = []
        if config.uniswap_v3_router:
            dex_list.append("uniswap_v3")
        if config.pancakeswap_router:
            dex_list.append("pancakeswap")
        if chain in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            dex_list.append("jupiter")
        
        chains.append(ChainInfo(
            chain_id=chain.value,
            name=config.name,
            native_token=config.native_token,
            is_testnet=config.is_testnet,
            explorer_url=config.explorer_url,
            dex_available=dex_list,
        ))
    
    return chains


@router.get("/chains/{chain_id}")
async def get_chain_details(chain_id: str):
    """Get detailed info for a specific chain."""
    try:
        chain = Chain(chain_id)
        config = CHAIN_CONFIGS[chain]
        
        return {
            "chain_id": chain.value,
            "chain_numeric_id": config.chain_id,
            "name": config.name,
            "native_token": config.native_token,
            "is_testnet": config.is_testnet,
            "rpc_url": config.rpc_url,
            "explorer_url": config.explorer_url,
            "contracts": {
                "weth": config.weth_address,
                "usdc": config.usdc_address,
                "usdt": config.usdt_address,
                "uniswap_v3_router": config.uniswap_v3_router,
                "pancakeswap_router": config.pancakeswap_router,
            }
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Chain '{chain_id}' not found")


# ============ Wallet Endpoints ============

@router.post("/wallet/balance")
async def get_wallet_balance(request: WalletBalanceRequest):
    """Get native token balance for wallet."""
    try:
        chain = Chain(request.chain)
        
        if chain in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            # Solana balance check
            return {
                "chain": request.chain,
                "address": request.address,
                "balance": "0",  # Would need Solana client
                "symbol": "SOL",
            }
        else:
            balance = blockchain_providers.get_balance(chain, request.address)
            config = CHAIN_CONFIGS[chain]
            return {
                "chain": request.chain,
                "address": request.address,
                "balance": str(balance),
                "symbol": config.native_token,
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/wallet/status")
async def get_backend_wallet_status():
    """Check if backend wallet is configured for automated trading."""
    address = blockchain_providers.address
    
    if not address:
        return {
            "configured": False,
            "message": "No DEX_PRIVATE_KEY configured. Automated trading disabled.",
        }
    
    # Get balances on testnets
    balances = {}
    for chain in [Chain.ETHEREUM_SEPOLIA, Chain.BSC_TESTNET]:
        try:
            balance = blockchain_providers.get_balance(chain, address)
            balances[chain.value] = balance
        except Exception:
            balances[chain.value] = 0
    
    return {
        "configured": True,
        "address": address,
        "balances": balances,
        "mode": "testnet",
    }


# ============ Swap Endpoints ============

@router.post("/swap/quote", response_model=SwapQuoteResponse)
async def get_swap_quote(request: SwapQuoteRequest):
    """Get swap quote for token pair."""
    try:
        chain = Chain(request.chain)
        config = CHAIN_CONFIGS[chain]
        
        # Parse amount (human readable to wei)
        decimals = 18  # Assume 18 decimals for native tokens
        amount_in_wei = int(float(request.amount_in) * (10 ** decimals))
        
        if chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA]:
            if not _uniswap_trader:
                raise HTTPException(status_code=503, detail="Uniswap trader not initialized")
            
            quote = await _uniswap_trader.get_quote(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
            )
            
            return SwapQuoteResponse(
                success=True,
                chain=request.chain,
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=request.amount_in,
                amount_out=str(float(quote["amount_out"]) / (10 ** decimals)),
                price_impact=quote.get("price_impact", 0),
                route=quote.get("route", [request.token_in, request.token_out]),
                gas_estimate=quote.get("gas_estimate", 200000),
            )
            
        elif chain in [Chain.BSC, Chain.BSC_TESTNET]:
            if not _pancakeswap_trader:
                raise HTTPException(status_code=503, detail="PancakeSwap trader not initialized")
            
            quote = await _pancakeswap_trader.get_quote(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
            )
            
            return SwapQuoteResponse(
                success=True,
                chain=request.chain,
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=request.amount_in,
                amount_out=str(float(quote["amount_out"]) / (10 ** decimals)),
                price_impact=quote.get("price_impact", 0),
                route=quote.get("route", []),
                gas_estimate=quote.get("gas_estimate", 250000),
            )
            
        elif chain in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            if not _jupiter:
                raise HTTPException(status_code=503, detail="Jupiter aggregator not initialized")
            
            # Convert symbol to mint if needed
            tokens = SOLANA_DEVNET_TOKENS if chain == Chain.SOLANA_DEVNET else SOLANA_TOKENS
            input_mint = tokens.get(request.token_in.upper(), request.token_in)
            output_mint = tokens.get(request.token_out.upper(), request.token_out)
            
            # Solana uses lamports (9 decimals for SOL)
            sol_decimals = 9
            amount_lamports = int(float(request.amount_in) * (10 ** sol_decimals))
            
            quote = await _jupiter.get_quote(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount_lamports,
                slippage_bps=int(request.slippage_pct * 100),
            )
            
            if not quote.get("success"):
                return SwapQuoteResponse(
                    success=False,
                    chain=request.chain,
                    token_in=request.token_in,
                    token_out=request.token_out,
                    amount_in=request.amount_in,
                    amount_out="0",
                    price_impact=0,
                    route=[],
                    gas_estimate=0,
                    error=quote.get("error"),
                )
            
            return SwapQuoteResponse(
                success=True,
                chain=request.chain,
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=request.amount_in,
                amount_out=str(float(quote["amount_out"]) / (10 ** sol_decimals)),
                price_impact=quote.get("price_impact_pct", 0),
                route=[input_mint, output_mint],
                gas_estimate=5000,  # Compute units estimate
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported chain: {request.chain}")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Quote error: {e}")
        return SwapQuoteResponse(
            success=False,
            chain=request.chain,
            token_in=request.token_in,
            token_out=request.token_out,
            amount_in=request.amount_in,
            amount_out="0",
            price_impact=0,
            route=[],
            gas_estimate=0,
            error=str(e),
        )


@router.post("/swap/build-transaction")
async def build_swap_transaction(request: SwapExecuteRequest):
    """Build unsigned swap transaction for frontend signing."""
    try:
        chain = Chain(request.chain)
        config = CHAIN_CONFIGS[chain]
        
        decimals = 18
        amount_in_wei = int(float(request.amount_in) * (10 ** decimals))
        min_amount_out_wei = int(float(request.min_amount_out) * (10 ** decimals))
        
        if chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA]:
            if not _uniswap_trader:
                raise HTTPException(status_code=503, detail="Trader not initialized")
            
            tx_data = _uniswap_trader.build_swap_transaction(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
                min_amount_out=min_amount_out_wei,
                recipient=request.recipient,
            )
            
            return {
                "success": True,
                "transaction": tx_data,
                "chain_id": config.chain_id,
            }
            
        elif chain in [Chain.BSC, Chain.BSC_TESTNET]:
            if not _pancakeswap_trader:
                raise HTTPException(status_code=503, detail="Trader not initialized")
            
            tx_data = _pancakeswap_trader.build_swap_transaction(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
                min_amount_out=min_amount_out_wei,
                recipient=request.recipient,
            )
            
            return {
                "success": True,
                "transaction": tx_data,
                "chain_id": config.chain_id,
            }
            
        elif chain in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            if not _jupiter:
                raise HTTPException(status_code=503, detail="Jupiter not initialized")
            
            # Get quote first
            tokens = SOLANA_DEVNET_TOKENS if chain == Chain.SOLANA_DEVNET else SOLANA_TOKENS
            input_mint = tokens.get(request.token_in.upper(), request.token_in)
            output_mint = tokens.get(request.token_out.upper(), request.token_out)
            
            amount_lamports = int(float(request.amount_in) * (10 ** 9))
            
            quote = await _jupiter.get_quote(input_mint, output_mint, amount_lamports)
            if not quote.get("success"):
                raise HTTPException(status_code=400, detail=quote.get("error"))
            
            # Get swap transaction
            swap_result = await _jupiter.get_swap_transaction(quote, request.recipient)
            
            return {
                "success": True,
                "transaction": swap_result.get("swap_transaction"),
                "requires_signing": True,
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported chain: {request.chain}")
            
    except Exception as e:
        logger.error(f"Build transaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swap/execute", response_model=SwapExecuteResponse)
async def execute_swap(request: SwapExecuteRequest):
    """Execute swap with backend wallet (automated mode)."""
    if not blockchain_providers.account:
        raise HTTPException(
            status_code=400,
            detail="Backend wallet not configured. Set DEX_PRIVATE_KEY for automated trading."
        )
    
    try:
        chain = Chain(request.chain)
        
        decimals = 18
        amount_in_wei = int(float(request.amount_in) * (10 ** decimals))
        min_amount_out_wei = int(float(request.min_amount_out) * (10 ** decimals))
        
        if chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA]:
            if not _uniswap_trader:
                raise HTTPException(status_code=503, detail="Trader not initialized")
            
            result = await _uniswap_trader.execute_swap(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
                min_amount_out=min_amount_out_wei,
                slippage_pct=request.slippage_pct,
            )
            
        elif chain in [Chain.BSC, Chain.BSC_TESTNET]:
            if not _pancakeswap_trader:
                raise HTTPException(status_code=503, detail="Trader not initialized")
            
            result = await _pancakeswap_trader.execute_swap(
                token_in=request.token_in,
                token_out=request.token_out,
                amount_in=amount_in_wei,
                slippage_pct=request.slippage_pct,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Automated execution not supported for {request.chain}")
        
        return SwapExecuteResponse(
            success=result.get("status") == "success",
            tx_hash=result.get("tx_hash"),
            status=result.get("status", "unknown"),
            chain=request.chain,
            gas_used=result.get("gas_used"),
            block_number=result.get("block_number"),
        )
        
    except Exception as e:
        logger.error(f"Swap execution error: {e}")
        return SwapExecuteResponse(
            success=False,
            status="failed",
            chain=request.chain,
            error=str(e),
        )


# ============ Sniper Endpoints ============

@router.get("/sniper/config")
async def get_sniper_config():
    """Get current sniper configuration."""
    if not _sniper:
        raise HTTPException(status_code=503, detail="Sniper not initialized")
    
    return {
        "enabled": _sniper.config.enabled,
        "chain": _sniper.config.chain,
        "buy_amount_eth": _sniper.config.buy_amount_eth,
        "max_slippage_pct": _sniper.config.max_slippage_pct,
        "min_liquidity_usd": _sniper.config.min_liquidity_usd,
        "max_buy_tax_pct": _sniper.config.max_buy_tax_pct,
        "max_sell_tax_pct": _sniper.config.max_sell_tax_pct,
        "auto_sell_enabled": _sniper.config.auto_sell_enabled,
        "auto_sell_profit_pct": _sniper.config.auto_sell_profit_pct,
        "auto_sell_loss_pct": _sniper.config.auto_sell_loss_pct,
        "blacklisted_tokens": _sniper.config.blacklisted_tokens,
    }


@router.post("/sniper/config")
async def update_sniper_config(config: SnipeConfigRequest):
    """Update sniper configuration."""
    if not _sniper:
        raise HTTPException(status_code=503, detail="Sniper not initialized")
    
    await _sniper.update_config(config.model_dump())
    
    return {"status": "updated", "config": config.model_dump()}


@router.post("/sniper/start")
async def start_sniper(background_tasks: BackgroundTasks, chains: List[str] = None):
    """Start liquidity monitoring and sniping."""
    if not _liquidity_monitor or not _sniper:
        raise HTTPException(status_code=503, detail="Sniper services not initialized")
    
    if not blockchain_providers.account:
        raise HTTPException(
            status_code=400,
            detail="Backend wallet required for sniping. Set DEX_PRIVATE_KEY."
        )
    
    # Default to testnets
    chain_list = chains or ["ethereum_sepolia", "bsc_testnet"]
    chain_enums = [Chain(c) for c in chain_list]
    
    # Start monitoring in background
    background_tasks.add_task(_liquidity_monitor.start_monitoring, chain_enums)
    
    return {
        "status": "started",
        "monitoring_chains": chain_list,
        "message": "Liquidity monitoring started. New pools will be evaluated for sniping."
    }


@router.post("/sniper/stop")
async def stop_sniper():
    """Stop liquidity monitoring."""
    if not _liquidity_monitor:
        raise HTTPException(status_code=503, detail="Monitor not initialized")
    
    await _liquidity_monitor.stop_monitoring()
    
    return {"status": "stopped"}


@router.get("/sniper/detected-pools")
async def get_detected_pools(
    limit: int = 20,
    chain: Optional[str] = None,
    db=Depends(get_db)
):
    """Get recently detected liquidity pools."""
    query = {}
    if chain:
        query["chain"] = chain
    
    pools = await db.detected_pools.find(
        query,
        {"_id": 0}
    ).sort("detected_at", -1).limit(limit).to_list(limit)
    
    return {"pools": pools, "count": len(pools)}


@router.get("/sniper/executions")
async def get_snipe_executions(
    limit: int = 20,
    status: Optional[str] = None,
    db=Depends(get_db)
):
    """Get snipe execution history."""
    query = {}
    if status:
        query["status"] = status
    
    executions = await db.snipe_executions.find(
        query,
        {"_id": 0}
    ).sort("executed_at", -1).limit(limit).to_list(limit)
    
    return {"executions": executions, "count": len(executions)}


@router.post("/sniper/analyze-token")
async def analyze_token(token_address: str, chain: str):
    """Analyze a token for safety before manual snipe."""
    if not _sniper:
        raise HTTPException(status_code=503, detail="Sniper not initialized")
    
    try:
        chain_enum = Chain(chain)
        analysis = await _sniper.analyzer.analyze_token(token_address, chain_enum)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Token Info ============

@router.get("/tokens/{chain}")
async def get_common_tokens(chain: str):
    """Get common token addresses for a chain."""
    try:
        chain_enum = Chain(chain)
        config = CHAIN_CONFIGS[chain_enum]
        
        if chain_enum in [Chain.SOLANA, Chain.SOLANA_DEVNET]:
            tokens = SOLANA_DEVNET_TOKENS if chain_enum == Chain.SOLANA_DEVNET else SOLANA_TOKENS
            return {"chain": chain, "tokens": tokens}
        
        return {
            "chain": chain,
            "tokens": {
                "WETH": config.weth_address,
                "USDC": config.usdc_address,
                "USDT": config.usdt_address,
            }
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Chain '{chain}' not found")
