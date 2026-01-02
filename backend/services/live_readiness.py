"""Live readiness checklist for BINANCE_LIVE.

We keep readiness strict:
- keys present
- allowed_symbols configured
- limits configured
- kill_switch not active
- testnet smoke passed
- live_cex_enabled must be true AND go-live gate must be GO (handled elsewhere)

This endpoint does NOT attempt to verify permissions like withdrawals disabled.
It returns best-effort warnings.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from services.execution.config import get_trading_config


class LiveReadinessService:
    def __init__(self, db):
        self.db = db

    async def get_status(self) -> Dict[str, Any]:
        cfg = get_trading_config()

        keys_present = bool(os.environ.get("BINANCE_API_KEY") and os.environ.get("BINANCE_API_SECRET"))

        allowed_symbols_configured = bool(cfg.allowed_symbols)
        limits_configured = bool(
            cfg.max_order_notional_usdt
            and cfg.max_trades_per_minute_per_agent
            and cfg.max_trades_per_minute_global
            and cfg.daily_loss_limit_usdt
        )

        kill_switch_ok = not cfg.kill_switch_active

        smoke_doc = await self.db.system_state.find_one({"key": "binance_testnet_smoke"}, {"_id": 0})
        testnet_smoke_passed = bool((smoke_doc or {}).get("passed"))

        ready_for_live = all(
            [
                keys_present,
                allowed_symbols_configured,
                limits_configured,
                kill_switch_ok,
                testnet_smoke_passed,
            ]
        )

        return {
            "keys_present": keys_present,
            "withdrawals_disabled_warning": "Ensure API key has NO withdrawal permissions (manual check).",
            "allowed_symbols_configured": allowed_symbols_configured,
            "limits_configured": limits_configured,
            "kill_switch_ok": kill_switch_ok,
            "testnet_smoke_passed": testnet_smoke_passed,
            "ready_for_live": ready_for_live,
            "current": {
                "trading_mode": cfg.trading_mode.value,
                "live_cex_enabled": cfg.live_cex_enabled,
                "allowed_symbols": cfg.allowed_symbols,
                "max_order_notional_usdt": cfg.max_order_notional_usdt,
                "daily_loss_limit_usdt": cfg.daily_loss_limit_usdt,
            },
        }
