"""
Enhanced Email Service with Async SMTP
Handles all email notifications with templates and async delivery
"""

import logging
import asyncio
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import uuid

import config
import database as db

logger = logging.getLogger(__name__)

# Frontend domain used in email links — configurable via FRONTEND_URL env var
_APP_DOMAIN = os.getenv("FRONTEND_URL", "https://amarktai.online")


class EmailTemplates:
    """Email templates for different notification types"""
    
    @staticmethod
    def withdrawal_confirmation(
        from_exchange: str,
        to_exchange: str,
        amount: float,
        currency: str,
        transfer_id: str,
        confirmation_url: str,
        expiry_hours: int
    ) -> tuple[str, str]:
        """Generate withdrawal confirmation email"""
        subject = f"Confirm Withdrawal: {amount} {currency}"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2c3e50;">Withdrawal Confirmation Required</h2>
                
                <p>You have initiated a withdrawal from your Amarktai Crypto account:</p>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>From:</strong> {from_exchange}</p>
                    <p style="margin: 5px 0;"><strong>To:</strong> {to_exchange}</p>
                    <p style="margin: 5px 0;"><strong>Amount:</strong> {amount} {currency}</p>
                    <p style="margin: 5px 0;"><strong>Transfer ID:</strong> {transfer_id}</p>
                </div>
                
                <p style="margin: 20px 0;">
                    <a href="{confirmation_url}" 
                       style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Confirm Withdrawal
                    </a>
                </p>
                
                <p style="color: #e74c3c; margin: 20px 0;">
                    <strong>Important:</strong> This link expires in {expiry_hours} hours.
                </p>
                
                <p style="color: #7f8c8d; font-size: 14px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
                    If you did not initiate this withdrawal, please contact support immediately.<br>
                    <strong>Amarktai Crypto Security Team (part of Amarktai Network)</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return subject, html
    
    @staticmethod
    def daily_report(
        user_email: str,
        total_bots: int,
        active_bots: int,
        total_profit: float,
        daily_profit: float,
        best_performing_bot: Dict,
        recent_trades: List[Dict],
        date: str
    ) -> tuple[str, str]:
        """Generate daily performance report"""
        subject = f"Daily Trading Report - {date}"
        
        trades_html = ""
        for trade in recent_trades[:5]:  # Last 5 trades
            trades_html += f"""
                <tr>
                    <td style="padding: 8px;">{trade.get('symbol', 'N/A')}</td>
                    <td style="padding: 8px;">{trade.get('side', 'N/A')}</td>
                    <td style="padding: 8px;">R{trade.get('profit', 0):.2f}</td>
                    <td style="padding: 8px; color: {'green' if trade.get('profit', 0) > 0 else 'red'};">
                        {trade.get('status', 'N/A')}
                    </td>
                </tr>
            """
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Daily Trading Report</h2>
                <p style="color: #7f8c8d;">Date: {date}</p>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0;">
                    <div style="background: #3498db; color: white; padding: 15px; border-radius: 5px;">
                        <h3 style="margin: 0;">Total Bots</h3>
                        <p style="font-size: 24px; margin: 10px 0;">{total_bots}</p>
                        <small>{active_bots} active</small>
                    </div>
                    
                    <div style="background: #27ae60; color: white; padding: 15px; border-radius: 5px;">
                        <h3 style="margin: 0;">Total Profit</h3>
                        <p style="font-size: 24px; margin: 10px 0;">R{total_profit:.2f}</p>
                        <small>Today: R{daily_profit:.2f}</small>
                    </div>
                </div>
                
                {f'''
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3>Best Performing Bot</h3>
                    <p><strong>Name:</strong> {best_performing_bot.get('name', 'N/A')}</p>
                    <p><strong>Profit:</strong> R{best_performing_bot.get('profit', 0):.2f}</p>
                    <p><strong>Win Rate:</strong> {best_performing_bot.get('win_rate', 0):.1f}%</p>
                </div>
                ''' if best_performing_bot else ''}
                
                <h3 style="margin-top: 30px;">Recent Trades</h3>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr style="background: #ecf0f1;">
                            <th style="padding: 10px; text-align: left;">Symbol</th>
                            <th style="padding: 10px; text-align: left;">Side</th>
                            <th style="padding: 10px; text-align: left;">Profit</th>
                            <th style="padding: 10px; text-align: left;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades_html}
                    </tbody>
                </table>
                
                <p style="color: #7f8c8d; font-size: 14px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
                    This is an automated report from your Amarktai Crypto trading system (part of Amarktai Network).<br>
                    <a href="{_APP_DOMAIN}/dashboard">View Dashboard</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return subject, html
    
    @staticmethod
    def critical_alert(
        alert_type: str,
        message: str,
        details: Dict,
        severity: str = "high"
    ) -> tuple[str, str]:
        """Generate critical system alert email"""
        subject = f"🚨 Critical Alert: {alert_type}"
        
        severity_colors = {
            "critical": "#e74c3c",
            "high": "#e67e22",
            "medium": "#f39c12",
            "low": "#3498db"
        }
        
        color = severity_colors.get(severity, "#e74c3c")
        
        details_html = ""
        for key, value in details.items():
            details_html += f"<p style='margin: 5px 0;'><strong>{key}:</strong> {value}</p>"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid {color}; border-radius: 5px;">
                <h2 style="color: {color};">🚨 Critical Alert</h2>
                
                <div style="background: {color}; color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin: 0;">{alert_type}</h3>
                    <p style="margin: 10px 0;">{message}</p>
                    <small>Severity: {severity.upper()}</small>
                </div>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4>Details:</h4>
                    {details_html}
                    <p style="margin-top: 10px;"><strong>Time:</strong> {datetime.now(timezone.utc).isoformat()}</p>
                </div>
                
                <p style="margin: 20px 0;">
                    <a href="{_APP_DOMAIN}/system-status" 
                       style="display: inline-block; padding: 12px 24px; background: {color}; color: white; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        View System Status
                    </a>
                </p>
                
                <p style="color: #7f8c8d; font-size: 14px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
                    This is an automated alert from your Amarktai Crypto system (part of Amarktai Network).<br>
                    <strong>Amarktai Crypto Operations</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return subject, html


class AsyncSMTPSender:
    """Async SMTP email sender"""
    
    def __init__(self):
        self.smtp_configured = bool(config.SMTP_USER and config.SMTP_PASSWORD)
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.username = config.SMTP_USER
        self.password = config.SMTP_PASSWORD
        self.from_email = config.FROM_EMAIL or config.SMTP_USER
        self.from_name = config.FROM_NAME
        
        if self.smtp_configured:
            logger.info(f"SMTP configured: {self.username}@{self.host}:{self.port}")
        else:
            logger.warning("SMTP not configured - emails will be logged only")
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        priority: str = "normal"
    ) -> bool:
        """
        Send email asynchronously
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML email content
            priority: Email priority (low, normal, high)
        
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.smtp_configured:
            logger.info(f"""
            === EMAIL (NOT SENT - SMTP NOT CONFIGURED) ===
            To: {to_email}
            Subject: {subject}
            Priority: {priority}
            ===============================================
            """)
            return False
        
        try:
            # Run SMTP in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._send_sync,
                to_email,
                subject,
                html_content,
                priority
            )
            return result
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def _send_sync(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        priority: str
    ) -> bool:
        """Synchronous email sending (runs in executor)"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Set priority header
            if priority == "high":
                msg['X-Priority'] = '1'
                msg['Importance'] = 'High'
            elif priority == "low":
                msg['X-Priority'] = '5'
                msg['Importance'] = 'Low'
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send via SMTP
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error sending to {to_email}: {e}")
            return False


class EnhancedEmailService:
    """Enhanced email service with templates and async delivery"""
    
    def __init__(self):
        self.sender = AsyncSMTPSender()
        self.templates = EmailTemplates()
    
    async def send_daily_report(
        self,
        user_id: str,
        user_email: str,
        report_data: Dict
    ) -> bool:
        """Send daily trading report"""
        try:
            subject, html = self.templates.daily_report(
                user_email=user_email,
                total_bots=report_data.get('total_bots', 0),
                active_bots=report_data.get('active_bots', 0),
                total_profit=report_data.get('total_profit', 0.0),
                daily_profit=report_data.get('daily_profit', 0.0),
                best_performing_bot=report_data.get('best_performing_bot', {}),
                recent_trades=report_data.get('recent_trades', []),
                date=datetime.now(timezone.utc).strftime('%Y-%m-%d')
            )
            
            success = await self.sender.send_email(
                to_email=user_email,
                subject=subject,
                html_content=html,
                priority="normal"
            )
            
            # Log to database
            await db.db['email_log'].insert_one({
                "user_id": user_id,
                "email": user_email,
                "type": "daily_report",
                "subject": subject,
                "sent": success,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send daily report to {user_email}: {e}")
            return False
    
    async def send_critical_alert(
        self,
        user_id: str,
        user_email: str,
        alert_type: str,
        message: str,
        details: Dict,
        severity: str = "high"
    ) -> bool:
        """Send critical system alert"""
        try:
            subject, html = self.templates.critical_alert(
                alert_type=alert_type,
                message=message,
                details=details,
                severity=severity
            )
            
            success = await self.sender.send_email(
                to_email=user_email,
                subject=subject,
                html_content=html,
                priority="high"
            )
            
            # Log to database
            await db.db['email_log'].insert_one({
                "user_id": user_id,
                "email": user_email,
                "type": "critical_alert",
                "alert_type": alert_type,
                "severity": severity,
                "subject": subject,
                "sent": success,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send critical alert to {user_email}: {e}")
            return False
    
    async def send_withdrawal_confirmation(
        self,
        user_id: str,
        user_email: str,
        transfer_id: str,
        from_exchange: str,
        to_exchange: str,
        currency: str,
        amount: float
    ) -> Dict:
        """Send withdrawal confirmation with token"""
        try:
            # Generate confirmation token
            confirmation_token = str(uuid.uuid4())
            expiry_hours = config.EMAIL_CONFIRMATION_TIMEOUT_HOURS
            expiry = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
            
            # Store in database
            await db.db['email_confirmations'].insert_one({
                "token": confirmation_token,
                "user_id": user_id,
                "transfer_id": transfer_id,
                "type": "withdrawal_confirmation",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expiry.isoformat(),
                "used": False,
                "email": user_email
            })
            
            # Generate email
            confirmation_url = f"{_APP_DOMAIN}/confirm-withdrawal?token={confirmation_token}"
            subject, html = self.templates.withdrawal_confirmation(
                from_exchange=from_exchange,
                to_exchange=to_exchange,
                amount=amount,
                currency=currency,
                transfer_id=transfer_id,
                confirmation_url=confirmation_url,
                expiry_hours=expiry_hours
            )
            
            # Send email
            success = await self.sender.send_email(
                to_email=user_email,
                subject=subject,
                html_content=html,
                priority="high"
            )
            
            return {
                "success": True,
                "confirmation_token": confirmation_token,
                "expires_at": expiry.isoformat(),
                "email_sent": success,
                "message": "Confirmation email sent" if success else "Token generated (check logs)"
            }
            
        except Exception as e:
            logger.error(f"Failed to send withdrawal confirmation: {e}")
            raise


# Global instance
enhanced_email_service = EnhancedEmailService()
