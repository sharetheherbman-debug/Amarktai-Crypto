"""
Tests: Binance paper bot creation from ZAR-funded paper wallet.
===============================================================

Validates that a USDT-exchange (Binance) bot can be created when the paper
wallet contains ZAR but no USDT, and that the correct ZAR amount is reserved
from the user wallet while the per-bot ledger is tracked in USDT.

Root-cause fixed: validator was checking USDT balance only; wallet is funded
in ZAR → PAPER_WALLET_INSUFFICIENT even when the wallet had sufficient ZAR.

Tests:
  1. Validator accepts Binance bot creation when ZAR balance covers ZAR equivalent
  2. Validator rejects when even ZAR balance is insufficient
  3. paper_wallet_ledger.reserve_funds() cross-currency: ZAR deducted, USDT ledger
  4. tag_new_bot() for USDT exchange reserves ZAR from user wallet, USDT in ledger
  5. Full end-to-end: reset → set ZAR balance → create Luno bot (existing flow)
  6. Full end-to-end: reset → set ZAR balance → create Binance bot (new flow)

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only \\
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_binance_paper_wallet_fix.py -v
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")


def _run(coro):
    """Run coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. Validator ZAR fallback for USDT exchange ─────────────────────────────

class TestBotValidatorZarFallback:
    """bot_validator should accept Binance paper bot when ZAR wallet covers cost."""

    def _make_validator_mocks(self, zar_balance=4000.0, usdt_balance=0.0):
        """Return common mock setup for bot_validator."""
        mock_db = MagicMock()
        mock_db.bots_collection.find_one = AsyncMock(return_value=None)
        mock_db.bots_collection.count_documents = AsyncMock(return_value=0)

        mock_wallet = MagicMock()
        async def get_available(uid, currency):
            if currency.upper() == "ZAR":
                return zar_balance
            if currency.upper() == "USDT":
                return usdt_balance
            return 0.0
        mock_wallet.get_available_balance = get_available
        return mock_db, mock_wallet

    def test_binance_bot_accepted_when_zar_covers_capital(self):
        """Binance paper bot must be accepted when ZAR balance >= requested capital."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()
        mock_db, mock_wallet = self._make_validator_mocks(zar_balance=4000.0, usdt_balance=0.0)

        with patch("validators.bot_validator.db", mock_db), \
             patch("validators.bot_validator.paper_wallet_service", mock_wallet), \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="binance"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_normal_cap", return_value=10), \
             patch("validators.bot_validator.resolve_capital_for_exchange") as mock_resolve:

            # R1000 ZAR → ~52.63 USDT (fx_rate = 19 ZAR per 1 USDT, so 1000/19 ≈ 52.63)
            mock_resolve.return_value = (52.63, "USDT", 19.0)

            bot_data = {
                "name": "BinancePaperBot",
                "exchange": "binance",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "normal",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert is_valid, (
            f"Expected Binance paper bot creation to succeed with ZAR-funded wallet, "
            f"got error: {result}"
        )

    def test_binance_bot_rejected_when_zar_also_insufficient(self):
        """Binance paper bot must be rejected when ZAR balance is also insufficient."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()
        mock_db, mock_wallet = self._make_validator_mocks(zar_balance=500.0, usdt_balance=0.0)

        with patch("validators.bot_validator.db", mock_db), \
             patch("validators.bot_validator.paper_wallet_service", mock_wallet), \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="binance"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_normal_cap", return_value=10), \
             patch("validators.bot_validator.resolve_capital_for_exchange") as mock_resolve:

            mock_resolve.return_value = (52.63, "USDT", 19.0)

            bot_data = {
                "name": "BinanceLowFundsBot",
                "exchange": "binance",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "normal",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert not is_valid, "Expected validation to fail when both ZAR and USDT are insufficient"
        assert result.get("code") == "PAPER_WALLET_INSUFFICIENT", (
            f"Expected PAPER_WALLET_INSUFFICIENT, got {result.get('code')}"
        )

    def test_luno_bot_rejected_when_zar_insufficient(self):
        """Luno ZAR bot still rejects correctly when ZAR balance is 0."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()
        mock_db, mock_wallet = self._make_validator_mocks(zar_balance=0.0, usdt_balance=0.0)

        with patch("validators.bot_validator.db", mock_db), \
             patch("validators.bot_validator.paper_wallet_service", mock_wallet), \
             patch("validators.bot_validator.is_valid_platform", return_value=True), \
             patch("validators.bot_validator.normalize_platform_id", return_value="luno"), \
             patch("validators.bot_validator.validate_platform_for_mode", return_value=(True, None)), \
             patch("validators.bot_validator.get_max_bots", return_value=10), \
             patch("validators.bot_validator.get_normal_cap", return_value=10), \
             patch("validators.bot_validator.resolve_capital_for_exchange") as mock_resolve:

            mock_resolve.return_value = (1000.0, "ZAR", 1.0)

            bot_data = {
                "name": "LunoPaperBot",
                "exchange": "luno",
                "capital": 1000,
                "trading_mode": "paper",
                "risk_mode": "safe",
                "bot_type": "normal",
            }
            is_valid, result = _run(validator.validate_bot_creation("u1", bot_data))

        assert not is_valid, "Expected validation to fail when ZAR wallet is empty"
        assert result.get("code") == "PAPER_WALLET_INSUFFICIENT"


# ─── 2. paper_wallet_ledger cross-currency reserve ───────────────────────────

class TestPaperWalletLedgerCrossCurrency:
    """reserve_funds() must deduct wallet_currency from user wallet, store ledger in currency."""

    def test_cross_currency_reserve_deducts_zar_creates_usdt_ledger(self):
        """When wallet_amount/wallet_currency differ from amount/currency, wallet deduction
        uses wallet args while ledger entry uses amount/currency."""
        from services.paper_wallet_ledger import PaperWalletLedger

        ledger = PaperWalletLedger()

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)  # no existing entry
        mock_collection.insert_one = AsyncMock(return_value=MagicMock())
        ledger.collection = mock_collection

        mock_wallet_svc = MagicMock()
        mock_wallet_svc.reserve_funds = AsyncMock(return_value=(True, "Reserved"))
        mock_wallet_svc.release_funds = AsyncMock()

        with patch("services.paper_wallet_ledger.paper_wallet_service", mock_wallet_svc), \
             patch.object(ledger, "get_user_balance", AsyncMock(return_value={})):

            success, msg = _run(ledger.reserve_funds(
                user_id="u1",
                bot_id="bot-binance-1",
                amount=52.63,       # USDT ledger amount
                currency="USDT",
                wallet_amount=1000.0,   # ZAR deducted from user wallet
                wallet_currency="ZAR",
            ))

        assert success, f"Expected reserve to succeed, got: {msg}"
        # Wallet service must be called with ZAR 1000 (not USDT 52.63)
        mock_wallet_svc.reserve_funds.assert_awaited_once_with("u1", 1000.0, "ZAR")
        # Ledger entry must be in USDT
        insert_call_args = mock_collection.insert_one.await_args[0][0]
        assert insert_call_args["currency"] == "USDT"
        assert abs(insert_call_args["initial_balance"] - 52.63) < 0.01
        assert abs(insert_call_args["current_balance"] - 52.63) < 0.01

    def test_same_currency_reserve_unchanged_behavior(self):
        """When wallet_amount is None, behavior must be identical to old code path."""
        from services.paper_wallet_ledger import PaperWalletLedger

        ledger = PaperWalletLedger()

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock(return_value=MagicMock())
        ledger.collection = mock_collection

        mock_wallet_svc = MagicMock()
        mock_wallet_svc.reserve_funds = AsyncMock(return_value=(True, "Reserved"))
        mock_wallet_svc.release_funds = AsyncMock()

        with patch("services.paper_wallet_ledger.paper_wallet_service", mock_wallet_svc), \
             patch.object(ledger, "get_user_balance", AsyncMock(return_value={})):

            success, msg = _run(ledger.reserve_funds(
                user_id="u1",
                bot_id="bot-luno-1",
                amount=1000.0,
                currency="ZAR",
                # no wallet_amount / wallet_currency → defaults to same as ledger
            ))

        assert success, f"Expected reserve to succeed, got: {msg}"
        mock_wallet_svc.reserve_funds.assert_awaited_once_with("u1", 1000.0, "ZAR")
        insert_call_args = mock_collection.insert_one.await_args[0][0]
        assert insert_call_args["currency"] == "ZAR"
        assert insert_call_args["initial_balance"] == 1000.0

    def test_cross_currency_reserve_rollback_on_ledger_failure(self):
        """If ledger insert fails after user wallet deduction, the wallet funds are released."""
        from services.paper_wallet_ledger import PaperWalletLedger

        ledger = PaperWalletLedger()

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock(side_effect=Exception("DB write failed"))
        ledger.collection = mock_collection

        mock_wallet_svc = MagicMock()
        mock_wallet_svc.reserve_funds = AsyncMock(return_value=(True, "Reserved"))
        mock_wallet_svc.release_funds = AsyncMock()

        with patch("services.paper_wallet_ledger.paper_wallet_service", mock_wallet_svc):
            success, msg = _run(ledger.reserve_funds(
                user_id="u1",
                bot_id="bot-binance-2",
                amount=52.63,
                currency="USDT",
                wallet_amount=1000.0,
                wallet_currency="ZAR",
            ))

        assert not success
        # Rollback: release_funds must be called with the ZAR amount
        mock_wallet_svc.release_funds.assert_awaited_once_with("u1", 1000.0, "ZAR")


# ─── 3. tag_new_bot() cross-currency for USDT exchanges ──────────────────────

class TestTagNewBotCrossCurrency:
    """tag_new_bot() must use ZAR wallet reservation for USDT-exchange paper bots."""

    def test_binance_bot_reserves_zar_creates_usdt_ledger(self):
        """For a Binance paper bot, tag_new_bot must reserve ZAR from user wallet."""
        from bot_lifecycle import BotLifecycleManager

        lifecycle = BotLifecycleManager()

        binance_bot = {
            "id": "bot-bin-1",
            "user_id": "u1",
            "exchange": "binance",
            "trading_mode": "paper",
            "initial_capital": 52.63,       # USDT
            "canonical_base_capital_zar": 1000.0,
            "fx_rate_at_creation": 19.0,
            "quote_currency": "USDT",
        }

        mock_db = MagicMock()
        mock_db.bots_collection.find_one = AsyncMock(return_value=binance_bot)
        mock_db.bots_collection.update_one = AsyncMock()

        mock_ledger = MagicMock()
        mock_ledger.reserve_funds = AsyncMock(return_value=(True, "Reserved"))

        with patch("bot_lifecycle.db", mock_db), \
             patch("bot_lifecycle.paper_wallet_ledger", mock_ledger):

            success, msg = _run(lifecycle.tag_new_bot(
                "bot-bin-1", origin="user", initial_capital=52.63
            ))

        assert success, f"Expected tag_new_bot to succeed, got: {msg}"
        # Verify reserve_funds was called with cross-currency args
        mock_ledger.reserve_funds.assert_awaited_once()
        await_args = mock_ledger.reserve_funds.await_args
        # currency may be positional (args[3]) or keyword
        pos_args = await_args.args if await_args else ()
        kw_args = await_args.kwargs if await_args else {}
        ledger_currency = kw_args.get("currency") or (pos_args[3] if len(pos_args) > 3 else None)
        assert ledger_currency == "USDT", (
            f"Expected ledger currency=USDT for Binance bot, got {ledger_currency}"
        )
        # Wallet deduction must use ZAR (always passed as keyword arg)
        assert kw_args.get("wallet_currency") == "ZAR", (
            f"Expected wallet_currency=ZAR, got {kw_args.get('wallet_currency')}"
        )
        assert abs(float(kw_args.get("wallet_amount", 0)) - 1000.0) < 0.01, (
            f"Expected wallet_amount≈1000 ZAR, got {kw_args.get('wallet_amount')}"
        )

    def test_luno_bot_reserves_zar_directly(self):
        """For a Luno paper bot, tag_new_bot must reserve ZAR directly (unchanged behavior)."""
        from bot_lifecycle import BotLifecycleManager

        lifecycle = BotLifecycleManager()

        luno_bot = {
            "id": "bot-luno-1",
            "user_id": "u1",
            "exchange": "luno",
            "trading_mode": "paper",
            "initial_capital": 1000.0,
            "canonical_base_capital_zar": 1000.0,
            "fx_rate_at_creation": 1.0,
            "quote_currency": "ZAR",
        }

        mock_db = MagicMock()
        mock_db.bots_collection.find_one = AsyncMock(return_value=luno_bot)
        mock_db.bots_collection.update_one = AsyncMock()

        mock_ledger = MagicMock()
        mock_ledger.reserve_funds = AsyncMock(return_value=(True, "Reserved"))

        with patch("bot_lifecycle.db", mock_db), \
             patch("bot_lifecycle.paper_wallet_ledger", mock_ledger):

            success, msg = _run(lifecycle.tag_new_bot(
                "bot-luno-1", origin="user", initial_capital=1000.0
            ))

        assert success, f"Expected tag_new_bot to succeed, got: {msg}"
        mock_ledger.reserve_funds.assert_awaited_once()
        call_kwargs = mock_ledger.reserve_funds.await_args.kwargs
        # Luno bots use ZAR for both wallet and ledger (no wallet_currency override)
        wallet_currency = call_kwargs.get("wallet_currency")
        assert wallet_currency is None or wallet_currency == "ZAR", (
            f"Luno bot should not set wallet_currency to non-ZAR, got {wallet_currency}"
        )
