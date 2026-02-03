"""
Bot Reconciliation Script
Finds and fixes bots with missing or inconsistent user_id field
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db
from logger_config import logger


async def reconcile_bots():
    """
    Find and report bots with issues:
    1. Missing user_id field
    2. user_id is None or empty
    3. Inconsistent status for active bots
    """
    
    logger.info("🔍 Starting bot reconciliation...")
    
    # Find all bots
    all_bots = await db.bots_collection.find({}, {"_id": 0, "id": 1, "user_id": 1, "name": 1, "status": 1}).to_list(10000)
    
    logger.info(f"📊 Total bots in database: {len(all_bots)}")
    
    # Issues tracking
    issues = {
        "missing_user_id": [],
        "empty_user_id": [],
        "active_without_status": []
    }
    
    for bot in all_bots:
        bot_id = bot.get("id", "unknown")
        bot_name = bot.get("name", "unnamed")
        
        # Check for missing user_id field
        if "user_id" not in bot:
            issues["missing_user_id"].append({
                "id": bot_id,
                "name": bot_name,
                "status": bot.get("status")
            })
            continue
        
        # Check for empty user_id
        user_id = bot.get("user_id")
        if not user_id or user_id == "":
            issues["empty_user_id"].append({
                "id": bot_id,
                "name": bot_name,
                "status": bot.get("status")
            })
            continue
        
        # Check for active bots without proper status
        status = bot.get("status")
        if status == "active" and not status:
            issues["active_without_status"].append({
                "id": bot_id,
                "name": bot_name,
                "user_id": user_id
            })
    
    # Report issues
    print("\n" + "="*80)
    print("BOT RECONCILIATION REPORT")
    print("="*80)
    
    if issues["missing_user_id"]:
        print(f"\n⚠️  Found {len(issues['missing_user_id'])} bots with MISSING user_id field:")
        for bot in issues["missing_user_id"]:
            print(f"   - ID: {bot['id']}, Name: {bot['name']}, Status: {bot['status']}")
        print("\n   Action: These bots should be quarantined and manually assigned to users")
    else:
        print("\n✅ No bots with missing user_id field")
    
    if issues["empty_user_id"]:
        print(f"\n⚠️  Found {len(issues['empty_user_id'])} bots with EMPTY user_id:")
        for bot in issues["empty_user_id"]:
            print(f"   - ID: {bot['id']}, Name: {bot['name']}, Status: {bot['status']}")
        print("\n   Action: These bots should be quarantined and manually assigned to users")
    else:
        print("\n✅ No bots with empty user_id")
    
    if issues["active_without_status"]:
        print(f"\n⚠️  Found {len(issues['active_without_status'])} active bots with status issues:")
        for bot in issues["active_without_status"]:
            print(f"   - ID: {bot['id']}, Name: {bot['name']}, User: {bot['user_id'][:8]}...")
    else:
        print("\n✅ No active bots with status issues")
    
    # Summary by user
    print("\n" + "="*80)
    print("BOTS BY USER")
    print("="*80)
    
    user_bots = {}
    for bot in all_bots:
        user_id = bot.get("user_id", "NO_USER")
        status = bot.get("status", "unknown")
        
        if user_id not in user_bots:
            user_bots[user_id] = {"total": 0, "active": 0, "paused": 0, "stopped": 0}
        
        user_bots[user_id]["total"] += 1
        if status == "active":
            user_bots[user_id]["active"] += 1
        elif status == "paused":
            user_bots[user_id]["paused"] += 1
        elif status in ["stopped", "deleted"]:
            user_bots[user_id]["stopped"] += 1
    
    for user_id, counts in sorted(user_bots.items()):
        user_display = user_id[:8] + "..." if user_id != "NO_USER" else "NO_USER"
        print(f"\nUser {user_display}:")
        print(f"   Total: {counts['total']}, Active: {counts['active']}, Paused: {counts['paused']}, Stopped: {counts['stopped']}")
    
    # Offer to fix issues
    total_issues = len(issues["missing_user_id"]) + len(issues["empty_user_id"])
    
    if total_issues > 0:
        print("\n" + "="*80)
        print(f"⚠️  FOUND {total_issues} ORPHANED BOTS")
        print("="*80)
        print("\nThese bots will be quarantined (status set to 'quarantined')")
        print("and trading_enabled set to False to prevent trading.")
        print("\nTo fix manually, assign proper user_id and change status back to active.")
        
        response = input("\nQuarantine these bots now? (yes/no): ").strip().lower()
        
        if response == "yes":
            await quarantine_orphaned_bots(issues)
        else:
            print("\n❌ Skipped quarantine. Run this script again to quarantine later.")
    else:
        print("\n" + "="*80)
        print("✅ ALL BOTS ARE PROPERLY CONFIGURED")
        print("="*80)
    
    print()


async def quarantine_orphaned_bots(issues):
    """
    Quarantine bots with missing or empty user_id
    """
    logger.info("🚨 Quarantining orphaned bots...")
    
    quarantined_count = 0
    
    # Quarantine bots with missing user_id
    for bot in issues["missing_user_id"]:
        result = await db.bots_collection.update_one(
            {"id": bot["id"]},
            {
                "$set": {
                    "status": "quarantined",
                    "trading_enabled": False,
                    "quarantine_reason": "Missing user_id field",
                    "user_id": "ORPHANED"  # Temporary marker
                }
            }
        )
        if result.modified_count > 0:
            quarantined_count += 1
            logger.info(f"✅ Quarantined bot {bot['id']} (missing user_id)")
    
    # Quarantine bots with empty user_id
    for bot in issues["empty_user_id"]:
        result = await db.bots_collection.update_one(
            {"id": bot["id"]},
            {
                "$set": {
                    "status": "quarantined",
                    "trading_enabled": False,
                    "quarantine_reason": "Empty user_id field",
                    "user_id": "ORPHANED"  # Temporary marker
                }
            }
        )
        if result.modified_count > 0:
            quarantined_count += 1
            logger.info(f"✅ Quarantined bot {bot['id']} (empty user_id)")
    
    print(f"\n✅ Quarantined {quarantined_count} orphaned bots")
    print("\nThese bots are now:")
    print("  - Status: quarantined")
    print("  - Trading: disabled")
    print("  - User ID: ORPHANED (temporary marker)")
    print("\nTo fix, update the user_id to the correct user and change status back to active.")


async def main():
    try:
        await reconcile_bots()
    except Exception as e:
        logger.error(f"❌ Reconciliation error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
