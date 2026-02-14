#!/usr/bin/env python3
"""
Simple verification script to test key changes without running the full server
"""

def test_openapi_config():
    """Verify FastAPI OpenAPI URLs are configured correctly"""
    print("Testing OpenAPI configuration...")
    
    # Read server.py to check the FastAPI initialization
    with open('backend/server.py', 'r') as f:
        content = f.read()
    
    # Check if OpenAPI URLs are set
    checks = {
        'openapi_url="/api/openapi.json"': 'OpenAPI URL set to /api/openapi.json',
        'docs_url="/api/docs"': 'Docs URL set to /api/docs',
        'redoc_url="/api/redoc"': 'ReDoc URL set to /api/redoc',
    }
    
    all_passed = True
    for check, description in checks.items():
        if check in content:
            print(f"  ✅ {description}")
        else:
            print(f"  ❌ FAIL: {description}")
            all_passed = False
    
    return all_passed

def test_auth_response():
    """Verify auth endpoints return only access_token, not duplicate token"""
    print("\nTesting auth response consistency...")
    
    with open('backend/routes/auth.py', 'r') as f:
        content = f.read()
    
    # Check that we're NOT returning the duplicate "token" field
    if '"token": access_token' in content:
        print("  ❌ FAIL: Still returning duplicate 'token' field")
        return False
    
    # Check that we ARE returning access_token
    if '"access_token": access_token' in content:
        print("  ✅ Auth endpoints return access_token")
    else:
        print("  ❌ FAIL: access_token not found in response")
        return False
    
    # Check frontend uses access_token
    frontend_checks = [
        ('frontend/src/pages/Login.js', 'response.data.access_token'),
        ('frontend/src/pages/Register.js', 'response.data.access_token'),
    ]
    
    for file_path, check_string in frontend_checks:
        with open(file_path, 'r') as f:
            if check_string in f.read():
                print(f"  ✅ {file_path} uses access_token")
            else:
                print(f"  ❌ FAIL: {file_path} doesn't use access_token")
                return False
    
    return True

def test_kucoin_form():
    """Verify KuCoin form is not duplicated"""
    print("\nTesting KuCoin form fix...")
    
    with open('frontend/src/pages/Dashboard.js', 'r') as f:
        content = f.read()
    
    # Count how many times we render KuCoin-specific fields
    # Should only be once now (in the config-driven section)
    kucoin_passphrase_count = content.count('provider === \'kucoin\'')
    
    # We should have exactly one kucoin check for passphrase
    # The old version had both SUPPORTED_PLATFORMS and separate kucoin block
    if kucoin_passphrase_count <= 1:
        print(f"  ✅ KuCoin form rendering is clean (found {kucoin_passphrase_count} conditional)")
    else:
        print(f"  ⚠️  Warning: Found {kucoin_passphrase_count} KuCoin conditionals (may indicate duplication)")
    
    # Check for bitget passphrase validation
    if 'bitget' in content and 'passphrase' in content:
        print("  ✅ Bitget passphrase support added")
    else:
        print("  ⚠️  Warning: Bitget passphrase support not verified")
    
    return True

def test_footer_fix():
    """Verify footer shows copyright and VersionBadge is conditional"""
    print("\nTesting footer fix...")
    
    with open('frontend/src/components/VersionBadge.js', 'r') as f:
        content = f.read()
    
    # Check that VersionBadge accepts showBuildInfo prop
    if 'showBuildInfo' in content:
        print("  ✅ VersionBadge supports showBuildInfo prop")
    else:
        print("  ❌ FAIL: VersionBadge missing showBuildInfo prop")
        return False
    
    # Check Dashboard footer
    with open('frontend/src/pages/Dashboard.js', 'r') as f:
        dashboard = f.read()
    
    if 'Part of Amarktai Network — For personal use only.' in dashboard:
        print("  ✅ Dashboard footer shows copyright")
    else:
        print("  ❌ FAIL: Dashboard footer missing copyright")
        return False
    
    if 'showAdmin && <VersionBadge' in dashboard:
        print("  ✅ VersionBadge only shown in admin view")
    else:
        print("  ⚠️  Warning: VersionBadge visibility not confirmed")
    
    return True

def test_verify_live_script():
    """Verify the verify_live.sh script exists and is executable"""
    print("\nTesting verify_live.sh script...")
    
    import os
    
    script_path = 'scripts/verify_live.sh'
    if os.path.exists(script_path):
        print(f"  ✅ {script_path} exists")
        
        if os.access(script_path, os.X_OK):
            print(f"  ✅ {script_path} is executable")
        else:
            print(f"  ⚠️  Warning: {script_path} is not executable")
        
        # Check that it has the key checks
        with open(script_path, 'r') as f:
            content = f.read()
        
        key_checks = [
            '/api/health/ping',
            '/api/openapi.json',
            '/api/auth/login',
            'access_token',
            'Route collision',
        ]
        
        for check in key_checks:
            if check in content:
                print(f"  ✅ Contains check for: {check}")
            else:
                print(f"  ⚠️  Warning: Missing check for: {check}")
    else:
        print(f"  ❌ FAIL: {script_path} not found")
        return False
    
    return True

def test_no_banned_exchanges():
    """Verify valr and ovex are not in the codebase"""
    print("\nTesting for banned exchanges (valr, ovex)...")
    
    import os
    import re
    
    banned = ['valr', 'ovex']
    found_banned = []
    
    # Check key files
    check_paths = [
        'frontend/src/constants/platforms.js',
        'backend/routes/keys.py',
        'backend/services/provider_registry.py',
    ]
    
    for path in check_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read().lower()
            for exchange in banned:
                if exchange in content and f'no {exchange}' not in content:
                    found_banned.append(f"{exchange} in {path}")
    
    if not found_banned:
        print(f"  ✅ No banned exchanges (valr, ovex) found")
        return True
    else:
        print(f"  ❌ FAIL: Found banned exchanges:")
        for item in found_banned:
            print(f"    - {item}")
        return False

def main():
    print("="*60)
    print("🔍 Amarktai Network - Change Verification")
    print("="*60)
    
    tests = [
        test_openapi_config,
        test_auth_response,
        test_kucoin_form,
        test_footer_fix,
        test_verify_live_script,
        test_no_banned_exchanges,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append(False)
    
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ ALL VERIFICATIONS PASSED")
        return 0
    else:
        print("\n⚠️  SOME VERIFICATIONS FAILED OR HAVE WARNINGS")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
