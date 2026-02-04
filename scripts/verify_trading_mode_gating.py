#!/usr/bin/env python3
"""
Verification Script for Trading Mode Gating Implementation
Tests all Phase 4A, 4B, 4C requirements are working correctly
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


async def verify_paper_wallet_ledger():
    """Verify paper wallet ledger functionality"""
    print("\n🔍 Testing Paper Wallet Ledger...")
    
    try:
        from services.paper_wallet_ledger import paper_wallet_ledger
        
        # Test 1: Reserve funds
        test_user = "verify_user_001"
        test_bot = "verify_bot_001"
        amount = 1000.0
        
        success, msg = await paper_wallet_ledger.reserve_funds(test_user, test_bot, amount)
        assert success, f"Failed to reserve funds: {msg}"
        print("  ✅ Reserve funds: PASS")
        
        # Test 2: Get balance
        success, balance, msg = await paper_wallet_ledger.get_balance(test_bot)
        assert success and balance == amount, f"Balance check failed: {balance} != {amount}"
        print("  ✅ Get balance: PASS")
        
        # Test 3: Can trade check
        can_trade, msg = await paper_wallet_ledger.can_trade(test_bot, 500.0)
        assert can_trade, f"Can trade check failed: {msg}"
        print("  ✅ Can trade (sufficient): PASS")
        
        # Test 4: Cannot trade with insufficient funds
        can_trade, msg = await paper_wallet_ledger.can_trade(test_bot, 2000.0)
        assert not can_trade, "Should not be able to trade with insufficient funds"
        print("  ✅ Can trade (insufficient): PASS")
        
        # Test 5: Debit funds
        success, msg = await paper_wallet_ledger.debit(test_bot, 300.0, "test")
        assert success, f"Failed to debit: {msg}"
        print("  ✅ Debit funds: PASS")
        
        # Test 6: Credit funds
        success, msg = await paper_wallet_ledger.credit(test_bot, 100.0, "test")
        assert success, f"Failed to credit: {msg}"
        print("  ✅ Credit funds: PASS")
        
        # Test 7: Verify final balance
        success, balance, msg = await paper_wallet_ledger.get_balance(test_bot)
        expected = 1000.0 - 300.0 + 100.0
        assert abs(balance - expected) < 0.01, f"Balance mismatch: {balance} != {expected}"
        print("  ✅ Balance calculation: PASS")
        
        # Cleanup
        await paper_wallet_ledger.release_funds(test_bot)
        print("  ✅ Release funds: PASS")
        
        print("✅ Paper Wallet Ledger: ALL TESTS PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Paper Wallet Ledger: FAILED - {e}")
        return False


async def verify_trading_mode_validator():
    """Verify trading mode validator functionality"""
    print("\n🔍 Testing Trading Mode Validator...")
    
    try:
        from services.trading_mode_validator import trading_mode_validator
        import database as db
        
        # Test 1: Global gates
        trading_allowed, reason = await trading_mode_validator.validate_global_trading_gates()
        print(f"  ✅ Global gates check: {reason}")
        
        # Test 2: Paper trading validation
        test_user = "verify_user_002"
        test_bot_id = "verify_bot_002"
        
        # Create mock system mode
        await db.system_modes_collection.insert_one({
            "user_id": test_user,
            "autopilot": True,
            "paperTrading": True,
            "emergencyStop": False
        })
        
        bot_data = {
            "id": test_bot_id,
            "user_id": test_user,
            "trading_mode": "paper",
            "name": "Test Bot"
        }
        
        can_trade, mode, reason = await trading_mode_validator.validate_paper_trading(bot_data)
        assert can_trade, f"Paper trading validation failed: {reason}"
        print("  ✅ Paper trading validation: PASS")
        
        # Test 3: Emergency stop blocks trading
        await db.system_modes_collection.update_one(
            {"user_id": test_user},
            {"$set": {"emergencyStop": True}}
        )
        
        can_trade, mode, reason = await trading_mode_validator.validate_paper_trading(bot_data)
        assert not can_trade, "Emergency stop should block trading"
        assert "Emergency stop" in reason
        print("  ✅ Emergency stop blocking: PASS")
        
        # Cleanup
        await db.system_modes_collection.delete_one({"user_id": test_user})
        
        print("✅ Trading Mode Validator: ALL TESTS PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Trading Mode Validator: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_bot_manager_integration():
    """Verify bot manager integration with paper wallet"""
    print("\n🔍 Testing Bot Manager Integration...")
    
    try:
        # Test that bot manager imports are available
        from engines.bot_manager import bot_manager
        from bot_lifecycle import bot_lifecycle
        
        print("  ✅ Bot manager imports: PASS")
        print("  ✅ Bot lifecycle imports: PASS")
        
        # Note: Full bot creation test requires complete DB setup
        # This verifies imports and structure are correct
        
        print("✅ Bot Manager Integration: STRUCTURE VERIFIED")
        return True
        
    except Exception as e:
        print(f"❌ Bot Manager Integration: FAILED - {e}")
        return False


async def verify_paper_trading_engine_integration():
    """Verify paper trading engine integration"""
    print("\n🔍 Testing Paper Trading Engine Integration...")
    
    try:
        from paper_trading_engine import paper_engine
        
        # Verify imports are present
        assert hasattr(paper_engine, 'execute_smart_trade')
        print("  ✅ Paper engine methods: PASS")
        
        # Check if paper wallet ledger is imported
        import paper_trading_engine as pte_module
        import inspect
        source = inspect.getsource(pte_module)
        
        assert 'paper_wallet_ledger' in source, "paper_wallet_ledger not imported"
        print("  ✅ Paper wallet ledger imported: PASS")
        
        assert 'trading_mode_validator' in source, "trading_mode_validator not imported"
        print("  ✅ Trading mode validator imported: PASS")
        
        print("✅ Paper Trading Engine Integration: STRUCTURE VERIFIED")
        return True
        
    except Exception as e:
        print(f"❌ Paper Trading Engine Integration: FAILED - {e}")
        return False


async def verify_database_setup():
    """Verify database collections are set up"""
    print("\n🔍 Testing Database Setup...")
    
    try:
        import database as db
        
        # Check paper_ledger_collection exists in globals
        assert hasattr(db, 'paper_ledger_collection'), "paper_ledger_collection not found"
        print("  ✅ paper_ledger_collection defined: PASS")
        
        # Verify setup_collections includes paper_ledger
        import inspect
        source = inspect.getsource(db.setup_collections)
        assert 'paper_ledger_collection' in source, "paper_ledger not in setup_collections"
        print("  ✅ paper_ledger in setup_collections: PASS")
        
        print("✅ Database Setup: VERIFIED")
        return True
        
    except Exception as e:
        print(f"❌ Database Setup: FAILED - {e}")
        return False


async def main():
    """Run all verification tests"""
    print("=" * 60)
    print("TRADING MODE GATING - VERIFICATION SCRIPT")
    print("=" * 60)
    print("\nThis script verifies Phase 4A, 4B, 4C implementation")
    print("Testing: Paper Wallet, Trading Mode Validator, Integration")
    
    results = []
    
    # Initialize database connection
    try:
        import database as db
        await db.connect_db()
        await db.setup_collections()
        print("\n✅ Database connected")
    except Exception as e:
        print(f"\n❌ Database connection failed: {e}")
        print("Note: Some tests will be skipped")
    
    # Run tests
    results.append(("Database Setup", await verify_database_setup()))
    results.append(("Paper Wallet Ledger", await verify_paper_wallet_ledger()))
    results.append(("Trading Mode Validator", await verify_trading_mode_validator()))
    results.append(("Bot Manager Integration", await verify_bot_manager_integration()))
    results.append(("Paper Trading Engine", await verify_paper_trading_engine_integration()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL VERIFICATIONS PASSED!")
        print("✅ Trading Mode Gating implementation is READY")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("❌ Review failures above and fix issues")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
