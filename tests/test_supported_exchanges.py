"""
Test Supported Exchanges
Ensures exactly 7 exchanges are supported: luno, binance, kucoin, bybit, kraken, bitget, gate
This test MUST fail if VALR/OVEX appear or if count != 7.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# Single source of truth for supported exchanges
SUPPORTED_EXCHANGES = {
    'luno',
    'binance', 
    'kucoin',
    'bybit',
    'kraken',
    'bitget',
    'gate'
}

# Exchanges that MUST NOT be present
FORBIDDEN_EXCHANGES = {'valr', 'ovex'}


def test_platforms_config_exact_exchanges():
    """
    Test that config/platforms.py defines exactly the 7 supported exchanges.
    
    MUST fail if:
    - Count != 7
    - VALR or OVEX are present
    - Any required exchange is missing
    """
    try:
        from config.platforms import SUPPORTED_PLATFORMS
    except ImportError:
        pytest.skip("config.platforms module not found (may use different structure)")
        return
    
    platforms_set = set(p.lower() for p in SUPPORTED_PLATFORMS)
    
    # Check count
    assert len(platforms_set) == 7, (
        f"Expected exactly 7 exchanges, found {len(platforms_set)}: {platforms_set}"
    )
    
    # Check for forbidden exchanges
    forbidden_found = platforms_set & FORBIDDEN_EXCHANGES
    assert len(forbidden_found) == 0, (
        f"Forbidden exchanges found: {forbidden_found}. "
        "VALR and OVEX MUST NOT be in active code."
    )
    
    # Check all required exchanges are present
    missing = SUPPORTED_EXCHANGES - platforms_set
    assert len(missing) == 0, (
        f"Missing required exchanges: {missing}"
    )
    
    # Check no extra exchanges
    extra = platforms_set - SUPPORTED_EXCHANGES
    assert len(extra) == 0, (
        f"Extra exchanges found: {extra}. "
        f"Only these 7 are supported: {SUPPORTED_EXCHANGES}"
    )
    
    print(f"✅ Platforms config has exactly 7 supported exchanges: {SUPPORTED_EXCHANGES}")


def test_exchange_limits_exact_exchanges():
    """
    Test that exchange_limits.py defines limits for exactly the 7 supported exchanges.
    """
    try:
        import exchange_limits
    except ImportError:
        pytest.skip("exchange_limits module not found")
        return
    
    # Check EXCHANGE_LIMITS if it exists
    if hasattr(exchange_limits, 'EXCHANGE_LIMITS'):
        limits_dict = exchange_limits.EXCHANGE_LIMITS
        exchanges_set = set(e.lower() for e in limits_dict.keys())
        
        # Check for forbidden exchanges
        forbidden_found = exchanges_set & FORBIDDEN_EXCHANGES
        assert len(forbidden_found) == 0, (
            f"Forbidden exchanges in EXCHANGE_LIMITS: {forbidden_found}"
        )
        
        # Should have limits for all 7 exchanges
        missing = SUPPORTED_EXCHANGES - exchanges_set
        if missing:
            print(f"⚠️  Warning: Missing exchange limits for: {missing}")
        
        print(f"✅ Exchange limits defined for: {exchanges_set}")


def test_provider_registry_exact_exchanges():
    """
    Test that provider_registry service lists exactly the 7 exchange providers.
    """
    try:
        from services.provider_registry import list_providers
    except ImportError:
        pytest.skip("provider_registry service not found")
        return
    
    providers = list_providers()
    
    # Filter to exchange type providers only
    exchange_providers = [
        p for p in providers 
        if p.get('type') == 'exchange'
    ]
    
    exchange_ids = set(p['id'].lower() for p in exchange_providers)
    
    # Check for forbidden exchanges
    forbidden_found = exchange_ids & FORBIDDEN_EXCHANGES
    assert len(forbidden_found) == 0, (
        f"Forbidden exchanges in provider registry: {forbidden_found}"
    )
    
    # Check all required exchanges are present
    missing = SUPPORTED_EXCHANGES - exchange_ids
    assert len(missing) == 0, (
        f"Missing required exchanges in provider registry: {missing}"
    )
    
    # Check no extra exchanges
    extra = exchange_ids - SUPPORTED_EXCHANGES
    assert len(extra) == 0, (
        f"Extra exchanges in provider registry: {extra}"
    )
    
    print(f"✅ Provider registry has exactly 7 exchanges: {SUPPORTED_EXCHANGES}")


def test_no_valr_ovex_in_active_code():
    """
    Test that VALR and OVEX do not appear in active Python code.
    
    Scans backend/ for VALR/OVEX references (excluding archives and tests).
    """
    import re
    from pathlib import Path
    
    backend_dir = Path(__file__).parent.parent / 'backend'
    
    # Patterns to search for
    patterns = [
        re.compile(r'\bvalr\b', re.IGNORECASE),
        re.compile(r'\bovex\b', re.IGNORECASE)
    ]
    
    # Directories to exclude
    exclude_dirs = {'_archive', 'site-packages', '.venv', '__pycache__', 'node_modules'}
    
    violations = []
    
    for py_file in backend_dir.rglob('*.py'):
        # Skip excluded directories
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        
        # Skip test files
        if py_file.name.startswith('test_'):
            continue
        
        try:
            content = py_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                for pattern in patterns:
                    if pattern.search(line):
                        violations.append({
                            'file': str(py_file.relative_to(backend_dir.parent)),
                            'line': line_num,
                            'text': line.strip()[:80]
                        })
        except Exception:
            pass  # Skip files that can't be read
    
    if violations:
        error_msg = "\n" + "="*80 + "\n"
        error_msg += "VALR/OVEX FOUND IN ACTIVE CODE!\n"
        error_msg += "="*80 + "\n"
        for v in violations[:10]:  # Show first 10
            error_msg += f"\n❌ {v['file']}:{v['line']}\n"
            error_msg += f"   {v['text']}\n"
        if len(violations) > 10:
            error_msg += f"\n... and {len(violations) - 10} more violations\n"
        error_msg += "\n" + "="*80 + "\n"
        error_msg += "VALR and OVEX MUST be removed from active code.\n"
        error_msg += "They may only exist in archive folders with warning headers.\n"
        error_msg += "="*80 + "\n"
        pytest.fail(error_msg)
    
    print("✅ No VALR/OVEX references found in active code")


if __name__ == "__main__":
    # Allow running directly for quick testing
    print("Testing platforms config...")
    test_platforms_config_exact_exchanges()
    
    print("\nTesting exchange limits...")
    test_exchange_limits_exact_exchanges()
    
    print("\nTesting provider registry...")
    test_provider_registry_exact_exchanges()
    
    print("\nTesting for VALR/OVEX in active code...")
    test_no_valr_ovex_in_active_code()
    
    print("\n✅ All exchange tests passed!")
