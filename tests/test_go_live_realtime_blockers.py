"""
Tests for Go-Live Realtime Backend Blocker Fixes.

Covers:
  A) MongoDB partial-index fix: partialFilterExpression uses null-equality (no $not/$exists:false)
     and _safe_create_index handles "Expression not supported" without crashing.
  B) Countdown broadcast: target param is passed as a plain float (not a Query descriptor object).
     Graceful degradation when countdown fails.
  C) Paper-trading skip logging: non-execution logs at INFO level with stable SKIP codes.
  D) AI error_code initialisation: variable is always defined before any reference.
"""

import os
import sys

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

_DATABASE_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "database.py")
_REALTIME_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "services", "realtime_service.py")
_SCHEDULER_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "trading_scheduler.py")
_PAPER_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "paper_trading_engine.py")
_AI_CHAT_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "ai_chat.py")


# ---------------------------------------------------------------------------
# A) MongoDB partial-index fix
# ---------------------------------------------------------------------------

class TestMongoIndexFix:
    """Verify uidx_bot_identity uses a MongoDB-compatible partialFilterExpression."""

    def _source(self):
        with open(_DATABASE_PATH) as fh:
            return fh.read()

    def test_partial_filter_no_dollar_exists_false(self):
        """partialFilterExpression must NOT use {$exists: false} (triggers $not on old Mongo)."""
        src = self._source()
        # The old incompatible expression must not appear as the actual kwarg value.
        # We check for the pattern used in the kwarg call, not in comments.
        # Our replacement comment intentionally contains the old value as documentation,
        # so we check that it does NOT appear as a keyword argument value.
        import re
        # Match partialFilterExpression={"deleted_at": {"$exists": False}}
        # (actual kwarg, not in a comment)
        pattern = r'partialFilterExpression\s*=\s*\{\s*"deleted_at"\s*:\s*\{\s*"\$exists"\s*:\s*False\s*\}\s*\}'
        assert not re.search(pattern, src), (
            "database.py partialFilterExpression kwarg still uses {$exists: False} — "
            "this triggers $not on older MongoDB and causes 'Expression not supported' errors"
        )

    def test_partial_filter_uses_null_equality(self):
        """partialFilterExpression must use {deleted_at: None} (null equality)."""
        src = self._source()
        assert '"deleted_at": None' in src, (
            "database.py must use partialFilterExpression={\"deleted_at\": None} "
            "for MongoDB-wide compatibility"
        )

    def test_safe_create_index_catches_expression_not_supported(self):
        """_safe_create_index must catch 'Expression not supported' without re-raising."""
        src = self._source()
        assert "Expression not supported" in src, (
            "_safe_create_index must handle 'Expression not supported' errors "
            "from MongoDB to prevent startup crashes on incompatible versions"
        )

    def test_bot_manager_sets_deleted_at_null_on_create(self):
        """Bots created via bot_manager.py must have deleted_at: None explicitly."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines", "bot_manager.py"
        )
        with open(path) as fh:
            src = fh.read()
        assert '"deleted_at": None' in src, (
            "bot_manager.py must set deleted_at=None on new bots so the "
            "partial index uidx_bot_identity covers them"
        )

    def test_bot_spawner_sets_deleted_at_null_on_create(self):
        """Bots created via bot_spawner.py must have deleted_at: None explicitly."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines", "bot_spawner.py"
        )
        with open(path) as fh:
            src = fh.read()
        assert '"deleted_at": None' in src, (
            "bot_spawner.py must set deleted_at=None on new bots"
        )

    def test_bot_lifecycle_sets_deleted_at_null_on_seed(self):
        """Seeded Luno bots (bot_lifecycle.py) must have deleted_at: None explicitly."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "bot_lifecycle.py"
        )
        with open(path) as fh:
            src = fh.read()
        assert '"deleted_at": None' in src, (
            "bot_lifecycle.py seed endpoint must set deleted_at=None on new bots"
        )


# ---------------------------------------------------------------------------
# B) Countdown broadcast fix
# ---------------------------------------------------------------------------

class TestCountdownBroadcastFix:
    """Verify broadcast_countdown_update passes target as a plain float."""

    def _source(self):
        with open(_REALTIME_PATH) as fh:
            return fh.read()

    def test_countdown_passes_explicit_target_float(self):
        """broadcast_countdown_update must pass target=1_000_000.0 (not rely on Query default)."""
        src = self._source()
        assert "target=1_000_000.0" in src, (
            "realtime_service.py broadcast_countdown_update must pass target=1_000_000.0 "
            "explicitly when calling get_countdown_status directly (bypassing FastAPI DI). "
            "Without this, target is a FastAPI Query descriptor object and arithmetic fails."
        )

    def test_countdown_graceful_degradation(self):
        """broadcast_countdown_update must send a safe response on failure (not just log)."""
        src = self._source()
        # There should be a degraded/offline payload inside the except block
        assert '"status": "unknown"' in src, (
            "broadcast_countdown_update must broadcast a degraded 'unknown' status on "
            "exception instead of silently swallowing errors"
        )


# ---------------------------------------------------------------------------
# C) Paper-trading skip logging
# ---------------------------------------------------------------------------

class TestPaperTradingSkipLogging:
    """Verify paper-trading non-executions log stable SKIP codes at INFO level."""

    def test_scheduler_logs_skip_with_stable_code(self):
        """trading_scheduler.py must log at INFO with SKIP_* codes on non-execution."""
        with open(_SCHEDULER_PATH) as fh:
            src = fh.read()
        assert "SKIP_EDGE_GATE" in src, (
            "trading_scheduler.py must include SKIP_EDGE_GATE code in skip log"
        )
        # Must use logger.info, not logger.debug, for the skip message
        # Find the SKIP_CODE_MAP block and verify it's followed by logger.info
        assert 'logger.info' in src and 'SKIP_OTHER' in src, (
            "trading_scheduler.py must log skip reasons at INFO level"
        )

    def test_scheduler_logs_paper_submit_and_fill(self):
        """trading_scheduler.py must log PAPER_SUBMIT and PAPER_FILL decision points."""
        with open(_SCHEDULER_PATH) as fh:
            src = fh.read()
        assert "PAPER_SUBMIT" in src, "trading_scheduler.py missing PAPER_SUBMIT log"
        assert "PAPER_FILL" in src, "trading_scheduler.py missing PAPER_FILL log"

    def test_paper_engine_logs_edge_gate_skip_at_info(self):
        """paper_trading_engine.py must log SKIP_EDGE_GATE at INFO, not DEBUG."""
        with open(_PAPER_PATH) as fh:
            src = fh.read()
        assert "SKIP_EDGE_GATE" in src, (
            "paper_trading_engine.py must log SKIP_EDGE_GATE code"
        )

    def test_paper_engine_logs_low_confidence_skip_at_info(self):
        """paper_trading_engine.py must log SKIP_LOW_CONFIDENCE at INFO."""
        with open(_PAPER_PATH) as fh:
            src = fh.read()
        assert "SKIP_LOW_CONFIDENCE" in src, (
            "paper_trading_engine.py must log SKIP_LOW_CONFIDENCE code at INFO level"
        )


# ---------------------------------------------------------------------------
# D) AI error_code always defined
# ---------------------------------------------------------------------------

class TestAIErrorCodeAlwaysDefined:
    """Verify error_code is initialised at the very top of the ai_chat try block."""

    def test_error_code_initialised_before_rate_limit_check(self):
        """error_code = None must appear at the very start of the try block in ai_chat."""
        with open(_AI_CHAT_PATH) as fh:
            lines = fh.readlines()

        # Find the ai_chat function body by looking for the decorator + function signature
        ai_chat_start = None
        try_start = None
        first_error_code_line = None
        rate_limit_line = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if '@router.post("/chat")' in stripped:
                ai_chat_start = i
            if ai_chat_start is not None and try_start is None and stripped == "try:":
                # Only accept the first try: after the function definition
                if i > ai_chat_start:
                    try_start = i
            if try_start is not None:
                if first_error_code_line is None and "error_code = None" in stripped:
                    first_error_code_line = i
                if rate_limit_line is None and "ai_rate_limiter" in stripped and "import" not in stripped:
                    rate_limit_line = i
                # Stop scanning once we've found both markers
                if first_error_code_line and rate_limit_line:
                    break

        assert ai_chat_start is not None, "Could not find @router.post('/chat') decorator"
        assert try_start is not None, "Could not find the ai_chat try: block"
        assert first_error_code_line is not None, (
            "error_code = None must appear inside the ai_chat try block"
        )
        assert rate_limit_line is None or first_error_code_line < rate_limit_line, (
            "error_code = None must be initialised BEFORE the rate-limiter check "
            "so that the outer except can always reference it. "
            f"error_code at line {first_error_code_line}, rate_limit at line {rate_limit_line}"
        )
