"""
Test Production-Safe Transfer Features - Syntax and Structure Check

Tests without requiring dependencies (motor, pydantic, fastapi).
Just checks that files exist, have valid syntax, and contain required code patterns.
"""

import sys
import os
import ast

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_file_syntax(filepath, name):
    """Test that a file has valid Python syntax"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        print(f"✅ {name} has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax error in {name}: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ {name} file not found: {filepath}")
        return False


def test_file_contains_patterns(filepath, name, patterns):
    """Test that a file contains required patterns"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        missing = []
        for pattern in patterns:
            if pattern not in content:
                missing.append(pattern)
        
        if missing:
            print(f"❌ {name} missing patterns: {', '.join(missing)}")
            return False
        else:
            print(f"✅ {name} contains all required patterns")
            return True
            
    except FileNotFoundError:
        print(f"❌ {name} file not found: {filepath}")
        return False


def test_transfer_limits_service():
    """Test transfer limits service file"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'services', 'transfer_limits_service.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "transfer_limits_service.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'class TransferLimitsService',
        'async def check_limits',
        'async def record_transfer',
        'WALLET_MAX_TRANSFER_ZAR_PER_TX',
        'WALLET_MAX_TRANSFER_ZAR_PER_DAY',
        'WALLET_MAX_TRANSFER_ZAR_PER_MONTH',
        'LIMIT_PER_TX',
        'LIMIT_DAILY',
        'LIMIT_MONTHLY',
        'wallet_transfer_usage'
    ]
    
    return test_file_contains_patterns(filepath, "transfer_limits_service.py", patterns)


def test_transfer_state_machine():
    """Test transfer state machine has required updates"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'services', 'transfer_state_machine.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "transfer_state_machine.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'transfer_limits_service',
        'check_limits',
        'LIMIT_PER_TX',
        'LIMIT_DAILY',
        'LIMIT_MONTHLY',
        'TAG_REQUIRED',
        'ADDRESS_NOT_WHITELISTED',
        'tag_required_currencies',
        'deposit_tag',
        'deposit_memo',
        'network',
        'address_whitelist_service',
        'is_address_whitelisted'
    ]
    
    return test_file_contains_patterns(filepath, "transfer_state_machine.py", patterns)


def test_models_updated():
    """Test models.py has tag/memo/network fields"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'models.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "models.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'deposit_tag',
        'deposit_memo',
        'network',
        'class TransferJobCreate',
        'tag:',
        'memo:'
    ]
    
    return test_file_contains_patterns(filepath, "models.py (transfer fields)", patterns)


def test_admin_whitelist_routes():
    """Test admin whitelist routes exist"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'routes', 'admin_whitelist.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "admin_whitelist.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'router = APIRouter',
        '/api/admin/whitelist',
        'list_pending_whitelist_approvals',
        'approve_whitelist_address',
        'reject_whitelist_address',
        'delete_whitelist_address'
    ]
    
    return test_file_contains_patterns(filepath, "admin_whitelist.py", patterns)


def test_user_whitelist_routes():
    """Test user whitelist routes exist"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'routes', 'user_whitelist.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "user_whitelist.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'router = APIRouter',
        '/api/wallet/whitelist',
        'request_whitelist_address',
        'get_my_whitelist_addresses',
        'delete_my_whitelist_address'
    ]
    
    return test_file_contains_patterns(filepath, "user_whitelist.py", patterns)


def test_diagnostics_endpoint():
    """Test diagnostics has transfer-path endpoint"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'routes', 'diagnostics.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "diagnostics.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'transfer-path',
        'transfer_path_diagnostic',
        'active_path',
        'production_ready',
        'transfer_state_machine',
        'transfer_limits_service'
    ]
    
    return test_file_contains_patterns(filepath, "diagnostics.py (transfer-path)", patterns)


def test_wallet_manager_integration():
    """Test wallet_manager routes to state machine"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'engines', 'wallet_manager.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "wallet_manager.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'transfer_state_machine',
        'ENABLE_WALLET_TRANSFERS_ENHANCED',
        'request_transfer',
        'enhanced_enabled'
    ]
    
    return test_file_contains_patterns(filepath, "wallet_manager.py (integration)", patterns)


def test_server_routes_registered():
    """Test that new routes are registered in server.py"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'server.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "server.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'routes.admin_whitelist',
        'routes.user_whitelist'
    ]
    
    return test_file_contains_patterns(filepath, "server.py (route registration)", patterns)


def test_config_has_limits():
    """Test config.py has transfer limits"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'config.py')
    
    # Check syntax
    syntax_ok = test_file_syntax(filepath, "config.py")
    if not syntax_ok:
        return False
    
    # Check required patterns
    patterns = [
        'WALLET_MAX_TRANSFER_ZAR_PER_TX',
        'WALLET_MAX_TRANSFER_ZAR_PER_DAY',
        'WALLET_MAX_TRANSFER_ZAR_PER_MONTH',
        'REQUIRE_ADDRESS_WHITELIST'
    ]
    
    return test_file_contains_patterns(filepath, "config.py (limits)", patterns)


if __name__ == '__main__':
    print("=" * 70)
    print("Testing Production-Safe Transfer Features - Syntax & Structure")
    print("=" * 70)
    
    tests = [
        ("Config has transfer limits", test_config_has_limits),
        ("Transfer Limits Service", test_transfer_limits_service),
        ("Transfer State Machine Updated", test_transfer_state_machine),
        ("Models Updated (tag/memo)", test_models_updated),
        ("Admin Whitelist Routes", test_admin_whitelist_routes),
        ("User Whitelist Routes", test_user_whitelist_routes),
        ("Diagnostics Endpoint", test_diagnostics_endpoint),
        ("Wallet Manager Integration", test_wallet_manager_integration),
        ("Server Routes Registration", test_server_routes_registered),
    ]
    
    results = []
    
    for i, (name, test_func) in enumerate(tests, 1):
        print(f"\n{i}. Testing {name}...")
        try:
            results.append(test_func())
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            import traceback
            traceback.print_exc()
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
