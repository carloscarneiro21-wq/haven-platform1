"""Token sniping engine for detecting and executing on new liquidity pools."""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from web3 import Web3

from .providers import BlockchainProviders, Chain, CHAIN_CONFIGS
from .uniswap import UniswapV3Trader
from .pancakeswap import PancakeSwapTrader

logger = logging.getLogger(__name__)


class SnipeStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class SnipeConfig:
    """Configuration for token sniping."""
    enabled: bool = False
    chain: str = "ethereum_sepolia"
    buy_amount_eth: float = 0.01  # Amount in native token to spend
    max_slippage_pct: float = 10.0
    min_liquidity_usd: float = 1000.0
    max_buy_tax_pct: float = 10.0
    max_sell_tax_pct: float = 10.0
    auto_sell_enabled: bool = False
    auto_sell_profit_pct: float = 100.0  # 2x
    auto_sell_loss_pct: float = 50.0  # Stop loss at -50%
    blacklisted_tokens: List[str] = field(default_factory=list)
    whitelisted_creators: List[str] = field(default_factory=list)


@dataclass
class DetectedPool:
    """Newly detected liquidity pool."""
    chain: str
    pool_address: str
    token_address: str
    paired_token: str  # Usually WETH/WBNB
    liquidity_amount: float
    tx_hash: str
    block_number: int
    detected_at: datetime
    creator_address: Optional[str] = None
    status: SnipeStatus = SnipeStatus.PENDING
    analysis: Optional[Dict] = None


class TokenAnalyzer:
    """Analyze tokens for safety before sniping."""
    
    def __init__(self, providers: BlockchainProviders):
        self.providers = providers
    
    async def analyze_token(
        self,
        token_address: str,
        chain: Chain
    ) -> Dict[str, Any]:
        """Perform safety analysis on token."""
        web3 = self.providers.get_provider(chain)
        
        result = {
            "token_address": token_address,
            "chain": chain.value,
            "is_safe": True,
            "warnings": [],
            "risk_score": 0,  # 0-100, higher = more risky
        }
        
        try:
            # Check if contract exists
            code = web3.eth.get_code(Web3.to_checksum_address(token_address))
            if code == b'' or code == b'0x':
                result["is_safe"] = False
                result["warnings"].append("No contract code found")
                result["risk_score"] = 100
                return result
            
            # Basic ERC20 checks
            erc20_abi = [
                {"constant": True, "inputs": [], "name": "name", "outputs": [{"type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "owner", "outputs": [{"type": "address"}], "type": "function"},
            ]
            
            contract = web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=erc20_abi
            )
            
            try:
                result["name"] = contract.functions.name().call()
                result["symbol"] = contract.functions.symbol().call()
                result["total_supply"] = contract.functions.totalSupply().call()
                result["decimals"] = contract.functions.decimals().call()
            except Exception as e:
                result["warnings"].append(f"Basic ERC20 calls failed: {e}")
                result["risk_score"] += 20
            
            # Check for owner (potential rug pull risk)
            try:
                owner = contract.functions.owner().call()
                if owner != "0x0000000000000000000000000000000000000000":
                    result["owner"] = owner
                    result["warnings"].append("Token has active owner (centralization risk)")
                    result["risk_score"] += 10
            except Exception:
                pass  # No owner function is actually good
            
            # Honeypot simulation would go here
            # In production, you'd simulate a buy+sell to detect honeypots
            
            # Contract age check
            # Newer contracts are riskier
            
            # Final risk assessment
            if result["risk_score"] >= 50:
                result["is_safe"] = False
                result["warnings"].append("High risk score - proceed with caution")
            
        except Exception as e:
            logger.error(f"Token analysis failed: {e}")
            result["is_safe"] = False
            result["warnings"].append(f"Analysis error: {e}")
            result["risk_score"] = 100
        
        return result


class LiquidityMonitor:
    """Monitor DEX factories for new liquidity pool creation."""
    
    # Uniswap V2 Factory - PoolCreated event
    UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    PAIR_CREATED_TOPIC = Web3.keccak(text="PairCreated(address,address,address,uint256)").hex()
    
    # PancakeSwap Factory
    PANCAKESWAP_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    
    def __init__(
        self,
        providers: BlockchainProviders,
        db,  # MongoDB database
        on_pool_detected: Optional[Callable] = None
    ):
        self.providers = providers
        self.db = db
        self.on_pool_detected = on_pool_detected
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    async def start_monitoring(self, chains: List[Chain]):
        """Start monitoring specified chains for new pools."""
        self._running = True
        
        for chain in chains:
            if chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA]:
                task = asyncio.create_task(self._monitor_uniswap(chain))
                self._tasks.append(task)
            elif chain in [Chain.BSC, Chain.BSC_TESTNET]:
                task = asyncio.create_task(self._monitor_pancakeswap(chain))
                self._tasks.append(task)
        
        logger.info(f"Started monitoring {len(chains)} chains for new pools")
    
    async def stop_monitoring(self):
        """Stop all monitoring tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Stopped pool monitoring")
    
    async def _monitor_uniswap(self, chain: Chain):
        """Monitor Uniswap V2/V3 for new pairs."""
        web3 = self.providers.get_provider(chain)
        config = CHAIN_CONFIGS[chain]
        
        # Use Uniswap V3 Factory for supported chains
        factory_address = config.uniswap_v3_factory or self.UNISWAP_V2_FACTORY
        
        logger.info(f"Monitoring Uniswap pools on {config.name}")
        
        last_block = web3.eth.block_number
        
        while self._running:
            try:
                current_block = web3.eth.block_number
                
                if current_block > last_block:
                    # Get logs for new blocks
                    logs = web3.eth.get_logs({
                        'fromBlock': last_block + 1,
                        'toBlock': current_block,
                        'address': Web3.to_checksum_address(factory_address),
                    })
                    
                    for log in logs:
                        await self._process_pool_log(log, chain, "uniswap")
                    
                    last_block = current_block
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Uniswap monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _monitor_pancakeswap(self, chain: Chain):
        """Monitor PancakeSwap for new pairs."""
        web3 = self.providers.get_provider(chain)
        config = CHAIN_CONFIGS[chain]
        
        factory_address = config.pancakeswap_router  # Would need factory address
        
        logger.info(f"Monitoring PancakeSwap pools on {config.name}")
        
        last_block = web3.eth.block_number
        
        while self._running:
            try:
                current_block = web3.eth.block_number
                
                if current_block > last_block:
                    # Similar log fetching logic
                    last_block = current_block
                
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"PancakeSwap monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _process_pool_log(self, log: Dict, chain: Chain, dex: str):
        """Process detected pool creation log."""
        try:
            pool = DetectedPool(
                chain=chain.value,
                pool_address=log.get('address', ''),
                token_address="",  # Would parse from log data
                paired_token=CHAIN_CONFIGS[chain].weth_address or "",
                liquidity_amount=0,
                tx_hash=log.get('transactionHash', b'').hex() if isinstance(log.get('transactionHash'), bytes) else str(log.get('transactionHash', '')),
                block_number=log.get('blockNumber', 0),
                detected_at=datetime.now(timezone.utc),
            )
            
            # Store in database
            await self.db.detected_pools.insert_one({
                **pool.__dict__,
                "detected_at": pool.detected_at.isoformat(),
                "dex": dex,
            })
            
            # Trigger callback
            if self.on_pool_detected:
                await self.on_pool_detected(pool)
            
            logger.info(f"New pool detected on {chain.value}: {pool.pool_address}")
            
        except Exception as e:
            logger.error(f"Failed to process pool log: {e}")


class TokenSniper:
    """Execute snipe trades on detected pools."""
    
    def __init__(
        self,
        providers: BlockchainProviders,
        db,
        config: Optional[SnipeConfig] = None
    ):
        self.providers = providers
        self.db = db
        self.config = config or SnipeConfig()
        self.analyzer = TokenAnalyzer(providers)
        
        # Initialize traders
        self._uniswap_trader: Optional[UniswapV3Trader] = None
        self._pancakeswap_trader: Optional[PancakeSwapTrader] = None
    
    def get_trader(self, chain: Chain):
        """Get appropriate trader for chain."""
        if chain in [Chain.ETHEREUM, Chain.ETHEREUM_SEPOLIA]:
            if not self._uniswap_trader:
                self._uniswap_trader = UniswapV3Trader(self.providers, chain)
            return self._uniswap_trader
        elif chain in [Chain.BSC, Chain.BSC_TESTNET]:
            if not self._pancakeswap_trader:
                self._pancakeswap_trader = PancakeSwapTrader(
                    self.providers,
                    testnet=(chain == Chain.BSC_TESTNET)
                )
            return self._pancakeswap_trader
        else:
            raise ValueError(f"No trader available for {chain}")
    
    async def evaluate_snipe(
        self,
        pool: DetectedPool
    ) -> Dict[str, Any]:
        """Evaluate if a pool should be sniped."""
        result = {
            "pool_address": pool.pool_address,
            "should_snipe": False,
            "reason": "",
            "analysis": None,
        }
        
        # Check if sniping is enabled
        if not self.config.enabled:
            result["reason"] = "Sniping disabled"
            return result
        
        # Check blacklist
        if pool.token_address.lower() in [t.lower() for t in self.config.blacklisted_tokens]:
            result["reason"] = "Token blacklisted"
            return result
        
        # Check minimum liquidity
        if pool.liquidity_amount < self.config.min_liquidity_usd:
            result["reason"] = f"Liquidity too low: ${pool.liquidity_amount}"
            return result
        
        # Analyze token
        chain = Chain(pool.chain)
        analysis = await self.analyzer.analyze_token(pool.token_address, chain)
        result["analysis"] = analysis
        
        if not analysis.get("is_safe", False):
            result["reason"] = f"Token failed safety check: {analysis.get('warnings', [])}"
            return result
        
        # All checks passed
        result["should_snipe"] = True
        result["reason"] = "All checks passed"
        
        return result
    
    async def execute_snipe(
        self,
        pool: DetectedPool,
        force: bool = False
    ) -> Dict[str, Any]:
        """Execute snipe trade on pool."""
        result = {
            "pool_address": pool.pool_address,
            "status": SnipeStatus.PENDING.value,
            "tx_hash": None,
            "error": None,
        }
        
        try:
            # Evaluate first (unless forced)
            if not force:
                evaluation = await self.evaluate_snipe(pool)
                if not evaluation.get("should_snipe"):
                    result["status"] = SnipeStatus.REJECTED.value
                    result["error"] = evaluation.get("reason")
                    return result
            
            result["status"] = SnipeStatus.EXECUTING.value
            
            # Get trader for chain
            chain = Chain(pool.chain)
            trader = self.get_trader(chain)
            config = CHAIN_CONFIGS[chain]
            
            # Calculate buy amount in wei
            buy_amount = Web3.to_wei(self.config.buy_amount_eth, 'ether')
            
            # Execute swap
            swap_result = await trader.execute_swap(
                token_in=config.weth_address,  # Buy with native token
                token_out=pool.token_address,
                amount_in=buy_amount,
                slippage_pct=self.config.max_slippage_pct
            )
            
            result["tx_hash"] = swap_result.get("tx_hash")
            result["status"] = SnipeStatus.SUCCESS.value if swap_result.get("status") == "success" else SnipeStatus.FAILED.value
            result["swap_result"] = swap_result
            
            # Log to database
            await self.db.snipe_executions.insert_one({
                "pool_address": pool.pool_address,
                "token_address": pool.token_address,
                "chain": pool.chain,
                "buy_amount": str(buy_amount),
                "tx_hash": result["tx_hash"],
                "status": result["status"],
                "executed_at": datetime.now(timezone.utc).isoformat(),
            })
            
        except Exception as e:
            logger.error(f"Snipe execution failed: {e}")
            result["status"] = SnipeStatus.FAILED.value
            result["error"] = str(e)
        
        return result
    
    async def update_config(self, new_config: Dict[str, Any]):
        """Update snipe configuration."""
        for key, value in new_config.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Save to database
        await self.db.snipe_configs.update_one(
            {"user_id": "system"},
            {"$set": {**self.config.__dict__, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
