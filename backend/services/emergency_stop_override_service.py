from datetime import datetime, timezone
from typing import Any, Dict

import database as db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmergencyStopOverrideService:
    """Admin override controls for user emergency stop state."""

    async def _get_doc(self) -> Dict[str, Any]:
        if db.emergency_stop_collection is None:
            return {"id": "admin_overrides", "global_disabled": False, "per_user": {}}
        doc = await db.emergency_stop_collection.find_one({"id": "admin_overrides"}, {"_id": 0})
        if not doc:
            return {"id": "admin_overrides", "global_disabled": False, "per_user": {}}
        doc.setdefault("per_user", {})
        doc.setdefault("global_disabled", False)
        return doc

    async def get_status(self) -> Dict[str, Any]:
        return await self._get_doc()

    async def set_global(self, *, disabled: bool, reason: str, updated_by: str) -> Dict[str, Any]:
        payload = {
            "global_disabled": bool(disabled),
            "global_reason": reason or "",
            "global_updated_by": updated_by,
            "global_updated_at": _now_iso(),
        }
        await db.emergency_stop_collection.update_one(
            {"id": "admin_overrides"},
            {"$set": payload, "$setOnInsert": {"per_user": {}}},
            upsert=True,
        )
        return await self._get_doc()

    async def set_user(self, *, user_id: str, disabled: bool, reason: str, updated_by: str) -> Dict[str, Any]:
        await db.emergency_stop_collection.update_one(
            {"id": "admin_overrides"},
            {
                "$set": {
                    f"per_user.{user_id}": {
                        "disabled": bool(disabled),
                        "reason": reason or "",
                        "updated_by": updated_by,
                        "updated_at": _now_iso(),
                    }
                },
                "$setOnInsert": {"global_disabled": False},
            },
            upsert=True,
        )
        return await self._get_doc()

    async def clear_user(self, user_id: str) -> Dict[str, Any]:
        await db.emergency_stop_collection.update_one(
            {"id": "admin_overrides"},
            {"$unset": {f"per_user.{user_id}": ""}},
            upsert=True,
        )
        return await self._get_doc()

    async def evaluate(self, user_id: str, emergency_stop_active: bool) -> Dict[str, Any]:
        status = await self._get_doc()
        global_disabled = bool(status.get("global_disabled"))
        user_override = (status.get("per_user") or {}).get(user_id) or {}
        user_disabled = bool(user_override.get("disabled"))
        effective_active = bool(emergency_stop_active) and not (global_disabled or user_disabled)
        return {
            "effective_active": effective_active,
            "global_disabled": global_disabled,
            "user_disabled": user_disabled,
            "user_override": user_override,
            "global_reason": status.get("global_reason"),
        }


emergency_stop_override_service = EmergencyStopOverrideService()

