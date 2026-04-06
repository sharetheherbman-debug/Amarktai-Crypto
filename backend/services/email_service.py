"""
Email Service
Handles email notifications including withdrawal confirmations

Production SMTP implementation with Gmail app password support
"""

import logging
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import asyncio

import config
import database as db

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_configured = bool(config.SMTP_USER and config.SMTP_PASSWORD)
        
        if not self.smtp_configured:
            logger.warning("SMTP not configured - emails will be logged only. Set SMTP_USER and SMTP_PASSWORD in .env")
        else:
            logger.info(f"SMTP configured: {config.SMTP_HOST}:{config.SMTP_PORT} as {config.SMTP_USER}")
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        retries: int = 3
    ) -> Dict:
        """
        Send email via SMTP with retry logic
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            retries: Number of retry attempts (default 3)
            
        Returns:
            Dict with success status and details
        """
        if not self.smtp_configured:
            logger.info(f"""
            === EMAIL NOT SENT (SMTP NOT CONFIGURED) ===
            To: {to_email}
            Subject: {subject}
            Body: {body[:200]}...
            =============================================
            """)
            return {
                "success": False,
                "sent": False,
                "reason": "SMTP not configured",
                "message": "Email logged but not sent. Configure SMTP_USER and SMTP_PASSWORD."
            }
        
        # Run SMTP sending in executor to avoid blocking async event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._send_smtp,
            to_email,
            subject,
            body,
            html_body,
            retries
        )
        
        return result
    
    def _send_smtp(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str],
        retries: int
    ) -> Dict:
        """
        Synchronous SMTP sending with retry logic
        
        Supports Gmail app passwords and TLS
        """
        last_error = None
        
        for attempt in range(retries):
            try:
                # Create message
                msg = MIMEMultipart('alternative')
                msg['From'] = f"{config.FROM_NAME} <{config.FROM_EMAIL}>"
                msg['To'] = to_email
                msg['Subject'] = subject
                
                # Add plain text part
                msg.attach(MIMEText(body, 'plain'))
                
                # Add HTML part if provided
                if html_body:
                    msg.attach(MIMEText(html_body, 'html'))
                
                # Connect to SMTP server
                server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
                server.starttls()  # Upgrade to TLS
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                
                # Send email
                server.sendmail(config.FROM_EMAIL, to_email, msg.as_string())
                server.quit()
                
                logger.info(f"Email sent successfully to {to_email}: {subject}")
                
                return {
                    "success": True,
                    "sent": True,
                    "to": to_email,
                    "subject": subject,
                    "attempts": attempt + 1
                }
                
            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"SMTP authentication failed (attempt {attempt + 1}/{retries}): {e}")
                last_error = f"Authentication failed. Check SMTP_USER and SMTP_PASSWORD (use Gmail app password if Gmail)"
                # Don't retry on auth errors
                break
                
            except smtplib.SMTPException as e:
                logger.error(f"SMTP error (attempt {attempt + 1}/{retries}): {e}")
                last_error = str(e)
                
            except Exception as e:
                logger.error(f"Email send error (attempt {attempt + 1}/{retries}): {e}")
                last_error = str(e)
            
            # Wait before retry (exponential backoff)
            if attempt < retries - 1:
                import time
                wait_time = 2 ** attempt
                time.sleep(wait_time)
        
        # All retries failed
        logger.error(f"Failed to send email to {to_email} after {retries} attempts: {last_error}")
        return {
            "success": False,
            "sent": False,
            "to": to_email,
            "subject": subject,
            "error": last_error,
            "attempts": retries
        }
    
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
Amarktai Network Security Team (part of Amarktai Network)
            """
            
            # Send email via SMTP
            send_result = await self.send_email(
                to_email=email,
                subject=subject,
                body=body
            )
            
            return {
                "success": True,
                "confirmation_token": confirmation_token,
                "expires_at": expiry.isoformat(),
                "email_sent": send_result.get("sent", False),
                "message": "Confirmation email sent" if send_result.get("sent") else f"Confirmation token generated but email not sent: {send_result.get('reason', 'unknown')}"
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
Amarktai Network Security Team (part of Amarktai Network)
            """
            
            # Send email via SMTP
            send_result = await self.send_email(
                to_email=email,
                subject=subject,
                body=body
            )
            
            logger.info(f"Withdrawal alert sent to {email}: {send_result.get('sent', False)}")
                
        except Exception as e:
            logger.error(f"Failed to send withdrawal alert: {e}")
    
    async def send_daily_report(
        self,
        user_id: str,
        email: str,
        report_data: Dict
    ):
        """Send daily performance report"""
        try:
            subject = f"Daily Trading Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            
            body = f"""
Daily Trading Report

Performance Summary:
- Total Profit: R{report_data.get('total_profit', 0):.2f}
- Win Rate: {report_data.get('win_rate', 0):.1f}%
- Active Bots: {report_data.get('active_bots', 0)}
- Trades Today: {report_data.get('trades_today', 0)}

View full details in your dashboard.

---
Amarktai Network (part of Amarktai Network)
            """
            
            # Send email via SMTP
            send_result = await self.send_email(
                to_email=email,
                subject=subject,
                body=body
            )
            
            logger.info(f"Daily report sent to {email}: {send_result.get('sent', False)}")
            
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")


# Global instance
email_service = EmailService()

def get_email_service():
    """Get email service singleton"""
    return email_service
