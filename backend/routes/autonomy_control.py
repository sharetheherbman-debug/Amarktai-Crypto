"""
Autonomy Control Endpoints
Expose autonomy subsystem status and pause/resume controls.
"""

from datetime import datetime, timezone
from typing import Optional, Dict
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user
import database as db
from services.autonomy_heartbeat import heartbeat_registry
from services.autonomy_state import autonomy_state
from services.system_mode_service import system_mode_service
from services.learning_loop import learning_loop
from autopilot_engine import autopilot
from trading_scheduler import trading_scheduler
from self_healing import self_healing
from websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/autonomy", tags=["Autonomy"])

CONFIRM_PAUSE = "CONFIRM AUTONOMY PAUSE"
CONFIRM_RESUME = "CONFIRM AUTONOMY RESUME"
CONFIRM_RUN = "CONFIRM AUTONOMY RUN"


class AutonomyControlRequest(BaseModel):
    subsystem: str
    confirmation_phrase: Optional[str] = None


class AutonomyRunRequest(BaseModel):
    confirmation_phrase: Optional[str] = None
    allow_live: bool = False


def _normalize_subsystem(value: str) -> str:
    return (value or "").strip().lower()


def _build_subsystem_payload(
    name: str,
    running: bool,
    last_tick: Optional[str],
    heartbeats: Dict[str, Dict[str, Optional[str]]],
    paused: Dict[str, bool],
    last_error: Optional[str] = None,
) -> Dict:
    heartbeat = heartbeats.get(name, {})
    paused_flag = paused.get(name, False)
    status = "paused" if paused_flag else ("running" if running else "stopped")
    return {
        "status": status,
        "running": running,
        "paused": paused_flag,
        "last_tick": last_tick or heartbeat.get("last_ok_at"),
        "last_ok_at": heartbeat.get("last_ok_at"),
        "last_error_at": heartbeat.get("last_error_at"),
        "last_error_message": last_error or heartbeat.get("last_error_message"),
    }


@router.get("/status")
async def get_autonomy_status(user_id: str = Depends(get_current_user)):
    """Return autonomy subsystem health and heartbeat summary."""
    heartbeats = heartbeat_registry.snapshot()
    paused = autonomy_state.snapshot()

    realtime_running = bool(manager.active_connections)
    autopilot_tick = autopilot.last_tick.get("timestamp") if autopilot.last_tick else None
    trading_tick = trading_scheduler.last_heartbeat.isoformat() if trading_scheduler.last_heartbeat else None
    learning_tick = learning_loop.last_run.isoformat() if learning_loop.last_run else None

    subsystems = {
        "autopilot": _build_subsystem_payload(
            "autopilot",
            autopilot.running,
            autopilot_tick,
            heartbeats,
            paused,
            autopilot.last_error,
        ),
        "trading_scheduler": _build_subsystem_payload(
            "trading_scheduler",
            trading_scheduler.is_running,
            trading_tick,
            heartbeats,
            paused,
        ),
        "realtime": _build_subsystem_payload(
            "realtime",
            realtime_running,
            heartbeats.get("realtime", {}).get("last_ok_at"),
            heartbeats,
            paused,
        ),
        "self_heal": _build_subsystem_payload(
            "self_heal",
            self_healing.is_running,
            heartbeats.get("self_heal", {}).get("last_ok_at"),
            heartbeats,
            paused,
        ),
        "bodyguard": _build_subsystem_payload(
            "bodyguard",
            not paused.get("bodyguard", False),
            heartbeats.get("bodyguard", {}).get("last_ok_at"),
            heartbeats,
            paused,
        ),
        "learning_loop": _build_subsystem_payload(
            "learning_loop",
            learning_loop.is_running,
            learning_tick,
            heartbeats,
            paused,
        ),
    }

    return {
        "success": True,
        "self_healing_detail": {
            "health_state": "running" if self_healing.is_running else "stopped",
            "monitored_systems": getattr(self_healing, "monitored_systems", []),
            "last_action": getattr(self_healing, "last_action", None),
            "last_result": getattr(self_healing, "last_result", None),
            "last_reason_code": getattr(self_healing, "last_reason_code", None),
            "last_check": self_healing.last_check.isoformat() if getattr(self_healing, "last_check", None) else None,
            "last_error": getattr(self_healing, "last_error", None),
        },
        "subsystems": subsystems,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _require_confirmation(expected_phrase: str, provided: Optional[str]):
    if not provided or provided.strip().upper() != expected_phrase:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "requires_confirmation": True,
                "confirmation_phrase": expected_phrase,
                "message": "Confirmation required for autonomy control.",
            },
        )
    return None


@router.post("/pause")
async def pause_autonomy(
    request: AutonomyControlRequest,
    user_id: str = Depends(get_current_user),
):
    confirmation = await _require_confirmation(CONFIRM_PAUSE, request.confirmation_phrase)
    if confirmation:
        return confirmation

    target = _normalize_subsystem(request.subsystem)
    if not target:
        raise HTTPException(status_code=400, detail="Subsystem required")

    targets = ["autopilot", "trading_scheduler", "realtime", "self_heal", "bodyguard", "learning_loop"]
    if target != "all" and target not in targets:
        raise HTTPException(status_code=400, detail="Invalid subsystem")
    if target == "all":
        target_list = targets
    else:
        target_list = [target]

    for subsystem in target_list:
        autonomy_state.set_paused(subsystem, True)
        if subsystem == "autopilot":
            await autopilot.stop()
        elif subsystem == "trading_scheduler":
            trading_scheduler.stop()
        elif subsystem == "self_heal":
            await self_healing.stop()
        elif subsystem == "learning_loop":
            learning_loop.stop()

    logger.info("Autonomy pause requested by %s for %s", user_id[:8], target)
    return {
        "success": True,
        "paused": target_list,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/resume")
async def resume_autonomy(
    request: AutonomyControlRequest,
    user_id: str = Depends(get_current_user),
):
    confirmation = await _require_confirmation(CONFIRM_RESUME, request.confirmation_phrase)
    if confirmation:
        return confirmation

    target = _normalize_subsystem(request.subsystem)
    if not target:
        raise HTTPException(status_code=400, detail="Subsystem required")

    targets = ["autopilot", "trading_scheduler", "realtime", "self_heal", "bodyguard", "learning_loop"]
    if target != "all" and target not in targets:
        raise HTTPException(status_code=400, detail="Invalid subsystem")
    if target == "all":
        target_list = targets
    else:
        target_list = [target]

    for subsystem in target_list:
        autonomy_state.set_paused(subsystem, False)
        if subsystem == "autopilot":
            await autopilot.start()
        elif subsystem == "trading_scheduler":
            trading_scheduler.start()
        elif subsystem == "self_heal":
            await self_healing.start()
        elif subsystem == "learning_loop":
            await learning_loop.start()

    logger.info("Autonomy resume requested by %s for %s", user_id[:8], target)
    return {
        "success": True,
        "resumed": target_list,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/run-now")
async def run_autonomy_now(
    request: AutonomyRunRequest,
    user_id: str = Depends(get_current_user),
):
    confirmation = await _require_confirmation(CONFIRM_RUN, request.confirmation_phrase)
    if confirmation:
        return confirmation

    mode = await system_mode_service.get_current_mode(user_id)
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "is_admin": 1})
    is_admin = bool((user or {}).get("is_admin"))

    if mode != "paper" and not request.allow_live:
        raise HTTPException(
            status_code=403,
            detail="Autonomy run requires allow_live=true when not in paper mode"
        )
    if request.allow_live and not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required for live autonomy run")

    await autopilot.hourly_reinvestment_cycle()
    try:
        await trading_scheduler.execute_bot_trades()
        heartbeat_registry.mark_ok("trading_scheduler")
    except Exception as e:
        heartbeat_registry.mark_error("trading_scheduler", str(e))

    return {
        "success": True,
        "mode": mode,
        "message": "Autonomy cycle triggered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
