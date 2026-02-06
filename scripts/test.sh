#!/usr/bin/env bash
#
# Test Runner - Prevents third-party plugin auto-loading
# =======================================================
#
# Problem: pytest-ethereum and other web3 plugins auto-load and crash tests.
# Solution: Disable plugin autoload and run tests with clean environment.
#
# Usage:
#   ./scripts/test.sh                 # Run all tests
#   ./scripts/test.sh tests/test_*.py # Run specific tests
#

set -e

# Change to repository root
cd "$(dirname "$0")/.."

# Export pytest configuration to prevent plugin auto-loading
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Run pytest with recommended settings
# -q: Quiet output (less verbose)
# --maxfail=25: Stop after 25 failures (prevents cascading failures)
# --disable-warnings: Suppress warning output for cleaner results
#
# Pass through any additional arguments (e.g., specific test files)
python -m pytest -q --maxfail=25 --disable-warnings "$@"
