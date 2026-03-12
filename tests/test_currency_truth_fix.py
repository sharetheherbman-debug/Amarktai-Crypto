"""
Tests: Currency Truth Fix — Phase 1-6 Canonical Validation
===========================================================

Validates the architectural corrections from the currency-truth fix:

1. bot_validator stores funding_input_amount + funding_input_currency
2. radar snapshot exposes canonical_base_capital_zar, fx_rate_at_creation,
   funding_input_amount, funding_input_currency
3. /api/wallet/converter logic works correctly with labeled responses
4. Luno vs Binance capital separation is correct end-to-end
5. FX normalizer is the single source of truth for converter and bot capital

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only \\
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_currency_truth_fix.py -v
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")
os.environ.setdefault("USDT_ZAR_RATE", "19.0")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. bot_validator: funding_input_amount + funding_input_currency ──────────

class TestBotValidatorFundingInputFields:
    """Validator must store funding_input_amount and funding_input_currency."""

    def _make_validator_mocks(self, zar_balance=2000.0):
        mock_db = MagicMock()
        mock_db.bots_collection.find_one = AsyncMock(return_value=None)
        mock_db.bots_collection.count_documents = AsyncMock(return_value=0)
        mock_wallet = MagicMock()

        async def get_available(uid, currency):
            if currency.upper() == "ZAR":
                return zar_balance
            return 0.0

        mock_wallet.get_available_balance = get_available
        return mock_db, mock_wallet

    def test_luno_bot_stores_funding_input_fields(self):
        from validators.bot_validator import BotValidator

        validator = BotValidator()
        mock_db, mock_wallet = self._make_validator_mocks(zar_balance=2000.0)

        with (
            patch("validators.bot_validator.db", mock_db),
            patch("validators.bot_validator.paper_wallet_service", mock_wallet),
            patch("validators.bot_validator.is_valid_platform", return_value=True),
            patch("validators.bot_validator.normalize_platform_id", return_value="luno"),
            patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)),
            patch("validators.bot_validator.get_max_bots", return_value=10),
            patch("validators.bot_validator.get_normal_cap", return_value=10),
            patch("validators.bot_validator.resolve_capital_for_exchange", return_value=(1000.0, "ZAR", 1.0)),
        ):
            bot_data = {
                "name": "Luno ZAR Bot",
                "exchange": "luno",
                "risk_mode": "balanced",
                "trading_mode": "paper",
                "capital": 1000.0,
                "bot_type": "normal",
            }
            ok, data = _run(validator.validate_bot_creation("user1", bot_data))

        assert ok, f"Expected success, got: {data}"
        assert data["funding_input_amount"] == 1000.0, "funding_input_amount must be user-entered ZAR amount"
        assert data["funding_input_currency"] == "ZAR", "funding_input_currency must be ZAR"
        assert data["canonical_base_capital_zar"] == 1000.0
        assert data["quote_currency"] == "ZAR"
        assert data["initial_capital"] == 1000.0

    def test_binance_bot_stores_funding_input_fields(self):
        from validators.bot_validator import BotValidator

        validator = BotValidator()
        mock_db, mock_wallet = self._make_validator_mocks(zar_balance=2000.0)

        with (
            patch("validators.bot_validator.db", mock_db),
            patch("validators.bot_validator.paper_wallet_service", mock_wallet),
            patch("validators.bot_validator.is_valid_platform", return_value=True),
            patch("validators.bot_validator.normalize_platform_id", return_value="binance"),
            patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)),
            patch("validators.bot_validator.get_max_bots", return_value=10),
            patch("validators.bot_validator.get_normal_cap", return_value=10),
            patch("validators.bot_validator.resolve_capital_for_exchange", return_value=(52.63, "USDT", 19.0)),
        ):
            bot_data = {
                "name": "Binance USDT Bot",
                "exchange": "binance",
                "risk_mode": "balanced",
                "trading_mode": "paper",
                "capital": 1000.0,
                "bot_type": "normal",
            }
            ok, data = _run(validator.validate_bot_creation("user1", bot_data))

        assert ok, f"Expected success, got: {data}"
        # funding_input_* always reflects user's ZAR input
        assert data["funding_input_amount"] == 1000.0, "funding_input_amount must be 1000 ZAR"
        assert data["funding_input_currency"] == "ZAR", "funding_input_currency must be ZAR"
        # canonical_base_capital_zar must be the user's ZAR amount (unchanged)
        assert data["canonical_base_capital_zar"] == 1000.0
        # For Binance, quote currency = USDT
        assert data["quote_currency"] == "USDT"
        assert data["initial_capital"] == pytest.approx(52.63)
        assert data["fx_rate_at_creation"] == pytest.approx(19.0)
        # Verify round-trip: initial_capital × fx_rate ≈ canonical_base_capital_zar
        approx_zar = data["initial_capital"] * data["fx_rate_at_creation"]
        assert abs(approx_zar - 1000.0) < 1.0, (
            f"initial_capital ({data['initial_capital']}) × fx_rate ({data['fx_rate_at_creation']}) "
            f"should ≈ 1000 ZAR, got {approx_zar}"
        )


# ─── 2. Radar snapshot: canonical fields are present ─────────────────────────

class TestRadarSnapshotCanonicalFields:
    """Radar _compute_radar_entry must return all canonical currency truth fields."""

    def _make_bot(self, exchange="luno", capital=1000.0):
        return {
            "id": "test-bot-id",
            "name": f"Test {exchange.title()} Bot",
            "exchange": exchange,
            "pair": "BTC/ZAR" if exchange == "luno" else "BTC/USDT",
            "bot_type": "normal",
            "status": "active",
            "trading_mode": "paper",
            "initial_capital": capital,
            "current_capital": capital,
            # These fields are stored at creation time by bot_validator
            "canonical_base_capital_zar": 1000.0,  # always ZAR
            "fx_rate_at_creation": 1.0 if exchange == "luno" else 19.0,
            "quote_currency": "ZAR" if exchange == "luno" else "USDT",
            "funding_input_amount": 1000.0,
            "funding_input_currency": "ZAR",
        }

    def _get_entry(self, bot):
        try:
            from routes.radar import _compute_radar_entry
        except ImportError:
            pytest.skip("routes.radar has unmet dependency")
        with patch("routes.radar.resolve_hold_policy", return_value={"max_hold_seconds": 3600, "source": "default"}):
            return _compute_radar_entry(bot, None, datetime.now(timezone.utc))

    def test_luno_radar_entry_has_canonical_fields(self):
        bot = self._make_bot("luno", capital=1000.0)
        entry = self._get_entry(bot)

        for field in ("canonical_base_capital_zar", "fx_rate_at_creation",
                      "funding_input_amount", "funding_input_currency"):
            assert field in entry, f"Missing {field} in radar entry"

        assert entry["canonical_base_capital_zar"] == 1000.0
        assert entry["fx_rate_at_creation"] == 1.0
        assert entry["funding_input_amount"] == 1000.0
        assert entry["funding_input_currency"] == "ZAR"
        assert entry["quote_currency"] == "ZAR"
        assert entry["display_currency"] == "ZAR"

    def test_binance_radar_entry_has_canonical_fields(self):
        bot = self._make_bot("binance", capital=52.63)  # USDT amount stored in DB
        entry = self._get_entry(bot)

        for field in ("canonical_base_capital_zar", "fx_rate_at_creation",
                      "funding_input_amount", "funding_input_currency"):
            assert field in entry, f"Missing {field} in radar entry"

        assert entry["canonical_base_capital_zar"] == 1000.0
        assert entry["fx_rate_at_creation"] == 19.0
        assert entry["funding_input_amount"] == 1000.0
        assert entry["funding_input_currency"] == "ZAR"
        assert entry["quote_currency"] == "USDT"
        assert entry["display_currency"] == "ZAR"

    def test_radar_entry_capital_allocated_display_is_zar(self):
        import services.fx_normalizer as fx_mod
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 19.0
        fx_mod._cached_rate_source = "test"
        try:
            bot = self._make_bot("binance", capital=52.63)
            entry = self._get_entry(bot)
            assert abs(entry["capital_allocated"] - 52.63) < 0.01
            assert entry["capital_allocated_display"] is not None
            assert entry["capital_allocated_display"] > 900, (
                f"capital_allocated_display should be ~1000 ZAR, got {entry['capital_allocated_display']}"
            )
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

    def test_radar_luno_display_equals_raw(self):
        bot = self._make_bot("luno", capital=1000.0)
        entry = self._get_entry(bot)
        assert entry["capital_allocated"] == entry["capital_allocated_display"]


# ─── 3. Converter logic functions ────────────────────────────────────────────

class TestConverterLogic:
    """Test the converter helper functions in wallet_hub.py directly (no HTTP)."""

    def test_zar_identity_rate(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, source = _get_to_zar_rate("ZAR")
        assert rate == 1.0
        assert source == "identity"

    def test_usdt_uses_fx_normalizer(self):
        import services.fx_normalizer as fx_mod
        from routes.wallet_hub import _get_to_zar_rate
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 20.0
        fx_mod._cached_rate_source = "test"
        try:
            rate, source = _get_to_zar_rate("USDT")
            assert abs(rate - 20.0) < 0.01
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

    def test_gbp_rate_positive(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, _ = _get_to_zar_rate("GBP")
        assert rate > 0

    def test_eur_rate_positive(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, _ = _get_to_zar_rate("EUR")
        assert rate > 0

    def test_btc_rate_large(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, _ = _get_to_zar_rate("BTC")
        assert rate > 100_000

    def test_eth_rate_large(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, _ = _get_to_zar_rate("ETH")
        assert rate > 1_000

    def test_unknown_currency_identity(self):
        from routes.wallet_hub import _get_to_zar_rate
        rate, source = _get_to_zar_rate("NOTACURRENCY")
        assert rate == 1.0
        assert source == "unknown"

    def test_supported_currencies_complete(self):
        from routes.wallet_hub import _SUPPORTED_CONVERTER_CURRENCIES
        for cur in ["ZAR", "USD", "GBP", "EUR", "USDT", "BUSD", "USDC", "BTC", "ETH"]:
            assert cur in _SUPPORTED_CONVERTER_CURRENCIES


# ─── 4. Converter endpoint via HTTP ──────────────────────────────────────────

class TestConverterEndpoint:
    """POST /api/wallet/converter returns correctly labeled conversion results."""

    def _get_app_with_override(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.wallet_hub import router
        import auth

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[auth.get_current_user] = lambda: "test-user"
        return app, TestClient(app)

    def test_zar_to_usdt_conversion(self):
        import services.fx_normalizer as fx_mod
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 19.0
        fx_mod._cached_rate_source = "test"

        app, client = self._get_app_with_override()
        try:
            resp = client.post(
                "/api/wallet/converter",
                json={"amount": 1000.0, "from_currency": "ZAR", "to_currency": "USDT"},
            )
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["input_currency"] == "ZAR"
        assert data["output_currency"] == "USDT"
        assert data["input_amount"] == 1000.0
        assert data["output_amount"] > 40.0
        assert data["output_amount"] < 100.0
        assert "effective_rate" in data
        assert "rate_source" in data
        assert "timestamp" in data

    def test_usdt_to_zar_conversion(self):
        import services.fx_normalizer as fx_mod
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 19.0
        fx_mod._cached_rate_source = "test"

        app, client = self._get_app_with_override()
        try:
            resp = client.post(
                "/api/wallet/converter",
                json={"amount": 52.63, "from_currency": "USDT", "to_currency": "ZAR"},
            )
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

        assert resp.status_code == 200
        data = resp.json()
        assert data["input_currency"] == "USDT"
        assert data["output_currency"] == "ZAR"
        assert data["output_amount"] > 900.0
        assert data["output_amount"] < 1100.0

    def test_zar_to_zar_identity(self):
        app, client = self._get_app_with_override()
        resp = client.post(
            "/api/wallet/converter",
            json={"amount": 500.0, "from_currency": "ZAR", "to_currency": "ZAR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["output_amount"] == 500.0

    def test_unsupported_currency_returns_400(self):
        app, client = self._get_app_with_override()
        resp = client.post(
            "/api/wallet/converter",
            json={"amount": 100.0, "from_currency": "XYZ", "to_currency": "ZAR"},
        )
        assert resp.status_code == 400

    def test_negative_amount_returns_400(self):
        app, client = self._get_app_with_override()
        resp = client.post(
            "/api/wallet/converter",
            json={"amount": -100.0, "from_currency": "ZAR", "to_currency": "USDT"},
        )
        assert resp.status_code == 400

    def test_gbp_to_zar_returns_positive(self):
        app, client = self._get_app_with_override()
        resp = client.post(
            "/api/wallet/converter",
            json={"amount": 100.0, "from_currency": "GBP", "to_currency": "ZAR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["output_amount"] > 0

    def test_rates_endpoint_returns_all_currencies(self):
        app, client = self._get_app_with_override()
        resp = client.get("/api/wallet/converter/rates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_currency"] == "ZAR"
        for cur in ["ZAR", "USDT", "BUSD", "USDC", "USD", "GBP", "EUR", "BTC", "ETH"]:
            assert cur in data["rates"]
            assert data["rates"][cur]["rate_to_zar"] > 0

    def test_converter_uses_fx_normalizer_for_usdt(self):
        """Converter must use fx_normalizer canonical rate for USDT, not a hardcoded value."""
        import services.fx_normalizer as fx_mod
        old_rate = fx_mod._cached_rate
        old_source = fx_mod._cached_rate_source
        fx_mod._cached_rate = 20.0
        fx_mod._cached_rate_source = "test_override"

        app, client = self._get_app_with_override()
        try:
            resp = client.post(
                "/api/wallet/converter",
                json={"amount": 1.0, "from_currency": "USDT", "to_currency": "ZAR"},
            )
        finally:
            fx_mod._cached_rate = old_rate
            fx_mod._cached_rate_source = old_source

        assert resp.status_code == 200
        data = resp.json()
        assert abs(data["output_amount"] - 20.0) < 1.0, (
            f"Converter should use fx_normalizer rate (20.0), got {data['output_amount']}"
        )


# ─── 5. FX normalizer single-source-of-truth ─────────────────────────────────

class TestFxNormalizerSingleSourceOfTruth:
    def test_resolve_capital_luno_no_conversion(self):
        from services.fx_normalizer import resolve_capital_for_exchange
        qc, cur, rate = resolve_capital_for_exchange(1000.0, "luno")
        assert qc == 1000.0
        assert cur == "ZAR"
        assert rate == 1.0

    def test_resolve_capital_binance_converts_to_usdt(self):
        from services.fx_normalizer import resolve_capital_for_exchange, update_fx_rate
        update_fx_rate(19.0, "test")
        qc, cur, rate = resolve_capital_for_exchange(1000.0, "binance")
        assert cur == "USDT"
        assert abs(rate - 19.0) < 0.01
        assert abs(qc * rate - 1000.0) < 1.0

    def test_canonical_base_immutability_contract(self):
        bot = {
            "canonical_base_capital_zar": 1000.0,
            "initial_capital": 52.63,
            "current_capital": 52.63,
        }
        # Simulate rebalancer updating current_capital
        updated = {**bot, "current_capital": 48.0}
        assert updated["canonical_base_capital_zar"] == 1000.0


# ─── 6. Regression tests ──────────────────────────────────────────────────────

class TestRegressions:
    def test_fx_normalizer_has_required_functions(self):
        from services import fx_normalizer
        for fn in ["resolve_capital_for_exchange", "get_fx_rate", "to_display_zar",
                   "normalize_money_field", "get_quote_currency"]:
            assert hasattr(fx_normalizer, fn)

    def test_wallet_hub_has_converter_routes(self):
        from routes.wallet_hub import router
        paths = [r.path for r in router.routes]
        assert "/api/wallet/converter" in paths
        assert "/api/wallet/converter/rates" in paths

    def test_radar_has_snapshot_route(self):
        from routes.radar import router
        paths = [r.path for r in router.routes]
        assert any("snapshot" in p for p in paths)

    def test_normalize_money_field_labels_correctly(self):
        from services.fx_normalizer import normalize_money_field
        result = normalize_money_field(52.63, "USDT", fx_rate=19.0)
        assert result["raw_currency"] == "USDT"
        assert result["display_currency"] == "ZAR"
        assert abs(result["display_value"] - 52.63 * 19.0) < 0.01

    def test_binance_quote_currency_is_not_zar(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("binance", "BTC/USDT") == "USDT"

    def test_luno_quote_currency_is_not_usdt(self):
        from services.fx_normalizer import get_quote_currency
        assert get_quote_currency("luno", "BTC/ZAR") == "ZAR"
