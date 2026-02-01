#!/usr/bin/env python
"""
Test script for trading mode gates
Verifies that gates properly block/allow trading based on environment variables
"""

import os
import sys

# Set minimal environment before importing
os.environ['MONGO_URI'] = 'mongodb://localhost:27017'
os.environ['MONGO_DB_NAME'] = 'test'

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


def test_basic_imports():
    """Test that we can import the gate functions"""
    print("\n" + "="*60)
    print("TEST 0: Basic Imports")
    print("="*60)
    
    try:
        from utils.env_utils import env_bool
        print("✓ env_utils imported successfully")
        
        # Test basic gate checks (without database)
        from utils.trading_gates import (
            check_trading_mode_enabled,
            check_autopilot_gates,
            TradingGateError
        )
        print("✓ trading_gates functions imported successfully")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_trading_mode_gates():
    """Test trading mode gate checks"""
    print("\n" + "="*60)
    print("TEST 1: Trading Mode Gates")
    print("="*60)
    
    from utils.trading_gates import check_trading_mode_enabled
    
    # Test 1: No modes enabled
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '0'
    enabled, reason = check_trading_mode_enabled()
    print(f"\n✓ PAPER_TRADING=0, LIVE_TRADING=0")
    print(f"  Result: enabled={enabled}, reason='{reason}'")
    assert not enabled, "Should not allow trading with both modes disabled"
    
    # Test 2: Paper trading enabled
    os.environ['PAPER_TRADING'] = '1'
    os.environ['LIVE_TRADING'] = '0'
    enabled, reason = check_trading_mode_enabled()
    print(f"\n✓ PAPER_TRADING=1, LIVE_TRADING=0")
    print(f"  Result: enabled={enabled}, mode='{reason}'")
    assert enabled and reason == "paper", "Should allow paper trading"
    
    # Test 3: Live trading enabled
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '1'
    enabled, reason = check_trading_mode_enabled()
    print(f"\n✓ PAPER_TRADING=0, LIVE_TRADING=1")
    print(f"  Result: enabled={enabled}, mode='{reason}'")
    assert enabled and reason == "live", "Should allow live trading"
    
    # Test 4: Both enabled (should prefer paper)
    os.environ['PAPER_TRADING'] = '1'
    os.environ['LIVE_TRADING'] = '1'
    enabled, reason = check_trading_mode_enabled()
    print(f"\n✓ PAPER_TRADING=1, LIVE_TRADING=1")
    print(f"  Result: enabled={enabled}, mode='{reason}'")
    assert enabled, "Should allow trading with either mode enabled"
    
    print("\n✅ All trading mode gate tests passed!")


def test_enforce_gates():
    """Test enforcement of gates"""
    print("\n" + "="*60)
    print("TEST 2: Gate Enforcement")
    print("="*60)
    
    from utils.trading_gates import enforce_trading_gates, TradingGateError
    
    # Test 1: Should raise error when disabled
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '0'
    print(f"\n✓ Testing enforce_trading_gates() with no modes enabled")
    try:
        enforce_trading_gates()
        assert False, "Should have raised TradingGateError"
    except TradingGateError as e:
        print(f"  Correctly raised error: {e}")
    
    # Test 2: Should pass when paper enabled
    os.environ['PAPER_TRADING'] = '1'
    print(f"\n✓ Testing enforce_trading_gates('paper') with PAPER_TRADING=1")
    try:
        enforce_trading_gates("paper")
        print(f"  Correctly allowed paper trading")
    except TradingGateError:
        assert False, "Should not have raised error"
    
    # Test 3: Should fail live when not enabled
    os.environ['LIVE_TRADING'] = '0'
    print(f"\n✓ Testing enforce_trading_gates('live') with LIVE_TRADING=0")
    try:
        enforce_trading_gates("live")
        assert False, "Should have raised TradingGateError"
    except TradingGateError as e:
        print(f"  Correctly raised error: {e}")
    
    print("\n✅ All gate enforcement tests passed!")


def test_autopilot_gates():
    """Test autopilot gate checks"""
    print("\n" + "="*60)
    print("TEST 3: Autopilot Gates")
    print("="*60)
    
    from utils.trading_gates import check_autopilot_gates
    
    # Test 1: Autopilot disabled
    os.environ['AUTOPILOT_ENABLED'] = '0'
    os.environ['PAPER_TRADING'] = '1'
    can_run, msg = check_autopilot_gates()
    print(f"\n✓ AUTOPILOT_ENABLED=0, PAPER_TRADING=1")
    print(f"  Result: can_run={can_run}, msg='{msg}'")
    assert not can_run, "Should not allow autopilot when disabled"
    
    # Test 2: Autopilot enabled but no trading mode
    os.environ['AUTOPILOT_ENABLED'] = '1'
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '0'
    can_run, msg = check_autopilot_gates()
    print(f"\n✓ AUTOPILOT_ENABLED=1, PAPER_TRADING=0, LIVE_TRADING=0")
    print(f"  Result: can_run={can_run}, msg='{msg}'")
    assert not can_run, "Should not allow autopilot without trading mode"
    
    # Test 3: Autopilot enabled with paper trading
    os.environ['AUTOPILOT_ENABLED'] = '1'
    os.environ['PAPER_TRADING'] = '1'
    can_run, msg = check_autopilot_gates()
    print(f"\n✓ AUTOPILOT_ENABLED=1, PAPER_TRADING=1")
    print(f"  Result: can_run={can_run}, msg='{msg}'")
    assert can_run, "Should allow autopilot with paper trading"
    
    # Test 4: Autopilot enabled with live trading
    os.environ['AUTOPILOT_ENABLED'] = '1'
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '1'
    can_run, msg = check_autopilot_gates()
    print(f"\n✓ AUTOPILOT_ENABLED=1, LIVE_TRADING=1")
    print(f"  Result: can_run={can_run}, msg='{msg}'")
    assert can_run, "Should allow autopilot with live trading"
    
    print("\n✅ All autopilot gate tests passed!")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("TRADING MODE GATES - TEST SUITE")
    print("="*60)
    
    try:
        if not test_basic_imports():
            print("\n❌ Import test failed")
            return 1
        
        test_trading_mode_gates()
        test_enforce_gates()
        test_autopilot_gates()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nTrading mode gates are working correctly:")
        print("  ✓ Trading blocked when PAPER_TRADING=0 AND LIVE_TRADING=0")
        print("  ✓ Paper trading allowed when PAPER_TRADING=1")
        print("  ✓ Live trading allowed when LIVE_TRADING=1")
        print("  ✓ Autopilot blocked unless AUTOPILOT_ENABLED=1 AND trading mode enabled")
        print("  ✓ Gate enforcement raises clear errors")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
