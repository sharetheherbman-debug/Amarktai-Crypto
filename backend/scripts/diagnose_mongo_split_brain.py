#!/usr/bin/env python3
"""
Diagnose MongoDB split-brain risk.

Prints:
  - Effective DB resolution (host, db name)
  - Collection counts in both 'amarktai' and 'amarktai_trading'
  - A recommendation

Does NOT print credentials or secrets.

Usage:
    cd backend
    python scripts/diagnose_mongo_split_brain.py
"""

import asyncio
import os
import sys

# Ensure backend package is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

COLLECTIONS = ["users", "bots", "trades", "api_keys", "system_modes"]


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    from urllib.parse import urlparse

    # ---- Resolve effective config (mirrors database._parse_mongo_config) ----
    mongo_uri = os.getenv("MONGO_URI", "").strip()
    if mongo_uri:
        try:
            parsed = urlparse(mongo_uri)
            path_db = parsed.path.lstrip("/").split("?")[0].strip()
            effective_db = path_db if path_db else os.getenv("MONGO_DB", os.getenv("DB_NAME", "amarktai_trading"))
            mongo_url = mongo_uri
        except Exception:
            effective_db = os.getenv("MONGO_DB", os.getenv("DB_NAME", "amarktai_trading"))
            mongo_url = mongo_uri
    else:
        mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        effective_db = os.getenv("MONGO_DB", os.getenv("DB_NAME", "amarktai_trading"))

    try:
        parsed = urlparse(mongo_url)
        safe_host = f"{parsed.hostname}:{parsed.port or 27017}"
    except Exception:
        safe_host = "unknown"

    print("=" * 60)
    print("MongoDB Split-Brain Diagnostic")
    print("=" * 60)
    print(f"Effective MongoDB: host={safe_host}  db={effective_db}")
    print()

    # ---- Connect ----
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command("ping")
    except Exception as e:
        print(f"ERROR: Cannot connect to MongoDB: {e}")
        return

    # ---- Count collections in both candidate DBs ----
    print(f"{'Collection':<20} {'amarktai':>12} {'amarktai_trading':>18}")
    print("-" * 52)

    counts = {}
    for db_name in ("amarktai", "amarktai_trading"):
        db = client[db_name]
        counts[db_name] = {}
        for coll in COLLECTIONS:
            try:
                n = await db[coll].count_documents({})
            except Exception:
                n = "ERR"
            counts[db_name][coll] = n

    for coll in COLLECTIONS:
        print(
            f"{coll:<20} {str(counts['amarktai'][coll]):>12} "
            f"{str(counts['amarktai_trading'][coll]):>18}"
        )

    print()

    # ---- Recommendation ----
    at_users = counts["amarktai_trading"].get("users", 0)
    a_users = counts["amarktai"].get("users", 0)

    if isinstance(at_users, int) and isinstance(a_users, int):
        if at_users > 0 and a_users == 0:
            recommendation = (
                "✅ SAFE – 'amarktai_trading' is the live DB. "
                "Ensure MONGO_URI or MONGO_DB=amarktai_trading is set."
            )
        elif at_users == 0 and a_users > 0:
            recommendation = (
                "⚠️  SPLIT-BRAIN RISK – 'amarktai' has users but "
                "'amarktai_trading' is empty. Set MONGO_DB=amarktai OR "
                "migrate data to 'amarktai_trading'."
            )
        elif at_users > 0 and a_users > 0:
            recommendation = (
                "🔴 SPLIT-BRAIN DETECTED – Both databases have users! "
                "Investigate before starting the service. "
                "Set MONGO_DB to the authoritative database."
            )
        else:
            recommendation = (
                "ℹ️  Both databases appear empty. "
                "Verify connection and seed data."
            )
    else:
        recommendation = "⚠️  Could not read user counts. Check DB connection."

    if effective_db not in ("amarktai", "amarktai_trading"):
        recommendation += f"\n⚠️  Effective DB '{effective_db}' is non-standard."

    print("Recommendation:")
    print(f"  {recommendation}")
    print()
    print(f"Effective DB used by app: {effective_db}")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
