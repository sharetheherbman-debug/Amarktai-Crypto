"""
Run Exchange Selection Endpoint

Manages which exchanges participate in the user's current paper-trading run.

Three-tier resolution (highest priority first):
  1. Explicit user selection stored in system_modes.run_active_exchanges
  2. Exchanges with a valid API key in the api_keys collection
  3. ['luno'] — safe single-exchange fallback

Routes:
  GET  /api/exchanges/run-selection  — view current selection + status
  PUT  /api/exchanges/run-selection  — explicitly set run_active_exchanges

Note: Setting run_active_exchanges does NOT affect which exchanges the
platform *supports*. All 8 exchanges remain in SUPPORTED_PLATFORMS.
This endpoint only controls which exchanges are *active for this run*.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
from typing import Dict, List
import logging

from auth import get_current_user
import database as db
from config import PAPER_SUPPORTED_EXCHANGES
from config.platforms import SUPPORTED_PLATFORMS
from services.canonical import get_user_run_exchanges, get_unlocked_exchanges, get_user_paper_exchanges

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exchanges", tags=["Exchange Run Selection"])


@router.get("/run-selection")
async def get_run_selection(user_id: str = Depends(get_current_user)):
    """
    GET /api/exchanges/run-selection

    Returns the exchanges participating in the user's current paper run.
    Includes resolution tier (explicit / api_keys / fallback) and the
    status of each supported exchange (supported / configured / run_active).
    """
    try:
        run_active = await get_user_run_exchanges(user_id)
        paper_run_exchanges = await get_user_paper_exchanges(user_id)

        # Determine which tier resolved the run_active list
        modes = await db.system_modes_collection.find_one(
            {"user_id": user_id}, {"_id": 0, "run_active_exchanges": 1}
        )
        explicit = modes.get("run_active_exchanges") if modes else None
        has_explicit = bool(isinstance(explicit, list) and any(
            e.lower() in SUPPORTED_PLATFORMS for e in explicit
        ))

        # Get configured exchanges (has API key — any key, tested or not).
        # Accept both "api_key" (legacy routes) and "api_key_encrypted" (canonical route).
        key_docs = await db.api_keys_collection.find(
            {
                "user_id": user_id,
                "$or": [
                    {"api_key": {"$exists": True, "$ne": ""}},
                    {"api_key_encrypted": {"$exists": True, "$ne": None}},
                ],
            },
            {"_id": 0, "provider": 1},
        ).to_list(50)
        configured_exchanges = list(dict.fromkeys(
            d["provider"].lower()
            for d in key_docs
            if d.get("provider") and d["provider"].lower() in SUPPORTED_PLATFORMS
        ))

        # Get UNLOCKED exchanges: key present AND last_test_ok=True
        unlocked_exchanges = await get_unlocked_exchanges(user_id)

        resolution_tier = (
            "explicit" if has_explicit
            else "api_keys" if configured_exchanges
            else "fallback"
        )

        # Build per-exchange status table.
        # Three independent flags per exchange:
        #   supported  — exchange is in SUPPORTED_PLATFORMS (always true here)
        #   configured — user has saved an API key (tested or not)
        #   unlocked   — key is saved AND last connection test passed
        #   run_active — exchange is participating in the current run
        exchange_table = []
        for ex in SUPPORTED_PLATFORMS:
            exchange_table.append({
                "exchange": ex,
                "supported": True,
                "configured": ex in configured_exchanges,
                "unlocked": ex in unlocked_exchanges,
                "run_active": ex in run_active,
            })

        # paper_active_exchanges: exchanges that have at least one active paper bot.
        # Paper bots bypass the API-key gate so this is the real participation truth.
        from config import PAPER_SUPPORTED_EXCHANGES
        _paper_exch: set = set()
        _pb_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "status": "active",
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0, "exchange": 1, "mode": 1, "trading_mode": 1},
        )
        async for _pb in _pb_cursor:
            _mode = ((_pb.get("mode") or _pb.get("trading_mode")) or "paper").lower()
            if _mode.startswith("paper") or _mode in ("", "paper"):
                _ex = (_pb.get("exchange") or "").lower()
                if _ex and _ex in PAPER_SUPPORTED_EXCHANGES:
                    _paper_exch.add(_ex)
        paper_active_exchanges = sorted(_paper_exch)

        # Count excluded bots
        excluded_count = await db.bots_collection.count_documents(
            {"user_id": user_id, "excluded_from_run": True}
        )

        return {
            "user_id": user_id,
            "run_active_exchanges": run_active,
            "paper_run_exchanges": paper_run_exchanges,
            "paper_active_exchanges": paper_active_exchanges,
            "resolution_tier": resolution_tier,
            "explicit_selection": explicit if has_explicit else None,
            "configured_exchanges": configured_exchanges,
            "unlocked_exchanges": unlocked_exchanges,
            "supported_exchanges": list(SUPPORTED_PLATFORMS),
            "exchange_status": exchange_table,
            "excluded_bots_count": excluded_count,
            "note": (
                "paper_run_exchanges: exchanges on which paper bots are ALLOWED to execute. "
                "Resolution: 1) explicit run_active_exchanges; "
                "2) exchanges with funded platform wallets (balance > 0); "
                "3) ['luno'] fallback.  "
                "paper_active_exchanges: exchanges where paper bots are actively executing NOW.  "
                "run_active_exchanges: exchange gate for live bots (requires API key proof).  "
                "configured_exchanges/unlocked_exchanges are advisory for paper mode."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("get_run_selection error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/run-selection")
async def set_run_selection(
    user_id: str = Depends(get_current_user),
    payload: Dict = Body(...),
):
    """
    PUT /api/exchanges/run-selection

    Explicitly set which exchanges participate in the user's current paper run.
    Body: { "exchanges": ["luno", "binance"] }

    To revert to automatic resolution (api_keys or fallback), pass:
    Body: { "exchanges": null }  or  { "exchanges": [] }
    """
    exchanges = payload.get("exchanges")

    if exchanges is None or exchanges == []:
        # Clear explicit selection — revert to automatic tier resolution
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"run_active_exchanges": ""}},
            upsert=False,
        )
        # Re-determine resolution tier after clearing explicit selection
        has_cfg = bool(await db.api_keys_collection.find_one(
            {
                "user_id": user_id,
                "$or": [
                    {"api_key": {"$exists": True, "$ne": ""}},
                    {"api_key_encrypted": {"$exists": True, "$ne": None}},
                ],
            }
        ))
        resolved = await get_user_run_exchanges(user_id)
        tier_after_clear = "api_keys" if has_cfg else "fallback"
        return {
            "success": True,
            "message": "Explicit selection cleared — using automatic resolution",
            "run_active_exchanges": resolved,
            "resolution_tier": tier_after_clear,
        }

    if not isinstance(exchanges, list):
        raise HTTPException(status_code=400, detail="'exchanges' must be a list of exchange IDs")

    # Validate all requested exchanges are supported
    invalid = [e for e in exchanges if str(e).lower() not in SUPPORTED_PLATFORMS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchanges: {invalid}. Supported: {list(SUPPORTED_PLATFORMS)}",
        )

    normalized = [str(e).lower() for e in exchanges]

    await db.system_modes_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "run_active_exchanges": normalized,
            "run_active_exchanges_set_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    logger.info("User %s set run_active_exchanges = %s", user_id, normalized)

    return {
        "success": True,
        "message": f"Run exchanges updated to: {normalized}",
        "run_active_exchanges": normalized,
        "resolution_tier": "explicit",
        "note": (
            "Bots on exchanges not in this list will be marked excluded_from_run=True "
            "and will not be ticked by the scheduler until the selection is changed."
        ),
    }


# ---------------------------------------------------------------------------
# Single-cohort validation mode — Phase B
# ---------------------------------------------------------------------------

@router.get("/paper-cohort")
async def get_paper_cohort(user_id: str = Depends(get_current_user)):
    """
    GET /api/exchanges/paper-cohort

    Returns the active single-cohort validation mode for paper trading.

    When a cohort is set, only paper bots matching the specified exchange
    and/or bot_type are ticked by the scheduler.  All other paper bots are
    skipped (not paused or deleted) until the cohort is cleared.

    Response:
        {
            "active": bool,
            "cohort": {"exchange": str | null, "bot_type": str | null} | null,
            "note": str
        }
    """
    try:
        modes = await db.system_modes_collection.find_one(
            {"user_id": user_id}, {"_id": 0, "paper_validation_cohort": 1}
        )
        cohort = modes.get("paper_validation_cohort") if modes else None
        is_active = bool(
            cohort
            and isinstance(cohort, dict)
            and (cohort.get("exchange") or cohort.get("bot_type"))
        )
        return {
            "active": is_active,
            "cohort": cohort if is_active else None,
            "note": (
                "When active, only paper bots matching exchange+bot_type are ticked. "
                "Set exchange=null to match all exchanges; bot_type=null to match all types. "
                "PUT /api/exchanges/paper-cohort to change; DELETE to clear."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("get_paper_cohort error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/paper-cohort")
async def set_paper_cohort(
    user_id: str = Depends(get_current_user),
    payload: Dict = Body(...),
):
    """
    PUT /api/exchanges/paper-cohort

    Set single-cohort validation mode.  Only paper bots matching the given
    exchange and/or bot_type will be ticked by the scheduler.

    Body (both fields optional — omit or set null to match all):
        {
            "exchange": "luno",      // null → all exchanges
            "bot_type": "normal"     // null → both normal and scalper
        }

    To clear the cohort and return to full-fleet mode:
        PUT with {"exchange": null, "bot_type": null}
    or DELETE /api/exchanges/paper-cohort
    """
    try:
        exchange = payload.get("exchange")
        bot_type = payload.get("bot_type")

        if exchange is not None:
            exchange = str(exchange).lower().strip()
            if exchange not in PAPER_SUPPORTED_EXCHANGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Exchange '{exchange}' not supported for paper trading. Supported: {sorted(PAPER_SUPPORTED_EXCHANGES)}",
                )
        if bot_type is not None:
            bot_type = str(bot_type).lower().strip()
            if bot_type not in ("normal", "scalper"):
                raise HTTPException(
                    status_code=400,
                    detail="bot_type must be 'normal' or 'scalper' (or null to match all)",
                )

        # If both are null, treat as a clear
        if exchange is None and bot_type is None:
            await db.system_modes_collection.update_one(
                {"user_id": user_id},
                {"$unset": {"paper_validation_cohort": ""}},
                upsert=False,
            )
            return {
                "success": True,
                "active": False,
                "cohort": None,
                "message": "Paper validation cohort cleared — all paper bots will be ticked.",
            }

        cohort = {"exchange": exchange, "bot_type": bot_type}
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "paper_validation_cohort": cohort,
                "paper_validation_cohort_set_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        logger.info("User %s set paper_validation_cohort = %s", user_id, cohort)
        return {
            "success": True,
            "active": True,
            "cohort": cohort,
            "message": (
                f"Cohort set: only {'all exchanges' if not exchange else exchange} / "
                f"{'all types' if not bot_type else bot_type} bots will be ticked."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("set_paper_cohort error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/paper-cohort")
async def clear_paper_cohort(user_id: str = Depends(get_current_user)):
    """
    DELETE /api/exchanges/paper-cohort

    Clear the single-cohort validation mode.  All paper bots resume normal
    scheduler participation after this call.
    """
    try:
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"paper_validation_cohort": ""}},
            upsert=False,
        )
        logger.info("User %s cleared paper_validation_cohort", user_id)
        return {
            "success": True,
            "active": False,
            "cohort": None,
            "message": "Paper validation cohort cleared — all paper bots will be ticked.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("clear_paper_cohort error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
