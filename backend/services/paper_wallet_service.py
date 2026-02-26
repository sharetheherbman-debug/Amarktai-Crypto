"""
Paper Wallet Service - Per-user simulated wallet balances.
Manages available (unallocated) paper funds with per-currency balances.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pymongo import ReturnDocument

import database as db
from config import PAPER_STARTING_CAPITAL_ZAR


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

        # Create an UNFUNDED wallet.  Balance starts at 0; the user must
        # explicitly fund it via the fund() / deposit() methods.
        wallet = {
            "user_id": user_id,
            "type": "paper",
            "balances": {"ZAR": 0.0},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await self.collection.insert_one(wallet)
        return wallet

    async def get_balances(self, user_id: str) -> Dict:
        wallet = await self._ensure_wallet(user_id)
        balances = wallet.get("balances") or {}
        total = sum(float(value or 0) for value in balances.values())
        return {
            "balances": balances,
            "total": round(total, 2)
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
        total = sum(float(value or 0) for value in balances.values())
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
            # This allows Binance/KuCoin paper bots to start without manual USDT funding.
            if currency == "USDT":
                # Paper FX rate: approximate 18.5 ZAR per USDT (conservative)
                PAPER_ZAR_PER_USDT = 18.5
                zar_required = amount * PAPER_ZAR_PER_USDT
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
                    return True, f"Paper FX: R{zar_required:.2f} ZAR → {amount:.2f} USDT (rate {PAPER_ZAR_PER_USDT})"
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


paper_wallet_service = PaperWalletService()
