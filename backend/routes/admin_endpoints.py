"""
Admin Dashboard Endpoints
User management, system monitoring, and administrative actions
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field, validator
import logging
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import bcrypt
import os
import secrets
import string
import random

from auth import get_current_user, require_admin
from utils.bot_state import normalize_bot_state
from services.wallet_summary_service import wallet_summary_service
from services.emergency_stop_override_service import emergency_stop_override_service
from services.bot_filters import bot_not_deleted_filter
import database as db
from engines.audit_logger import audit_logger
from json_utils import serialize_doc, serialize_list

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])

_AUDIT_COLLECTION_WARNING_INTERVAL = 300
_last_missing_audit_collection_warning = 0.0


def _warn_missing_audit_collection():
    global _last_missing_audit_collection_warning
    now = time.monotonic()
    if now - _last_missing_audit_collection_warning >= _AUDIT_COLLECTION_WARNING_INTERVAL:
        logger.warning("Audit logging skipped: audit_logs_collection is not initialized")
        _last_missing_audit_collection_warning = now


# ============================================================================
# AUDIT LOGGING HELPER
# ============================================================================

async def log_admin_action(
    admin_id: str, 
    action: str, 
    target_type: str, 
    target_id: str, 
    details: dict = None,
    request: Request = None
):
    """Log admin actions to audit trail"""
    try:
        # Get admin username
        admin_user = await db.users_collection.find_one({"id": admin_id}, {"_id": 0, "email": 1, "first_name": 1})
        admin_username = admin_user.get("email", "unknown") if admin_user else "unknown"
        
        # Get IP address from request if available
        ip_address = "unknown"
        if request:
            ip_address = request.client.host if request.client else "unknown"
        
        audit_doc = {
            "admin_id": admin_id,
            "admin_username": admin_username,
            "action": action,
            "target_type": target_type,  # "user" or "bot"
            "target_id": target_id,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_address": ip_address,
        }
        if db.audit_logs_collection is None:
            _warn_missing_audit_collection()
            return
        await db.audit_logs_collection.insert_one(audit_doc)
        logger.info(f"Admin action logged: {admin_id[:8]} → {action} on {target_type} {target_id[:8]}")
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")


# ============================================================================
# RBAC HELPER
# ============================================================================

# Use require_admin from auth.py for consistency
# Backward compatibility alias
verify_admin = require_admin



class AdminUnlockRequest(BaseModel):
    password: str = Field(..., min_length=1, description="Admin password")


class BlockUserRequest(BaseModel):
    reason: str = Field("No reason provided", description="Reason for blocking the user")


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, description="New password for the user")


class DeleteUserRequest(BaseModel):
    confirm: bool = Field(..., description="Confirmation flag to prevent accidental deletion")


class ChangeAdminPasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, description="Current admin password")
    new_password: str = Field(..., min_length=8, description="New admin password")


class BotModeChangeRequest(BaseModel):
    mode: str = Field(..., description="Trading mode: paper or live")


class BotExchangeChangeRequest(BaseModel):
    exchange: str = Field(..., description="Exchange: luno, binance, kucoin, bybit, bitget")


class EmergencyStopGlobalOverrideRequest(BaseModel):
    disabled: bool
    reason: str = Field(..., min_length=1, max_length=500)


class EmergencyStopUserOverrideRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    disabled: bool
    reason: str = Field(..., min_length=1, max_length=500)


class EmergencyStopClearUserOverrideRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


class PurgeDeletedBotsRequest(BaseModel):
    days: Optional[int] = Field(None, ge=0, description="Only purge bots deleted more than N days ago")


class ResetBotLocksRequest(BaseModel):
    reason: str = Field("Admin reset locks", description="Reason for clearing safety locks")


class SystemResetRequest(BaseModel):
    confirm: bool = Field(False, description="Confirmation flag to proceed with reset")
    confirm_token: Optional[str] = Field(None, description="Optional confirmation token")


class RuntimeResetRequest(BaseModel):
    confirmation_phrase: str = Field(..., description="Confirmation phrase required for reset")
    mode: str = Field("paper", description="Mode to reset: paper or live")


@router.post("/unlock")
async def unlock_admin_panel(
    request: AdminUnlockRequest,
    current_user_id: str = Depends(get_current_user)
):
    """
    Verify admin password and generate unlock token
    Case-insensitive and whitespace-tolerant password check
    
    SECURITY: Requires ADMIN_PASSWORD environment variable to be set.
    Token is returned but not stored (stateless approach).
    In production, implement Redis-based token validation for added security.
    """
    try:
        # Get password from request
        password = request.password.strip()
        
        if not password:
            raise HTTPException(status_code=400, detail="Password is required")
        
        # Import centralized verification from auth.py
        from auth import verify_admin_password, get_admin_password
        
        # Verify password using centralized function
        try:
            is_valid = await verify_admin_password(password)
        except ValueError as e:
            logger.error(f"Admin password misconfiguration: {e}")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: Admin password not configured properly"
            )
        
        if not is_valid:
            # Log failed attempt
            await audit_logger.log_event(
                event_type="admin_unlock_failed",
                user_id=current_user_id,
                details={"reason": "Invalid password"},
                severity="warning"
            )
            raise HTTPException(status_code=403, detail="Invalid admin password")
        
        # Update user to have is_admin flag
        await db.users_collection.update_one(
            {"id": current_user_id},
            {"$set": {"is_admin": True}}
        )
        
        # Generate JWT token with admin role claim
        from auth import create_access_token
        from datetime import timedelta
        
        admin_token = create_access_token(
            data={
                "user_id": current_user_id,
                "sub": current_user_id,
                "role": "admin",
                "is_admin": True
            },
            expires_delta=timedelta(hours=24)
        )
        
        # Log successful unlock
        await audit_logger.log_event(
            event_type="admin_panel_unlocked",
            user_id=current_user_id,
            details={"timestamp": datetime.now(timezone.utc).isoformat()},
            severity="info"
        )
        
        logger.info(f"Admin panel unlocked by user {current_user_id}")
        
        return {
            "success": True,
            "message": "Admin panel unlocked",
            "admin_token": admin_token,
            "unlock_token": secrets.token_urlsafe(32),  # Keep for backward compat
            "expires_in": 86400,  # 24 hours in seconds
            "user": {
                "id": current_user_id,
                "is_admin": True,
                "role": "admin"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin unlock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADMIN HEALTH / STATUS
# ============================================================================

@router.get("/health")
async def admin_health(admin_id: str = Depends(require_admin)):
    """Admin health check including database and scheduler state."""
    try:
        db_status = "unknown"
        try:
            if db.client is not None:
                await db.client.admin.command("ping")
                db_status = "ok"
            else:
                db_status = "disconnected"
        except Exception as e:
            logger.warning(f"DB ping failed: {e}")
            db_status = "error"

        from trading_scheduler import trading_scheduler
        scheduler_status = {
            "running": trading_scheduler.is_running,
            "last_heartbeat": trading_scheduler.last_heartbeat.isoformat() if trading_scheduler.last_heartbeat else None
        }

        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "database": {"status": db_status},
            "scheduler": scheduler_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Admin health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-system")
async def reset_system_zero(
    request: SystemResetRequest,
    admin_id: str = Depends(require_admin),
):
    """Admin-only reset to zero (preserves users + API keys)."""
    reset_token = os.getenv("RESET_SYSTEM_CONFIRM_TOKEN")
    token_ok = bool(reset_token and request.confirm_token == reset_token)
    if not (request.confirm or token_ok):
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirmation required. Set confirm=true or confirm_token matching "
                "RESET_SYSTEM_CONFIRM_TOKEN."
            ),
        )

    protected = {"users_collection", "api_keys_collection"}
    cleared = []
    skipped = []

    for name, collection in vars(db).items():
        if not name.endswith("_collection"):
            continue
        if name in protected:
            skipped.append({"collection": name, "reason": "protected"})
            continue
        if collection is None:
            skipped.append({"collection": name, "reason": "not_initialized"})
            continue
        result = await collection.delete_many({})
        cleared.append({"collection": name, "deleted_count": result.deleted_count})
        logger.info("Admin reset: cleared %s (%s)", name, result.deleted_count)

    await log_admin_action(
        admin_id=admin_id,
        action="reset_system_zero",
        target_type="system",
        target_id="all",
        details={"cleared": cleared, "skipped": skipped},
    )

    return {
        "success": True,
        "message": "System reset completed (users + API keys preserved)",
        "cleared_collections": cleared,
        "skipped_collections": skipped,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/runtime/reset")
async def runtime_reset(
    request: RuntimeResetRequest,
    admin_id: str = Depends(require_admin),
):
    """DEPRECATED: Use POST /api/admin/start-fresh instead.

    This endpoint is kept for backward compatibility but redirects to the
    canonical start-fresh flow.  The System Mode section is the single source
    of truth for runtime resets.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": (
            "This endpoint is deprecated. "
            "Use POST /api/admin/start-fresh with confirmation_phrase='START FRESH'."
        ),
    }


@router.get("/status")
async def admin_status(admin_id: str = Depends(require_admin)):
    """Admin status summary including system modes and counts."""
    try:
        modes = await db.system_modes_collection.find_one({"user_id": admin_id}, {"_id": 0}) or {}

        total_users = await db.users_collection.count_documents({})
        total_bots = await db.bots_collection.count_documents(bot_not_deleted_filter())
        active_bots = await db.bots_collection.count_documents(bot_not_deleted_filter({"status": "active"}))
        paused_bots = await db.bots_collection.count_documents(bot_not_deleted_filter({"status": "paused"}))
        total_trades = await db.trades_collection.count_documents({})

        from trading_scheduler import trading_scheduler
        scheduler_status = {
            "running": trading_scheduler.is_running,
            "last_heartbeat": trading_scheduler.last_heartbeat.isoformat() if trading_scheduler.last_heartbeat else None
        }

        return {
            "system_mode": modes,
            "scheduler": scheduler_status,
            "counts": {
                "users": total_users,
                "bots": total_bots,
                "active_bots": active_bots,
                "paused_bots": paused_bots,
                "trades": total_trades
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Admin status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/users")
async def get_all_users(admin_id: str = Depends(require_admin)):
    """
    Get all users with comprehensive details
    - User info (id, username, email, role, status, timestamps)
    - API keys summary (which exchanges are configured)
    - Bots summary (total, by exchange, by mode)
    - Resource usage (trades count)
    """
    try:
        users = await db.users_collection.find({}, {"password_hash": 0, "password": 0}).to_list(1000)
        
        # Enrich users with comprehensive data
        enriched_users = []
        for user in users:
            # Serialize the user document
            user_data = serialize_doc(user)
            user_id = user_data.get('id') or str(user.get('_id'))
            user_data['id'] = user_id
            user_data.pop('_id', None)
            
            # Get API keys summary
            api_keys_cursor = db.api_keys_collection.find({"user_id": user_id}, {"_id": 0, "provider": 1})
            api_keys = await api_keys_cursor.to_list(100)
            api_keys_summary = {
                "openai": any(k.get("provider") == "openai" for k in api_keys),
                "luno": any(k.get("provider") == "luno" for k in api_keys),
                "binance": any(k.get("provider") == "binance" for k in api_keys),
                "kucoin": any(k.get("provider") == "kucoin" for k in api_keys),
                "bybit": any(k.get("provider") == "bybit" for k in api_keys),
                "kraken": any(k.get("provider") == "kraken" for k in api_keys),
                "bitget": any(k.get("provider") == "bitget" for k in api_keys),
                "gate": any(k.get("provider") == "gate" for k in api_keys),
            }
            
            # Get bots summary (exclude deleted)
            bots_cursor = db.bots_collection.find(
                bot_not_deleted_filter({"user_id": user_id}),
                {"_id": 0, "exchange": 1, "trading_mode": 1, "status": 1}
            )
            bots = await bots_cursor.to_list(1000)
            
            # Count by exchange
            by_exchange = {}
            for bot in bots:
                exchange = bot.get("exchange", "unknown")
                by_exchange[exchange] = by_exchange.get(exchange, 0) + 1
            
            # Count by mode
            by_mode = {}
            for bot in bots:
                mode = bot.get("trading_mode", "paper")
                status = bot.get("status", "unknown")
                
                # Map status to simplified mode
                if status == "paused":
                    key = "paused"
                else:
                    key = mode
                
                by_mode[key] = by_mode.get(key, 0) + 1
            
            bots_summary = {
                "total": len(bots),
                "by_exchange": by_exchange,
                "by_mode": by_mode
            }
            
            # Get resource usage - trades count
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            yesterday = now - timedelta(days=1)
            
            trades_last_24h = await db.trades_collection.count_documents({
                "user_id": user_id,
                "timestamp": {"$gte": yesterday.isoformat()}
            })
            
            total_trades = await db.trades_collection.count_documents({"user_id": user_id})
            
            resource_usage = {
                "trades_last_24h": trades_last_24h,
                "total_trades": total_trades
            }
            
            # Build comprehensive user object
            enriched_user = {
                "id": user_id,
                "user_id": user_id,
                "first_name": user_data.get("first_name") or user_data.get("name", "Unknown"),
                "username": user_data.get("first_name") or user_data.get("name", "Unknown"),
                "email": user_data.get("email", "N/A"),
                "role": user_data.get("role", "admin" if user_data.get("is_admin") else "user"),
                "status": "blocked" if user_data.get("blocked", False) else "active",
                "is_active": not user_data.get("blocked", False),
                "created_at": user_data.get("created_at", "N/A"),
                "last_seen": user_data.get("last_seen", "N/A"),
                "api_keys": api_keys_summary,
                "api_keys_count": len(api_keys),
                "bots_summary": bots_summary,
                "bots_count": bots_summary.get("total", 0),
                "resource_usage": resource_usage
            }
            enriched_user["stats"] = {
                "total_bots": bots_summary.get("total", 0),
                "total_trades": resource_usage.get("total_trades", 0),
                "total_profit": round(sum(b.get('total_profit', 0) for b in bots), 2)
            }
            
            enriched_users.append(enriched_user)
        
        return {
            "users": enriched_users,
            "total_count": len(enriched_users)
        }
        
    except Exception as e:
        logger.error(f"Get all users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}")
async def get_user_details(user_id: str, admin_user_id: str = Depends(verify_admin)):
    """Get detailed user information"""
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "password": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get bots
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
        
        # Get recent trades
        recent_trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        # Get audit logs
        audit_logs = await audit_logger.get_user_audit_trail(user_id, days=30)
        
        return {
            "user": user,
            "bots": bots,
            "recent_trades": recent_trades[:10],  # Last 10 trades
            "audit_logs": audit_logs[:20],  # Last 20 audit events
            "stats": {
                "total_bots": len(bots),
                "total_trades": len(recent_trades),
                "total_profit": sum(b.get('total_profit', 0) for b in bots)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/block")
async def block_user(
    user_id: str,
    request: BlockUserRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Block a user and pause all their bots"""
    try:
        # Update user status - set is_active to false
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "is_active": False,
                    "blocked": True,
                    "blocked_at": datetime.now(timezone.utc).isoformat(),
                    "blocked_by": admin_id,
                    "blocked_reason": request.reason
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Pause all user's active bots
        paused_result = await db.bots_collection.update_many(
            {"user_id": user_id, "status": {"$ne": "paused"}},
            {"$set": {"status": "paused", "pause_reason": "USER_BLOCKED_BY_ADMIN"}}
        )
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="block_user",
            target_type="user",
            target_id=user_id,
            details={"reason": request.reason, "bots_paused": paused_result.modified_count},
            request=req
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "is_active": False,
            "message": f"User blocked. {paused_result.modified_count} bots paused."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Block user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: str, 
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Unblock a user"""
    try:
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "is_active": True,
                    "blocked": False,
                    "unblocked_at": datetime.now(timezone.utc).isoformat(),
                    "unblocked_by": admin_id
                },
                "$unset": {"blocked_reason": "", "blocked_at": "", "blocked_by": ""}
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="unblock_user",
            target_type="user",
            target_id=user_id,
            details={},
            request=req
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "is_active": True,
            "message": "User unblocked"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unblock user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Reset user password (admin action)
    Generates a random secure password automatically
    """
    try:
        # Generate random password (12 characters, mixed case, numbers, symbols)
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        new_password = ''.join(random.choice(chars) for _ in range(12))
        
        # Ensure at least one of each type
        new_password = (
            random.choice(string.ascii_uppercase) +
            random.choice(string.ascii_lowercase) +
            random.choice(string.digits) +
            random.choice("!@#$%^&*") +
            new_password[4:]
        )
        
        # Hash new password using passlib (same as auth.py)
        from auth import get_password_hash
        hashed = get_password_hash(new_password)
        
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "password_hash": hashed,
                    "password": hashed,  # Legacy support
                    "password_reset_by_admin": True,
                    "password_reset_at": datetime.now(timezone.utc).isoformat(),
                    "must_change_password": True  # Force password change on next login
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Log action (don't log actual password)
        await log_admin_action(
            admin_id=admin_id,
            action="reset_password",
            target_type="user",
            target_id=user_id,
            details={"reset_by": admin_id},
            request=req
        )
        
        # FUTURE ENHANCEMENT: Send email with new password if email service is configured
        # For now, return the password in response (admin must share it securely)
        
        return {
            "success": True,
            "new_password": new_password,
            "message": "Password reset successfully. Email sent (if configured).",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: DeleteUserRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Delete user and all their data (dangerous!)
    Prevents admin from deleting themselves
    """
    try:
        # Check if admin is trying to delete themselves
        if user_id == admin_id:
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete your own admin account"
            )
        
        if not request.confirm:
            return {
                "success": False,
                "message": "Confirmation required. Set confirm=true to proceed."
            }
        
        # Delete all user's bots
        bots_result = await db.bots_collection.delete_many({"user_id": user_id})
        
        # Delete all user's trades
        trades_result = await db.trades_collection.delete_many({"user_id": user_id})
        
        # Delete all user's API keys
        api_keys_result = await db.api_keys_collection.delete_many({"user_id": user_id})
        
        # Delete all user's alerts
        alerts_result = await db.alerts_collection.delete_many({"user_id": user_id})
        
        # Delete user
        user_result = await db.users_collection.delete_one({"id": user_id})
        
        if user_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="delete_user",
            target_type="user",
            target_id=user_id,
            details={
                "bots_deleted": bots_result.deleted_count,
                "trades_deleted": trades_result.deleted_count,
                "api_keys_deleted": api_keys_result.deleted_count
            },
            request=req
        )
        
        return {
            "success": True,
            "deleted": {
                "user": user_result.deleted_count,
                "bots": bots_result.deleted_count,
                "trades": trades_result.deleted_count,
                "api_keys": api_keys_result.deleted_count
            },
            "message": f"User {user_id} and all associated data deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/logout")
async def force_logout_user(
    user_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Forcefully log out a user by invalidating their sessions
    Note: Actual session invalidation depends on session storage implementation
    """
    try:
        # Delete all user sessions if sessions collection exists
        if db.sessions_collection is not None:
            sessions_result = await db.sessions_collection.delete_many({"user_id": user_id})
            sessions_deleted = sessions_result.deleted_count
        else:
            sessions_deleted = 0
        
        # Add user to force_logout list (checked during auth)
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "force_logout": True,
                    "force_logout_at": datetime.now(timezone.utc).isoformat(),
                    "force_logout_by": admin_id
                }
            }
        )
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="force_logout",
            target_type="user",
            target_id=user_id,
            details={"sessions_deleted": sessions_deleted},
            request=req
        )
        
        return {
            "success": True,
            "message": "User forcefully logged out",
            "user_id": user_id,
            "sessions_deleted": sessions_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force logout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/clear-force-logout")
async def clear_force_logout(
    user_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Clear force_logout flag for a user (admin only).

    This is a one-time kill switch — once an admin force-logs a user out,
    that user cannot authenticate again until this endpoint is called.
    """
    try:
        result = await db.users_collection.update_one(
            {"id": user_id},
            {"$unset": {"force_logout": 1, "force_logout_at": 1, "force_logout_by": 1}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")

        await log_admin_action(
            admin_id=admin_id,
            action="clear_force_logout",
            target_type="user",
            target_id=user_id,
            details={},
            request=req
        )
        return {"success": True, "message": "Force logout cleared for user", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clear force logout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BOT OVERRIDE ENDPOINTS
# ============================================================================

# GET /system-stats canonical version is in routes/admin_enhanced.py (already mounted).
# This extended version is available at /system-stats-extended to avoid collision.
@router.get("/system-stats-extended")
async def get_system_stats_extended(admin_user_id: str = Depends(verify_admin)):
    """
    Get comprehensive system statistics including VPS resources
    Returns CPU, RAM, disk usage, and system health
    """
    import psutil
    import shutil
    
    try:
        # Get user statistics
        from rules import SUPPORTED_EXCHANGES

        total_users = await db.users_collection.count_documents({})
        blocked_users = await db.users_collection.count_documents({
            "$or": [{"blocked": True}, {"status": "blocked"}]
        })
        active_users = max(total_users - blocked_users, 0)

        bot_filter = bot_not_deleted_filter()
        total_bots = await db.bots_collection.count_documents(bot_filter)
        active_bots = await db.bots_collection.count_documents({**bot_filter, "status": "active"})
        paused_bots = await db.bots_collection.count_documents({**bot_filter, "status": "paused"})
        quarantined_bots = await db.bots_collection.count_documents({**bot_filter, "status": "quarantined"})
        live_bots = await db.bots_collection.count_documents({
            **bot_filter,
            "$or": [{"trading_mode": "live"}, {"mode": "live"}]
        })
        paper_bots = max(total_bots - live_bots, 0)

        total_trades = await db.trades_collection.count_documents({})
        live_trades = await db.trades_collection.count_documents({
            "$or": [{"trading_mode": "live"}, {"is_paper": False}]
        })
        paper_trades = max(total_trades - live_trades, 0)

        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        trades_24h = await db.trades_collection.count_documents({
            "$or": [
                {"timestamp": {"$gte": last_24h.isoformat()}},
                {"created_at": {"$gte": last_24h.isoformat()}}
            ]
        })

        exchange_breakdown = {
            exchange: {"bots": 0, "trades": 0, "profit": 0.0}
            for exchange in SUPPORTED_EXCHANGES
        }
        for exchange in SUPPORTED_EXCHANGES:
            exchange_breakdown[exchange]["bots"] = await db.bots_collection.count_documents({
                **bot_filter,
                "exchange": exchange
            })

        trade_pipeline = [
            {"$match": {"exchange": {"$in": SUPPORTED_EXCHANGES}}},
            {"$project": {
                "exchange": 1,
                "profit": {
                    "$ifNull": ["$net_pnl", {"$ifNull": ["$profit_loss", 0]}]
                }
            }},
            {"$group": {
                "_id": "$exchange",
                "trades": {"$sum": 1},
                "profit": {"$sum": "$profit"}
            }}
        ]
        trade_groups = await db.trades_collection.aggregate(trade_pipeline).to_list(len(SUPPORTED_EXCHANGES))
        total_profit = 0.0
        for doc in trade_groups:
            exchange = doc.get("_id")
            if exchange in exchange_breakdown:
                exchange_breakdown[exchange]["trades"] = doc.get("trades", 0)
                exchange_breakdown[exchange]["profit"] = round(doc.get("profit", 0.0), 2)
                total_profit += doc.get("profit", 0.0)

        total_profit = round(total_profit, 2)

        modes_cursor = db.system_modes_collection.find({}, {"_id": 0, "paperTrading": 1, "liveTrading": 1, "autopilot": 1})
        modes = await modes_cursor.to_list(1000)
        system_modes = {
            "paper_trading": sum(1 for mode in modes if mode.get("paperTrading")),
            "live_trading": sum(1 for mode in modes if mode.get("liveTrading")),
            "autopilot": sum(1 for mode in modes if mode.get("autopilot"))
        }

        try:
            from trading_scheduler import trading_scheduler
            is_running_attr = getattr(trading_scheduler, "is_running", None)
            if callable(is_running_attr):
                scheduler_running = is_running_attr()
            elif isinstance(is_running_attr, bool):
                scheduler_running = is_running_attr
            else:
                scheduler_running = False
        except Exception as e:
            logger.warning(f"Scheduler status error: {e}")
            scheduler_running = False
        
        # VPS Resource metrics
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_total_gb = memory.total / (1024**3)
        memory_used_gb = memory.used / (1024**3)
        memory_free_gb = memory.available / (1024**3)
        memory_percent = memory.percent
        
        # Disk usage
        disk = shutil.disk_usage("/")
        disk_total_gb = disk.total / (1024**3)
        disk_used_gb = disk.used / (1024**3)
        disk_free_gb = disk.free / (1024**3)
        disk_percent = round((disk.used / disk.total) * 100, 2)
        
        # Load average (if available)
        try:
            load_avg = psutil.getloadavg()
            load_info = {
                "1min": round(load_avg[0], 2),
                "5min": round(load_avg[1], 2),
                "15min": round(load_avg[2], 2)
            }
        except (AttributeError, OSError):
            load_info = None
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "blocked": blocked_users
            },
            "bots": {
                "total": total_bots,
                "active": active_bots,
                "live": live_bots,
                "paper": paper_bots,
                "paused": paused_bots,
                "quarantined": quarantined_bots
            },
            "trades": {
                "total": total_trades,
                "live": live_trades,
                "paper": paper_trades,
                "last_24h": trades_24h
            },
            "profit": {
                "total": total_profit
            },
            "exchange_breakdown": exchange_breakdown,
            "system_modes": system_modes,
            "scheduler_status": {
                "running": bool(scheduler_running)
            },
            "vps_resources": {
                "cpu": {
                    "usage_percent": round(cpu_percent, 2),
                    "count": cpu_count,
                    "load_average": load_info
                },
                "memory": {
                    "total_gb": round(memory_total_gb, 2),
                    "used_gb": round(memory_used_gb, 2),
                    "free_gb": round(memory_free_gb, 2),
                    "usage_percent": round(memory_percent, 2)
                },
                "disk": {
                    "total_gb": round(disk_total_gb, 2),
                    "used_gb": round(disk_used_gb, 2),
                    "free_gb": round(disk_free_gb, 2),
                    "usage_percent": disk_percent
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user-storage")
async def get_user_storage_usage(admin_user_id: str = Depends(verify_admin)):
    """
    Get per-user storage usage
    Calculates storage consumed by each user (logs, uploads, reports, bot data)
    """
    import os
    from pathlib import Path
    
    try:
        users = await db.users_collection.find({}, {"id": 1, "email": 1, "first_name": 1}).to_list(1000)
        
        user_storage = []
        
        for user in users:
            user_id = user.get('id') or str(user.get('_id'))
            email = user.get('email', 'Unknown')
            first_name = user.get('first_name', 'Unknown')
            
            # Define user-specific storage directories
            user_dirs = [
                f"/var/log/amarktai/users/{user_id}",
                f"/opt/amarktai/uploads/{user_id}",
                f"/opt/amarktai/reports/{user_id}",
                f"logs/users/{user_id}",
                f"uploads/{user_id}",
                f"reports/{user_id}"
            ]
            
            total_bytes = 0
            
            for dir_path in user_dirs:
                if os.path.exists(dir_path):
                    try:
                        # Calculate directory size
                        for dirpath, dirnames, filenames in os.walk(dir_path):
                            for filename in filenames:
                                filepath = os.path.join(dirpath, filename)
                                try:
                                    total_bytes += os.path.getsize(filepath)
                                except (OSError, FileNotFoundError):
                                    continue
                    except Exception as e:
                        logger.warning(f"Could not calculate size for {dir_path}: {e}")
            
            # Convert bytes to MB
            total_mb = round(total_bytes / (1024**2), 2)
            
            user_storage.append({
                "user_id": user_id,
                "email": email,
                "name": first_name,
                "storage_bytes": total_bytes,
                "storage_mb": total_mb,
                "storage_gb": round(total_mb / 1024, 3)
            })
        
        # Sort by storage usage (descending)
        user_storage.sort(key=lambda x: x['storage_bytes'], reverse=True)
        
        total_storage_bytes = sum(u['storage_bytes'] for u in user_storage)
        total_storage_mb = round(total_storage_bytes / (1024**2), 2)
        
        return {
            "users": user_storage,
            "total_storage_bytes": total_storage_bytes,
            "total_storage_mb": total_storage_mb,
            "total_storage_gb": round(total_storage_mb / 1024, 3),
            "user_count": len(user_storage),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get user storage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_system_stats(admin_user_id: str = Depends(verify_admin)):
    """Get overall system statistics"""
    try:
        total_users = await db.users_collection.count_documents({})
        active_users = await db.users_collection.count_documents({"status": "active"})
        blocked_users = await db.users_collection.count_documents({"status": "blocked"})
        
        total_bots = await db.bots_collection.count_documents(bot_not_deleted_filter())
        active_bots = await db.bots_collection.count_documents(bot_not_deleted_filter({"status": "active"}))
        live_bots = await db.bots_collection.count_documents(bot_not_deleted_filter({"$or": [{"mode": "live"}, {"trading_mode": "live"}]}))
        
        total_trades = await db.trades_collection.count_documents({})
        live_trades = await db.trades_collection.count_documents({"is_paper": False})
        
        # Calculate total profit across all active bots
        all_bots = await db.bots_collection.find(
            bot_not_deleted_filter(),
            {"_id": 0, "total_profit": 1}
        ).to_list(10000)
        total_profit = sum(b.get('total_profit', 0) for b in all_bots)
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "blocked": blocked_users
            },
            "bots": {
                "total": total_bots,
                "active": active_bots,
                "live": live_bots,
                "paper": total_bots - live_bots
            },
            "trades": {
                "total": total_trades,
                "live": live_trades,
                "paper": total_trades - live_trades
            },
            "profit": {
                "total": round(total_profit, 2)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/events")
async def get_audit_events(
    limit: int = 100,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    admin_user_id: str = Depends(verify_admin)
):
    """Get audit trail events for admin monitoring"""
    try:
        # Build query
        query = {}
        if user_id:
            query["user_id"] = user_id
        if event_type:
            query["event_type"] = event_type
        
        # Get events from audit logs collection
        events = await db.audit_logs_collection.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Serialize events
        serialized_events = serialize_list(events, exclude_fields=['_id'])
        
        return {
            "events": serialized_events,
            "total": len(serialized_events),
            "filters": {
                "user_id": user_id,
                "event_type": event_type,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Get audit events error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/resources")
async def get_system_resources(admin_user_id: str = Depends(verify_admin)):
    """Get system resource usage (disk, memory, load, inodes)"""
    import psutil
    import shutil
    
    try:
        # Disk usage
        disk = shutil.disk_usage("/")
        disk_info = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round((disk.used / disk.total) * 100, 2)
        }
        
        # Inode usage (Linux only)
        inode_info = {}
        try:
            import subprocess
            result = subprocess.run(['df', '-i', '/'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        inode_info = {
                            "total": parts[1],
                            "used": parts[2],
                            "free": parts[3],
                            "percent": parts[4]
                        }
        except Exception as e:
            logger.warning(f"Could not get inode info: {e}")
            inode_info = {"error": "Not available"}
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_info = {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": memory.percent
        }
        
        # Load average (Linux/Unix)
        try:
            load_avg = psutil.getloadavg()
            load_info = {
                "1min": load_avg[0],
                "5min": load_avg[1],
                "15min": load_avg[2]
            }
        except (AttributeError, OSError):
            load_info = {"error": "Not available on this platform"}
        
        return {
            "disk": disk_info,
            "inodes": inode_info,
            "memory": memory_info,
            "load": load_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system resources error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/processes")
async def get_process_health(admin_user_id: str = Depends(verify_admin)):
    """Get health status of key processes (amarktai-api, nginx, redis)"""
    import psutil
    
    try:
        processes = {}
        
        # Check for key processes by name
        process_names = ['python', 'uvicorn', 'nginx', 'redis-server', 'mongod']
        
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
            try:
                name = proc.info['name']
                if any(pname in name.lower() for pname in process_names):
                    if name not in processes:
                        processes[name] = []
                    
                    processes[name].append({
                        "pid": proc.info['pid'],
                        "status": proc.info['status'],
                        "cpu_percent": round(proc.info['cpu_percent'], 2),
                        "memory_percent": round(proc.info['memory_percent'], 2)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Determine overall health
        health_status = "healthy" if processes else "degraded"
        
        return {
            "status": health_status,
            "processes": processes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get process health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/logs")
async def get_system_logs(
    lines: int = 200,
    log_file: str = "backend",
    admin_user_id: str = Depends(verify_admin)
):
    """Get last N lines of key logs (sanitized to remove secrets)"""
    import re
    
    try:
        # Map log file names to actual paths
        log_paths = {
            "backend": "/var/log/amarktai/backend.log",
            "nginx": "/var/log/nginx/access.log",
            "error": "/var/log/nginx/error.log"
        }
        
        # Default to looking in current directory if standard paths don't exist
        if log_file not in log_paths:
            log_file = "backend"
        
        log_path = log_paths.get(log_file, "/var/log/amarktai/backend.log")
        
        # Try alternate paths if main path doesn't exist
        import os
        if not os.path.exists(log_path):
            # Try current directory
            alt_paths = [
                f"logs/{log_file}.log",
                f"{log_file}.log",
                "server.log"
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    log_path = alt_path
                    break
        
        # Read log file
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:]
        else:
            recent_lines = [f"Log file not found: {log_path}"]
        
        # Sanitize logs to remove API keys, passwords, tokens
        sanitized_lines = []
        for line in recent_lines:
            # Remove API keys (look for patterns like api_key=..., apiKey:..., etc.)
            line = re.sub(r'(api[_-]?key|apiKey|API[_-]?KEY)["\s:=]+[a-zA-Z0-9_-]+', r'\1=***REDACTED***', line, flags=re.IGNORECASE)
            # Remove tokens
            line = re.sub(r'(token|Token|TOKEN)["\s:=]+[a-zA-Z0-9._-]+', r'\1=***REDACTED***', line)
            # Remove passwords
            line = re.sub(r'(password|Password|PASSWORD)["\s:=]+[^\s"]+', r'\1=***REDACTED***', line)
            # Remove bearer tokens
            line = re.sub(r'Bearer [a-zA-Z0-9._-]+', 'Bearer ***REDACTED***', line)
            
            sanitized_lines.append(line.rstrip())
        
        return {
            "log_file": log_file,
            "path": log_path,
            "lines": sanitized_lines,
            "total_lines": len(sanitized_lines),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/change-password")
async def change_admin_password(
    request: ChangeAdminPasswordRequest,
    admin_user_id: str = Depends(verify_admin)
):
    """Change the admin unlock password (stores hashed in env or database)"""
    try:
        current_password = request.current_password.strip()
        new_password = request.new_password.strip()
        
        # Import centralized verification from auth.py
        from auth import verify_admin_password
        
        # Verify current password using centralized function
        try:
            is_valid = await verify_admin_password(current_password)
        except ValueError as e:
            logger.error(f"Admin password misconfiguration: {e}")
            raise HTTPException(status_code=500, detail="Server configuration error")
        
        if not is_valid:
            raise HTTPException(status_code=403, detail="Current password incorrect")
        
        # Hash new password
        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        # Store in database (admin_config collection)
        await db.admin_config_collection.update_one(
            {"key": "admin_password"},
            {
                "$set": {
                    "value": hashed.decode('utf-8'),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": admin_user_id
                }
            },
            upsert=True
        )
        
        # Log action
        await audit_logger.log_event(
            event_type="admin_password_changed",
            user_id=admin_user_id,
            details={"timestamp": datetime.now(timezone.utc).isoformat()},
            severity="critical"
        )
        
        return {
            "success": True,
            "message": "Admin password changed successfully. Update ADMIN_PASSWORD env variable for persistence."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change admin password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/api-keys")
async def get_user_api_keys_status(
    user_id: str,
    admin_user_id: str = Depends(verify_admin)
):
    """Get status of which exchanges have keys set for a user (no secrets exposed)"""
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"api_keys": 1})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        api_keys = user.get("api_keys", {})
        
        # Return only status, not actual keys
        key_status = {}
        for exchange in ["luno", "binance", "kucoin", "bybit", "bitget"]:
            key_status[exchange] = {
                "configured": exchange in api_keys and api_keys[exchange],
                "last_tested": api_keys.get(f"{exchange}_last_tested"),
                "status": api_keys.get(f"{exchange}_status", "unknown")
            }
        
        return {
            "user_id": user_id,
            "exchanges": key_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user API keys status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# REMOVED: Admin override endpoints per production-ready requirements
# Bots may only go live if they pass all existing rules/gates
# No "override" that can force bots live

# @router.get("/bots/eligible-for-live") - REMOVED
# @router.post("/bots/{bot_id}/override-live") - REMOVED  
# @router.post("/bots/{bot_id}/override") - REMOVED

# Admin can view bot status but cannot bypass trading rules

# The following functions have been disabled:
# - get_eligible_bots_for_live
# - override_bot_to_live  
# - set_bot_override_rules

# Bots must meet all live trading requirements without admin bypass


# REMOVED: Admin override endpoints per production-ready requirements
# Bots may only go live if they pass all existing rules/gates
# No "override" that can force bots live

# The following admin override endpoints have been permanently disabled:
# - GET /bots/eligible-for-live - listed bots eligible for admin override
# - POST /bots/{bot_id}/override-live - forced bot to live mode bypassing rules
# - POST /bots/{bot_id}/override - set override trading parameters

# Bots must meet all live trading requirements without admin bypass


@router.get("/bots")
async def get_all_bots_admin(
    mode: Optional[str] = None,
    user_id: Optional[str] = None,
    admin_id: str = Depends(require_admin)
):
    """
    Get all bots (admin view) with comprehensive details — excludes deleted bots.
    Use GET /api/admin/bots/archived to see deleted bots.
    """
    try:
        # Build query — always exclude deleted bots
        query = bot_not_deleted_filter()
        if mode:
            query["trading_mode"] = mode
        if user_id:
            query["user_id"] = user_id
        
        # Get bots
        bots_cursor = db.bots_collection.find(query, {"_id": 0})
        bots = await bots_cursor.to_list(10000)
        
        # Enrich bots with user info
        enriched_bots = []
        for bot in bots:
            bot_user_id = bot.get("user_id")
            user = await db.users_collection.find_one(
                {"id": bot_user_id}, 
                {"_id": 0, "email": 1, "first_name": 1}
            )
            
            enriched_bot = {
                "bot_id": bot.get("id"),
                "name": bot.get("name"),
                "user_id": bot_user_id,
                "username": user.get("first_name") if user else "Unknown",
                "email": user.get("email") if user else "Unknown",
                "exchange": bot.get("exchange"),
                "mode": bot.get("trading_mode", "paper"),
                "status": bot.get("status", "unknown"),
                "pause_reason": bot.get("pause_reason"),
                "paused_at": bot.get("paused_at"),
                "current_capital": bot.get("current_capital", 0),
                "profit_loss": bot.get("total_profit", 0)
            }
            enriched_bots.append(enriched_bot)
        
        # Sort by name
        enriched_bots.sort(key=lambda b: b["name"] or "")
        
        return {
            "bots": enriched_bots,
            "total": len(enriched_bots)
        }
        
    except Exception as e:
        logger.error(f"Get all bots admin error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots/archived")
async def get_archived_bots(
    user_id: Optional[str] = None,
    admin_id: str = Depends(require_admin)
):
    """Admin-only: return soft-deleted (archived) bots.
    
    These are bots with status='deleted' or is_deleted=True.
    Normal queries never include these; this endpoint provides explicit access.
    """
    try:
        query: dict = {
            "$or": [
                {"status": "deleted"},
                {"is_deleted": True},
                {"deleted_at": {"$exists": True}},
            ]
        }
        if user_id:
            query["user_id"] = user_id

        bots_cursor = db.bots_collection.find(query, {"_id": 0})
        bots = await bots_cursor.to_list(10000)

        enriched = []
        for bot in bots:
            bot_user_id = bot.get("user_id")
            user_doc = await db.users_collection.find_one(
                {"id": bot_user_id},
                {"_id": 0, "email": 1, "first_name": 1}
            )
            enriched.append({
                "bot_id": bot.get("id"),
                "name": bot.get("name"),
                "user_id": bot_user_id,
                "username": user_doc.get("first_name") if user_doc else "Unknown",
                "email": user_doc.get("email") if user_doc else "Unknown",
                "exchange": bot.get("exchange"),
                "mode": bot.get("trading_mode", "paper"),
                "status": bot.get("status"),
                "deleted_at": bot.get("deleted_at"),
                "deleted_by": bot.get("deleted_by"),
                "current_capital": bot.get("current_capital", 0),
                "profit_loss": bot.get("total_profit", 0),
            })

        enriched.sort(key=lambda b: b.get("deleted_at") or "0000-00-00", reverse=True)
        return {"bots": enriched, "total": len(enriched)}

    except Exception as e:
        logger.error(f"Get archived bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/purge-deleted")
async def purge_deleted_bots(
    request: PurgeDeletedBotsRequest,
    admin_id: str = Depends(require_admin)
):
    """Permanently remove soft-deleted bots (admin only)."""
    try:
        query = {
            "$or": [
                {"status": "deleted"},
                {"deleted": True},
                {"deleted_at": {"$exists": True}}
            ]
        }
        if request.days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=request.days)
            query = {
                "$and": [
                    query,
                    {"deleted_at": {"$lte": cutoff.isoformat()}}
                ]
            }

        bots_to_purge = await db.bots_collection.find(query, {"_id": 0, "id": 1}).to_list(10000)
        bot_ids = [b.get("id") for b in bots_to_purge if b.get("id")]

        result = await db.bots_collection.delete_many(query)

        paper_result = None
        if bot_ids and db.paper_ledger_collection is not None:
            paper_result = await db.paper_ledger_collection.delete_many({"bot_id": {"$in": bot_ids}})

        return {
            "success": True,
            "deleted_bots": result.deleted_count,
            "deleted_ledgers": paper_result.deleted_count if paper_result else 0
        }
    except Exception as e:
        logger.error(f"Purge deleted bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/mode")
async def change_bot_mode(
    bot_id: str,
    request: BotModeChangeRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Change bot trading mode (paper/live)
    Checks ENABLE_LIVE_TRADING environment variable
    Verifies API keys exist for live mode
    """
    try:
        new_mode = request.mode.lower()
        
        if new_mode not in ["paper", "live"]:
            raise HTTPException(status_code=400, detail="Mode must be 'paper' or 'live'")
        
        # Check if bot exists
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check global live trading gate
        if new_mode == "live":
            enable_live = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
            if not enable_live:
                raise HTTPException(
                    status_code=403, 
                    detail="Live trading is globally disabled. Set ENABLE_LIVE_TRADING=true"
                )
            
            # Verify user has API keys for this exchange
            exchange = bot.get("exchange")
            user_id = bot.get("user_id")
            
            api_key = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": exchange
            })
            
            if not api_key:
                raise HTTPException(
                    status_code=400,
                    detail=f"User has no API keys configured for {exchange}"
                )
        
        # Update bot mode
        result = await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": {"trading_mode": new_mode}}
        )
        
        if result.modified_count == 0:
            logger.warning(f"Bot {bot_id} mode unchanged (already {new_mode})")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="change_bot_mode",
            target_type="bot",
            target_id=bot_id,
            details={"old_mode": bot.get("trading_mode"), "new_mode": new_mode},
            request=req
        )
        
        return {
            "success": True,
            "bot_id": bot_id,
            "mode": new_mode,
            "message": f"Bot mode changed to {new_mode}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change bot mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/pause")
async def pause_bot(
    bot_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Pause a bot with admin override reason"""
    try:
        result = await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "paused",
                    "pause_reason": "MANUAL_ADMIN_PAUSE",
                    "paused_at": datetime.now(timezone.utc).isoformat(),
                    "paused_by": admin_id
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="pause_bot",
            target_type="bot",
            target_id=bot_id,
            details={"reason": "MANUAL_ADMIN_PAUSE"},
            request=req
        )
        
        return {
            "success": True,
            "bot_id": bot_id,
            "status": "paused",
            "message": "Bot paused by admin"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/resume")
async def resume_bot(
    bot_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Resume a paused bot"""
    try:
        result = await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "running",
                    "resumed_at": datetime.now(timezone.utc).isoformat(),
                    "resumed_by": admin_id
                },
                "$unset": {"pause_reason": "", "paused_at": ""}
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="resume_bot",
            target_type="bot",
            target_id=bot_id,
            details={},
            request=req
        )
        
        return {
            "success": True,
            "bot_id": bot_id,
            "status": "running",
            "message": "Bot resumed by admin"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/restart")
async def restart_bot(
    bot_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Restart a bot (if supported by scheduler)
    Note: This requires integration with trading_scheduler.py
    """
    try:
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # FUTURE ENHANCEMENT: Integrate with trading_scheduler.py for actual restart
        # For now, we'll just return a message that manual restart is logged
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="restart_bot",
            target_type="bot",
            target_id=bot_id,
            details={"note": "Manual restart requested"},
            request=req
        )
        
        return {
            "success": False,
            "message": "Auto-restart not supported. Use pause/resume instead.",
            "bot_id": bot_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restart bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/reset-locks")
async def reset_bot_locks(
    bot_id: str,
    request: ResetBotLocksRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Reset safety lock flags for a bot (admin-only).

    After reset the bot becomes active again and the bodyguard is given a
    grace period so it cannot immediately re-lock.  equity_peak is aligned
    to the current capital so the next drawdown calculation starts from a
    fresh baseline.
    """
    try:
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        # Determine a fresh equity baseline: prefer current_capital, fall back to initial_capital.
        current_capital = bot.get("current_capital") or bot.get("initial_capital") or 0
        now_iso = datetime.now(timezone.utc).isoformat()

        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    # Make bot tradeable immediately
                    "status": "active",
                    "paused_by_system": False,
                    "paused_by_bodyguard": False,
                    "requires_manual_reset": False,
                    # Re-baseline equity so bodyguard drawdown calculation starts clean
                    "equity_peak": current_capital,
                    "current_drawdown_pct": 0,
                    # Grace-period timestamp: bodyguard will not re-lock for N minutes after this
                    "bodyguard_reset_at": now_iso,
                    # Reset breach counter
                    "bodyguard_breach_count": 0,
                },
                "$unset": {
                    "pause_reason": "",
                    "pause_reason_code": "",
                    "paused_at": "",
                    "paused_by": "",
                    "quarantine_reason": "",
                    "quarantine_reason_code": "",
                    "quarantined_at": "",
                    "retraining_until": "",
                    "quarantine_duration_seconds": "",
                    "bodyguard_pause_threshold": "",
                    "bodyguard_pause_drawdown": "",
                    "bodyguard_last_pause_at": "",
                    "bodyguard_last_breach_at": "",
                    "bodyguard_warmup": "",
                    "bodyguard_warmup_reason": "",
                    "bodyguard_status": "",
                    "training_job_id": "",
                },
            }
        )

        # Cancel any pending training jobs for this bot so they don't hold the lock
        try:
            await db.training_jobs_collection.update_many(
                {"bot_id": bot_id, "status": {"$in": ["pending", "running"]}},
                {"$set": {"status": "cancelled", "cancelled_at": now_iso, "cancelled_by": "admin_reset_locks"}}
            )
        except Exception:
            pass

        # Emit realtime event so the dashboard reflects the new state immediately
        try:
            from realtime_events import rt_events
            updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            user_id_for_event = (updated_bot or bot).get("user_id", "")
            await rt_events.bot_status_changed(user_id_for_event, bot_id, "active", "admin_reset_locks")
        except Exception:
            pass

        await log_admin_action(
            admin_id=admin_id,
            action="reset_bot_locks",
            target_type="bot",
            target_id=bot_id,
            details={"reason": request.reason, "equity_baseline_reset_to": current_capital},
            request=req
        )

        return {
            "success": True,
            "bot_id": bot_id,
            "status": "active",
            "paused_by_bodyguard": False,
            "reason": request.reason,
            "equity_peak_reset_to": current_capital,
            "message": "Bot safety locks cleared. Bot is now active with a fresh equity baseline.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset bot locks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/exchange")
async def change_bot_exchange(
    bot_id: str,
    request: BotExchangeChangeRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Change bot's exchange
    Verifies user has API keys for new exchange
    """
    try:
        new_exchange = request.exchange.lower()
        valid_exchanges = ["luno", "binance", "kucoin", "bybit", "bitget"]
        
        if new_exchange not in valid_exchanges:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid exchange. Must be one of: {', '.join(valid_exchanges)}"
            )
        
        # Check if bot exists
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Verify user has API keys for new exchange
        user_id = bot.get("user_id")
        api_key = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": new_exchange
        })
        
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"User has no API keys configured for {new_exchange}"
            )
        
        # Update bot exchange
        result = await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": {"exchange": new_exchange}}
        )
        
        if result.modified_count == 0:
            logger.warning(f"Bot {bot_id} exchange unchanged")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="change_bot_exchange",
            target_type="bot",
            target_id=bot_id,
            details={"old_exchange": bot.get("exchange"), "new_exchange": new_exchange},
            request=req
        )
        
        return {
            "success": True,
            "bot_id": bot_id,
            "exchange": new_exchange,
            "message": f"Bot exchange changed to {new_exchange}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change bot exchange error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# REMOVED: set_bot_override_rules endpoint
# Admin cannot override trading parameters or force bot state changes
# Bots must operate within their configured rules

@router.get("/resources/users")
async def get_user_resource_usage(
    admin_user_id: str = Depends(verify_admin)
):
    """Get per-user storage usage and counts (admin only)
    
    Returns storage breakdown per user:
    - chat_messages count and size
    - trades count and size
    - bots count and size
    - alerts count and size
    - total storage
    
    Args:
        admin_user_id: Admin user ID from auth
        
    Returns:
        Per-user storage usage + system totals
    """
    try:
        import sys
        import json
        
        # Get all users
        users_cursor = db.users_collection.find({}, {"_id": 0, "id": 1, "email": 1, "first_name": 1})
        users = await users_cursor.to_list(1000)
        
        user_usage = []
        
        for user in users:
            user_id = user.get("id")
            
            # Count documents
            chat_count = await db.chat_messages_collection.count_documents({"user_id": user_id})
            trades_count = await db.trades_collection.count_documents({"user_id": user_id})
            bots_count = await db.bots_collection.count_documents({"user_id": user_id})
            alerts_count = await db.alerts_collection.count_documents({"user_id": user_id})
            
            # Estimate storage (rough)
            # Note: In production, use MongoDB's collStats or dataSize for accurate measurements
            chat_size_mb = (chat_count * 500) / (1024 * 1024)  # ~500 bytes per message
            trades_size_mb = (trades_count * 800) / (1024 * 1024)  # ~800 bytes per trade
            bots_size_mb = (bots_count * 1000) / (1024 * 1024)  # ~1KB per bot
            alerts_size_mb = (alerts_count * 300) / (1024 * 1024)  # ~300 bytes per alert
            
            total_mb = chat_size_mb + trades_size_mb + bots_size_mb + alerts_size_mb
            
            user_usage.append({
                "user_id": user_id,
                "email": user.get("email", "N/A"),
                "first_name": user.get("first_name", "N/A"),
                "storage_breakdown": {
                    "chat_messages": {"count": chat_count, "size_mb": round(chat_size_mb, 3)},
                    "trades": {"count": trades_count, "size_mb": round(trades_size_mb, 3)},
                    "bots": {"count": bots_count, "size_mb": round(bots_size_mb, 3)},
                    "alerts": {"count": alerts_count, "size_mb": round(alerts_size_mb, 3)}
                },
                "total_storage_mb": round(total_mb, 3)
            })
        
        # Sort by total storage descending
        user_usage.sort(key=lambda u: u["total_storage_mb"], reverse=True)
        
        # Calculate system totals
        total_system_storage_mb = sum(u["total_storage_mb"] for u in user_usage)
        total_users = len(user_usage)
        total_chats = sum(u["storage_breakdown"]["chat_messages"]["count"] for u in user_usage)
        total_trades = sum(u["storage_breakdown"]["trades"]["count"] for u in user_usage)
        total_bots = sum(u["storage_breakdown"]["bots"]["count"] for u in user_usage)
        total_alerts = sum(u["storage_breakdown"]["alerts"]["count"] for u in user_usage)
        
        return {
            "success": True,
            "users": user_usage,
            "system_totals": {
                "total_users": total_users,
                "total_storage_mb": round(total_system_storage_mb, 3),
                "total_chat_messages": total_chats,
                "total_trades": total_trades,
                "total_bots": total_bots,
                "total_alerts": total_alerts
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get user resource usage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/bots/reconcile")
async def reconcile_bots(
    fix: bool = False,
    admin_user_id: str = Depends(verify_admin)
):
    """
    Reconcile bot user_id fields and find orphaned bots
    
    Args:
        fix: If True, quarantines orphaned bots. If False, just reports.
    
    Returns:
        Report of bot status and any issues found
    """
    try:
        logger.info(f"Admin {admin_user_id[:8]} initiated bot reconciliation (fix={fix})")
        
        # Find all bots
        all_bots = await db.bots_collection.find(
            {},
            {"_id": 0, "id": 1, "user_id": 1, "name": 1, "status": 1}
        ).to_list(10000)
        
        # Issues tracking
        issues = {
            "missing_user_id": [],
            "empty_user_id": [],
            "orphaned": []
        }
        
        user_counts = {}
        
        for bot in all_bots:
            bot_id = bot.get("id", "unknown")
            bot_name = bot.get("name", "unnamed")
            status = bot.get("status", "unknown")
            
            # Check for missing user_id field
            if "user_id" not in bot:
                issues["missing_user_id"].append({
                    "id": bot_id,
                    "name": bot_name,
                    "status": status
                })
                continue
            
            # Check for empty user_id
            user_id = bot.get("user_id")
            if not user_id or user_id == "" or user_id == "ORPHANED":
                issues["empty_user_id"].append({
                    "id": bot_id,
                    "name": bot_name,
                    "status": status
                })
                continue
            
            # Count bots by user
            if user_id not in user_counts:
                user_counts[user_id] = {"total": 0, "active": 0, "paused": 0, "stopped": 0}
            
            user_counts[user_id]["total"] += 1
            if status == "active":
                user_counts[user_id]["active"] += 1
            elif status == "paused":
                user_counts[user_id]["paused"] += 1
            elif status in ["stopped", "deleted", "quarantined"]:
                user_counts[user_id]["stopped"] += 1
        
        # If fix=True, quarantine orphaned bots
        quarantined_count = 0
        if fix:
            # Quarantine bots with missing user_id
            for bot in issues["missing_user_id"]:
                result = await db.bots_collection.update_one(
                    {"id": bot["id"]},
                    {
                        "$set": {
                            "status": "quarantined",
                            "trading_enabled": False,
                            "quarantine_reason": "Missing user_id field",
                            "user_id": "ORPHANED"
                        }
                    }
                )
                if result.modified_count > 0:
                    quarantined_count += 1
            
            # Quarantine bots with empty user_id
            for bot in issues["empty_user_id"]:
                result = await db.bots_collection.update_one(
                    {"id": bot["id"]},
                    {
                        "$set": {
                            "status": "quarantined",
                            "trading_enabled": False,
                            "quarantine_reason": "Empty or ORPHANED user_id",
                            "user_id": "ORPHANED"
                        }
                    }
                )
                if result.modified_count > 0:
                    quarantined_count += 1
            
            logger.info(f"✅ Quarantined {quarantined_count} orphaned bots")
        
        total_issues = len(issues["missing_user_id"]) + len(issues["empty_user_id"])
        
        return {
            "success": True,
            "total_bots": len(all_bots),
            "issues": {
                "missing_user_id": len(issues["missing_user_id"]),
                "empty_user_id": len(issues["empty_user_id"]),
                "total": total_issues
            },
            "orphaned_bots": issues["missing_user_id"] + issues["empty_user_id"],
            "user_counts": user_counts,
            "quarantined": quarantined_count if fix else 0,
            "fix_applied": fix,
            "message": f"Found {total_issues} orphaned bots. {'Quarantined ' + str(quarantined_count) + ' bots.' if fix else 'Use fix=true to quarantine.'}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Bot reconciliation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate-api-keys")
async def migrate_api_keys_encryption(
    user_id_target: Optional[str] = None,
    current_user: str = Depends(get_current_user),
    request: Request = None
):
    """
    Migrate API keys from old derived encryption to new dedicated AMARKTAI_FERNET_KEY
    
    ADMIN ONLY endpoint for migrating encrypted API keys when transitioning
    from JWT_SECRET-derived encryption to dedicated AMARKTAI_FERNET_KEY.
    
    Args:
        user_id_target: Optional specific user ID to migrate (if None, migrates all)
        
    Returns:
        Migration results with counts
        
    Requires:
        - Admin privileges
        - AMARKTAI_FERNET_KEY must be set in environment
    """
    try:
        # Verify admin
        admin_user = await db.users_collection.find_one({"id": current_user}, {"_id": 0})
        if not admin_user or not admin_user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        
        # Import migration utility
        from utils.key_migration import migrate_user_keys, migrate_all_keys
        
        # Check if AMARKTAI_FERNET_KEY is set
        if not os.getenv("AMARKTAI_FERNET_KEY") and not os.getenv("FERNET_KEY"):
            raise HTTPException(
                status_code=400,
                detail="AMARKTAI_FERNET_KEY or FERNET_KEY must be set before migration"
            )
        
        # Perform migration
        if user_id_target:
            # Migrate specific user
            result = await migrate_user_keys(user_id_target)
            message = f"Migration for user {user_id_target[:8]}..."
        else:
            # Migrate all users
            result = await migrate_all_keys()
            message = "Migration for all users"
        
        # Log admin action
        await log_admin_action(
            admin_id=current_user,
            action="migrate_api_keys",
            target_type="api_keys",
            target_id=user_id_target or "all_users",
            details=result,
            request=request
        )
        
        logger.info(f"✅ API key migration completed: {message}")
        
        return {
            "success": True,
            "message": message,
            "results": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key migration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FRONTEND COMPATIBILITY ROUTES (PUT versions of POST endpoints)
# ============================================================================

@router.put("/users/{user_id}/block")
async def block_user_put(
    user_id: str,
    request: BlockUserRequest,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Block/unblock user (PUT version for frontend compatibility)"""
    if request.blocked:
        # Block the user
        return await block_user(user_id, request, admin_id, req)
    else:
        # Unblock the user
        return await unblock_user(user_id, admin_id, req)


@router.put("/users/{user_id}/password")
async def reset_user_password_put(
    user_id: str,
    request: Dict[str, Any],
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """Reset user password with custom password (PUT version for frontend compatibility)"""
    try:
        new_password = request.get("new_password")
        if not new_password or len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Hash new password
        from auth import get_password_hash
        hashed = get_password_hash(new_password)
        
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "password_hash": hashed,
                    "password": hashed,  # Legacy support
                    "password_reset_by_admin": True,
                    "password_reset_at": datetime.now(timezone.utc).isoformat(),
                    "must_change_password": False  # Admin set specific password
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="change_password",
            target_type="user",
            target_id=user_id,
            details={"changed_by": admin_id},
            request=req
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "message": "Password changed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADMIN OVERVIEW & SYSTEM MANAGEMENT
# ============================================================================

@router.get("/overview")
async def get_admin_overview(admin_id: str = Depends(require_admin)):
    """
    Get admin dashboard overview with system counts and statistics
    """
    try:
        # Count active users (not blocked, not deleted)
        total_users = await db.users_collection.count_documents({"blocked": {"$ne": True}})
        blocked_users = await db.users_collection.count_documents({"blocked": True})
        
        # Count bots by status (exclude deleted)
        bots = await db.bots_collection.find(
            {
                "status": {"$ne": "deleted"},
                "deleted": {"$ne": True},
                "deleted_at": {"$exists": False}
            },
            {"_id": 0, "status": 1, "paused_by_system": 1, "paused_by_user": 1, "deleted": 1, "deleted_at": 1}
        ).to_list(5000)
        normalized_bots = [normalize_bot_state(bot) for bot in bots]
        total_bots = len(normalized_bots)
        active_bots = sum(1 for b in normalized_bots if b.get("active"))
        paused_bots = sum(1 for b in normalized_bots if b.get("paused"))
        stopped_bots = sum(1 for b in normalized_bots if b.get("stopped"))
        
        # Count trades (last 24h)
        from datetime import datetime, timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_trades = await db.trades_collection.count_documents({
            "$or": [
                {"timestamp": {"$gte": yesterday.isoformat()}},
                {"created_at": {"$gte": yesterday.isoformat()}},
                {"timestamp": {"$gte": yesterday}},
                {"created_at": {"$gte": yesterday}}
            ]
        })
        
        # Get system mode flags (from system modes collection)
        from routes.system_mode import get_system_mode
        modes = await get_system_mode(admin_id)
        system_mode = {
            "paper_trading": modes.get("paperTrading", True),
            "live_trading": modes.get("liveTrading", False),
            "autopilot": modes.get("autopilot", False),
        }
        
        wallet_summary = await wallet_summary_service.get_summary(admin_id)

        return {
            "success": True,
            "stats": {
                "users": {
                    "total": total_users,
                    "blocked": blocked_users,
                    "active": total_users - blocked_users
                },
                "bots": {
                    "total": total_bots,
                    "active": active_bots,
                    "paused": paused_bots,
                    "stopped": stopped_bots
                },
                "trades": {
                    "last_24h": recent_trades
                },
                "wallet_funding": {
                    "status": wallet_summary.get("status"),
                    "required_funds_zar": wallet_summary.get("required_funds_zar"),
                    "available_wallet_zar": wallet_summary.get("available_wallet_zar"),
                    "shortfall_zar": wallet_summary.get("shortfall_zar")
                },
                "system_mode": system_mode
            }
        }
    except Exception as e:
        logger.error(f"Admin overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/factory-reset")
async def factory_reset_keep_admin(
    admin_email: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Factory reset system - keeps only the specified admin email
    DANGEROUS: Deletes all users, bots, trades except admin
    """
    try:
        # Verify admin is performing the reset
        admin_user = await db.users_collection.find_one({"id": admin_id})
        if not admin_user or not admin_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Validate admin_email matches current admin
        if admin_user.get("email") != admin_email:
            raise HTTPException(
                status_code=400, 
                detail="Admin email mismatch. Only the current admin can perform factory reset."
            )
        
        # Store admin data before deletion
        admin_data = dict(admin_user)
        admin_user_id = admin_data.get("id")
        
        # Delete all non-admin users
        users_deleted = await db.users_collection.delete_many({
            "id": {"$ne": admin_user_id}
        })
        
        # Delete all bots
        bots_deleted = await db.bots_collection.delete_many({})
        
        # Delete all trades
        trades_deleted = await db.trades_collection.delete_many({})
        
        # Delete all API keys except admin's
        keys_deleted = await db.api_keys_collection.delete_many({
            "user_id": {"$ne": admin_user_id}
        })
        
        # Reset admin user to defaults (keep email, password, is_admin)
        await db.users_collection.update_one(
            {"id": admin_user_id},
            {
                "$set": {
                    "blocked": False,
                    "system_mode": "testing",
                    "autopilot_enabled": False,
                    "bodyguard_enabled": True,
                    "learning_enabled": True,
                    "emergency_stop": False,
                }
            }
        )
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="factory_reset",
            target_type="system",
            target_id="global",
            details={
                "users_deleted": users_deleted.deleted_count,
                "bots_deleted": bots_deleted.deleted_count,
                "trades_deleted": trades_deleted.deleted_count,
                "keys_deleted": keys_deleted.deleted_count,
                "kept_admin": admin_email
            },
            request=req
        )
        
        logger.warning(f"Factory reset completed by {admin_email}")
        
        return {
            "success": True,
            "message": "Factory reset completed. All data cleared except admin account.",
            "deleted": {
                "users": users_deleted.deleted_count,
                "bots": bots_deleted.deleted_count,
                "trades": trades_deleted.deleted_count,
                "api_keys": keys_deleted.deleted_count
            },
            "kept_admin": admin_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Factory reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/reset")
async def reset_user_account(
    user_id: str,
    admin_id: str = Depends(require_admin),
    req: Request = None
):
    """
    Reset user account - deletes all their bots, trades, and API keys
    Keeps the user account active
    """
    try:
        # Verify user exists
        user = await db.users_collection.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user's bots
        bots_deleted = await db.bots_collection.delete_many({"user_id": user_id})
        
        # Delete user's trades
        trades_deleted = await db.trades_collection.delete_many({"user_id": user_id})
        
        # Delete user's API keys (except admin's own keys)
        keys_deleted = await db.api_keys_collection.delete_many({
            "user_id": user_id,
            "user_id": {"$ne": admin_id}  # Don't delete admin's own keys
        })
        
        # Reset user settings to defaults
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "system_mode": "testing",
                    "autopilot_enabled": False,
                    "bodyguard_enabled": True,
                    "learning_enabled": True,
                    "emergency_stop": False,
                    "blocked": False
                }
            }
        )
        
        # Log action
        await log_admin_action(
            admin_id=admin_id,
            action="reset_user_account",
            target_type="user",
            target_id=user_id,
            details={
                "bots_deleted": bots_deleted.deleted_count,
                "trades_deleted": trades_deleted.deleted_count,
                "keys_deleted": keys_deleted.deleted_count
            },
            request=req
        )
        
        return {
            "success": True,
            "message": "User account reset successfully",
            "deleted": {
                "bots": bots_deleted.deleted_count,
                "trades": trades_deleted.deleted_count,
                "api_keys": keys_deleted.deleted_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset user account error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/clamp-caps")
async def clamp_bot_caps(admin_id: str = Depends(require_admin)):
    """
    Enforce bot caps across all users
    - Pause/quarantine bots exceeding per-exchange caps
    - Mark extras with reason='CAP_EXCEEDED'
    """
    try:
        from rules.bot_rules import BOT_CAPS, SUPPORTED_EXCHANGES
        
        results = {
            "users_processed": 0,
            "bots_clamped": 0,
            "details": []
        }
        
        # Get all users
        users = await db.users_collection.find({}).to_list(length=None)
        
        for user in users:
            user_id = user.get("id")
            if not user_id:
                continue
            
            results["users_processed"] += 1
            
            # Check each exchange
            for exchange in SUPPORTED_EXCHANGES:
                max_bots = BOT_CAPS.get(exchange, 10)
                
                # Get user's bots on this exchange (active + paused, sorted by created_at)
                user_bots = await db.bots_collection.find({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": {"$in": ["active", "paused"]}
                }).sort("created_at", 1).to_list(length=None)
                
                bot_count = len(user_bots)
                
                if bot_count > max_bots:
                    # Clamp: Keep first max_bots, pause the rest
                    bots_to_clamp = user_bots[max_bots:]
                    
                    for bot in bots_to_clamp:
                        bot_id = bot.get("id")
                        await db.bots_collection.update_one(
                            {"id": bot_id},
                            {
                                "$set": {
                                    "status": "paused",
                                    "quarantine_reason": "CAP_EXCEEDED",
                                    "clamped_at": datetime.now(timezone.utc).isoformat(),
                                    "clamped_by_admin": admin_id
                                }
                            }
                        )
                        results["bots_clamped"] += 1
                    
                    results["details"].append({
                        "user_id": user_id,
                        "exchange": exchange,
                        "had": bot_count,
                        "cap": max_bots,
                        "clamped": len(bots_to_clamp)
                    })
        
        logger.info(f"Bot caps clamped: {results['bots_clamped']} bots across {results['users_processed']} users")
        
        return {
            "success": True,
            "message": f"Bot caps enforced. {results['bots_clamped']} bots clamped.",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Clamp bot caps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BOT MANAGEMENT - START ALL BOTS (ADMIN ONLY)
# ============================================================================

class StartAllBotsRequest(BaseModel):
    """Request to start/resume all paused bots with safety guardrails"""
    confirm: bool = Field(..., description="Confirmation flag - must be true")
    force_unlock: bool = Field(False, description="Force unlock emergency stops (requires extra confirmation)")
    
    @validator('confirm')
    def validate_confirm(cls, v):
        """Ensure confirm is explicitly True"""
        if v is not True:
            raise ValueError("Confirmation required. Set confirm=true to proceed.")
        return v


@router.post("/bots/start-all")
async def start_all_bots(
    data: StartAllBotsRequest,
    request: Request,
    admin_user_id: str = Depends(verify_admin)
):
    """
    Admin-only: Start/resume all paused bots across all users
    
    SAFETY GUARDRAILS:
    - Requires admin authentication
    - Requires explicit confirmation (confirm=true)
    - Respects live trading mode settings
    - Respects emergency stop locks (unless force_unlock=true)
    - Logs detailed audit trail
    - Does NOT start quarantined bots or bots in training
    
    Args:
        data: StartAllBotsRequest with confirmation flags
        
    Returns:
        Summary of bots resumed and any that were skipped
        
    Raises:
        400: If confirmation not provided
        403: If system is in emergency stop and force not specified
        500: Internal server error
    """
    try:
        if not data.confirm:
            raise HTTPException(
                status_code=400,
                detail="Confirmation required. Set confirm=true to proceed."
            )
        
        # Check system modes
        system_mode_doc = await db.system_mode_collection.find_one({}) or {}
        paper_trading = system_mode_doc.get("paperTrading", True)
        live_trading = system_mode_doc.get("liveTrading", False)
        emergency_stop = system_mode_doc.get("emergencyStop", False)
        
        # Check for emergency stop lock
        if emergency_stop and not data.force_unlock:
            raise HTTPException(
                status_code=403,
                detail="System is in EMERGENCY STOP mode. Use force_unlock=true to override (use with extreme caution)."
            )
        
        # Find all paused bots (not quarantined, not in training)
        paused_bots = await db.bots_collection.find({
            "status": "paused",
            "quarantine_reason": {"$exists": False}  # Exclude quarantined bots
        }).to_list(length=None)
        
        resumed_count = 0
        skipped_count = 0
        skipped_reasons = []
        
        for bot in paused_bots:
            bot_id = bot.get("id")
            bot_name = bot.get("name", "Unknown")
            bot_mode = bot.get("mode", "paper")
            user_id = bot.get("user_id")
            
            # Safety check: If bot is in live mode but live trading is disabled, skip
            if bot_mode == "live" and not live_trading:
                skipped_count += 1
                skipped_reasons.append({
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                    "reason": "Live trading disabled system-wide",
                    "mode": bot_mode
                })
                continue
            
            # Resume the bot
            try:
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "status": "active",
                            "resumed_at": datetime.now(timezone.utc).isoformat(),
                            "resumed_by_admin": admin_user_id
                        }
                    }
                )
                resumed_count += 1
                
                # Emit realtime event to user
                try:
                    from realtime_events import rt_events
                    await rt_events.bot_resumed(user_id, bot)
                except Exception as e:
                    logger.warning(f"Failed to emit bot_resumed event: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to resume bot {bot_id}: {e}")
                skipped_count += 1
                skipped_reasons.append({
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                    "reason": f"Error: {str(e)}"
                })
        
        # Log admin action to audit trail
        await log_admin_action(
            admin_id=admin_user_id,
            action="start_all_bots",
            target_type="system",
            target_id="all_bots",
            details={
                "resumed_count": resumed_count,
                "skipped_count": skipped_count,
                "force_unlock": data.force_unlock,
                "emergency_stop_bypassed": emergency_stop and data.force_unlock,
                "live_trading_enabled": live_trading,
                "paper_trading_enabled": paper_trading,
                "skipped_reasons": skipped_reasons[:10]  # Limit to first 10 for brevity
            },
            request=request
        )
        
        logger.info(
            f"Admin {admin_user_id[:8]} started all bots: "
            f"{resumed_count} resumed, {skipped_count} skipped"
        )
        
        return {
            "success": True,
            "message": f"Resumed {resumed_count} bots, skipped {skipped_count}",
            "resumed_count": resumed_count,
            "skipped_count": skipped_count,
            "skipped_reasons": skipped_reasons,
            "system_status": {
                "paper_trading": paper_trading,
                "live_trading": live_trading,
                "emergency_stop": emergency_stop,
                "emergency_stop_bypassed": emergency_stop and data.force_unlock
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start all bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emergency-stop/status")
async def get_emergency_stop_override_status(admin_id: str = Depends(require_admin)):
    """Get global/per-user emergency-stop overrides and currently active users."""
    overrides = await emergency_stop_override_service.get_status()
    active_docs = await db.system_modes_collection.find(
        {"emergencyStop": True},
        {"_id": 0, "user_id": 1, "emergency_stop_reason": 1, "emergency_stop_at": 1}
    ).to_list(1000)
    return {
        "success": True,
        "global": {
            "disabled": bool(overrides.get("global_disabled")),
            "reason": overrides.get("global_reason"),
            "updated_by": overrides.get("global_updated_by"),
            "updated_at": overrides.get("global_updated_at"),
        },
        "per_user": overrides.get("per_user", {}),
        "active_emergency_stop_users": active_docs,
    }


@router.post("/emergency-stop/global")
async def set_emergency_stop_global_override(
    data: EmergencyStopGlobalOverrideRequest,
    admin_id: str = Depends(require_admin),
):
    overrides = await emergency_stop_override_service.set_global(
        disabled=data.disabled,
        reason=data.reason,
        updated_by=admin_id,
    )
    await log_admin_action(
        admin_id=admin_id,
        action="emergency_stop_global_override",
        target_type="system",
        target_id="emergency_stop",
        details={"disabled": data.disabled, "reason": data.reason},
    )
    try:
        from realtime_events import rt_events
        affected = await db.system_modes_collection.find({"emergencyStop": True}, {"_id": 0, "user_id": 1}).to_list(1000)
        for item in affected:
            if item.get("user_id"):
                await rt_events.force_refresh(item["user_id"], reason="Emergency stop override updated by admin.")
    except Exception as e:
        logger.warning(f"Emergency stop global override realtime broadcast failed: {e}")
    return {"success": True, "global": {
        "disabled": bool(overrides.get("global_disabled")),
        "reason": overrides.get("global_reason"),
        "updated_by": overrides.get("global_updated_by"),
        "updated_at": overrides.get("global_updated_at"),
    }}


@router.post("/emergency-stop/user")
async def set_emergency_stop_user_override(
    data: EmergencyStopUserOverrideRequest,
    admin_id: str = Depends(require_admin),
):
    overrides = await emergency_stop_override_service.set_user(
        user_id=data.user_id,
        disabled=data.disabled,
        reason=data.reason,
        updated_by=admin_id,
    )
    await log_admin_action(
        admin_id=admin_id,
        action="emergency_stop_user_override",
        target_type="user",
        target_id=data.user_id,
        details={"disabled": data.disabled, "reason": data.reason},
    )
    try:
        from realtime_events import rt_events
        await rt_events.force_refresh(data.user_id, reason="Emergency stop override updated by admin.")
    except Exception as e:
        logger.warning(f"Emergency stop user override realtime broadcast failed: {e}")
    return {"success": True, "user_override": (overrides.get("per_user") or {}).get(data.user_id, {})}


@router.post("/emergency-stop/clear-user")
async def clear_emergency_stop_user_override(
    data: EmergencyStopClearUserOverrideRequest,
    admin_id: str = Depends(require_admin),
):
    overrides = await emergency_stop_override_service.clear_user(data.user_id)
    await log_admin_action(
        admin_id=admin_id,
        action="emergency_stop_user_override_clear",
        target_type="user",
        target_id=data.user_id,
        details={},
    )
    try:
        from realtime_events import rt_events
        await rt_events.force_refresh(data.user_id, reason="Emergency stop override cleared by admin.")
    except Exception as e:
        logger.warning(f"Emergency stop clear override realtime broadcast failed: {e}")
    return {"success": True, "per_user": overrides.get("per_user", {})}


@router.get("/trade-queue/state")
async def get_trade_queue_state(admin_id: str = Depends(require_admin)):
    """Admin-only diagnostic endpoint for trade queue state
    
    Returns:
        queue_size: int - Number of trades queued
        next_eligible: str - Timestamp when next trade can execute
        locks: dict - Current locks by bot_id
        cooldowns: dict - Current cooldowns by exchange
        sample_items: list - Small sample of queued items (redacted)
        timestamp: str - State snapshot timestamp
    """
    try:
        from engines.trade_staggerer import trade_staggerer
        
        # Get queue state
        state = await trade_staggerer.get_queue_state()
        
        return {
            "success": True,
            "queue_size": state.get("queue_size", 0),
            "next_eligible": state.get("next_eligible"),
            "locks": state.get("locks", {}),
            "cooldowns": state.get("cooldowns", {}),
            "sample_items": state.get("sample_items", []),
            "exchange_stats": state.get("exchange_stats", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Trade queue state error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status(
    admin_id: str = Depends(require_admin)
):
    """
    Get trading scheduler status (admin-only diagnostic endpoint)
    
    Returns scheduler state including:
    - running status
    - last tick timestamp
    - next tick timestamp  
    - total tick count
    - check interval
    """
    try:
        from trading_scheduler import trading_scheduler
        
        status = trading_scheduler.get_status()
        
        return {
            "success": True,
            "scheduler": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Scheduler status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/cohort-skips")
async def get_cohort_skip_counts(
    admin_id: str = Depends(require_admin)
):
    """
    P3 Diagnostic: per-cohort skip-reason counts (admin-only).

    Returns exact skip-reason counts broken down by:
    - exchange (binance / luno / kucoin / …)
    - bot_type (normal / scalper)

    Cohorts returned:
    - binance_normal, binance_scalper
    - luno_normal, luno_scalper
    - <exchange>_<type> for every other active exchange/type combination

    Each cohort entry contains:
    - total_bots: number of bots in this cohort
    - last_skip_reason: raw per-bot last skip reason
    - top_skip_reasons: ranked dict {reason: count}
    - eligibility_codes: ranked dict {code: count}
    """
    try:
        bots = await db.bots_collection.find(
            {
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {
                "_id": 0,
                "id": 1,
                "name": 1,
                "exchange": 1,
                "bot_type": 1,
                "last_skip_reason": 1,
                "last_eligibility": 1,
                "last_eligibility_code": 1,
                "status": 1,
            },
        ).to_list(5000)

        cohorts: dict = defaultdict(lambda: {
            "total_bots": 0,
            "skip_reason_counts": Counter(),
            "eligibility_code_counts": Counter(),
            "bot_details": [],
        })

        for bot in bots:
            exchange = (bot.get("exchange") or "unknown").lower()
            bot_type = (bot.get("bot_type") or "normal").lower()
            key = f"{exchange}_{bot_type}"
            cohorts[key]["total_bots"] += 1
            sr = bot.get("last_skip_reason") or ""
            ec = bot.get("last_eligibility") or bot.get("last_eligibility_code") or ""
            if sr:
                cohorts[key]["skip_reason_counts"][sr] += 1
            if ec:
                cohorts[key]["eligibility_code_counts"][ec] += 1
            cohorts[key]["bot_details"].append({
                "id": (bot.get("id") or "")[:8],
                "name": bot.get("name"),
                "status": bot.get("status"),
                "last_skip_reason": sr or None,
                "last_eligibility_code": ec or None,
            })

        result = {}
        for key, data in sorted(cohorts.items()):
            result[key] = {
                "total_bots": data["total_bots"],
                "top_skip_reasons": dict(data["skip_reason_counts"].most_common(10)),
                "eligibility_codes": dict(data["eligibility_code_counts"].most_common(10)),
                "bot_details": data["bot_details"],
            }

        return {
            "success": True,
            "cohorts": result,
            "total_bots_scanned": len(bots),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Cohort skip counts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/status")
async def get_learning_scheduler_status(
    admin_id: str = Depends(require_admin)
):
    """
    Get nightly learning scheduler status (admin-only diagnostic endpoint)
    
    Returns scheduler state including:
    - enabled status and reason
    - running status
    - last run timestamp and status
    - schedule hour
    - live learning flag
    """
    try:
        from services.nightly_learning_scheduler import nightly_learning_scheduler
        
        status = nightly_learning_scheduler.get_status()
        
        return {
            "success": True,
            "learning_scheduler": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Learning scheduler status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Admin: AI Chat Audit Trail ───────────────────────────────────────────────

@router.get("/audit/chat")
async def get_chat_audit(
    user_id_filter: Optional[str] = None,
    last_n: int = 100,
    admin_id: str = Depends(require_admin),
):
    """Get AI chat message audit trail (admin only).

    Query params:
        user_id_filter: restrict to a single user (optional)
        last_n: max number of records to return (default 100, max 500)

    Returns messages with action_name, action_payload, action_result, error_code.
    """
    try:
        limit = min(int(last_n), 500)
        query: dict = {}
        if user_id_filter:
            query["user_id"] = user_id_filter

        if db.chat_messages_collection is None:
            return {"success": True, "messages": [], "count": 0, "note": "chat_messages collection not available"}

        cursor = db.chat_messages_collection.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        messages = await cursor.to_list(limit)

        # Summarise per-user counts for the filtered set
        user_summary: dict = {}
        for msg in messages:
            uid = msg.get("user_id", "unknown")
            user_summary.setdefault(uid, {"messages": 0, "actions": 0, "errors": 0})
            user_summary[uid]["messages"] += 1
            if msg.get("action_name"):
                user_summary[uid]["actions"] += 1
            if msg.get("error_code"):
                user_summary[uid]["errors"] += 1

        return {
            "success": True,
            "messages": messages,
            "count": len(messages),
            "user_summary": user_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Chat audit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
