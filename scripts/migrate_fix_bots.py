#!/usr/bin/env python3
"""
Migration Script: Fix Bots
- Assigns UUID to bots missing 'id'
- Creates unique indexes
- Clamps bot counts to caps (Luno: 5, others: 10)
- Pauses and quarantines excess bots deterministically
- Rebuilds profit ledgers
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from uuid import uuid4

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db
from rules import SUPPORTED_EXCHANGES, BOT_CAPS
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def fix_bot_ids():
    """Ensure all bots have non-null unique id"""
    logger.info("Step 1: Fixing bot IDs...")
    
    # Find bots without id
    bots_without_id = await db.bots_collection.find({"id": None}).to_list(10000)
    
    if not bots_without_id:
        bots_without_id = await db.bots_collection.find({"id": {"$exists": False}}).to_list(10000)
    
    logger.info(f"Found {len(bots_without_id)} bots without id")
    
    fixed = 0
    for bot in bots_without_id:
        new_id = str(uuid4())
        try:
            await db.bots_collection.update_one(
                {"_id": bot["_id"]},
                {"$set": {"id": new_id}}
            )
            fixed += 1
            logger.info(f"  Assigned id {new_id} to bot {bot.get('name', 'unknown')}")
        except Exception as e:
            logger.error(f"  Error fixing bot {bot.get('_id')}: {e}")
    
    logger.info(f"✅ Fixed {fixed} bots with missing IDs\n")
    return fixed


async def create_indexes():
    """Create unique indexes on bots collection"""
    logger.info("Step 2: Creating indexes...")
    
    try:
        # Create unique index on id
        await db.bots_collection.create_index("id", unique=True)
        logger.info("  ✅ Created unique index on 'id'")
        
        # Create compound indexes for queries
        await db.bots_collection.create_index([("user_id", 1), ("exchange", 1)])
        logger.info("  ✅ Created compound index on 'user_id' and 'exchange'")
        
        await db.bots_collection.create_index([("user_id", 1), ("status", 1)])
        logger.info("  ✅ Created compound index on 'user_id' and 'status'")
        
        # Profit ledger collection index
        await db.profit_ledger_collection.create_index("ledger_key", unique=True)
        logger.info("  ✅ Created unique index on profit_ledger.ledger_key")
        
    except Exception as e:
        logger.warning(f"  Index creation warning (may already exist): {e}")
    
    logger.info("✅ Indexes verified\n")


async def clamp_bot_counts():
    """Clamp bot counts to caps, pause and quarantine excess"""
    logger.info("Step 3: Clamping bot counts to caps...")
    
    # Get all users
    users = await db.users_collection.find({}, {"id": 1, "email": 1}).to_list(1000)
    
    total_quarantined = 0
    
    for user in users:
        user_id = user.get('id')
        user_email = user.get('email', 'unknown')
        
        logger.info(f"\nProcessing user: {user_email} ({user_id})")
        
        for exchange in SUPPORTED_EXCHANGES:
            max_bots = BOT_CAPS.get(exchange, 10)
            
            # Get active bots for this user/exchange
            bots = await db.bots_collection.find({
                "user_id": user_id,
                "exchange": exchange,
                "status": {"$nin": ["deleted", "quarantined"]}
            }).sort("created_at", 1).to_list(1000)  # Oldest first
            
            if len(bots) <= max_bots:
                logger.info(f"  {exchange}: {len(bots)}/{max_bots} bots - OK")
                continue
            
            # Too many bots - quarantine the newest ones
            excess_count = len(bots) - max_bots
            bots_to_keep = bots[:max_bots]
            bots_to_quarantine = bots[max_bots:]
            
            logger.warning(f"  {exchange}: {len(bots)}/{max_bots} bots - OVER LIMIT by {excess_count}")
            logger.info(f"    Keeping {len(bots_to_keep)} oldest bots")
            logger.info(f"    Quarantining {len(bots_to_quarantine)} newest bots")
            
            for bot in bots_to_quarantine:
                try:
                    await db.bots_collection.update_one(
                        {"id": bot["id"]},
                        {
                            "$set": {
                                "status": "quarantined",
                                "quarantined_at": datetime.now(timezone.utc).isoformat(),
                                "quarantine_reason": f"BOT_CAP_EXCEEDED:{exchange}:max_{max_bots}",
                                "quarantine_by": "migration_clamp",
                                "previous_status": bot.get("status", "active")
                            }
                        }
                    )
                    total_quarantined += 1
                    logger.info(f"      ✅ Quarantined bot: {bot.get('name', bot['id'][:8])}")
                except Exception as e:
                    logger.error(f"      ❌ Error quarantining bot {bot['id']}: {e}")
    
    logger.info(f"\n✅ Total bots quarantined: {total_quarantined}\n")
    return total_quarantined


async def rebuild_profit_ledgers():
    """Rebuild profit ledgers from trades"""
    logger.info("Step 4: Rebuilding profit ledgers...")
    
    # Clear existing ledger
    await db.profit_ledger_collection.delete_many({})
    logger.info("  Cleared existing profit ledger")
    
    # Get all users
    users = await db.users_collection.find({}, {"id": 1}).to_list(1000)
    
    total_ledgers = 0
    
    for user in users:
        user_id = user.get('id')
        
        for exchange in SUPPORTED_EXCHANGES:
            for trading_mode in ['paper', 'live']:
                # Calculate profit
                trades = await db.trades_collection.find({
                    "user_id": user_id,
                    "exchange": exchange,
                    "trading_mode": trading_mode,
                    "status": "closed",
                    "profit_loss": {"$exists": True}
                }).to_list(10000)
                
                if not trades:
                    continue
                
                total_profit = sum(trade.get('profit_loss', 0) for trade in trades)
                
                # Create ledger entry
                ledger_key = f"{user_id}:{exchange}:{trading_mode}"
                
                try:
                    await db.profit_ledger_collection.insert_one({
                        "ledger_key": ledger_key,
                        "user_id": user_id,
                        "exchange": exchange,
                        "trading_mode": trading_mode,
                        "total_profit": total_profit,
                        "trade_count": len(trades),
                        "last_spawn_milestone": 0,  # Reset milestones
                        "total_spawns": 0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })
                    total_ledgers += 1
                    logger.info(f"  Created ledger: {exchange}:{trading_mode} = R{total_profit:.2f} ({len(trades)} trades)")
                except DuplicateKeyError:
                    pass
    
    logger.info(f"✅ Created {total_ledgers} profit ledger entries\n")
    return total_ledgers


async def print_summary():
    """Print summary of bot distribution"""
    logger.info("="*60)
    logger.info("MIGRATION SUMMARY")
    logger.info("="*60)
    
    users = await db.users_collection.find({}, {"id": 1, "email": 1}).to_list(1000)
    
    for user in users:
        user_id = user.get('id')
        user_email = user.get('email', 'unknown')
        
        logger.info(f"\nUser: {user_email}")
        
        for exchange in SUPPORTED_EXCHANGES:
            active = await db.bots_collection.count_documents({
                "user_id": user_id,
                "exchange": exchange,
                "status": {"$nin": ["deleted", "quarantined"]}
            })
            
            quarantined = await db.bots_collection.count_documents({
                "user_id": user_id,
                "exchange": exchange,
                "status": "quarantined"
            })
            
            max_bots = BOT_CAPS.get(exchange, 10)
            
            status = "✅ OK" if active <= max_bots else "❌ OVER"
            logger.info(f"  {exchange:10s}: {active:2d}/{max_bots:2d} active, {quarantined:2d} quarantined {status}")


async def main():
    """Run migration"""
    logger.info("="*60)
    logger.info("STARTING BOT MIGRATION")
    logger.info("="*60)
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Database: {os.getenv('MONGODB_URI', 'mongodb://localhost:27017')}")
    logger.info("="*60 + "\n")
    
    try:
        # Connect to database
        await db.init_db()
        
        # Run migration steps
        fixed_ids = await fix_bot_ids()
        await create_indexes()
        quarantined = await clamp_bot_counts()
        ledgers = await rebuild_profit_ledgers()
        
        # Print summary
        await print_summary()
        
        logger.info("\n" + "="*60)
        logger.info("MIGRATION COMPLETE")
        logger.info("="*60)
        logger.info(f"  Bot IDs fixed: {fixed_ids}")
        logger.info(f"  Bots quarantined: {quarantined}")
        logger.info(f"  Profit ledgers created: {ledgers}")
        logger.info("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
