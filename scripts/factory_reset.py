#!/usr/bin/env python3
"""
Factory Reset Script
Resets system to clean state keeping ONLY admin user: amarktainetwork@gmail.com
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
import secrets

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ADMIN_EMAIL = "amarktainetwork@gmail.com"


def generate_confirmation_token():
    """Generate a random confirmation token"""
    return secrets.token_hex(16)


async def factory_reset(confirmation_token: str, provided_token: str):
    """
    Perform factory reset
    
    Args:
        confirmation_token: Expected token
        provided_token: Token provided by user
    """
    
    # Verify token
    if confirmation_token != provided_token:
        logger.error("❌ INVALID CONFIRMATION TOKEN")
        logger.error("Factory reset ABORTED")
        return False
    
    logger.warning("⚠️  STARTING FACTORY RESET - THIS CANNOT BE UNDONE")
    logger.warning("⚠️  Keeping ONLY admin user: " + ADMIN_EMAIL)
    
    # Log the reset action
    reset_log = {
        "action": "factory_reset",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "admin_email": ADMIN_EMAIL,
        "confirmation_token": confirmation_token
    }
    
    try:
        await db.init_db()
        
        # 1. Delete all bots
        logger.info("\n1. Deleting all bots...")
        result = await db.bots_collection.delete_many({})
        logger.info(f"   ✅ Deleted {result.deleted_count} bots")
        
        # 2. Delete all trades
        logger.info("\n2. Deleting all trades...")
        result = await db.trades_collection.delete_many({})
        logger.info(f"   ✅ Deleted {result.deleted_count} trades")
        
        # 3. Delete all profit ledgers
        logger.info("\n3. Deleting all profit ledgers...")
        result = await db.profit_ledger_collection.delete_many({})
        logger.info(f"   ✅ Deleted {result.deleted_count} ledger entries")
        
        # 4. Delete all API keys except admin
        logger.info("\n4. Deleting non-admin API keys...")
        admin_user = await db.users_collection.find_one({"email": ADMIN_EMAIL})
        admin_id = admin_user.get('id') if admin_user else None
        
        if admin_id:
            result = await db.api_keys_collection.delete_many({"user_id": {"$ne": admin_id}})
            logger.info(f"   ✅ Deleted {result.deleted_count} API keys")
        else:
            logger.warning("   ⚠️  Admin user not found, keeping all API keys")
        
        # 5. Delete all users except admin
        logger.info("\n5. Deleting non-admin users...")
        result = await db.users_collection.delete_many({"email": {"$ne": ADMIN_EMAIL}})
        logger.info(f"   ✅ Deleted {result.deleted_count} users")
        
        # 6. Verify admin user exists
        logger.info("\n6. Verifying admin user...")
        admin_user = await db.users_collection.find_one({"email": ADMIN_EMAIL})
        if admin_user:
            logger.info(f"   ✅ Admin user exists: {admin_user.get('email')}")
            logger.info(f"      User ID: {admin_user.get('id')}")
            logger.info(f"      Role: {admin_user.get('role', 'N/A')}")
        else:
            logger.error("   ❌ ADMIN USER NOT FOUND!")
            logger.error(f"      Expected: {ADMIN_EMAIL}")
            logger.error("      System may be in invalid state!")
        
        # 7. Log the reset
        logger.info("\n7. Logging reset action...")
        await db.audit_log_collection.insert_one(reset_log)
        logger.info("   ✅ Reset logged to audit_log")
        
        # 8. Print final summary
        logger.info("\n" + "="*60)
        logger.info("FACTORY RESET COMPLETE")
        logger.info("="*60)
        logger.info(f"  Admin user: {ADMIN_EMAIL}")
        logger.info(f"  All bots: DELETED")
        logger.info(f"  All trades: DELETED")
        logger.info(f"  All profit ledgers: DELETED")
        logger.info(f"  Non-admin API keys: DELETED")
        logger.info(f"  Non-admin users: DELETED")
        logger.info(f"  Timestamp: {reset_log['timestamp']}")
        logger.info("="*60 + "\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Factory reset failed: {e}", exc_info=True)
        return False


async def main():
    """Interactive factory reset"""
    
    logger.info("="*60)
    logger.info("FACTORY RESET - ADMIN ONLY")
    logger.info("="*60)
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Database: {os.getenv('MONGODB_URI', 'mongodb://localhost:27017')}")
    logger.info("="*60 + "\n")
    
    # Check if running interactively
    if len(sys.argv) > 1 and sys.argv[1] == "--token":
        # Token provided via command line (for API endpoint use)
        if len(sys.argv) < 3:
            logger.error("Usage: factory_reset.py --token <confirmation_token> <provided_token>")
            return 1
        confirmation_token = sys.argv[2]
        provided_token = sys.argv[3] if len(sys.argv) > 3 else ""
    else:
        # Interactive mode
        logger.warning("⚠️  WARNING: This will DELETE ALL DATA except admin user!")
        logger.warning(f"⚠️  Admin user to keep: {ADMIN_EMAIL}")
        logger.warning("⚠️  This action CANNOT be undone!\n")
        
        response = input("Type 'DELETE EVERYTHING' to confirm: ")
        if response != "DELETE EVERYTHING":
            logger.info("Reset cancelled by user")
            return 0
        
        # Generate and display confirmation token
        confirmation_token = generate_confirmation_token()
        logger.info(f"\nConfirmation token: {confirmation_token}")
        logger.info("Please save this token for audit purposes.\n")
        
        provided_token = input("Enter confirmation token to proceed: ")
    
    # Perform reset
    success = await factory_reset(confirmation_token, provided_token)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
