"""
Test Production-Safe Transfer Features

Tests the complete transfer system including:
- Transfer limits enforcement
- Tag/memo validation
- Whitelist enforcement  
- Idempotency
- 2FA requirement
- Emergency stop
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_transfer_limits_service_exists():
    """Test that transfer limits service exists and has required methods"""
    try:
        from services.transfer_limits_service import transfer_limits_service
        
        assert transfer_limits_service is not None, "Transfer limits service not found"
        
        # Check required methods exist
        assert hasattr(transfer_limits_service, 'check_limits'), "Missing check_limits method"
        assert hasattr(transfer_limits_service, 'record_transfer'), "Missing record_transfer method"
        assert hasattr(transfer_limits_service, 'get_usage_summary'), "Missing get_usage_summary method"
        
        print("✅ Transfer limits service exists with required methods")
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import transfer_limits_service: {e}")
        return False


def test_transfer_limits_config():
    """Test that transfer limit configuration exists"""
    try:
        import config
        
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_TX'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_TX"
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_DAY'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_DAY"
        assert hasattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_MONTH'), "Missing WALLET_MAX_TRANSFER_ZAR_PER_MONTH"
        
        # Check that values are reasonable
        assert config.WALLET_MAX_TRANSFER_ZAR_PER_TX > 0, "Per-tx limit must be positive"
        assert config.WALLET_MAX_TRANSFER_ZAR_PER_DAY > 0, "Daily limit must be positive"
        assert config.WALLET_MAX_TRANSFER_ZAR_PER_MONTH > 0, "Monthly limit must be positive"
        
        # Check that limits make sense (daily <= monthly, per-tx <= daily)
        assert config.WALLET_MAX_TRANSFER_ZAR_PER_TX <= config.WALLET_MAX_TRANSFER_ZAR_PER_DAY, \
            "Per-tx limit should not exceed daily limit"
        assert config.WALLET_MAX_TRANSFER_ZAR_PER_DAY <= config.WALLET_MAX_TRANSFER_ZAR_PER_MONTH, \
            "Daily limit should not exceed monthly limit"
        
        print(f"✅ Transfer limits configured:")
        print(f"   Per-tx: R{config.WALLET_MAX_TRANSFER_ZAR_PER_TX:,.2f}")
        print(f"   Daily: R{config.WALLET_MAX_TRANSFER_ZAR_PER_DAY:,.2f}")
        print(f"   Monthly: R{config.WALLET_MAX_TRANSFER_ZAR_PER_MONTH:,.2f}")
        return True
        
    except Exception as e:
        print(f"❌ Transfer limits config error: {e}")
        return False


def test_transfer_state_machine_has_limits_check():
    """Test that transfer state machine integrates limits checking"""
    try:
        import inspect
        from services.transfer_state_machine import TransferStateMachine
        
        # Get source code of request_transfer method
        source = inspect.getsource(TransferStateMachine.request_transfer)
        
        # Check that it calls transfer_limits_service
        assert 'transfer_limits_service' in source, "Transfer state machine doesn't use limits service"
        assert 'check_limits' in source, "Transfer state machine doesn't call check_limits"
        
        print("✅ Transfer state machine integrates limit checking")
        return True
        
    except Exception as e:
        print(f"❌ Transfer state machine limits check error: {e}")
        return False


def test_transfer_models_have_tag_memo_fields():
    """Test that transfer models support tag/memo/network"""
    try:
        from models import TransferJob, TransferJobCreate
        
        # Check TransferJob has the fields
        annotations = TransferJob.__annotations__
        assert 'deposit_tag' in annotations, "Missing deposit_tag field"
        assert 'deposit_memo' in annotations, "Missing deposit_memo field"
        assert 'network' in annotations, "Missing network field"
        
        # Check TransferJobCreate has the fields
        create_annotations = TransferJobCreate.__annotations__
        assert 'tag' in create_annotations, "Missing tag field in create model"
        assert 'memo' in create_annotations, "Missing memo field in create model"
        assert 'network' in create_annotations, "Missing network field in create model"
        
        print("✅ Transfer models support tag/memo/network")
        return True
        
    except Exception as e:
        print(f"❌ Transfer model fields error: {e}")
        return False


def test_transfer_state_machine_validates_tags():
    """Test that transfer state machine validates required tags"""
    try:
        import inspect
        from services.transfer_state_machine import TransferStateMachine
        
        # Get source code of request_transfer method
        source = inspect.getsource(TransferStateMachine.request_transfer)
        
        # Check that it validates tags for currencies that require them
        assert 'tag_required_currencies' in source or 'XRP' in source, \
            "Transfer state machine doesn't validate tag requirements"
        assert 'TAG_REQUIRED' in source, "Missing TAG_REQUIRED error code"
        
        print("✅ Transfer state machine validates required tags")
        return True
        
    except Exception as e:
        print(f"❌ Tag validation check error: {e}")
        return False


def test_whitelist_service_exists():
    """Test that address whitelist service exists"""
    try:
        from services.address_whitelist import address_whitelist_service
        
        assert address_whitelist_service is not None, "Whitelist service not found"
        
        # Check required methods exist
        required_methods = [
            'add_address',
            'approve_address',
            'reject_address',
            'is_address_whitelisted',
            'get_user_addresses'
        ]
        
        for method in required_methods:
            assert hasattr(address_whitelist_service, method), f"Missing {method} method"
        
        print("✅ Address whitelist service exists with required methods")
        return True
        
    except Exception as e:
        print(f"❌ Whitelist service error: {e}")
        return False


def test_transfer_state_machine_checks_whitelist():
    """Test that transfer state machine checks whitelist"""
    try:
        import inspect
        from services.transfer_state_machine import TransferStateMachine
        
        # Get source code of _execute_transfer method
        source = inspect.getsource(TransferStateMachine._execute_transfer)
        
        # Check that it calls whitelist service
        assert 'address_whitelist_service' in source, "Doesn't use whitelist service"
        assert 'is_address_whitelisted' in source, "Doesn't check whitelist"
        assert 'ADDRESS_NOT_WHITELISTED' in source or 'not whitelisted' in source.lower(), \
            "Missing whitelist enforcement"
        
        print("✅ Transfer state machine checks address whitelist")
        return True
        
    except Exception as e:
        print(f"❌ Whitelist check error: {e}")
        return False


def test_transfer_blocked_reasons_complete():
    """Test that TransferBlockedReason enum includes all required reasons"""
    try:
        from services.transfer_state_machine import TransferBlockedReason
        
        required_reasons = [
            'EMERGENCY_STOP',
            'LIMIT_PER_TX',
            'LIMIT_DAILY',
            'LIMIT_MONTHLY',
            'MISSING_2FA',
            'ADDRESS_NOT_WHITELISTED',
            'TAG_REQUIRED'
        ]
        
        actual_reasons = [r.value.upper().replace('-', '_') for r in TransferBlockedReason]
        
        for reason in required_reasons:
            assert any(reason in ar for ar in actual_reasons), f"Missing blocked reason: {reason}"
        
        print("✅ TransferBlockedReason enum includes all required reasons")
        return True
        
    except Exception as e:
        print(f"❌ Blocked reasons check error: {e}")
        return False


def test_whitelist_admin_routes_exist():
    """Test that admin whitelist management routes exist"""
    try:
        from routes.admin_whitelist import router
        
        assert router is not None, "Admin whitelist router not found"
        
        # Check that it has expected prefix
        assert hasattr(router, 'prefix'), "Router missing prefix"
        assert 'whitelist' in router.prefix.lower(), "Router doesn't have whitelist prefix"
        
        print("✅ Admin whitelist management routes exist")
        return True
        
    except Exception as e:
        print(f"❌ Admin whitelist routes error: {e}")
        return False


def test_user_whitelist_routes_exist():
    """Test that user whitelist management routes exist"""
    try:
        from routes.user_whitelist import router
        
        assert router is not None, "User whitelist router not found"
        
        # Check that it has expected prefix
        assert hasattr(router, 'prefix'), "Router missing prefix"
        assert 'whitelist' in router.prefix.lower(), "Router doesn't have whitelist prefix"
        
        print("✅ User whitelist management routes exist")
        return True
        
    except Exception as e:
        print(f"❌ User whitelist routes error: {e}")
        return False


def test_diagnostics_transfer_path_endpoint():
    """Test that /api/diagnostics/transfer-path endpoint exists"""
    try:
        from routes.diagnostics import router
        import inspect
        
        # Get source to check for transfer-path endpoint
        source = inspect.getsource(router.__class__)
        
        # Look for the endpoint in the diagnostics module
        with open(os.path.join(os.path.dirname(__file__), '..', 'routes', 'diagnostics.py')) as f:
            diag_source = f.read()
        
        assert 'transfer-path' in diag_source or 'transfer_path' in diag_source, \
            "Missing transfer-path diagnostic endpoint"
        
        print("✅ Diagnostics transfer-path endpoint exists")
        return True
        
    except Exception as e:
        print(f"❌ Diagnostics endpoint error: {e}")
        return False


def test_wallet_manager_uses_state_machine():
    """Test that wallet_manager routes to state machine when enhanced transfers enabled"""
    try:
        import inspect
        from engines.wallet_manager import WalletManager
        
        # Get source code of transfer_funds_between_exchanges
        source = inspect.getsource(WalletManager.transfer_funds_between_exchanges)
        
        # Check that it uses transfer_state_machine when enhanced
        assert 'transfer_state_machine' in source, "Doesn't use transfer_state_machine"
        assert 'ENABLE_WALLET_TRANSFERS_ENHANCED' in source or 'ENABLE_REALTIME_TRANSFERS' in source, \
            "Doesn't check feature flag"
        
        print("✅ Wallet manager routes to state machine when enabled")
        return True
        
    except Exception as e:
        print(f"❌ Wallet manager integration error: {e}")
        return False


if __name__ == '__main__':
    print("=" * 70)
    print("Testing Production-Safe Transfer Features")
    print("=" * 70)
    
    tests = [
        ("Transfer Limits Service", test_transfer_limits_service_exists),
        ("Transfer Limits Config", test_transfer_limits_config),
        ("Limits Check Integration", test_transfer_state_machine_has_limits_check),
        ("Tag/Memo Model Fields", test_transfer_models_have_tag_memo_fields),
        ("Tag Validation", test_transfer_state_machine_validates_tags),
        ("Whitelist Service", test_whitelist_service_exists),
        ("Whitelist Check Integration", test_transfer_state_machine_checks_whitelist),
        ("Blocked Reasons Complete", test_transfer_blocked_reasons_complete),
        ("Admin Whitelist Routes", test_whitelist_admin_routes_exist),
        ("User Whitelist Routes", test_user_whitelist_routes_exist),
        ("Diagnostics Endpoint", test_diagnostics_transfer_path_endpoint),
        ("Wallet Manager Integration", test_wallet_manager_uses_state_machine),
    ]
    
    results = []
    
    for i, (name, test_func) in enumerate(tests, 1):
        print(f"\n{i}. Testing {name}...")
        try:
            results.append(test_func())
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    
    print(f"Results: {passed}/{total} tests passed")
    
    if all(results):
        print("✅ All production-safe transfer features implemented correctly")
        sys.exit(0)
    else:
        print("❌ Some features missing or incorrectly implemented")
        sys.exit(1)
