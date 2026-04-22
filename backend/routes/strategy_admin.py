"""
Strategy Admin API — Operator Controls for Strategy Promotion
=============================================================
Routes
------
GET  /api/strategy/active           — current promoted strategy versions
POST /api/strategy/promote          — promote a strategy version
POST /api/strategy/rollback         — roll back to previous/no active strategy
POST /api/strategy/reload           — force reload of active.json from disk

All state-changing actions write an audit log entry.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
import database as db
from services.strategy_version_loader import strategy_version_loader

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PromoteRequest(BaseModel):
    strategy: str          # e.g. "momentum"
    version: str           # e.g. "v2"
    from_stage: str = "validated"
    notes: Optional[str] = None


class RollbackRequest(BaseModel):
    strategy: Optional[str] = None   # None = rollback all
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _write_audit(action: str, user_id: str, payload: dict) -> None:
    try:
        await db.audit_logs_collection.insert_one({
            "action": action,
            "user_id": user_id,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("strategy_admin audit write failed: %s", exc)


def _registry_promote(strategy: str, version: str, from_stage: str = "validated") -> dict:
    """Delegate to research/strategy_registry.py and return the new config."""
    try:
        import sys, os
        # Make sure research/ is importable
        repo_root = str(__file__)
        # backend/routes/ → backend/ → project_root/
        for _ in range(3):
            repo_root = os.path.dirname(repo_root)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        from research.strategy_registry import registry  # type: ignore
        registry.promote(strategy, version, from_stage, "active")
        # Reload loader so the engine picks up the new active immediately
        strategy_version_loader.reload_active_strategy()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Promotion failed: {exc}") from exc


def _registry_rollback(strategy: Optional[str]) -> dict:
    """Remove a strategy (or all) from research/strategies/active.json."""
    import json, sys, os
    # Locate active.json
    repo_root = str(__file__)
    for _ in range(3):
        repo_root = os.path.dirname(repo_root)
    active_path = os.path.join(repo_root, "research", "strategies", "active.json")

    if not os.path.exists(active_path):
        strategy_version_loader.reload_active_strategy()
        return {"ok": True, "removed": None}

    with open(active_path, encoding="utf-8") as f:
        data = json.load(f)

    if strategy is None:
        removed = list(data.keys())
        data = {}
    else:
        removed = [strategy] if strategy in data else []
        data.pop(strategy, None)

    with open(active_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    strategy_version_loader.reload_active_strategy()
    return {"ok": True, "removed": removed}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/strategy/active")
async def get_active_strategy(user_id: str = Depends(get_current_user)):
    """Return current promoted strategy versions."""
    try:
        info = strategy_version_loader.get_active_version_info()
        return {
            "active": info,
            "version_string": strategy_version_loader.current_version_string(),
            "loaded_at": strategy_version_loader.loaded_at,
        }
    except Exception as exc:
        logger.error("get_active_strategy error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/strategy/promote")
async def promote_strategy(
    body: PromoteRequest, user_id: str = Depends(get_current_user)
):
    """Promote a validated strategy version to active.

    This calls research/strategy_registry.py:promote() and immediately reloads
    the in-memory cache so the live paper engine picks up the new parameters.
    """
    try:
        result = _registry_promote(body.strategy, body.version, body.from_stage)
        await _write_audit(
            "strategy_promote",
            user_id,
            {
                "strategy": body.strategy,
                "version": body.version,
                "from_stage": body.from_stage,
                "notes": body.notes,
            },
        )
        logger.info(
            "Strategy promoted: %s/%s by user %s", body.strategy, body.version, user_id
        )
        return {
            "promoted": True,
            "strategy": body.strategy,
            "version": body.version,
            "active_now": strategy_version_loader.current_version_string(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("promote_strategy error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/strategy/rollback")
async def rollback_strategy(
    body: RollbackRequest, user_id: str = Depends(get_current_user)
):
    """Roll back active strategy (or all strategies) to no active version.

    The paper engine will revert to hardcoded config defaults.
    """
    try:
        result = _registry_rollback(body.strategy)
        await _write_audit(
            "strategy_rollback",
            user_id,
            {"strategy": body.strategy, "reason": body.reason, "removed": result.get("removed")},
        )
        logger.info("Strategy rollback by user %s: %s", user_id, result)
        return {
            "rolled_back": True,
            "removed": result.get("removed"),
            "active_now": strategy_version_loader.current_version_string(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("rollback_strategy error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/strategy/reload")
async def reload_active_strategy(user_id: str = Depends(get_current_user)):
    """Force reload of research/strategies/active.json from disk."""
    try:
        strategy_version_loader.reload_active_strategy()
        return {
            "reloaded": True,
            "active_now": strategy_version_loader.current_version_string(),
            "loaded_at": strategy_version_loader.loaded_at,
        }
    except Exception as exc:
        logger.error("reload_active_strategy error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
