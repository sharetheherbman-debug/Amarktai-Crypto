"""Strategy Admin Routes

Provides:
  GET  /api/strategy/active   — list all available strategy configs from research/strategies/
  GET  /api/strategy/list     — alias for /active (same data, explicit list verb)

The active strategy is determined by reading all JSON files in the research/strategies/
directory.  There is no promoted-single-active concept in the current runtime; all
registered strategy files are returned so the operator can see what is deployed.
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import List, Dict, Any
import logging
import os
import json

from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategy", tags=["Strategy"])

# Path to the strategy JSON files (relative to the backend directory root)
_STRATEGIES_DIR = os.path.join(
    os.path.dirname(__file__),        # backend/routes/
    "..",                             # backend/
    "..",                             # repo root
    "research",
    "strategies",
)


def _load_strategy_files() -> List[Dict[str, Any]]:
    """Load all strategy JSON files from research/strategies/.

    Returns a list of strategy config dicts.  Non-fatal on individual file errors.
    """
    strategies: List[Dict[str, Any]] = []
    try:
        strat_dir = os.path.realpath(_STRATEGIES_DIR)
        if not os.path.isdir(strat_dir):
            logger.warning("Strategy directory not found: %s", strat_dir)
            return strategies
        for fname in sorted(os.listdir(strat_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(strat_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["_filename"] = fname
                strategies.append(data)
            except Exception as _fe:
                logger.warning("Could not read strategy file %s: %s", fname, _fe)
    except Exception as _de:
        logger.error("Could not list strategy directory: %s", _de)
    return strategies


@router.get("/active")
async def get_active_strategies(user_id: str = Depends(get_current_user)):
    """GET /api/strategy/active

    Returns all registered strategy configurations from research/strategies/.
    Each entry includes: name, version, stage, notes, registered_at, config.

    In the current runtime all strategy files are "active" (the bot fleet selects
    strategies via bot_type and playbook at spawn time).  This endpoint makes the
    full strategy catalogue visible to operators and the dashboard.
    """
    try:
        strategies = _load_strategy_files()
        return {
            "strategies": strategies,
            "count": len(strategies),
            "source": "research/strategies",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("get_active_strategies error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_strategies(user_id: str = Depends(get_current_user)):
    """GET /api/strategy/list — alias for /api/strategy/active."""
    return await get_active_strategies(user_id=user_id)
