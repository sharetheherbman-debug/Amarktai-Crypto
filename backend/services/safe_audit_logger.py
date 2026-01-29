"""
Safe Audit Logger Wrapper

Prevents 500 errors from audit logging failures.
Guards all log_action calls and provides fallback.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import database as db

logger = logging.getLogger(__name__)


class SafeAuditLogger:
    """
    Safe wrapper for audit logging that never raises exceptions
    
    Prevents endpoints from returning 500 due to audit logging failures.
    """
    
    async def log_action(
        self,
        user_id: str,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Log an action to the audit trail
        
        Args:
            user_id: User performing the action
            action: Action name (e.g., "bot_created", "autopilot_enabled")
            target_type: Type of target (e.g., "bot", "user", "system")
            target_id: ID of the target
            details: Additional details dict
            ip_address: IP address of the request
        
        Returns:
            bool: True if logged successfully, False if failed (never raises)
        """
        try:
            audit_doc = {
                "user_id": user_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if target_type:
                audit_doc["target_type"] = target_type
            
            if target_id:
                audit_doc["target_id"] = target_id
            
            if details:
                audit_doc["details"] = details
            
            if ip_address:
                audit_doc["ip_address"] = ip_address
            
            # Insert into audit logs collection
            await db.audit_logs_collection.insert_one(audit_doc)
            
            logger.debug(f"Audit log: {user_id[:8]} → {action}")
            return True
            
        except Exception as e:
            # Log the error but don't raise
            logger.error(f"Audit logging failed (non-fatal): {e}")
            logger.error(f"  Action: {action}, User: {user_id[:8] if user_id else 'unknown'}")
            return False
    
    async def log_admin_action(
        self,
        admin_id: str,
        action: str,
        target_type: str,
        target_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Log an admin action with additional admin-specific fields
        
        Never raises exceptions.
        """
        try:
            # Get admin details
            admin_user = await db.users_collection.find_one(
                {"id": admin_id},
                {"_id": 0, "email": 1, "first_name": 1}
            )
            
            admin_username = "unknown"
            if admin_user:
                admin_username = admin_user.get("email", "unknown")
            
            audit_doc = {
                "admin_id": admin_id,
                "admin_username": admin_username,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if details:
                audit_doc["details"] = details
            
            if ip_address:
                audit_doc["ip_address"] = ip_address
            
            await db.audit_logs_collection.insert_one(audit_doc)
            
            logger.debug(f"Admin audit log: {admin_id[:8]} → {action} on {target_type} {target_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"Admin audit logging failed (non-fatal): {e}")
            return False
    
    async def log_system_event(
        self,
        event: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log a system-level event (no specific user)
        
        Never raises exceptions.
        """
        try:
            audit_doc = {
                "event_type": "system",
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if details:
                audit_doc["details"] = details
            
            await db.audit_logs_collection.insert_one(audit_doc)
            
            logger.debug(f"System event logged: {event}")
            return True
            
        except Exception as e:
            logger.error(f"System event logging failed (non-fatal): {e}")
            return False
    
    async def get_recent_logs(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Get recent audit logs
        
        Args:
            user_id: Filter by user ID (optional)
            limit: Max number of logs to return
        
        Returns:
            List of audit log documents
        """
        try:
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            cursor = db.audit_logs_collection.find(
                query,
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            
            logs = await cursor.to_list(limit)
            return logs
            
        except Exception as e:
            logger.error(f"Get recent logs failed: {e}")
            return []


# Global instance
safe_audit_logger = SafeAuditLogger()


# Legacy compatibility
class AuditLoggerCompat:
    """
    Compatibility layer for existing code that uses audit_logger.log_action
    """
    
    async def log_action(self, *args, **kwargs):
        """Delegate to safe audit logger"""
        return await safe_audit_logger.log_action(*args, **kwargs)


# Export for backward compatibility
audit_logger = AuditLoggerCompat()
