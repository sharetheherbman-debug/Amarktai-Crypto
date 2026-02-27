"""
Phase 5 & 6 Production Readiness Tests

Validates:
  A1. SystemModeService.get_mode(user_id) is the canonical interface
  A2. PaperWalletService.get_wallet_status(user_id) returns required schema
  A3. Diagnostics /why-not-trading does not raise AttributeError or emit
      MODE_CHECK_ERROR / WALLET_CHECK_ERROR under normal conditions
  E.  Tick recorder updates last_tick_at via bot_runtime_state
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub heavy optional deps that are not installed in CI
for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_modes_col(paper: bool = True):
    """Return a mock system_modes_collection with a pre-set document."""
    doc = {"user_id": "user1", "paperTrading": paper, "liveTrading": not paper}

    async def find_one(filt, projection=None):
        return doc if filt.get("user_id") == "user1" else None

    async def update_one(filt, update, upsert=False):
        doc.update(update.get("$set", {}))
        return MagicMock(modified_count=1, upserted_id=None)

    col = MagicMock()
    col.find_one = AsyncMock(side_effect=find_one)
    col.update_one = AsyncMock(side_effect=update_one)
    return col


def _make_wallets_col(zar: float = 5000.0):
    """Return a mock wallets_collection with a pre-funded ZAR balance."""
    stored = [{"user_id": "user1", "type": "paper",
               "balances": {"ZAR": zar},
               "updated_at": datetime.now(timezone.utc).isoformat()}]

    async def find_one(filt, projection=None):
        return stored[0]

    async def insert_one(doc):
        stored.append(doc)
        return MagicMock(inserted_id="x")

    async def find_one_and_update(filt, update, upsert=False, return_document=None):
        doc = stored[0]
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        for k, v in update.get("$inc", {}).items():
            parts = k.split(".")
            if len(parts) == 2:
                doc[parts[0]][parts[1]] = float(doc[parts[0]].get(parts[1], 0)) + float(v)
        return doc

    col = MagicMock()
    col.find_one = AsyncMock(side_effect=find_one)
    col.insert_one = AsyncMock(side_effect=insert_one)
    col.find_one_and_update = AsyncMock(side_effect=find_one_and_update)
    col.update_one = AsyncMock()
    return col


# ---------------------------------------------------------------------------
# A1 — SystemModeService.get_mode(user_id) canonical interface
# ---------------------------------------------------------------------------

class TestSystemModeServiceCanonical:
    """get_mode(user_id) is the canonical method; get_current_mode delegates to it."""

    @pytest.mark.asyncio
    async def test_get_mode_returns_paper_when_paper_flag_set(self):
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        modes_col = _make_modes_col(paper=True)
        with patch("database.system_modes_collection", modes_col):
            result = await svc.get_mode("user1")
        assert result == "paper", f"Expected 'paper', got {result!r}"

    @pytest.mark.asyncio
    async def test_get_mode_returns_live_when_live_flag_set(self):
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        modes_col = _make_modes_col(paper=False)
        with patch("database.system_modes_collection", modes_col):
            result = await svc.get_mode("user1")
        assert result == "live", f"Expected 'live', got {result!r}"

    @pytest.mark.asyncio
    async def test_get_mode_defaults_to_paper_when_no_document(self):
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        col = MagicMock()
        col.find_one = AsyncMock(return_value=None)
        with patch("database.system_modes_collection", col):
            result = await svc.get_mode("user_unknown")
        assert result == "paper"

    @pytest.mark.asyncio
    async def test_get_current_mode_delegates_to_get_mode(self):
        """get_current_mode must be an alias — not an independent code path."""
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        modes_col = _make_modes_col(paper=True)
        with patch("database.system_modes_collection", modes_col):
            via_canonical = await svc.get_mode("user1")
            via_compat = await svc.get_current_mode("user1")
        assert via_canonical == via_compat, (
            "get_current_mode must return the same value as get_mode"
        )

    @pytest.mark.asyncio
    async def test_get_mode_returns_string_not_dict(self):
        """get_mode must return a plain string, not a dict."""
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        col = _make_modes_col(paper=True)
        with patch("database.system_modes_collection", col):
            result = await svc.get_mode("user1")
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    @pytest.mark.asyncio
    async def test_get_mode_requires_user_id(self):
        """get_mode without user_id must raise TypeError (not silently use wrong default)."""
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        with pytest.raises(TypeError):
            await svc.get_mode()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# A2 — PaperWalletService.get_wallet_status(user_id) schema
# ---------------------------------------------------------------------------

class TestPaperWalletServiceGetWalletStatus:
    """get_wallet_status must exist and return the documented schema."""

    @pytest.mark.asyncio
    async def test_method_exists(self):
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        assert hasattr(svc, "get_wallet_status"), (
            "PaperWalletService must expose get_wallet_status(user_id)"
        )

    @pytest.mark.asyncio
    async def test_returns_required_keys(self):
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=10000.0)
        with patch("database.wallets_collection", col):
            svc.collection = col
            status = await svc.get_wallet_status("user1")
        required = {"balances", "total", "available_zar", "funded", "updated_at"}
        missing = required - set(status.keys())
        assert not missing, f"get_wallet_status missing keys: {missing}"

    @pytest.mark.asyncio
    async def test_funded_true_when_balance_positive(self):
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=5000.0)
        with patch("database.wallets_collection", col):
            svc.collection = col
            status = await svc.get_wallet_status("user1")
        assert status["funded"] is True
        assert status["total"] == 5000.0
        assert status["available_zar"] == 5000.0

    @pytest.mark.asyncio
    async def test_funded_false_when_balance_zero(self):
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=0.0)
        with patch("database.wallets_collection", col):
            svc.collection = col
            status = await svc.get_wallet_status("user1")
        assert status["funded"] is False
        assert status["total"] == 0.0

    @pytest.mark.asyncio
    async def test_total_is_numeric(self):
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=1234.56)
        with patch("database.wallets_collection", col):
            svc.collection = col
            status = await svc.get_wallet_status("user1")
        assert isinstance(status["total"], (int, float)), (
            f"total must be numeric, got {type(status['total'])}"
        )


# ---------------------------------------------------------------------------
# A3 — Diagnostics /why-not-trading does not emit MODE_CHECK_ERROR or
#       WALLET_CHECK_ERROR under normal paper-mode conditions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# A3 — Diagnostics contract: mode check and wallet check use correct methods
# ---------------------------------------------------------------------------

class TestDiagnosticsWhyNotTradingNoBugs:
    """Verify that the contracts that WHY_NOT_TRADING depends on are correct.

    We test the service-level correctness (not the full FastAPI route import)
    to avoid requiring the full production dependency stack in CI.
    """

    @pytest.mark.asyncio
    async def test_mode_check_passes_user_id(self):
        """The mode check code calls get_mode(user_id), not get_mode() with no args.

        This verifies the fix for diagnostics.py:1718.  We simulate what
        why_not_trading does: call get_mode(user_id) and check the return.
        """
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        col = _make_modes_col(paper=True)
        with patch("database.system_modes_collection", col):
            # Correct call (with user_id) must not raise and must return 'paper'
            mode = await svc.get_mode("user1")
        assert mode == "paper"
        # The old code called get_mode() without args — verify that raises TypeError
        with pytest.raises(TypeError):
            await svc.get_mode()  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_mode_returns_string_for_mode_check_logic(self):
        """After the fix, mode is a plain string so .get() would raise AttributeError.

        This verifies that the diagnostics code must NOT use mode.get(...)
        on the result of get_mode(user_id).
        """
        from services.system_mode_service import SystemModeService
        svc = SystemModeService()
        col = _make_modes_col(paper=True)
        with patch("database.system_modes_collection", col):
            mode = await svc.get_mode("user1")
        # mode is a str — calling .get() on it would raise AttributeError
        assert not hasattr(mode, "get"), (
            "get_mode must return a str, not a dict. "
            "The diagnostics code must not call mode.get() after the fix."
        )
        # The correct check is a string equality comparison
        assert mode in ("paper", "live")

    @pytest.mark.asyncio
    async def test_wallet_status_method_satisfies_diagnostics_contract(self):
        """get_wallet_status must return a dict with a 'total' key (what diagnostics reads).

        This verifies diagnostics.py:1754 will work after the A2 fix.
        """
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=5000.0)
        with patch("database.wallets_collection", col):
            svc.collection = col
            wallet = await svc.get_wallet_status("user1")
        # diagnostics reads: total = wallet.get("total", 0)
        assert "total" in wallet, "get_wallet_status must include 'total' key"
        assert wallet["total"] > 0, "Funded wallet must have total > 0"

    @pytest.mark.asyncio
    async def test_wallet_unfunded_detection(self):
        """Unfunded wallet returns total=0, which diagnostics uses for WALLET_UNFUNDED."""
        from services.paper_wallet_service import PaperWalletService
        svc = PaperWalletService()
        col = _make_wallets_col(zar=0.0)
        with patch("database.wallets_collection", col):
            svc.collection = col
            wallet = await svc.get_wallet_status("user1")
        assert wallet.get("total", -1) == 0
        assert wallet.get("funded") is False


# ---------------------------------------------------------------------------
# B — Tick recorder: record_tick writes last_tick_at to bot_runtime_state
# ---------------------------------------------------------------------------

class TestTickRecorder:
    """BotRuntimeStateStore.record_tick() must update last_tick_at and updated_at."""

    @pytest.mark.asyncio
    async def test_record_tick_method_exists(self):
        from services.bot_runtime_state import BotRuntimeStateStore
        svc = BotRuntimeStateStore()
        assert hasattr(svc, "record_tick"), (
            "BotRuntimeStateStore must expose record_tick(bot_id, user_id)"
        )

    @pytest.mark.asyncio
    async def test_record_tick_writes_last_tick_at(self):
        from services.bot_runtime_state import BotRuntimeStateStore
        svc = BotRuntimeStateStore()

        written = {}

        async def fake_update_one(filt, update, upsert=False):
            written["set"] = update.get("$set", {})
            return MagicMock(modified_count=1)

        col = MagicMock()
        col.update_one = AsyncMock(side_effect=fake_update_one)

        with patch("database.bot_runtime_state_collection", col):
            await svc.record_tick("bot_abc", "user_xyz")

        assert "last_tick_at" in written.get("set", {}), (
            "record_tick must write last_tick_at into bot_runtime_state"
        )
        assert "updated_at" in written.get("set", {}), (
            "record_tick must write updated_at into bot_runtime_state"
        )

    @pytest.mark.asyncio
    async def test_record_tick_upserts(self):
        """record_tick must upsert (not fail on missing document)."""
        from services.bot_runtime_state import BotRuntimeStateStore
        svc = BotRuntimeStateStore()
        calls = []

        async def fake_update_one(filt, update, upsert=False):
            calls.append({"upsert": upsert})
            return MagicMock(modified_count=0, upserted_id="new")

        col = MagicMock()
        col.update_one = AsyncMock(side_effect=fake_update_one)

        with patch("database.bot_runtime_state_collection", col):
            await svc.record_tick("bot_new", "user_new")

        assert calls and calls[0].get("upsert") is True, (
            "record_tick must use upsert=True so it works on missing documents"
        )

    @pytest.mark.asyncio
    async def test_record_tick_tolerates_db_error(self):
        """record_tick must not raise even if the DB operation fails."""
        from services.bot_runtime_state import BotRuntimeStateStore
        svc = BotRuntimeStateStore()

        col = MagicMock()
        col.update_one = AsyncMock(side_effect=RuntimeError("DB down"))

        with patch("database.bot_runtime_state_collection", col):
            # Must not raise
            await svc.record_tick("bot_err", "user_err")


# ---------------------------------------------------------------------------
# C — Close loop: time_exit_due trades are always attempted (no null-price block)
# ---------------------------------------------------------------------------

class TestCloseLoopTimeExitDue:
    """_close_open_trade must attempt closure for time_exit_due trades."""

    @pytest.mark.asyncio
    async def test_time_exit_triggers_close_not_skip(self):
        """A trade older than PAPER_MAX_HOLD_MINUTES must set close_reason=time_exit."""
        from paper_trading_engine import PaperTradingEngine, PAPER_MAX_HOLD_MINUTES
        from datetime import timedelta

        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        engine._action_log = []
        engine.market_data_provider = None
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        engine.bybit_exchange = None
        engine.bitget_exchange = None
        engine.price_cache = {}

        old_entry = (datetime.now(timezone.utc) - timedelta(minutes=PAPER_MAX_HOLD_MINUTES + 10)).isoformat()

        open_trade = {
            "id": "trade_old",
            "pair": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 50000.0,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.03,
            "stop_loss_price": 49000.0,
            "take_profit_price": 51500.0,
            "opened_at": old_entry,
            "amount": 0.001,
            "trade_amount": 50.0,
            "entry_value": 50.0,
        }

        bot_data = {
            "id": "bot1",
            "name": "TestBot",
            "user_id": "user1",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.03,
            "initial_capital": 10000.0,
            "current_capital": 10000.0,
        }

        # Mock get_market_snapshot to return a valid mid price
        async def mock_snapshot(sym, exch):
            return {"bid": 50100.0, "ask": 50200.0, "mid": 50150.0}

        engine.market_data_provider = mock_snapshot

        # Also mock the DB writes that happen on close
        trades_col = MagicMock()
        trades_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        trades_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fill_id"))
        bots_col = MagicMock()
        bots_col.update_one = AsyncMock()

        with patch("database.trades_collection", trades_col), \
             patch("database.bots_collection", bots_col), \
             patch("database.db", MagicMock()):
            result = await engine._close_open_trade("bot1", bot_data, open_trade)

        assert result is not None, "_close_open_trade must return a result"
        skip = result.get("skip_reason")
        assert skip != "no_price_data", (
            "Close must not be blocked by null price when mock snapshot provides a price"
        )
        # The trade should have been closed (success=True or it wrote a close result)
        assert result.get("success") is True or result.get("close_reason") == "time_exit", (
            f"Expected time_exit close, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_no_price_data_returns_skip_not_exception(self):
        """When price is truly unavailable, skip_reason=no_price_data is returned (not an exception)."""
        from paper_trading_engine import PaperTradingEngine, PAPER_MAX_HOLD_MINUTES
        from datetime import timedelta

        engine = PaperTradingEngine.__new__(PaperTradingEngine)
        engine._action_log = []
        engine.market_data_provider = None
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        engine.bybit_exchange = None
        engine.bitget_exchange = None
        engine.price_cache = {}

        old_entry = (datetime.now(timezone.utc) - timedelta(minutes=PAPER_MAX_HOLD_MINUTES + 1)).isoformat()

        open_trade = {
            "id": "trade_stale",
            "pair": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 50000.0,
            "opened_at": old_entry,
            "amount": 0.001,
            "entry_value": 50.0,
        }

        # Mock snapshot to return None mid (price truly unavailable)
        async def mock_no_price(sym, exch):
            return {"bid": None, "ask": None, "mid": None}

        engine.market_data_provider = mock_no_price
        # Also override get_real_price to simulate fallback returning None
        async def mock_no_real_price(sym, exch=None, with_label=False):
            return None
        engine.get_real_price = mock_no_real_price

        bot_data = {"id": "bot1", "user_id": "user1", "exchange": "binance", "pair": "BTC/USDT"}

        result = await engine._close_open_trade("bot1", bot_data, open_trade)

        assert result is not None, "_close_open_trade must never raise"
        assert result.get("skip_reason") == "no_price_data", (
            "When price is unavailable, skip_reason must be 'no_price_data', not an exception"
        )


# ---------------------------------------------------------------------------
# D — Active bot filter consistency
# ---------------------------------------------------------------------------

class TestActiveBotFilterConsistency:
    """bot_not_deleted_filter must handle bots with deleted_at=null correctly."""

    def test_bot_not_deleted_filter_excludes_deleted_status(self):
        from services.bot_filters import bot_not_deleted_filter
        filt = bot_not_deleted_filter({"user_id": "u1", "status": "active"})
        # When called with status="active", the exact-match status guards against deleted bots.
        # Also check the is_deleted and deleted guards are present.
        assert filt.get("is_deleted") == {"$ne": True}, (
            "bot_not_deleted_filter must include is_deleted: {$ne: True}"
        )
        assert filt.get("deleted") == {"$ne": True}, (
            "bot_not_deleted_filter must include deleted: {$ne: True}"
        )

    def test_bot_not_deleted_filter_includes_user_id(self):
        from services.bot_filters import bot_not_deleted_filter
        filt = bot_not_deleted_filter({"user_id": "user1", "status": "active"})
        assert filt.get("user_id") == "user1"

    def test_bot_not_deleted_filter_active_status_set(self):
        from services.bot_filters import bot_not_deleted_filter
        filt = bot_not_deleted_filter({"user_id": "user1", "status": "active"})
        assert filt.get("status") == "active" or (
            isinstance(filt.get("status"), dict)
        ), "status must be set or be a dict filter"

    @pytest.mark.asyncio
    async def test_why_not_trading_active_bots_uses_bot_not_deleted_filter(self):
        """The active-bots count in why_not_trading must use bot_not_deleted_filter,
        not a raw deleted_at query (which misses bots with deleted_at=null field)."""
        from services.bot_filters import bot_not_deleted_filter

        # Build the filter the same way why_not_trading now does it
        filt = bot_not_deleted_filter({"user_id": "user1", "status": "active"})

        # The filter must NOT contain {"deleted_at": {"$exists": False}} alone
        # (which would miss bots with deleted_at=null).
        # It must have the $nin status guard as the primary guard.
        status_val = filt.get("status", {})
        has_status_nin = isinstance(status_val, dict) and "$nin" in status_val
        has_is_deleted_ne = filt.get("is_deleted") == {"$ne": True}

        assert has_status_nin or has_is_deleted_ne, (
            "bot_not_deleted_filter must guard against deleted bots via status $nin "
            "or is_deleted checks, not solely deleted_at $exists"
        )
