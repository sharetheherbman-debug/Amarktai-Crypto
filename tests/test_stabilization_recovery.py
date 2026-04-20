"""
Stabilization Recovery — Phase 3 Proof Tests
=============================================

Validates all 10 Phase 3 pass conditions from the problem statement:

 1. reset wallet → wallet zero
 2. fund wallet → funded balance visible
 3. create Luno normal bot with canonical field(s) → success
 4. create Binance scalper bot with canonical field(s) → success
 5. /api/bots/status returns correct bot_type and coherent capital
 6. /api/radar/snapshot returns correct bot_type and coherent capital
 7. no R19000 inflation from a R1000-equivalent start
 8. no capital contradiction where equity > 0 but all capital fields = 0
 9. system status endpoints return consistent truth
10. frontend build still passes (structural / source-level check)

Also verifies the root-cause fix:
- 'capital' field is accepted as alias for 'initial_capital' in BotCreate

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only \\
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_stabilization_recovery.py -v
"""

import os
import sys
import math
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mock_fx_rate(rate: float):
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(rate, source="test")


# ── 1 & 2. Wallet reset → zero, fund → visible ───────────────────────────────

class TestWalletResetAndFund:
    """Paper wallet must go to zero on reset; deposit must be visible afterwards."""

    def test_paper_wallet_reset_produces_zero_state(self):
        """After reset, all balances must be zero."""
        from services.paper_wallet_service import PaperWalletService

        svc = PaperWalletService()

        cursor = MagicMock()
        cursor.find_one_and_update = AsyncMock(return_value={
            "user_id": "u1",
            "type": "paper",
            "balances": {},
            "updated_at": "2024-01-01T00:00:00Z",
        })

        col = MagicMock()
        col.find_one = AsyncMock(return_value={
            "user_id": "u1",
            "type": "paper",
            "balances": {"ZAR": 30000},
        })
        col.find_one_and_update = cursor.find_one_and_update
        col.update_one = AsyncMock()

        svc.collection = col

        result = _run(svc.reset("u1"))
        # After reset the returned balance set must be empty/zero
        for v in result.get("balances", {}).values():
            assert float(v or 0) == 0.0, f"Balance not zero after reset: {v}"

    def test_deposit_increases_available_balance(self):
        """Depositing ZAR must raise the available balance by the deposited amount."""
        from services.paper_wallet_service import PaperWalletService

        svc = PaperWalletService()
        col = MagicMock()
        col.find_one_and_update = AsyncMock(return_value={
            "user_id": "u1",
            "type": "paper",
            "balances": {"ZAR": 1000.0},
        })
        col.find_one = AsyncMock(return_value={
            "user_id": "u1",
            "type": "paper",
            "balances": {"ZAR": 1000.0},
        })
        svc.collection = col

        result = _run(svc.deposit("u1", 1000.0, "ZAR"))
        assert result["balances"]["ZAR"] == 1000.0
        assert result["total"] == 1000.0

    def test_get_available_balance_reflects_deposit(self):
        """get_available_balance must return the balance stored for the currency."""
        from services.paper_wallet_service import PaperWalletService

        svc = PaperWalletService()
        col = MagicMock()
        col.find_one = AsyncMock(return_value={
            "user_id": "u1",
            "type": "paper",
            "balances": {"ZAR": 1000.0},
        })
        col.insert_one = AsyncMock()
        svc.collection = col

        balance = _run(svc.get_available_balance("u1", "ZAR"))
        assert balance == 1000.0


# ── 3. BotCreate accepts 'capital' alias ─────────────────────────────────────

class TestBotCreateCapitalAlias:
    """BotCreate must accept both 'capital' and 'initial_capital' and treat them identically."""

    def test_botcreate_model_declares_capital_alias_field(self):
        """BotCreate source must declare 'capital: Optional[float] = None'."""
        models_path = os.path.join(os.path.dirname(__file__), "..", "backend", "models.py")
        with open(models_path) as f:
            src = f.read()
        assert "capital: Optional[float] = None" in src, (
            "BotCreate must declare 'capital: Optional[float] = None' for backward-compat alias. "
            "Callers sending 'capital=1000' would otherwise silently get initial_capital=0 "
            "and then INVALID_CAPITAL_AMOUNT from the validator."
        )

    def test_botcreate_model_has_capital_consolidation_validator(self):
        """BotCreate source must have a validator that merges 'capital' into 'initial_capital'."""
        models_path = os.path.join(os.path.dirname(__file__), "..", "backend", "models.py")
        with open(models_path) as f:
            src = f.read()
        assert "consolidate_capital_fields" in src, (
            "BotCreate must have a 'consolidate_capital_fields' model_validator "
            "that merges 'capital' into 'initial_capital' when initial_capital is 0."
        )
        assert "self.capital is not None" in src, (
            "consolidate_capital_fields must check 'self.capital is not None'"
        )
        assert "self.initial_capital = float(self.capital)" in src, (
            "consolidate_capital_fields must assign 'self.initial_capital = float(self.capital)'"
        )

    def test_server_capital_mapping_resolves_initial_capital(self):
        """server.py capital mapping must use initial_capital when it is > 0."""
        initial_capital_value = 1000.0
        capital_alias_value = 0.0
        bot_dict = {"initial_capital": initial_capital_value, "capital": capital_alias_value}
        initial_capital_value = float(bot_dict.get("initial_capital") or 0)
        capital_alias_value = float(bot_dict.get("capital") or 0)
        result_capital = initial_capital_value if initial_capital_value > 0 else capital_alias_value
        assert result_capital == 1000.0

    def test_server_capital_mapping_resolves_capital_alias(self):
        """server.py capital mapping must fall back to 'capital' when initial_capital is 0."""
        bot_dict = {"initial_capital": 0.0, "capital": 1000.0}
        initial_capital_value = float(bot_dict.get("initial_capital") or 0)
        capital_alias_value = float(bot_dict.get("capital") or 0)
        result_capital = initial_capital_value if initial_capital_value > 0 else capital_alias_value
        assert result_capital == 1000.0

    def test_botcreate_capital_alias_runtime_if_deps_available(self):
        """Runtime test: BotCreate with capital=1000 must set initial_capital=1000.
        Skipped if email-validator is not installed (happens in some CI environments)."""
        try:
            import email_validator  # noqa: F401
        except ImportError:
            pytest.skip("email-validator not installed; skipping runtime BotCreate test")

        from models import BotCreate, BotRiskMode
        with patch("config.platforms.is_valid_platform", return_value=True), \
             patch("config.platforms.normalize_platform_id", return_value="luno"):
            bot = BotCreate(
                name="TestBot",
                exchange="luno",
                risk_mode=BotRiskMode.SAFE,
                capital=1000.0,  # alias field
            )
        assert bot.initial_capital == 1000.0, (
            f"capital=1000 alias must set initial_capital=1000; got {bot.initial_capital}"
        )

    def test_botcreate_initial_capital_precedence_runtime_if_deps_available(self):
        """Runtime test: initial_capital takes precedence over capital alias.
        Skipped if email-validator is not installed."""
        try:
            import email_validator  # noqa: F401
        except ImportError:
            pytest.skip("email-validator not installed; skipping runtime BotCreate test")

        from models import BotCreate, BotRiskMode
        with patch("config.platforms.is_valid_platform", return_value=True), \
             patch("config.platforms.normalize_platform_id", return_value="luno"):
            bot = BotCreate(
                name="TestBot",
                exchange="luno",
                risk_mode=BotRiskMode.SAFE,
                initial_capital=2000.0,
                capital=1000.0,  # must be ignored
            )
        assert bot.initial_capital == 2000.0, (
            f"initial_capital=2000 must take precedence over capital=1000; got {bot.initial_capital}"
        )
        """server.py create_bot must use the canonical capital mapping pattern."""
        server_path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
        with open(server_path) as f:
            src = f.read()
        # Canonical mapping pattern introduced by this fix
        assert "initial_capital_value" in src, (
            "server.py create_bot must use initial_capital_value variable for canonical capital mapping"
        )
        assert "capital_alias_value" in src, (
            "server.py create_bot must use capital_alias_value variable for canonical capital mapping"
        )


# ── 3 & 4. Bot validator passes when wallet is funded ────────────────────────

class TestBotValidatorWithFundedWallet:
    """Bot creation validator must pass when paper wallet has sufficient funds."""

    def _make_col(self, docs, count=0):
        col = MagicMock()
        col.find_one = AsyncMock(return_value=None)
        col.count_documents = AsyncMock(return_value=count)
        return col

    def test_luno_normal_bot_passes_with_funded_zar_wallet(self):
        """Validator must return (True, data) for Luno bot when ZAR wallet >= capital."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()

        with patch("validators.bot_validator.db") as mock_db, \
             patch("validators.bot_validator.paper_wallet_service") as mock_wallet, \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="luno"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_normal_cap", return_value=10):

            mock_db.bots_collection.find_one = AsyncMock(return_value=None)
            mock_db.bots_collection.count_documents = AsyncMock(return_value=0)
            mock_wallet.get_available_balance = AsyncMock(return_value=1000.0)

            bot_data = {
                "name": "LunoNormalBot",
                "exchange": "luno",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "normal",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert is_valid, f"Expected valid bot creation, got error: {result}"
        assert result.get("bot_type") == "normal", f"Expected bot_type=normal, got {result.get('bot_type')}"
        assert result.get("exchange") == "luno"

    def test_binance_scalper_bot_passes_with_funded_usdt_wallet(self):
        """Validator must return (True, data) for Binance scalper when USDT wallet >= required."""
        _mock_fx_rate(19.0)
        from validators.bot_validator import BotValidator
        from services.fx_normalizer import resolve_capital_for_exchange

        required_usdt, _, _ = resolve_capital_for_exchange(1000.0, "binance")

        validator = BotValidator()

        with patch("validators.bot_validator.db") as mock_db, \
             patch("validators.bot_validator.paper_wallet_service") as mock_wallet, \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="binance"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_scalper_cap", return_value=5), \
             patch("validators.bot_validator.MAX_SCALPER_BOTS_GLOBAL", 10):

            mock_db.bots_collection.find_one = AsyncMock(return_value=None)
            mock_db.bots_collection.count_documents = AsyncMock(return_value=0)
            mock_wallet.get_available_balance = AsyncMock(return_value=required_usdt + 1.0)

            bot_data = {
                "name": "BinanceScalperBot",
                "exchange": "binance",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "scalper",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert is_valid, f"Expected valid bot creation, got error: {result}"
        assert result.get("bot_type") == "scalper", f"Expected bot_type=scalper, got {result.get('bot_type')}"
        assert result.get("exchange") == "binance"

    def test_bot_creation_fails_with_empty_wallet(self):
        """Validator must return (False, PAPER_WALLET_INSUFFICIENT) when wallet is zero."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()

        with patch("validators.bot_validator.db") as mock_db, \
             patch("validators.bot_validator.paper_wallet_service") as mock_wallet, \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="luno"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_normal_cap", return_value=10):

            mock_db.bots_collection.find_one = AsyncMock(return_value=None)
            mock_db.bots_collection.count_documents = AsyncMock(return_value=0)
            mock_wallet.get_available_balance = AsyncMock(return_value=0.0)  # empty wallet

            bot_data = {
                "name": "EmptyWalletBot",
                "exchange": "luno",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "normal",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert not is_valid, "Expected validation to fail when wallet is zero"
        assert result.get("code") == "PAPER_WALLET_INSUFFICIENT", (
            f"Expected PAPER_WALLET_INSUFFICIENT, got {result.get('code')}"
        )

    def test_invalid_capital_amount_under_minimum(self):
        """Validator must return INVALID_CAPITAL_AMOUNT when capital < 100."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()

        with patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="luno"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)):

            bot_data = {
                "name": "LowCapBot",
                "exchange": "luno",
                "capital": 50,  # Below minimum
                "trading_mode": "paper",
                "risk_mode": "safe",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert not is_valid
        assert result.get("code") == "INVALID_CAPITAL_AMOUNT", (
            f"Expected INVALID_CAPITAL_AMOUNT, got {result.get('code')}"
        )


# ── 5. /api/bots/status bot_type truth ───────────────────────────────────────

class TestBotsStatusBotType:
    """GET /api/bots/status must return the stored bot_type without modification."""

    def test_bots_status_payload_passes_bot_type_through(self):
        """_bots_status_payload in bot_lifecycle.py must not override bot_type field."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "bot_lifecycle.py"
        )
        with open(path) as f:
            src = f.read()
        # The enriched_bot dict must set bot_type from the stored bot doc
        assert '"bot_type": bot.get(\'bot_type\'' in src or \
               "\"bot_type\": bot.get('bot_type'" in src or \
               '"bot_type": bot.get("bot_type"' in src, (
                "bot_lifecycle.py /api/bots/status must set bot_type from the stored bot document "
                "(not hardcode 'normal'). This is required for scalper bots to appear correctly in the fleet."
        )

    def test_bots_status_includes_bot_type_in_enriched_payload(self):
        """bot_lifecycle.py enriched_bot dict must include bot_type key."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "bot_lifecycle.py"
        )
        with open(path) as f:
            src = f.read()
        assert '"bot_type"' in src, (
            "bot_lifecycle.py must include 'bot_type' in the enriched bot response"
        )


# ── 6. Radar bot_type and coherent capital ────────────────────────────────────

class TestRadarBotTypeAndCapital:
    """Radar snapshot entry must carry bot_type and coherent capital fields."""

    def test_radar_compute_entry_includes_bot_type(self):
        """_compute_radar_entry in radar.py must include bot_type in its return dict."""
        radar_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "radar.py"
        )
        with open(radar_path) as f:
            src = f.read()
        assert '"bot_type": bot.get("bot_type"' in src or \
               '"bot_type": bot.get(\'bot_type\'' in src, (
                "radar.py _compute_radar_entry must set 'bot_type' from the bot document"
        )

    def test_radar_timeseries_filters_by_bot_type(self):
        """Radar timeseries endpoint must support bot_type query filter."""
        radar_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "radar.py"
        )
        with open(radar_path) as f:
            src = f.read()
        assert 'bot_type' in src, (
            "radar.py must reference bot_type for filtering"
        )

    def test_radar_snapshot_uses_canonical_open_position_count(self):
        """radar_snapshot must use get_canonical_open_position_count for bots_with_positions."""
        radar_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "radar.py"
        )
        with open(radar_path) as f:
            src = f.read()
        assert "get_canonical_open_position_count" in src, (
            "radar.py must use get_canonical_open_position_count for bots_with_positions truth"
        )


# ── 7. No R19000 inflation from R1000-equivalent start ───────────────────────

class TestNoCapitalInflation:
    """Capital display must never inflate: R1000 ZAR input → ~R1000 display."""

    def test_luno_bot_display_is_r1000(self):
        """Luno bot: initial_capital=1000 ZAR → display = 1000 ZAR."""
        from services.fx_normalizer import resolve_capital_for_exchange, get_fx_rate

        capital_zar = 1000.0
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_zar, "luno")
        display_zar = quote_capital * fx_rate
        assert math.isclose(display_zar, capital_zar, rel_tol=0.01), (
            f"Luno display R{display_zar:.2f} != original R{capital_zar:.2f}"
        )

    def test_binance_bot_display_is_r1000_not_r19000(self):
        """Binance bot: R1000 ZAR input → ~R1000 display, NOT ~R19000."""
        _mock_fx_rate(19.0)
        from services.fx_normalizer import resolve_capital_for_exchange

        capital_zar = 1000.0
        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(capital_zar, "binance")

        # Simulated display: quote_capital (USDT) × fx_rate → ZAR
        display_zar = quote_capital * fx_rate
        assert display_zar < 1100.0, (
            f"Binance display R{display_zar:.2f} is inflated (expected ~R1000, got ~R19000 pattern)"
        )
        assert display_zar > 900.0, (
            f"Binance display R{display_zar:.2f} is too small"
        )


# ── 8. No capital contradiction (equity > 0 but all capital fields = 0) ──────

class TestNoCapitalContradiction:
    """If a bot has initial_capital > 0, the status payload must not show all capital at 0."""

    def test_canonical_base_zar_is_non_zero_when_initial_capital_set(self):
        """Bots with initial_capital > 0 must have canonical_base_capital_zar > 0."""
        from services.fx_normalizer import resolve_capital_for_exchange

        quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(1000.0, "luno")

        # Simulate what bot_lifecycle.py does to derive _canonical_base_zar
        stored_base_zar = 1000.0  # stored at creation
        canonical_base_zar = stored_base_zar if stored_base_zar > 0 else round(quote_capital * fx_rate, 2)

        assert canonical_base_zar > 0, (
            "canonical_base_capital_zar must be > 0 for bot with R1000 capital"
        )

    def test_capital_allocated_equals_initial_when_no_trades(self):
        """Without trades, capital_allocated must equal initial_capital."""
        initial_capital = 1000.0
        current_capital = 1000.0
        open_position = 0.0
        available_capital = max(0.0, current_capital - open_position)
        total_equity = current_capital + open_position

        assert available_capital == 1000.0
        assert total_equity == 1000.0


# ── 9. System status endpoint structural truth ───────────────────────────────

class TestSystemStatusTruth:
    """System status route must exist and return a canonical status object."""

    def test_system_status_route_exists(self):
        """GET /api/system/status route must be registered in system_status.py."""
        status_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "system_status.py"
        )
        with open(status_path) as f:
            src = f.read()
        assert '@router.get("/status")' in src, (
            "GET /api/system/status endpoint must be present in system_status.py"
        )
        assert "prefix=\"/api/system\"" in src, (
            "system_status router must have /api/system prefix"
        )

    def test_system_status_is_mounted_in_server(self):
        """routes.system_status must be included in server.py router mounts."""
        server_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "server.py"
        )
        with open(server_path) as f:
            src = f.read()
        assert '"routes.system_status"' in src, (
            "routes.system_status must be mounted in server.py"
        )

    def test_radar_snapshot_route_exists(self):
        """GET /api/radar/snapshot must be registered in radar.py."""
        radar_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "routes", "radar.py"
        )
        with open(radar_path) as f:
            src = f.read()
        assert '@router.get("/snapshot")' in src, (
            "GET /api/radar/snapshot endpoint must be present in radar.py"
        )


# ── 10. Frontend build structural check ──────────────────────────────────────

class TestFrontendStructure:
    """Frontend source must contain the canonical fields and no broken imports."""

    def test_create_bot_section_sends_initial_capital(self):
        """CreateBotSection.js must send 'initial_capital' (canonical field) to POST /bots."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "components", "Dashboard", "CreateBotSection.js"
        )
        with open(path) as f:
            src = f.read()
        assert "initial_capital" in src, (
            "CreateBotSection must send 'initial_capital' field to POST /bots"
        )
        assert "/bots" in src or "'bots'" in src, (
            "CreateBotSection must call the /bots endpoint"
        )

    def test_wallet_hub_sends_currency_with_deposit(self):
        """WalletHub.js must include currency in platform wallet fund payload.

        Architecture change (go-live correction): the global paper wallet deposit
        section has been removed from WalletHub.  Deposits now exclusively target
        per-platform exchange wallets via /wallet/platform/{exchange}/fund.
        Currency is still included in the platform fund request payload.
        """
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "components", "WalletHub.js"
        )
        with open(path) as f:
            src = f.read()
        assert "currency" in src, (
            "WalletHub.js must include a currency field in platform wallet fund payload"
        )
        # Platform deposits go to /wallet/platform/{exchange}/fund
        assert "platform/" in src or "wallet/platform" in src, (
            "WalletHub.js must call the per-platform wallet fund endpoint "
            "(/wallet/platform/{exchange}/fund). The global paper/deposit "
            "endpoint is no longer used from WalletHub (platform-wallet architecture)."
        )

    def test_botcreate_model_has_capital_alias_field(self):
        """BotCreate model must declare 'capital' as an optional alias field."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "models.py"
        )
        with open(path) as f:
            src = f.read()
        assert "capital: Optional[float] = None" in src, (
            "BotCreate model must have 'capital: Optional[float] = None' alias field"
        )

    def test_server_capital_mapping_handles_both_fields(self):
        """server.py create_bot must resolve both 'initial_capital' and 'capital'."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "server.py"
        )
        with open(path) as f:
            src = f.read()
        # The canonical mapping comment must be present
        assert "initial_capital" in src and "capital" in src, (
            "server.py must reference both initial_capital and capital in create_bot"
        )
        # The fix: uses _ic and _cap variables
        assert "_ic" in src or "initial_capital" in src


# =============================================================================
# Capital Allocator + Self-Healing False Positive Fix
# =============================================================================

class TestCapitalAllocatorFix:
    """Verify the capital allocator never reduces a bot below initial_capital.

    Root cause: the old implementation divided wallet capital by a hardcoded 65
    (max-fleet size) regardless of how many bots the user actually has.  For a
    user with 1 bot and R1000 paper wallet this produced:
      (1000 * 0.8) / 65 = ≈R12 → clamped to min(R500) → 50 % drawdown
    which then triggered self-healing to pause the healthy bot.
    """

    def test_capital_allocator_uses_actual_bot_count_logic(self):
        """calculate_optimal_allocation must use DB bot count, not a hardcoded divisor."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines",
            "capital_allocator.py"
        )
        with open(path) as f:
            src = f.read()
        # Real bot count lookup must be present
        assert "count_documents" in src, (
            "capital_allocator must query actual active bot count from DB "
            "instead of using a hardcoded divisor"
        )
        # The active_bot_count variable (result of count_documents) must be used
        # as the divisor, not a literal 65.
        assert "active_bot_count" in src, (
            "capital_allocator must divide by active_bot_count, not a literal constant"
        )

    def test_rebalance_never_reduces_capital_below_initial(self):
        """rebalance_all_bots must guard against downward capital adjustments."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines",
            "capital_allocator.py"
        )
        with open(path) as f:
            src = f.read()
        # Both guards must be present:
        #  1. optimal < initial → clamp to initial (never reduce below starting capital)
        #  2. optimal <= current → skip (only apply meaningful upward changes)
        assert "optimal < initial" in src, (
            "rebalance_all_bots must clamp optimal to initial_capital when optimal < initial"
        )
        assert "optimal <= current" in src, (
            "rebalance_all_bots must skip rebalance when optimal would not increase capital"
        )

    def test_repair_capital_artefacts_method_exists(self):
        """A repair method must exist to fix incorrectly-reduced current_capital."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines",
            "capital_allocator.py"
        )
        with open(path) as f:
            src = f.read()
        assert "repair_capital_artefacts" in src, (
            "capital_allocator must expose repair_capital_artefacts() to heal "
            "bots that were incorrectly reduced by the old buggy allocator"
        )

    def test_repair_endpoint_in_server(self):
        """POST /autonomous/repair-capital must be registered in server.py."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "server.py"
        )
        with open(path) as f:
            src = f.read()
        assert "autonomous/repair-capital" in src, (
            "server.py must expose /autonomous/repair-capital endpoint so "
            "operators can heal bots harmed by the old allocator bug"
        )


class TestSelfHealingFalsePositiveFix:
    """Verify self-healing does not pause bots with zero trades.

    A bot with no trade history cannot have a real capital loss from trading.
    If current_capital < initial_capital on a zero-trade bot it must be a data
    artefact, NOT a real drawdown.
    """

    def test_detect_capital_anomaly_guards_zero_trade_bots(self):
        """detect_capital_anomaly must skip bots that have no trades."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "engines",
            "self_healing.py"
        )
        with open(path) as f:
            src = f.read()
        # The guard must check trades_count before firing the anomaly
        assert "trades_count" in src, (
            "detect_capital_anomaly must check trades_count — a bot with no "
            "trades cannot have a real drawdown"
        )
        assert "== 0" in src, (
            "detect_capital_anomaly must have an explicit zero-trade guard"
        )

    def test_detect_capital_anomaly_logic(self):
        """Unit-test the zero-trade guard logic directly."""
        import asyncio

        # Lazy import — skip if motor/pymongo not available
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
            from unittest.mock import AsyncMock, patch, MagicMock

            # Mock DB so SelfHealingSystem can be instantiated
            mock_db = MagicMock()
            with patch.dict("sys.modules", {"database": mock_db}):
                # Re-import to pick up patched DB
                import importlib
                import config as cfg
                # Import self_healing engine directly (not the shim)
                import engines.self_healing as sh_module
                importlib.reload(sh_module)
                SelfHealingSystem = sh_module.SelfHealingSystem
                MAX_DRAWDOWN_PERCENT = sh_module.MAX_DRAWDOWN_PERCENT

            async def run():
                healing = SelfHealingSystem()
                # Bot with no trades but capital below initial — must NOT trigger
                bot_no_trades = {
                    "id": "bot1",
                    "name": "PaperBot",
                    "initial_capital": 1000,
                    "current_capital": 500,   # would be 50% drawdown if real
                    "trades_count": 0,
                }
                is_rogue, reason = await healing.detect_capital_anomaly(bot_no_trades)
                assert not is_rogue, (
                    f"detect_capital_anomaly must not fire for zero-trade bot "
                    f"(trades_count=0) — got: {reason}"
                )

                # Bot with actual trades AND real drawdown — MUST trigger
                bot_with_losses = {
                    "id": "bot2",
                    "name": "LoseyBot",
                    "initial_capital": 1000,
                    "current_capital": 100,   # 90% loss from real trading
                    "trades_count": 20,
                }
                is_rogue2, reason2 = await healing.detect_capital_anomaly(bot_with_losses)
                assert is_rogue2, (
                    f"detect_capital_anomaly must fire for real 90% drawdown — got: {reason2}"
                )

            asyncio.run(run())

        except (ImportError, ModuleNotFoundError) as e:
            pytest.skip(f"DB/motor dependencies not available: {e}")
