"""
Migration: Deduplicate bots with the same (user_id, exchange, trading_mode, name).

Run once before adding the unique partial index uidx_bot_identity.
For each duplicate group (non-deleted bots sharing the same identity), keeps
the oldest bot (lowest created_at or insertion order) and soft-deletes the rest.

Safe to re-run: subsequent runs are no-ops.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
from logger_config import logger

_DEDUP_REASON = "dedup_migration_keep_oldest"


async def deduplicate_bots() -> int:
    """
    Find and soft-delete duplicate non-deleted bots, keeping the oldest per
    (user_id, exchange, trading_mode, name) group.

    Returns the number of bots soft-deleted.
    """
    if db.bots_collection is None:
        logger.warning("⚠️  deduplicate_bots: bots_collection not initialized, skipping")
        return 0

    pipeline = [
        {"$match": {"deleted_at": {"$exists": False}}},
        {
            "$group": {
                "_id": {
                    "user_id": "$user_id",
                    "exchange": "$exchange",
                    "trading_mode": "$trading_mode",
                    "name": "$name",
                },
                "ids": {"$push": "$id"},
                "count": {"$sum": 1},
                # Keep the oldest by created_at (lexicographic ISO-8601 sort is correct)
                "oldest_id": {"$min": "$id"},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]

    duplicate_groups = await db.bots_collection.aggregate(pipeline).to_list(None)

    if not duplicate_groups:
        logger.info("✅ No duplicate bots found – nothing to deduplicate")
        return 0

    delete_ts = datetime.now(timezone.utc).isoformat()
    total_deleted = 0

    for group in duplicate_groups:
        gid = group["_id"]
        all_ids = group["ids"]
        # "oldest" by id is a proxy; prefer created_at if available
        # Fetch the actual docs sorted by created_at to determine which to keep
        docs = await db.bots_collection.find(
            {
                "user_id": gid["user_id"],
                "exchange": gid["exchange"],
                "trading_mode": gid["trading_mode"],
                "name": gid["name"],
                "deleted_at": {"$exists": False},
            },
            {"_id": 0, "id": 1, "created_at": 1},
        ).sort("created_at", 1).to_list(None)

        if len(docs) <= 1:
            continue

        keep_id = docs[0]["id"]
        duplicate_ids = [d["id"] for d in docs[1:]]

        result = await db.bots_collection.update_many(
            {"id": {"$in": duplicate_ids}},
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": delete_ts,
                    "deleted_by": "dedup_migration",
                    "deletion_reason": _DEDUP_REASON,
                }
            },
        )
        deleted = result.modified_count
        total_deleted += deleted
        logger.info(
            f"Dedup: kept {keep_id[:8]} for "
            f"{gid['user_id'][:8]}/{gid['exchange']}/{gid['trading_mode']}/{gid['name']}; "
            f"soft-deleted {deleted} duplicate(s)"
        )

    logger.info(f"✅ Bot deduplication complete: {total_deleted} duplicate(s) soft-deleted")
    return total_deleted


async def run_dedup_on_startup() -> None:
    """
    Called at server startup (before index creation) to safely remove duplicate
    bots that would otherwise violate the new unique partial index.
    Errors are caught and logged – startup is never blocked.
    """
    try:
        count = await deduplicate_bots()
        if count:
            logger.info(f"🔧 Startup dedup: removed {count} duplicate bot(s)")
    except Exception as exc:
        logger.error(f"Startup bot deduplication failed (non-critical): {exc}")


if __name__ == "__main__":
    async def _main():
        await db.connect()
        await deduplicate_bots()
        await db.close_db()

    asyncio.run(_main())
