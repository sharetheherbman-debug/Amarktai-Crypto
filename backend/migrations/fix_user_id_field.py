"""
Startup Migration: Fix User ID Field
Ensures all users have 'id' field set to str(_id) if missing
Run this once at startup to repair any schema drift
"""

import asyncio
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


async def migrate_user_ids(db):
    """
    Migrate users missing 'id' field
    For each user: if no 'id' field, set id = str(_id)
    """
    try:
        users_collection = db.users_collection
        
        # Find all users without 'id' field
        users_without_id = await users_collection.find(
            {"id": {"$exists": False}},
            {"_id": 1, "email": 1}
        ).to_list(None)
        
        if not users_without_id:
            logger.info("✓ User ID migration: All users have 'id' field")
            return
        
        logger.info(f"Found {len(users_without_id)} users without 'id' field - migrating...")
        
        migrated_count = 0
        for user in users_without_id:
            user_id = str(user["_id"])
            email = user.get("email", "unknown")
            
            result = await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"id": user_id}}
            )
            
            if result.modified_count > 0:
                migrated_count += 1
                logger.info(f"✓ Migrated user {email} - set id={user_id}")
        
        logger.info(f"✓ User ID migration complete: {migrated_count} users updated")
        
    except Exception as e:
        logger.error(f"✗ User ID migration failed: {e}")
        # Don't raise - let app continue even if migration fails


async def migrate_api_keys_repair(db):
    """
    Repair API keys collection
    Adds missing id fields, ensures consistent schema
    """
    try:
        # Import repair function from scripts
        import sys
        import os
        scripts_path = os.path.join(os.path.dirname(__file__), '..', 'scripts')
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        
        from repair_api_keys import repair_api_keys
        
        logger.info("Running API keys repair migration...")
        stats = await repair_api_keys()
        
        if stats.get("errors", 0) > 0:
            logger.warning(f"✗ API keys repair completed with {stats['errors']} errors")
        else:
            logger.info(f"✓ API keys repair complete: {stats.get('fixed_id', 0)} keys fixed")
        
    except Exception as e:
        logger.error(f"✗ API keys repair failed: {e}")
        # Don't raise - let app continue even if repair fails


async def run_startup_migrations(db):
    """
    Run all startup migrations
    Called once when the application starts
    """
    logger.info("Running startup migrations...")
    await migrate_user_ids(db)
    await migrate_api_keys_repair(db)
    logger.info("Startup migrations complete")


if __name__ == "__main__":
    # Test migration standalone
    import sys
    sys.path.append("/home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment/backend")
    
    import database as db
    
    async def main():
        await db.connect_to_database()
        await run_startup_migrations(db)
    
    asyncio.run(main())
