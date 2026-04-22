"""
Exchange Status & Test Endpoints

Provides:
  GET  /api/exchanges/status      — status of all 7 exchanges for the authenticated user
  POST /api/exchanges/test        — test connectivity to a specific exchange
  GET  /api/exchanges/paper-cohort — paper-mode bot cohort status per exchange
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict
from datetime import datetime, timezone
import logging

import database as db
from auth import get_current_user
from services.exchange_adapter import exchange_adapter, SUPPORTED_EXCHANGES
from utils.bot_state import normalize_bot_state, is_active_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exchanges", tags=["Exchanges"])


@router.get("/status")
async def exchanges_status(user_id: str = Depends(get_current_user)):
    """
    GET /api/exchanges/status

    Returns configuration + readiness status for all 7 supported exchanges.
    Shows: configured/not, last tested, pass/fail, error reason, default pairs.
    """
    results = []
    for ex in SUPPORTED_EXCHANGES:
        status = await exchange_adapter.get_exchange_status(ex, user_id=user_id)
        results.append(status)

    return {
        "total": len(results),
        "configured_count": sum(1 for s in results if s.get("configured")),
        "exchanges": results,
    }


@router.post("/test")
async def test_exchange(
    user_id: str = Depends(get_current_user),
    payload: Dict = Body(...),
):
    """
    POST /api/exchanges/test

    Test connectivity to a specific exchange.
    Body: { "exchange": "binance" }
    Optional: { "exchange": "binance", "api_key": "...", "secret": "..." }
    """
    exchange = payload.get("exchange", "").lower()
    if not exchange:
        raise HTTPException(status_code=400, detail="exchange is required")
    if not exchange_adapter.is_supported(exchange):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange}. Supported: {SUPPORTED_EXCHANGES}",
        )

    api_key = payload.get("api_key", "")
    secret = payload.get("secret", "")
    passphrase = payload.get("passphrase", "")

    result = await exchange_adapter.test_connection(
        exchange, api_key=api_key, secret=secret, passphrase=passphrase
    )

    return result


@router.get("/paper-cohort")
async def get_paper_cohort(user_id: str = Depends(get_current_user)):
    """GET /api/exchanges/paper-cohort

    Returns per-exchange cohort status for the authenticated user's paper fleet:
    - how many bots are active / paused / total per exchange
    - whether the exchange has a funded paper wallet
    - the native currency and available balance

    This is the canonical source for paper-cohort dashboards and radar panels.
    """
    from services.paper_wallet_service import PaperWalletService as _PWS

    _now = datetime.now(timezone.utc).isoformat()

    # Fetch all bots for the user
    try:
        all_bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "id": 1, "exchange": 1, "state": 1, "status": 1, "mode": 1,
             "trading_mode": 1, "bot_type": 1, "name": 1},
        ).to_list(500)
    except Exception as _e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch bots: {_e}")

    # Group by exchange
    cohort: dict = {}
    for bot in all_bots:
        _mode = bot.get("mode") or bot.get("trading_mode", "paper")
        if not str(_mode).strip().lower().startswith("paper"):
            continue  # skip non-paper bots
        _exch = (bot.get("exchange") or "unknown").lower()
        if _exch not in cohort:
            cohort[_exch] = {"exchange": _exch, "total": 0, "active": 0, "paused": 0,
                             "scalper": 0, "normal": 0, "funded": False,
                             "native_currency": None, "available_balance": 0.0}
        _state = normalize_bot_state(bot.get("state") or bot.get("status", ""))
        cohort[_exch]["total"] += 1
        if is_active_bot({"state": _state}):
            cohort[_exch]["active"] += 1
        else:
            cohort[_exch]["paused"] += 1
        _btype = str(bot.get("bot_type") or "normal").lower()
        if _btype == "scalper":
            cohort[_exch]["scalper"] += 1
        else:
            cohort[_exch]["normal"] += 1

    # Enrich with wallet funding status
    try:
        _pws = _PWS()
        existing_wallets = await _pws.get_all_exchange_wallets(user_id)
        for exch, wallet in existing_wallets.items():
            _k = exch.lower()
            if _k not in cohort:
                cohort[_k] = {"exchange": _k, "total": 0, "active": 0, "paused": 0,
                               "scalper": 0, "normal": 0}
            cohort[_k]["funded"] = float(wallet.get("available", 0) or 0) > 0
            cohort[_k]["native_currency"] = wallet.get("native_currency")
            cohort[_k]["available_balance"] = round(float(wallet.get("available", 0) or 0), 4)
    except Exception:
        pass

    _exchanges = sorted(cohort.values(), key=lambda x: x["exchange"])
    return {
        "cohort": _exchanges,
        "funded_exchanges": [e["exchange"] for e in _exchanges if e.get("funded")],
        "total_bots": sum(e["total"] for e in _exchanges),
        "total_active": sum(e["active"] for e in _exchanges),
        "timestamp": _now,
    }
