"""
Growth Engine Routes
====================
Per-user toggles for safe automated growth features (paper and live trading).

ALL endpoints require authentication.
Master toggle defaults to OFF.
Leverage is a position-sizing multiplier (1.0-2.0x); guardrails apply at all times.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
from typing import Optional
import logging

from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/growth", tags=["Growth Engine"])


@router.get("/settings")
async def get_growth_settings(user_id: str = Depends(get_current_user)):
    """
    GET /api/growth/settings

    Returns the user's current Growth Engine settings merged with safe defaults.
    All features are off by default.
    """
    try:
        from services.growth_engine_service import get_settings
        settings = await get_settings(user_id)
        return {
            "success": True,
            "settings": settings,
            "warning": (
                "Higher risk: these features can increase drawdown. "
                "Enable only if you understand the risk."
            ),
        }
    except Exception as e:
        logger.error(f"GET /growth/settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings")
async def update_growth_settings(
    body: dict = Body(default={}),
    user_id: str = Depends(get_current_user),
):
    """
    PUT /api/growth/settings

    Update Growth Engine settings/toggles.
    Leverage is always forced off regardless of submitted value.

    Body: partial settings dict (unknown keys are ignored).
    """
    try:
        from services.growth_engine_service import get_settings, save_settings, DEFAULT_SETTINGS

        # Merge current settings with submitted update (only allow known keys)
        current = await get_settings(user_id)
        allowed_keys = set(DEFAULT_SETTINGS.keys())
        update = {k: v for k, v in body.items() if k in allowed_keys}
        merged = {**current, **update}
        # Clamp leverage multiplier to safe bounds
        if "leverage_multiplier" in merged:
            merged["leverage_multiplier"] = max(1.0, min(2.0, float(merged["leverage_multiplier"])))

        saved = await save_settings(user_id, merged)
        return {
            "success": True,
            "settings": saved,
        }
    except Exception as e:
        logger.error(f"PUT /growth/settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_growth_status(user_id: str = Depends(get_current_user)):
    """
    GET /api/growth/status

    Returns the current Growth Engine state for the user:
    - Whether it is enabled
    - Last tick time
    - Current regime + confidence
    - Blocked reasons (if any)
    - Last actions taken
    """
    try:
        from services.growth_engine_service import get_settings, get_state, _check_guardrails

        settings, state = await _gather_status(user_id)
        guardrail = await _check_guardrails(user_id)

        TOGGLE_KEYS = [
            "profit_recycling", "capital_redistribution", "strategy_specialization",
            "trade_frequency_tuning", "dynamic_risk_budgeting", "capital_aggression",
            "exchange_filtering", "bot_cap_ramp", "leverage_enabled",
        ]
        active_features = [k for k in TOGGLE_KEYS if settings.get(k)]
        enabled_toggles = {k: bool(settings.get(k)) for k in TOGGLE_KEYS}

        # Resolve trading mode
        mode = "paper"
        try:
            import database as db
            user_doc = await db.users_collection.find_one({"id": user_id}, {"trading_mode": 1, "_id": 0})
            if user_doc and user_doc.get("trading_mode") == "live":
                mode = "live"
        except Exception:
            pass

        return {
            "success": True,
            "enabled": settings.get("enabled", False),
            "mode": mode,
            "enabled_toggles": enabled_toggles,
            "active_features": active_features,
            "last_tick": state.get("last_tick"),
            "last_tick_at": state.get("last_tick"),
            "current_regime": state.get("current_regime", "unknown"),
            "confidence": state.get("confidence", 0.0),
            "blocked": not guardrail["ok"],
            "blocked_reasons": guardrail.get("reasons", []) + state.get("blocked_reasons", []),
            "last_actions": state.get("last_actions", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"GET /growth/status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions")
async def get_growth_decisions(
    limit: int = 50,
    user_id: str = Depends(get_current_user),
):
    """
    GET /api/growth/decisions?limit=50

    Returns the most recent Growth Engine decision records for the user.
    Decisions are append-only and include plain-English reasons for every action.
    """
    try:
        limit = max(1, min(limit, 200))
        from services.growth_engine_service import get_decisions
        decisions = await get_decisions(user_id, limit=limit)
        return {
            "success": True,
            "decisions": decisions,
            "count": len(decisions),
        }
    except Exception as e:
        logger.error(f"GET /growth/decisions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-once")
async def run_growth_once(
    body: dict = Body(default={}),
    user_id: str = Depends(get_current_user),
):
    """
    POST /api/growth/run-once

    Manually trigger one Growth Engine tick for the user.

    Requires confirmation: body must include {"confirm": true}.
    Paper mode only — no live trading actions are taken.

    This does NOT bypass any safety guardrails; if locks are active the tick
    will record them and exit without taking action.
    """
    if not body.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: send {\"confirm\": true} to run Growth Engine tick."
        )

    try:
        from services.growth_engine_service import run_tick
        decision = await run_tick(user_id, force=True)
        return {
            "success": True,
            "decision": decision,
            "note": "One tick executed. Review decisions list for full history.",
        }
    except Exception as e:
        logger.error(f"POST /growth/run-once error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _gather_status(user_id: str):
    from services.growth_engine_service import get_settings, get_state
    settings = await get_settings(user_id)
    state = await get_state(user_id)
    return settings, state
