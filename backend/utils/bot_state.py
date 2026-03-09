"""
Bot state helpers for consistent status flags across endpoints.
"""

from typing import Dict, List, Tuple


# Canonical bot states
BOT_STATE_ACTIVE = "active"
BOT_STATE_PAUSED = "paused"
BOT_STATE_TRAINING = "training"
BOT_STATE_QUARANTINE = "quarantine"
BOT_STATE_STOPPED = "stopped"


def _has_trading_mode(bot: Dict) -> bool:
    """Return True if the bot has any trading mode configured."""
    return bool(
        bot.get("trading_mode")
        or bot.get("mode")
        or bot.get("is_paper")
        or bot.get("is_live")
    )


def _compute_eligible_to_trade(
    bot: Dict, active: bool, paused: bool, stopped: bool, deleted: bool
) -> Tuple[bool, List[str]]:
    """Compute eligible_to_trade boolean and reasons list.

    A bot is eligible to trade when:
    - It is active (not paused, stopped, deleted, or quarantined)
    - It is not locked by daily-loss lock
    - It is not in a retraining/quarantine period
    - It has a valid trading_mode

    Returns:
        (eligible: bool, reasons: List[str])
    """
    reasons: List[str] = []

    if deleted:
        reasons.append("bot_deleted")
    if stopped:
        reasons.append("bot_stopped")
    if paused:
        reasons.append("bot_paused")
    if bot.get("quarantine_until") or bot.get("retraining_until"):
        reasons.append("bot_quarantined")
    if bot.get("daily_loss_lock_active"):
        reasons.append("daily_loss_lock")
    if bot.get("circuit_breaker_active"):
        reasons.append("circuit_breaker_active")
    if not _has_trading_mode(bot):
        reasons.append("no_trading_mode")

    eligible = active and not reasons
    return eligible, reasons


def normalize_bot_state(bot: Dict) -> Dict:
    """Return bot payload with consistent flags for status and deletion.

    The canonical bot ``status`` field is the single source of truth for
    whether a bot is active, paused, or stopped.  The ``paused_by_system``
    and ``paused_by_user`` flags are supplementary metadata explaining *why*
    the bot was paused — they must NOT override an ``active`` status, because
    the resume/restart endpoints clear these flags at the same time as they set
    ``status = 'active'``.  Treating them as independent pause triggers was
    causing bots to appear ineligible even after a successful resume.
    """
    status = bot.get("status", "unknown")
    deleted = bool(
        status == "deleted"
        or bot.get("deleted")
        or bot.get("is_deleted")
        or bot.get("deleted_at")
    )
    # A bot is paused only when its canonical status is "paused".
    # paused_by_system / paused_by_user are metadata fields — they do NOT
    # independently mark a bot as paused if its status is "active".
    paused = bool(status == "paused")
    stopped = bool(status == "stopped")
    active = bool(status == "active" and not paused and not stopped and not deleted)

    trading_mode = bot.get("trading_mode") or bot.get("mode")
    if not trading_mode:
        if bot.get("is_paper"):
            trading_mode = "paper"
        elif bot.get("is_live"):
            trading_mode = "live"

    lifecycle_stage = bot.get("lifecycle_stage")
    if not lifecycle_stage:
        if deleted:
            lifecycle_stage = "deleted"
        elif paused:
            lifecycle_stage = "paused"
        elif stopped:
            lifecycle_stage = "stopped"
        else:
            lifecycle_stage = status

    eligible, not_eligible_reasons = _compute_eligible_to_trade(
        {**bot, "trading_mode": trading_mode},
        active, paused, stopped, deleted,
    )

    return {
        **bot,
        "deleted": deleted,
        "is_deleted": deleted,
        "paused": paused,
        "stopped": stopped,
        "active": active,
        "lifecycle_stage": lifecycle_stage,
        "mode": trading_mode,
        "trading_mode": trading_mode or bot.get("trading_mode"),
        "eligible_to_trade": eligible,
        "not_eligible_reasons": not_eligible_reasons,
    }


def is_active_bot(bot: Dict) -> bool:
    """Return True if bot should count as active."""
    return normalize_bot_state(bot).get("active", False)

