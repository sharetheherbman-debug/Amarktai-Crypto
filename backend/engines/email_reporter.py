"""
Email Reporter - Daily Performance Reports
- Sends daily summary emails to users
- Configurable via .env (SMTP settings)
- Includes performance charts, alerts, recommendations
- Gracefully handles missing SMTP credentials
"""

import asyncio
from typing import Dict, List
from datetime import datetime, timezone, timedelta
import logging
import os

import database as db
from engines.audit_logger import audit_logger

logger = logging.getLogger(__name__)

# Try to import email libraries
try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    logger.warning("Email libraries not available")
    EMAIL_AVAILABLE = False

class EmailReporter:
    def __init__(self):
        # SMTP configuration from .env (optional)
        self.smtp_enabled = os.environ.get('SMTP_ENABLED', 'false').lower() == 'true'
        self.smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_username = os.environ.get('SMTP_USERNAME', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.sender_email = os.environ.get('SENDER_EMAIL', 'noreply@amarktai.com')
        
        self.reports_enabled = EMAIL_AVAILABLE and self.smtp_enabled and self.smtp_username
        
        if not self.reports_enabled:
            logger.info("📧 Email reports disabled (SMTP not configured)")
        else:
            logger.info("✅ Email reports enabled")
    
    async def generate_daily_report(self, user_id: str, user_email: str) -> Dict:
        """Generate daily performance report for a user"""
        try:
            # Get yesterday's date range
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get all bots
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).to_list(1000)
            
            # Get yesterday's trades
            trades = await db.trades_collection.find(
                {
                    "user_id": user_id,
                    "timestamp": {
                        "$gte": yesterday_start.isoformat(),
                        "$lte": yesterday_end.isoformat()
                    }
                },
                {"_id": 0}
            ).to_list(10000)
            
            # Get active alerts
            alerts = await db.alerts_collection.find(
                {
                    "user_id": user_id,
                    "dismissed": False
                },
                {"_id": 0}
            ).limit(10).to_list(10)
            
            # Calculate stats
            total_bots = len(bots)
            active_bots = len([b for b in bots if b.get('status') == 'active'])
            live_bots = len([b for b in bots if b.get('mode') == 'live'])
            
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.get('profit_loss', 0) > 0])
            
            total_profit = sum(t.get('profit_loss', 0) for t in trades)
            
            # Get top performers
            bots_sorted = sorted(bots, key=lambda b: b.get('total_profit', 0), reverse=True)
            top_5 = bots_sorted[:5]
            bottom_5 = bots_sorted[-5:]
            
            report = {
                "user_id": user_id,
                "user_email": user_email,
                "report_date": yesterday.strftime("%Y-%m-%d"),
                "summary": {
                    "total_bots": total_bots,
                    "active_bots": active_bots,
                    "live_bots": live_bots,
                    "total_trades_yesterday": total_trades,
                    "winning_trades": winning_trades,
                    "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                    "total_profit_yesterday": total_profit,
                    "total_capital": sum(b.get('current_capital', 0) for b in bots),
                    "total_profit_all_time": sum(b.get('total_profit', 0) for b in bots)
                },
                "top_performers": [
                    {
                        "name": b.get('name'),
                        "profit": b.get('total_profit', 0),
                        "win_rate": (b.get('win_count', 0) / b.get('trades_count', 1)) * 100 if b.get('trades_count', 0) > 0 else 0
                    }
                    for b in top_5
                ],
                "bottom_performers": [
                    {
                        "name": b.get('name'),
                        "profit": b.get('total_profit', 0),
                        "win_rate": (b.get('win_count', 0) / b.get('trades_count', 1)) * 100 if b.get('trades_count', 0) > 0 else 0
                    }
                    for b in bottom_5
                ],
                "active_alerts": [
                    {
                        "type": a.get('type'),
                        "message": a.get('message'),
                        "severity": a.get('severity')
                    }
                    for a in alerts
                ],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Generate daily report error: {e}")
            return {"error": str(e)}
    
    def format_html_report(self, report: Dict) -> str:
        """Format report as HTML email"""
        summary = report.get('summary', {})
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .summary {{ background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .stat {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #3498db; }}
        .stat-label {{ color: #7f8c8d; font-size: 14px; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
        .alert {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 10px 0; }}
        .footer {{ text-align: center; color: #7f8c8d; margin-top: 30px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Amarktai Network (part of Amarktai Network) - Daily Report</h1>
        <p><strong>Date:</strong> {report.get('report_date', 'N/A')}</p>
        
        <div class="summary">
            <h2>📊 Daily Summary</h2>
            <div class="stat">
                <div class="stat-value">{summary.get('total_bots', 0)}</div>
                <div class="stat-label">Total Bots</div>
            </div>
            <div class="stat">
                <div class="stat-value">{summary.get('active_bots', 0)}</div>
                <div class="stat-label">Active Bots</div>
            </div>
            <div class="stat">
                <div class="stat-value">{summary.get('live_bots', 0)}</div>
                <div class="stat-label">Live Trading</div>
            </div>
            <div class="stat">
                <div class="stat-value">{summary.get('total_trades_yesterday', 0)}</div>
                <div class="stat-label">Trades Yesterday</div>
            </div>
            <div class="stat">
                <div class="stat-value">{summary.get('win_rate', 0):.1f}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat">
                <div class="stat-value {'positive' if summary.get('total_profit_yesterday', 0) > 0 else 'negative'}">
                    R{summary.get('total_profit_yesterday', 0):.2f}
                </div>
                <div class="stat-label">Profit Yesterday</div>
            </div>
        </div>
        
        <h2>🏆 Top 5 Performers</h2>
        <table>
            <tr>
                <th>Bot Name</th>
                <th>Total Profit</th>
                <th>Win Rate</th>
            </tr>
            {''.join([f"<tr><td>{b['name']}</td><td class='{'positive' if b['profit'] > 0 else 'negative'}'>R{b['profit']:.2f}</td><td>{b['win_rate']:.1f}%</td></tr>" for b in report.get('top_performers', [])])}
        </table>
        
        <h2>⚠️ Active Alerts</h2>
        {''.join([f"<div class='alert'><strong>{a['severity'].upper()}</strong>: {a['message']}</div>" for a in report.get('active_alerts', [])]) or '<p>No active alerts</p>'}
        
        <div class="footer">
            <p>Amarktai Network (part of Amarktai Network) - Autonomous AI Trading</p>
            <p>This is an automated daily report. Do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    async def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send email via SMTP"""
        if not self.reports_enabled:
            logger.info("📧 Email not sent (SMTP disabled)")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = to_email
            
            # Attach HTML
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False
    
    async def send_daily_report(self, user_id: str, user_email: str) -> Dict:
        """Generate and send daily report"""
        try:
            # Generate report
            report = await self.generate_daily_report(user_id, user_email)
            
            if report.get('error'):
                return {
                    "success": False,
                    "error": report['error']
                }
            
            # Format as HTML
            html_content = self.format_html_report(report)
            
            # Send email
            subject = f"Amarktai Daily Report - {report.get('report_date')}"
            sent = await self.send_email(user_email, subject, html_content)
            
            if sent:
                # Log the action
                await audit_logger.log_event(
                    event_type='daily_report_sent',
                    user_id=user_id,
                    details={
                        "email": user_email,
                        "report_date": report.get('report_date')
                    },
                    severity='info'
                )
            
            return {
                "success": sent,
                "report": report,
                "email_sent": sent
            }
            
        except Exception as e:
            logger.error(f"Send daily report error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_alert_email(self, user_id: str, user_email: str, alert: Dict) -> bool:
        """Send immediate alert email for critical events"""
        if not self.reports_enabled:
            return False
        
        try:
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
        .alert {{ background: #{'#ffebee' if alert.get('severity') == 'critical' else '#fff3cd'}; 
                  border-left: 4px solid #{'#f44336' if alert.get('severity') == 'critical' else '#ffc107'}; 
                  padding: 20px; margin: 20px 0; }}
        h1 {{ color: #{'#c62828' if alert.get('severity') == 'critical' else '#f57c00'}; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚨 {alert.get('severity', 'ALERT').upper()}</h1>
        <div class="alert">
            <h2>{alert.get('type', 'System Alert')}</h2>
            <p>{alert.get('message', 'No details available')}</p>
            <p><small>Time: {alert.get('timestamp', 'Unknown')}</small></p>
        </div>
        <p>Please check your dashboard for more details.</p>
    </div>
</body>
</html>
"""
            
            subject = f"🚨 Amarktai Alert: {alert.get('type', 'System Alert')}"
            return await self.send_email(user_email, subject, html)
            
        except Exception as e:
            logger.error(f"Send alert email error: {e}")
            return False

# Global instance
email_reporter = EmailReporter()
