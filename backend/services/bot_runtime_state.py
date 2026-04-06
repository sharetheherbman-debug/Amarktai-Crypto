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

    async def record_tick(self, bot_id: str, user_id: str) -> None:
        """Record that the scheduler evaluated this bot in the current tick.

        Writes ``last_tick_at`` and ``updated_at`` so that diagnostics
        endpoints always reflect the most recent scheduler activity, even
        when no trade was opened or closed.

        This is intentionally fire-and-forget (best-effort): a failure
        must not interrupt the trading loop.
        """
        collection = self._collection()
        if collection is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        try:
            await collection.update_one(
                {"bot_id": bot_id},
                {
                    "$set": {
                        "last_tick_at": now,
                        "updated_at": now,
                        "user_id": user_id,
                    },
                    "$setOnInsert": {
                        "bot_id": bot_id,
                        "created_at": now,
                        "state": "active",
                    },
                },
                upsert=True,
            )
        except Exception as e:
            logger.debug("record_tick failed for bot %s: %s", bot_id, e)

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

    async def remove_for_user(self, user_id: str) -> int:
        """Delete all runtime-state rows for *user_id*.

        Called by ``perform_paper_reset`` to guarantee that every reset
        leaves zero stale runtime-state rows regardless of whether the rows
        still carry a now-deleted bot_id.

        Returns the number of rows deleted.
        """
        collection = self._collection()
        if collection is None:
            return 0
        result = await collection.delete_many({"user_id": user_id})
        return result.deleted_count

    async def reconcile_with_bot_doc(self, bot_id: str, bot_doc: Dict) -> Dict:
        """Reconcile runtime state against the canonical bot document.

        The bot document in the ``bots`` collection is the single source of
        truth for bot lifecycle state.  If the runtime-state store disagrees
        (e.g. it says ``active`` while the bot doc says ``paused`` or
        ``deleted``), this method overwrites the runtime row to match the bot
        document so that the scheduler and dashboard always agree.

        Returns the (potentially updated) runtime-state row.
        """
        doc_status = _normalize_state(bot_doc.get("status", ""))
        user_id = bot_doc.get("user_id", "")

        # Deleted bots must never have an active runtime-state row.
        if doc_status == "deleted" or bot_doc.get("deleted_at"):
            await self.remove(bot_id)
            logger.info(
                "reconcile_with_bot_doc: removed runtime state for deleted bot %s", bot_id
            )
            return {}

        existing = await self.get_state(bot_id)
        if existing is None:
            # No row yet — bootstrap from the bot document.
            return await self.ensure_state(bot_doc)

        existing_state = existing.get("state", "")
        if existing_state == doc_status:
            return existing  # already in sync

        logger.warning(
            "reconcile_with_bot_doc: state drift for bot %s — "
            "runtime=%s bot_doc=%s → overwriting with bot_doc truth",
            bot_id, existing_state, doc_status,
        )
        return await self.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state=doc_status,
            reason=bot_doc.get("pause_reason") or bot_doc.get("stop_reason"),
            source="reconcile",
        )


bot_runtime_state = BotRuntimeStateStore()
