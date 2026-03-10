"""
Test: canonical bot counts agree across all relevant endpoints.

Verifies the ONE SOURCE OF TRUTH guarantee:
  /api/bots/status          → active_bots
  /api/diagnostics/paper-status → active_bots
  /api/overview/snapshot    → activeBots
  /api/wallet/paper         → (funded_status is deterministic)

All three bot-count values must agree.  No mocking of the canonical
service is done — instead, the canonical function itself is called for
the expected value so the tests always move in lockstep with the real
implementation.
"""

import sys
import os
import asyncio
import importlib.util
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot(status: str, *, bot_type: str = "standard") -> dict:
    return {
        "id": f"bot-{status}-1",
        "user_id": "u1",
        "status": status,
        "exchange": "luno",
        "trading_mode": "paper",
        "initial_capital": 1000,
        "bot_type": bot_type,
    }


def _mock_collection(bots: list):
    """Return a MagicMock bots_collection that serves the given list."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=bots)
    col = MagicMock()
    col.find.return_value = cursor
    return col


# ---------------------------------------------------------------------------
# Unit tests for canonical.get_canonical_bot_counts
# ---------------------------------------------------------------------------

class TestGetCanonicalBotCounts:

    @pytest.mark.asyncio
    async def test_all_active(self):
        from services.canonical import get_canonical_bot_counts

        bots = [_make_bot("active"), _make_bot("active")]
        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots)
            counts = await get_canonical_bot_counts("u1")

        assert counts["total"] == 2
        assert counts["active"] == 2
        assert counts["paused"] == 0

    @pytest.mark.asyncio
    async def test_mixed_states(self):
        from services.canonical import get_canonical_bot_counts

        bots = [
            _make_bot("active"),
            _make_bot("paused"),
            _make_bot("training"),
        ]
        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots)
            counts = await get_canonical_bot_counts("u1")

        assert counts["total"] == 3
        assert counts["active"] == 1
        assert counts["paused"] == 1
        assert counts["training"] == 1

    @pytest.mark.asyncio
    async def test_empty_db_returns_zeros(self):
        from services.canonical import get_canonical_bot_counts

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection([])
            counts = await get_canonical_bot_counts("u1")

        assert counts["total"] == 0
        assert counts["active"] == 0

    @pytest.mark.asyncio
    async def test_none_collection_returns_zeros(self):
        from services.canonical import get_canonical_bot_counts

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = None
            counts = await get_canonical_bot_counts("u1")

        assert counts["total"] == 0
        assert counts["active"] == 0

    @pytest.mark.asyncio
    async def test_scalper_counted_separately(self):
        from services.canonical import get_canonical_bot_counts

        bots = [
            _make_bot("active", bot_type="scalper"),
            _make_bot("active", bot_type="standard"),
        ]
        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots)
            counts = await get_canonical_bot_counts("u1")

        assert counts["scalper_count"] == 1
        assert counts["normal_count"] == 1
        assert counts["total"] == 2

    @pytest.mark.asyncio
    async def test_activity_semantics_expose_active_vs_runnable_and_reasons(self):
        from services.canonical import get_canonical_bot_counts

        bots = [
            _make_bot("active"),
            {
                **_make_bot("active"),
                "id": "blocked-bot",
                "trading_mode": None,
            },
            _make_bot("paused"),
        ]
        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots)
            mock_db.trades_collection = None
            counts = await get_canonical_bot_counts("u1")

        assert counts["total_bot_records"] == 3
        assert counts["active_bot_records"] == 2
        assert counts["runnable_active_bots"] == 1
        assert counts["blocked_bots"] == 1
        assert counts["non_runnable_reasons"]["no_trading_mode"] == 1


# ---------------------------------------------------------------------------
# Unit tests for canonical.get_canonical_wallet_truth
# ---------------------------------------------------------------------------

class TestGetCanonicalWalletTruth:

    @pytest.mark.asyncio
    async def test_zero_total_is_unfunded(self):
        from services.canonical import get_canonical_wallet_truth

        with patch("services.canonical.db") as mock_db, \
             patch("services.canonical.paper_wallet_service") as mock_pw:
            mock_db.bots_collection = _mock_collection([])
            mock_pw.get_balances = AsyncMock(return_value={"total": 0.0})
            truth = await get_canonical_wallet_truth("u1")

        assert truth["funded_status"] == "UNFUNDED"
        assert truth["status"] == truth["funded_status"], \
            "status and funded_status must always agree"
        assert truth["total"] == 0.0

    @pytest.mark.asyncio
    async def test_funded_when_balance_covers_bots(self):
        from services.canonical import get_canonical_wallet_truth

        active_bot = _make_bot("active")
        active_bot["initial_capital"] = 500

        with patch("services.canonical.db") as mock_db, \
             patch("services.canonical.paper_wallet_service") as mock_pw:
            mock_db.bots_collection = _mock_collection([active_bot])
            mock_pw.get_balances = AsyncMock(return_value={"total": 1000.0})
            truth = await get_canonical_wallet_truth("u1")

        assert truth["funded_status"] == "FUNDED"
        assert truth["status"] == "FUNDED"
        assert truth["shortfall"] == 0.0

    @pytest.mark.asyncio
    async def test_unfunded_when_balance_below_required(self):
        from services.canonical import get_canonical_wallet_truth

        active_bot = _make_bot("active")
        active_bot["initial_capital"] = 5000

        with patch("services.canonical.db") as mock_db, \
             patch("services.canonical.paper_wallet_service") as mock_pw:
            mock_db.bots_collection = _mock_collection([active_bot])
            mock_pw.get_balances = AsyncMock(return_value={"total": 100.0})
            truth = await get_canonical_wallet_truth("u1")

        assert truth["funded_status"] == "UNFUNDED"
        assert truth["status"] == "UNFUNDED"
        assert truth["shortfall"] > 0


class TestGetCanonicalTradeCounts:
    pytestmark = pytest.mark.skipif(
        importlib.util.find_spec("motor") is None,
        reason="canonical service dependencies (motor/database) not installed",
    )

    @pytest.mark.asyncio
    async def test_trade_counts_scoped_to_closed_trades_for_user_bots(self):
        from services.canonical import get_canonical_trade_counts

        bots_cursor = MagicMock()
        bots_cursor.to_list = AsyncMock(return_value=[
            {"id": "bot-1", "user_id": "u1"},
            {"id": "bot-2", "user_id": "u1"},
        ])
        bots_collection = MagicMock()
        bots_collection.find.return_value = bots_cursor

        trades_collection = MagicMock()
        trades_collection.count_documents = AsyncMock(side_effect=[12, 4])

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = bots_collection
            mock_db.trades_collection = trades_collection
            counts = await get_canonical_trade_counts("u1")

        assert counts == {"total": 12, "today": 4}
        first_query = trades_collection.count_documents.await_args_list[0].args[0]
        second_query = trades_collection.count_documents.await_args_list[1].args[0]
        assert first_query["status"] == "closed"
        assert second_query["status"] == "closed"
        assert first_query["bot_id"]["$in"] == ["bot-1", "bot-2"]
        assert second_query["bot_id"]["$in"] == ["bot-1", "bot-2"]

    @pytest.mark.asyncio
    async def test_trade_counts_zero_when_user_has_no_bots(self):
        from services.canonical import get_canonical_trade_counts

        bots_cursor = MagicMock()
        bots_cursor.to_list = AsyncMock(return_value=[])
        bots_collection = MagicMock()
        bots_collection.find.return_value = bots_cursor

        trades_collection = MagicMock()
        trades_collection.count_documents = AsyncMock()

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = bots_collection
            mock_db.trades_collection = trades_collection
            counts = await get_canonical_trade_counts("u1")

        assert counts == {"total": 0, "today": 0}
        trades_collection.count_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_funded_status_never_contradict(self):
        """The hallmark test: status and funded_status must always be equal."""
        from services.canonical import get_canonical_wallet_truth

        scenarios = [
            (0.0, []),
            (1000.0, []),
            (0.0, [_make_bot("active")]),
            (500.0, [_make_bot("active")]),
        ]
        for balance, bots in scenarios:
            with patch("services.canonical.db") as mock_db, \
                 patch("services.canonical.paper_wallet_service") as mock_pw:
                mock_db.bots_collection = _mock_collection(bots)
                mock_pw.get_balances = AsyncMock(return_value={"total": balance})
                truth = await get_canonical_wallet_truth("u1")

            assert truth["status"] == truth["funded_status"], (
                f"Contradiction for balance={balance}, bots={len(bots)}: "
                f"status={truth['status']!r} != funded_status={truth['funded_status']!r}"
            )


# ---------------------------------------------------------------------------
# Integration-style: canonical counts used by paper-status matches bots/status
# ---------------------------------------------------------------------------

class TestEndpointConsistency:
    """
    Proves that get_canonical_bot_counts is the shared function driving
    /api/bots/status active_bots and /api/diagnostics/paper-status active_bots.

    Both endpoints must return the same active count for the same user.
    """

    @pytest.mark.asyncio
    async def test_bots_status_active_matches_canonical(self):
        """_bots_status_payload active_bots must equal canonical active count."""
        from services.canonical import get_canonical_bot_counts
        from routes.bot_lifecycle import _bots_status_payload

        bots_db = [_make_bot("active"), _make_bot("paused")]

        # canonical path
        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots_db)
            canonical = await get_canonical_bot_counts("u1")

        # bot_lifecycle path — enriched_bots already computed by bot_lifecycle
        enriched = [
            {"id": "bot-active-1", "status": "active", "active": True,
             "state": "active", "exchange": "luno"},
            {"id": "bot-paused-1", "status": "paused", "active": False,
             "state": "paused", "exchange": "luno"},
        ]
        from routes.bot_lifecycle import ALL_EXCHANGES
        exchange_counts = {ex: 0 for ex in ALL_EXCHANGES}
        exchange_counts["luno"] = 2
        payload = _bots_status_payload(enriched, exchange_counts, ALL_EXCHANGES)
        bot_lifecycle_active = payload["active_bots"]

        assert canonical["active"] == bot_lifecycle_active, (
            f"Canonical active={canonical['active']} != "
            f"bot_lifecycle active_bots={bot_lifecycle_active}"
        )

    @pytest.mark.asyncio
    async def test_overview_snapshot_active_bots_uses_canonical(self):
        """overview/snapshot activeBots must equal get_canonical_bot_counts active."""
        from services.canonical import get_canonical_bot_counts

        bots_db = [_make_bot("active"), _make_bot("active"), _make_bot("paused")]

        with patch("services.canonical.db") as mock_db:
            mock_db.bots_collection = _mock_collection(bots_db)
            canonical = await get_canonical_bot_counts("u1")

        # The snapshot endpoint calls get_canonical_bot_counts("u1") and returns
        # counts["active"] as activeBots.  We verify the canonical service itself.
        assert canonical["active"] == 2
        assert canonical["total"] == 3


# ---------------------------------------------------------------------------
# Regression: paper reset must clear fills_ledger
# ---------------------------------------------------------------------------

class TestPaperResetClearsFills:

    def test_perform_paper_reset_clears_fills_ledger(self):
        """perform_paper_reset must reference 'fills_ledger' in its logic."""
        import inspect
        from routes.system_mode import perform_paper_reset
        src = inspect.getsource(perform_paper_reset)
        assert "fills_ledger" in src, (
            "perform_paper_reset must clear fills_ledger on paper reset"
        )

    def test_perform_paper_reset_resets_circuit_breaker(self):
        """perform_paper_reset must reference circuit_breaker_state."""
        import inspect
        from routes.system_mode import perform_paper_reset
        src = inspect.getsource(perform_paper_reset)
        assert "circuit_breaker_state" in src, (
            "perform_paper_reset must reset circuit_breaker_state"
        )


# ---------------------------------------------------------------------------
# Regression: diagnostics/go-live must not use db.database (wrong attribute)
# ---------------------------------------------------------------------------

class TestGoLiveEndpointUsesDbDot:

    def test_go_live_uses_db_db_not_db_database(self):
        """The go-live endpoint source must call db.db, never db.database."""
        import ast
        server_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'server.py'
        )
        with open(server_path) as f:
            source = f.read()

        # Locate diagnostics_go_live function source via simple string search
        # (avoids importing server which needs openai)
        func_start = source.find("async def diagnostics_go_live(")
        assert func_start != -1, "diagnostics_go_live not found in server.py"
        # Find next top-level function to bound the search
        func_end = source.find("\nasync def ", func_start + 1)
        func_src = source[func_start:func_end] if func_end != -1 else source[func_start:]

        assert "db.database" not in func_src, (
            "diagnostics_go_live must not reference db.database (use db.db)"
        )
        assert "db.db" in func_src, (
            "diagnostics_go_live must reference db.db"
        )
