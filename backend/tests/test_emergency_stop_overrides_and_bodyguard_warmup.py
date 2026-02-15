import asyncio
from datetime import datetime, timezone

import services.bodyguard_service as bodyguard_module
import services.emergency_stop_override_service as override_module


class FakeCollection:
    def __init__(self, doc=None):
        self.doc = doc or {}

    async def find_one(self, query, projection=None):
        if query.get("id") == "admin_overrides":
            return dict(self.doc) if self.doc else None
        return None

    async def update_one(self, query, update, upsert=False):
        if not self.doc:
            self.doc = {"id": "admin_overrides", "per_user": {}, "global_disabled": False}
        if "$set" in update:
            for key, value in update["$set"].items():
                if key.startswith("per_user."):
                    _, user_id = key.split(".", 1)
                    self.doc.setdefault("per_user", {})[user_id] = value
                else:
                    self.doc[key] = value
        if "$unset" in update:
            for key in update["$unset"].keys():
                if key.startswith("per_user."):
                    _, user_id = key.split(".", 1)
                    self.doc.setdefault("per_user", {}).pop(user_id, None)


class FakeBotsCollection:
    def __init__(self, bot):
        self.bot = dict(bot)
        self.last_set = {}

    async def find_one(self, query, projection=None):
        if query.get("id") == self.bot["id"]:
            return dict(self.bot)
        return None

    async def update_one(self, query, update):
        if "$set" in update:
            self.bot.update(update["$set"])
            self.last_set.update(update["$set"])
        if "$unset" in update:
            for key in update["$unset"].keys():
                self.bot.pop(key, None)


def test_emergency_override_disables_effective_lock(monkeypatch):
    fake_collection = FakeCollection({"id": "admin_overrides", "global_disabled": True, "per_user": {}})
    monkeypatch.setattr(override_module.db, "emergency_stop_collection", fake_collection)

    result = asyncio.run(override_module.emergency_stop_override_service.evaluate("u1", True))
    assert result["effective_active"] is False
    assert result["global_disabled"] is True


def test_bodyguard_warmup_skips_pause(monkeypatch):
    bot_id = "warmup-bot"
    fake_bots = FakeBotsCollection({
        "id": bot_id,
        "user_id": "u1",
        "name": "Warmup Bot",
        "status": "active",
        "trading_mode": "paper",
        "risk_mode": "safe",
        "trades_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "current_capital": 1000,
        "equity_peak": 1200,
    })
    monkeypatch.setattr(bodyguard_module.db, "bots_collection", fake_bots)
    # Disable shared DB handle so the test remains isolated from DB-backed services.
    monkeypatch.setattr(bodyguard_module.db, "db", None)

    action_taken, _ = asyncio.run(bodyguard_module.bodyguard_service.check_bot_drawdown("u1", bot_id))
    assert action_taken is False
    assert fake_bots.last_set.get("bodyguard_warmup") is True
