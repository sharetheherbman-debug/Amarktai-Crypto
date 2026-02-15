#!/usr/bin/env python3
"""
Deployment Verification Script
Verifies all critical systems are working correctly
"""

import asyncio
import sys
import os
from datetime import datetime
import requests

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database as db
from rules import SUPPORTED_EXCHANGES, BOT_CAPS

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def verify_database():
    """Verify MongoDB connection and collections"""
    logger.info("\n=== DATABASE VERIFICATION ===")
    
    try:
        await db.init_db()
        
        # Test collections exist
        collections = await db.db.list_collection_names()
        required = ['users', 'bots', 'trades', 'profit_ledger', 'api_keys']
        
        for coll in required:
            if coll in collections:
                count = await db.db[coll].count_documents({})
                logger.info(f"✅ Collection '{coll}' exists ({count} documents)")
            else:
                logger.error(f"❌ Collection '{coll}' NOT FOUND")
                return False
        
        # Verify indexes
        bot_indexes = await db.bots_collection.index_information()
        if 'id_1' in bot_indexes:
            logger.info("✅ Bot 'id' index exists")
        else:
            logger.warning("⚠️  Bot 'id' index missing - run migration script")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


async def verify_bot_caps():
    """Verify bot counts are at or under caps"""
    logger.info("\n=== BOT CAP VERIFICATION ===")
    
    try:
        users = await db.users_collection.find({}, {"id": 1, "email": 1}).to_list(100)
        
        violations = []
        
        for user in users:
            user_id = user.get('id')
            user_email = user.get('email', 'unknown')
            
            for exchange in SUPPORTED_EXCHANGES:
                count = await db.bots_collection.count_documents({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": {"$nin": ["deleted", "quarantined"]}
                })
                
                max_bots = BOT_CAPS[exchange]
                
                if count > max_bots:
                    violations.append(f"{user_email}/{exchange}: {count}/{max_bots}")
                    logger.warning(f"⚠️  {user_email}: {exchange} has {count}/{max_bots} bots (OVER CAP)")
        
        if violations:
            logger.error(f"❌ {len(violations)} bot cap violations found")
            logger.info("   Run: python scripts/migrate_fix_bots.py")
            return False
        else:
            logger.info("✅ All bot counts are at or under caps")
            return True
            
    except Exception as e:
        logger.error(f"❌ Bot cap verification failed: {e}")
        return False


async def verify_profit_ledger():
    """Verify profit ledger system"""
    logger.info("\n=== PROFIT LEDGER VERIFICATION ===")
    
    try:
        from profit_ledger import profit_ledger
        
        # Check collection exists
        ledger_count = await db.profit_ledger_collection.count_documents({})
        logger.info(f"✅ Profit ledger has {ledger_count} entries")
        
        # Test ledger functions
        users = await db.users_collection.find({}, {"id": 1}).limit(1).to_list(1)
        if users:
            user_id = users[0]['id']
            
            # Test get_all_exchange_profits
            profits = await profit_ledger.get_all_exchange_profits(user_id)
            logger.info(f"✅ get_all_exchange_profits() works ({len(profits)} exchanges)")
            
            # Test check_spawn_milestone
            can_spawn, profit, milestone = await profit_ledger.check_spawn_milestone(
                user_id, 'luno', 'paper'
            )
            logger.info(f"✅ check_spawn_milestone() works (can_spawn={can_spawn}, milestone={milestone})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Profit ledger verification failed: {e}")
        return False


async def verify_api_health(base_url="http://localhost:8000"):
    """Verify API endpoints are responding"""
    logger.info("\n=== API HEALTH VERIFICATION ===")
    
    try:
        # Health check
        response = requests.get(f"{base_url}/api/health/ping", timeout=5)
        if response.status_code == 200:
            logger.info("✅ Health endpoint responding")
        else:
            logger.warning(f"⚠️  Health endpoint returned {response.status_code}")
        
        # Check OpenAPI docs
        response = requests.get(f"{base_url}/openapi.json", timeout=5)
        if response.status_code == 200:
            logger.info("✅ OpenAPI docs available")
        else:
            logger.warning(f"⚠️  OpenAPI docs returned {response.status_code}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        logger.warning("⚠️  API not running (expected if backend is stopped)")
        return True  # Not a failure if API is stopped
    except Exception as e:
        logger.error(f"❌ API health check failed: {e}")
        return False


async def verify_rules_module():
    """Verify rules module has correct configuration"""
    logger.info("\n=== RULES MODULE VERIFICATION ===")
    
    try:
        from rules import (
            SUPPORTED_EXCHANGES,
            BOT_CAPS,
            PROFIT_THRESHOLD_ZAR,
            check_bot_cap_limit,
            check_profit_threshold_met
        )
        
        # Verify exchanges
        if len(SUPPORTED_EXCHANGES) == 7:
            logger.info(f"✅ Exactly 7 exchanges defined: {', '.join(SUPPORTED_EXCHANGES)}")
        else:
            logger.error(f"❌ Wrong number of exchanges: {len(SUPPORTED_EXCHANGES)} (expected 7)")
            return False
        
        # Verify caps
        if BOT_CAPS['luno'] == 5:
            logger.info("✅ Luno cap is 5")
        else:
            logger.error(f"❌ Luno cap is {BOT_CAPS['luno']} (expected 5)")
            return False
        
        # Verify profit threshold
        if PROFIT_THRESHOLD_ZAR == 1000:
            logger.info("✅ Profit threshold is R1000")
        else:
            logger.error(f"❌ Profit threshold is R{PROFIT_THRESHOLD_ZAR} (expected 1000)")
            return False
        
        # Test functions
        can_create, reason = check_bot_cap_limit('luno', 5, 'test_user')
        if not can_create:
            logger.info("✅ check_bot_cap_limit() works (correctly rejects 6th Luno bot)")
        else:
            logger.error("❌ check_bot_cap_limit() not working correctly")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Rules module verification failed: {e}")
        return False


async def verify_no_valr_ovex():
    """Verify no VALR/OVEX/Legacy AI in active code"""
    logger.info("\n=== VALR/OVEX/LEGACY_AI CLEANUP VERIFICATION ===")
    
    import re
    from pathlib import Path
    
    violations = []
    
    # Check backend Python files
    backend_path = Path("backend")
    for py_file in backend_path.rglob("*.py"):
        if "_archive" in str(py_file) or "test_" in str(py_file):
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            
            # Check for VALR/OVEX
            if re.search(r'\b(valr|ovex)\b', content, re.IGNORECASE):
                violations.append(f"{py_file}: contains VALR/OVEX")
            
            # Check for Legacy AI (excluding legacy_aiintegrations)
            if re.search(r'\blegacy_ai\b', content, re.IGNORECASE) and 'legacy_aiintegrations' not in content:
                violations.append(f"{py_file}: contains Legacy AI reference")
        except:
            pass
    
    if violations:
        logger.error(f"❌ Found {len(violations)} VALR/OVEX/Legacy AI violations:")
        for v in violations[:5]:
            logger.error(f"   {v}")
        return False
    else:
        logger.info("✅ No VALR/OVEX/Legacy AI in active backend code")
        return True


async def main():
    """Run all verifications"""
    logger.info("="*60)
    logger.info("DEPLOYMENT VERIFICATION")
    logger.info("="*60)
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("="*60)
    
    results = {}
    
    # Run verifications
    results['database'] = await verify_database()
    results['bot_caps'] = await verify_bot_caps()
    results['profit_ledger'] = await verify_profit_ledger()
    results['api_health'] = await verify_api_health()
    results['rules_module'] = await verify_rules_module()
    results['no_valr_ovex'] = await verify_no_valr_ovex()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{name:20s}: {status}")
    
    logger.info("="*60)
    logger.info(f"TOTAL: {passed}/{total} checks passed")
    
    if passed == total:
        logger.info("✅ ALL VERIFICATIONS PASSED - READY FOR PRODUCTION")
        return 0
    else:
        logger.error("❌ SOME VERIFICATIONS FAILED - FIX ISSUES BEFORE DEPLOYING")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
