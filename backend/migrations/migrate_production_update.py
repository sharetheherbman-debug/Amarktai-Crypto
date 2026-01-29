"""
Migration Script - Ensure All Required Fields Exist
Run this script to update existing bot and trade records with new fields
"""

import asyncio
import logging
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_bots():
    """Ensure all bots have required fields for new features"""
    logger.info("Migrating bot records...")
    
    try:
        # Get all bots
        bots = await db.bots_collection.find({}, {"_id": 0}).to_list(10000)
        logger.info(f"Found {len(bots)} bots to check")
        
        updated_count = 0
        
        for bot in bots:
            bot_id = bot.get('id')
            updates = {}
            
            # Ensure equity_peak is set
            if 'equity_peak' not in bot or bot.get('equity_peak') is None:
                current_capital = bot.get('current_capital', bot.get('initial_capital', 1000))
                updates['equity_peak'] = current_capital
            
            # Ensure current_drawdown_pct is set
            if 'current_drawdown_pct' not in bot:
                updates['current_drawdown_pct'] = 0
            
            # Ensure deleted_at and deleted_by exist for deleted bots
            if bot.get('status') == 'deleted':
                if 'deleted_at' not in bot:
                    updates['deleted_at'] = datetime.now(timezone.utc).isoformat()
                if 'deleted_by' not in bot:
                    updates['deleted_by'] = bot.get('user_id', 'system')
            
            # Ensure quarantine_count exists
            if 'quarantine_count' not in bot:
                updates['quarantine_count'] = 0
            
            # Apply updates if any
            if updates:
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {"$set": updates}
                )
                updated_count += 1
                logger.debug(f"Updated bot {bot_id}: {list(updates.keys())}")
        
        logger.info(f"✅ Migrated {updated_count} bot records")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error migrating bots: {e}")
        return 0


async def migrate_trades():
    """Ensure all trades have fee fields"""
    logger.info("Migrating trade records...")
    
    try:
        # Get trades without fee fields
        trades = await db.trades_collection.find(
            {
                "$or": [
                    {"fee_amount": {"$exists": False}},
                    {"gross_pnl": {"$exists": False}},
                    {"net_pnl": {"$exists": False}}
                ]
            },
            {"_id": 0}
        ).to_list(10000)
        
        logger.info(f"Found {len(trades)} trades to migrate")
        
        updated_count = 0
        
        for trade in trades:
            trade_id = trade.get('id')
            updates = {}
            
            # Get existing profit_loss
            profit_loss = trade.get('profit_loss', 0)
            
            # Set fee fields if missing
            if 'fee_amount' not in trade:
                # Estimate fee based on exchange
                exchange = trade.get('exchange', 'binance').lower()
                from exchange_limits import get_fee_rate
                fee_rate = get_fee_rate(exchange, 'taker')
                
                # Estimate fee amount (rough approximation)
                trade_amount = trade.get('amount', 0) * trade.get('price', 0)
                fee_amount = trade_amount * fee_rate * 2  # Entry + exit
                
                updates['fee_amount'] = round(fee_amount, 2)
                updates['fee_rate'] = fee_rate
            
            # Set gross_pnl if missing (assume profit_loss already includes fees)
            if 'gross_pnl' not in trade:
                fee_amount = updates.get('fee_amount', trade.get('fee_amount', 0))
                updates['gross_pnl'] = round(profit_loss + fee_amount, 2)
            
            # Set net_pnl if missing
            if 'net_pnl' not in trade:
                updates['net_pnl'] = profit_loss  # profit_loss is already net
            
            # Apply updates if any
            if updates:
                await db.trades_collection.update_one(
                    {"id": trade_id},
                    {"$set": updates}
                )
                updated_count += 1
                logger.debug(f"Updated trade {trade_id}: {list(updates.keys())}")
        
        logger.info(f"✅ Migrated {updated_count} trade records")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error migrating trades: {e}")
        return 0


async def create_indexes():
    """Create indexes for performance"""
    logger.info("Creating indexes...")
    
    try:
        # Bot indexes
        await db.bots_collection.create_index([("user_id", 1), ("status", 1)])
        await db.bots_collection.create_index([("id", 1)])
        logger.info("✅ Created bot indexes")
        
        # Trade indexes
        await db.trades_collection.create_index([("bot_id", 1), ("timestamp", -1)])
        await db.trades_collection.create_index([("user_id", 1), ("status", 1)])
        logger.info("✅ Created trade indexes")
        
        # Training jobs indexes
        await db.training_jobs_collection.create_index([("bot_id", 1), ("status", 1)])
        await db.training_jobs_collection.create_index([("user_id", 1)])
        logger.info("✅ Created training job indexes")
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        return False


async def main():
    """Run all migrations"""
    logger.info("="*60)
    logger.info("Starting Amarktai Network Migration")
    logger.info("="*60)
    
    try:
        # Connect to database
        await db.connect()
        logger.info("✅ Connected to database")
        
        # Run migrations
        bot_count = await migrate_bots()
        trade_count = await migrate_trades()
        await create_indexes()
        
        logger.info("="*60)
        logger.info("Migration Summary:")
        logger.info(f"  Bots updated: {bot_count}")
        logger.info(f"  Trades updated: {trade_count}")
        logger.info("✅ Migration completed successfully!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    
    finally:
        # Close database connection
        await db.close_db()
        logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
