"""
Autopilot Reinvest Service
Runs daily per-platform reinvestment when bot caps are reached.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import logging

import config
from config.platforms import SUPPORTED_PLATFORMS
from services.reserved_funds_service import reserved_funds_service

logger = logging.getLogger(__name__)


def _platform_bot_limit(platform: str) -> int:
    if config.AUTOPILOT_MAX_BOTS_PER_PLATFORM > 0:
        return config.AUTOPILOT_MAX_BOTS_PER_PLATFORM
    return config.EXCHANGE_BOT_LIMITS.get(platform, config.MAX_TOTAL_BOTS)


class AutopilotReinvestService:
    def __init__(self, database, user_id: str):
        self.db = database
        self.user_id = user_id
        self.events = self.db.autopilot_reinvest_events
        self.timezone = ZoneInfo("Africa/Johannesburg")

    async def get_platform_realized_profit_zar(
        self,
        platform: str,
        since: Optional[datetime] = None
    ) -> float:
        query = {
            "user_id": self.user_id,
            "exchange": platform,
            "status": "closed",
            "profit_loss": {"$exists": True}
        }
        if since:
            query["timestamp"] = {"$gte": since.isoformat()}
        trades = await self.db.trades.find(query).to_list(10000)
        return float(sum(t.get("profit_loss", 0) for t in trades))

    async def run_daily_reinvest(self, platform: str) -> Optional[Dict]:
        eligible, reasons = await self._check_guardrails(platform)
        if not eligible:
            return {"success": False, "blocked_reasons": reasons}

        today_key = self._date_key()
        existing = await self.events.find_one({
            "user_id": self.user_id,
            "platform": platform,
            "date_key": today_key,
            "status": "completed"
        })
        if existing:
            return {"success": False, "blocked_reasons": ["ALREADY_REINVESTED_TODAY"]}

        last_event = await self._get_last_event(platform)
        since = None
        if last_event:
            try:
                since = datetime.fromisoformat(last_event.get("created_at"))
            except Exception:
                since = None

        realized_profit = await self.get_platform_realized_profit_zar(platform, since=since)
        if realized_profit < config.AUTOPILOT_REINVEST_MIN_ZAR:
            return {"success": False, "blocked_reasons": ["PROFIT_BELOW_MINIMUM"]}

        available_balance = await reserved_funds_service.get_available_balance(
            self.user_id, platform, "ZAR"
        )
        reinvest_amount = min(realized_profit, available_balance)
        if reinvest_amount < config.AUTOPILOT_REINVEST_MIN_ZAR:
            return {"success": False, "blocked_reasons": ["INSUFFICIENT_AVAILABLE_FUNDS"]}

        bots = await self.db.bots.find({
            "user_id": self.user_id,
            "exchange": platform,
            "status": {"$ne": "deleted"}
        }).to_list(1000)
        if not bots:
            return {"success": False, "blocked_reasons": ["NO_BOTS_AVAILABLE"]}

        bots.sort(key=lambda bot: bot.get("total_profit", 0), reverse=True)
        top_count = max(1, int(getattr(config, "TOP_PERFORMERS_COUNT", 3)))
        top_bots = bots[: min(top_count, len(bots))]
        allocation_per_bot = reinvest_amount / len(top_bots)

        distribution = {}
        for bot in top_bots:
            bot_id = bot.get("id")
            distribution[bot_id] = round(allocation_per_bot, 2)
            await self.db.bots.update_one(
                {"id": bot_id},
                {
                    "$inc": {
                        "current_capital": allocation_per_bot,
                        "allocated_capital": allocation_per_bot
                    },
                    "$push": {
                        "capital_history": {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "amount": allocation_per_bot,
                            "reason": "autopilot_reinvest",
                            "platform": platform
                        }
                    }
                }
            )

        event_doc = {
            "user_id": self.user_id,
            "platform": platform,
            "date_key": today_key,
            "amount_zar": round(reinvest_amount, 2),
            "distribution": distribution,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed"
        }
        await self.events.update_one(
            {"user_id": self.user_id, "platform": platform, "date_key": today_key},
            {"$setOnInsert": event_doc},
            upsert=True
        )

        return {"success": True, "event": event_doc}

    async def get_reinvest_status(self) -> Dict:
        status = {}
        for platform in SUPPORTED_PLATFORMS:
            status[platform] = await self._get_platform_status(platform)
        return {
            "user_id": self.user_id,
            "enabled": config.ENABLE_AUTOPILOT_REINVEST,
            "min_reinvest_zar": float(config.AUTOPILOT_REINVEST_MIN_ZAR),
            "platforms": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def _get_platform_status(self, platform: str) -> Dict:
        bots_current = await self.db.bots.count_documents({
            "user_id": self.user_id,
            "exchange": platform,
            "status": {"$ne": "deleted"}
        })
        bots_max = _platform_bot_limit(platform)
        last_event = await self._get_last_event(platform)
        last_amount = last_event.get("amount_zar") if last_event else None
        last_date = last_event.get("date_key") if last_event else None
        eligible, reasons = await self._check_guardrails(platform)
        return {
            "bots_current": bots_current,
            "bots_max": bots_max,
            "last_reinvest_date": last_date,
            "last_reinvest_amount": last_amount,
            "next_run": self._next_run_iso(),
            "eligible": eligible,
            "blocked_reasons": reasons
        }

    async def _get_last_event(self, platform: str) -> Dict:
        return await self.events.find_one(
            {"user_id": self.user_id, "platform": platform, "status": "completed"},
            sort=[("created_at", -1)]
        ) or {}

    async def _check_guardrails(self, platform: str) -> Tuple[bool, List[str]]:
        reasons: List[str] = []
        if not config.ENABLE_AUTOPILOT_REINVEST:
            reasons.append("AUTOPILOT_REINVEST_DISABLED")
        if not config.ENABLE_AUTOPILOT:
            reasons.append("AUTOPILOT_DISABLED")
        if not config.ENABLE_TRADING or not (config.ENABLE_PAPER_TRADING or config.ENABLE_LIVE_TRADING):
            reasons.append("TRADING_MODE_DISABLED")

        user = await self.db.users.find_one(
            {"id": self.user_id},
            {"_id": 0, "autopilot_enabled": 1, "daily_loss_lock_active": 1}
        )
        if user and not user.get("autopilot_enabled", False):
            reasons.append("AUTOPILOT_OFF_FOR_USER")
        if user and user.get("daily_loss_lock_active", False):
            reasons.append("DAILY_LOSS_LOCK_ACTIVE")

        modes = await self.db.system_modes.find_one({"user_id": self.user_id}, {"_id": 0})
        if modes and not modes.get("autopilot", False):
            reasons.append("AUTOPILOT_MODE_DISABLED")
        if modes and modes.get("emergencyStop", False):
            reasons.append("EMERGENCY_STOP_ACTIVE")

        bots_current = await self.db.bots.count_documents({
            "user_id": self.user_id,
            "exchange": platform,
            "status": {"$ne": "deleted"}
        })
        if bots_current < _platform_bot_limit(platform):
            reasons.append("BOTS_NOT_MAXED")

        return len(reasons) == 0, reasons

    def _date_key(self) -> str:
        return datetime.now(self.timezone).strftime("%Y-%m-%d")

    def _next_run_iso(self) -> str:
        now = datetime.now(self.timezone)
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        return next_day.astimezone(timezone.utc).isoformat()


class AutopilotReinvestScheduler:
    def __init__(self, database, interval_seconds: int = 3600):
        self.db = database
        self.interval_seconds = interval_seconds
        self.task: Optional[asyncio.Task] = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()

    async def run_once(self):
        if not config.ENABLE_AUTOPILOT_REINVEST:
            return
        users = await self.db.users.find({}, {"_id": 0, "id": 1}).to_list(1000)
        for user in users:
            user_id = user.get("id")
            if not user_id:
                continue
            service = AutopilotReinvestService(self.db, user_id)
            for platform in SUPPORTED_PLATFORMS:
                await service.run_daily_reinvest(platform)

    async def _run_loop(self):
        while self.running:
            try:
                await self.run_once()
            except Exception as exc:
                logger.warning(f"Autopilot reinvest loop error: {exc}")
            await asyncio.sleep(self.interval_seconds)


_reinvest_scheduler: Optional[AutopilotReinvestScheduler] = None


def get_autopilot_reinvest_scheduler(database) -> AutopilotReinvestScheduler:
    global _reinvest_scheduler
    if _reinvest_scheduler is None:
        _reinvest_scheduler = AutopilotReinvestScheduler(database)
    return _reinvest_scheduler
