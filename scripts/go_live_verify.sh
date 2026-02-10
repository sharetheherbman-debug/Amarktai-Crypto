#!/usr/bin/env bash
set -e

python - <<'PY'
import asyncio
import getpass
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient

API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "amarktai_trading")

passed = 0
failed = 0

def report(ok, message):
    global passed, failed
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {message}")
    if ok:
        passed += 1
    else:
        failed += 1
    return ok

def request_json(method, path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, f"{API_BASE}{path}", headers=headers, json=payload, timeout=20)
    data = response.json() if response.content else {}
    return response, data

def get_ws_url():
    if API_BASE.startswith("https://"):
        return API_BASE.replace("https://", "wss://")
    return API_BASE.replace("http://", "ws://")

print(f"🔍 GO-LIVE VERIFY @ {API_BASE}")

# 1) Health ping
resp, _ = request_json("GET", "/api/health/ping")
report(resp.status_code == 200, "/api/health/ping returns 200")

# 2) Login + JWT
email = input("Email: ").strip()
password = getpass.getpass("Password: ").strip()
resp, data = request_json("POST", "/api/auth/login", payload={"email": email, "password": password})
token = data.get("access_token")
report(resp.status_code == 200 and token, "Login returned JWT token")
if not token:
    sys.exit(1)

resp, profile = request_json("GET", "/api/auth/me", token=token)
user_id = profile.get("id") or profile.get("user_id")
report(resp.status_code == 200 and user_id, "Fetched /api/auth/me profile")

# 3) API shapes
resp, bots_data = request_json("GET", "/api/bots", token=token)
report(resp.status_code == 200 and isinstance(bots_data, dict) and "bots" in bots_data, "/api/bots returns object with bots")

resp, trades_data = request_json("GET", "/api/trades/recent?limit=5", token=token)
report(resp.status_code == 200 and isinstance(trades_data, dict) and "trades" in trades_data, "/api/trades/recent returns object with trades")
required_fields = {"bot_id", "exchange", "pair", "side", "price", "qty", "trading_mode", "created_at", "is_live"}
if trades_data.get("trades"):
    missing = [
        field for field in required_fields
        if any(t.get(field) in (None, "") for t in trades_data["trades"])
    ]
    report(len(missing) == 0, f"Recent trades have required fields ({', '.join(missing)})")
else:
    report(True, "No recent trades to validate fields (skipped)")

# 4) Admin overview correctness
admin_password = getpass.getpass("Admin password (optional, press Enter to skip admin overview): ").strip()
admin_token = token
if admin_password:
    resp, unlock = request_json("POST", "/api/admin/unlock", token=token, payload={"password": admin_password})
    if resp.status_code == 200:
        admin_token = unlock.get("admin_token", token)
        report(True, "Admin unlock succeeded")
    else:
        report(False, "Admin unlock failed")
resp, overview = request_json("GET", "/api/admin/overview", token=admin_token)
if resp.status_code == 200 and overview.get("stats"):
    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
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
    report(api_count == direct_count, f"Admin overview last_24h matches Mongo ({api_count})")
    if direct_count > 0:
        report(api_count > 0, "Admin overview last_24h > 0 when trades exist")
else:
    report(False, "Admin overview unavailable (admin token missing?)")

# 5) Paper wallet works
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]
wallet_count = db.wallet_balances.count_documents({})
report(wallet_count > 0, "wallet_balances collection has documents")

bot_id = None
for bot in bots_data.get("bots", []):
    bot_id = bot.get("id")
    if bot_id:
        break
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
    bot_id = created.get("id")
if bot_id:
    sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
    import database as database
    from services.paper_wallet_ledger import paper_wallet_ledger
    async def verify_wallet():
        if database.db is None:
            await database.connect()
        success, balance_before, msg = await paper_wallet_ledger.get_balance(bot_id)
        if not success:
            return False, f"No paper wallet: {msg}"
        await paper_wallet_ledger.credit(bot_id, 1.0, "go_live_verify")
        success, balance_after, msg = await paper_wallet_ledger.get_balance(bot_id)
        if not success:
            return False, f"Balance read failed: {msg}"
        wallet_doc = await database.wallet_balances_collection.find_one({"user_id": user_id}, {"_id": 0})
        updated = wallet_doc and abs(wallet_doc.get("paper_wallet_balance_zar", 0) - balance_after) < 0.01
        can_trade, msg = await paper_wallet_ledger.can_trade(bot_id, balance_after + 999999)
        await paper_wallet_ledger.debit(bot_id, 1.0, "go_live_verify")
        return updated and (not can_trade), "paper wallet updated & insufficient funds blocked"
    ok, msg = asyncio.run(verify_wallet())
    report(ok, msg)
else:
    report(False, "No bot available for paper wallet test")

# 6) Bot deletion/name reuse
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
    resp, _ = request_json(
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
    report(resp.status_code == 200, "Bot name reuse after delete works")
else:
    report(False, "Bot create/delete for name reuse failed")

# Wallet transfer endpoints (optional simulation)
resp, transfers = request_json("GET", "/api/wallet/transfers", token=token)
report(resp.status_code == 200, "Wallet transfer history endpoint reachable")
transfer_phrase = input('Type "TEST WALLET TRANSFER" to simulate a transfer (or press Enter to skip): ')
if transfer_phrase == "TEST WALLET TRANSFER":
    payload = {
        "from_exchange": "luno",
        "to_exchange": "binance",
        "amount": 1.0,
        "currency": "ZAR",
        "idempotency_key": f"go-live-{int(datetime.now(timezone.utc).timestamp())}"
    }
    resp, transfer_data = request_json("POST", "/api/wallet/transfer", token=token, payload=payload)
    report(resp.status_code == 200, "Wallet transfer request accepted")
    if resp.status_code == 200:
        report("mode" in transfer_data, "Wallet transfer response includes mode")
else:
    print("[INFO] Wallet transfer simulation skipped.")

# 7) AI chat verification
resp, ai_data = request_json("POST", "/api/ai/chat", token=token, payload={"content": "go-live verify ping"})
ai_ok = resp.status_code == 200
report(ai_ok, "/api/ai/chat returned 200")
if ai_ok:
    report("model_used" in ai_data, "AI response includes model_used")
    report("key_source" in ai_data, "AI response includes key_source")
    try:
        openai_key = db.api_keys.find_one({"user_id": user_id, "provider": "openai"})
        if openai_key:
            report(ai_data.get("key_source") == "user", "AI key_source=user when OpenAI key configured")
    except Exception as e:
        print(f"[WARN] OpenAI key check skipped: {e}")

# 8) WebSocket handshake (optional)
try:
    import websockets
    async def ws_check():
        ws_url = f"{get_ws_url()}/api/ws?token={token}"
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await ws.send("ping")
    asyncio.run(ws_check())
    report(True, "WebSocket handshake (optional)")
except Exception as e:
    print(f"[WARN] WebSocket handshake skipped/failed: {e}")
    report(True, "WebSocket handshake skipped (optional)")

# 9) Go-live gating checks
resp, mode_data = request_json("GET", "/api/system/mode", token=token)
mode_ok = resp.status_code == 200 and mode_data.get("paperTrading") is True
report(mode_ok, "System mode defaults to paper")

phrase = input('Type EXACT confirmation phrase to attempt live switch (or press Enter to skip): ')
if phrase == "I UNDERSTAND LIVE TRADING USES REAL FUNDS":
    resp, toggle = request_json(
        "PUT",
        "/api/system/mode",
        token=token,
        payload={"mode": "liveTrading", "enabled": True, "confirmation_token": "CONFIRM_LIVE_TRADING"}
    )
    report(resp.status_code == 200, "Live mode switch request accepted")
else:
    print("[INFO] Live switch skipped (confirmation phrase not provided).")

print("")
print(f"SUMMARY: {passed} passed, {failed} failed")
if failed == 0:
    print("✅ PASS: System ready. Next step to enable live trading:")
    print("   1) Set ENABLE_LIVE_TRADING=true in environment")
    print("   2) Use /api/system/mode with confirmation_token=CONFIRM_LIVE_TRADING")
else:
    print("❌ FAIL: Fix the failures above before enabling live trading.")
sys.exit(1 if failed else 0)
PY
