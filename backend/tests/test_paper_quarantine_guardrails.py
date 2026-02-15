import pytest
import asyncio

from services.bot_quarantine import BotQuarantineService
import services.bot_quarantine as quarantine_module


class FakeBotsCollection:
    def __init__(self, docs):
        self.docs = docs
        self.last_update = None

    async def find_one(self, query):
        return self.docs.get(query.get("id"))

    async def update_one(self, query, update):
        bot_id = query["id"]
        doc = self.docs[bot_id]
        if "$set" in update:
            doc.update(update["$set"])
        self.last_update = update


def test_paper_mode_disabled_is_not_quarantined(monkeypatch):
    bot_id = "paper-bot-1"
    fake_collection = FakeBotsCollection({
        bot_id: {
            "id": bot_id,
            "mode": "paper",
            "status": "active",
            "quarantine_count": 0,
        }
    })
    monkeypatch.setattr(quarantine_module.db, "bots_collection", fake_collection)

    service = BotQuarantineService()
    result = asyncio.run(service.quarantine_bot(bot_id, "MODE_DISABLED", {
        "source": "trading_scheduler",
        "rule": "system_mode_gate",
        "reason_code": "MODE_DISABLED",
    }))

    assert result["action"] == "skipped"
    assert fake_collection.last_update is None


def test_paper_non_strategy_quarantine_is_short(monkeypatch):
    bot_id = "paper-bot-2"
    fake_collection = FakeBotsCollection({
        bot_id: {
            "id": bot_id,
            "mode": "paper",
            "status": "active",
            "quarantine_count": 0,
        }
    })
    monkeypatch.setattr(quarantine_module.db, "bots_collection", fake_collection)

    service = BotQuarantineService()
    result = asyncio.run(service.quarantine_bot(bot_id, "UNSUPPORTED_EXCHANGE", {
        "source": "trading_scheduler",
        "rule": "unsupported_exchange",
        "reason_code": "UNSUPPORTED_EXCHANGE",
    }))

    assert result["action"] == "retraining"
    assert result["quarantine_duration_seconds"] <= 60
    assert fake_collection.docs[bot_id]["quarantine_source"] == "trading_scheduler"
