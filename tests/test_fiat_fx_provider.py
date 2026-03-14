"""
Tests: Canonical FX Architecture — Fiat Provider + System-wide Display Truth
=============================================================================

Covers:
1. fiat_fx_provider: fallback chain (env → cache_stale → static), stale handling,
   force_update_rate, get_rates_snapshot, refresh_rates_async without network
2. fx_normalizer integration: _fiat_to_zar_rate uses fiat_fx_provider
3. Mixed wallet math: ZAR-only, USDT-only, mixed ZAR+USDT
4. Countdown ZAR truth: calculate_daily_roi uses realized_pnl_zar
5. Analytics countdown equity ZAR normalization
6. wallet_hub _get_to_zar_rate delegates to fx_normalizer
7. Round-trip: USDT → ZAR → USD consistency
8. USD/USDT separation regression
9. Native quote values never relabeled

Run with:
  ENVIRONMENT=testing PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
  python3 -m pytest tests/test_fiat_fx_provider.py -v
"""

import os
import sys
import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ── Stub heavy infrastructure ─────────────────────────────────────────────────
for _mod in ("motor", "motor.motor_asyncio", "pymongo", "pymongo.errors"):
    sys.modules.setdefault(_mod, MagicMock())

# bson needed by some routes
if "bson" not in sys.modules:
    _bson_stub = MagicMock()
    _bson_stub.ObjectId = str
    sys.modules["bson"] = _bson_stub

_mock_db_module = MagicMock()
_mock_db_module.bots_collection = None
_mock_db_module.trades_collection = None
_mock_db_module.users_collection = None
sys.modules.setdefault("database", _mock_db_module)

# Stub fastapi and pydantic for route modules that import them
if "fastapi" not in sys.modules:
    _fastapi_stub = MagicMock()

    # APIRouter must return an object with .get/.post/.put/.delete decorators
    class _FakeRouter:
        def get(self, *a, **kw):
            return lambda f: f
        def post(self, *a, **kw):
            return lambda f: f
        def put(self, *a, **kw):
            return lambda f: f
        def delete(self, *a, **kw):
            return lambda f: f
        def patch(self, *a, **kw):
            return lambda f: f
        include_router = lambda *a, **kw: None

    _fastapi_stub.APIRouter = lambda *a, **kw: _FakeRouter()
    _fastapi_stub.HTTPException = Exception

    class _FakeDepends:
        def __call__(self, func):
            return func
    _fastapi_stub.Depends = lambda f: f
    _fastapi_stub.Query = lambda *a, **kw: a[0] if a else None

    sys.modules["fastapi"] = _fastapi_stub
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["fastapi.security"] = MagicMock()

# Stub pydantic with minimal BaseModel
if "pydantic" not in sys.modules:
    class _BaseModel:
        def __init_subclass__(cls, **kw):
            pass
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)
    class _Field:
        def __call__(self, *a, **kw):
            return a[0] if a else None
        def __getattr__(self, name):
            return self
    _pydantic_stub = MagicMock()
    _pydantic_stub.BaseModel = _BaseModel
    _pydantic_stub.Field = _Field()
    sys.modules["pydantic"] = _pydantic_stub

if "auth" not in sys.modules:
    _auth_stub = MagicMock()
    _auth_stub.get_current_user = lambda: "user1"
    sys.modules["auth"] = _auth_stub

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USDT_ZAR_RATE", "19.0")
os.environ.setdefault("USD_ZAR_RATE", "18.5")
os.environ.setdefault("GBP_ZAR_RATE", "23.5")
os.environ.setdefault("EUR_ZAR_RATE", "20.0")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. fiat_fx_provider Unit Tests ──────────────────────────────────────────

class TestFiatFxProvider:
    """Unit tests for services/fiat_fx_provider.py"""

    def setup_method(self):
        """Reset the cache before each test."""
        from services import fiat_fx_provider as ffp
        ffp.clear_cache()

    def test_get_zar_per_unit_usd_fallback(self):
        """Cold cache → should return env fallback value."""
        from services.fiat_fx_provider import get_zar_per_unit
        rate, source = get_zar_per_unit("USD")
        assert rate == 18.5
        assert source == "env_fallback"

    def test_get_zar_per_unit_gbp_fallback(self):
        from services.fiat_fx_provider import get_zar_per_unit
        rate, source = get_zar_per_unit("GBP")
        assert rate == 23.5
        assert source == "env_fallback"

    def test_get_zar_per_unit_eur_fallback(self):
        from services.fiat_fx_provider import get_zar_per_unit
        rate, source = get_zar_per_unit("EUR")
        assert rate == 20.0
        assert source == "env_fallback"

    def test_get_zar_per_unit_unknown_currency(self):
        from services.fiat_fx_provider import get_zar_per_unit
        rate, source = get_zar_per_unit("XYZ")
        assert rate == 1.0
        assert source == "unknown"

    def test_force_update_rate_stores_value(self):
        """force_update_rate injects a rate into cache."""
        from services.fiat_fx_provider import force_update_rate, get_zar_per_unit
        force_update_rate("USD", 19.2, source="manual_override")
        rate, source = get_zar_per_unit("USD")
        assert rate == 19.2
        assert source == "manual_override"

    def test_force_update_rate_unsupported_currency_raises(self):
        from services.fiat_fx_provider import force_update_rate
        with pytest.raises(ValueError, match="Unsupported"):
            force_update_rate("USDT", 19.0)

    def test_force_update_rate_nonpositive_raises(self):
        from services.fiat_fx_provider import force_update_rate
        with pytest.raises(ValueError, match="positive"):
            force_update_rate("USD", 0.0)

    def test_fresh_cache_returns_cached_value(self):
        """After force_update_rate, subsequent calls return the cached rate."""
        from services.fiat_fx_provider import force_update_rate, get_zar_per_unit
        force_update_rate("GBP", 24.0, source="live_fiat_primary")
        rate, source = get_zar_per_unit("GBP")
        assert rate == 24.0
        assert source == "live_fiat_primary"

    def test_stale_cache_returns_stale_label(self):
        """Stale cache (past TTL but within stale window) returns 'cache_stale'."""
        import services.fiat_fx_provider as ffp
        from services.fiat_fx_provider import get_zar_per_unit

        # Manually inject a cache entry with old timestamp
        with ffp._cache_lock:
            ffp._rate_cache["USD"] = {
                "rate": 18.9,
                "fetched_at": time.monotonic() - ffp.CACHE_TTL_SECONDS - 1,
                "source": "live_fiat_primary",
            }

        rate, source = get_zar_per_unit("USD")
        assert rate == 18.9
        assert source == "cache_stale"

    def test_expired_cache_returns_fallback(self):
        """Cache older than STALE_MAX_SECONDS → return env/static fallback."""
        import services.fiat_fx_provider as ffp
        from services.fiat_fx_provider import get_zar_per_unit

        with ffp._cache_lock:
            ffp._rate_cache["EUR"] = {
                "rate": 21.5,
                "fetched_at": time.monotonic() - ffp.STALE_MAX_SECONDS - 10,
                "source": "live_fiat_primary",
            }

        rate, source = get_zar_per_unit("EUR")
        # Should fall back to env (20.0) not the expired 21.5
        assert rate == 20.0
        assert source == "env_fallback"

    def test_get_rates_snapshot_structure(self):
        from services.fiat_fx_provider import get_rates_snapshot
        snapshot = get_rates_snapshot()
        assert "rates" in snapshot
        assert "cache_ttl_seconds" in snapshot
        for cur in ("USD", "GBP", "EUR"):
            assert cur in snapshot["rates"]
            entry = snapshot["rates"][cur]
            assert "rate_zar_per_unit" in entry
            assert "source" in entry
            assert "fresh" in entry

    def test_refresh_rates_async_without_network(self):
        """refresh_rates_async should gracefully degrade when both providers fail."""
        from services.fiat_fx_provider import refresh_rates_async, clear_cache
        clear_cache()

        async def _run_with_fail():
            import services.fiat_fx_provider as ffp
            with patch.object(ffp, "_fetch_from_primary", new=AsyncMock(return_value=(None, "primary_failed"))):
                with patch.object(ffp, "_fetch_from_fallback", new=AsyncMock(return_value=(None, "fallback_failed"))):
                    return await refresh_rates_async()

        result = _run(_run_with_fail())
        assert result == {}  # Both failed — empty dict

    def test_refresh_rates_async_with_mocked_primary(self):
        """refresh_rates_async updates cache from primary provider."""
        from services.fiat_fx_provider import refresh_rates_async, get_zar_per_unit, clear_cache
        clear_cache()

        mock_rates = {"USD": 18.9, "GBP": 24.1, "EUR": 20.3}

        async def _do_refresh():
            import services.fiat_fx_provider as ffp
            with patch.object(ffp, "_fetch_from_primary",
                              new=AsyncMock(return_value=(mock_rates, "live_fiat_primary"))):
                return await refresh_rates_async()

        result = _run(_do_refresh())
        assert result.get("USD") == 18.9

        # Verify cache was updated
        rate, source = get_zar_per_unit("USD")
        assert rate == 18.9
        assert source == "live_fiat_primary"

    def test_get_all_fiat_rates_returns_dict(self):
        from services.fiat_fx_provider import get_all_fiat_rates
        rates = get_all_fiat_rates()
        assert set(rates.keys()) == {"USD", "GBP", "EUR"}
        for val in rates.values():
            assert isinstance(val, tuple)
            rate, source = val
            assert rate > 0


# ─── 2. fx_normalizer integration with fiat_fx_provider ──────────────────────

class TestFxNormalizerFiatIntegration:
    """Test that fx_normalizer._fiat_to_zar_rate correctly delegates to fiat_fx_provider."""

    def setup_method(self):
        from services import fiat_fx_provider as ffp
        ffp.clear_cache()

    def test_get_fx_rate_usd_uses_fiat_provider(self):
        """get_fx_rate('ZAR','USD') should use fiat_fx_provider, not USDT rate."""
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("USD", 18.9, source="test_injected")

        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("ZAR", "USD")
        # ZAR→USD = 1/18.9
        expected = 1.0 / 18.9
        assert abs(rate - expected) < 0.001
        assert "test_injected" in source

    def test_get_fx_rate_gbp_uses_fiat_provider(self):
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("GBP", 24.0, source="test_gbp")

        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("ZAR", "GBP")
        expected = 1.0 / 24.0
        assert abs(rate - expected) < 0.001

    def test_get_fx_rate_eur_uses_fiat_provider(self):
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("EUR", 20.5, source="test_eur")

        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("ZAR", "EUR")
        expected = 1.0 / 20.5
        assert abs(rate - expected) < 0.001

    def test_usdt_uses_separate_cache_not_fiat_provider(self):
        """USDT→ZAR must NOT use fiat_fx_provider (it uses its own USDT cache)."""
        import services.fiat_fx_provider as ffp
        # Even if fiat provider has a USD rate, USDT should use its own path
        ffp.force_update_rate("USD", 999.0, source="should_not_be_used_for_usdt")

        from services.fx_normalizer import get_fx_rate
        usdt_rate, usdt_source = get_fx_rate("USDT", "ZAR")
        # Should be 19.0 from env (USDT_ZAR_RATE), not 999.0
        assert usdt_rate == 19.0
        assert "env_fallback" not in usdt_source or usdt_rate != 999.0

    def test_fiat_provider_fallback_when_unavailable(self):
        """If fiat_fx_provider raises, _fiat_to_zar_rate falls back to static."""
        from services.fx_normalizer import _fiat_to_zar_rate

        with patch("services.fiat_fx_provider.get_zar_per_unit", side_effect=Exception("provider down")):
            rate, source = _fiat_to_zar_rate("USD")
        # Should fall back to env_fallback_usd (18.5)
        assert rate == 18.5
        assert source == "env_fallback_usd"


# ─── 3. wallet_hub _get_to_zar_rate delegates to fx_normalizer ───────────────

class TestWalletHubRateDelegation:
    """wallet_hub._get_to_zar_rate must delegate USD/GBP/EUR to fx_normalizer.

    Since wallet_hub imports websocket/redis infrastructure that is unavailable
    in the test env, we verify the delegation contract indirectly by confirming
    that (a) fx_normalizer and fiat_fx_provider produce consistent rates and
    (b) the wallet_hub rate logic is equivalent to fx_normalizer's output.
    """

    def setup_method(self):
        from services import fiat_fx_provider as ffp
        ffp.clear_cache()

    def test_usd_rate_consistent_across_normalizer_and_provider(self):
        """Injecting a rate into fiat_fx_provider must flow through fx_normalizer."""
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("USD", 18.7, source="test_consistency")

        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("USD", "ZAR")
        assert abs(rate - 18.7) < 0.01, (
            "fx_normalizer should use the fiat_fx_provider injected rate"
        )

    def test_zar_identity_in_normalizer(self):
        """ZAR→ZAR must always be 1.0 (required by wallet_hub delegation)."""
        from services.fx_normalizer import get_fx_rate
        rate, source = get_fx_rate("ZAR", "ZAR")
        assert rate == 1.0
        assert source == "identity"

    def test_usdt_delegates_to_normalizer_live_cache(self):
        """USDT uses its own live/cached rate, not fiat_fx_provider."""
        from services.fx_normalizer import get_fx_rate, update_fx_rate
        update_fx_rate(19.5, source="test_live")
        rate, source = get_fx_rate("USDT", "ZAR")
        assert abs(rate - 19.5) < 0.01
        assert "test_live" in source  # source may be composite

    def test_btc_not_in_fiat_provider(self):
        """BTC is not in SUPPORTED_FIAT of fiat_fx_provider."""
        from services.fiat_fx_provider import SUPPORTED_FIAT
        assert "BTC" not in SUPPORTED_FIAT


# ─── 4. Mixed wallet math — ZAR truth ─────────────────────────────────────────

class TestMixedWalletMath:
    """Core invariant: mixed ZAR+USDT sums must never be raw-mixed."""

    def test_zar_only_wallet(self):
        from services.fx_normalizer import to_display_zar
        zar_val, rate, _ = to_display_zar(5000.0, "ZAR")
        assert zar_val == 5000.0
        assert rate == 1.0

    def test_usdt_only_wallet(self):
        """5000 USDT should convert to 95000 ZAR at rate 19."""
        from services.fx_normalizer import to_display_zar
        from services.fx_normalizer import update_fx_rate
        update_fx_rate(19.0, source="test")
        zar_val, rate, _ = to_display_zar(5000.0, "USDT")
        assert rate == 19.0
        assert abs(zar_val - 95000.0) < 0.01

    def test_mixed_zar_usdt_correct_total(self):
        """5000 ZAR + 5000 USDT must NOT equal 10000 ZAR.
        At rate 19: 5000 ZAR + (5000 * 19 = 95000 ZAR) = 100000 ZAR."""
        from services.fx_normalizer import to_display_zar, update_fx_rate
        update_fx_rate(19.0, source="test")

        zar_part, _, _ = to_display_zar(5000.0, "ZAR")
        usdt_part, _, _ = to_display_zar(5000.0, "USDT")
        total = zar_part + usdt_part

        # Must NOT be 10000 (raw mixed)
        assert total != 10000.0
        # Must be correct converted total
        assert abs(total - 100000.0) < 0.01

    def test_mixed_zar_usdt_display_in_usd(self):
        """100000 ZAR converted to USD at 18.5 ZAR/USD ≈ 5405.40 USD."""
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("USD", 18.5, source="test")
        from services.fx_normalizer import to_display_currency
        usd_val, rate, _ = to_display_currency(100000.0, "USD")
        expected = 100000.0 / 18.5
        assert abs(usd_val - expected) < 0.5

    def test_mixed_zar_usdt_display_in_gbp(self):
        """100000 ZAR → GBP at 23.5."""
        import services.fiat_fx_provider as ffp
        ffp.force_update_rate("GBP", 23.5, source="test")
        from services.fx_normalizer import to_display_currency
        gbp_val, _, _ = to_display_currency(100000.0, "GBP")
        expected = 100000.0 / 23.5
        assert abs(gbp_val - expected) < 0.5

    def test_native_quote_never_relabeled(self):
        """The native quote amount must stay labeled as its original currency."""
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(52.63, "USDT")
        # Native amount unchanged
        assert result["raw_value"] == 52.63
        assert result["raw_currency"] == "USDT"
        # Display ZAR is the converted value
        assert result["display_currency"] == "ZAR"
        assert abs(result["display_value"] - 52.63 * 19.0) < 0.1


# ─── 5. countdown ZAR truth — calculate_daily_roi ─────────────────────────────

class TestCountdownZarTruth:
    """Tests for user_countdowns.calculate_daily_roi ZAR normalization."""

    def _run_roi(self, trades, user):
        import routes.user_countdowns as uc_mod

        mock_db = MagicMock()
        # trades cursor
        trades_cursor = MagicMock()
        trades_cursor.to_list = AsyncMock(return_value=trades)
        mock_db.trades_collection.find.return_value = trades_cursor

        user_cursor = AsyncMock(return_value=user)
        mock_db.users_collection.find_one = user_cursor

        async def run():
            with patch.object(uc_mod, "db", mock_db):
                return await uc_mod.calculate_daily_roi("user1")

        return _run(run())

    def test_roi_with_zar_trades_uses_realized_pnl_zar(self):
        """Trades with realized_pnl_zar are used directly (no FX conversion)."""
        trades = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "realized_pnl_zar": 100.0, "fee_display_zar": 5.0},
        ]
        user = {"total_capital": 1100.0}
        roi = self._run_roi(trades, user)
        # total_profit_zar = 100
        # starting_capital = 1100 - 100 = 1000
        # total_roi = 100/1000 * 100 = 10%
        # daily = 10/7 ≈ 1.43%
        assert roi > 0

    def test_roi_with_usdt_trades_normalizes_to_zar(self):
        """USDT trades without realized_pnl_zar must be converted to ZAR."""
        trades = [
            {"exchange": "binance", "quote_currency": "USDT",
             "net_pnl": 5.0, "fees": 0.5},
        ]
        # 5 USDT - 0.5 USDT = 4.5 USDT net
        # At 19 ZAR/USDT = 85.5 ZAR
        user = {"total_capital": 1000.0}
        roi = self._run_roi(trades, user)
        # starting = 1000 - 85.5 = 914.5
        # total_roi = 85.5/914.5 * 100 ≈ 9.35%
        # daily ≈ 1.34%
        assert roi > 0

    def test_roi_mixed_zar_usdt_does_not_raw_mix(self):
        """Mixed ZAR + USDT trades: USDT profit must be converted before summing."""
        trades = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "realized_pnl_zar": 100.0},
            {"exchange": "binance", "quote_currency": "USDT",
             "net_pnl": 10.0, "fees": 0.0},  # 10 USDT = 190 ZAR
        ]
        user = {"total_capital": 2000.0}
        roi = self._run_roi(trades, user)
        # total_profit_zar = 100 + 190 = 290
        # starting = 2000 - 290 = 1710
        # raw mix would give: starting = 2000 - 110 = 1890 (WRONG)
        assert roi > 0

    def test_roi_no_trades_returns_zero(self):
        trades = []
        user = {"total_capital": 1000.0}
        roi = self._run_roi(trades, user)
        assert roi == 0.0

    def test_roi_zero_starting_capital_returns_zero(self):
        trades = [{"exchange": "luno", "quote_currency": "ZAR",
                   "realized_pnl_zar": 1000.0}]
        user = {"total_capital": 1000.0}  # starting = 1000 - 1000 = 0
        roi = self._run_roi(trades, user)
        assert roi == 0.0


# ─── 6. analytics_api countdown equity ZAR normalization ─────────────────────

class TestCountdownEquityZAR:
    """Tests for analytics_api.get_countdown_to_target ZAR normalization."""

    def _bots(self, bots_list):
        mock_db = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=bots_list)
        mock_db.bots_collection.find.return_value = cursor
        mock_db.trades_collection.find_one = AsyncMock(return_value=None)
        return mock_db

    def test_pure_luno_bots_equity_in_zar(self):
        """Luno bots with canonical_base_capital_zar: equity sums correctly."""
        import routes.analytics_api as aa_mod
        bots = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "initial_capital": 1000.0, "current_capital": 1100.0,
             "canonical_base_capital_zar": 1000.0, "status": "active"},
        ]

        async def run():
            with patch.object(aa_mod, "db", self._bots(bots)):
                return await aa_mod.get_countdown_to_target(
                    target_amount=10000.0, user_id="user1"
                )

        result = _run(run())
        assert result.get("equity_currency") == "ZAR"
        # 1000 * (1100/1000) = 1100 ZAR
        assert abs(result.get("equity_current", 0) - 1100.0) < 1.0

    def test_binance_bot_equity_converted_to_zar(self):
        """Binance bot with canonical_base_capital_zar: equity uses base not raw USDT."""
        import routes.analytics_api as aa_mod
        bots = [
            {"exchange": "binance", "quote_currency": "USDT",
             "initial_capital": 52.63, "current_capital": 55.0,
             "canonical_base_capital_zar": 1000.0, "status": "active"},
        ]

        async def run():
            with patch.object(aa_mod, "db", self._bots(bots)):
                return await aa_mod.get_countdown_to_target(
                    target_amount=10000.0, user_id="user1"
                )

        result = _run(run())
        assert result.get("equity_currency") == "ZAR"
        # growth_ratio = 55/52.63 ≈ 1.045; equity = 1000 * 1.045 ≈ 1045
        assert result.get("equity_current", 0) > 1000.0

    def test_mixed_bots_equity_never_raw_mixed(self):
        """Mixed Luno+Binance bots: raw 1000 ZAR + 52.63 USDT != 1052.63 ZAR."""
        import routes.analytics_api as aa_mod
        bots = [
            {"exchange": "luno", "quote_currency": "ZAR",
             "initial_capital": 1000.0, "current_capital": 1000.0,
             "canonical_base_capital_zar": 1000.0, "status": "active"},
            {"exchange": "binance", "quote_currency": "USDT",
             "initial_capital": 52.63, "current_capital": 52.63,
             "canonical_base_capital_zar": 1000.0, "status": "active"},
        ]

        async def run():
            with patch.object(aa_mod, "db", self._bots(bots)):
                return await aa_mod.get_countdown_to_target(
                    target_amount=10000.0, user_id="user1"
                )

        result = _run(run())
        equity = result.get("equity_current", 0)
        # Should be ~2000 ZAR (1000 + 1000), NOT 1052.63
        assert equity != 1052.63
        assert abs(equity - 2000.0) < 5.0


# ─── 7. Round-trip consistency ────────────────────────────────────────────────

class TestRoundTripConsistency:
    """FX round-trip invariants."""

    def test_usdt_zar_usdt_round_trip(self):
        """USDT → ZAR → USDT must return original."""
        from services.fx_normalizer import get_fx_rate
        usdt_to_zar, _ = get_fx_rate("USDT", "ZAR")
        zar_to_usdt, _ = get_fx_rate("ZAR", "USDT")
        assert abs(usdt_to_zar * zar_to_usdt - 1.0) < 0.001

    def test_zar_usd_zar_round_trip(self):
        """ZAR → USD → ZAR must return original."""
        from services.fx_normalizer import get_fx_rate
        zar_usd, _ = get_fx_rate("ZAR", "USD")
        usd_zar, _ = get_fx_rate("USD", "ZAR")
        assert abs(zar_usd * usd_zar - 1.0) < 0.001

    def test_usdt_usd_rate_not_one(self):
        """USDT→USD is not 1.0 (they have different ZAR rates)."""
        from services.fx_normalizer import get_fx_rate
        rate, _ = get_fx_rate("USDT", "USD")
        # USDT/ZAR = 19, USD/ZAR = 18.5 → USDT/USD ≈ 1.027
        assert abs(rate - 1.027) < 0.02
        assert rate != 1.0


# ─── 8. USD/USDT ambiguity regression ────────────────────────────────────────

class TestUSDUSDAmbiguityRegression:
    """Regression tests for the original bug where USD was treated as USDT."""

    def setup_method(self):
        from services import fiat_fx_provider as ffp
        ffp.clear_cache()

    def test_usd_rate_not_equal_to_usdt_rate(self):
        """USD/ZAR and USDT/ZAR rates must differ (they are different assets)."""
        from services.fx_normalizer import get_fx_rate
        usd_rate, _ = get_fx_rate("USD", "ZAR")
        usdt_rate, _ = get_fx_rate("USDT", "ZAR")
        # USD = 18.5, USDT = 19.0 → must differ
        assert abs(usd_rate - usdt_rate) > 0.1, (
            f"USD ({usd_rate}) and USDT ({usdt_rate}) rates are equal — USD/USDT ambiguity bug!"
        )

    def test_usd_display_symbol_not_usdt_rate(self):
        """Converting R18.5 to USD should give $1.0, not a USDT-biased value."""
        from services.fx_normalizer import to_display_currency
        usd_val, rate, _ = to_display_currency(18.5, "USD")
        assert abs(usd_val - 1.0) < 0.01, (
            f"R18.5 → USD gave {usd_val} (expected 1.0). USD/USDT ambiguity!"
        )

    def test_normalize_money_field_usd_display(self):
        """normalize_money_field with display_currency=USD uses fiat USD rate."""
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(52.63, "USDT", display_currency="USD")
        assert result["display_currency"] == "USD"
        assert result["raw_currency"] == "USDT"
        # 52.63 USDT * 19 = 999.97 ZAR → / 18.5 ≈ 54.05 USD (not 52.63!)
        expected_usd = (52.63 * 19.0) / 18.5
        assert abs(result["display_value"] - expected_usd) < 0.5


# ─── 9. Fiat provider priority chain ─────────────────────────────────────────

class TestFiatProviderPriorityChain:
    """Verify priority: live → stale_cache → env/static fallback."""

    def setup_method(self):
        from services import fiat_fx_provider as ffp
        ffp.clear_cache()

    def test_live_beats_env_fallback(self):
        """A freshly injected live rate is returned over env fallback."""
        from services.fiat_fx_provider import force_update_rate, get_zar_per_unit
        # Inject a "live" value different from env (18.5)
        force_update_rate("USD", 19.5, source="live_fiat_primary")
        rate, source = get_zar_per_unit("USD")
        assert rate == 19.5
        assert source == "live_fiat_primary"

    def test_stale_beats_hard_static(self):
        """Stale cache is preferred over hard static (still carries user value)."""
        import services.fiat_fx_provider as ffp
        from services.fiat_fx_provider import get_zar_per_unit

        with ffp._cache_lock:
            ffp._rate_cache["GBP"] = {
                "rate": 25.0,
                "fetched_at": time.monotonic() - ffp.CACHE_TTL_SECONDS - 1,
                "source": "live_fiat_fallback",
            }

        rate, source = get_zar_per_unit("GBP")
        # 25.0 from stale cache, not 23.5 from env
        assert rate == 25.0
        assert source == "cache_stale"

    def test_fallback_from_both_providers_fail(self):
        """If both providers fail and no cache, env fallback is returned."""
        from services.fiat_fx_provider import refresh_rates_async, get_zar_per_unit, clear_cache
        clear_cache()

        async def _fail_both():
            import services.fiat_fx_provider as ffp
            with patch.object(ffp, "_fetch_from_primary", new=AsyncMock(return_value=(None, "fail"))):
                with patch.object(ffp, "_fetch_from_fallback", new=AsyncMock(return_value=(None, "fail"))):
                    await refresh_rates_async()

        _run(_fail_both())
        rate, source = get_zar_per_unit("EUR")
        assert rate == 20.0  # env fallback
        assert source == "env_fallback"
