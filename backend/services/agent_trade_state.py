"""Agent Trade State Store

Persists per-agent execution state needed for guardrails:
- last open timestamps (for rate limit that survives restarts)
- mapping (symbol,strategy) -> trade_id for deterministic closes

Collection: agent_trade_state
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class AgentTradeStateStore:
    COLLECTION = "agent_trade_state"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def initialize(self) -> None:
        await self.db[self.COLLECTION].create_index("agent_id", unique=True)

    def _key(self, symbol: str, strategy: str) -> str:
        return f"{symbol.upper()}::{strategy.upper()}"

    async def get_state(self, agent_id: str) -> Dict[str, Any]:
        doc = await self.db[self.COLLECTION].find_one({"agent_id": agent_id}, {"_id": 0})
        if doc:
            return doc
        return {"agent_id": agent_id, "positions": {}, "open_events": []}

    async def set_open_trade_id(self, agent_id: str, symbol: str, strategy: str, trade_id: str) -> None:
        key = self._key(symbol, strategy)
        await self.db[self.COLLECTION].update_one(
            {"agent_id": agent_id},
            {"$set": {f"positions.{key}": trade_id}},
            upsert=True,
        )

    async def clear_open_trade_id(self, agent_id: str, symbol: str, strategy: str) -> None:
        key = self._key(symbol, strategy)
        await self.db[self.COLLECTION].update_one(
            {"agent_id": agent_id},
            {"$unset": {f"positions.{key}": ""}},
            upsert=True,
        )

    async def get_open_trade_id(self, agent_id: str, symbol: str, strategy: str) -> Optional[str]:
        key = self._key(symbol, strategy)
        doc = await self.db[self.COLLECTION].find_one({"agent_id": agent_id}, {"_id": 0, f"positions.{key}": 1})
        if not doc:
            return None
        positions = doc.get("positions") or {}
        return positions.get(key)

    async def record_open_event(self, agent_id: str, ts: Optional[datetime] = None) -> None:
        ts = ts or datetime.now(timezone.utc)
        ts_str = ts.isoformat()
        # Keep the list reasonably small (last 50)
        await self.db[self.COLLECTION].update_one(
            {"agent_id": agent_id},
            {"$push": {"open_events": {"$each": [ts_str], "$slice": -50}}},
            upsert=True,
        )

    async def get_open_events_in_window(self, agent_id: str, window_seconds: int) -> List[datetime]:
        doc = await self.db[self.COLLECTION].find_one({"agent_id": agent_id}, {"_id": 0, "open_events": 1})
        raw = (doc or {}).get("open_events") or []
        events: List[datetime] = []
        for s in raw:
            try:
                events.append(datetime.fromisoformat(s))
            except Exception:
                continue

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        return [e for e in events if e >= cutoff]
