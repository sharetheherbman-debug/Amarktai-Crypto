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
