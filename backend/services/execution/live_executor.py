"""Live Executor - Real trading execution (BLOCKED BY DEFAULT).

⚠️  WARNING: This executor can execute REAL trades with REAL money.

This is a STRUCTURE-ONLY implementation.
Actual exchange integration is NOT yet implemented.

Safety Validations:
1. TRADING_MODE must be 'live'
2. LIVE_CEX_ENABLED or LIVE_DEX_ENABLED must be true
3. GO-LIVE gate must be 'GO'
4. API keys must be present
5. User role must be authorized

If ANY validation fails → Execution BLOCKED.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class LiveTradeExecutor:
    """Live trading executor.
    
    ⚠️  BLOCKED BY DEFAULT - Structure only.
    
    This executor will:
    1. Validate all safety requirements
    2. Log all execution attempts
    3. Block if ANY requirement is not met
    
    Future implementation will include:
    - Binance API integration
    - Kraken API integration  
    - DEX SDK integration (Web3, Jupiter)
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, go_live_gate=None):
        self.db = db
        self.go_live_gate = go_live_gate
        self._execution_count = 0
        self._blocked_count = 0
        
        logger.warning("⚠️  LiveTradeExecutor initialized - Exchange integration NOT implemented")
    
    async def execute(self, request) -> "TradeResult":
        """Execute a live trade.
        
        Currently ALWAYS returns BLOCKED because exchange integration
        is not yet implemented.
        """
        from services.execution.router import TradeResult
        from services.execution.config import get_trading_config, TradingMode
        
        config = get_trading_config()
        
        result = TradeResult(
            request_id=request.request_id,
            execution_id=str(uuid.uuid4()),
            mode="live",
            symbol=request.symbol,
            side=request.side,
        )
        
        # Log the attempt
        await self._log_execution_attempt(request, "PENDING")
        
        # Validate requirements
        validation_error = await self._validate_requirements(request, config)
        if validation_error:
            result.success = False
            result.status = "BLOCKED"
            result.blocked_reason = validation_error
            self._blocked_count += 1
            await self._log_execution_attempt(request, "BLOCKED", validation_error)
            logger.warning(f"Live execution BLOCKED: {validation_error}")
            return result
        
        # ═══════════════════════════════════════════════════════════════
        # ⚠️  EXCHANGE INTEGRATION NOT IMPLEMENTED
        # ═══════════════════════════════════════════════════════════════
        # When implemented, this is where we would:
        # 1. Select appropriate exchange client (Binance, Kraken, DEX)
        # 2. Validate API keys are present
        # 3. Check account balance
        # 4. Submit order to exchange
        # 5. Wait for fill confirmation
        # 6. Store execution result
        # ═══════════════════════════════════════════════════════════════
        
        # For now, ALWAYS block with explanation
        result.success = False
        result.status = "BLOCKED"
        result.blocked_reason = "Exchange integration not implemented - LIVE execution unavailable"
        self._blocked_count += 1
        
        await self._log_execution_attempt(
            request, 
            "BLOCKED", 
            "Exchange integration pending"
        )
        
        logger.warning(
            f"Live execution request received but BLOCKED: "
            f"{request.side} {request.amount} {request.symbol} - Exchange not integrated"
        )
        
        return result
    
    async def _validate_requirements(self, request, config) -> Optional[str]:
        """Validate all requirements for live execution."""
        # 1. Trading mode
        if config.trading_mode != TradingMode.LIVE:
            return f"TRADING_MODE is '{config.trading_mode.value}', not 'live'"
        
        # 2. Live flags
        is_cex = request.venue.lower() in ["binance", "kraken", "okx", "bybit"]
        is_dex = request.venue.lower() in ["uniswap", "pancakeswap", "jupiter"]
        
        if is_cex and not config.live_cex_enabled:
            return "LIVE_CEX_ENABLED is false"
        
        if is_dex and not config.live_dex_enabled:
            return "LIVE_DEX_ENABLED is false"
        
        # 3. Kill switch
        if config.kill_switch_active:
            return f"Kill switch active: {config.kill_switch_reason}"
        
        # 4. GO-LIVE gate
        if self.go_live_gate:
            try:
                gate_status = await self.go_live_gate.get_current_status()
                if gate_status.get("decision") != "GO":
                    return f"GO-LIVE gate is NO-GO"
            except Exception as e:
                return f"GO-LIVE gate check failed: {e}"
        else:
            return "GO-LIVE gate not configured"
        
        # 5. API keys (would check here when implemented)
        # if is_cex:
        #     if not os.environ.get(f"{request.venue.upper()}_API_KEY"):
        #         return f"API key not configured for {request.venue}"
        
        return None  # All validations passed
    
    async def _log_execution_attempt(self, request, status: str, reason: str = ""):
        """Log execution attempt for audit."""
        try:
            doc = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "agent_type": request.agent_type,
                "symbol": request.symbol,
                "side": request.side,
                "amount": request.amount,
                "venue": request.venue,
                "status": status,
                "reason": reason,
                "mode": "live",
            }
            await self.db.live_execution_attempts.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to log execution attempt: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            "executor": "LiveTradeExecutor",
            "status": "NOT_IMPLEMENTED",
            "exchange_integration": False,
            "execution_count": self._execution_count,
            "blocked_count": self._blocked_count,
            "warning": "Exchange integration pending - all live requests will be BLOCKED",
        }


# Import TradingMode for validation
from services.execution.config import TradingMode
