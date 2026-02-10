#!/usr/bin/env python3
"""
Verify critical production blockers in a single CLI run.
"""

import asyncio
import getpass
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient


API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "amarktai_trading")


def log_result(ok: bool, message: str) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {message}")
    return ok


def request_json(method: str, path: str, token: str = None, payload: dict | None = None):
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, url, headers=headers, json=payload, timeout=15)
    return response, response.json() if response.content else {}


async def verify_paper_wallet(user_id: str, bot_id: str) -> bool:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    import database as database
    from services.paper_wallet_ledger import paper_wallet_ledger

    if database.db is None:
        await database.connect()

    success, balance_before, msg = await paper_wallet_ledger.get_balance(bot_id)
    if not success:
        return log_result(False, f"Paper wallet missing for bot {bot_id}: {msg}")

    await paper_wallet_ledger.credit(bot_id, 1.0, "verify_system")
    success, balance_after, msg = await paper_wallet_ledger.get_balance(bot_id)
    if not success:
        return log_result(False, f"Paper wallet balance not readable after credit: {msg}")

    wallet_doc = None
    if database.wallet_balances_collection is not None:
        wallet_doc = await database.wallet_balances_collection.find_one({"user_id": user_id}, {"_id": 0})

    updated = wallet_doc and abs(wallet_doc.get("paper_wallet_balance_zar", 0) - balance_after) < 0.01
    log_result(updated, "wallet_balances updated after paper trade simulation")

    can_trade, msg = await paper_wallet_ledger.can_trade(bot_id, balance_after + 999999)
    log_result(not can_trade, "Paper wallet blocks insufficient funds trades")

    await paper_wallet_ledger.debit(bot_id, 1.0, "verify_system")
    return updated and not can_trade


def main() -> int:
    print(f"🔎 Verifying system against {API_BASE}")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ").strip()

    resp, data = request_json("POST", "/api/auth/login", payload={"email": email, "password": password})
    token = data.get("access_token")
    if resp.status_code != 200 or not token:
        log_result(False, f"Login failed: {data}")
        return 1
    log_result(True, "Authenticated successfully")

    resp, profile = request_json("GET", "/api/auth/me", token=token)
    user_id = profile.get("id") or profile.get("user_id")
    log_result(resp.status_code == 200 and user_id, "Fetched user profile")

    resp, bots_data = request_json("GET", "/api/bots", token=token)
    bots_ok = resp.status_code == 200 and isinstance(bots_data, dict) and "bots" in bots_data
    log_result(bots_ok, "/api/bots returns object with bots list")

    resp, trades_data = request_json("GET", "/api/trades/recent?limit=5", token=token)
    trades_ok = resp.status_code == 200 and isinstance(trades_data, dict) and "trades" in trades_data
    log_result(trades_ok, "/api/trades/recent returns object with trades list")
    required_fields = {"bot_id", "exchange", "pair", "side", "price", "qty", "trading_mode", "created_at", "is_live"}
    if trades_ok and trades_data.get("trades"):
        missing = [
            field for field in required_fields
            if any(t.get(field) in (None, "") for t in trades_data["trades"])
        ]
        log_result(len(missing) == 0, f"Recent trades include required fields ({', '.join(missing)})")

    bot_id = None
    if bots_ok and bots_data.get("bots"):
        bot_id = bots_data["bots"][0].get("id")

    if not bot_id:
        bot_name = f"verify-bot-{int(datetime.now(timezone.utc).timestamp())}"
        resp, created = request_json(
            "POST",
            "/api/bots",
            token=token,
            payload={
                "name": bot_name,
                "exchange": "luno",
                "risk_mode": "safe",
                "trading_mode": "paper",
                "initial_capital": 1000
            }
        )
        if resp.status_code == 200:
            bot_id = created.get("id") or created.get("bot", {}).get("id")

    if not bot_id or not user_id:
        log_result(False, "No bot or user available for paper wallet verification")
    else:
        asyncio.run(verify_paper_wallet(user_id, bot_id))

    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    wallet_count = db.wallet_balances.count_documents({})
    log_result(wallet_count > 0, "wallet_balances collection has documents")

    admin_password = getpass.getpass("Admin password (optional, press Enter to skip): ").strip()
    admin_token = token
    if admin_password:
        resp, unlock = request_json("POST", "/api/admin/unlock", token=token, payload={"password": admin_password})
        if resp.status_code == 200:
            admin_token = unlock.get("admin_token", token)
            log_result(True, "Admin unlock successful")
        else:
            log_result(False, "Admin unlock failed")

    resp, overview = request_json("GET", "/api/admin/overview", token=admin_token)
    if resp.status_code == 200 and overview.get("stats"):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        query = {
            "$or": [
                {"timestamp": {"$gte": cutoff}},
                {"created_at": {"$gte": cutoff}},
                {"timestamp": {"$gte": cutoff.isoformat()}},
                {"created_at": {"$gte": cutoff.isoformat()}},
            ]
        }
        direct_count = db.trades.count_documents(query)
        api_count = overview["stats"]["trades"]["last_24h"]
        log_result(api_count == direct_count, f"Admin overview last_24h matches Mongo ({api_count})")
    else:
        log_result(False, "Admin overview unavailable (not admin?)")

    # Bot deletion/name reuse
    bot_name = f"verify-delete-{int(datetime.now(timezone.utc).timestamp())}"
    resp, created = request_json(
        "POST",
        "/api/bots",
        token=token,
        payload={
            "name": bot_name,
            "exchange": "luno",
            "risk_mode": "safe",
            "trading_mode": "paper",
            "initial_capital": 1000
        }
    )
    bot_id = created.get("id")
    if resp.status_code == 200 and bot_id:
        request_json("DELETE", f"/api/bots/{bot_id}", token=token)
        resp, recreated = request_json(
            "POST",
            "/api/bots",
            token=token,
            payload={
                "name": bot_name,
                "exchange": "luno",
                "risk_mode": "safe",
                "trading_mode": "paper",
                "initial_capital": 1000
            }
        )
        log_result(resp.status_code == 200, "Bot name reuse after delete works")
    else:
        log_result(False, "Bot creation failed for delete/reuse check")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
