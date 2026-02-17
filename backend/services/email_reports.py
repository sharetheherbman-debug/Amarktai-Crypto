"""
Email Reports Service - AI-Generated Health & Performance Reports

Generates and sends:
1. Daily Admin Health Report (to amarktainetwork@gmail.com) - AI-powered, short, actionable
2. Daily User Performance Report (to all users) - win/loss, P&L, trade counts

Uses existing email templates with embedded logo.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class EmailReportsService:
    """Service for generating and sending email reports"""
    
    def __init__(self, db, email_service, ai_service=None):
        self.db = db
        self.email_service = email_service
        self.ai_service = ai_service
        self.admin_email = "amarktainetwork@gmail.com"  # Fixed admin email
    
    async def send_daily_admin_health_report(self):
        """
        Generate and send AI-powered admin health report.
        Short, actionable, sent to amarktainetwork@gmail.com ONLY.
        """
        try:
            # Gather system health data
            health_data = await self._gather_health_data()
            
            # Generate AI-powered report (if AI available)
            report_content = await self._generate_admin_report_ai(health_data)
            
            # Build HTML email
            from email_templates.templates import get_base_template
            
            html_body = get_base_template(
                content=report_content,
                title="Daily System Health Report"
            )
            
            # Send to admin email only
            success = await self.email_service.send_email(
                to_email=self.admin_email,
                subject=f"Amarktai System Health Report - {datetime.now(timezone.utc).strftime('%b %d, %Y')}",
                html_body=html_body
            )
            
            if success:
                logger.info(f"✅ Admin health report sent to {self.admin_email}")
            else:
                logger.error(f"❌ Failed to send admin health report to {self.admin_email}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending admin health report: {e}")
            return False
    
    async def send_daily_user_performance_reports(self):
        """
        Send daily performance reports to all users.
        Includes: win/loss, realized P&L, equity change, trade counts.
        """
        try:
            # Get all active users with email
            users = await self.db['users'].find(
                {"email": {"$exists": True, "$ne": ""}},
                {"_id": 0, "id": 1, "email": 1, "name": 1}
            ).to_list(10000)
            
            success_count = 0
            fail_count = 0
            
            for user in users:
                try:
                    # Generate user performance report
                    report_html = await self._generate_user_performance_report(user)
                    
                    if report_html:
                        # Send email
                        success = await self.email_service.send_email(
                            to_email=user['email'],
                            subject=f"Your Daily Trading Report - {datetime.now(timezone.utc).strftime('%b %d, %Y')}",
                            html_body=report_html
                        )
                        
                        if success:
                            success_count += 1
                        else:
                            fail_count += 1
                    
                except Exception as e:
                    logger.error(f"Error sending report to {user.get('email')}: {e}")
                    fail_count += 1
                
                # Rate limit: small delay between emails
                await asyncio.sleep(0.5)
            
            logger.info(f"User performance reports: {success_count} sent, {fail_count} failed")
            return {"success_count": success_count, "fail_count": fail_count}
            
        except Exception as e:
            logger.error(f"Error sending user performance reports: {e}")
            return {"success_count": 0, "fail_count": 0, "error": str(e)}
    
    async def _gather_health_data(self) -> Dict[str, Any]:
        """Gather system health metrics"""
        try:
            now = datetime.now(timezone.utc)
            yesterday = now - timedelta(days=1)
            
            # Get counts
            total_users = await self.db['users'].count_documents({})
            total_bots = await self.db['bots'].count_documents({"status": "active"})
            active_bots = await self.db['bots'].count_documents({
                "status": "active",
                "last_trade_at": {"$gte": yesterday.isoformat()}
            })
            
            # Get trades in last 24h
            trades_24h = await self.db['trades'].count_documents({
                "timestamp": {"$gte": yesterday.isoformat()}
            })
            
            # Get circuit breaker trips
            cb_trips = await self.db['circuit_breaker_state'].count_documents({
                "tripped": True,
                "tripped_at": {"$gte": yesterday.isoformat()}
            })
            
            # Get quarantined bots
            quarantined = await self.db['bots'].count_documents({
                "status": "quarantined"
            })
            
            # Get scheduler status (check if schedulers ran recently)
            ai_scheduler_ok = True  # Would check last run timestamp
            trading_scheduler_ok = True  # Would check if trades are happening
            
            # Get top errors (from ledger or logs)
            top_errors = []  # Would query error logs
            
            # Exchange connectivity
            exchange_status = {
                "luno": "connected",
                "binance": "connected",
                "kucoin": "connected"
            }
            
            return {
                "timestamp": now.isoformat(),
                "counts": {
                    "total_users": total_users,
                    "total_bots": total_bots,
                    "active_bots": active_bots,
                    "trades_24h": trades_24h
                },
                "health_indicators": {
                    "circuit_breaker_trips": cb_trips,
                    "quarantined_bots": quarantined,
                    "ai_scheduler_ok": ai_scheduler_ok,
                    "trading_scheduler_ok": trading_scheduler_ok
                },
                "exchange_status": exchange_status,
                "top_errors": top_errors
            }
            
        except Exception as e:
            logger.error(f"Error gathering health data: {e}")
            return {"error": str(e)}
    
    async def _generate_admin_report_ai(self, health_data: Dict[str, Any]) -> str:
        """Generate AI-powered admin report HTML"""
        try:
            # Determine system status
            is_healthy = True
            issues = []
            
            cb_trips = health_data.get('health_indicators', {}).get('circuit_breaker_trips', 0)
            quarantined = health_data.get('health_indicators', {}).get('quarantined_bots', 0)
            trades_24h = health_data.get('counts', {}).get('trades_24h', 0)
            
            if cb_trips > 5:
                is_healthy = False
                issues.append(f"⚠️ {cb_trips} circuit breaker trips in 24h")
            
            if quarantined > 10:
                is_healthy = False
                issues.append(f"⚠️ {quarantined} bots quarantined")
            
            if trades_24h == 0:
                is_healthy = False
                issues.append("⚠️ No trades executed in 24h")
            
            status_emoji = "✅" if is_healthy else "⚠️"
            status_text = "System OK" if is_healthy else "Attention Required"
            status_color = "#10b981" if is_healthy else "#f59e0b"
            
            # Generate AI summary if available
            ai_summary = ""
            if self.ai_service and not is_healthy:
                try:
                    # Call AI to analyze issues and recommend fixes
                    prompt = f"""Analyze this system health data and provide brief actionable recommendations:
                    
Issues detected:
{chr(10).join(issues)}

Health data:
- Active bots: {health_data.get('counts', {}).get('active_bots', 0)}
- Total users: {health_data.get('counts', {}).get('total_users', 0)}
- Trades (24h): {trades_24h}

Provide 2-3 short bullet points with recommended fixes."""

                    ai_response = await self.ai_service.generate_completion(prompt, max_tokens=150)
                    ai_summary = f"""
                    <div style="background-color: #1e293b; border-left: 4px solid #60a5fa; padding: 16px; margin-top: 24px; border-radius: 4px;">
                        <h4 style="margin: 0 0 12px 0; color: #60a5fa; font-size: 14px; font-weight: 600;">AI Recommendations</h4>
                        <div style="color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                            {ai_response}
                        </div>
                    </div>
                    """
                except Exception as e:
                    logger.warning(f"AI summary generation failed: {e}")
            
            # Build HTML report
            content = f"""
            <div style="text-align: center; margin-bottom: 32px;">
                <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                    Daily System Health Report
                </h2>
                <p style="margin: 0; color: #94a3b8; font-size: 14px;">
                    {datetime.now(timezone.utc).strftime('%B %d, %Y')}
                </p>
            </div>
            
            <div style="background: linear-gradient(135deg, {status_color}22 0%, {status_color}11 100%); border: 1px solid {status_color}44; border-radius: 8px; padding: 20px; margin-bottom: 24px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 8px;">{status_emoji}</div>
                <h3 style="margin: 0 0 4px 0; color: #ffffff; font-size: 20px; font-weight: 600;">
                    {status_text}
                </h3>
            </div>
            
            <div style="margin-bottom: 24px;">
                <h4 style="margin: 0 0 16px 0; color: #ffffff; font-size: 16px; font-weight: 600;">System Metrics</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Active Bots</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{health_data.get('counts', {}).get('active_bots', 0)}/{health_data.get('counts', {}).get('total_bots', 0)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Trades (24h)</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{trades_24h}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Circuit Breaker Trips</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{cb_trips}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; color: #94a3b8; font-size: 14px;">Quarantined Bots</td>
                        <td style="padding: 12px 0; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{quarantined}</td>
                    </tr>
                </table>
            </div>
            
            {"".join([f'<div style="background-color: #1e293b; border-left: 4px solid #f59e0b; padding: 12px 16px; margin-bottom: 8px; border-radius: 4px;"><div style="color: #fbbf24; font-size: 14px;">{issue}</div></div>' for issue in issues])}
            
            {ai_summary}
            
            <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid #1e293b; text-align: center;">
                <p style="margin: 0; color: #64748b; font-size: 13px;">
                    This is an automated report. Login to dashboard for detailed analysis.
                </p>
            </div>
            """
            
            return content
            
        except Exception as e:
            logger.error(f"Error generating admin report: {e}")
            return f"<p>Error generating report: {str(e)}</p>"
    
    async def _generate_user_performance_report(self, user: Dict[str, Any]) -> Optional[str]:
        """Generate user performance report HTML"""
        try:
            user_id = user['id']
            user_name = user.get('name', 'Trader')
            
            # Get user's bots
            bots = await self.db['bots'].find(
                {"user_id": user_id, "status": {"$ne": "deleted"}},
                {"_id": 0}
            ).to_list(1000)
            
            if not bots:
                return None  # No bots, skip report
            
            # Aggregate stats
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            
            total_trades_24h = 0
            winning_trades = 0
            losing_trades = 0
            total_profit = 0.0
            total_equity = 0.0
            paper_bots = 0
            live_bots = 0
            
            for bot in bots:
                if bot.get('trading_mode') == 'paper':
                    paper_bots += 1
                else:
                    live_bots += 1
                
                total_equity += bot.get('current_capital', 0)
                
                # Count 24h trades for this bot
                bot_trades = await self.db['trades'].find({
                    "bot_id": bot['id'],
                    "timestamp": {"$gte": yesterday.isoformat()}
                }).to_list(1000)
                
                total_trades_24h += len(bot_trades)
                
                for trade in bot_trades:
                    pnl = trade.get('profit_loss', 0)
                    if pnl > 0:
                        winning_trades += 1
                        total_profit += pnl
                    elif pnl < 0:
                        losing_trades += 1
                        total_profit += pnl
            
            win_rate = (winning_trades / total_trades_24h * 100) if total_trades_24h > 0 else 0
            
            # Build HTML
            from email_templates.templates import get_base_template
            
            # Determine currency based on primary exchange
            currency_symbol = "R"  # Default ZAR for Luno
            primary_exchange = bots[0].get('exchange', 'luno').lower() if bots else 'luno'
            if primary_exchange in ['binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']:
                currency_symbol = "$"  # USD for international exchanges
            
            profit_color = "#10b981" if total_profit >= 0 else "#ef4444"
            profit_sign = "+" if total_profit >= 0 else ""
            
            content = f"""
            <div style="text-align: center; margin-bottom: 32px;">
                <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                    Hey {user_name}! 👋
                </h2>
                <p style="margin: 0; color: #94a3b8; font-size: 14px;">
                    Here's your trading performance for {datetime.now(timezone.utc).strftime('%B %d, %Y')}
                </p>
            </div>
            
            <div style="background: linear-gradient(135deg, #1e40af22 0%, #1e3a8a11 100%); border: 1px solid #1e40af44; border-radius: 8px; padding: 24px; margin-bottom: 24px;">
                <div style="text-align: center;">
                    <div style="color: #94a3b8; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">24h P&L</div>
                    <div style="color: {profit_color}; font-size: 36px; font-weight: 700; margin-bottom: 4px;">
                        {profit_sign}{currency_symbol}{abs(total_profit):.2f}
                    </div>
                    <div style="color: #64748b; font-size: 14px;">
                        {winning_trades}W / {losing_trades}L · {win_rate:.1f}% Win Rate
                    </div>
                </div>
            </div>
            
            <div style="margin-bottom: 24px;">
                <h4 style="margin: 0 0 16px 0; color: #ffffff; font-size: 16px; font-weight: 600;">Account Summary</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Total Equity</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{currency_symbol}{total_equity:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Trades (24h)</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{total_trades_24h}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 14px;">Active Bots</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #1e293b; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">{len(bots)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; color: #94a3b8; font-size: 14px;">Mode</td>
                        <td style="padding: 12px 0; color: #ffffff; font-size: 14px; text-align: right; font-weight: 600;">
                            {f'{paper_bots} Paper' if paper_bots > 0 else ''}{' · ' if paper_bots > 0 and live_bots > 0 else ''}{f'{live_bots} Live' if live_bots > 0 else ''}
                        </td>
                    </tr>
                </table>
            </div>
            
            <div style="background-color: #1e293b; border-radius: 8px; padding: 20px; text-align: center;">
                <p style="margin: 0 0 16px 0; color: #cbd5e1; font-size: 14px;">
                    {"🎉 Great work! Keep it up!" if total_profit > 0 else "💪 Every trader has tough days. Stay disciplined!"}
                </p>
                <a href="https://www.amarktai.online/dashboard" style="display: inline-block; background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%); color: #ffffff; text-decoration: none; padding: 12px 32px; border-radius: 6px; font-size: 14px; font-weight: 600;">
                    View Full Dashboard
                </a>
            </div>
            """
            
            return get_base_template(content, f"Daily Report - {user_name}")
            
        except Exception as e:
            logger.error(f"Error generating user report for {user.get('id')}: {e}")
            return None


# Singleton instance
_email_reports_service = None

def get_email_reports_service(db, email_service, ai_service=None):
    """Get or create email reports service singleton"""
    global _email_reports_service
    if _email_reports_service is None:
        _email_reports_service = EmailReportsService(db, email_service, ai_service)
    return _email_reports_service
