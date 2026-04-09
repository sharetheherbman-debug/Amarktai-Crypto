"""
Autopilot Growth Service
Handles profit milestone tracking and autonomous bot spawning per platform.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import logging

import config
import database as db
from config.platforms import SUPPORTED_PLATFORMS, PLATFORM_CONFIG
from engines.bot_spawner import bot_spawner
from services.reserved_funds_service import reserved_funds_service
from services.provider_registry import ProviderStatus

logger = logging.getLogger(__name__)


def _normalize_key_status(status: Optional[str]) -> str:
    if not status:
        return ProviderStatus.NOT_CONFIGURED.value
    normalized = status.lower()
    legacy_map = {
        ProviderStatus.SAVED_UNTESTED.value: ProviderStatus.CONFIGURED_UNTESTED.value,
        ProviderStatus.TEST_OK.value: ProviderStatus.CONFIGURED_VALID.value,
        ProviderStatus.TEST_FAILED.value: ProviderStatus.CONFIGURED_INVALID.value
    }
    return legacy_map.get(normalized, normalized)


def _exchange_reserved_from_summary(summary: Dict, platform: str) -> float:
    """Extract reserved capital for a platform from reserved summary payload."""
    if not isinstance(summary, dict):
        return 0.0
    by_exchange = summary.get("by_exchange") or {}
    exchange_data = by_exchange.get(platform) or {}
    return float(exchange_data.get("total_reserved", 0) or 0)


def _platform_bot_limit(platform: str) -> int:
    if config.AUTOPILOT_MAX_BOTS_PER_PLATFORM > 0:
        return config.AUTOPILOT_MAX_BOTS_PER_PLATFORM
    return config.EXCHANGE_BOT_LIMITS.get(platform, config.MAX_TOTAL_BOTS)


def _platform_display_name(platform: str) -> str:
    return PLATFORM_CONFIG.get(platform, {}).get("display_name", platform.capitalize())


class AutopilotGrowthService:
    def __init__(self, database, user_id: str):
        self.db = database
        self.user_id = user_id
        self.milestones = self.db.autopilot_milestones

    async def get_platform_realized_profit_zar(self, platform: str) -> float:
        try:
            trades = await self.db.trades.find({
                "user_id": self.user_id,
                "exchange": platform,
                "status": "closed",
                "profit_loss": {"$exists": True}
            }).to_list(10000)
            return float(sum(t.get("profit_loss", 0) for t in trades))
        except Exception as exc:
            logger.warning(f"Profit lookup failed for {platform}: {exc}")
            return 0.0

    async def get_next_milestone(self, platform: str) -> int:
        last = await self._get_last_milestone_index(platform)
        return last + 1

    async def try_trigger_spawn(self, platform: str) -> Optional[str]:
        threshold = float(config.AUTOPILOT_PROFIT_MILESTONE_ZAR)
        if threshold <= 0:
            return None

        eligible, reasons = await self._check_guardrails(platform)
        if not eligible:
            logger.info(f"Autopilot growth blocked for {platform}: {', '.join(reasons)}")
            return None

        profit = await self.get_platform_realized_profit_zar(platform)
        next_milestone = await self.get_next_milestone(platform)
        target_profit = next_milestone * threshold

        if profit < target_profit:
            return None

        reservation = await self.milestones.update_one(
            {"user_id": self.user_id, "platform": platform, "milestone_index": next_milestone},
            {"$setOnInsert": {
                "user_id": self.user_id,
                "platform": platform,
                "milestone_index": next_milestone,
                "profit_threshold_zar": threshold,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "realized_profit_zar": round(profit, 2)
            }},
            upsert=True
        )

        if reservation.upserted_id is None:
            logger.info(f"Milestone {next_milestone} already recorded for {self.user_id} on {platform}")
            return None

        # Calculate spawn capital proportional to excess profit
        # Allocate 30% of profit above threshold, with minimum of NEW_BOT_CAPITAL
        base_capital = float(config.NEW_BOT_CAPITAL)
        excess_profit = profit - target_profit
        
        if excess_profit > 0:
            # Allocate 30% of excess profit to new bot
            proportional_capital = excess_profit * 0.30
            spawn_capital = max(base_capital, proportional_capital)
            # Cap at 3x the base capital to avoid too large allocations
            spawn_capital = min(spawn_capital, base_capital * 3.0)
        else:
            spawn_capital = base_capital
        
        spawn_capital = round(spawn_capital, 2)
        logger.info(f"Spawning bot on {platform} with capital ZAR {spawn_capital:.2f} (base: {base_capital}, profit: {profit:.2f}, threshold: {target_profit:.2f})")
        
        spawn_result = await bot_spawner.spawn_bot(self.user_id, {
            "exchange": platform,
            "risk_mode": "safe",
            "capital": spawn_capital,
            "name": f"Auto-{_platform_display_name(platform)}-{next_milestone:02d}"
        })

        if not spawn_result.get("success"):
            await self.milestones.update_one(
                {"user_id": self.user_id, "platform": platform, "milestone_index": next_milestone},
                {"$set": {
                    "status": "failed",
                    "failure_reason": spawn_result.get("error")
                }}
            )
            return None

        bot_id = spawn_result.get("bot_id")
        await self.db.bots.update_one(
            {"id": bot_id},
            {"$set": {
                "spawned_by": "autopilot_growth",
                "spawn_milestone": next_milestone,
                "spawn_exchange_profit": round(profit, 2)
            }}
        )

        await self.milestones.update_one(
            {"user_id": self.user_id, "platform": platform, "milestone_index": next_milestone},
            {"$set": {
                "status": "spawned",
                "bot_id": bot_id
            }}
        )

        return bot_id

    async def get_growth_status(self) -> Dict:
        status = {}
        for platform in SUPPORTED_PLATFORMS:
            status[platform] = await self._get_platform_status(platform)

        return {
            "user_id": self.user_id,
            "enabled": config.ENABLE_AUTOPILOT_GROWTH,
            "profit_threshold_zar": float(config.AUTOPILOT_PROFIT_MILESTONE_ZAR),
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
        profit = await self.get_platform_realized_profit_zar(platform)
        last_milestone = await self._get_last_milestone_index(platform)
        next_milestone = last_milestone + 1
        threshold = float(config.AUTOPILOT_PROFIT_MILESTONE_ZAR)
        next_threshold = next_milestone * threshold
        milestones_spawned = await self.milestones.count_documents({
            "user_id": self.user_id,
            "platform": platform,
            "status": "spawned"
        })
        last_event = await self.milestones.find_one(
            {"user_id": self.user_id, "platform": platform, "status": "spawned"},
            sort=[("milestone_index", -1)]
        )
        if last_event:
            last_event["_id"] = str(last_event["_id"])

        eligible, reasons = await self._check_guardrails(platform)
        profit_ready = profit >= next_threshold
        if not profit_ready:
            reasons.append("PROFIT_BELOW_THRESHOLD")

        spawn_capital = float(config.NEW_BOT_CAPITAL)
        has_funds, available_capital = await reserved_funds_service.check_available_funds(
            self.user_id, platform, "ZAR", spawn_capital
        )
        reserved_summary = await reserved_funds_service.get_reserved_summary(self.user_id)
        reserved_capital = _exchange_reserved_from_summary(reserved_summary, platform)
        shortfall = max(0.0, spawn_capital - float(available_capital))
        block_reason_details = []
        if not has_funds or "INSUFFICIENT_AVAILABLE_FUNDS" in reasons:
            block_reason_details.append(
                f"minimum required={spawn_capital:.2f}, available={float(available_capital):.2f}, "
                f"reserved={reserved_capital:.2f}, shortfall={shortfall:.2f}"
            )

        return {
            "realized_profit_zar": round(profit, 2),
            "next_threshold_zar": round(next_threshold, 2),
            "bots_current": bots_current,
            "bots_max": bots_max,
            "milestones_spawned": milestones_spawned,
            "eligible": eligible and profit_ready,
            "blocked_reasons": reasons,
            "last_spawn_event": last_event,
            "min_capital_required": round(spawn_capital, 2),
            "available_capital": round(float(available_capital), 2),
            "reserved_capital": round(reserved_capital, 2),
            "shortfall_capital": round(shortfall, 2),
            "block_reason_details": block_reason_details,
        }

    async def _get_last_milestone_index(self, platform: str) -> int:
        last_event = await self.milestones.find_one(
            {"user_id": self.user_id, "platform": platform, "status": {"$in": ["spawned", "pending"]}},
            sort=[("milestone_index", -1)],
            projection={"milestone_index": 1}
        )
        return int(last_event.get("milestone_index", 0)) if last_event else 0

    async def _check_guardrails(self, platform: str) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        if not config.ENABLE_AUTOPILOT_GROWTH:
            reasons.append("AUTOPILOT_GROWTH_DISABLED")

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

        bodyguard_count = await self.db.bots.count_documents({
            "user_id": self.user_id,
            "paused_by_bodyguard": True
        })
        if bodyguard_count > 0:
            reasons.append("BODYGUARD_LOCK_ACTIVE")

        bots_current = await self.db.bots.count_documents({
            "user_id": self.user_id,
            "exchange": platform,
            "status": {"$ne": "deleted"}
        })
        if bots_current >= _platform_bot_limit(platform):
            reasons.append("MAX_BOTS_REACHED")

        # Check cooldown period - no spawns within AUTO_SPAWN_COOLDOWN_MINUTES
        if config.AUTO_SPAWN_COOLDOWN_MINUTES > 0:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=config.AUTO_SPAWN_COOLDOWN_MINUTES)
            recent_spawn = await self.milestones.find_one({
                "user_id": self.user_id,
                "platform": platform,
                "status": "spawned",
                "triggered_at": {"$gte": cutoff_time.isoformat()}
            })
            if recent_spawn:
                reasons.append("COOLDOWN_ACTIVE")

        # Check daily spawn limit - no more than AUTO_SPAWN_MAX_PER_DAY per day
        if config.AUTO_SPAWN_MAX_PER_DAY > 0:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_spawns = await self.milestones.count_documents({
                "user_id": self.user_id,
                "platform": platform,
                "status": "spawned",
                "triggered_at": {"$gte": today_start.isoformat()}
            })
            if today_spawns >= config.AUTO_SPAWN_MAX_PER_DAY:
                reasons.append("MAX_SPAWNS_REACHED")

        # API keys are only required for live trading; paper mode runs without exchange keys
        skip_api_key_check = config.ENABLE_PAPER_TRADING and not config.ENABLE_LIVE_TRADING
        if not skip_api_key_check:
            key_doc = await self.db.api_keys.find_one(
                {"user_id": str(self.user_id), "provider": platform},
                {"_id": 0, "status": 1, "last_test_ok": 1, "valid": 1}
            )
            if not key_doc:
                reasons.append("API_KEYS_MISSING")
            else:
                status = _normalize_key_status(key_doc.get("status"))
                if status != ProviderStatus.CONFIGURED_VALID.value and not key_doc.get("last_test_ok") and not key_doc.get("valid"):
                    reasons.append("API_KEYS_INVALID")

        spawn_capital = float(config.NEW_BOT_CAPITAL)
        has_funds, _available = await reserved_funds_service.check_available_funds(
            self.user_id, platform, "ZAR", spawn_capital
        )
        if not has_funds:
            reasons.append("INSUFFICIENT_AVAILABLE_FUNDS")

        return len(reasons) == 0, reasons


class AutopilotGrowthScheduler:
    def __init__(self, database, interval_seconds: int = 60):
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
        if not config.ENABLE_AUTOPILOT_GROWTH:
            return
        users = await self.db.users.find({}, {"_id": 0, "id": 1}).to_list(1000)
        for user in users:
            user_id = user.get("id")
            if not user_id:
                continue
            service = AutopilotGrowthService(self.db, user_id)
            for platform in SUPPORTED_PLATFORMS:
                await service.try_trigger_spawn(platform)

    async def _run_loop(self):
        while self.running:
            try:
                await self.run_once()
            except Exception as exc:
                logger.warning(f"Autopilot growth loop error: {exc}")
            await asyncio.sleep(self.interval_seconds)


_growth_scheduler: Optional[AutopilotGrowthScheduler] = None


def get_autopilot_growth_scheduler(database) -> AutopilotGrowthScheduler:
    global _growth_scheduler
    if _growth_scheduler is None:
        _growth_scheduler = AutopilotGrowthScheduler(database)
    return _growth_scheduler
