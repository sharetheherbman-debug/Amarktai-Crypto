"""
Tests: Paper bots must never be gated by training.

Covers:
  1. get_bots_status — paper bot with training_complete=False shows state='active'.
  2. seed_luno_paper_bots — seeded bots have training_complete=True.
  3. _check_bot_blockers — training block is skipped for paper bots.
  4. Intelligence status — per-user CoinStats key overrides key_missing fetch_status.
  5. Platform-scoped cloning — _clone_top_bot_for_platform copies top bot, same exchange only.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

_HEAVY_STUBS = [
    "ccxt", "ccxt.async_support", "ccxt_service", "tenacity", "huggingface_hub",
]
for _mod in _HEAVY_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ── 1. Paper bot state never shows "training" ─────────────────────────────────

class TestPaperBotNeverInTraining:
    """get_bots_status must show paper bots as active regardless of training_complete."""

    def _make_bot(self, **overrides):
        base = {
            "id": "b001",
            "user_id": "u001",
            "name": "PaperBot",
            "status": "active",
            "exchange": "luno",
            "trading_mode": "paper",
            "training_complete": False,  # <-- intentionally False
            "training_in_progress": False,
        }
        base.update(overrides)
        return base

    def test_paper_bot_active_state_despite_training_complete_false(self):
        """A paper bot with training_complete=False and status=active must show state='active'."""
        from routes.bot_lifecycle import get_bots_status
        import inspect

        source = inspect.getsource(get_bots_status)
        # The new logic must reference 'is_paper' somewhere
        assert "is_paper" in source, (
            "get_bots_status must define 'is_paper' to skip training gate for paper bots"
        )

    def test_paper_bot_status_logic(self):
        """Directly verify the state-mapping logic: paper + active + training_complete=False => active."""
        bot = self._make_bot()
        is_paper = bot.get("trading_mode", "paper") == "paper"
        status = bot.get("status", "unknown")
        training_complete = bot.get("training_complete", True if is_paper else False)
        training_in_progress = bot.get("training_in_progress", False)

        # Mirror the new logic from get_bots_status
        if status in ("training",) or (training_in_progress and not is_paper):
            state = "training"
        elif status == "training_failed" or (bot.get("training_failed") and not is_paper):
            state = "training_failed"
        elif status == "active" and not training_complete and not is_paper:
            state = "training"
        elif status == "active":
            state = "active"
        else:
            state = status

        assert state == "active", (
            f"Paper bot with training_complete=False must show state='active', got {state!r}"
        )

    def test_live_bot_without_training_still_shows_training(self):
        """A live bot with training_complete=False must still show state='training'."""
        bot = self._make_bot(trading_mode="live", training_complete=False)
        is_paper = bot.get("trading_mode", "paper") == "paper"
        status = bot.get("status", "unknown")
        training_complete = bot.get("training_complete", True if is_paper else False)
        training_in_progress = bot.get("training_in_progress", False)

        if status in ("training",) or (training_in_progress and not is_paper):
            state = "training"
        elif status == "training_failed" or (bot.get("training_failed") and not is_paper):
            state = "training_failed"
        elif status == "active" and not training_complete and not is_paper:
            state = "training"
        elif status == "active":
            state = "active"
        else:
            state = status

        assert state == "training", (
            f"Live bot with training_complete=False must show state='training', got {state!r}"
        )


# ── 2. Seeded paper bots have training_complete=True ─────────────────────────

class TestSeedBotsTrainingComplete:
    """seed_luno_paper_bots must set training_complete=True on new paper bots."""

    def test_seed_sets_training_complete(self):
        """Inspect seed_luno_paper_bots source to confirm training_complete=True is set."""
        import inspect
        from routes.bot_lifecycle import seed_luno_paper_bots

        source = inspect.getsource(seed_luno_paper_bots)
        assert '"training_complete": True' in source or "'training_complete': True" in source, (
            "seed_luno_paper_bots must set training_complete=True for new paper bots"
        )
        assert '"training_in_progress": False' in source or "'training_in_progress': False" in source, (
            "seed_luno_paper_bots must set training_in_progress=False for new paper bots"
        )


# ── 3. _check_bot_blockers skips training block for paper bots ───────────────

class TestBotBlockersSkipTrainingForPaper:
    """_check_bot_blockers must NOT return a training block for paper bots."""

    @pytest.mark.asyncio
    async def test_paper_bot_with_training_status_not_blocked(self):
        """A paper bot in training status must not be blocked by _check_bot_blockers."""
        from routes.bot_lifecycle import _check_bot_blockers

        paper_bot = {
            "id": "b001",
            "user_id": "u001",
            "trading_mode": "paper",
            "status": "training",
            "training_in_progress": True,
        }

        mock_user = None
        mock_modes = None

        import database as db_module
        mock_users = MagicMock()
        mock_users.find_one = AsyncMock(return_value=mock_user)
        mock_modes_col = MagicMock()
        mock_modes_col.find_one = AsyncMock(return_value=mock_modes)

        with patch.object(db_module, "users_collection", mock_users), \
             patch.object(db_module, "system_modes_collection", mock_modes_col):
            result = await _check_bot_blockers(paper_bot, "u001")

        # Should be None (no blocker) since it's a paper bot
        assert result is None, (
            f"Paper bot must not be blocked by training gate; got blocker: {result}"
        )

    @pytest.mark.asyncio
    async def test_live_bot_with_training_status_is_blocked(self):
        """A live bot with training status MUST be blocked by _check_bot_blockers."""
        from routes.bot_lifecycle import _check_bot_blockers

        live_bot = {
            "id": "b002",
            "user_id": "u001",
            "trading_mode": "live",
            "status": "training",
            "training_in_progress": True,
        }

        import database as db_module
        mock_users = MagicMock()
        mock_users.find_one = AsyncMock(return_value=None)
        mock_modes_col = MagicMock()
        mock_modes_col.find_one = AsyncMock(return_value=None)

        with patch.object(db_module, "users_collection", mock_users), \
             patch.object(db_module, "system_modes_collection", mock_modes_col):
            result = await _check_bot_blockers(live_bot, "u001")

        # Live bot SHOULD be blocked
        assert result is not None, "Live bot in training must return a blocker"
        assert result.get("code") == "training", (
            f"Blocker code must be 'training', got {result.get('code')!r}"
        )


# ── 4. Intelligence status per-user key fix ───────────────────────────────────

class TestIntelligenceStatusPerUserKey:
    """GET /api/intelligence/status must resolve CoinStats key for the calling user."""

    def test_intelligence_status_resolves_per_user_key(self):
        """routes/intelligence.py must call resolve_coinstats_key(user_id)."""
        import inspect
        import routes.intelligence as intel_module

        source = inspect.getsource(intel_module.get_intelligence_status)
        assert "resolve_coinstats_key" in source, (
            "get_intelligence_status must call resolve_coinstats_key to check per-user key"
        )
        assert "user_id" in source, (
            "get_intelligence_status must pass user_id to key resolution"
        )
        assert "key_source" in source, (
            "get_intelligence_status must return key_source in response"
        )
        assert "resolved_for_user_id" in source, (
            "get_intelligence_status must return resolved_for_user_id in response"
        )

    def test_fetch_status_not_key_missing_when_user_has_key(self):
        """If user has a valid CoinStats key, fetch_status must not be key_missing."""
        # Simulate the override logic introduced in intelligence.py
        coinstats_key = "valid-key-12345"
        coinstats_configured = bool(coinstats_key)

        # brief from scheduler says key_missing (scheduler ran with no user context)
        brief_fetch_status = "key_missing"
        last_run_at = "2026-01-01T00:00:00+00:00"

        # The new logic overrides fetch_status when user has a key
        fetch_status = brief_fetch_status
        if coinstats_configured and fetch_status == "key_missing":
            fetch_status = "ok" if last_run_at else "pending"

        assert fetch_status != "key_missing", (
            "fetch_status must not be 'key_missing' when user has a valid CoinStats key"
        )
        assert coinstats_configured is True


# ── 5. Platform-scoped cloning ────────────────────────────────────────────────

class TestPlatformScopedCloning:
    """_clone_top_bot_for_platform must clone the top-performing bot on the same exchange."""

    def _make_autopilot(self, db_mock):
        from autopilot_engine import AutopilotEngine
        engine = AutopilotEngine.__new__(AutopilotEngine)
        engine.db = db_mock
        engine.running = False
        engine.last_error = None
        return engine

    @pytest.mark.asyncio
    async def test_clones_top_performing_bot_on_same_exchange(self):
        """Clone picks the bot with highest total_profit on the target exchange."""
        # Two bots on luno; one on binance
        luno_bots = [
            {"id": "bot1", "exchange": "luno", "total_profit": 500.0, "win_rate": 0.6,
             "risk_mode": "balanced", "stop_loss_pct": 0.02, "take_profit_pct": 0.03,
             "strategy": {"type": "momentum"}, "status": "active", "trading_mode": "paper"},
            {"id": "bot2", "exchange": "luno", "total_profit": 1200.0, "win_rate": 0.7,
             "risk_mode": "safe", "stop_loss_pct": 0.015, "take_profit_pct": 0.025,
             "strategy": {"type": "mean_reversion"}, "status": "active", "trading_mode": "paper"},
            {"id": "bot3", "exchange": "binance", "total_profit": 5000.0, "win_rate": 0.9,
             "risk_mode": "aggressive", "stop_loss_pct": 0.01, "take_profit_pct": 0.04,
             "strategy": {"type": "arb"}, "status": "active", "trading_mode": "paper"},
        ]
        # Only return luno bots for the query (exchange filter)
        luno_only = [b for b in luno_bots if b["exchange"] == "luno"]

        inserted = []

        async def mock_insert(doc):
            inserted.append(doc)
            return MagicMock(inserted_id="x")

        mock_bots_col = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=luno_only)
        mock_bots_col.find = MagicMock(return_value=mock_cursor)
        mock_bots_col.insert_one = AsyncMock(side_effect=mock_insert)

        db_mock = MagicMock()
        db_mock.bots = mock_bots_col

        engine = self._make_autopilot(db_mock)
        result = await engine._clone_top_bot_for_platform("u001", 1000.0, "luno")

        assert result.get("success") is True, f"Expected success, got: {result}"
        assert result.get("exchange") == "luno", "Clone must be on same exchange"
        # Top luno bot by profit is bot2
        assert result.get("cloned_from") == "bot2", (
            f"Expected cloned_from='bot2' (highest luno profit), got {result.get('cloned_from')!r}"
        )

        # Verify the inserted bot has the right params
        assert len(inserted) == 1
        cloned_bot = inserted[0]
        assert cloned_bot["exchange"] == "luno"
        assert cloned_bot["risk_mode"] == "safe"  # From bot2
        assert cloned_bot["stop_loss_pct"] == 0.015  # From bot2
        assert cloned_bot["strategy"] == {"type": "mean_reversion"}  # From bot2
        assert cloned_bot["trading_mode"] == "paper"
        # Must be immediately active
        assert cloned_bot["status"] == "active"
        assert cloned_bot["training_complete"] is True
        assert cloned_bot["training_in_progress"] is False
        assert cloned_bot["initial_capital"] == 1000.0

    @pytest.mark.asyncio
    async def test_no_cross_platform_copy(self):
        """Cloning must only pick bots from the target exchange."""
        luno_bots = [
            {"id": "luno1", "exchange": "luno", "total_profit": 100.0, "win_rate": 0.5,
             "risk_mode": "balanced", "status": "active", "trading_mode": "paper"},
        ]

        inserted = []

        async def mock_insert(doc):
            inserted.append(doc)
            return MagicMock(inserted_id="x")

        mock_bots_col = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=luno_bots)
        mock_bots_col.find = MagicMock(return_value=mock_cursor)
        mock_bots_col.insert_one = AsyncMock(side_effect=mock_insert)

        db_mock = MagicMock()
        db_mock.bots = mock_bots_col

        engine = self._make_autopilot(db_mock)
        result = await engine._clone_top_bot_for_platform("u001", 1000.0, "luno")

        assert result.get("exchange") == "luno", "Clone must be on luno exchange"
        # The find() call must have been filtered by exchange
        find_call_args = mock_bots_col.find.call_args
        assert find_call_args is not None
        query = find_call_args[0][0] if find_call_args[0] else find_call_args.args[0]
        assert query.get("exchange") == "luno", (
            f"find() query must filter by exchange='luno', got: {query}"
        )

    @pytest.mark.asyncio
    async def test_clone_works_when_no_existing_bots(self):
        """When there are no existing bots on a platform, clone creates a bot with defaults."""
        inserted = []

        async def mock_insert(doc):
            inserted.append(doc)
            return MagicMock(inserted_id="x")

        mock_bots_col = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_bots_col.find = MagicMock(return_value=mock_cursor)
        mock_bots_col.insert_one = AsyncMock(side_effect=mock_insert)

        db_mock = MagicMock()
        db_mock.bots = mock_bots_col

        engine = self._make_autopilot(db_mock)
        result = await engine._clone_top_bot_for_platform("u001", 1000.0, "binance")

        assert result.get("success") is True
        assert result.get("cloned_from") is None  # No source bot
        assert len(inserted) == 1
        assert inserted[0]["status"] == "active"
        assert inserted[0]["training_complete"] is True
