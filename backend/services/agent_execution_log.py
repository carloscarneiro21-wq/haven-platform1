"""Agent Execution Log

Stores visibility events for agent execution attempts (success/blocked/error),
so the Trades Report can explain what failed beyond persisted trades.

Collection: agent_execution_logs
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


class AgentExecutionLogStore:
    COLLECTION = "agent_execution_logs"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def initialize(self) -> None:
        await self.db[self.COLLECTION].create_index([("ts", -1)])
        await self.db[self.COLLECTION].create_index([("agent_id", 1), ("ts", -1)])
        await self.db[self.COLLECTION].create_index([("strategy", 1), ("ts", -1)])

    async def log(
        self,
        *,
        agent_id: str,
        strategy: str,
        symbol: str,
        action: str,  # open|close
        status: str,  # success|blocked|error
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        ts: Optional[datetime] = None,
    ) -> None:
        ts = ts or datetime.now(timezone.utc)
        doc = {
            "ts": ts.isoformat(),
            "agent_id": agent_id,
            "strategy": strategy,
            "symbol": symbol,
            "action": action,
            "status": status,
            "code": code,
            "message": message,
            "details": details or {},
        }
        await self.db[self.COLLECTION].insert_one(doc)
