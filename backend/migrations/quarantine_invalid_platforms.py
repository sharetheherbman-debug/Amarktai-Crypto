"""
Migration: Quarantine bots with invalid platforms
Sets status=quarantine for bots with platform=null or invalid platform
"""

import asyncio
import logging
from datetime import datetime, timezone

# Import after setting up paths
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

import database as db
from config.platforms import SUPPORTED_PLATFORMS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_invalid_platform_bots():
    """Find and quarantine bots with null or invalid platforms"""
    
    # Initialize database
    await db.init_db()
    
    logger.info("Starting migration: quarantine invalid platform bots")
    
    # Find bots with null platform
    null_platform_bots = await db.bots_collection.find(
        {
            "$or": [
                {"platform": None},
                {"platform": {"$exists": False}},
                {"exchange": None},
                {"exchange": {"$exists": False}}
            ],
            "status": {"$ne": "deleted"}
        },
        {"_id": 0, "id": 1, "name": 1, "user_id": 1, "platform": 1, "exchange": 1}
    ).to_list(10000)
    
    logger.info(f"Found {len(null_platform_bots)} bots with null platform")
    
    # Find bots with invalid platform (not in SUPPORTED_PLATFORMS)
    all_bots = await db.bots_collection.find(
        {"status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "name": 1, "user_id": 1, "platform": 1, "exchange": 1, "status": 1}
    ).to_list(10000)
    
    invalid_platform_bots = []
    for bot in all_bots:
        platform = bot.get("platform") or bot.get("exchange")
        if platform and platform.lower() not in SUPPORTED_PLATFORMS:
            invalid_platform_bots.append(bot)
    
    logger.info(f"Found {len(invalid_platform_bots)} bots with invalid platform")
    
    # Combine lists
    bots_to_quarantine = null_platform_bots + invalid_platform_bots
    
    if not bots_to_quarantine:
        logger.info("No bots need quarantining")
        return
    
    # Quarantine each bot
    quarantined_count = 0
    for bot in bots_to_quarantine:
        bot_id = bot["id"]
        bot_name = bot.get("name", "Unnamed")
        platform = bot.get("platform") or bot.get("exchange") or "null"
        
        try:
            result = await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "status": "quarantined",
                        "pause_reason": "INVALID_PLATFORM",
                        "quarantine_reason": f"Invalid or missing platform: {platform}",
                        "quarantined_at": datetime.now(timezone.utc).isoformat(),
                        "quarantine_migration": True
                    }
                }
            )
            
            if result.modified_count > 0:
                quarantined_count += 1
                logger.info(f"✅ Quarantined bot {bot_id[:8]} ({bot_name}) - platform: {platform}")
            else:
                logger.warning(f"⚠️ Failed to quarantine bot {bot_id[:8]} ({bot_name})")
                
        except Exception as e:
            logger.error(f"❌ Error quarantining bot {bot_id[:8]}: {e}")
    
    logger.info(f"Migration complete: Quarantined {quarantined_count}/{len(bots_to_quarantine)} bots")
    
    # Close database connection
    await db.close_db()


if __name__ == "__main__":
    asyncio.run(migrate_invalid_platform_bots())
