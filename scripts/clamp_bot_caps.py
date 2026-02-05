#!/usr/bin/env python3
"""
Clamp Bot Caps Script
Enforces bot capacity limits across all users
Pauses/quarantines bots exceeding per-exchange caps
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db
from database import init_db
from rules.bot_rules import BOT_CAPS, SUPPORTED_EXCHANGES


async def clamp_bot_caps(dry_run: bool = True):
    """Clamp bot caps across all users"""
    
    mode_str = "DRY RUN" if dry_run else "LIVE MODE"
    print(f"🔧 Clamp Bot Caps - {mode_str}")
    print("=" * 70)
    
    # Initialize database connection
    await init_db()
    
    results = {
        "users_processed": 0,
        "bots_clamped": 0,
        "details": []
    }
    
    # Get all users
    users = await db.users_collection.find({}).to_list(length=None)
    
    print(f"\n📊 Processing {len(users)} users...")
    
    for user in users:
        user_id = user.get("id")
        if not user_id:
            continue
        
        results["users_processed"] += 1
        user_email = user.get("email", "unknown")
        
        # Check each exchange
        for exchange in SUPPORTED_EXCHANGES:
            max_bots = BOT_CAPS.get(exchange, 10)
            
            # Get user's bots on this exchange (active + paused, sorted by created_at)
            user_bots = await db.bots_collection.find({
                "user_id": user_id,
                "exchange": exchange,
                "status": {"$in": ["active", "paused"]}
            }).sort("created_at", 1).to_list(length=None)
            
            bot_count = len(user_bots)
            
            if bot_count > max_bots:
                # Clamp: Keep first max_bots, pause the rest
                bots_to_clamp = user_bots[max_bots:]
                
                print(f"\n⚠️  User {user_email} has {bot_count} {exchange} bots (cap: {max_bots})")
                print(f"   Clamping {len(bots_to_clamp)} excess bots")
                
                for bot in bots_to_clamp:
                    bot_id = bot.get("id")
                    bot_name = bot.get("name", "Unknown")
                    
                    if not dry_run:
                        await db.bots_collection.update_one(
                            {"id": bot_id},
                            {
                                "$set": {
                                    "status": "paused",
                                    "quarantine_reason": "CAP_EXCEEDED",
                                    "clamped_at": datetime.now(timezone.utc).isoformat(),
                                    "clamped_by_script": True
                                }
                            }
                        )
                    
                    print(f"     → Paused: {bot_name} ({bot_id})")
                    results["bots_clamped"] += 1
                
                results["details"].append({
                    "user_email": user_email,
                    "user_id": user_id,
                    "exchange": exchange,
                    "had": bot_count,
                    "cap": max_bots,
                    "clamped": len(bots_to_clamp)
                })
    
    print("\n" + "=" * 70)
    print(f"📊 Summary:")
    print(f"   Users processed: {results['users_processed']}")
    print(f"   Bots clamped: {results['bots_clamped']}")
    print(f"   Users affected: {len(results['details'])}")
    
    if results['details']:
        print("\n📋 Details:")
        for detail in results['details']:
            print(f"   • {detail['user_email']}: {detail['exchange']} {detail['had']}/{detail['cap']} " +
                  f"(clamped {detail['clamped']})")
    
    if dry_run:
        print("\n⚠️  DRY RUN - No changes were made")
        print("   Run with --execute flag to apply changes")
    else:
        print("\n✅ Bot caps enforced!")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clamp bot caps across all users")
    parser.add_argument("--execute", action="store_true", 
                       help="Execute changes (default is dry run)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(clamp_bot_caps(dry_run=not args.execute))
    except KeyboardInterrupt:
        print("\n❌ Script cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Script failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
