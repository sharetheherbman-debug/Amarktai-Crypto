"""
Bot Runtime State Store
Single source of truth for bot runtime status (active/paused/stopped).
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List
import logging

import database as db

logger = logging.getLogger(__name__)


def _normalize_state(status: str) -> str:
    status = (status or "").lower()
    if status in {"active", "running"}:
        return "active"
    if status in {"paused", "paused_ready"}:
        return "paused"
    if status in {"stopped", "stop"}:
        return "stopped"
    return status or "unknown"


class BotRuntimeStateStore:
    def __init__(self):
        self._lock = asyncio.Lock()

    def _collection(self):
        return db.bot_runtime_state_collection

    async def get_state(self, bot_id: str) -> Optional[Dict]:
        collection = self._collection()
        if collection is None:
            return None
        return await collection.find_one({"bot_id": bot_id}, {"_id": 0})

    async def list_states(self, user_id: str) -> List[Dict]:
        collection = self._collection()
        if collection is None:
            return []
        return await collection.find({"user_id": user_id}, {"_id": 0}).to_list(1000)

    async def set_state(
        self,
        bot_id: str,
        user_id: str,
        state: str,
        reason: Optional[str] = None,
        source: str = "system",
        details: Optional[Dict] = None,
    ) -> Dict:
        collection = self._collection()
        if collection is None:
            logger.warning("Bot runtime store unavailable; skipping state write")
            return {
                "bot_id": bot_id,
                "user_id": user_id,
                "state": _normalize_state(state),
                "reason": reason,
                "source": source,
            }

        async with self._lock:
            normalized = _normalize_state(state)
            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "bot_id": bot_id,
                "user_id": user_id,
                "state": normalized,
                "reason": reason,
                "source": source,
                "updated_at": now,
            }
            if details:
                payload["details"] = details
            await collection.update_one(
                {"bot_id": bot_id},
                {"$set": payload, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            return payload

    async def ensure_state(self, bot: Dict) -> Dict:
        bot_id = bot.get("id")
        user_id = bot.get("user_id")
        if not bot_id or not user_id:
            return {}
        existing = await self.get_state(bot_id)
        if existing:
            return existing
        status = _normalize_state(bot.get("status"))
        return await self.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state=status,
            reason=bot.get("pause_reason") or bot.get("stop_reason"),
            source="bootstrap",
        )

    async def remove(self, bot_id: str) -> None:
        collection = self._collection()
        if collection is None:
            return
        await collection.delete_one({"bot_id": bot_id})


bot_runtime_state = BotRuntimeStateStore()
