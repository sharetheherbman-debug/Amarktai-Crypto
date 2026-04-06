"""
Wallet summary service for funding readiness and balances.
"""

from datetime import datetime, timezone
from typing import Dict, List
import logging

import database as db
from config import PAPER_STARTING_CAPITAL_ZAR
from utils.bot_state import normalize_bot_state
from services.system_mode_service import system_mode_service

logger = logging.getLogger(__name__)


class WalletSummaryService:
    def __init__(self):
        self._warned_missing_wallets = set()

    async def _get_wallet_doc(self, user_id: str) -> Dict | None:
        if db.wallet_balances_collection is None:
            return None
        return await db.wallet_balances_collection.find_one({"user_id": user_id}, {"_id": 0})

    async def _get_injected_capital(self, user_id: str) -> float:
        if db.capital_injections_collection is None:
            return 0.0
        injections = await db.capital_injections_collection.find(
            {"user_id": user_id},
            {"_id": 0, "amount": 1}
        ).to_list(1000)
        return sum(float(inj.get("amount", 0)) for inj in injections)

    async def _ensure_paper_wallet_doc(self, user_id: str, balance: float) -> Dict:
        if db.wallet_balances_collection is None:
            return {"user_id": user_id, "paper_wallet_balance_zar": balance}

        await db.wallet_balances_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "paper_wallet_balance_zar": balance,
                    "paper_wallet_updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {"user_id": user_id}
            },
            upsert=True
        )
        return await self._get_wallet_doc(user_id) or {"user_id": user_id, "paper_wallet_balance_zar": balance}

    async def _sync_paper_wallet_balance(self, user_id: str, balance: float) -> None:
        if db.wallet_balances_collection is None:
            return
        await db.wallet_balances_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "paper_wallet_balance_zar": round(balance, 2),
                    "paper_wallet_updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )

    async def _get_paper_balance(self, user_id: str) -> float:
        from services.paper_wallet_ledger import paper_wallet_ledger
        from services.paper_wallet_service import paper_wallet_service

        # Prefer the canonical paper_wallet_ledger (per-bot reserved balance)
        balance = await paper_wallet_ledger.get_user_balance(user_id)
        if balance is not None:
            await self._sync_paper_wallet_balance(user_id, balance)
            return balance

        # Fall back to the direct wallet document (what paper_wallet_service writes)
        try:
            result = await paper_wallet_service.get_balances(user_id)
            available = result.get("total", None)
            if available is not None:
                await self._sync_paper_wallet_balance(user_id, float(available))
                return float(available)
        except Exception as e:
            logger.debug("paper_wallet_service.get_balances fallback failed: %s", e)

        # Wallet does not exist yet – return 0 (UNFUNDED).
        # Do NOT auto-create with PAPER_STARTING_CAPITAL_ZAR; the user must
        # explicitly fund the wallet.
        if user_id not in self._warned_missing_wallets:
            logger.info(
                "Paper wallet not yet funded for user %s. Returning 0.",
                user_id[:8],
            )
            self._warned_missing_wallets.add(user_id)

        return 0.0

    async def _get_live_balance(self, user_id: str) -> float:
        wallet_doc = await self._get_wallet_doc(user_id) or {}
        master_wallet = wallet_doc.get("master_wallet", {})
        total = float(master_wallet.get("total_zar", 0) or 0)

        exchanges = wallet_doc.get("exchanges", {}) or {}
        for exchange_data in exchanges.values():
            total += float(
                exchange_data.get("total_zar")
                or exchange_data.get("available_zar")
                or exchange_data.get("zar_balance")
                or 0
            )

        if total <= 0:
            try:
                from engines.wallet_manager import wallet_manager
                master_balance = await wallet_manager.get_master_balance(user_id)
                if not master_balance.get("error"):
                    total = float(master_balance.get("total_zar", 0))
            except Exception as e:
                logger.debug(f"Live balance fallback failed: {e}")

        return total

    async def get_summary(self, user_id: str) -> Dict:
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(2000)
        normalized = [normalize_bot_state(bot) for bot in bots]
        mode = await system_mode_service.get_current_mode(user_id)
        active_bots = [
            b for b in normalized
            if b.get("active")
            and (b.get("trading_mode") or b.get("mode") or "paper") == mode
        ]
        non_deleted = [b for b in normalized if not b.get("is_deleted")]

        required_funds = sum(
            float(b.get("initial_capital") or 1000) for b in active_bots
        )
        allocated_funds = sum(
            float(b.get("allocated_capital") or b.get("initial_capital") or 1000)
            for b in non_deleted
        )
        reserved_funds = 0.0
        if db.wallet_balances_collection is not None:
            reserved_docs = await db.wallet_balances_collection.find(
                {"user_id": user_id, "reserved": {"$exists": True}},
                {"_id": 0, "reserved": 1}
            ).to_list(2000)
            reserved_funds = sum(float(doc.get("reserved", 0) or 0) for doc in reserved_docs)
        available_wallet = await (
            self._get_paper_balance(user_id) if mode == "paper" else self._get_live_balance(user_id)
        )

        shortfall = max(0.0, required_funds - available_wallet)
        status = "FUNDED" if shortfall <= 0 else "UNDERFUNDED"

        return {
            "success": True,
            "mode": mode,
            "active_bots_count": len(active_bots),
            "required_funds_zar": round(required_funds, 2),
            "allocated_funds_zar": round(allocated_funds, 2),
            "available_wallet_zar": round(available_wallet, 2),
            "reserved_funds_zar": round(reserved_funds, 2),
            "shortfall_zar": round(shortfall, 2),
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


wallet_summary_service = WalletSummaryService()
