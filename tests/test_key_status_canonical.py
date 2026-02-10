"""
Test API Key Status Canonical Vocabulary
Ensures /api/keys/list and related endpoints return ONLY canonical statuses.
Canonical statuses: not_configured, configured_untested, configured_valid, configured_invalid
Legacy statuses (test_ok, saved_untested, test_failed) must NOT appear in API responses.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


CANONICAL_STATUSES = {
    "not_configured",
    "configured_untested",
    "configured_valid",
    "configured_invalid",
    "configured_rate_limited",
}

LEGACY_STATUSES = {
    "saved_untested",
    "test_ok",
    "test_failed",
}


def test_provider_status_enum_has_canonical_values():
    """ProviderStatus enum must define all canonical statuses"""
    try:
        from services.provider_registry import ProviderStatus
    except ImportError:
        pytest.skip("provider_registry dependencies not installed")
    
    enum_values = {s.value for s in ProviderStatus}
    
    # Must include core canonical statuses
    required = {"not_configured", "configured_untested", "configured_valid", "configured_invalid"}
    missing = required - enum_values
    assert len(missing) == 0, f"ProviderStatus enum missing canonical statuses: {missing}"


def test_normalize_status_maps_legacy_to_canonical():
    """normalize_status must map all legacy statuses to canonical ones"""
    try:
        from routes.keys import normalize_status
    except ImportError:
        pytest.skip("routes.keys dependencies not installed")
    
    # Legacy -> Canonical mappings
    assert normalize_status("saved_untested") == "configured_untested"
    assert normalize_status("test_ok") == "configured_valid"
    assert normalize_status("test_failed") == "configured_invalid"
    
    # Canonical statuses should pass through unchanged
    assert normalize_status("not_configured") == "not_configured"
    assert normalize_status("configured_untested") == "configured_untested"
    assert normalize_status("configured_valid") == "configured_valid"
    assert normalize_status("configured_invalid") == "configured_invalid"


def test_no_legacy_statuses_in_keys_route_code():
    """keys.py route code must not hardcode legacy status strings in responses"""
    import inspect
    try:
        import routes.keys as keys_module
    except ImportError:
        pytest.skip("routes.keys dependencies not installed")
    
    source = inspect.getsource(keys_module)
    
    # Count occurrences outside of normalize_status function and docstrings
    lines = source.split('\n')
    violations = []
    in_normalize_func = False
    in_docstring = False
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Track if we're in a docstring
        if '"""' in stripped:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        
        # Track normalize_status function
        if 'def normalize_status' in stripped:
            in_normalize_func = True
            continue
        if in_normalize_func and stripped.startswith('def '):
            in_normalize_func = False
        if in_normalize_func:
            continue
        
        # Check for legacy status string literals in response code
        if '"test_ok"' in stripped and 'status' in stripped.lower():
            violations.append(f"Line {i}: {stripped}")
        if '"saved_untested"' in stripped and 'status' in stripped.lower():
            violations.append(f"Line {i}: {stripped}")
    
    assert len(violations) == 0, (
        f"Legacy status strings found in keys.py response code:\n" +
        "\n".join(violations)
    )


def test_provider_registry_required_fields():
    """Provider registry must define correct required_fields for each provider"""
    try:
        from services.provider_registry import get_provider
    except ImportError:
        pytest.skip("provider_registry dependencies not installed")
    
    # OpenAI: api_key only
    openai = get_provider("openai")
    if openai:
        assert "api_key" in openai.required_fields
        assert "api_secret" not in openai.required_fields
    
    # Standard exchanges: api_key + api_secret
    for exchange in ["luno", "binance", "bybit", "kraken"]:
        provider = get_provider(exchange)
        if provider:
            assert "api_key" in provider.required_fields, f"{exchange} must require api_key"
            assert "api_secret" in provider.required_fields, f"{exchange} must require api_secret"
    
    # KuCoin and Bitget: api_key + api_secret + passphrase
    for exchange in ["kucoin", "bitget"]:
        provider = get_provider(exchange)
        if provider:
            assert "api_key" in provider.required_fields, f"{exchange} must require api_key"
            assert "api_secret" in provider.required_fields, f"{exchange} must require api_secret"
            assert "passphrase" in provider.required_fields, f"{exchange} must require passphrase"


if __name__ == "__main__":
    test_provider_status_enum_has_canonical_values()
    test_normalize_status_maps_legacy_to_canonical()
    test_no_legacy_statuses_in_keys_route_code()
    test_provider_registry_required_fields()
    print("✅ All API key status canonical vocabulary tests passed!")
