#!/usr/bin/env python3
"""
Manual verification that the fix works correctly
Tests that list_providers() returns dicts and we access them correctly
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.provider_registry import list_providers

def test_list_providers_format():
    """Verify list_providers returns dicts with correct keys"""
    print("Testing list_providers() return format...")
    
    all_providers = list_providers()
    
    print(f"✅ list_providers() returned {len(all_providers)} providers")
    
    # Verify it's a list
    assert isinstance(all_providers, list), "list_providers() should return a list"
    print("✅ Return type is list")
    
    # Verify first item is a dict
    if all_providers:
        first_provider = all_providers[0]
        assert isinstance(first_provider, dict), "Provider should be a dict"
        print("✅ Providers are dicts, not objects")
        
        # Verify it has 'id' key
        assert 'id' in first_provider, "Provider dict should have 'id' key"
        print(f"✅ Provider has 'id' key: {first_provider['id']}")
        
        # This is what the OLD code tried to do (would crash):
        try:
            provider_id = first_provider.provider_id  # This should fail
            print("❌ ERROR: Should not be able to access .provider_id on dict!")
            sys.exit(1)
        except AttributeError:
            print("✅ Confirmed: dict has no .provider_id attribute (as expected)")
        
        # This is what the NEW code does (works correctly):
        provider_ids = [p['id'] for p in all_providers]
        print(f"✅ Successfully extracted {len(provider_ids)} provider IDs: {', '.join(provider_ids)}")
        
        # Verify we have exactly 10 providers
        assert len(provider_ids) == 10, f"Expected 10 providers, got {len(provider_ids)}"
        print("✅ Exactly 10 providers found")
        
        # Verify the expected providers
        expected = ["openai", "flokx", "fetchai", "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
        for expected_id in expected:
            assert expected_id in provider_ids, f"Expected provider {expected_id} not found"
        print(f"✅ All expected providers present: {', '.join(expected)}")
        
    print("\n🎉 All verifications passed! The fix is correct.")
    return True

if __name__ == "__main__":
    try:
        test_list_providers_format()
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
