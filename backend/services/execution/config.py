"""Trading Mode Configuration - Central configuration for HAVEN execution.

🔒 CORE PRINCIPLES:
1. PAPER MODE is the DEFAULT - always safe
2. LIVE execution requires explicit flags + GO-LIVE gate
3. Configuration is loaded from environment variables
4. All agents inherit from this configuration
"""

import os
import logging
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TradingMode(str, Enum):
    """Trading execution mode."""
    PAPER = "paper"                 # Simulated execution - DEFAULT
    BINANCE_TESTNET = "binance_testnet"  # Real spot testnet execution
    BINANCE_LIVE = "binance_live"        # Real spot live execution (LOCKED)


class TradingConfig(BaseModel):
    """Global trading configuration.
    
    Environment Variables:
    - TRADING_MODE: 'paper' (default) or 'live'
    - LIVE_CEX_ENABLED: 'true' or 'false' (default: false)
    - LIVE_DEX_ENABLED: 'true' or 'false' (default: false)
    
    RULE: If TRADING_MODE=paper, NOTHING executes live,
    even if other flags are accidentally enabled.
    """
    
    # Core mode
    trading_mode: TradingMode = TradingMode.PAPER

    # Live execution flags
    live_cex_enabled: bool = False
    live_dex_enabled: bool = False  # legacy/compat

    # Guardrails
    allowed_symbols: list[str] = Field(default_factory=list)
    max_order_notional_usdt: float = 10.0
    max_trades_per_minute_per_agent: int = 2
    max_trades_per_minute_global: int = 30
    max_open_positions_per_agent_symbol: int = 1
    daily_loss_limit_usdt: float = 20.0

    # Legacy safety limits (kept for compatibility with older code paths)
    max_position_size_eur: float = 500.0
    daily_loss_limit_eur: float = 200.0
    max_daily_trades: int = 50
    
    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    kill_switch_activated_at: Optional[datetime] = None
    
    # Dry run (simulate live without actual execution)
    dry_run: bool = True
    
    # Loaded timestamp
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @classmethod
    def from_env(cls) -> "TradingConfig":
        """Load configuration from environment variables."""
        # Parse trading mode
        mode_str = os.environ.get("TRADING_MODE", "paper").lower()
        trading_mode = TradingMode.PAPER  # Default
        if mode_str == "binance_testnet":
            trading_mode = TradingMode.BINANCE_TESTNET
        elif mode_str == "binance_live":
            trading_mode = TradingMode.BINANCE_LIVE
        
        # Parse boolean flags
        def parse_bool(key: str, default: bool = False) -> bool:
            val = os.environ.get(key, "").lower()
            return val in ("true", "1", "yes", "on")
        
        live_cex = parse_bool("LIVE_CEX_ENABLED", False)
        live_dex = parse_bool("LIVE_DEX_ENABLED", False)

        # Guardrails
        allowed_symbols_raw = os.environ.get("ALLOWED_SYMBOLS", "")
        allowed_symbols = [s.strip().upper() for s in allowed_symbols_raw.split(",") if s.strip()]

        max_order_notional_usdt = float(os.environ.get("MAX_ORDER_NOTIONAL_USDT", "10"))
        max_tpm_agent = int(os.environ.get("MAX_TRADES_PER_MINUTE_PER_AGENT", "2"))
        max_tpm_global = int(os.environ.get("MAX_TRADES_PER_MINUTE_GLOBAL", "30"))
        max_open_positions = int(os.environ.get("MAX_OPEN_POSITIONS_PER_AGENT_SYMBOL", "1"))
        daily_loss_usdt = float(os.environ.get("DAILY_LOSS_LIMIT_USDT", "20"))

        # Legacy safety limits
        max_position = float(os.environ.get("MAX_POSITION_SIZE_EUR", "500"))
        daily_loss = float(os.environ.get("DAILY_LOSS_LIMIT_EUR", "200"))
        max_trades = int(os.environ.get("MAX_DAILY_TRADES", "50"))

        config = cls(
            trading_mode=trading_mode,
            live_cex_enabled=live_cex,
            live_dex_enabled=live_dex,
            allowed_symbols=allowed_symbols,
            max_order_notional_usdt=max_order_notional_usdt,
            max_trades_per_minute_per_agent=max_tpm_agent,
            max_trades_per_minute_global=max_tpm_global,
            max_open_positions_per_agent_symbol=max_open_positions,
            daily_loss_limit_usdt=daily_loss_usdt,
            max_position_size_eur=max_position,
            daily_loss_limit_eur=daily_loss,
            max_daily_trades=max_trades,
        )
        
        # Log configuration
        logger.info(f"Trading Config loaded: mode={config.trading_mode.value}, "
                    f"live_cex={config.live_cex_enabled}")
        
        # Safety warning if non-paper mode
        if config.trading_mode != TradingMode.PAPER:
            logger.warning(f"⚠️  TRADING_MODE={config.trading_mode.value} - Real execution may occur!")
            if config.live_cex_enabled:
                logger.warning("⚠️  LIVE_CEX_ENABLED=true - CEX trading enabled!")
        
        return config
    
    def is_live_execution_allowed(self) -> bool:
        """Check if live execution is currently allowed.
        
        Returns True only if:
        1. TRADING_MODE = live
        2. LIVE_CEX_ENABLED = true OR LIVE_DEX_ENABLED = true
        3. Kill switch is NOT active
        """
        if self.kill_switch_active:
            return False
        
        if self.trading_mode == TradingMode.PAPER:
            return False

        # At least one live flag must be enabled
        return self.live_cex_enabled or self.live_dex_enabled
    
    def activate_kill_switch(self, reason: str) -> None:
        """Activate emergency kill switch."""
        self.kill_switch_active = True
        self.kill_switch_reason = reason
        self.kill_switch_activated_at = datetime.now(timezone.utc)
        logger.critical(f"🛑 KILL SWITCH ACTIVATED: {reason}")
    
    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch (requires manual intervention)."""
        self.kill_switch_active = False
        self.kill_switch_reason = None
        self.kill_switch_activated_at = None
        logger.warning("Kill switch deactivated")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current configuration status."""
        return {
            "trading_mode": self.trading_mode.value,
            "live_cex_enabled": self.live_cex_enabled,
            "live_dex_enabled": self.live_dex_enabled,
            "allowed_symbols": self.allowed_symbols,
            "max_order_notional_usdt": self.max_order_notional_usdt,
            "daily_loss_limit_usdt": self.daily_loss_limit_usdt,
            "is_live_allowed": self.is_live_execution_allowed(),
            "kill_switch": {
                "active": self.kill_switch_active,
                "reason": self.kill_switch_reason,
                "activated_at": self.kill_switch_activated_at.isoformat() if self.kill_switch_activated_at else None,
            },
            "safety_limits": {
                "max_position_size_eur": self.max_position_size_eur,
                "daily_loss_limit_eur": self.daily_loss_limit_eur,
                "max_daily_trades": self.max_daily_trades,
            },
            "dry_run": self.dry_run,
            "loaded_at": self.loaded_at.isoformat(),
        }


# Global singleton
_trading_config: Optional[TradingConfig] = None


def get_trading_config() -> TradingConfig:
    """Get global trading configuration singleton."""
    global _trading_config
    if _trading_config is None:
        _trading_config = TradingConfig.from_env()
    return _trading_config


def reload_trading_config() -> TradingConfig:
    """Reload configuration from environment."""
    global _trading_config
    _trading_config = TradingConfig.from_env()
    return _trading_config
