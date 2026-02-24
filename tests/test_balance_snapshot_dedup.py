"""
Tests for balance snapshot writer and bot deduplication migration.

Verifies:
1. Empty-balance fetch results in status="no_data", not "success".
2. successful_syncs is NOT incremented for empty-balance exchanges.
3. store_balance_snapshot skips writing when there are no real balances.
4. Deduplication migration keeps the oldest bot and soft-deletes the rest.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# Balance Snapshot Tests
# ---------------------------------------------------------------------------

class TestBalanceSyncNoData:
    """fetch_all_balances must not produce 'success' for empty-balance results."""

    @pytest.mark.asyncio
    async def test_empty_balances_marked_as_no_data(self):
        """API succeeds but balances={} → status must be 'no_data', not 'success'."""
        from services.balance_sync_service import BalanceSyncService

        svc = BalanceSyncService()

        # Stub the per-exchange fetch to return empty balances (fresh account)
        async def _fake_fetch(user_id, exchange, api_key, api_secret, passphrase=None):
            return {
                "success": True,
                "exchange": exchange,
                "balances": {},  # empty – the production bug scenario
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        svc.fetch_exchange_balance = _fake_fetch

        mock_keys = [
            {"provider": "luno", "id": "k1", "api_key_encrypted": "x", "api_secret_encrypted": "y"}
        ]

        mock_api_keys_col = MagicMock()
        mock_api_keys_col.find = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=mock_keys))
        )

        with (
            patch("database.api_keys_collection", mock_api_keys_col),
            patch(
                "services.balance_sync_service.get_platform_config",
                return_value={"ccxt_id": "luno"},
            ),
            patch(
                "routes.api_key_management.get_decrypted_key",
                new_callable=AsyncMock,
                return_value={"api_key": "k", "api_secret": "s"},
            ),
        ):
            result = await svc.fetch_all_balances("user_1")

        exchanges = result.get("exchanges", {})
        assert "luno" in exchanges, "luno should be in exchanges dict"
        luno_data = exchanges["luno"]
        assert luno_data["status"] == "no_data", (
            f"Expected status='no_data' for empty balances, got '{luno_data['status']}'"
        )
        assert result.get("successful_syncs", 0) == 0, (
            "successful_syncs must not be incremented for empty-balance exchanges"
        )

    @pytest.mark.asyncio
    async def test_non_empty_balances_still_success(self):
        """Non-empty balances should keep status='success' and count as successful_syncs."""
        from services.balance_sync_service import BalanceSyncService

        svc = BalanceSyncService()

        async def _fake_fetch(user_id, exchange, api_key, api_secret, passphrase=None):
            return {
                "success": True,
                "exchange": exchange,
                "balances": {"ZAR": {"free": 1000.0, "used": 0.0, "total": 1000.0}},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        svc.fetch_exchange_balance = _fake_fetch

        mock_keys = [
            {"provider": "luno", "id": "k1", "api_key_encrypted": "x", "api_secret_encrypted": "y"}
        ]
        mock_api_keys_col = MagicMock()
        mock_api_keys_col.find = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=mock_keys))
        )

        with (
            patch("database.api_keys_collection", mock_api_keys_col),
            patch(
                "services.balance_sync_service.get_platform_config",
                return_value={"ccxt_id": "luno"},
            ),
            patch(
                "routes.api_key_management.get_decrypted_key",
                new_callable=AsyncMock,
                return_value={"api_key": "k", "api_secret": "s"},
            ),
        ):
            result = await svc.fetch_all_balances("user_1")

        exchanges = result.get("exchanges", {})
        assert exchanges["luno"]["status"] == "success"
        assert result.get("successful_syncs") == 1


class TestStoreBalanceSnapshotGuard:
    """store_balance_snapshot must skip writing when there is no real data."""

    @pytest.mark.asyncio
    async def test_skips_snapshot_when_no_real_data(self):
        """No-data snapshot (successful_syncs=0, empty balances) must not be written."""
        from services.balance_sync_service import BalanceSyncService

        svc = BalanceSyncService()

        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()

        all_no_data = {
            "user_id": "u1",
            "exchanges": {
                "luno": {"balances": {}, "status": "no_data", "timestamp": "t"}
            },
            "successful_syncs": 0,
            "failed_syncs": 0,
            "timestamp": "t",
        }

        with patch("database.balance_snapshots_collection", mock_col):
            stored = await svc.store_balance_snapshot("u1", all_no_data)

        assert stored is False, "Should return False when skipping empty snapshot"
        mock_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_snapshot_when_data_exists(self):
        """Snapshot with real balance data must be written."""
        from services.balance_sync_service import BalanceSyncService

        svc = BalanceSyncService()

        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))

        real_data = {
            "user_id": "u1",
            "exchanges": {
                "luno": {
                    "balances": {"ZAR": {"total": 5000.0}},
                    "status": "success",
                    "timestamp": "t",
                }
            },
            "successful_syncs": 1,
            "failed_syncs": 0,
            "timestamp": "t",
        }

        with patch("database.balance_snapshots_collection", mock_col):
            stored = await svc.store_balance_snapshot("u1", real_data)

        assert stored is True
        mock_col.insert_one.assert_called_once()


# ---------------------------------------------------------------------------
# Bot Deduplication Tests
# ---------------------------------------------------------------------------

class TestDeduplicateBots:
    """run_dedup_on_startup must soft-delete duplicates, keeping the oldest."""

    @pytest.mark.asyncio
    async def test_no_duplicates_is_noop(self):
        """When no duplicates exist, nothing is modified."""
        from migrations.deduplicate_bots import deduplicate_bots

        mock_col = MagicMock()
        # aggregate returns empty list → no duplicates
        mock_col.aggregate = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=[]))
        )
        mock_col.update_many = AsyncMock()

        with patch("database.bots_collection", mock_col):
            deleted = await deduplicate_bots()

        assert deleted == 0
        mock_col.update_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_keeps_oldest_bot_deletes_duplicate(self):
        """With 2 bots sharing the same identity, the older one is kept."""
        from migrations.deduplicate_bots import deduplicate_bots

        duplicate_group = [
            {
                "_id": {"user_id": "u1", "exchange": "luno", "trading_mode": "paper", "name": "Gbot1"},
                "ids": ["bot-old", "bot-new"],
                "count": 2,
                "oldest_id": "bot-old",
            }
        ]

        # find() returns docs sorted by created_at (oldest first)
        sorted_docs = [
            {"id": "bot-old", "created_at": "2024-01-01T00:00:00"},
            {"id": "bot-new", "created_at": "2024-06-01T00:00:00"},
        ]

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=sorted_docs)

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=duplicate_group))
        )
        mock_col.find = MagicMock(return_value=mock_cursor)

        update_calls = []

        async def mock_update_many(query, update):
            update_calls.append((query, update))
            return MagicMock(modified_count=1)

        mock_col.update_many = mock_update_many

        with patch("database.bots_collection", mock_col):
            deleted = await deduplicate_bots()

        assert deleted == 1
        assert len(update_calls) == 1
        # The NEWER bot must be soft-deleted (not the older one)
        deleted_ids = update_calls[0][0]["id"]["$in"]
        assert "bot-new" in deleted_ids
        assert "bot-old" not in deleted_ids
        # Soft-delete (not hard-delete)
        assert "$set" in update_calls[0][1]
        assert update_calls[0][1]["$set"]["status"] == "deleted"
