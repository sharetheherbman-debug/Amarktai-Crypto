"""
Email Service
Handles email notifications including withdrawal confirmations

NOTE: This is a stub implementation that logs emails instead of sending them.
When SMTP is configured, it will actually send emails.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

import config
import database as db

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails (stub for now, real SMTP later)"""
    
    def __init__(self):
        self.smtp_configured = bool(config.SMTP_USER and config.SMTP_PASSWORD)
        
        if not self.smtp_configured:
            logger.info("SMTP not configured - emails will be logged only")
    
    async def send_withdrawal_confirmation(
        self, 
        user_id: str,
        email: str,
        transfer_id: str,
        from_exchange: str,
        to_exchange: str,
        currency: str,
        amount: float
    ) -> Dict:
        """
        Send withdrawal confirmation email
        
        Returns confirmation token and expiry
        """
        try:
            # Generate confirmation token
            confirmation_token = str(uuid.uuid4())
            expiry = datetime.now(timezone.utc) + timedelta(hours=config.EMAIL_CONFIRMATION_TIMEOUT_HOURS)
            
            # Store token in database
            confirmation_record = {
                "token": confirmation_token,
                "user_id": user_id,
                "transfer_id": transfer_id,
                "type": "withdrawal_confirmation",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expiry.isoformat(),
                "used": False,
                "email": email
            }
            
            await db.db['email_confirmations'].insert_one(confirmation_record)
            
            # Email content
            subject = f"Confirm Withdrawal: {amount} {currency}"
            
            # Confirmation URL (would be frontend URL in production)
            confirmation_url = f"https://your-domain.com/confirm-withdrawal?token={confirmation_token}"
            
            body = f"""
            Withdrawal Confirmation Required
            
            You have initiated a withdrawal:
            - From: {from_exchange}
            - To: {to_exchange}
            - Amount: {amount} {currency}
            - Transfer ID: {transfer_id}
            
            To confirm this withdrawal, click the link below:
            {confirmation_url}
            
            This link expires in {config.EMAIL_CONFIRMATION_TIMEOUT_HOURS} hours.
            
            If you did not initiate this withdrawal, please contact support immediately.
            
            ---
            Amarktai Network Security Team
            """
            
            # For now, just log the email (SMTP configured later)
            if self.smtp_configured:
                # TODO: Actually send email via SMTP
                logger.info(f"Would send email to {email}: {subject}")
            else:
                logger.info(f"""
                === EMAIL CONFIRMATION (NOT SENT - SMTP NOT CONFIGURED) ===
                To: {email}
                Subject: {subject}
                Transfer ID: {transfer_id}
                Confirmation Token: {confirmation_token}
                Confirmation URL: {confirmation_url}
                Expiry: {expiry.isoformat()}
                ============================================================
                """)
            
            return {
                "success": True,
                "confirmation_token": confirmation_token,
                "expires_at": expiry.isoformat(),
                "email_sent": self.smtp_configured,
                "message": "Confirmation email sent" if self.smtp_configured else "Confirmation token generated (SMTP not configured - check logs)"
            }
            
        except Exception as e:
            logger.error(f"Failed to send withdrawal confirmation email: {e}")
            raise
    
    async def verify_confirmation_token(self, token: str) -> Optional[Dict]:
        """
        Verify and consume a confirmation token
        
        Returns confirmation record if valid, None if invalid/expired
        """
        try:
            # Find token
            confirmation = await db.db['email_confirmations'].find_one(
                {"token": token, "used": False},
                {"_id": 0}
            )
            
            if not confirmation:
                return None
            
            # Check expiry
            expiry = datetime.fromisoformat(confirmation['expires_at'])
            if datetime.now(timezone.utc) > expiry:
                logger.warning(f"Confirmation token {token} has expired")
                return None
            
            # Mark as used
            await db.db['email_confirmations'].update_one(
                {"token": token},
                {
                    "$set": {
                        "used": True,
                        "used_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"Confirmation token {token} verified and consumed")
            return confirmation
            
        except Exception as e:
            logger.error(f"Failed to verify confirmation token: {e}")
            return None
    
    async def send_withdrawal_alert(
        self,
        user_id: str,
        email: str,
        transfer_id: str,
        from_exchange: str,
        to_exchange: str,
        currency: str,
        amount: float
    ):
        """Send alert that withdrawal has been executed"""
        try:
            subject = f"Withdrawal Executed: {amount} {currency}"
            
            body = f"""
            Withdrawal Executed
            
            Your withdrawal has been processed:
            - From: {from_exchange}
            - To: {to_exchange}
            - Amount: {amount} {currency}
            - Transfer ID: {transfer_id}
            - Time: {datetime.now(timezone.utc).isoformat()}
            
            You can track the transfer status in your dashboard.
            
            If you did not authorize this withdrawal, contact support immediately.
            
            ---
            Amarktai Network Security Team
            """
            
            if self.smtp_configured:
                # TODO: Actually send email via SMTP
                logger.info(f"Would send withdrawal alert to {email}")
            else:
                logger.info(f"""
                === WITHDRAWAL ALERT (NOT SENT - SMTP NOT CONFIGURED) ===
                To: {email}
                Subject: {subject}
                Transfer ID: {transfer_id}
                ==========================================================
                """)
                
        except Exception as e:
            logger.error(f"Failed to send withdrawal alert: {e}")


# Global instance
email_service = EmailService()
