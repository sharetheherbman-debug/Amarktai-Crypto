"""
Funding Router - ZAR → USDT → Exchange allocation

Luno is the funding source in ZAR.
1. ZAR wallet buys USDT (paper first; later live).
2. USDT is allocated/credited to other exchange paper wallets.
3. All conversions/transfers create ledger entries.

Ledger event types:
  CONVERT_ZAR_USDT       — ZAR converted to USDT on Luno
  TRANSFER_USDT_TO_EXCHANGE — USDT sent from Luno to another exchange
"""

from datetime import datetime, timezone
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Paper conversion rate (approximate; live would use market price)
DEFAULT_ZAR_USDT_RATE = 18.50  # ~R18.50 per 1 USDT (illustrative)


async def convert_zar_to_usdt(
    user_id: str,
    zar_amount: float,
    db,
    rate: Optional[float] = None,
    is_paper: bool = True,
) -> Dict:
    """
    Convert ZAR to USDT in the user's paper wallet and record ledger event.

    Returns: { "usdt_amount": float, "rate": float, "event_id": str }
    """
    rate = rate or DEFAULT_ZAR_USDT_RATE
    usdt_amount = round(zar_amount / rate, 6)

    # Record ledger event
    event_doc = {
        "user_id": user_id,
        "event_type": "CONVERT_ZAR_USDT",
        "amount_zar": zar_amount,
        "amount_usdt": usdt_amount,
        "rate": rate,
        "currency_from": "ZAR",
        "currency_to": "USDT",
        "is_paper": is_paper,
        "timestamp": datetime.now(timezone.utc),
        "metadata": {"source": "luno", "type": "conversion"},
    }
    result = await db["ledger_events"].insert_one(event_doc)
    event_id = str(result.inserted_id)

    # Update paper wallets
    await db["paper_wallets"].update_one(
        {"user_id": user_id},
        {
            "$inc": {
                "zar_available": -zar_amount,
                "usdt_available": usdt_amount,
            },
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    logger.info(
        f"Converted R{zar_amount:.2f} ZAR → {usdt_amount:.6f} USDT @ {rate} for user {user_id}"
    )
    return {"usdt_amount": usdt_amount, "rate": rate, "event_id": event_id}


async def allocate_usdt_to_exchange(
    user_id: str,
    exchange: str,
    usdt_amount: float,
    db,
    is_paper: bool = True,
) -> Dict:
    """
    Allocate USDT from user's central wallet to a specific exchange paper wallet.

    Returns: { "exchange": str, "amount": float, "event_id": str }
    """
    # Record ledger event
    event_doc = {
        "user_id": user_id,
        "event_type": "TRANSFER_USDT_TO_EXCHANGE",
        "amount": usdt_amount,
        "currency": "USDT",
        "exchange": exchange,
        "is_paper": is_paper,
        "timestamp": datetime.now(timezone.utc),
        "metadata": {"source": "central_wallet", "destination": exchange},
    }
    result = await db["ledger_events"].insert_one(event_doc)
    event_id = str(result.inserted_id)

    # Debit central USDT wallet
    await db["paper_wallets"].update_one(
        {"user_id": user_id},
        {"$inc": {"usdt_available": -usdt_amount}},
    )

    # Credit exchange-specific wallet
    await db["exchange_wallets"].update_one(
        {"user_id": user_id, "exchange": exchange},
        {
            "$inc": {"usdt_available": usdt_amount},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    logger.info(
        f"Allocated {usdt_amount:.6f} USDT → {exchange} for user {user_id}"
    )
    return {"exchange": exchange, "amount": usdt_amount, "event_id": event_id}


async def get_funding_status(user_id: str, db) -> Dict:
    """
    Return current funding status across all exchange wallets.
    """
    central = await db["paper_wallets"].find_one({"user_id": user_id}) or {}
    exchange_wallets = await db["exchange_wallets"].find(
        {"user_id": user_id}
    ).to_list(length=20)

    return {
        "zar_available": float(central.get("zar_available", 0)),
        "usdt_available": float(central.get("usdt_available", 0)),
        "exchange_allocations": [
            {
                "exchange": w.get("exchange"),
                "usdt_available": float(w.get("usdt_available", 0)),
            }
            for w in exchange_wallets
        ],
    }
