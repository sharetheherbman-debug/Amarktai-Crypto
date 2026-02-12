"""
Daily Admin Report Scheduler
Sends a brief letter to admin users (guarded by ENABLE_DAILY_REPORTS).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta, time
from email.mime.text import MIMEText
import smtplib
from typing import Optional

import database as db
from services.ledger_service import get_ledger_service

logger = logging.getLogger(__name__)


class DailyAdminReporter:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_from = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.report_time = os.getenv("DAILY_REPORT_TIME", "08:00")

    async def start(self):
        if self._task:
            return
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("📧 Daily admin reporter started")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("📧 Daily admin reporter stopped")

    async def _schedule_loop(self):
        while self._running:
            if not os.getenv("ENABLE_DAILY_REPORTS", "false").lower() == "true":
                await asyncio.sleep(3600)
                continue
            now = datetime.now(timezone.utc)
            target_hour, target_minute = map(int, self.report_time.split(":"))
            target = datetime.combine(now.date(), time(target_hour, target_minute)).replace(tzinfo=timezone.utc)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info("📧 Next admin report in %.1f hours", wait_seconds / 3600)
            await asyncio.sleep(wait_seconds)
            await self.send_admin_reports()

    async def send_admin_reports(self):
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP not configured; skipping admin daily report")
            return

        admins = await db.users_collection.find(
            {"is_admin": True},
            {"_id": 0, "id": 1, "email": 1, "name": 1}
        ).to_list(200)

        for admin in admins:
            if not admin.get("email"):
                continue
            try:
                letter = await self._build_letter(admin["id"], admin.get("name") or "Admin")
                subject = f"Amarktai Daily Admin Letter - {datetime.now(timezone.utc).strftime('%B %d, %Y')}"
                await self._send_email(admin["email"], subject, letter)
            except Exception as e:
                logger.error(f"Admin report send failed ({admin.get('email')}): {e}")

    async def _build_letter(self, user_id: str, name: str) -> str:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        trades = await db.trades_collection.find(
            {"user_id": user_id, "timestamp": {"$gte": today_start.isoformat()}},
            {"_id": 0, "net_pnl": 1, "profit_loss": 1, "fees_total": 1, "slippage_cost": 1}
        ).to_list(10000)

        wins = sum(1 for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
        losses = sum(1 for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) < 0)
        pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)
        fees_today = sum(t.get("fees_total", 0) for t in trades)
        slippage_today = sum(t.get("slippage_cost", 0) for t in trades)

        active_bots = await db.bots_collection.count_documents({"user_id": user_id, "status": "active"})

        errors = await db.alerts_collection.count_documents({
            "user_id": user_id,
            "severity": {"$in": ["error", "critical"]},
            "timestamp": {"$gte": today_start.isoformat()}
        })

        drawdown_current = None
        drawdown_max = None
        try:
            ledger = get_ledger_service(db.db)
            current_dd, max_dd = await ledger.compute_drawdown(user_id)
            drawdown_current = round(current_dd * 100, 2)
            drawdown_max = round(max_dd * 100, 2)
        except Exception as e:
            logger.warning(f"Drawdown unavailable for admin report: {e}")

        last_learning = await db.learning_runs_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "summary": 1, "completed_at": 1, "report": 1, "strategy_version_id": 1, "run_id": 1},
            sort=[("completed_at", -1)]
        )

        learning_changes = []
        if last_learning and last_learning.get("run_id"):
            learning_changes = await db.learning_changes_collection.find(
                {"run_id": last_learning["run_id"]},
                {"_id": 0, "parameter": 1, "old_value": 1, "new_value": 1}
            ).to_list(20)

        user_doc = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "daily_loss_lock_active": 1})
        quarantined = await db.bots_collection.count_documents({"user_id": user_id, "status": "quarantined"})
        safety_status = "clear"
        if user_doc and user_doc.get("daily_loss_lock_active"):
            safety_status = "daily loss lock active"
        if quarantined > 0:
            safety_status = f"{safety_status}, {quarantined} bot(s) quarantined" if safety_status != "clear" else f"{quarantined} bot(s) quarantined"

        changes_lines = ["- No parameter changes applied."] if not learning_changes else [
            f"- {c['parameter']}: {c['old_value']} → {c['new_value']}" for c in learning_changes
        ]

        learning_summary = last_learning.get("summary") if last_learning else "No learning run recorded last night."
        next_steps = learning_summary or "Maintain current parameters."
        report_letter = (last_learning or {}).get("report", {}).get("letter")

        letter = (
            f"Good morning {name},\n\n"
            f"Here is your Amarktai daily letter:\n\n"
            f"Trades today: {len(trades)} (wins: {wins}, losses: {losses})\n"
            f"PnL today: R{pnl:.2f}\n"
            f"Costs today: fees R{fees_today:.2f}, slippage R{slippage_today:.2f}\n"
            f"Active bots: {active_bots}\n"
            f"Errors today: {errors}\n"
        )
        if drawdown_current is not None:
            letter += f"Drawdown: {drawdown_current:.2f}% (max {drawdown_max:.2f}%)\n"

        letter += (
            "\nWhat changed overnight:\n"
            + "\n".join(changes_lines)
            + "\n\nWhat the system learned:\n"
            + f"- {learning_summary}\n"
        )
        if report_letter:
            letter += f"\nLearning report excerpt:\n{report_letter}\n"
        letter += (
            "\nSafety status:\n"
            f"- {safety_status}\n\n"
            "Next plan for tomorrow:\n"
            f"- {next_steps}\n\n"
            "Have a focused trading day.\n"
        )
        return letter

    async def _send_email(self, to_email: str, subject: str, body: str):
        msg = MIMEText(body, "plain")
        msg["From"] = self.smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info("📧 Admin daily letter sent to %s", to_email)
        except smtplib.SMTPAuthenticationError as auth_error:
            logger.error("SMTP authentication failed for admin report: %s", auth_error)
            raise
        except smtplib.SMTPConnectError as connect_error:
            logger.error("SMTP connection failed for admin report: %s", connect_error)
            raise
        except smtplib.SMTPServerDisconnected as disconnect_error:
            logger.error("SMTP disconnected while sending admin report: %s", disconnect_error)
            raise
        except smtplib.SMTPException as smtp_error:
            logger.error("SMTP error sending admin report: %s", smtp_error)
            raise


daily_admin_reporter = DailyAdminReporter()
