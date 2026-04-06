"""
Canonical bot query filters — single source of truth.

Every query that should exclude soft-deleted bots must use
``bot_not_deleted_filter()``.  Only explicit archive endpoints
may query deleted bots directly.
"""

from typing import Optional, Dict, Any


def bot_not_deleted_filter(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a MongoDB filter dict that excludes all soft-deleted bots.

    Covers every deletion field set by the delete endpoint:
      - status = "deleted"
      - is_deleted = True
      - deleted = True          (legacy field)
      - deleted_at exists       (timestamp set on delete)

    Args:
        extra: Optional additional filter fields merged into the base filter.

    Returns:
        A dict suitable for use directly in a pymongo query.

    Example::

        # Count only live bots
        count = await db.bots_collection.count_documents(
            bot_not_deleted_filter({"user_id": user_id, "status": "active"})
        )
    """
    base: Dict[str, Any] = {
        "status": {"$nin": ["deleted", "marked_for_deletion"]},
        "is_deleted": {"$ne": True},
        "deleted": {"$ne": True},
        "deleted_at": {"$exists": False},
    }
    if extra:
        base.update(extra)
    return base
