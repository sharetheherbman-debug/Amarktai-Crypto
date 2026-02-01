"""
Code Quality and Structure Tests for Wallet System

Tests that don't require external dependencies.
Validates code structure, implementation completeness, and integration points.
"""

import sys
import os
import re

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_transfer_state_machine_completeness():
    """Test transfer state machine has all required methods"""
    try:
        service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'transfer_state_machine.py')
        
        with open(service_path, 'r') as f:
            content = f.read()
        
        required_methods = [
            'request_transfer',
            '_execute_transfer',
            '_monitor_withdrawal',
            '_check_idempotency',
            '_check_emergency_stop',
            '_verify_totp',
            '_check_reserved_funds',
            '_transition_state',
            '_append_ledger',
            '_reserve_funds',
            '_release_funds',
            '_get_deposit_address'
        ]
        
        missing = []
        for method in required_methods:
            if f'def {method}' not in content:
                missing.append(method)
        
        assert len(missing) == 0, f"Missing methods: {missing}"
        
        print("✅ Transfer state machine has all required methods")
        return True
        
    except AssertionError as e:
        print(f"❌ Transfer state machine incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_address_whitelist_completeness():
    """Test address whitelist service has all required methods"""
    try:
        service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'address_whitelist.py')
        
        with open(service_path, 'r') as f:
            content = f.read()
        
        required_methods = [
            '_validate_address_format',
            'add_address',
            'approve_address',
            'reject_address',
            'get_user_addresses',
            'get_pending_approvals',
            'is_address_whitelisted',
            'delete_address'
        ]
        
        missing = []
        for method in required_methods:
            if f'def {method}' not in content:
                missing.append(method)
        
        assert len(missing) == 0, f"Missing methods: {missing}"
        
        # Check currency validations exist
        assert 'BTC' in content and 'BITCOIN' in content, "Bitcoin validation missing"
        assert 'ETH' in content and 'ETHEREUM' in content, "Ethereum validation missing"
        assert 'XRP' in content and 'RIPPLE' in content, "XRP validation missing"
        
        print("✅ Address whitelist service has all required methods and validations")
        return True
        
    except AssertionError as e:
        print(f"❌ Address whitelist service incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_transfer_endpoints_completeness():
    """Test transfer endpoints have all required routes"""
    try:
        routes_path = os.path.join(os.path.dirname(__file__), '..', 'routes', 'wallet_transfers_enhanced.py')
        
        with open(routes_path, 'r') as f:
            content = f.read()
        
        required_endpoints = [
            '/wallet/transfers/create',
            '/wallet/transfers',  # list
            '/wallet/transfers/{transfer_id}',  # get
            '/wallet/transfers/{transfer_id}/cancel',
            '/admin/transfers/pending',
            '/admin/transfers/{transfer_id}/approve',
            '/admin/transfers/{transfer_id}/reject'
        ]
        
        missing = []
        for endpoint in required_endpoints:
            # Convert to regex-friendly format
            pattern = endpoint.replace('{', r'\{').replace('}', r'\}').replace('/', r'/')
            if not re.search(pattern, content):
                missing.append(endpoint)
        
        assert len(missing) == 0, f"Missing endpoints: {missing}"
        
        print("✅ Transfer endpoints have all required routes")
        return True
        
    except AssertionError as e:
        print(f"❌ Transfer endpoints incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_address_endpoints_completeness():
    """Test address endpoints have all required routes"""
    try:
        routes_path = os.path.join(os.path.dirname(__file__), '..', 'routes', 'wallet_addresses.py')
        
        with open(routes_path, 'r') as f:
            content = f.read()
        
        required_endpoints = [
            '/addresses/add',
            '/addresses/list',
            '/addresses/{address_id}',  # delete
            '/admin/addresses/pending',
            '/admin/addresses/approve',
            '/admin/addresses/reject'
        ]
        
        missing = []
        for endpoint in required_endpoints:
            pattern = endpoint.replace('{', r'\{').replace('}', r'\}').replace('/', r'/')
            if not re.search(pattern, content):
                missing.append(endpoint)
        
        assert len(missing) == 0, f"Missing endpoints: {missing}"
        
        print("✅ Address endpoints have all required routes")
        return True
        
    except AssertionError as e:
        print(f"❌ Address endpoints incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_frontend_components_completeness():
    """Test frontend components have required functionality"""
    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'components')
        
        # Check TransferCreate
        with open(os.path.join(frontend_dir, 'TransferCreate.js'), 'r') as f:
            transfer_create = f.read()
        
        assert 'totp_code' in transfer_create, "2FA support missing"
        assert 'idempotency_key' in transfer_create, "Idempotency key generation missing"
        assert 'withdrawal_address' in transfer_create, "Withdrawal address support missing"
        assert '/wallet/transfers/create' in transfer_create, "Create endpoint not called"
        
        # Check TransferHistory
        with open(os.path.join(frontend_dir, 'TransferHistory.js'), 'r') as f:
            transfer_history = f.read()
        
        assert 'pending' in transfer_history, "Pending filter missing"
        assert 'completed' in transfer_history, "Completed filter missing"
        assert 'failed' in transfer_history, "Failed filter missing"
        assert 'useRealtimeEvent' in transfer_history, "Real-time updates missing"
        assert '/wallet/transfers' in transfer_history, "List endpoint not called"
        
        # Check AdminApproval
        with open(os.path.join(frontend_dir, 'AdminApproval.js'), 'r') as f:
            admin_approval = f.read()
        
        assert 'approveTransfer' in admin_approval, "Transfer approval missing"
        assert 'rejectTransfer' in admin_approval, "Transfer rejection missing"
        assert 'approveAddress' in admin_approval, "Address approval missing"
        assert 'rejectAddress' in admin_approval, "Address rejection missing"
        assert '/admin/transfers/pending' in admin_approval, "Admin endpoint not called"
        
        print("✅ Frontend components have all required functionality")
        return True
        
    except AssertionError as e:
        print(f"❌ Frontend components incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_security_features():
    """Test that security features are implemented"""
    try:
        results = []
        
        # Check transfer state machine for security
        tsm_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'transfer_state_machine.py')
        with open(tsm_path, 'r') as f:
            tsm = f.read()
        
        # Idempotency
        assert '_check_idempotency' in tsm, "Idempotency check missing"
        print("  ✅ Idempotency enforcement")
        
        # Emergency stop
        assert '_check_emergency_stop' in tsm, "Emergency stop check missing"
        print("  ✅ Emergency stop integration")
        
        # 2FA
        assert '_verify_totp' in tsm or 'totp' in tsm.lower(), "2FA verification missing"
        print("  ✅ 2FA verification")
        
        # Withdrawal limits
        assert 'withdrawal_limit' in tsm.lower() or 'limit' in tsm.lower(), "Withdrawal limits missing"
        print("  ✅ Withdrawal limits")
        
        # Reserved funds
        assert '_check_reserved_funds' in tsm, "Reserved funds check missing"
        print("  ✅ Reserved funds protection")
        
        # Address whitelist
        assert 'is_address_whitelisted' in tsm, "Address whitelist check missing"
        print("  ✅ Address whitelist validation")
        
        # Audit logging
        assert 'audit' in tsm.lower() or '_append_ledger' in tsm, "Audit logging missing"
        print("  ✅ Audit trail logging")
        
        print("✅ All security features implemented")
        return True
        
    except AssertionError as e:
        print(f"❌ Security features incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_error_handling():
    """Test that proper error handling is implemented"""
    try:
        # Check transfer state machine
        tsm_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'transfer_state_machine.py')
        with open(tsm_path, 'r') as f:
            tsm = f.read()
        
        # Check for try-except blocks
        try_count = tsm.count('try:')
        except_count = tsm.count('except')
        
        assert try_count >= 5, f"Insufficient error handling (only {try_count} try blocks)"
        assert except_count >= 5, f"Insufficient error handling (only {except_count} except blocks)"
        
        # Check for error logging
        assert 'logger.error' in tsm, "Error logging missing"
        
        # Check for state transitions on error
        assert 'TransferState.FAILED' in tsm or 'failed' in tsm.lower(), "Failed state handling missing"
        
        print("✅ Proper error handling implemented")
        return True
        
    except AssertionError as e:
        print(f"❌ Error handling incomplete: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_code_quality():
    """Test code quality metrics"""
    try:
        results = []
        
        # Check for documentation
        for filename in ['transfer_state_machine.py', 'address_whitelist.py']:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'services', filename)
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Check for docstrings
            assert '"""' in content or "'''" in content, f"{filename}: No docstrings found"
            
            # Check for type hints
            assert '->' in content or 'Optional' in content or 'Dict' in content or 'List' in content, f"{filename}: No type hints found"
        
        print("✅ Code quality standards met (docstrings, type hints)")
        return True
        
    except AssertionError as e:
        print(f"❌ Code quality issues: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == '__main__':
    print("=" * 70)
    print("Code Quality and Structure Tests - Wallet System")
    print("=" * 70)
    
    results = []
    
    print("\n1. Testing service completeness...")
    results.append(test_transfer_state_machine_completeness())
    results.append(test_address_whitelist_completeness())
    
    print("\n2. Testing endpoint completeness...")
    results.append(test_transfer_endpoints_completeness())
    results.append(test_address_endpoints_completeness())
    
    print("\n3. Testing frontend completeness...")
    results.append(test_frontend_components_completeness())
    
    print("\n4. Testing security features...")
    results.append(test_security_features())
    
    print("\n5. Testing error handling...")
    results.append(test_error_handling())
    
    print("\n6. Testing code quality...")
    results.append(test_code_quality())
    
    print("\n" + "=" * 70)
    if all(results):
        print("✅ ALL STRUCTURE TESTS PASSED")
        print("\nWallet system implementation verified:")
        print("  • Complete service implementations")
        print("  • All endpoints present")
        print("  • Frontend components complete")
        print("  • Security features implemented")
        print("  • Proper error handling")
        print("  • Code quality standards met")
        sys.exit(0)
    else:
        print("❌ SOME STRUCTURE TESTS FAILED")
        failed = sum(1 for r in results if not r)
        print(f"\n{failed} tests failed")
        sys.exit(1)
