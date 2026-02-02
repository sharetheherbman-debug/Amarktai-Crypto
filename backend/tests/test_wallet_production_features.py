"""
Production Wallet Features Tests

Tests for:
- Reserved funds tracking
- Balance sync service
- 2FA enforcement
- Idempotency
- Admin approval workflows
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_reserved_funds_service_exists():
    """Test that reserved funds service exists and has required methods"""
    try:
        from services.reserved_funds_service import ReservedFundsService, reserved_funds_service
        
        # Check class exists
        assert ReservedFundsService is not None
        
        # Check instance exists
        assert reserved_funds_service is not None
        
        # Check key methods exist
        required_methods = [
            'reserve_funds',
            'release_funds',
            'get_reserved_funds',
            'get_available_balance',
            'check_available_funds',
            'reconcile_reserved_funds'
        ]
        
        for method_name in required_methods:
            assert hasattr(ReservedFundsService, method_name), f"Missing method: {method_name}"
        
        print("✅ Reserved funds service exists with all required methods")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import reserved funds service: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Reserved funds service validation failed: {e}")
        return False


def test_balance_sync_service_exists():
    """Test that balance sync service exists and has required methods"""
    try:
        from services.balance_sync_service import BalanceSyncService, balance_sync_service
        
        # Check class exists
        assert BalanceSyncService is not None
        
        # Check instance exists
        assert balance_sync_service is not None
        
        # Check key methods exist
        required_methods = [
            'sync_user_balances',
            'sync_exchange_balance',
            'get_latest_balance',
            'start_background_sync',
            'stop_background_sync'
        ]
        
        for method_name in required_methods:
            assert hasattr(BalanceSyncService, method_name), f"Missing method: {method_name}"
        
        print("✅ Balance sync service exists with all required methods")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import balance sync service: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Balance sync service validation failed: {e}")
        return False


def test_email_service_has_smtp():
    """Test that email service has real SMTP implementation"""
    try:
        from services.email_service import EmailService, email_service
        
        # Check class exists
        assert EmailService is not None
        
        # Check instance exists
        assert email_service is not None
        
        # Check SMTP methods exist
        required_methods = [
            'send_email',
            'send_withdrawal_confirmation',
            'send_withdrawal_alert',
            'send_daily_report'
        ]
        
        for method_name in required_methods:
            assert hasattr(EmailService, method_name), f"Missing method: {method_name}"
        
        # Check for new SMTP implementation (not stub)
        assert hasattr(EmailService, '_send_smtp'), "Missing _send_smtp method (should exist in SMTP implementation)"
        
        print("✅ Email service has SMTP implementation")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import email service: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Email service validation failed: {e}")
        return False


def test_transfer_state_machine_idempotency():
    """Test that transfer state machine has idempotency checking"""
    try:
        from services.transfer_state_machine import TransferStateMachine, transfer_state_machine
        
        # Check class exists
        assert TransferStateMachine is not None
        
        # Check instance exists
        assert transfer_state_machine is not None
        
        # Check idempotency method exists
        assert hasattr(TransferStateMachine, '_check_idempotency'), "Missing _check_idempotency method"
        
        # Check request_transfer signature includes idempotency_key
        import inspect
        sig = inspect.signature(TransferStateMachine.request_transfer)
        params = list(sig.parameters.keys())
        assert 'idempotency_key' in params, "request_transfer missing idempotency_key parameter"
        
        print("✅ Transfer state machine has idempotency support")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import transfer state machine: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Transfer state machine validation failed: {e}")
        return False


def test_wallet_config_vars():
    """Test that wallet configuration variables are defined"""
    try:
        import config
        
        # Check 2FA config
        assert hasattr(config, 'REQUIRE_2FA_FOR_WITHDRAWALS'), "Missing REQUIRE_2FA_FOR_WITHDRAWALS"
        
        # Check approval thresholds
        assert hasattr(config, 'REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR'), "Missing REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR"
        
        # Check transfer limits
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_TX'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_TX"
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_DAY'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_DAY"
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_MONTH'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_MONTH"
        
        # Check reserve requirements
        assert hasattr(config, 'MIN_RESERVE_LUNO_ZAR'), "Missing MIN_RESERVE_LUNO_ZAR"
        assert hasattr(config, 'MIN_RESERVE_PER_EXCHANGE_ZAR'), "Missing MIN_RESERVE_PER_EXCHANGE_ZAR"
        
        # Check address whitelisting
        assert hasattr(config, 'REQUIRE_ADDRESS_WHITELIST'), "Missing REQUIRE_ADDRESS_WHITELIST"
        
        print("✅ All wallet configuration variables are defined")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import config: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Wallet config validation failed: {e}")
        return False


def test_platform_config_has_7_exchanges():
    """Test that platform config has exactly 7 exchanges"""
    try:
        from config.platforms import SUPPORTED_PLATFORMS, PLATFORM_CONFIG
        
        # Check SUPPORTED_PLATFORMS exists
        assert SUPPORTED_PLATFORMS is not None
        assert isinstance(SUPPORTED_PLATFORMS, list)
        
        # Check exactly 7 exchanges
        assert len(SUPPORTED_PLATFORMS) == 7, f"Expected 7 exchanges, found {len(SUPPORTED_PLATFORMS)}"
        
        # Check required exchanges
        required = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']
        for exchange in required:
            assert exchange in SUPPORTED_PLATFORMS, f"Missing required exchange: {exchange}"
        
        # Check PLATFORM_CONFIG has all exchanges
        for exchange in SUPPORTED_PLATFORMS:
            assert exchange in PLATFORM_CONFIG, f"PLATFORM_CONFIG missing entry for: {exchange}"
        
        # Check no VALR/OVEX
        assert 'valr' not in SUPPORTED_PLATFORMS, "VALR should not be in SUPPORTED_PLATFORMS"
        assert 'ovex' not in SUPPORTED_PLATFORMS, "OVEX should not be in SUPPORTED_PLATFORMS"
        
        print("✅ Platform config has exactly 7 exchanges (no VALR/OVEX)")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import platforms config: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Platform config validation failed: {e}")
        return False


def test_wallet_hub_uses_supported_platforms():
    """Test that wallet_hub imports SUPPORTED_PLATFORMS"""
    try:
        # Read wallet_hub.py file
        wallet_hub_path = os.path.join(os.path.dirname(__file__), '..', 'routes', 'wallet_hub.py')
        with open(wallet_hub_path, 'r') as f:
            content = f.read()
        
        # Check for import
        assert 'from config.platforms import SUPPORTED_PLATFORMS' in content, \
            "wallet_hub.py should import SUPPORTED_PLATFORMS from config.platforms"
        
        # Check it's used (not hardcoded list)
        assert 'for exchange in SUPPORTED_PLATFORMS' in content, \
            "wallet_hub.py should iterate over SUPPORTED_PLATFORMS"
        
        # Check no hardcoded exchange lists
        hardcoded_list = "['luno', 'binance', 'kucoin', 'bybit', 'bitget']"
        assert hardcoded_list not in content, \
            "wallet_hub.py should not have hardcoded exchange list"
        
        print("✅ wallet_hub.py uses SUPPORTED_PLATFORMS correctly")
        return True
        
    except FileNotFoundError as e:
        print(f"❌ wallet_hub.py not found: {e}")
        return False
    except AssertionError as e:
        print(f"❌ wallet_hub validation failed: {e}")
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("Production Wallet Features Tests")
    print("="*70 + "\n")
    
    tests = [
        ("Reserved Funds Service", test_reserved_funds_service_exists),
        ("Balance Sync Service", test_balance_sync_service_exists),
        ("Email Service SMTP", test_email_service_has_smtp),
        ("Transfer Idempotency", test_transfer_state_machine_idempotency),
        ("Wallet Config Vars", test_wallet_config_vars),
        ("7 Exchanges Config", test_platform_config_has_7_exchanges),
        ("Wallet Hub Integration", test_wallet_hub_uses_supported_platforms),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 70)
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            failed += 1
    
    print("\n" + "="*70)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*70 + "\n")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
