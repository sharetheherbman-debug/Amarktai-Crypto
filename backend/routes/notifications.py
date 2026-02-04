"""
Notifications API Endpoints
Handles email notifications, test emails, and welcome emails
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
import logging
from datetime import datetime

from auth import get_current_user
from services.enhanced_email_service import enhanced_email_service
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.post("/test-email")
async def send_test_email(current_user: Dict = Depends(get_current_user)):
    """
    Send test email to verify SMTP configuration (admin only).
    
    Requires admin privileges.
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": current_user['id']}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Admin check
        is_admin = user.get('is_admin', False) or user.get('role') == 'admin'
        if not is_admin:
            raise HTTPException(
                status_code=403, 
                detail="Admin privileges required to send test emails"
            )
        
        user_email = user.get('email')
        if not user_email:
            raise HTTPException(status_code=404, detail="User email not found")
        
        # Check if email service is enabled
        if not enhanced_email_service.enabled:
            return {
                "success": False,
                "message": "Email service is not configured. Set SMTP_USER, SMTP_PASSWORD, and SMTP_HOST environment variables.",
                "email_enabled": False
            }
        
        # Send test email
        success = await enhanced_email_service.send_test_email(user_email)
        
        return {
            "success": success,
            "message": f"Test email {'sent successfully' if success else 'failed'} to {user_email}",
            "email": user_email,
            "email_enabled": enhanced_email_service.enabled,
            "smtp_server": enhanced_email_service.smtp_server,
            "smtp_port": enhanced_email_service.smtp_port
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test email error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test email failed: {str(e)}")


@router.post("/welcome-email")
async def send_welcome_email_manual(
    email: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Manually send welcome email to a user (admin only).
    
    Requires admin privileges.
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": current_user['id']}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Admin check
        is_admin = user.get('is_admin', False) or user.get('role') == 'admin'
        if not is_admin:
            raise HTTPException(
                status_code=403, 
                detail="Admin privileges required"
            )
        
        # Check if email service is enabled
        if not enhanced_email_service.enabled:
            return {
                "success": False,
                "message": "Email service is not configured",
                "email_enabled": False
            }
        
        # Send welcome email
        success = await enhanced_email_service.send_welcome_email(email)
        
        return {
            "success": success,
            "message": f"Welcome email {'sent successfully' if success else 'failed'} to {email}",
            "email": email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Welcome email error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Welcome email failed: {str(e)}")


@router.post("/circuit-breaker-alert")
async def send_circuit_breaker_alert_manual(
    exchange: str,
    reason: str,
    error_count: int = 0,
    current_user: Dict = Depends(get_current_user)
):
    """
    Manually send circuit breaker alert (admin only, for testing).
    
    Requires admin privileges.
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": current_user['id']}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Admin check
        is_admin = user.get('is_admin', False) or user.get('role') == 'admin'
        if not is_admin:
            raise HTTPException(
                status_code=403, 
                detail="Admin privileges required"
            )
        
        user_email = user.get('email')
        if not user_email:
            raise HTTPException(status_code=404, detail="User email not found")
        
        # Check if email service is enabled
        if not enhanced_email_service.enabled:
            return {
                "success": False,
                "message": "Email service is not configured",
                "email_enabled": False
            }
        
        # Prepare alert data
        alert_data = {
            'exchange': exchange,
            'reason': reason,
            'error_count': error_count,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Send circuit breaker alert
        success = await enhanced_email_service.send_circuit_breaker_alert(
            user_email, 
            alert_data
        )
        
        return {
            "success": success,
            "message": f"Circuit breaker alert {'sent successfully' if success else 'failed'} to {user_email}",
            "email": user_email,
            "alert_data": alert_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Circuit breaker alert error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Alert send failed: {str(e)}")


@router.get("/email-status")
async def get_email_status(current_user: Dict = Depends(get_current_user)):
    """
    Get email service status and configuration.
    """
    return {
        "email_enabled": enhanced_email_service.enabled,
        "smtp_server": enhanced_email_service.smtp_server if enhanced_email_service.enabled else None,
        "smtp_port": enhanced_email_service.smtp_port if enhanced_email_service.enabled else None,
        "from_email": enhanced_email_service.from_email if enhanced_email_service.enabled else None,
        "from_name": enhanced_email_service.from_name if enhanced_email_service.enabled else None,
    }
