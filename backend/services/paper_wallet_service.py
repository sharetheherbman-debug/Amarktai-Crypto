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

        wallet = {
            "user_id": user_id,
            "type": "paper",
            "balances": {"ZAR": float(PAPER_STARTING_CAPITAL_ZAR)},
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
        await self.init_db()
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
        return {
            "balances": result.get("balances") or {"ZAR": 0.0},
            "total": 0.0
        }

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
