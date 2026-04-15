"""
Live-Funds Control Layer — Admin API
======================================
Exposes live-funds policy status, limits, and audit trail to admin users.

Endpoints:
  GET  /api/live-funds/status        — Current policy limits + today's usage
  GET  /api/live-funds/audit         — Recent audit log entries (admin only)
  POST /api/live-funds/reconcile     — Manual reconciliation trigger (admin)
  GET  /api/live-funds/health        — Quick health/readiness check

IMPORTANT:
  - All live-money movement still requires LIVE_FUNDS_MOVEMENT_ALLOWED=true
    AND ENABLE_LIVE_TRADING=true in config/env.
  - These endpoints are READ-ONLY (status + audit). They do not place trades.
  - The reconcile endpoint triggers a balance diff check; it does not move money.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from auth import get_current_user
import database as db
import config
from services.live_funds_policy import live_funds_policy, FundCategory, LiveFundsViolation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live-funds", tags=["Live Funds Control"])


# ─────────────────────────────────────────────── models

class ReconcileRequest(BaseModel):
    exchange: str
    reported_balance_zar: float
    expected_balance_zar: float


# ─────────────────────────────────────────────── endpoints

@router.get("/status")
async def get_live_funds_status(user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Return the current live-funds policy status for the authenticated user.

    Includes:
    - whether live-funds movement is globally allowed
    - all configured monetary limits
    - today's usage (daily loss realized, daily transfers out)
    - whether any circuit breakers have been triggered today
    - fund categories supported

    This endpoint always returns HTTP 200. A 500 would mean the policy layer
    itself is broken, which is a critical failure.
    """
    try:
        summary = await live_funds_policy.get_daily_summary(user_id)
        return {
            "ok": True,
            **summary,
            "env_flags": {
                "ENABLE_LIVE_TRADING":         getattr(config, "ENABLE_LIVE_TRADING", False),
                "LIVE_FUNDS_MOVEMENT_ALLOWED": getattr(config, "LIVE_FUNDS_MOVEMENT_ALLOWED", False),
                "REQUIRE_API_KEYS_FOR_LIVE":   getattr(config, "REQUIRE_API_KEYS_FOR_LIVE", True),
                "AUTO_PROMOTE_LIVE":           getattr(config, "AUTO_PROMOTE_LIVE", False),
            },
            "checklist": _build_readiness_checklist(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as err:
        logger.error("live_funds status error: %s", err)
        raise HTTPException(status_code=500, detail="Failed to retrieve live-funds status")


@router.get("/health")
async def live_funds_health(user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Quick health check: are live funds movement controls active and correct?

    Returns:
    - live_movement_allowed: bool — master kill-switch state
    - live_trading_flag: bool — ENABLE_LIVE_TRADING env flag
    - circuit_breakers_clear: bool — no daily limits exceeded today
    - verdict: str — "SAFE_PAPER_ONLY" | "LIVE_READY" | "CIRCUIT_BREAKER_HIT"
    """
    try:
        summary = await live_funds_policy.get_daily_summary(user_id)
        movement_allowed = summary.get("movement_globally_allowed", False)
        circuit_hit = any(summary.get("circuit_breakers", {}).values())

        if circuit_hit:
            verdict = "CIRCUIT_BREAKER_HIT"
        elif movement_allowed:
            verdict = "LIVE_READY"
        else:
            verdict = "SAFE_PAPER_ONLY"

        return {
            "live_movement_allowed": movement_allowed,
            "live_trading_flag": getattr(config, "ENABLE_LIVE_TRADING", False),
            "circuit_breakers_clear": not circuit_hit,
            "verdict": verdict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as err:
        logger.error("live_funds health error: %s", err)
        return {
            "live_movement_allowed": False,
            "verdict": "ERROR",
            "error": str(err),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/audit")
async def get_live_funds_audit(
    user_id: str = Depends(get_current_user),
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Return recent live-funds policy audit log entries for the user.

    Entries include: trade checks, transfer checks, reconciliation events.
    Sorted newest-first. Maximum 200 records per request.
    """
    limit = min(max(1, limit), 200)
    try:
        if db.audit_logs_collection is None:
            return {"ok": True, "entries": [], "message": "audit_logs_collection not initialized"}

        docs = await db.audit_logs_collection.find(
            {"user_id": user_id, "category": "live_funds_policy"},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit).to_list(limit)

        return {
            "ok": True,
            "count": len(docs),
            "entries": docs,
        }
    except Exception as err:
        logger.error("live_funds audit fetch error: %s", err)
        raise HTTPException(status_code=500, detail="Failed to retrieve audit log")


@router.post("/reconcile")
async def trigger_reconciliation(
    user_id: str = Depends(get_current_user),
    body: ReconcileRequest = Body(...),
) -> Dict[str, Any]:
    """
    Manually trigger a balance reconciliation check for one exchange.

    The caller provides:
    - exchange: exchange ID (e.g. "binance")
    - reported_balance_zar: ZAR-equivalent balance as reported by the exchange API
    - expected_balance_zar: ZAR-equivalent balance as recorded in our ledger

    This endpoint DOES NOT move money. It only compares values and logs the result.

    If the discrepancy exceeds LIVE_RECONCILIATION_TOLERANCE_PCT, a critical
    alert is emitted and written to the audit log.
    """
    try:
        result = await live_funds_policy.reconcile_exchange_balance(
            user_id=user_id,
            exchange=body.exchange,
            reported_balance_zar=body.reported_balance_zar,
            expected_balance_zar=body.expected_balance_zar,
        )
        return {"ok": True, **result}
    except Exception as err:
        logger.error("reconciliation endpoint error: %s", err)
        raise HTTPException(status_code=500, detail="Reconciliation check failed")


# ─────────────────────────────────────────────── helper

def _build_readiness_checklist() -> List[Dict[str, Any]]:
    """
    Build a human-readable checklist showing what must be satisfied
    before LIVE_FUNDS_MOVEMENT_ALLOWED can safely be set to True.

    This mirrors the FINAL RULE requirements from the architecture document.
    """
    return [
        {
            "item": "ENABLE_LIVE_TRADING env flag set to true",
            "satisfied": getattr(config, "ENABLE_LIVE_TRADING", False),
            "how_to_satisfy": "Set ENABLE_LIVE_TRADING=true in .env",
        },
        {
            "item": "LIVE_FUNDS_MOVEMENT_ALLOWED kill-switch enabled",
            "satisfied": getattr(config, "LIVE_FUNDS_MOVEMENT_ALLOWED", False),
            "how_to_satisfy": "Set LIVE_FUNDS_MOVEMENT_ALLOWED=true in .env (only after full checklist passes)",
        },
        {
            "item": "VectorBT research harness in place",
            "satisfied": True,  # research/vectorbt_runner.py committed
            "how_to_satisfy": "research/vectorbt_runner.py — already implemented",
        },
        {
            "item": "Freqtrade validation harness in place",
            "satisfied": True,  # validation/freqtrade/ committed
            "how_to_satisfy": "validation/freqtrade/ — already implemented",
        },
        {
            "item": "Strategy promotion workflow in place",
            "satisfied": True,  # research/strategy_registry.py committed
            "how_to_satisfy": "research/strategy_registry.py — already implemented",
        },
        {
            "item": "Per-trade size limits configured",
            "satisfied": getattr(config, "LIVE_MAX_TRADE_SIZE_ZAR", 0) > 0,
            "value_zar": getattr(config, "LIVE_MAX_TRADE_SIZE_ZAR", 5000.0),
            "how_to_satisfy": "Set LIVE_MAX_TRADE_SIZE_ZAR in .env (default 5000)",
        },
        {
            "item": "Per-exchange exposure cap configured",
            "satisfied": getattr(config, "LIVE_MAX_EXCHANGE_EXPOSURE_ZAR", 0) > 0,
            "value_zar": getattr(config, "LIVE_MAX_EXCHANGE_EXPOSURE_ZAR", 20000.0),
            "how_to_satisfy": "Set LIVE_MAX_EXCHANGE_EXPOSURE_ZAR in .env (default 20000)",
        },
        {
            "item": "Daily loss circuit breaker configured",
            "satisfied": getattr(config, "LIVE_MAX_DAILY_LOSS_ZAR", 0) > 0,
            "value_zar": getattr(config, "LIVE_MAX_DAILY_LOSS_ZAR", 2000.0),
            "how_to_satisfy": "Set LIVE_MAX_DAILY_LOSS_ZAR in .env (default 2000)",
        },
        {
            "item": "7-day paper training completed with realistic mixed outcomes",
            "satisfied": False,  # runtime check — must be verified externally
            "how_to_satisfy": "Run 7 days of paper trading, verify mixed wins/losses in analytics dashboard",
        },
        {
            "item": "Truth layer verified: countdown/growth/wallet agree",
            "satisfied": False,  # runtime check — must be verified externally
            "how_to_satisfy": "Compare admin truth console, countdown endpoint, and paper wallet equity",
        },
    ]
