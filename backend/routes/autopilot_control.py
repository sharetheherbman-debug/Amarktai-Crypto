"""
Autopilot Persistence Endpoints

Ensure autopilot state persists across page refreshes.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging

from auth import get_current_user
import database as db
from realtime_events import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/autopilot/status")
async def get_autopilot_status(user_id: str = Depends(get_current_user)):
    """
    Get current autopilot status for the user
    
    Returns server-side autopilot state that persists across sessions.
    """
    try:
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "autopilot_enabled": 1, "autopilot_settings": 1}
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "user_id": user_id,
            "autopilot_enabled": user.get("autopilot_enabled", False),
            "autopilot_settings": user.get("autopilot_settings", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting autopilot status for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autopilot/toggle")
async def toggle_autopilot(user_id: str = Depends(get_current_user)):
    """
    Toggle autopilot on/off
    
    Persists state server-side and broadcasts realtime event.
    """
    try:
        # Get current state
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "autopilot_enabled": 1}
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Toggle state
        current_state = user.get("autopilot_enabled", False)
        new_state = not current_state
        
        # Update in database
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "autopilot_enabled": new_state,
                    "autopilot_last_toggle": datetime.now(timezone.utc).isoformat(),
                    "autopilot_toggled_by": "user"
                }
            }
        )
        
        # Create audit log entry
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "autopilot_toggle",
            "details": {
                "previous_state": current_state,
                "new_state": new_state
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "user_action"
        })
        
        # Broadcast realtime event
        await manager.broadcast_json({
            "type": "autopilot_toggled",
            "user_id": user_id,
            "enabled": new_state,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Autopilot toggled for user {user_id}: {current_state} -> {new_state}")
        
        return {
            "success": True,
            "user_id": user_id,
            "autopilot_enabled": new_state,
            "previous_state": current_state,
            "message": f"Autopilot {'enabled' if new_state else 'disabled'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling autopilot for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autopilot/enable")
async def enable_autopilot(user_id: str = Depends(get_current_user)):
    """
    Enable autopilot (idempotent)
    """
    try:
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "autopilot_enabled": 1}
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # If already enabled, return success (idempotent)
        if user.get("autopilot_enabled", False):
            return {
                "success": True,
                "user_id": user_id,
                "autopilot_enabled": True,
                "message": "Autopilot already enabled",
                "idempotent": True
            }
        
        # Enable autopilot
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "autopilot_enabled": True,
                    "autopilot_enabled_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Audit log
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "autopilot_enabled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "user_action"
        })
        
        # Broadcast
        await manager.broadcast_json({
            "type": "autopilot_enabled",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Autopilot enabled for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "autopilot_enabled": True,
            "message": "Autopilot enabled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling autopilot for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autopilot/disable")
async def disable_autopilot(user_id: str = Depends(get_current_user)):
    """
    Disable autopilot (idempotent)
    """
    try:
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "autopilot_enabled": 1}
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # If already disabled, return success (idempotent)
        if not user.get("autopilot_enabled", False):
            return {
                "success": True,
                "user_id": user_id,
                "autopilot_enabled": False,
                "message": "Autopilot already disabled",
                "idempotent": True
            }
        
        # Disable autopilot
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "autopilot_enabled": False,
                    "autopilot_disabled_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Audit log
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "autopilot_disabled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "user_action"
        })
        
        # Broadcast
        await manager.broadcast_json({
            "type": "autopilot_disabled",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Autopilot disabled for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "autopilot_enabled": False,
            "message": "Autopilot disabled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling autopilot for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
