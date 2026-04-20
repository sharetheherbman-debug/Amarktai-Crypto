"""
Paper Wallet Service - Per-user simulated wallet balances.
Manages available (unallocated) paper funds with per-currency balances.
"""

import asyncio
import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pymongo import ReturnDocument

import database as db
from config import PAPER_STARTING_CAPITAL_ZAR

logger = logging.getLogger(__name__)

# Default static ZAR/USDT rate for paper mode.  Configurable via env var.
_PAPER_ZAR_PER_USDT_DEFAULT: float = float(os.getenv("PAPER_ZAR_PER_USDT", "18.5"))

# Sanity bounds for the live-derived FX rate: typical ZAR/USDT is ~10–40.
_PAPER_FX_RATE_MIN: float = 5.0
_PAPER_FX_RATE_MAX: float = 100.0

# Negative-cache: after a failed live-rate fetch, skip retries for this many
# seconds to avoid hammering exchange APIs on every request.
_FX_NEGATIVE_CACHE_TTL: float = 30.0
_fx_last_failed_at: float = 0.0

# Hard cap on total time spent fetching the live FX rate.  Must be well under
# nginx's proxy_read_timeout (30 s) so the HTTP request always completes.
_FX_FETCH_TIMEOUT: float = float(os.getenv("PAPER_FX_FETCH_TIMEOUT_SECONDS", "5"))


async def _get_paper_zar_per_usdt() -> float:
    """Return the ZAR-per-USDT rate to use for paper FX conversion.

    Resolution order (paper-only — never used for live trades):
    1. Try to derive a live rate via the price fallback service if it has
       been initialised and has cached Luno/Binance prices.
       Capped at _FX_FETCH_TIMEOUT seconds to prevent nginx 502 storms
       caused by slow exchange responses.
    2. Fall back to the PAPER_ZAR_PER_USDT environment variable
       (default 18.5) — a conservative mid-market approximation.

    Never raises — always returns a positive float.
    """
    global _fx_last_failed_at

    # Skip live fetch while in the negative-cache window (recent failure).
    now_mono = _time.monotonic()
    if now_mono - _fx_last_failed_at < _FX_NEGATIVE_CACHE_TTL:
        return _PAPER_ZAR_PER_USDT_DEFAULT

    try:
        from services.price_fallback_service import price_fallback_service
        async with asyncio.timeout(_FX_FETCH_TIMEOUT):
            btczar = await price_fallback_service.get_price("luno", "BTC/ZAR")
            btcusdt = await price_fallback_service.get_price("binance", "BTC/USDT")
        if btczar and btcusdt and btcusdt > 0:
            rate = round(btczar / btcusdt, 4)
            if _PAPER_FX_RATE_MIN < rate < _PAPER_FX_RATE_MAX:
                logger.debug("Paper FX: live USDZAR rate %.4f", rate)
                return rate
        # Prices fetched but not usable — set negative cache
        _fx_last_failed_at = _time.monotonic()
    except Exception:
        # Timeout or any other error — set negative cache to avoid repeated
        # slow retries that would cause cascading nginx 502s.
        _fx_last_failed_at = _time.monotonic()

    return _PAPER_ZAR_PER_USDT_DEFAULT


class PaperWalletService:
    def __init__(self):
        self.collection = None

    async def init_db(self):
        if self.collection is None:
            self.collection = db.wallets_collection
        if self.collection is None:
            raise RuntimeError("Wallets collection not initialized")

    async def _ensure_wallet(self, user_id: str) -> Dict:
        await self.init_db()

        wallet = await self.collection.find_one(
            {"user_id": user_id, "type": "paper"},
            {"_id": 0}
        )
        if wallet:
            return wallet

        # Auto-fund new paper wallets with PAPER_STARTING_CAPITAL_ZAR so that
        # paper-trading is immediately usable after deploy / first login.
        # The admin can still reset or adjust via /api/wallet/paper/reset or
        # /api/wallet/paper/set-balance.
        initial_capital = max(0.0, PAPER_STARTING_CAPITAL_ZAR)
        wallet = {
            "user_id": user_id,
            "type": "paper",
            "balances": {"ZAR": initial_capital},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await self.collection.insert_one(wallet)
        if initial_capital > 0:
            logger.info(
                "Paper wallet auto-funded with R%.2f ZAR for user %s",
                initial_capital, user_id[:8],
            )
        return wallet

    async def get_balances(self, user_id: str) -> Dict:
        wallet = await self._ensure_wallet(user_id)
        balances = wallet.get("balances") or {}
        # Convert non-ZAR currencies to ZAR before summing portfolio total.
        # USDT is the only non-ZAR currency currently held in paper wallets.
        usdt_to_zar = await _get_paper_zar_per_usdt()
        total = 0.0
        for currency, value in balances.items():
            v = float(value or 0)
            if currency.upper() == "USDT":
                total += v * usdt_to_zar
            else:
                total += v
        return {
            "balances": balances,
            "total": round(total, 2)
        }

    async def get_wallet_status(self, user_id: str) -> Dict:
        """Canonical wallet status for diagnostics and API consumers.

        Returns:
            {
                "balances": {"ZAR": float, ...},
                "total": float,
                "available_zar": float,
                "funded": bool,
                "updated_at": str | None,
            }
        """
        wallet = await self._ensure_wallet(user_id)
        balances = wallet.get("balances") or {}
        # Convert non-ZAR currencies to ZAR before computing total portfolio value.
        usdt_to_zar = await _get_paper_zar_per_usdt()
        total = 0.0
        for currency, value in balances.items():
            v = float(value or 0)
            if currency.upper() == "USDT":
                total += v * usdt_to_zar
            else:
                total += v
        total = round(total, 2)
        available_zar = float(balances.get("ZAR", 0))
        return {
            "balances": balances,
            "total": total,
            "available_zar": available_zar,
            "funded": total > 0,
            "updated_at": wallet.get("updated_at"),
        }

    async def get_available_balance(self, user_id: str, currency: str) -> float:
        wallet = await self._ensure_wallet(user_id)
        balances = wallet.get("balances") or {}
        return float(balances.get(currency.upper(), 0))

    async def deposit(self, user_id: str, amount: float, currency: str) -> Dict:
        await self.init_db()
        currency = currency.upper()
        result = await self.collection.find_one_and_update(
            {"user_id": user_id, "type": "paper"},
            {
                "$inc": {f"balances.{currency}": amount},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                "$setOnInsert": {
                    "user_id": user_id,
                    "type": "paper",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        balances = result.get("balances") or {}
        usdt_to_zar = await _get_paper_zar_per_usdt()
        total = 0.0
        for cur, value in balances.items():
            v = float(value or 0)
            total += v * usdt_to_zar if cur.upper() == "USDT" else v
        return {
            "balances": balances,
            "total": round(total, 2)
        }

    async def reset(self, user_id: str) -> Dict:
        """Reset paper wallet to ZERO balance (unfunded state).

        Per hard requirement: after a reset the wallet must show balance=0 and
        allocated=0.  The system remains UNFUNDED until the user explicitly
        funds it via the /api/wallet/paper/fund endpoint.
        """
        await self.init_db()
        # Capture balance before reset
        existing = await self.collection.find_one(
            {"user_id": user_id, "type": "paper"},
            {"_id": 0, "balances": 1}
        )
        wallet_before = (existing or {}).get("balances", {})

        result = await self.collection.find_one_and_update(
            {"user_id": user_id, "type": "paper"},
            {
                "$set": {
                    "balances": {"ZAR": 0.0},
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "type": "paper",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        wallet_after = result.get("balances") or {"ZAR": 0.0}
        return {
            "balances": wallet_after,
            "total": round(sum(float(v or 0) for v in wallet_after.values()), 2),
            "wallet_before": wallet_before,
            "wallet_after": wallet_after,
        }

    async def fund(self, user_id: str, amount: float, currency: str = "ZAR") -> Dict:
        """Explicitly fund the paper wallet (user action, not auto-init).

        This is the ONLY path that should add starting capital.  It requires
        ``amount > 0`` and logs an audit event via the caller.
        """
        if amount <= 0:
            raise ValueError(f"Fund amount must be positive, got {amount}")
        return await self.deposit(user_id, amount, currency)

    async def reserve_funds(self, user_id: str, amount: float, currency: str) -> Tuple[bool, str]:
        await self._ensure_wallet(user_id)
        currency = currency.upper()
        result = await self.collection.find_one_and_update(
            {
                "user_id": user_id,
                "type": "paper",
                f"balances.{currency}": {"$gte": amount}
            },
            {
                "$inc": {f"balances.{currency}": -amount},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            },
            return_document=ReturnDocument.AFTER
        )
        if not result:
            # If USDT is needed but only ZAR is available, auto-convert using paper FX rate.
            # This allows Binance/KuCoin/Bybit/Bitget/Gate/Kraken paper bots to start
            # without manual USDT funding.
            if currency == "USDT":
                # Resolve the ZAR→USDT paper FX rate.
                # Prefer a live rate if available; fall back to the env-configurable
                # static rate (PAPER_ZAR_PER_USDT, default 18.5).
                fx_rate = await _get_paper_zar_per_usdt()
                zar_required = amount * fx_rate
                # Single atomic operation: deduct ZAR equivalent (simulate ZAR→USDT conversion)
                fx_result = await self.collection.find_one_and_update(
                    {
                        "user_id": user_id,
                        "type": "paper",
                        "balances.ZAR": {"$gte": zar_required}
                    },
                    {
                        "$inc": {"balances.ZAR": -zar_required},
                        "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                    },
                    return_document=ReturnDocument.AFTER
                )
                if fx_result:
                    return True, f"Paper FX: R{zar_required:.2f} ZAR → {amount:.2f} USDT (rate {fx_rate})"
            available = await self.get_available_balance(user_id, currency)
            return False, f"Insufficient paper wallet balance. Available: {available:.2f} {currency}"
        return True, "Reserved"

    async def release_funds(self, user_id: str, amount: float, currency: str) -> None:
        await self.init_db()
        currency = currency.upper()
        await self.collection.update_one(
            {"user_id": user_id, "type": "paper"},
            {
                "$inc": {f"balances.{currency}": amount},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            },
            upsert=True
        )

    # ------------------------------------------------------------------
    # Per-exchange (per-platform) paper wallet helpers
    # ------------------------------------------------------------------
    # Each exchange has its own wallet document:
    #   { user_id, type: "paper_exchange", exchange: "luno", balances: {ZAR: X} }
    # These are the canonical per-platform paper wallets.  The global "paper"
    # wallet (type="paper") is kept for backward compatibility.
    # ------------------------------------------------------------------

    _EXCHANGE_NATIVE_CURRENCY: Dict[str, str] = {
        "luno":     "ZAR",
        "binance":  "USDT",
        "kucoin":   "USDT",
        "bybit":    "USDT",
        "kraken":   "USDT",
        "bitget":   "USDT",
        "gate":     "USDT",
        "coinbase": "USDT",
    }

    @classmethod
    def native_currency_for(cls, exchange: str) -> str:
        """Return the canonical paper-wallet currency for an exchange."""
        return cls._EXCHANGE_NATIVE_CURRENCY.get(exchange.lower(), "USDT")

    @classmethod
    def _native_currency_for(cls, exchange: str) -> str:
        """Alias kept for internal backward-compatibility."""
        return cls.native_currency_for(exchange)

    async def _ensure_exchange_wallet(self, user_id: str, exchange: str) -> Dict:
        """Return (or create) the per-exchange paper wallet document.

        Per-exchange wallets start at 0 balance — the user funds them manually.
        """
        await self.init_db()
        exchange = exchange.lower()
        wallet = await self.collection.find_one(
            {"user_id": user_id, "type": "paper_exchange", "exchange": exchange},
            {"_id": 0},
        )
        if wallet:
            return wallet
        native = self._native_currency_for(exchange)
        wallet = {
            "user_id": user_id,
            "type": "paper_exchange",
            "exchange": exchange,
            "balances": {native: 0.0},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.collection.insert_one(wallet)
        return wallet

    async def get_exchange_wallet(self, user_id: str, exchange: str) -> Dict:
        """Return per-exchange paper wallet status."""
        exchange = exchange.lower()
        wallet = await self._ensure_exchange_wallet(user_id, exchange)
        balances = wallet.get("balances") or {}
        native = self.native_currency_for(exchange)
        available = float(balances.get(native, 0) or 0)
        return {
            "exchange": exchange,
            "balances": balances,
            "native_currency": native,
            "available": available,
            "funded": available > 0,
            "updated_at": wallet.get("updated_at"),
        }

    async def get_all_exchange_wallets(self, user_id: str) -> Dict[str, Dict]:
        """Return all per-exchange paper wallets keyed by exchange name."""
        await self.init_db()
        try:
            docs = await self.collection.find(
                {"user_id": user_id, "type": "paper_exchange"},
                {"_id": 0},
            ).to_list(20)
        except Exception as exc:
            logger.warning("get_all_exchange_wallets failed for %s: %s", user_id[:8], exc)
            return {}
        result: Dict[str, Dict] = {}
        for doc in docs:
            exch = doc.get("exchange", "")
            if exch:
                balances = doc.get("balances") or {}
                native = self._native_currency_for(exch)
                available = float(balances.get(native, 0) or 0)
                result[exch] = {
                    "exchange": exch,
                    "balances": balances,
                    "native_currency": native,
                    "available": available,
                    "funded": available > 0,
                    "updated_at": doc.get("updated_at"),
                }
        return result

    async def fund_exchange_wallet(
        self,
        user_id: str,
        exchange: str,
        amount: float,
        currency: Optional[str] = None,
    ) -> Dict:
        """Fund a per-exchange paper wallet.

        Args:
            user_id:  User ID.
            exchange: Exchange name (e.g. 'luno', 'binance').
            amount:   Positive amount to add.
            currency: Currency code; defaults to the exchange's native currency.
        """
        if amount <= 0:
            raise ValueError(f"Fund amount must be positive, got {amount}")
        await self.init_db()
        exchange = exchange.lower()
        native = self._native_currency_for(exchange)
        currency = (currency or native).upper()
        now_iso = datetime.now(timezone.utc).isoformat()
        result = await self.collection.find_one_and_update(
            {"user_id": user_id, "type": "paper_exchange", "exchange": exchange},
            {
                "$inc": {f"balances.{currency}": amount},
                "$set": {"updated_at": now_iso},
                "$setOnInsert": {
                    "user_id": user_id,
                    "type": "paper_exchange",
                    "exchange": exchange,
                    "created_at": now_iso,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        balances = (result or {}).get("balances") or {}
        available = float(balances.get(native, 0) or 0)
        return {
            "exchange": exchange,
            "balances": balances,
            "native_currency": native,
            "available": available,
            "funded": available > 0,
            "updated_at": now_iso,
        }

    async def reset_exchange_wallet(self, user_id: str, exchange: str) -> Dict:
        """Reset a per-exchange paper wallet to zero balance."""
        await self.init_db()
        exchange = exchange.lower()
        native = self._native_currency_for(exchange)
        now_iso = datetime.now(timezone.utc).isoformat()
        await self.collection.update_one(
            {"user_id": user_id, "type": "paper_exchange", "exchange": exchange},
            {
                "$set": {
                    "balances": {native: 0.0},
                    "updated_at": now_iso,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "type": "paper_exchange",
                    "exchange": exchange,
                    "created_at": now_iso,
                },
            },
            upsert=True,
        )
        return {
            "exchange": exchange,
            "balances": {native: 0.0},
            "native_currency": native,
            "available": 0.0,
            "funded": False,
            "updated_at": now_iso,
        }

    async def reserve_exchange_funds(
        self, user_id: str, exchange: str, amount: float, currency: str
    ) -> Tuple[bool, str]:
        """Atomically reserve funds from a per-exchange paper wallet.

        Falls back to the global paper wallet if the exchange wallet is empty,
        preserving backward-compatibility with single-wallet seeding.
        """
        await self.init_db()
        exchange = exchange.lower()
        currency = currency.upper()
        native = self._native_currency_for(exchange)
        now_iso = datetime.now(timezone.utc).isoformat()

        result = await self.collection.find_one_and_update(
            {
                "user_id": user_id,
                "type": "paper_exchange",
                "exchange": exchange,
                f"balances.{currency}": {"$gte": amount},
            },
            {
                "$inc": {f"balances.{currency}": -amount},
                "$set": {"updated_at": now_iso},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result:
            return True, f"Reserved {amount:.2f} {currency} from {exchange} wallet"

        # Exchange wallet has insufficient funds — do NOT fall back to the global
        # paper wallet.  Each exchange is funded independently; cross-exchange
        # capital sharing is prohibited by the platform-wallet architecture.
        available = float(
            (await self.get_exchange_wallet(user_id, exchange)).get("available", 0) or 0
        )
        return False, (
            f"Insufficient {exchange} paper wallet balance. "
            f"Available: {available:.2f} {native}. "
            "Fund this exchange wallet via /api/wallet/platform/{exchange}/fund."
        )


paper_wallet_service = PaperWalletService()
