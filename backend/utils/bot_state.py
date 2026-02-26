"""
Bot state helpers for consistent status flags across endpoints.
"""

from typing import Dict


def normalize_bot_state(bot: Dict) -> Dict:
    """Return bot payload with consistent flags for status and deletion."""
    status = bot.get("status", "unknown")
    deleted = bool(
        status == "deleted"
        or bot.get("deleted")
        or bot.get("is_deleted")
        or bot.get("deleted_at")
    )
    paused = bool(status == "paused" or bot.get("paused_by_system") or bot.get("paused_by_user"))
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

    # Canonical display_state: reflects training override
    training_in_progress = bool(bot.get("training_in_progress") or bot.get("status") == "training")
    training_complete = bool(bot.get("training_complete"))
    if training_in_progress or (active and not training_complete and bot.get("training_required_closed_trades") is not None):
        display_state = "training"
    elif lifecycle_stage == "deleted":
        display_state = "stopped"
    else:
        display_state = lifecycle_stage or "unknown"

    return {
        **bot,
        "deleted": deleted,
        "is_deleted": deleted,
        "paused": paused,
        "stopped": stopped,
        "active": active,
        "lifecycle_stage": lifecycle_stage,
        "display_state": display_state,
        "mode": trading_mode,
        "trading_mode": trading_mode or bot.get("trading_mode"),
    }


def is_active_bot(bot: Dict) -> bool:
    """Return True if bot should count as active."""
    return normalize_bot_state(bot).get("active", False)
