#!/usr/bin/env python3
"""
Boot Self-Test Script
=====================
Validates that the backend can boot without import errors.
Run this before deployment to catch missing imports or syntax errors.

Usage:
    python scripts/boot_self_test.py

Exit codes:
    0 - Success: All checks passed
    1 - Failure: Import or syntax errors detected
"""

import sys
import os
import re
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

def test_python_syntax():
    """Test that all Python files compile successfully"""
    print("🔍 Testing Python syntax...")
    backend_py_files = list(backend_dir.rglob("*.py"))
    
    # Compile regex pattern for paths to exclude
    exclude_pattern = re.compile(r'(__pycache__|\.venv|venv/|\.git/)')
    
    errors = []
    checked_count = 0
    for py_file in backend_py_files:
        # Skip files matching exclude pattern (works on both Unix and Windows paths)
        if exclude_pattern.search(str(py_file)):
            continue
        
        checked_count += 1
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                compile(f.read(), str(py_file), 'exec')
        except SyntaxError as e:
            errors.append(f"  ❌ {py_file.relative_to(backend_dir)}: {e}")
    
    if errors:
        print(f"  ❌ Found {len(errors)} syntax errors:")
        for error in errors[:10]:  # Show first 10
            print(error)
        return False
    else:
        print(f"  ✅ All {checked_count} Python files compile successfully")
        return True

def test_critical_imports():
    """Test that critical modules can be imported"""
    print("\n🔍 Testing critical imports...")
    
    critical_modules = [
        "auth",
        "models", 
        "database",
        "config",
    ]
    
    errors = []
    for module in critical_modules:
        try:
            __import__(module)
            print(f"  ✅ {module}")
        except Exception as e:
            errors.append(f"  ❌ {module}: {e}")
            print(f"  ❌ {module}: {e}")
    
    return len(errors) == 0

def test_auth_exports():
    """Test that auth.py exports required functions"""
    print("\n🔍 Testing auth.py exports...")
    
    required_exports = [
        'create_access_token',
        'get_current_user', 
        'get_password_hash',
        'verify_password',
        'is_admin',
        'require_admin',
    ]
    
    try:
        import auth
        missing = []
        for export in required_exports:
            if not hasattr(auth, export):
                missing.append(export)
        
        if missing:
            print(f"  ❌ Missing exports: {', '.join(missing)}")
            return False
        else:
            print(f"  ✅ All required exports present")
            return True
    except Exception as e:
        print(f"  ❌ Failed to import auth: {e}")
        return False

def test_server_imports():
    """Test that server.py imports correctly"""
    print("\n🔍 Testing server.py imports...")
    
    # Check that is_admin is imported
    server_file = backend_dir / "server.py"
    with open(server_file, 'r') as f:
        content = f.read()
    
    # Verify it's specifically in an 'from auth import' line
    import_lines = [line for line in content.split('\n') if 'from auth import' in line]
    has_is_admin = any('is_admin' in line for line in import_lines)
    
    if has_is_admin:
        print(f"  ✅ is_admin imported in server.py")
        return True
    else:
        print(f"  ❌ is_admin not found in auth import line")
        return False

def main():
    """Run all boot self-tests"""
    print("=" * 60)
    print("🚀 Backend Boot Self-Test")
    print("=" * 60)
    
    tests = [
        ("Python Syntax", test_python_syntax),
        ("Critical Imports", test_critical_imports),
        ("Auth Exports", test_auth_exports),
        ("Server Imports", test_server_imports),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    print(f"\n{'✅' if passed == total else '❌'} {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All boot self-tests passed! Backend is ready to start.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Fix errors before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
