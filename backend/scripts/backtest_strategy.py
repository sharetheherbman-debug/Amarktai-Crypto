#!/usr/bin/env python3
"""
Vectorbt Strategy Backtester — offline performance analysis tool.

Tests the current paper trading signal logic (RSI + MACD consensus) against
90 days of real OHLCV data fetched from Binance public API.  Run this script
before deploying any parameter change to validate it improves Sharpe ratio
and reduces max drawdown without requiring live capital.

Usage
-----
    python3 backtest_strategy.py --symbol BTC/USDT --days 90
    python3 backtest_strategy.py --symbol ETH/USDT --days 180 --fee 0.001
    python3 backtest_strategy.py --list-symbols

Output
------
    Console summary: total return, CAGR, Sharpe, Sortino, max drawdown,
                     win rate, profit factor, number of trades.

Requirements
------------
    pip install vectorbt ccxt
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest")

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
try:
    import vectorbt as vbt
except ImportError:
    print("vectorbt is not installed. Run: pip install vectorbt", file=sys.stderr)
    sys.exit(1)

try:
    import ccxt
except ImportError:
    print("ccxt is not installed. Run: pip install ccxt", file=sys.stderr)
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("pandas is not installed.", file=sys.stderr)
    sys.exit(1)

# Supported symbols (mirrors PAPER_PAIR_WHITELIST for USDT exchanges)
SUPPORTED_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT",
    "BNB/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
]

DEFAULT_INIT_CASH = 10_000.0  # USD equivalent
DEFAULT_FEE = 0.001           # 0.1% per side


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def fetch_ohlcv(symbol: str, days: int, timeframe: str = "1h") -> pd.DataFrame:
    """Fetch OHLCV data from Binance public API (no key required)."""
    exchange = ccxt.binance({"enableRateLimit": True})
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since_ms = candles[-1][0] + 1
        if len(candles) < 1000:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    logger.info("Fetched %d candles for %s (%s timeframe, %d days)", len(df), symbol, timeframe, days)
    return df


# ---------------------------------------------------------------------------
# Signal generation — mirrors ml_predictor rule-based fallback
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Compute RSI + MACD consensus signals that match the rule-based prediction
    used in ml_predictor.py when XGBoost is unavailable.

    Returns (entries, exits) boolean Series.
    """
    close = df["close"]

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD(12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - signal_line

    # SMA20
    sma20 = close.rolling(20).mean()
    close_vs_sma = close - sma20

    # Entry conditions (bullish consensus: 2 of 3 signals agree)
    rsi_bullish = rsi < 45          # oversold
    macd_bullish = macd_hist > 0    # positive histogram
    price_bullish = close_vs_sma > 0  # above 20-period SMA

    consensus = rsi_bullish.astype(int) + macd_bullish.astype(int) + price_bullish.astype(int)
    entries = consensus >= 2

    # Exit conditions (bearish consensus)
    rsi_bearish = rsi > 60
    macd_bearish = macd_hist < 0
    price_bearish = close_vs_sma < 0

    exit_consensus = rsi_bearish.astype(int) + macd_bearish.astype(int) + price_bearish.astype(int)
    exits = exit_consensus >= 2

    return entries, exits


# ---------------------------------------------------------------------------
# Run backtest
# ---------------------------------------------------------------------------

def run_backtest(
    symbol: str,
    days: int,
    init_cash: float = DEFAULT_INIT_CASH,
    fee: float = DEFAULT_FEE,
    timeframe: str = "1h",
) -> None:
    df = fetch_ohlcv(symbol, days, timeframe)
    entries, exits = compute_signals(df)

    close = df["close"]

    # Run with vectorbt Portfolio
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        init_cash=init_cash,
        fees=fee,
        freq=timeframe,
    )

    # ---- Print summary --------------------------------------------------
    stats = pf.stats()
    print(f"\n{'='*60}")
    print(f"  Backtest: {symbol}  |  {days}d  |  {timeframe}  |  fee={fee*100:.2f}%")
    print(f"{'='*60}")

    def _fmt(key: str) -> str:
        try:
            val = stats[key]
            if isinstance(val, float):
                return f"{val:.4f}"
            return str(val)
        except KeyError:
            return "N/A"

    print(f"  Total Return:          {_fmt('Total Return [%]')} %")
    print(f"  CAGR:                  {_fmt('Annualized Return [%]')} %")
    print(f"  Sharpe Ratio:          {_fmt('Sharpe Ratio')}")
    print(f"  Sortino Ratio:         {_fmt('Sortino Ratio')}")
    print(f"  Max Drawdown:          {_fmt('Max Drawdown [%]')} %")
    print(f"  Win Rate:              {_fmt('Win Rate [%]')} %")
    print(f"  Profit Factor:         {_fmt('Profit Factor')}")
    print(f"  Total Trades:          {_fmt('Total Trades')}")
    print(f"  Avg Trade Duration:    {_fmt('Avg Winning Trade Duration')}")
    print(f"  Final Portfolio Value: {init_cash + pf.total_profit():.2f}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vectorbt strategy backtester")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--days", type=int, default=90, help="Lookback window in days")
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE, help="Fee per side (e.g. 0.001 = 0.1%%)")
    parser.add_argument("--cash", type=float, default=DEFAULT_INIT_CASH, help="Starting capital (USD)")
    parser.add_argument("--timeframe", default="1h", help="OHLCV timeframe (default: 1h)")
    parser.add_argument("--list-symbols", action="store_true", help="Print supported symbols and exit")

    args = parser.parse_args()

    if args.list_symbols:
        print("Supported symbols:", ", ".join(SUPPORTED_SYMBOLS))
        sys.exit(0)

    run_backtest(
        symbol=args.symbol,
        days=args.days,
        init_cash=args.cash,
        fee=args.fee,
        timeframe=args.timeframe,
    )
