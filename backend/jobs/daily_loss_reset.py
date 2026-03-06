"""
Daily Loss Lock Auto-Reset Job

Automatically clears expired daily_loss_lock_active flags at UTC midnight.

A daily loss lock is considered EXPIRED when:
  - daily_loss_lock_active is True AND
  - daily_loss_day_key (YYYY-MM-DD UTC) does not match today's UTC date.

This runs:
1. Once at server startup (clear any locks left over from previous days).
2. Continuously in the background — wakes at 00:00:01 UTC each day to clear
   stale locks for all users.

This preserves the lock WITHIN the same UTC day (the protection is real and
intentional) but reliably releases it when a new trading day begins.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_FIELD_ACTIVE = "daily_loss_lock_active"
_FIELD_DAY_KEY = "daily_loss_day_key"

RESET_FIELDS = {
    _FIELD_ACTIVE: False,
    "daily_loss_lock_reset_at": None,  # set dynamically
    "daily_loss_lock_reset_by": "system:midnight_scheduler",
}

UNSET_FIELDS = {
    "daily_loss_locked_at": "",
    "daily_loss_locked_reason": "",
    "daily_loss_pct": "",
    _FIELD_DAY_KEY: "",
}


def _today_key() -> str:
    """Return today's UTC date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def reset_stale_daily_loss_locks(db) -> dict:
    """
    Find all users whose daily_loss_lock_active is True but whose
    daily_loss_day_key is NOT today's UTC date, then clear their lock.

    Returns a dict with counts for observability.
    """
    today = _today_key()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # Find users with an active lock that is not from today
        stale_users = await db.users_collection.find(
            {
                _FIELD_ACTIVE: True,
                _FIELD_DAY_KEY: {"$exists": True, "$ne": today, "$ne": ""},
            },
            {"_id": 0, "id": 1, _FIELD_DAY_KEY: 1},
        ).to_list(1000)

        # Also catch locks with no day_key at all (legacy / corrupt state)
        legacy_locked = await db.users_collection.find(
            {
                _FIELD_ACTIVE: True,
                "$or": [
                    {_FIELD_DAY_KEY: {"$exists": False}},
                    {_FIELD_DAY_KEY: ""},
                    {_FIELD_DAY_KEY: None},
                ],
            },
            {"_id": 0, "id": 1},
        ).to_list(1000)

        all_users = stale_users + legacy_locked
        if not all_users:
            logger.debug("[DailyLossReset] No stale locks found (today=%s).", today)
            return {"cleared": 0, "today": today}

        user_ids = [u["id"] for u in all_users if u.get("id")]
        if not user_ids:
            return {"cleared": 0, "today": today}

        result = await db.users_collection.update_many(
            {"id": {"$in": user_ids}},
            {
                "$set": {
                    _FIELD_ACTIVE: False,
                    "daily_loss_lock_reset_at": now_iso,
                    "daily_loss_lock_reset_by": "system:midnight_scheduler",
                },
                "$unset": {k: "" for k in UNSET_FIELDS},
            },
        )

        count = result.modified_count
        logger.info(
            "[DailyLossReset] Cleared %d stale daily_loss_lock(s). day_keys: %s",
            count,
            [u.get(_FIELD_DAY_KEY, "<none>") for u in stale_users],
        )
        return {"cleared": count, "today": today, "user_ids": user_ids}

    except Exception as exc:
        logger.error("[DailyLossReset] Error clearing stale locks: %s", exc, exc_info=True)
        return {"cleared": 0, "error": str(exc), "today": today}


def _seconds_until_next_midnight_utc() -> float:
    """Return number of seconds until 00:00:01 UTC tomorrow."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=1, microsecond=0
    )
    return max(0.0, (tomorrow - now).total_seconds())


async def run_daily_loss_reset_loop(db) -> None:
    """
    Continuous background coroutine that:
    1. Runs an immediate stale-lock clearance on startup.
    2. Then sleeps until 00:00:01 UTC and repeats every 24 h.
    """
    logger.info("[DailyLossReset] Background loop started.")

    # Immediate pass — clear any locks left over from yesterday
    await reset_stale_daily_loss_locks(db)

    while True:
        sleep_s = _seconds_until_next_midnight_utc()
        logger.info(
            "[DailyLossReset] Next midnight reset in %.0f seconds (%.1f hours).",
            sleep_s,
            sleep_s / 3600,
        )
        await asyncio.sleep(sleep_s)
        result = await reset_stale_daily_loss_locks(db)
        logger.info("[DailyLossReset] Midnight pass complete: %s", result)
