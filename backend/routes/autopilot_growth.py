"""
Autopilot Growth + Reinvest Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
import logging

from auth import get_current_user, is_admin
import database as db
from config.platforms import SUPPORTED_PLATFORMS
from services.autopilot_growth import AutopilotGrowthService
from services.autopilot_reinvest import AutopilotReinvestService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autopilot", tags=["Autopilot Growth"])


@router.get("/growth/status")
async def growth_status(user_id: str = Depends(get_current_user)):
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        service = AutopilotGrowthService(db.db, user_id)
        return await service.get_growth_status()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Growth status error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/growth/trigger")
async def growth_trigger(user_id: str = Depends(get_current_user), is_admin_user: bool = Depends(is_admin)):
    if not is_admin_user:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        service = AutopilotGrowthService(db.db, user_id)
        results = {}
        for platform in SUPPORTED_PLATFORMS:
            bot_id = await service.try_trigger_spawn(platform)
            results[platform] = {"spawned": bool(bot_id), "bot_id": bot_id}
        return {
            "success": True,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Growth trigger error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/reinvest/status")
async def reinvest_status(user_id: str = Depends(get_current_user)):
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        service = AutopilotReinvestService(db.db, user_id)
        return await service.get_reinvest_status()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Reinvest status error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reinvest/run")
async def reinvest_run(user_id: str = Depends(get_current_user), is_admin_user: bool = Depends(is_admin)):
    if not is_admin_user:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        service = AutopilotReinvestService(db.db, user_id)
        results = {}
        for platform in SUPPORTED_PLATFORMS:
            result = await service.run_daily_reinvest(platform)
            results[platform] = result or {"success": False}
        return {
            "success": True,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Reinvest run error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
