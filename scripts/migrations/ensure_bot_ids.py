#!/usr/bin/env python3
"""
Migration: Ensure all bots have proper UUID string IDs
Fixes any bots with missing or null 'id' field
"""

import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'backend'))

import database as db
from database import init_db


async def ensure_bot_ids():
    """Ensure all bots have proper UUID string IDs"""
    
    print("🔧 Migration: Ensuring all bots have proper UUID string IDs")
    print("=" * 70)
    
    # Initialize database connection
    await init_db()
    
    # Find bots without proper 'id' field
    bots_without_id = await db.bots_collection.find({
        "$or": [
            {"id": {"$exists": False}},
            {"id": None},
            {"id": ""}
        ]
    }).to_list(length=10000)
    
    print(f"\n📊 Found {len(bots_without_id)} bots without proper ID")
    
    if not bots_without_id:
        print("✅ All bots have proper IDs. No migration needed.")
        return
    
    # Fix each bot
    fixed_count = 0
    for bot in bots_without_id:
        bot_objectid = bot.get("_id")
        new_id = str(uuid4())
        
        result = await db.bots_collection.update_one(
            {"_id": bot_objectid},
            {
                "$set": {
                    "id": new_id,
                    "migrated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            fixed_count += 1
            print(f"  ✓ Fixed bot {bot_objectid} -> {new_id}")
    
    print(f"\n✅ Migration complete! Fixed {fixed_count} bots")
    
    # Verify unique index exists on 'id' field
    print("\n🔍 Verifying indexes...")
    
    indexes = await db.bots_collection.index_information()
    has_id_index = any(
        'id' in str(idx.get('key', [])) for idx in indexes.values()
    )
    
    if not has_id_index:
        print("  ⚠️  Creating unique index on 'id' field...")
        await db.bots_collection.create_index("id", unique=True, sparse=False)
        print("  ✅ Index created")
    else:
        print("  ✅ Index already exists")
    
    print("\n🎉 All done!")


if __name__ == "__main__":
    try:
        asyncio.run(ensure_bot_ids())
    except KeyboardInterrupt:
        print("\n❌ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
