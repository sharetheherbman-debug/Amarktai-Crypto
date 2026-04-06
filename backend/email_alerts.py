"""
Email Alert System
- SMTP email notifications for critical events
- Large losses, system errors, promotions, milestones
"""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from logger_config import logger
import os


class EmailAlertSystem:
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@amarktai.com')
        self.enabled = bool(self.smtp_user and self.smtp_password)
        
        if not self.enabled:
            logger.warning("Email alerts disabled - SMTP credentials not configured")
    
    async def send_email(self, to_email: str, subject: str, body: str, html: bool = True):
        """Send email notification"""
        if not self.enabled:
            logger.info(f"Email would be sent to {to_email}: {subject}")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Send email in thread to not block
            await asyncio.to_thread(self._send_smtp, msg)
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
    
    def _send_smtp(self, msg):
        """Send via SMTP (blocking)"""
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
    
    async def alert_large_loss(self, user_email: str, bot_name: str, loss_amount: float):
        """Alert on large losses"""
        subject = f"🚨 Large Loss Alert - {bot_name}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #ef4444;">⚠️ Large Loss Detected</h2>
            <p>Your bot <strong>{bot_name}</strong> has experienced a significant loss.</p>
            <p><strong>Loss Amount:</strong> R{abs(loss_amount):.2f}</p>
            <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <hr>
            <p>Please review your bot's performance and consider adjusting its parameters.</p>
            <p><a href="https://amarktai.com/dashboard">View Dashboard</a></p>
        </body>
        </html>
        """
        await self.send_email(user_email, subject, body)
    
    async def alert_bot_promotion(self, user_email: str, bot_name: str):
        """Alert when bot promoted to live"""
        subject = f"🎉 Bot Promoted - {bot_name}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #10b981;">✅ Bot Promoted to Live Trading</h2>
            <p>Congratulations! Your bot <strong>{bot_name}</strong> has successfully completed its 7-day paper trading period.</p>
            <p><strong>Status:</strong> Now trading LIVE</p>
            <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <hr>
            <p>Your bot met all promotion criteria:</p>
            <ul>
                <li>✓ 7+ days of paper trading</li>
                <li>✓ 50+ trades executed</li>
                <li>✓ 55%+ win rate</li>
                <li>✓ Less than 10% drawdown</li>
            </ul>
            <p><a href="https://amarktai.com/dashboard">View Dashboard</a></p>
        </body>
        </html>
        """
        await self.send_email(user_email, subject, body)
    
    async def alert_million_achieved(self, user_email: str, user_name: str):
        """Alert when R1M milestone reached"""
        subject = "🎊 MILESTONE ACHIEVED - R1 MILLION!"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; text-align: center;">
            <h1 style="color: #10b981; font-size: 3em;">🎉🎉🎉</h1>
            <h2 style="color: #10b981;">CONGRATULATIONS {user_name.upper()}!</h2>
            <p style="font-size: 2em;">💰 R1,000,000 ACHIEVED 💰</p>
            <p>You've reached your first million rand through automated trading!</p>
            <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <hr>
            <p>This is an incredible milestone. Your patience and strategy have paid off!</p>
            <p><a href="https://amarktai.com/dashboard">View Your Success</a></p>
        </body>
        </html>
        """
        await self.send_email(user_email, subject, body)
    
    async def alert_system_error(self, admin_email: str, error_message: str):
        """Alert admins of system errors"""
        subject = "🚨 System Error - Amarktai"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #ef4444;">⚠️ System Error Detected</h2>
            <p><strong>Error:</strong> {error_message}</p>
            <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <hr>
            <p>Please investigate and resolve this issue.</p>
        </body>
        </html>
        """
        await self.send_email(admin_email, subject, body)
    
    async def send_daily_summary(self, user_email: str, user_name: str, summary_data: dict):
        """Send daily performance summary"""
        subject = f"📊 Daily Summary - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>📊 Daily Performance Summary</h2>
            <p>Hi {user_name},</p>
            <p>Here's your trading summary for today:</p>
            <hr>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Total Profit:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd; color: {'#10b981' if summary_data.get('daily_profit', 0) >= 0 else '#ef4444'};">
                        R{summary_data.get('daily_profit', 0):.2f}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Trades Today:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{summary_data.get('trades_today', 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Win Rate:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{summary_data.get('win_rate', 0):.1f}%</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>Active Bots:</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{summary_data.get('active_bots', 0)}</td>
                </tr>
            </table>
            <hr>
            <p><a href="https://amarktai.com/dashboard">View Full Report</a></p>
        </body>
        </html>
        """
        await self.send_email(user_email, subject, body)


# Global instance
email_alerts = EmailAlertSystem()
