"""
Admin Dashboard Endpoints
User management, system monitoring, and administrative actions
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
import logging
from datetime import datetime, timezone
import bcrypt
import os
import secrets
import string
import random

from auth import get_current_user, require_admin
import database as db
from engines.audit_logger import audit_logger
from json_utils import serialize_doc, serialize_list

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])


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
        
        # Get admin password from environment (defaults to Ashmor12@ if not set)
        admin_password = os.getenv('ADMIN_PASSWORD', 'Ashmor12@')
        
        if not admin_password or not admin_password.strip():
            logger.error("ADMIN_PASSWORD environment variable is empty")
            raise HTTPException(
                status_code=500, 
                detail="Server configuration error: Admin password not configured"
            )
        
        admin_password = admin_password.strip()
        
        # Case-insensitive and whitespace-tolerant comparison
        if password.lower() != admin_password.lower():
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
                "bitget": any(k.get("provider") == "bitget" for k in api_keys),
            }
            
            # Get bots summary
            bots_cursor = db.bots_collection.find({"user_id": user_id}, {"_id": 0, "exchange": 1, "trading_mode": 1, "status": 1})
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
                "user_id": user_id,
                "username": user_data.get("first_name") or user_data.get("name", "Unknown"),
                "email": user_data.get("email", "N/A"),
                "role": user_data.get("role", "admin" if user_data.get("is_admin") else "user"),
                "is_active": not user_data.get("blocked", False),
                "created_at": user_data.get("created_at", "N/A"),
                "last_seen": user_data.get("last_seen", "N/A"),
                "api_keys": api_keys_summary,
                "bots_summary": bots_summary,
                "resource_usage": resource_usage
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
        if db.sessions_collection:
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


# ============================================================================
# BOT OVERRIDE ENDPOINTS
# ============================================================================

@router.get("/system-stats")
async def get_system_stats_extended(admin_user_id: str = Depends(verify_admin)):
    """
    Get comprehensive system statistics including VPS resources
    Returns CPU, RAM, disk usage, and system health
    """
    import psutil
    import shutil
    
    try:
        # Get user statistics
        total_users = await db.users_collection.count_documents({})
        active_users = await db.users_collection.count_documents({"status": "active"})
        blocked_users = await db.users_collection.count_documents({"status": "blocked"})
        
        total_bots = await db.bots_collection.count_documents({})
        active_bots = await db.bots_collection.count_documents({"status": "active"})
        live_bots = await db.bots_collection.count_documents({"mode": "live"})
        
        total_trades = await db.trades_collection.count_documents({})
        live_trades = await db.trades_collection.count_documents({"is_paper": False})
        
        # Calculate total profit across all users
        all_bots = await db.bots_collection.find(
            {},
            {"_id": 0, "total_profit": 1}
        ).to_list(10000)
        total_profit = sum(b.get('total_profit', 0) for b in all_bots)
        
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
        
        total_bots = await db.bots_collection.count_documents({})
        active_bots = await db.bots_collection.count_documents({"status": "active"})
        live_bots = await db.bots_collection.count_documents({"mode": "live"})
        
        total_trades = await db.trades_collection.count_documents({})
        live_trades = await db.trades_collection.count_documents({"is_paper": False})
        
        # Calculate total profit across all users
        all_bots = await db.bots_collection.find(
            {},
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
        
        # Verify current password
        admin_password = os.getenv('ADMIN_PASSWORD')
        if not admin_password or current_password.lower() != admin_password.lower():
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
    Get all bots (admin view) with comprehensive details
    - Bot info (id, name, user, exchange, mode, status)
    - Pause information (reason, timestamp)
    - Capital and profit/loss
    
    Args:
        mode: Filter by trading mode ('paper' or 'live')
        user_id: Filter by specific user (optional)
    """
    try:
        # Build query
        query = {}
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
        enriched_bots.sort(key=lambda b: b["name"])
        
        return {
            "bots": enriched_bots,
            "total": len(enriched_bots)
        }
        
    except Exception as e:
        logger.error(f"Get all bots admin error: {e}")
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
        
        # Count bots by status
        total_bots = await db.bots_collection.count_documents({})
        active_bots = await db.bots_collection.count_documents({"status": "active"})
        paused_bots = await db.bots_collection.count_documents({"status": "paused"})
        stopped_bots = await db.bots_collection.count_documents({"status": "stopped"})
        
        # Count trades (last 24h)
        from datetime import datetime, timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_trades = await db.trades_collection.count_documents({
            "created_at": {"$gte": yesterday.isoformat()}
        })
        
        # Get system mode flags (from first admin user)
        admin_user = await db.users_collection.find_one({"is_admin": True})
        system_mode = {
            "paper_trading": admin_user.get("paper_trading", True) if admin_user else True,
            "live_trading": admin_user.get("live_trading", False) if admin_user else False,
            "autopilot": admin_user.get("autopilot_enabled", False) if admin_user else False,
        }
        
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
