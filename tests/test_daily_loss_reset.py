"""
Test: Daily Loss Lock Auto-Reset Job

Validates that the daily_loss_reset job:
1. Identifies stale locks (day_key != today)
2. Clears stale locks
3. Leaves today's locks intact
4. Handles missing day_key (legacy state)
5. Correctly identifies today's key
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from jobs.daily_loss_reset import (
    _today_key,
    reset_stale_daily_loss_locks,
    _seconds_until_next_midnight_utc,
)


def run(coro):
    """Helper to run async functions in sync test context."""
    return asyncio.run(coro)


class TestTodayKey:
    """Test _today_key() returns expected UTC format."""

    def test_today_key_format(self):
        key = _today_key()
        assert len(key) == 10, "Expected YYYY-MM-DD format"
        parts = key.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # year
        assert len(parts[1]) == 2  # month
        assert len(parts[2]) == 2  # day

    def test_today_key_is_utc(self):
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert _today_key() == now_utc


class TestSecondsUntilMidnight:
    """Test the midnight sleep calculation."""

    def test_returns_positive_seconds(self):
        secs = _seconds_until_next_midnight_utc()
        assert secs > 0, "Sleep duration must be positive"
        assert secs <= 86401, "Must be at most ~24 hours"


def _make_db(stale_users, legacy_users, modified_count=0):
    """Build a mock db with pre-configured cursor results."""
    db = MagicMock()

    stale_cursor = MagicMock()
    stale_cursor.to_list = AsyncMock(return_value=stale_users)
    legacy_cursor = MagicMock()
    legacy_cursor.to_list = AsyncMock(return_value=legacy_users)

    db.users_collection.find = MagicMock(side_effect=[stale_cursor, legacy_cursor])

    update_result = MagicMock()
    update_result.modified_count = modified_count
    db.users_collection.update_many = AsyncMock(return_value=update_result)

    return db


class TestResetStaleDailyLossLocks:
    """Test reset_stale_daily_loss_locks correctly identifies and clears stale locks."""

    def test_clears_stale_lock(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        stale = [{"id": "user1", "daily_loss_day_key": yesterday}]
        db = _make_db(stale_users=stale, legacy_users=[], modified_count=1)

        result = run(reset_stale_daily_loss_locks(db))

        assert result["cleared"] == 1
        assert "user1" in result.get("user_ids", [])
        db.users_collection.update_many.assert_called_once()

    def test_clears_legacy_lock_no_day_key(self):
        legacy = [{"id": "user2"}]
        db = _make_db(stale_users=[], legacy_users=legacy, modified_count=1)

        result = run(reset_stale_daily_loss_locks(db))

        assert result["cleared"] == 1
        assert "user2" in result.get("user_ids", [])

    def test_no_stale_locks_skips_update(self):
        db = _make_db(stale_users=[], legacy_users=[], modified_count=0)

        result = run(reset_stale_daily_loss_locks(db))

        assert result["cleared"] == 0
        db.users_collection.update_many.assert_not_called()

    def test_today_lock_is_not_cleared(self):
        today = _today_key()
        stale_users = []  # DB filter excludes today's key — returns empty
        db = _make_db(stale_users=stale_users, legacy_users=[], modified_count=0)

        result = run(reset_stale_daily_loss_locks(db))

        assert result["cleared"] == 0
        assert result["today"] == today

    def test_db_error_returns_graceful_result(self):
        db = MagicMock()
        db.users_collection.find = MagicMock(side_effect=Exception("DB offline"))

        result = run(reset_stale_daily_loss_locks(db))

        assert result["cleared"] == 0
        assert "error" in result

