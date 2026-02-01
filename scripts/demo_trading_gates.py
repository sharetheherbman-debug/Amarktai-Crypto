#!/usr/bin/env python
"""
Trading Gates Demo Script
Demonstrates the gate checks in action with various scenarios
"""

import os
import sys

# Set minimal environment
os.environ['MONGO_URI'] = 'mongodb://localhost:27017'
os.environ['MONGO_DB_NAME'] = 'test'

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from utils.trading_gates import (
    check_trading_mode_enabled,
    check_autopilot_gates,
    enforce_trading_gates,
    TradingGateError
)


def demo_scenario_1():
    """Scenario 1: System freshly deployed, no flags set"""
    print("\n" + "="*60)
    print("SCENARIO 1: Fresh Deployment (All flags disabled)")
    print("="*60)
    
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '0'
    os.environ['AUTOPILOT_ENABLED'] = '0'
    
    print("\n📋 Configuration:")
    print("   PAPER_TRADING=0")
    print("   LIVE_TRADING=0")
    print("   AUTOPILOT_ENABLED=0")
    
    print("\n🔍 Checking trading mode...")
    enabled, reason = check_trading_mode_enabled()
    print(f"   Result: {'✅ ALLOWED' if enabled else '❌ BLOCKED'}")
    print(f"   Reason: {reason}")
    
    print("\n🤖 Checking autopilot...")
    can_run, msg = check_autopilot_gates()
    print(f"   Result: {'✅ ALLOWED' if can_run else '❌ BLOCKED'}")
    print(f"   Reason: {msg}")
    
    print("\n💼 Attempting to execute trade...")
    try:
        enforce_trading_gates()
        print("   ✅ Trade allowed")
    except TradingGateError as e:
        print(f"   ❌ Trade blocked: {e}")
    
    print("\n✅ Expected behavior: ALL trading blocked for safety")


def demo_scenario_2():
    """Scenario 2: Paper trading enabled for testing"""
    print("\n" + "="*60)
    print("SCENARIO 2: Testing Phase (Paper trading enabled)")
    print("="*60)
    
    os.environ['PAPER_TRADING'] = '1'
    os.environ['LIVE_TRADING'] = '0'
    os.environ['AUTOPILOT_ENABLED'] = '0'
    
    print("\n📋 Configuration:")
    print("   PAPER_TRADING=1")
    print("   LIVE_TRADING=0")
    print("   AUTOPILOT_ENABLED=0")
    
    print("\n🔍 Checking trading mode...")
    enabled, reason = check_trading_mode_enabled()
    print(f"   Result: {'✅ ALLOWED' if enabled else '❌ BLOCKED'}")
    print(f"   Mode: {reason}")
    
    print("\n🤖 Checking autopilot...")
    can_run, msg = check_autopilot_gates()
    print(f"   Result: {'✅ ALLOWED' if can_run else '❌ BLOCKED'}")
    print(f"   Reason: {msg}")
    
    print("\n💼 Attempting to execute paper trade...")
    try:
        enforce_trading_gates("paper")
        print("   ✅ Paper trade allowed")
    except TradingGateError as e:
        print(f"   ❌ Trade blocked: {e}")
    
    print("\n💰 Attempting to execute live trade...")
    try:
        enforce_trading_gates("live")
        print("   ✅ Live trade allowed")
    except TradingGateError as e:
        print(f"   ❌ Live trade blocked: {e}")
    
    print("\n✅ Expected behavior: Paper trading works, live trading blocked")


def demo_scenario_3():
    """Scenario 3: Autopilot with paper trading"""
    print("\n" + "="*60)
    print("SCENARIO 3: Automated Testing (Autopilot + Paper Trading)")
    print("="*60)
    
    os.environ['PAPER_TRADING'] = '1'
    os.environ['LIVE_TRADING'] = '0'
    os.environ['AUTOPILOT_ENABLED'] = '1'
    
    print("\n📋 Configuration:")
    print("   PAPER_TRADING=1")
    print("   LIVE_TRADING=0")
    print("   AUTOPILOT_ENABLED=1")
    
    print("\n🔍 Checking trading mode...")
    enabled, reason = check_trading_mode_enabled()
    print(f"   Result: {'✅ ALLOWED' if enabled else '❌ BLOCKED'}")
    print(f"   Mode: {reason}")
    
    print("\n🤖 Checking autopilot...")
    can_run, msg = check_autopilot_gates()
    print(f"   Result: {'✅ ALLOWED' if can_run else '❌ BLOCKED'}")
    print(f"   Message: {msg}")
    
    print("\n💼 Attempting to execute trade...")
    try:
        enforce_trading_gates()
        print("   ✅ Trade allowed")
    except TradingGateError as e:
        print(f"   ❌ Trade blocked: {e}")
    
    print("\n✅ Expected behavior: Autopilot can manage paper trading bots")


def demo_scenario_4():
    """Scenario 4: Live trading enabled but autopilot off"""
    print("\n" + "="*60)
    print("SCENARIO 4: Manual Live Trading (No Autopilot)")
    print("="*60)
    
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '1'
    os.environ['AUTOPILOT_ENABLED'] = '0'
    
    print("\n📋 Configuration:")
    print("   PAPER_TRADING=0")
    print("   LIVE_TRADING=1")
    print("   AUTOPILOT_ENABLED=0")
    
    print("\n🔍 Checking trading mode...")
    enabled, reason = check_trading_mode_enabled()
    print(f"   Result: {'✅ ALLOWED' if enabled else '❌ BLOCKED'}")
    print(f"   Mode: {reason}")
    
    print("\n🤖 Checking autopilot...")
    can_run, msg = check_autopilot_gates()
    print(f"   Result: {'✅ ALLOWED' if can_run else '❌ BLOCKED'}")
    print(f"   Reason: {msg}")
    
    print("\n💰 Attempting to execute live trade...")
    try:
        enforce_trading_gates("live")
        print("   ✅ Live trade allowed (API keys required)")
    except TradingGateError as e:
        print(f"   ❌ Live trade blocked: {e}")
    
    print("\n✅ Expected behavior: Live trading allowed, autopilot blocked")


def demo_scenario_5():
    """Scenario 5: Full production with autopilot"""
    print("\n" + "="*60)
    print("SCENARIO 5: Full Production (Autopilot + Live Trading)")
    print("="*60)
    
    os.environ['PAPER_TRADING'] = '0'
    os.environ['LIVE_TRADING'] = '1'
    os.environ['AUTOPILOT_ENABLED'] = '1'
    
    print("\n📋 Configuration:")
    print("   PAPER_TRADING=0")
    print("   LIVE_TRADING=1")
    print("   AUTOPILOT_ENABLED=1")
    print("\n⚠️  WARNING: This is PRODUCTION mode with REAL MONEY!")
    
    print("\n🔍 Checking trading mode...")
    enabled, reason = check_trading_mode_enabled()
    print(f"   Result: {'✅ ALLOWED' if enabled else '❌ BLOCKED'}")
    print(f"   Mode: {reason}")
    
    print("\n🤖 Checking autopilot...")
    can_run, msg = check_autopilot_gates()
    print(f"   Result: {'✅ ALLOWED' if can_run else '❌ BLOCKED'}")
    print(f"   Message: {msg}")
    
    print("\n💰 Attempting to execute live trade...")
    try:
        enforce_trading_gates("live")
        print("   ✅ Live trade allowed (API keys + connection test required)")
    except TradingGateError as e:
        print(f"   ❌ Live trade blocked: {e}")
    
    print("\n✅ Expected behavior: Full system operational with all safety checks")


def main():
    """Run all demo scenarios"""
    print("\n" + "="*60)
    print("TRADING MODE GATES - DEMONSTRATION")
    print("="*60)
    print("\nThis script demonstrates how the trading gates work")
    print("in different deployment scenarios.\n")
    
    demo_scenario_1()
    demo_scenario_2()
    demo_scenario_3()
    demo_scenario_4()
    demo_scenario_5()
    
    print("\n" + "="*60)
    print("✅ DEMONSTRATION COMPLETE")
    print("="*60)
    print("\nKey Takeaways:")
    print("  1. System is safe-by-default (blocks trading unless explicitly enabled)")
    print("  2. Paper trading can be enabled independently for testing")
    print("  3. Live trading requires explicit flag + API key validation")
    print("  4. Autopilot requires both AUTOPILOT_ENABLED=1 AND trading mode")
    print("  5. All gates log clear errors when blocking operations")
    print()


if __name__ == "__main__":
    main()
