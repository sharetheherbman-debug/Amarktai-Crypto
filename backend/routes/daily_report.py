"""
SMTP Daily Report System
Sends automated daily email reports with trading performance, bot status, and errors
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import logging
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import os

from auth import get_current_user, is_admin
from database import get_database
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class DailyReportService:
    """Handles generation and sending of daily reports"""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_from = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.report_time = os.getenv("DAILY_REPORT_TIME", "08:00")  # 8 AM by default
        self.scheduler_task = None
        
    async def generate_report_html(self, user_id: str) -> str:
        """Generate HTML report for a user using LEDGER DATA
        
        This method prioritizes ledger data as the single source of truth for all metrics.
        If ledger data is unavailable, it falls back to bot-based calculations to ensure
        reports can always be generated.
        
        Ledger-based metrics include:
        - Total equity (from compute_equity)
        - Realized PnL (from compute_realized_pnl)  
        - Fees paid (from compute_fees_paid)
        - Drawdown (from compute_drawdown)
        - Yesterday's profit (from profit_series)
        
        Args:
            user_id: User ID to generate report for
            
        Returns:
            HTML formatted report or None if user not found
        """
        try:
            # Get user info
            user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
            if not user:
                return None
            
            user_email = user.get("email", "Unknown")
            user_name = user.get("name", user_email)
            
            # Get yesterday's date range
            now = datetime.now(timezone.utc)
            yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            max_dd = 0.0
            
            # Get all bots
            bots_cursor = db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}})
            bots = await bots_cursor.to_list(1000)
            
            active_bots = [b for b in bots if b.get("status") == "active"]
            paused_bots = [b for b in bots if b.get("status") == "paused"]
            stopped_bots = [b for b in bots if b.get("status") == "stopped"]
            
            # NEW: Get metrics from LEDGER (single source of truth)
            try:
                import database as db
                from services.ledger_service import get_ledger_service
                
                db = await get_database()
                ledger = get_ledger_service(db)
                
                # Get ledger-based metrics
                total_equity = await ledger.compute_equity(user_id)
                realized_pnl = await ledger.compute_realized_pnl(user_id)
                total_fees = await ledger.compute_fees_paid(user_id)
                current_dd, max_dd = await ledger.compute_drawdown(user_id)
                stats = await ledger.get_stats(user_id)
                
                # Get yesterday's profit from ledger
                yesterday_series = await ledger.profit_series(user_id, period="daily", limit=1)
                net_profit = yesterday_series["values"][0] if yesterday_series["values"] else 0.0
                
                # Calculate yesterday's stats from ledger fills
                yesterday_fills = await ledger.get_fills(
                    user_id,
                    since=yesterday_start,
                    until=yesterday_end
                )
                
                total_trades = len(yesterday_fills)
                # Simplified: count buy fills as trades (in reality need to match buy/sell pairs)
                winning_trades = 0
                losing_trades = 0
                
                drawdown_percent = current_dd * 100
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
                
                # Use ledger data
                total_profit = realized_pnl
                
            except Exception as ledger_error:
                # Fallback to bot-based calculation if ledger fails
                logger.warning(f"Ledger data unavailable, using bot-based calculation: {ledger_error}")
                
                # Get yesterday's trades (fallback)
                trades_cursor = db.trades_collection.find({
                    "user_id": user_id,
                    "created_at": {
                        "$gte": yesterday_start.isoformat(),
                        "$lt": yesterday_end.isoformat()
                    }
                })
                trades = await trades_cursor.to_list(10000)
                
                # Calculate stats
                total_trades = len(trades)
                winning_trades = len([t for t in trades if t.get("realized_profit", 0) > 0])
                losing_trades = len([t for t in trades if t.get("realized_profit", 0) < 0])
                
                total_profit = sum(t.get("realized_profit", 0.0) for t in trades)
                total_fees = sum(t.get("fees", 0.0) for t in trades)
                net_profit = total_profit - total_fees
                
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
                
                # Calculate current portfolio value
                total_equity = sum(b.get("current_capital", b.get("initial_capital", 0.0)) for b in bots)
                
                # Calculate max drawdown (simplified)
                funded_capital = user.get("funded_capital", total_equity)
                drawdown_percent = ((funded_capital - total_equity) / funded_capital * 100) if funded_capital > 0 else 0.0
                max_dd = drawdown_percent / 100
            
            # Get alerts/errors from yesterday
            alerts_cursor = db.alerts_collection.find({
                "user_id": user_id,
                "created_at": {
                    "$gte": yesterday_start.isoformat(),
                    "$lt": yesterday_end.isoformat()
                },
                "severity": {"$in": ["error", "critical"]}
            })
            alerts = await alerts_cursor.to_list(100)

            last_learning = await db.learning_runs_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "summary": 1, "report": 1, "run_id": 1},
                sort=[("completed_at", -1)]
            )
            learning_changes = []
            if last_learning and last_learning.get("run_id"):
                learning_changes = await db.learning_changes_collection.find(
                    {"run_id": last_learning["run_id"]},
                    {"_id": 0, "parameter": 1, "old_value": 1, "new_value": 1}
                ).to_list(20)

            change_lines = ["- No parameter changes applied."] if not learning_changes else [
                f"- {c['parameter']}: {c['old_value']} → {c['new_value']}" for c in learning_changes
            ]
            safety_notes = []
            if drawdown_percent is not None:
                safety_notes.append(f"Drawdown: {drawdown_percent:.2f}% (max {max_dd * 100:.2f}%)")
            if alerts:
                safety_notes.append(f"Alerts: {len(alerts)} critical/error")
            safety_status = "; ".join(safety_notes) if safety_notes else "All safety checks nominal."

            learning_summary = last_learning.get("summary") if last_learning else "No learning run recorded last night."
            report_letter = (last_learning or {}).get("report", {}).get("letter")

            letter = (
                f"Good morning {user_name},\n\n"
                "Here is your Amarktai daily letter:\n\n"
                f"Wins/Losses yesterday: {winning_trades}/{losing_trades} across {total_trades} trades\n"
                f"Net profit yesterday: R{net_profit:.2f}\n"
                f"Fees paid yesterday: R{total_fees:.2f}\n"
                f"Total equity: R{total_equity:.2f}\n"
                f"Active bots: {len(active_bots)} (paused: {len(paused_bots)}, stopped: {len(stopped_bots)})\n\n"
                "What changed overnight:\n"
                + "\n".join(change_lines)
                + "\n\nWhat the system learned:\n"
                f"- {learning_summary}\n"
            )
            if report_letter:
                letter += f"\nLearning report excerpt:\n{report_letter}\n"
            letter += (
                "\nSafety status:\n"
                f"- {safety_status}\n\n"
                "Next plan for tomorrow:\n"
                f"- {learning_summary}\n\n"
                "Have a focused trading day.\n"
            )
            return letter
            
            # Generate HTML
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .section {{
            background: #f8f9fa;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
        .warning {{ color: #ffc107; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #667eea;
            color: white;
        }}
        .footer {{
            text-align: center;
            color: #666;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Amarktai Network Daily Report</h1>
        <p>{user_name} | {yesterday_start.strftime("%B %d, %Y")}</p>
    </div>
    
    <div class="section">
        <h2>📊 Yesterday's Performance</h2>
        <div class="metric">
            <div class="metric-label">Trades</div>
            <div class="metric-value">{total_trades}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value {'positive' if win_rate >= 50 else 'negative'}">{win_rate:.1f}%</div>
        </div>
        <div class="metric">
            <div class="metric-label">Profit</div>
            <div class="metric-value {'positive' if net_profit > 0 else 'negative'}">R {net_profit:.2f}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Fees</div>
            <div class="metric-value">R {total_fees:.2f}</div>
        </div>
    </div>
    
    <div class="section">
        <h2>💼 Portfolio Status</h2>
        <div class="metric">
            <div class="metric-label">Total Equity</div>
            <div class="metric-value">R {total_equity:.2f}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Drawdown</div>
            <div class="metric-value {'warning' if drawdown_percent > 10 else ''}">{drawdown_percent:.2f}%</div>
        </div>
    </div>
    
    <div class="section">
        <h2>🤖 Bot Status</h2>
        <table>
            <tr>
                <th>Status</th>
                <th>Count</th>
            </tr>
            <tr>
                <td>Active</td>
                <td class="positive"><strong>{len(active_bots)}</strong></td>
            </tr>
            <tr>
                <td>Paused</td>
                <td class="warning"><strong>{len(paused_bots)}</strong></td>
            </tr>
            <tr>
                <td>Stopped</td>
                <td class="negative"><strong>{len(stopped_bots)}</strong></td>
            </tr>
            <tr>
                <td><strong>Total</strong></td>
                <td><strong>{len(bots)}</strong></td>
            </tr>
        </table>
    </div>
    """
            
            # Add alerts section if there are any
            if alerts:
                html += """
    <div class="section">
        <h2>⚠️ Alerts & Errors</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>Severity</th>
                <th>Message</th>
            </tr>
"""
                for alert in alerts[:10]:  # Limit to 10 most recent
                    severity = alert.get("severity", "info")
                    timestamp = alert.get("created_at", "")
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        time_str = dt.strftime("%H:%M")
                    except:
                        time_str = "Unknown"
                    
                    html += f"""
            <tr>
                <td>{time_str}</td>
                <td class="{'negative' if severity == 'critical' else 'warning'}">{severity.upper()}</td>
                <td>{alert.get('message', 'No details')[:100]}</td>
            </tr>
"""
                html += """
        </table>
    </div>
"""
            
            # Footer
            html += f"""
    <div class="footer">
        <p>Amarktai Network Trading Platform | Generated {now.strftime("%Y-%m-%d %H:%M UTC")}</p>
        <p>This is an automated report. Do not reply to this email.</p>
    </div>
</body>
</html>
"""
            
            return html
            
        except Exception as e:
            logger.error(f"Generate report HTML error: {e}")
            return None
    
    async def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send email via SMTP
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML email body
            
        Returns:
            True if sent successfully
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not configured - skipping email")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Attach plain text content
            text_part = MIMEText(html_content, 'plain')
            msg.attach(text_part)
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Daily report sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Send email error: {e}")
            return False
    
    async def send_daily_reports(self):
        """Send daily reports to all users"""
        try:
            # Get all users
            users_cursor = db.users_collection.find({}, {"_id": 0})
            users = await users_cursor.to_list(10000)
            
            logger.info(f"📧 Sending daily reports to {len(users)} users...")
            
            sent_count = 0
            failed_count = 0
            
            for user in users:
                user_id = user.get("id")
                user_email = user.get("email")
                
                if not user_email:
                    continue
                
                # Generate report
                html = await self.generate_report_html(user_id)
                if not html:
                    failed_count += 1
                    continue
                
                # Send email
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)
                subject = f"Amarktai Daily Report - {yesterday.strftime('%B %d, %Y')}"
                
                if await self.send_email(user_email, subject, html):
                    sent_count += 1
                else:
                    failed_count += 1
                
                # Rate limit
                await asyncio.sleep(1)
            
            logger.info(f"✅ Daily reports complete: {sent_count} sent, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Send daily reports error: {e}")
    
    async def schedule_daily_reports(self):
        """Run scheduler for daily reports"""
        while True:
            try:
                # Get current time
                now = datetime.now(timezone.utc)
                
                # Parse target time (e.g., "08:00")
                target_hour, target_minute = map(int, self.report_time.split(":"))
                
                # Calculate next run time
                target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                
                if target_time < now:
                    # If target time has passed today, schedule for tomorrow
                    target_time += timedelta(days=1)
                
                # Calculate wait time
                wait_seconds = (target_time - now).total_seconds()
                
                logger.info(f"📅 Next daily report scheduled for {target_time.isoformat()} (in {wait_seconds/3600:.1f} hours)")
                
                # Wait until target time
                await asyncio.sleep(wait_seconds)
                
                # Send reports
                await self.send_daily_reports()
                
            except Exception as e:
                logger.error(f"Daily report scheduler error: {e}")
                # Wait 1 hour before retrying
                await asyncio.sleep(3600)
    
    def start(self):
        """Start the daily report scheduler"""
        if self.scheduler_task is None:
            self.scheduler_task = asyncio.create_task(self.schedule_daily_reports())
            logger.info("📧 Daily report scheduler started")
    
    def stop(self):
        """Stop the daily report scheduler"""
        if self.scheduler_task:
            self.scheduler_task.cancel()
            self.scheduler_task = None
            logger.info("📧 Daily report scheduler stopped")


# Global instance
daily_report_service = DailyReportService()


@router.post("/daily/send-test")
async def send_test_report(user_id: str = Depends(get_current_user)):
    """Send a test daily report to the current user
    
    Admin endpoint to test email functionality
    
    Args:
        user_id: Current user ID from auth
        
    Returns:
        Test result
    """
    try:
        # Get user email
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_email = user.get("email")
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not configured")
        
        # Generate report
        html = await daily_report_service.generate_report_html(user_id)
        if not html:
            raise HTTPException(status_code=500, detail="Failed to generate report")
        
        # Send test email
        subject = f"[TEST] Amarktai Daily Report - {datetime.now(timezone.utc).strftime('%B %d, %Y')}"
        
        success = await daily_report_service.send_email(user_email, subject, html)
        
        if success:
            return {
                "success": True,
                "message": f"Test report sent to {user_email}",
                "email": user_email
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email - check SMTP configuration")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send test report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daily/send-all")
async def send_all_reports(user_id: str = Depends(get_current_user)):
    """Send daily reports to all users now (admin only)
    
    Args:
        user_id: Current user ID from auth (must be admin)
        
    Returns:
        Send status
    """
    try:
        # Verify admin
        if not await is_admin(user_id):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Send reports in background
        asyncio.create_task(daily_report_service.send_daily_reports())
        
        return {
            "success": True,
            "message": "Daily reports are being sent to all users"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send all reports error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily/config")
async def get_report_config():
    """Get daily report configuration
    
    Returns:
        Configuration details
    """
    return {
        "success": True,
        "config": {
            "enabled": bool(daily_report_service.smtp_user and daily_report_service.smtp_password),
            "report_time": daily_report_service.report_time,
            "smtp_host": daily_report_service.smtp_host,
            "smtp_port": daily_report_service.smtp_port,
            "smtp_from": daily_report_service.smtp_from,
            "smtp_configured": bool(daily_report_service.smtp_user)
        }
    }


@router.post("/admin/reinvest/trigger")
async def trigger_manual_reinvestment(
    data: dict = None,
    user_id: str = Depends(get_current_user)
):
    """Manually trigger daily reinvestment cycle (admin only)
    
    Args:
        data: Optional dict with "user_id" key to run for specific user
        user_id: Current user ID from auth (must be admin)
        
    Returns:
        Reinvestment cycle results
    """
    try:
        # Verify admin
        if not await is_admin(user_id):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get reinvestment service
        from services.daily_reinvestment import get_reinvestment_service
        import database as db
        
        db = await get_database()
        reinvest_service = get_reinvestment_service(db)
        
        # Get target user if specified
        target_user_id = data.get("user_id") if data else None
        
        # Trigger cycle
        result = await reinvest_service.trigger_manual_cycle(target_user_id)
        
        return {
            "success": True,
            "message": "Reinvestment cycle triggered",
            "result": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual reinvestment trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/reinvest/status")
async def get_reinvestment_status(
    user_id: str = Depends(get_current_user)
):
    """Get daily reinvestment scheduler status (admin only)"""
    try:
        # Verify admin
        if not await is_admin(user_id):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get reinvestment service
        from services.daily_reinvestment import get_reinvestment_service
        import database as db
        
        db = await get_database()
        reinvest_service = get_reinvestment_service(db)
        
        return {
            "success": True,
            "is_running": reinvest_service.is_running,
            "daily_time": reinvest_service.daily_time,
            "last_run": reinvest_service.last_run.isoformat() if reinvest_service.last_run else None,
            "config": {
                "reinvest_threshold": reinvest_service.reinvest_threshold,
                "reinvest_top_n": reinvest_service.reinvest_top_n,
                "reinvest_percentage": reinvest_service.reinvest_percentage
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get reinvestment status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
