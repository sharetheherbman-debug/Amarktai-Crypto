"""
Tests for problem-statement requirements D, E, F:

D. Luno ticker caching/throttling
   4) Luno ticker requests are cached/throttled and do not spam repeated calls
   5) Scheduler diagnostics expose true noop reasons

E. Scheduler / Queue Truth
   5) scheduler diagnostics expose true noop reasons (skip-reason categories)

F. Reason Codes / Truth Surfaces
   6) New reason codes are present in REASON_CATALOG
"""

import asyncio
import os
import time
import pytest

os.environ.setdefault("LUNO_TICKER_TTL_SECONDS", "20")
os.environ.setdefault("LUNO_TICKER_STALE_SECONDS", "120")


# ── D. Luno Ticker Cache ──────────────────────────────────────────────────────

class TestLunoTickerCache:
    """Verify the shared TTL cache prevents request storms."""

    def setup_method(self):
        # Import fresh each time and clear state
        from services import luno_ticker_cache as tc
        tc.clear_cache()
        self._tc = tc

    def _make_mock_ticker(self, price=50000.0):
        return {
            "last_trade": price,
            "bid": price - 10,
            "ask": price + 10,
            "rolling_24_hour_volume": 1.5,
            "source": "luno_public",
        }

    def test_cache_stores_entry_after_fetch(self):
        """After populating the cache directly, cache_stats reflects the entry."""
        tc = self._tc
        ticker = self._make_mock_ticker(49000.0)
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        stats = tc.cache_stats()
        assert "XBTZAR" in stats
        assert stats["XBTZAR"]["last_trade"] == 49000.0
        assert stats["XBTZAR"]["age_seconds"] >= 0

    def test_cache_is_fresh_within_ttl(self):
        """Entry fetched within TTL is considered fresh."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        entry = tc._cache["XBTZAR"]
        assert tc._is_fresh(entry) is True

    def test_cache_is_stale_after_ttl(self):
        """Entry older than TTL is NOT fresh."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        # Pretend entry was fetched 100 seconds ago (TTL default is 20s)
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic() - 100}
        entry = tc._cache["XBTZAR"]
        assert tc._is_fresh(entry) is False

    def test_within_stale_window_for_fallback(self):
        """Entry older than TTL but younger than STALE_FALLBACK is in stale window."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        # 50 seconds old, TTL=20s, STALE_FALLBACK=120s → within stale window
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic() - 50}
        entry = tc._cache["XBTZAR"]
        assert tc._is_fresh(entry) is False
        assert tc._is_within_stale_window(entry) is True

    def test_clear_single_pair(self):
        """clear_cache(pair) removes only that entry."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        tc._cache["ETHZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        tc.clear_cache("XBTZAR")
        assert "XBTZAR" not in tc._cache
        assert "ETHZAR" in tc._cache

    def test_clear_all_pairs(self):
        """clear_cache() with no args clears everything."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        tc._cache["ETHZAR"] = {"data": ticker, "fetched_at": time.monotonic()}
        tc.clear_cache()
        assert tc._cache == {}

    def test_get_ticker_returns_cached_on_fresh_hit(self):
        """get_ticker returns cache source when entry is fresh — no HTTP call."""
        tc = self._tc
        ticker = self._make_mock_ticker(75000.0)
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic()}

        result = asyncio.get_event_loop().run_until_complete(tc.get_ticker("XBTZAR"))
        assert result is not None
        assert result["source"] == "cache"
        assert result["last_trade"] == 75000.0

    def test_get_ticker_returns_none_when_no_cache_and_network_fails(self, monkeypatch):
        """When cache is empty and network raises, get_ticker returns None."""
        tc = self._tc
        tc.clear_cache()

        async def _fail(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(tc, "_fetch_from_luno", _fail)
        result = asyncio.get_event_loop().run_until_complete(tc.get_ticker("XBTZAR"))
        assert result is None

    def test_get_ticker_returns_stale_on_network_error(self, monkeypatch):
        """When cache exists but is stale, and network fails, stale value is returned."""
        import httpx
        tc = self._tc
        ticker = self._make_mock_ticker(42000.0)
        # Place entry that is 50 s old (stale but within STALE_FALLBACK=120s window)
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic() - 50}

        async def _fail(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(tc, "_fetch_from_luno", _fail)
        result = asyncio.get_event_loop().run_until_complete(tc.get_ticker("XBTZAR"))
        assert result is not None
        assert result["source"] == "cache_stale_fallback"
        assert result["last_trade"] == 42000.0

    def test_get_ticker_429_returns_stale_with_429_source(self, monkeypatch):
        """HTTP 429 returns cached value with source=cache_429_fallback."""
        import httpx
        tc = self._tc
        ticker = self._make_mock_ticker(55000.0)
        tc._cache["XBTZAR"] = {"data": ticker, "fetched_at": time.monotonic() - 50}

        async def _rate_limited(*args, **kwargs):
            resp = httpx.Response(429, request=httpx.Request("GET", "https://api.luno.com"))
            raise httpx.HTTPStatusError("429", request=resp.request, response=resp)

        monkeypatch.setattr(tc, "_fetch_from_luno", _rate_limited)
        result = asyncio.get_event_loop().run_until_complete(tc.get_ticker("XBTZAR"))
        assert result is not None
        assert result["source"] == "cache_429_fallback"
        assert result["last_trade"] == 55000.0

    def test_multiple_calls_within_ttl_do_not_fetch_twice(self, monkeypatch):
        """Two consecutive get_ticker calls within TTL window only trigger one fetch."""
        tc = self._tc
        tc.clear_cache()
        fetch_count = {"n": 0}

        async def _mock_fetch(*args, **kwargs):
            fetch_count["n"] += 1
            return {
                "last_trade": 60000.0,
                "bid": 59990.0,
                "ask": 60010.0,
                "rolling_24_hour_volume": 2.0,
                "source": "luno_public",
            }

        monkeypatch.setattr(tc, "_fetch_from_luno", _mock_fetch)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(tc.get_ticker("XBTZAR"))
        loop.run_until_complete(tc.get_ticker("XBTZAR"))
        loop.run_until_complete(tc.get_ticker("XBTZAR"))

        # Should only have fetched once (subsequent calls hit the fresh cache)
        assert fetch_count["n"] == 1

    def test_cache_stats_reflects_all_pairs(self):
        """cache_stats returns an entry for each cached pair."""
        tc = self._tc
        ticker = self._make_mock_ticker()
        for pair in ["XBTZAR", "ETHZAR", "XRPZAR"]:
            tc._cache[pair] = {"data": ticker, "fetched_at": time.monotonic()}
        stats = tc.cache_stats()
        assert set(stats.keys()) == {"XBTZAR", "ETHZAR", "XRPZAR"}


# ── E. Scheduler Skip-Reason Classification ───────────────────────────────────

class TestSchedulerSkipReasonClassification:
    """Verify classify_skip_reason maps raw reasons to canonical categories."""

    def test_economics_keywords_classified_correctly(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_ECONOMICS
        counts = {}
        for reason in ["trade_worth_filter", "edge_gate", "abs_profit_too_small",
                       "insufficient_net_expectancy", "low_entry_confidence",
                       "scalper_low_confidence"]:
            classify_skip_reason(reason, counts)
        assert counts.get(SKIP_CATEGORY_ECONOMICS, 0) == 6

    def test_cooldown_keywords_classified_correctly(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_COOLDOWN
        counts = {}
        classify_skip_reason("rate_limit_exceeded", counts)
        classify_skip_reason("reentry_cooldown", counts)
        classify_skip_reason("scalper_coverage_throttle", counts)
        assert counts.get(SKIP_CATEGORY_COOLDOWN, 0) == 3

    def test_exposure_keywords_classified_correctly(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_EXPOSURE
        counts = {}
        classify_skip_reason("max_drawdown_exceeded", counts)
        classify_skip_reason("circuit_breaker_triggered", counts)
        assert counts.get(SKIP_CATEGORY_EXPOSURE, 0) == 2

    def test_open_position_keywords_classified_correctly(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_OPEN_POSITION
        counts = {}
        classify_skip_reason("open_position_active", counts)
        classify_skip_reason("already_open_trade", counts)
        assert counts.get(SKIP_CATEGORY_OPEN_POSITION, 0) == 2

    def test_unknown_reason_classified_as_other(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_OTHER
        counts = {}
        classify_skip_reason("some_completely_random_thing", counts)
        assert counts.get(SKIP_CATEGORY_OTHER, 0) == 1

    def test_empty_reason_classified_as_other(self):
        from services.scheduler_diagnostics import classify_skip_reason, SKIP_CATEGORY_OTHER
        counts = {}
        classify_skip_reason("", counts)
        classify_skip_reason(None, counts)
        assert counts.get(SKIP_CATEGORY_OTHER, 0) == 2

    def test_dominant_skip_category_returns_most_common(self):
        from services.scheduler_diagnostics import dominant_skip_category, SKIP_CATEGORY_ECONOMICS, SKIP_CATEGORY_COOLDOWN
        counts = {SKIP_CATEGORY_ECONOMICS: 3, SKIP_CATEGORY_COOLDOWN: 1}
        assert dominant_skip_category(counts) == SKIP_CATEGORY_ECONOMICS

    def test_dominant_skip_category_empty_returns_empty(self):
        from services.scheduler_diagnostics import dominant_skip_category
        assert dominant_skip_category({}) == ""


# ── F. Reason Codes / Truth Surfaces ─────────────────────────────────────────

class TestNewReasonCodesF:
    """Validate the newly added reason codes are present and documented."""

    def test_rate_limited_cache_fallback_in_catalog(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        assert ReasonCodes.RATE_LIMITED_CACHE_FALLBACK in REASON_CATALOG
        assert len(REASON_CATALOG[ReasonCodes.RATE_LIMITED_CACHE_FALLBACK]) > 5

    def test_scheduler_noop_codes_in_catalog(self):
        from services.trading_brain_v2.reason_codes import ReasonCodes, REASON_CATALOG
        for attr in [
            "SCHEDULER_BLOCKED_OPEN_POSITION",
            "SCHEDULER_BLOCKED_COOLDOWN",
            "SCHEDULER_BLOCKED_ECONOMICS",
            "SCHEDULER_BLOCKED_EXPOSURE",
            "SCHEDULER_DEFERRED_STAGGERER",
        ]:
            code = getattr(ReasonCodes, attr)
            assert code in REASON_CATALOG, f"Missing catalog entry for {attr}"
            assert len(REASON_CATALOG[code]) > 5, f"Empty catalog text for {attr}"

    def test_safe_reason_text_for_new_codes(self):
        from services.trading_brain_v2.reason_codes import safe_reason_text, ReasonCodes
        text = safe_reason_text(ReasonCodes.RATE_LIMITED_CACHE_FALLBACK)
        assert text and ("429" in text.lower() or "rate" in text.lower())


# ── A. Paper hold cap ≤ 20 min ────────────────────────────────────────────────

class TestPaperHoldCapTightened:
    """Paper hold cap default should be ≤ 1200s (20 min) per spec requirement A."""

    def test_paper_cap_default_is_at_most_1200s(self):
        """Default PAPER_NORMAL_MAX_HOLD_SECONDS must be ≤ 1200s (20 min)."""
        import os
        os.environ.pop("PAPER_NORMAL_MAX_HOLD_SECONDS", None)
        import importlib
        import services.hold_policy as hp
        importlib.reload(hp)
        assert hp.PAPER_NORMAL_MAX_HOLD_SECONDS <= 1200, (
            f"Paper hold cap {hp.PAPER_NORMAL_MAX_HOLD_SECONDS}s exceeds 1200s (20 min) spec limit"
        )

    def test_paper_cap_is_not_the_old_21600s(self):
        """Ensure we have NOT reverted to the old 6-hour default."""
        import os
        os.environ.pop("PAPER_NORMAL_MAX_HOLD_SECONDS", None)
        import importlib
        import services.hold_policy as hp
        importlib.reload(hp)
        assert hp.PAPER_NORMAL_MAX_HOLD_SECONDS != 21600, (
            "Paper hold cap reverted to old 6-hour default!"
        )
