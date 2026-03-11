"""
Single-Source-Of-Truth Repair Tests

Validates that the final gap between internal engine decisions/queueing
and API-visible bot/radar/trade truth is closed:

1.  _canonical_bot_id() exists in trading_scheduler.py and falls back to _id
    when the application-level 'id' field is absent — mirrors radar.py.
2.  The active_bots query no longer excludes _id, so the fallback can work.
3.  The queue-adding loop uses _canonical_bot_id and skips empty IDs.
4.  The queue-processing loop uses _canonical_bot_id for the bot lookup.
5.  get_health_snapshot() exposes queued_bot_ids for API-visible truth.
6.  trade_staggerer.add_to_queue() rejects empty bot_ids early.
7.  execute_live_trade() uses bot_id from _canonical_bot_id.

Run with:
  ENVIRONMENT=testing PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
      python -m pytest tests/test_single_source_truth_repair.py -v
"""

import os
import ast

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCHEDULER_PATH = os.path.join(ROOT, "backend", "trading_scheduler.py")
STAGGERER_PATH = os.path.join(ROOT, "backend", "engines", "trade_staggerer.py")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _extract_function_body(src: str, func_name: str) -> str:
    """Extract the body of a top-level or class method by name."""
    patterns = [f"async def {func_name}", f"def {func_name}"]
    for pat in patterns:
        start = src.find(pat)
        if start != -1:
            break
    else:
        return ""
    # Find next function/method at the same indent level
    end = src.find("\n    async def ", start + 1)
    if end == -1:
        end = src.find("\n    def ", start + 1)
    if end == -1:
        end = src.find("\nasync def ", start + 1)
    if end == -1:
        end = src.find("\ndef ", start + 1)
    return src[start:end] if end != -1 else src[start:]


# ──────────────────────────────────────────────────────────────────────────────
# 1. _canonical_bot_id helper
# ──────────────────────────────────────────────────────────────────────────────

class TestCanonicalBotIdHelper:
    """_canonical_bot_id must exist at module level in trading_scheduler.py."""

    def test_function_defined(self):
        src = _read(SCHEDULER_PATH)
        assert "def _canonical_bot_id" in src, (
            "_canonical_bot_id helper must be defined in trading_scheduler.py"
        )

    def test_falls_back_to_underscore_id(self):
        src = _read(SCHEDULER_PATH)
        assert '"_id"' in src or "'_id'" in src, (
            "_canonical_bot_id must access '_id' for MongoDB ObjectId fallback"
        )

    def test_has_docstring_mentioning_radar(self):
        src = _read(SCHEDULER_PATH)
        assert "radar" in src.lower(), (
            "_canonical_bot_id docstring / comment should reference radar.py "
            "to document the shared pattern"
        )

    def test_returns_empty_string_sentinel(self):
        """Function must return '' (not None) when both id and _id are missing."""
        src = _read(SCHEDULER_PATH)
        # 'return ""' must appear inside the function body
        assert 'return ""' in src, (
            "_canonical_bot_id must return empty string for malformed documents"
        )

    def test_module_parses(self):
        src = _read(SCHEDULER_PATH)
        try:
            ast.parse(src)
        except SyntaxError as exc:
            raise AssertionError(f"Syntax error in trading_scheduler.py: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 2. active_bots query no longer excludes _id
# ──────────────────────────────────────────────────────────────────────────────

class TestActiveBotQueryIncludes_id:
    """The MongoDB query that fetches active bots must not suppress _id."""

    def test_no_id_zero_projection_on_active_bots(self):
        """{"_id": 0} must not appear in the active_bots query block."""
        src = _read(SCHEDULER_PATH)
        # The projection {"_id": 0} next to {"status": "active"} is the bug.
        # A simple text check is sufficient — the old code had both on adjacent lines.
        assert '{"status": "active"},\n            {"_id": 0}' not in src, (
            'active_bots query must not use {"_id": 0} projection '
            "— _id is needed as canonical bot_id fallback"
        )

    def test_comment_explains_why_id_included(self):
        src = _read(SCHEDULER_PATH)
        assert "_canonical_bot_id" in src, (
            "Scheduler must use _canonical_bot_id after including _id in query"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 3. Queue-adding loop uses _canonical_bot_id and skips empty IDs
# ──────────────────────────────────────────────────────────────────────────────

class TestQueueAddingLoopBotId:
    """The queue-adding loop must use _canonical_bot_id and skip empty results."""

    def test_uses_canonical_bot_id_in_queue_loop(self):
        src = _read(SCHEDULER_PATH)
        assert "_canonical_bot_id(bot)" in src, (
            "Queue-adding loop must call _canonical_bot_id(bot) to resolve ID"
        )

    def test_skips_empty_bot_id(self):
        src = _read(SCHEDULER_PATH)
        assert "if not bot_id" in src, (
            "Queue-adding loop must skip bots where _canonical_bot_id returns empty"
        )

    def test_warns_on_missing_id(self):
        src = _read(SCHEDULER_PATH)
        assert "missing canonical id" in src or "Skipping bot" in src, (
            "Scheduler must log a warning when a bot has no resolvable canonical id"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Queue-processing lookup uses _canonical_bot_id
# ──────────────────────────────────────────────────────────────────────────────

class TestQueueProcessingLookup:
    """The bot lookup after dequeue must use _canonical_bot_id, not b['id']."""

    def test_bot_lookup_uses_canonical_id(self):
        src = _read(SCHEDULER_PATH)
        # Old code: b['id'] == bot_id
        # New code: _canonical_bot_id(b) == bot_id
        assert "_canonical_bot_id(b) == bot_id" in src, (
            "Queue-processing bot lookup must compare _canonical_bot_id(b) to bot_id"
        )

    def test_paper_engine_called_with_bot_id_variable(self):
        """paper_engine.run_trading_cycle must receive the resolved bot_id, not bot['id']."""
        src = _read(SCHEDULER_PATH)
        # The old call was run_trading_cycle(bot['id'], ...) — that must be gone.
        # The new call uses the locally-resolved bot_id variable.
        assert "run_trading_cycle(\n                            bot_id," in src or \
               "run_trading_cycle(bot_id," in src or \
               "run_trading_cycle(\n                            bot_id\n" in src, (
            "paper_engine.run_trading_cycle must be called with the resolved "
            "bot_id variable, not bot['id']"
        )
        # Ensure the old pattern is gone from the scheduler's paper path
        assert "run_trading_cycle(\n                            bot['id']" not in src


# ──────────────────────────────────────────────────────────────────────────────
# 5. get_health_snapshot exposes queued_bot_ids
# ──────────────────────────────────────────────────────────────────────────────

class TestHealthSnapshotQueuesApiTruth:
    """get_health_snapshot must include queued_bot_ids for API-visible truth."""

    def test_queued_bot_ids_field_present(self):
        src = _read(SCHEDULER_PATH)
        assert '"queued_bot_ids"' in src, (
            "get_health_snapshot must return 'queued_bot_ids' so the "
            "/api/diagnostics/scheduler-health endpoint exposes engine decisions"
        )

    def test_queued_bot_ids_derived_from_staggerer(self):
        src = _read(SCHEDULER_PATH)
        assert "trade_staggerer.trade_queue" in src, (
            "queued_bot_ids must be derived from trade_staggerer.trade_queue"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. trade_staggerer.add_to_queue rejects empty bot_ids
# ──────────────────────────────────────────────────────────────────────────────

class TestTradeStaggererEmptyIdGuard:
    """add_to_queue must reject empty bot_ids before adding to the queue."""

    def test_guard_exists(self):
        src = _read(STAGGERER_PATH)
        assert "not bot_id" in src or "if not bot_id" in src, (
            "add_to_queue must guard against empty bot_id"
        )

    def test_guard_logs_warning(self):
        src = _read(STAGGERER_PATH)
        assert "logger.warning" in src, (
            "add_to_queue must log a warning when called with empty bot_id"
        )

    def test_guard_returns_early(self):
        src = _read(STAGGERER_PATH)
        # The early return must appear before the trade_request dict is built.
        # Use 'return' inside the guard block presence check — both guard and
        # trade_request must appear, with guard first.
        guard_text = "not bot_id"
        trade_req_text = "trade_request = {"
        guard_idx = src.find(guard_text)
        trade_req_idx = src.find(trade_req_text)
        assert guard_idx != -1, f"Could not find '{guard_text}' in trade_staggerer.py"
        assert trade_req_idx != -1, f"Could not find '{trade_req_text}' in trade_staggerer.py"
        assert guard_idx < trade_req_idx, (
            "The empty bot_id guard must appear before trade_request is built"
        )

    def test_staggerer_parses(self):
        src = _read(STAGGERER_PATH)
        try:
            ast.parse(src)
        except SyntaxError as exc:
            raise AssertionError(f"Syntax error in trade_staggerer.py: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 7. execute_live_trade uses canonical bot_id
# ──────────────────────────────────────────────────────────────────────────────

class TestExecuteLiveTradeCanonicalId:
    """execute_live_trade must derive bot_id via _canonical_bot_id."""

    def test_live_trade_resolves_canonical_id(self):
        src = _read(SCHEDULER_PATH)
        func_body = _extract_function_body(src, "execute_live_trade")
        assert func_body, "execute_live_trade function not found in trading_scheduler.py"
        assert "_canonical_bot_id(bot)" in func_body, (
            "execute_live_trade must call _canonical_bot_id(bot) to resolve bot_id"
        )

    def test_live_trade_doc_uses_bot_id_variable(self):
        src = _read(SCHEDULER_PATH)
        func_body = _extract_function_body(src, "execute_live_trade")
        assert func_body, "execute_live_trade function not found in trading_scheduler.py"
        # Trade doc must use 'bot_id' (the resolved variable), not "bot['id']"
        assert '"bot_id": bot_id' in func_body, (
            "execute_live_trade must use the resolved bot_id variable "
            "in the trade document (not bot['id'])"
        )
