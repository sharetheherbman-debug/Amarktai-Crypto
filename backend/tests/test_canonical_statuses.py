"""
Test Canonical API Key Statuses - Go-Live Verification
Ensures that all API endpoints return canonical status values
"""

import pytest
from services.provider_registry import ProviderStatus
from routes.keys import normalize_status, get_status_display


def test_provider_status_enum_canonical_values():
    """Test that ProviderStatus enum has canonical values"""
    
    # Canonical values (go-live standard)
    assert ProviderStatus.NOT_CONFIGURED.value == "not_configured"
    assert ProviderStatus.CONFIGURED_UNTESTED.value == "configured_untested"
    assert ProviderStatus.CONFIGURED_VALID.value == "configured_valid"
    assert ProviderStatus.CONFIGURED_INVALID.value == "configured_invalid"
    
    # Legacy aliases should still exist for backward compatibility
    assert ProviderStatus.SAVED_UNTESTED.value == "saved_untested"
    assert ProviderStatus.TEST_OK.value == "test_ok"
    assert ProviderStatus.TEST_FAILED.value == "test_failed"


def test_normalize_status_converts_legacy_to_canonical():
    """Test that normalize_status() converts legacy values to canonical"""
    
    # Legacy -> Canonical mappings
    assert normalize_status("saved_untested") == "configured_untested"
    assert normalize_status("test_ok") == "configured_valid"
    assert normalize_status("test_failed") == "configured_invalid"
    
    # Canonical values should pass through unchanged
    assert normalize_status("configured_untested") == "configured_untested"
    assert normalize_status("configured_valid") == "configured_valid"
    assert normalize_status("configured_invalid") == "configured_invalid"
    assert normalize_status("not_configured") == "not_configured"
    
    # Unknown values should pass through unchanged
    assert normalize_status("unknown_status") == "unknown_status"


def test_get_status_display_returns_correct_text():
    """Test that get_status_display() returns human-readable text"""
    
    # Test canonical status displays
    assert get_status_display("not_configured") == "Not configured"
    assert get_status_display("configured_untested") == "Configured (untested)"
    assert get_status_display("configured_valid") == "Valid ✅"
    assert get_status_display("configured_invalid") == "Invalid ❌"
    
    # Unknown status should return itself
    assert get_status_display("unknown") == "unknown"


def test_no_legacy_statuses_in_canonical_enum():
    """Test that canonical enum values don't use legacy strings"""
    
    # The primary enum values should be canonical
    assert ProviderStatus.CONFIGURED_UNTESTED.value != "saved_untested"
    assert ProviderStatus.CONFIGURED_VALID.value != "test_ok"
    assert ProviderStatus.CONFIGURED_INVALID.value != "test_failed"
    
    # Verify they ARE the canonical values
    assert ProviderStatus.CONFIGURED_UNTESTED.value == "configured_untested"
    assert ProviderStatus.CONFIGURED_VALID.value == "configured_valid"
    assert ProviderStatus.CONFIGURED_INVALID.value == "configured_invalid"


def test_canonical_status_values_are_consistent():
    """Test that all canonical status values follow naming convention"""
    
    canonical_statuses = [
        ProviderStatus.NOT_CONFIGURED.value,
        ProviderStatus.CONFIGURED_UNTESTED.value,
        ProviderStatus.CONFIGURED_VALID.value,
        ProviderStatus.CONFIGURED_INVALID.value,
    ]
    
    # All canonical statuses should use underscores (snake_case)
    for status in canonical_statuses:
        assert "_" in status or status == "not_configured"
        assert status.islower()
    
    # Configured statuses should start with "configured_"
    configured_statuses = [
        ProviderStatus.CONFIGURED_UNTESTED.value,
        ProviderStatus.CONFIGURED_VALID.value,
        ProviderStatus.CONFIGURED_INVALID.value,
    ]
    
    for status in configured_statuses:
        assert status.startswith("configured_")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
