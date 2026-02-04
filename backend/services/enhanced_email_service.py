"""
Enhanced Email Service with Template Support
Handles welcome emails, daily reports, and circuit breaker alerts
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger_config import logger
from core.settings import settings, FeatureFlags
from typing import List, Dict, Optional
from datetime import datetime
import secrets
from email_templates.templates import (
    get_welcome_template,
    get_daily_report_template,
    get_circuit_breaker_template
)


class EnhancedEmailService:
    """Enhanced email service with template support and scheduled reports"""
    
    def __init__(self):
        # Load SMTP configuration from settings
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.from_email_address
        self.from_name = settings.FROM_NAME
        
        # Validate configuration on startup
        self.enabled = self._validate_config()
        
        if not self.enabled:
            logger.warning("⚠️  Email service disabled: Missing SMTP configuration")
            logger.warning("⚠️  Set SMTP_USER, SMTP_PASSWORD, SMTP_HOST to enable")
        else:
            logger.info(f"✅ Enhanced email service enabled: {self.smtp_server}:{self.smtp_port}")
    
    def _validate_config(self) -> bool:
        """Validate SMTP configuration"""
        if not self.smtp_user or not self.smtp_password:
            return False
        
        if not self.smtp_server:
            logger.error("SMTP_HOST is required but not set")
            return False
        
        return True
    
    async def send_email(self, 
                        to_email: str, 
                        subject: str, 
                        html_body: str, 
                        plain_text_body: Optional[str] = None) -> bool:
        """
        Send email with both HTML and plain text versions.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            plain_text_body: Plain text fallback (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"Email disabled, skipping: {subject} to {to_email}")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add plain text version first (fallback)
            if plain_text_body:
                msg.attach(MIMEText(plain_text_body, 'plain', 'utf-8'))
            
            # Add HTML version second (preferred)
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✉️  Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Email send error to {to_email}: {e}", exc_info=True)
            return False
    
    async def send_welcome_email(self, 
                                 user_email: str, 
                                 set_password_token: Optional[str] = None) -> bool:
        """
        Send welcome email with secure password setup link.
        IMPORTANT: Does NOT send password in email for security.
        
        Args:
            user_email: New user's email address
            set_password_token: Secure token for password setup (generated if not provided)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        # Generate token if not provided
        if not set_password_token:
            set_password_token = secrets.token_urlsafe(32)
            logger.info(f"Generated password setup token for {user_email}: {set_password_token}")
        
        # Construct password setup URL
        base_url = "https://www.amarktai.online"
        set_password_url = f"{base_url}/set-password?token={set_password_token}&email={user_email}"
        
        # Generate email from template
        html_body, plain_text = get_welcome_template(user_email, set_password_url)
        
        # Send email
        success = await self.send_email(
            to_email=user_email,
            subject="Welcome to Amarktai Network - Set Your Password",
            html_body=html_body,
            plain_text_body=plain_text
        )
        
        if success:
            logger.info(f"✅ Welcome email sent to {user_email}")
        
        return success
    
    async def send_daily_report(self, user_email: str, report_data: Dict) -> bool:
        """
        Send daily trading report.
        
        Args:
            user_email: User's email address
            report_data: Report data dictionary with keys:
                - date: Report date
                - total_profit: Total realized profit
                - daily_profit: Today's profit
                - weekly_profit: This week's profit
                - monthly_profit: This month's profit
                - trades_today: Number of trades today
                - win_rate: Win rate percentage
                - active_bots: Number of active bots
                - exchange_breakdown: Dict of exchange data
                - top_performers: List of top performing bots
                
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        if not FeatureFlags.ENABLE_EMAIL_REPORTS:
            logger.debug("Email reports disabled via ENABLE_EMAIL_REPORTS flag")
            return False
        
        # Add current date if not provided
        if 'date' not in report_data:
            report_data['date'] = datetime.now().strftime('%B %d, %Y')
        
        # Generate email from template
        html_body, plain_text = get_daily_report_template(report_data)
        
        # Send email
        subject = f"Daily Trading Report - {report_data.get('date', 'Today')}"
        success = await self.send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text
        )
        
        if success:
            logger.info(f"✅ Daily report sent to {user_email}")
        
        return success
    
    async def send_circuit_breaker_alert(self, 
                                         user_email: str, 
                                         alert_data: Dict) -> bool:
        """
        Send circuit breaker activation alert.
        
        Args:
            user_email: User's email address
            alert_data: Alert data dictionary with keys:
                - exchange: Exchange name
                - reason: Reason for circuit breaker activation
                - error_count: Number of errors detected
                - timestamp: Alert timestamp
                
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        # Add timestamp if not provided
        if 'timestamp' not in alert_data:
            alert_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Generate email from template
        html_body, plain_text = get_circuit_breaker_template(alert_data)
        
        # Send email
        exchange = alert_data.get('exchange', 'Unknown')
        subject = f"⚠️ Circuit Breaker Activated - {exchange.title()}"
        success = await self.send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text
        )
        
        if success:
            logger.info(f"✅ Circuit breaker alert sent to {user_email} for {exchange}")
        
        return success
    
    async def send_test_email(self, to_email: str) -> bool:
        """
        Send test email to verify configuration.
        
        Args:
            to_email: Recipient email address
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        # Simple test email
        html_body = """
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #3b82f6;">Test Email from Amarktai Network</h2>
            <p>This is a test email to verify your SMTP configuration is working correctly.</p>
            <p>If you received this email, your email service is configured properly!</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Sent at: {timestamp}<br>
                From: {from_name} &lt;{from_email}&gt;
            </p>
        </div>
        """.format(
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            from_name=self.from_name,
            from_email=self.from_email
        )
        
        plain_text = f"""
Test Email from Amarktai Network

This is a test email to verify your SMTP configuration is working correctly.

If you received this email, your email service is configured properly!

---
Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
From: {self.from_name} <{self.from_email}>
        """.strip()
        
        success = await self.send_email(
            to_email=to_email,
            subject="Test Email - Amarktai Network",
            html_body=html_body,
            plain_text_body=plain_text
        )
        
        if success:
            logger.info(f"✅ Test email sent to {to_email}")
        
        return success
    
    async def send_bulk_daily_reports(self, 
                                     user_reports: List[Dict[str, Dict]]) -> Dict[str, int]:
        """
        Send daily reports to multiple users.
        
        Args:
            user_reports: List of dicts with 'email' and 'report_data' keys
            
        Returns:
            Dict with 'sent' and 'failed' counts
        """
        sent = 0
        failed = 0
        
        for user_report in user_reports:
            user_email = user_report.get('email')
            report_data = user_report.get('report_data', {})
            
            if not user_email:
                failed += 1
                continue
            
            success = await self.send_daily_report(user_email, report_data)
            if success:
                sent += 1
            else:
                failed += 1
        
        logger.info(f"📊 Bulk daily reports: {sent} sent, {failed} failed")
        return {"sent": sent, "failed": failed}


# Singleton instance
enhanced_email_service = EnhancedEmailService()
