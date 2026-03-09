"""
Startup Migration: Fix Bot Type Field

Bots created before the bot_validator fix (PR: audit-repair-live-trading)
had their bot_type stripped by validate_bot_creation(), so scalper bots
created via POST /api/bots were stored without bot_type.

This migration:
1. Sets bot_type='scalper' for bots whose strategy_preset='scalping'
   or whose name starts with 'Scalper' (heuristic for legacy bots).
2. Sets bot_type='normal' for any bot that still has bot_type=None/missing.
3. Sets bot_type='uagent' for bots with bot_type already set to 'uagent'
   (no-op, just ensures field is set).

This is idempotent — already-correct bots are not touched.
"""

import logging

logger = logging.getLogger(__name__)


async def run_bot_type_migration(db):
    """
    Repair bots missing the bot_type field.
    Returns (fixed_scalper, fixed_normal) counts.
    """
    try:
        bots_collection = db.bots_collection
        if bots_collection is None:
            logger.warning("fix_bot_type_field: bots_collection not available, skipping")
            return 0, 0

        # -- Step 1: Fix bots that are clearly scalper but missing the field.
        # Only match bots where bot_type is null/missing/empty — never overwrite
        # an explicitly-set 'normal' value to avoid incorrectly reclassifying bots.
        scalper_result = await bots_collection.update_many(
            {
                "bot_type": {"$in": [None, ""]},
                "$or": [
                    {"strategy_preset": "scalping"},
                    {"strategy.preset": "scalping"},
                    {"name": {"$regex": "^[Ss]calper", "$options": "i"}},
                ]
            },
            {"$set": {"bot_type": "scalper"}}
        )
        fixed_scalper = scalper_result.modified_count

        # -- Step 2: Set bot_type='normal' for any bot still missing the field
        normal_result = await bots_collection.update_many(
            {"bot_type": {"$in": [None, ""]}},
            {"$set": {"bot_type": "normal"}}
        )
        fixed_normal = normal_result.modified_count

        if fixed_scalper or fixed_normal:
            logger.info(
                "fix_bot_type_field: promoted %d bots to scalper, set %d bots to normal",
                fixed_scalper, fixed_normal
            )
        else:
            logger.info("fix_bot_type_field: all bots already have bot_type set — no changes needed")

        return fixed_scalper, fixed_normal

    except Exception as e:
        logger.warning("fix_bot_type_field migration failed (non-fatal): %s", e)
        return 0, 0
