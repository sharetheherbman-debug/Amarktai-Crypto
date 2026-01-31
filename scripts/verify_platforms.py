#!/usr/bin/env python3
"""
Verify Platform CCXT Support
Checks that all 7 supported platforms are available in CCXT (both sync and async)
Exits with non-zero status if any platform is missing or unavailable
"""

import sys
import ccxt
import ccxt.async_support as ccxt_async
import asyncio


# Expected platforms from backend/config/platforms.py
REQUIRED_PLATFORMS = {
    'luno': 'luno',
    'binance': 'binance',
    'kucoin': 'kucoin',
    'bybit': 'bybit',
    'kraken': 'kraken',
    'bitget': 'bitget',
    'gate': 'gateio',  # Note: CCXT uses 'gateio' not 'gate'
}


def check_sync_support():
    """Check synchronous CCXT support"""
    print("Checking CCXT synchronous support...")
    all_exchanges = ccxt.exchanges
    
    errors = []
    for platform, ccxt_id in REQUIRED_PLATFORMS.items():
        if ccxt_id in all_exchanges:
            print(f"  ✓ {platform} ({ccxt_id}) - sync support OK")
            
            # Try instantiating
            try:
                exchange_class = getattr(ccxt, ccxt_id)
                exchange = exchange_class()
                print(f"    → Can instantiate {ccxt_id}")
            except Exception as e:
                print(f"    ✗ Cannot instantiate {ccxt_id}: {e}")
                errors.append(f"{platform}: instantiation error in sync mode")
        else:
            print(f"  ✗ {platform} ({ccxt_id}) - NOT FOUND in CCXT")
            errors.append(f"{platform}: not available in CCXT sync")
    
    return errors


async def check_async_support():
    """Check asynchronous CCXT support"""
    print("\nChecking CCXT asynchronous support...")
    all_exchanges = ccxt_async.exchanges
    
    errors = []
    for platform, ccxt_id in REQUIRED_PLATFORMS.items():
        if ccxt_id in all_exchanges:
            print(f"  ✓ {platform} ({ccxt_id}) - async support OK")
            
            # Try instantiating
            try:
                exchange_class = getattr(ccxt_async, ccxt_id)
                exchange = exchange_class()
                print(f"    → Can instantiate {ccxt_id}")
                await exchange.close()  # Cleanup
            except Exception as e:
                print(f"    ✗ Cannot instantiate {ccxt_id}: {e}")
                errors.append(f"{platform}: instantiation error in async mode")
        else:
            print(f"  ✗ {platform} ({ccxt_id}) - NOT FOUND in CCXT async")
            errors.append(f"{platform}: not available in CCXT async")
    
    return errors


def main():
    """Main verification function"""
    print("=" * 60)
    print("Platform CCXT Support Verification")
    print("=" * 60)
    print(f"\nVerifying {len(REQUIRED_PLATFORMS)} required platforms:")
    for platform, ccxt_id in REQUIRED_PLATFORMS.items():
        print(f"  - {platform}: {ccxt_id}")
    print()
    
    # Check sync
    sync_errors = check_sync_support()
    
    # Check async
    async_errors = asyncio.run(check_async_support())
    
    # Summary
    all_errors = sync_errors + async_errors
    
    print("\n" + "=" * 60)
    if all_errors:
        print("❌ VERIFICATION FAILED")
        print("=" * 60)
        print("\nErrors found:")
        for error in all_errors:
            print(f"  - {error}")
        print("\nPlease ensure you have the latest version of CCXT installed:")
        print("  pip install --upgrade ccxt")
        sys.exit(1)
    else:
        print("✅ VERIFICATION PASSED")
        print("=" * 60)
        print("\nAll platforms are supported in both sync and async CCXT modes.")
        print("Ready for deployment!")
        sys.exit(0)


if __name__ == "__main__":
    main()
