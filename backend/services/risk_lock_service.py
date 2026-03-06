"""
Risk Lock Service — Centralized Daily Loss Lock State Management

Single canonical service responsible for:
  - Activating the daily_loss_lock_active flag when the daily loss threshold
    is breached (by ANY automated path: bodyguard, scheduler, circuit breaker).
  - Clearing the flag (admin resets, midnight auto-reset, paper reset).
  - Computing whether today's daily loss threshold has been exceeded.

Why this exists
---------------
Previously the AI bodyguard paused bots on daily loss breach but never wrote
the ``daily_loss_lock_active`` field.  The trading scheduler did not check that
field.  This created a state where bots were paused but the lock field was
never set — so the auto-reset job, bot-start guard, and diagnostics endpoint
had no data to work with.

This service eliminates that gap.  All paths that previously paused bots due
to daily loss now call ``activate_daily_loss_lock`` so the persisted state
stays in sync with the operational state.

Fields written on ACTIVATE
--------------------------
  daily_loss_lock_active   : True
  daily_loss_day_key       : YYYY-MM-DD (UTC)
  daily_loss_locked_at     : ISO timestamp
  daily_loss_locked_reason : human-readable reason
  daily_loss_pct           : float — observed loss %

Fields written on CLEAR
-----------------------
  daily_loss_lock_active        : False
  daily_loss_lock_reset_at      : ISO timestamp
  daily_loss_lock_reset_by      : caller identifier string
  (unset) daily_loss_locked_at / locked_reason / daily_loss_pct / day_key
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Field name constants (single source of truth)
# ──────────────────────────────────────────────────────────────────────────────

FIELD_ACTIVE = "daily_loss_lock_active"
FIELD_DAY_KEY = "daily_loss_day_key"
FIELD_LOCKED_AT = "daily_loss_locked_at"
FIELD_LOCKED_REASON = "daily_loss_locked_reason"
FIELD_LOSS_PCT = "daily_loss_pct"
FIELD_RESET_AT = "daily_loss_lock_reset_at"
FIELD_RESET_BY = "daily_loss_lock_reset_by"

# ──────────────────────────────────────────────────────────────────────────────
# Default loss threshold (used when user profile cannot be loaded)
# ──────────────────────────────────────────────────────────────────────────────

_PROFILE_THRESHOLDS: dict[str, float] = {
    "safe": 15.0,
    "balanced": 20.0,
    "risky": 25.0,
}
_DEFAULT_THRESHOLD = 20.0  # % of total capital


def _today_utc() -> str:
    """Return today's UTC date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskLockService:
    """
    Atomic read/write service for the daily_loss_lock_active user flag.

    Usage
    -----
    Inject ``db`` at call time (lazy) so this module can be imported at
    module-load without triggering database connections.
    """

    # ── Activate lock ────────────────────────────────────────────────────────

    async def activate_daily_loss_lock(
        self,
        user_id: str,
        reason: str,
        loss_pct: float = 0.0,
        db=None,
    ) -> bool:
        """
        Persist the daily loss lock for ``user_id``.

        Returns True if the lock was newly written (or updated), False on error.

        This is idempotent: if the lock is already active for today it just
        updates the reason/pct but does not create a duplicate.
        """
        if db is None:
            import database as _db
            db = _db

        today = _today_utc()
        now = _now_iso()

        try:
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        FIELD_ACTIVE: True,
                        FIELD_DAY_KEY: today,
                        FIELD_LOCKED_AT: now,
                        FIELD_LOCKED_REASON: reason,
                        FIELD_LOSS_PCT: round(loss_pct, 4),
                    }
                },
            )
            logger.warning(
                "[RiskLock] ACTIVATED for user %s: %s (loss=%.1f%%, day=%s)",
                user_id[:8],
                reason,
                loss_pct,
                today,
            )
            return True
        except Exception as exc:
            logger.error(
                "[RiskLock] Failed to activate lock for user %s: %s",
                user_id[:8],
                exc,
                exc_info=True,
            )
            return False

    # ── Clear lock ───────────────────────────────────────────────────────────

    async def clear_daily_loss_lock(
        self,
        user_id: str,
        cleared_by: str = "system",
        db=None,
    ) -> bool:
        """
        Clear the daily loss lock for ``user_id``.

        ``cleared_by`` should identify the caller, e.g.:
          - "admin:<user_id>"
          - "system:midnight_scheduler"
          - "system:day_boundary"
          - "paper_reset"
        """
        if db is None:
            import database as _db
            db = _db

        now = _now_iso()
        try:
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        FIELD_ACTIVE: False,
                        FIELD_RESET_AT: now,
                        FIELD_RESET_BY: cleared_by,
                    },
                    "$unset": {
                        FIELD_LOCKED_AT: "",
                        FIELD_LOCKED_REASON: "",
                        FIELD_LOSS_PCT: "",
                        FIELD_DAY_KEY: "",
                    },
                },
            )
            logger.info(
                "[RiskLock] CLEARED for user %s by %s",
                user_id[:8],
                cleared_by,
            )
            return True
        except Exception as exc:
            logger.error(
                "[RiskLock] Failed to clear lock for user %s: %s",
                user_id[:8],
                exc,
                exc_info=True,
            )
            return False

    # ── Check current lock state ─────────────────────────────────────────────

    async def is_locked_today(self, user_id: str, db=None) -> Tuple[bool, Optional[str]]:
        """
        Return (is_locked, reason) where *is_locked* is True only if:
          - daily_loss_lock_active is True AND
          - daily_loss_day_key == today's UTC date.

        A lock from a previous day is treated as stale (not active).
        """
        if db is None:
            import database as _db
            db = _db

        today = _today_utc()
        try:
            user = await db.users_collection.find_one(
                {"id": user_id},
                {"_id": 0, FIELD_ACTIVE: 1, FIELD_DAY_KEY: 1, FIELD_LOCKED_REASON: 1},
            )
            if not user:
                return False, None
            if not user.get(FIELD_ACTIVE, False):
                return False, None
            if user.get(FIELD_DAY_KEY, "") != today:
                # Stale lock — treat as not active; background job will clean it
                return False, None
            return True, user.get(FIELD_LOCKED_REASON, "Daily loss limit reached")
        except Exception as exc:
            logger.error("[RiskLock] is_locked_today error for %s: %s", user_id[:8], exc)
            return False, None

    # ── Evaluate whether threshold is breached ───────────────────────────────

    async def evaluate_and_lock_if_breached(
        self,
        user_id: str,
        db=None,
    ) -> Tuple[bool, float, str]:
        """
        Compute today's realized PnL from closed trades.
        If the daily loss % exceeds the user's threshold, activate the lock.

        Returns:
            (breached: bool, loss_pct: float, reason: str)
        """
        if db is None:
            import database as _db
            db = _db

        today = _today_utc()
        try:
            # Get user risk profile for threshold
            user = await db.users_collection.find_one(
                {"id": user_id},
                {"_id": 0, "risk_profile": 1},
            )
            profile = (user or {}).get("risk_profile", "balanced") or "balanced"
            threshold_pct = _PROFILE_THRESHOLDS.get(profile.lower(), _DEFAULT_THRESHOLD)

            # Calculate today's total capital from bots
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0, "current_capital": 1, "initial_capital": 1},
            ).to_list(1000)
            total_capital = sum(b.get("current_capital", b.get("initial_capital", 0)) for b in bots)

            if total_capital <= 0:
                return False, 0.0, ""

            # Calculate today's realized PnL (closed trades only)
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            trades = await db.trades_collection.find(
                {
                    "user_id": user_id,
                    "status": {"$in": ["closed", "completed"]},
                    "timestamp": {"$gte": today_start},
                },
                {"_id": 0, "net_pnl": 1, "profit_loss": 1},
            ).to_list(10000)

            daily_pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)

            if daily_pnl >= 0:
                return False, 0.0, ""

            loss_pct = abs(daily_pnl) / total_capital * 100

            if loss_pct >= threshold_pct:
                reason = (
                    f"Daily loss {loss_pct:.1f}% exceeds {threshold_pct:.0f}% "
                    f"threshold (profile={profile})"
                )
                await self.activate_daily_loss_lock(user_id, reason, loss_pct, db=db)
                return True, loss_pct, reason

            return False, loss_pct, ""

        except Exception as exc:
            logger.error(
                "[RiskLock] evaluate_and_lock_if_breached error for %s: %s",
                user_id[:8],
                exc,
                exc_info=True,
            )
            return False, 0.0, str(exc)


# ── Singleton ─────────────────────────────────────────────────────────────────

risk_lock_service = RiskLockService()
