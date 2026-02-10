"""
Datetime helper utilities shared across routes.
"""

from datetime import datetime, timezone
from typing import Optional


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string into a timezone-aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def remaining_seconds(release_at: Optional[str]) -> Optional[int]:
    """Calculate remaining seconds until release_at timestamp."""
    release_dt = parse_iso_datetime(release_at)
    if not release_dt:
        return None
    now = datetime.now(timezone.utc)
    return max(0, int((release_dt - now).total_seconds()))
