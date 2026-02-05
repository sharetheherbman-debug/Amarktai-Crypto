#!/usr/bin/env python3
"""
Factory Reset Script - Keep Only Admin Account
DANGEROUS: Deletes all users, bots, trades except the specified admin
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db
from database import init_db


async def factory_reset(admin_email: str, confirm: bool = False):
    """Factory reset keeping only the admin account"""
    
    print("⚠️  FACTORY RESET - KEEP ADMIN ONLY")
    print("=" * 70)
    print(f"Admin to keep: {admin_email}")
    print("=" * 70)
    
    if not confirm:
        print("\n❌ This is a DESTRUCTIVE operation!")
        print("   It will DELETE all users, bots, trades, and API keys")
        print(f"   EXCEPT for admin account: {admin_email}")
        print("\n   Use --confirm flag to proceed")
        return
    
    # Initialize database connection
    await init_db()
    
    # Find admin user
    admin_user = await db.users_collection.find_one({"email": admin_email})
    
    if not admin_user:
        print(f"\n❌ Admin user not found: {admin_email}")
        print("   Please provide a valid admin email")
        sys.exit(1)
    
    admin_id = admin_user.get("id")
    
    if not admin_id:
        print(f"\n❌ Admin user has no 'id' field")
        sys.exit(1)
    
    print(f"\n✅ Found admin: {admin_email} (ID: {admin_id})")
    
    # Confirm one more time
    print("\n" + "=" * 70)
    print("⚠️  FINAL WARNING: About to DELETE everything except admin!")
    print("=" * 70)
    response = input("Type 'DELETE' to confirm: ")
    
    if response != "DELETE":
        print("❌ Cancelled. No changes made.")
        return
    
    print("\n🗑️  Starting factory reset...")
    
    # Delete all non-admin users
    users_result = await db.users_collection.delete_many({
        "id": {"$ne": admin_id}
    })
    print(f"  ✓ Deleted {users_result.deleted_count} users")
    
    # Delete all bots
    bots_result = await db.bots_collection.delete_many({})
    print(f"  ✓ Deleted {bots_result.deleted_count} bots")
    
    # Delete all trades
    trades_result = await db.trades_collection.delete_many({})
    print(f"  ✓ Deleted {trades_result.deleted_count} trades")
    
    # Delete all API keys except admin's
    keys_result = await db.api_keys_collection.delete_many({
        "user_id": {"$ne": admin_id}
    })
    print(f"  ✓ Deleted {keys_result.deleted_count} API keys")
    
    # Reset admin user to safe defaults
    await db.users_collection.update_one(
        {"id": admin_id},
        {
            "$set": {
                "blocked": False,
                "system_mode": "testing",
                "autopilot_enabled": False,
                "bodyguard_enabled": True,
                "learning_enabled": True,
                "emergency_stop": False,
                "factory_reset_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    print(f"  ✓ Reset admin user to safe defaults")
    
    print("\n✅ Factory reset complete!")
    print(f"   Kept admin: {admin_email}")
    print(f"   System is now clean and ready for fresh setup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Factory reset keeping only admin account")
    parser.add_argument("--email", required=True, help="Admin email to keep")
    parser.add_argument("--confirm", action="store_true", help="Confirm the factory reset")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(factory_reset(args.email, args.confirm))
    except KeyboardInterrupt:
        print("\n❌ Factory reset cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Factory reset failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
