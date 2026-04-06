"""
Regression tests for queue hardening:
- Malformed trade_request entries (missing bot_id / exchange) must never crash
  the TradeStaggerer loop. They are dropped with a WARNING log.
- add_to_queue() must reject entries with empty bot_id or exchange and log a warning.
"""
import asyncio
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ---------------------------------------------------------------------------
# Minimal stub so trade_staggerer can import without a real DB connection
# ---------------------------------------------------------------------------
import types

_db_stub = types.ModuleType("database")
_db_stub.bots_collection = None  # type: ignore[attr-defined]
sys.modules.setdefault("database", _db_stub)


from engines.trade_staggerer import TradeStaggerer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTradeStaggererQueueHardening:

    def test_add_to_queue_rejects_empty_bot_id(self):
        """add_to_queue must log a warning and drop entries with an empty bot_id."""
        staggerer = TradeStaggerer()
        run(staggerer.add_to_queue("", "binance"))
        assert len(staggerer.trade_queue) == 0, "Queue must remain empty after rejected entry"

    def test_add_to_queue_rejects_none_bot_id(self):
        """add_to_queue must log a warning and drop entries when bot_id is None."""
        staggerer = TradeStaggerer()
        run(staggerer.add_to_queue(None, "binance"))  # type: ignore[arg-type]
        assert len(staggerer.trade_queue) == 0

    def test_add_to_queue_rejects_empty_exchange(self):
        """add_to_queue must log a warning and drop entries with an empty exchange."""
        staggerer = TradeStaggerer()
        run(staggerer.add_to_queue("bot-123", ""))
        assert len(staggerer.trade_queue) == 0

    def test_add_to_queue_accepts_valid_entry(self):
        """add_to_queue must accept a well-formed entry."""
        staggerer = TradeStaggerer()
        run(staggerer.add_to_queue("bot-abc", "binance"))
        assert len(staggerer.trade_queue) == 1

    def test_get_next_trade_drops_malformed_missing_bot_id(self):
        """get_next_trade must drop queue entries that are missing bot_id."""
        staggerer = TradeStaggerer()
        # Manually inject a malformed entry (bypasses add_to_queue guard)
        staggerer.trade_queue.append({"exchange": "binance", "queued_at": "2025-01-01T00:00:00+00:00"})
        result = run(staggerer.get_next_trade())
        assert result is None, "Malformed entry must be dropped; nothing returned"
        assert len(staggerer.trade_queue) == 0, "Queue must be empty after dropping malformed entry"

    def test_get_next_trade_drops_malformed_missing_exchange(self):
        """get_next_trade must drop queue entries that are missing exchange."""
        staggerer = TradeStaggerer()
        staggerer.trade_queue.append({"bot_id": "bot-xyz", "queued_at": "2025-01-01T00:00:00+00:00"})
        result = run(staggerer.get_next_trade())
        assert result is None
        assert len(staggerer.trade_queue) == 0

    def test_get_next_trade_continues_after_malformed_entry(self):
        """After dropping a malformed entry the loop must continue and return the next valid item."""
        staggerer = TradeStaggerer()

        # First entry is malformed (no bot_id)
        staggerer.trade_queue.append({"exchange": "binance", "queued_at": "2025-01-01T00:00:00+00:00"})
        # Second entry is valid
        staggerer.trade_queue.append({
            "bot_id": "bot-good",
            "exchange": "binance",
            "queued_at": "2025-01-01T00:00:00+00:00",
        })

        # get_next_trade also calls can_execute_now which checks active_trades – bot-good is not
        # locked so it should be eligible.
        result = run(staggerer.get_next_trade())
        # The malformed entry was discarded; the valid one was returned.
        assert result is not None, "Valid entry must be returned after malformed entry is dropped"
        assert result.get("bot_id") == "bot-good"

    def test_scheduler_loop_does_not_crash_on_malformed_queue(self):
        """Simulate multiple malformed entries: get_next_trade must not raise."""
        staggerer = TradeStaggerer()
        for _ in range(10):
            staggerer.trade_queue.append({"junk": "data"})  # completely missing fields

        # Must not raise; should return None after exhausting the queue
        result = run(staggerer.get_next_trade())
        assert result is None
        assert len(staggerer.trade_queue) == 0, "All malformed entries must be purged"
