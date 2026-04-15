#!/usr/bin/env bash
# Freqtrade Validation Harness — Setup Script
# ============================================
# Installs Freqtrade in a local Python venv, isolated from the live app.
# NEVER modify the main backend/requirements.txt with Freqtrade dependencies.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Amarktai Crypto: Freqtrade Validation Setup ==="
echo ""

# Python version check
PY_VER=$(python3 --version 2>&1)
echo "  Using: $PY_VER"

# Create isolated venv
if [ ! -d "freqtrade_venv" ]; then
    echo "  Creating isolated virtual environment: freqtrade_venv/"
    python3 -m venv freqtrade_venv
else
    echo "  Virtual environment already exists: freqtrade_venv/"
fi

source freqtrade_venv/bin/activate

# Install Freqtrade
echo ""
echo "  Installing Freqtrade (may take 2-3 minutes)..."
pip install --quiet --upgrade pip
pip install --quiet "freqtrade"

# Create required directories
mkdir -p user_data/data user_data/backtest_results user_data/logs user_data/notebooks

echo ""
echo "=== Setup complete ==="
echo ""
echo "  Usage:"
echo ""
echo "    source freqtrade_venv/bin/activate"
echo ""
echo "    # Download Binance historical data"
echo "    freqtrade download-data \\"
echo "        --exchange binance \\"
echo "        --pairs BTC/USDT ETH/USDT SOL/USDT \\"
echo "        --timeframes 1h \\"
echo "        --timerange 20240101-"
echo ""
echo "    # Run backtest"
echo "    freqtrade backtesting \\"
echo "        --config config.json \\"
echo "        --strategy AmarktaiBaseline \\"
echo "        --timerange 20240101-20240401"
echo ""
echo "    # Start dry-run (paper mode)"
echo "    freqtrade trade --config config.json --strategy AmarktaiBaseline"
echo ""
echo "  Results in: user_data/backtest_results/"
echo "  Logs:       user_data/logs/"
echo ""
echo "  See README.md for how to compare Freqtrade results to Amarktai paper engine."
