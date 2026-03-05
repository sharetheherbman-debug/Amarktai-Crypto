"""
Scalper Bot Management Endpoints

Separate endpoints for scalper bot CRUD, cap checking, and profit routing.
Scalper bots are a distinct category from normal bots with independent caps.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
from typing import Dict, Optional
import logging

from auth import get_current_user
import database as db
from exchange_limits import (
    SCALPER_BOT_ALLOCATION,
    MAX_SCALPER_BOTS_GLOBAL,
    get_scalper_cap,
    get_normal_cap,
    compute_scalper_ev,
    get_fee_rate,
    SCALPER_EV_MIN_BPS,
    SCALPER_SPREAD_MAX_BPS,
    SCALPER_MAX_HOLD_SECONDS,
    SCALPER_STAGNATION_SECONDS,
    SCALPER_ORDERS_PER_MIN,
    SCALPER_CANCELS_PER_MIN,
    SCALPER_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scalper", tags=["Scalper Bots"])


@router.get("/caps")
async def scalper_caps(user_id: str = Depends(get_current_user)):
    """
    GET /api/scalper/caps

    Returns per-exchange scalper bot cap usage and global limits.
    """
    bots = await db.bots_collection.find(
        {"user_id": user_id, "deleted": {"$ne": True}, "bot_type": "scalper"}
    ).to_list(length=200)

    per_exchange = {}
    for exchange, cap in SCALPER_BOT_ALLOCATION.items():
        count = sum(1 for b in bots if b.get("exchange") == exchange)
        per_exchange[exchange] = {"current": count, "cap": cap, "available": cap - count}

    return {
        "global_cap": MAX_SCALPER_BOTS_GLOBAL,
        "global_current": len(bots),
        "global_available": MAX_SCALPER_BOTS_GLOBAL - len(bots),
        "per_exchange": per_exchange,
        "thresholds": {
            "ev_min_bps": SCALPER_EV_MIN_BPS,
            "spread_max_bps": SCALPER_SPREAD_MAX_BPS,
            "max_hold_seconds": SCALPER_MAX_HOLD_SECONDS,
            "stagnation_seconds": SCALPER_STAGNATION_SECONDS,
            "orders_per_min": SCALPER_ORDERS_PER_MIN,
            "cancels_per_min": SCALPER_CANCELS_PER_MIN,
            "cooldown_seconds": SCALPER_COOLDOWN_SECONDS,
        },
    }


@router.get("/summary")
async def scalper_summary(user_id: str = Depends(get_current_user)):
    """
    GET /api/scalper/summary

    Returns scalper-specific metrics separate from normal bots.
    """
    bots = await db.bots_collection.find(
        {"user_id": user_id, "deleted": {"$ne": True}, "bot_type": "scalper"}
    ).to_list(length=200)

    normal_bots = await db.bots_collection.count_documents(
        {"user_id": user_id, "deleted": {"$ne": True}, "bot_type": {"$ne": "scalper"}}
    )

    active = [b for b in bots if b.get("status") == "active"]
    paused = [b for b in bots if b.get("status") == "paused"]

    total_realized = sum(float(b.get("total_profit", 0)) for b in bots)
    total_capital = sum(float(b.get("current_capital", 0)) for b in bots)

    # Count profit routing modes
    growth_count = sum(1 for b in bots if b.get("profit_routing") == "SCALPER_GROWTH")
    return_count = len(bots) - growth_count

    return {
        "scalper_bots_total": len(bots),
        "scalper_active": len(active),
        "scalper_paused": len(paused),
        "normal_bots_total": normal_bots,
        "scalper_realized_pnl": round(total_realized, 2),
        "scalper_total_capital": round(total_capital, 2),
        "profit_routing": {
            "SCALPER_GROWTH": growth_count,
            "RETURN_TO_MAIN": return_count,
        },
        "per_exchange": {
            ex: sum(1 for b in bots if b.get("exchange") == ex)
            for ex in SCALPER_BOT_ALLOCATION
        },
    }


@router.post("/routing")
async def set_profit_routing(
    mode: str,
    user_id: str = Depends(get_current_user),
):
    """
    POST /api/scalper/routing?mode=SCALPER_GROWTH|RETURN_TO_MAIN

    Set the default profit routing mode for all scalper bots.
    """
    valid_modes = ["SCALPER_GROWTH", "RETURN_TO_MAIN"]
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")

    result = await db.bots_collection.update_many(
        {"user_id": user_id, "bot_type": "scalper", "deleted": {"$ne": True}},
        {"$set": {"profit_routing": mode}},
    )

    return {
        "mode": mode,
        "bots_updated": result.modified_count,
        "message": f"Profit routing set to {mode} for all scalper bots",
    }


@router.get("/ev-check")
async def scalper_ev_check(
    exchange: str = "binance",
    win_rate: float = 0.55,
    tp_pct: float = 0.005,
    sl_pct: float = 0.003,
    spread_pct: float = 0.001,
    slippage_pct: float = 0.0005,
    user_id: str = Depends(get_current_user),
):
    """
    GET /api/scalper/ev-check

    Compute expected value for a proposed scalper trade.
    Returns EV, cost breakdown, and PASS/FAIL gate result.
    """
    fee = get_fee_rate(exchange, "taker")
    ev = compute_scalper_ev(win_rate, tp_pct, sl_pct, fee, fee, spread_pct, slippage_pct)
    ev_bps = round(ev * 10000, 2)
    cost_rt = fee + fee + spread_pct + slippage_pct
    spread_bps = round(spread_pct * 10000, 2)

    gate_pass = ev_bps >= SCALPER_EV_MIN_BPS and spread_bps <= SCALPER_SPREAD_MAX_BPS

    return {
        "ev_pct": round(ev * 100, 4),
        "ev_bps": ev_bps,
        "cost_rt_pct": round(cost_rt * 100, 4),
        "spread_bps": spread_bps,
        "gate_pass": gate_pass,
        "reasons": (
            []
            if gate_pass
            else (
                (["ev_below_minimum"] if ev_bps < SCALPER_EV_MIN_BPS else [])
                + (["spread_too_wide"] if spread_bps > SCALPER_SPREAD_MAX_BPS else [])
            )
        ),
        "thresholds": {
            "ev_min_bps": SCALPER_EV_MIN_BPS,
            "spread_max_bps": SCALPER_SPREAD_MAX_BPS,
        },
    }


@router.post("/seed")
async def scalper_seed(
    data: Dict = {},
    user_id: str = Depends(get_current_user),
):
    """POST /api/scalper/seed

    Seed scalper bots for testing. Creates a default set of scalper bots
    if none exist. Useful for paper trading verification.
    """
    import uuid

    existing = await db.bots_collection.count_documents(
        {"user_id": user_id, "bot_type": "scalper", "deleted": {"$ne": True}}
    )

    if existing > 0:
        return {"seeded": 0, "message": f"User already has {existing} scalper bot(s)", "existing": existing}

    exchange = data.get("exchange", "binance")
    pair = data.get("pair", "BTC/USDT")

    bot_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": f"Scalper-{exchange[:3].upper()}-SEED",
        "bot_type": "scalper",
        "exchange": exchange,
        "pair": pair,
        "status": "active",
        "risk_mode": "aggressive",
        "initial_capital": float(data.get("capital", 500)),
        "current_capital": float(data.get("capital", 500)),
        "trading_mode": "paper",
        "deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.bots_collection.insert_one(bot_doc)
    bot_doc.pop("_id", None)

    return {"seeded": 1, "bot": bot_doc}
