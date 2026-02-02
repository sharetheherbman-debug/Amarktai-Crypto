"""
Email Service - SMTP Email System
Sends daily reports, alerts, and admin broadcasts
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger_config import logger
import os
from typing import List


class EmailService:
    def __init__(self):
        # Load SMTP configuration from environment variables
        self.smtp_server = os.getenv('SMTP_HOST', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.from_name = os.getenv('FROM_NAME', 'Amarktai Network')
        
        # Validate configuration on startup
        self.enabled = self._validate_config()
        
        if not self.enabled:
            logger.warning("⚠️  Email service disabled: Missing SMTP configuration")
            logger.warning("⚠️  Set required SMTP environment variables to enable email notifications")
    
    def _validate_config(self) -> bool:
        """Validate SMTP configuration and return whether email is enabled"""
        if not self.smtp_user or not self.smtp_password:
            return False
        
        if not self.smtp_server:
            logger.error("SMTP_HOST is required but not set")
            return False
        
        logger.info(f"✅ Email service enabled: {self.smtp_server}:{self.smtp_port}")
        return True
    
    async def send_email(self, to_email: str, subject: str, body: str, html: bool = False) -> bool:
        """Send single email"""
        if not self.enabled:
            logger.debug(f"Email disabled, skipping: {subject} to {to_email}")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False
    
    async def send_bulk_email(self, recipients: List[str], subject: str, body: str) -> dict:
        """Send email to multiple recipients"""
        sent = 0
        failed = 0
        
        for email in recipients:
            success = await self.send_email(email, subject, body)
            if success:
                sent += 1
            else:
                failed += 1
        
        return {"sent": sent, "failed": failed}
    
    async def send_daily_report(self, user_email: str, report_data: dict) -> bool:
        """Send daily performance report"""
        subject = f"Amarktai Daily Report - {report_data.get('date', 'Today')}"
        
        body = f"""
Daily Trading Report

Paper Mode:
  Equity: R{report_data.get('paper_equity', 0):,.2f}
  P&L Today: R{report_data.get('paper_pnl_today', 0):,.2f}
  Trades: {report_data.get('paper_trades', 0)}

Live Mode:
  Equity: R{report_data.get('live_equity', 0):,.2f}
  P&L Today: R{report_data.get('live_pnl_today', 0):,.2f}
  Trades: {report_data.get('live_trades', 0)}

Active Bots: {report_data.get('active_bots', 0)}
System Health: {report_data.get('health_score', 0)}/100

Top Performers:
{report_data.get('top_performers', 'N/A')}

---
Amarktai Network
        """
        
        return await self.send_email(user_email, subject, body)


email_service = EmailService()
