#!/usr/bin/env python3
"""
Amarktai Crypto — VectorBT Research Runner
===========================================
SIDECAR ONLY — never imported by the live trading engine.

Usage:
    # Run a parameter sweep on BTC/USDT momentum strategy
    python research/vectorbt_runner.py --pair BTC/USDT --exchange binance

    # Run sweep for all Luno ZAR pairs
    python research/vectorbt_runner.py --exchange luno --all-pairs

    # Compare normal vs scalper thresholds
    python research/vectorbt_runner.py --compare-modes --pair BTC/USDT

    # Save results to JSON
    python research/vectorbt_runner.py --pair ETH/USDT --output results/eth_usdt.json

Install dependencies (isolated from live app):
    pip install vectorbt ccxt pandas numpy

The live app uses ccxt already, so only vectorbt and pandas need adding
for research purposes. Do NOT add vectorbt to the production requirements.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Soft-import vectorbt — gives a clear error if not installed rather than
# crashing at module load time.
# ---------------------------------------------------------------------------
try:
    import vectorbt as vbt  # type: ignore
    _VBT_AVAILABLE = True
except ImportError:
    _VBT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Exchange / fee constants  (mirrors live engine assumptions)
# ---------------------------------------------------------------------------

EXCHANGE_FEES: Dict[str, Dict[str, float]] = {
    "luno":     {"taker": 0.0025, "maker": 0.0025, "slippage": 0.0008, "spread_avg": 0.0006},
    "binance":  {"taker": 0.0010, "maker": 0.0010, "slippage": 0.0003, "spread_avg": 0.0002},
    "kucoin":   {"taker": 0.0010, "maker": 0.0008, "slippage": 0.0003, "spread_avg": 0.0002},
    "bybit":    {"taker": 0.0010, "maker": 0.0010, "slippage": 0.0003, "spread_avg": 0.0002},
    "kraken":   {"taker": 0.0016, "maker": 0.0016, "slippage": 0.0004, "spread_avg": 0.0003},
    "bitget":   {"taker": 0.0010, "maker": 0.0010, "slippage": 0.0003, "spread_avg": 0.0002},
    "gate":     {"taker": 0.0010, "maker": 0.0010, "slippage": 0.0003, "spread_avg": 0.0002},
    "coinbase": {"taker": 0.0060, "maker": 0.0060, "slippage": 0.0005, "spread_avg": 0.0004},
}

# Default pairs to scan per exchange
DEFAULT_PAIRS: Dict[str, List[str]] = {
    "luno":    ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR", "SOL/ZAR", "USDC/ZAR"],
    "binance": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
                "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT"],
}


# ---------------------------------------------------------------------------
# OHLCV data loading via CCXT
# ---------------------------------------------------------------------------

def fetch_ohlcv_ccxt(
    symbol: str,
    exchange_id: str = "binance",
    timeframe: str = "1h",
    limit: int = 500,
    since_days: int = 90,
) -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV data from an exchange via CCXT.

    Returns a DataFrame with columns: [open, high, low, close, volume]
    and a DatetimeIndex. Returns None on failure.
    """
    try:
        import ccxt  # type: ignore  # already installed in the live app
    except ImportError:
        print("ERROR: ccxt not installed. Run: pip install ccxt")
        return None

    try:
        exchange_cls = getattr(ccxt, exchange_id)
        exchange = exchange_cls({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

        since_ms = int(
            (datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000
        )

        raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)

        if not raw:
            print(f"No OHLCV data returned for {symbol} on {exchange_id}")
            return None

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        print(f"  ✓ {symbol} ({exchange_id}): {len(df)} candles, "
              f"{df.index[0].date()} → {df.index[-1].date()}")
        return df

    except Exception as err:
        print(f"  ✗ fetch_ohlcv_ccxt({symbol}, {exchange_id}): {err}")
        return None


# ---------------------------------------------------------------------------
# Technical indicator computation
# ---------------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute RSI, EMA-20, EMA-50, ATR-14, MACD on a price DataFrame.
    All computations use rolling pandas operations — no extra library needed.
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # RSI-14
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, 1e-9)
    df["rsi"] = 100 - 100 / (1 + rs)

    # EMA 20 and 50
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    # ATR-14
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr14"] / close * 100

    # MACD (12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]      = ema12 - ema26
    df["macd_sig"]  = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]

    # Volume ratio (current vs 20-bar avg)
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean().replace(0, 1e-9)

    return df


# ---------------------------------------------------------------------------
# Strategy signal generators
# ---------------------------------------------------------------------------

def signals_momentum(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.Series, pd.Series]:
    """
    Simple momentum strategy: EMA crossover + RSI filter.

    Entry: ema20 > ema50 AND rsi > rsi_min
    Exit:  ema20 < ema50 OR rsi > rsi_exit
    """
    rsi_min  = params.get("rsi_entry_min", 45)
    rsi_exit = params.get("rsi_exit_max",  75)
    entries = (df["ema20"] > df["ema50"]) & (df["rsi"] > rsi_min)
    exits   = (df["ema20"] < df["ema50"]) | (df["rsi"] > rsi_exit)
    return entries, exits


def signals_mean_reversion(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.Series, pd.Series]:
    """
    Mean-reversion strategy: buy RSI oversold, exit at midline.

    Entry: rsi < oversold_level
    Exit:  rsi > exit_level
    """
    oversold  = params.get("rsi_oversold",  35)
    exit_lvl  = params.get("rsi_exit",      55)
    entries   = df["rsi"] < oversold
    exits     = df["rsi"] > exit_lvl
    return entries, exits


def signals_scalper(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.Series, pd.Series]:
    """
    Scalper strategy: tight RSI + MACD histogram cross + high volume.

    Entry: rsi between 40-60 AND macd_hist crosses above 0 AND vol_ratio > threshold
    Exit:  after N bars OR macd_hist < 0
    """
    rsi_lo    = params.get("rsi_lo",          40)
    rsi_hi    = params.get("rsi_hi",          60)
    vol_min   = params.get("vol_ratio_min",  1.2)
    macd_cross = (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)
    entries = macd_cross & (df["rsi"] > rsi_lo) & (df["rsi"] < rsi_hi) & (df["vol_ratio"] > vol_min)
    # Exit: macd_hist goes negative
    exits   = df["macd_hist"] < 0
    return entries, exits


STRATEGY_SIGNALS = {
    "momentum":       signals_momentum,
    "mean_reversion": signals_mean_reversion,
    "scalper":        signals_scalper,
}


# ---------------------------------------------------------------------------
# Single VectorBT backtest
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    strategy: str,
    params: Dict[str, Any],
    exchange: str,
    tp_pct: float,
    sl_pct: float,
    init_cash: float = 10_000.0,
) -> Dict[str, Any]:
    """
    Run a single VectorBT backtest.

    Returns a dict with key metrics:
        total_return, sharpe, max_drawdown, total_trades, win_rate,
        avg_trade_return, expectancy_per_trade, fee_drag_pct, params
    """
    if not _VBT_AVAILABLE:
        raise ImportError("vectorbt not installed. Run: pip install vectorbt")

    df = compute_indicators(df.copy()).dropna()
    signal_fn = STRATEGY_SIGNALS[strategy]
    entries, exits = signal_fn(df, params)

    fees = EXCHANGE_FEES.get(exchange, EXCHANGE_FEES["binance"])
    round_trip_cost = (fees["taker"] * 2 + fees["slippage"] * 2 + fees["spread_avg"]) * 100

    # VectorBT portfolio with fixed TP/SL
    pf = vbt.Portfolio.from_signals(
        close=df["close"],
        entries=entries,
        exits=exits,
        sl_stop=sl_pct / 100,
        tp_stop=tp_pct / 100,
        fees=fees["taker"],
        slippage=fees["slippage"],
        init_cash=init_cash,
        freq="1h",
    )

    stats = pf.stats()
    total_trades = int(stats.get("Total Trades", 0))
    total_return = float(stats.get("Total Return [%]", 0))
    sharpe       = float(stats.get("Sharpe Ratio", 0) or 0)
    max_dd       = float(stats.get("Max Drawdown [%]", 0))

    win_rate = float(stats.get("Win Rate [%]", 0)) if total_trades > 0 else 0.0
    avg_trade = total_return / max(total_trades, 1)

    # Simple expectancy per trade (win_rate × avg_win - loss_rate × avg_loss)
    # approximated as: avg_trade return (after fees)
    expectancy = avg_trade - round_trip_cost

    return {
        "strategy":          strategy,
        "exchange":          exchange,
        "params":            params,
        "tp_pct":            tp_pct,
        "sl_pct":            sl_pct,
        "total_return_pct":  round(total_return, 3),
        "sharpe":            round(sharpe, 3),
        "max_drawdown_pct":  round(max_dd, 3),
        "total_trades":      total_trades,
        "win_rate_pct":      round(win_rate, 2),
        "avg_trade_pct":     round(avg_trade, 4),
        "expectancy_pct":    round(expectancy, 4),
        "round_trip_cost_pct": round(round_trip_cost, 4),
    }


# ---------------------------------------------------------------------------
# Parameter sweep
# ---------------------------------------------------------------------------

def parameter_sweep(
    df: pd.DataFrame,
    strategy: str,
    exchange: str,
    param_grid: Dict[str, List[Any]],
    tp_range: List[float],
    sl_range: List[float],
    init_cash: float = 10_000.0,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run a grid sweep over all combinations of parameters.

    param_grid example:
        {"rsi_entry_min": [40, 45, 50], "rsi_exit_max": [70, 75, 80]}

    tp_range: list of take-profit % values to test
    sl_range: list of stop-loss % values to test

    Returns sorted list of result dicts (best total_return first).
    """
    from itertools import product as _product

    keys   = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(_product(*values))

    results = []
    total_runs = len(combos) * len(tp_range) * len(sl_range)
    if verbose:
        print(f"\n  Running {total_runs} backtest combinations for {strategy} on {exchange}…")

    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        for tp in tp_range:
            for sl in sl_range:
                if tp <= sl:
                    continue  # skip invalid R:R
                try:
                    result = run_backtest(df, strategy, params, exchange, tp, sl, init_cash)
                    results.append(result)
                except Exception as err:
                    if verbose:
                        print(f"    ✗ combo {params} tp={tp} sl={sl}: {err}")

    results.sort(key=lambda r: r["total_return_pct"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def print_report(results: List[Dict[str, Any]], top_n: int = 10) -> None:
    """Print a human-readable ranked summary of sweep results."""
    if not results:
        print("  No results to display.")
        return

    print(f"\n{'='*80}")
    print(f"  TOP {min(top_n, len(results))} RESULTS  (of {len(results)} total combinations)")
    print(f"{'='*80}")
    header = f"{'#':>3}  {'Return%':>8}  {'Sharpe':>7}  {'DD%':>6}  {'Trades':>6}  "
    header += f"{'WinRate%':>8}  {'Expect%':>8}  {'TP':>5}  {'SL':>5}  Params"
    print(header)
    print("-" * 100)

    for rank, r in enumerate(results[:top_n], 1):
        params_str = ", ".join(f"{k}={v}" for k, v in r["params"].items())
        print(
            f"{rank:>3}  {r['total_return_pct']:>8.2f}%  {r['sharpe']:>7.2f}  "
            f"{r['max_drawdown_pct']:>6.2f}%  {r['total_trades']:>6}  "
            f"{r['win_rate_pct']:>8.1f}%  {r['expectancy_pct']:>8.4f}%  "
            f"{r['tp_pct']:>5.1f}%  {r['sl_pct']:>5.1f}%  {params_str}"
        )

    print(f"\n  Exchange round-trip cost: {results[0]['round_trip_cost_pct']:.4f}%")
    print(f"  (Only strategies with expectancy > 0 are viable in production)\n")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Amarktai Crypto — VectorBT Research Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--pair",     default="BTC/USDT", help="Trading pair, e.g. BTC/USDT or BTC/ZAR")
    parser.add_argument("--exchange", default="binance",  help="Exchange ID (binance, luno, etc.)")
    parser.add_argument("--strategy", default="momentum", choices=["momentum", "mean_reversion", "scalper"],
                        help="Strategy type to sweep")
    parser.add_argument("--timeframe",default="1h",       help="OHLCV timeframe (1m, 5m, 15m, 1h, 4h)")
    parser.add_argument("--days",     default=90, type=int,
                        help="Days of historical data to fetch")
    parser.add_argument("--top",      default=10, type=int,
                        help="How many top results to print")
    parser.add_argument("--output",   default=None,
                        help="Save full results to a JSON file")
    parser.add_argument("--compare-modes", action="store_true",
                        help="Run both momentum and scalper and compare results")
    parser.add_argument("--all-pairs", action="store_true",
                        help="Sweep all default pairs for the exchange")
    return parser.parse_args()


def _default_grid_for_strategy(strategy: str) -> Dict[str, Any]:
    """Return default parameter grid for each strategy type."""
    if strategy == "momentum":
        return {
            "param_grid": {
                "rsi_entry_min": [40, 45, 50],
                "rsi_exit_max":  [70, 75, 80],
            },
            "tp_range": [1.5, 2.0, 2.5, 3.0, 4.0, 5.5],
            "sl_range": [0.8, 1.0, 1.5, 2.0],
        }
    elif strategy == "mean_reversion":
        return {
            "param_grid": {
                "rsi_oversold": [25, 30, 35, 40],
                "rsi_exit":     [50, 55, 60, 65],
            },
            "tp_range": [1.5, 2.5, 3.0, 4.0],
            "sl_range": [0.8, 1.0, 1.5],
        }
    elif strategy == "scalper":
        return {
            "param_grid": {
                "rsi_lo":         [35, 40, 45],
                "rsi_hi":         [55, 60, 65],
                "vol_ratio_min":  [1.0, 1.2, 1.5],
            },
            "tp_range": [0.3, 0.5, 0.8, 1.0, 1.5],
            "sl_range": [0.2, 0.3, 0.5, 0.8],
        }
    return {}


def main() -> None:
    args = _parse_args()

    if not _VBT_AVAILABLE:
        print("ERROR: vectorbt is not installed.")
        print("  Run:  pip install vectorbt")
        print("  (Do NOT add vectorbt to the live app's requirements.txt)")
        sys.exit(1)

    pairs_to_run = DEFAULT_PAIRS.get(args.exchange, [args.pair]) if args.all_pairs else [args.pair]
    strategies_to_run = (
        ["momentum", "scalper"] if args.compare_modes else [args.strategy]
    )

    all_results: Dict[str, List[Dict[str, Any]]] = {}

    for pair in pairs_to_run:
        print(f"\n{'='*60}")
        print(f"  PAIR: {pair}  |  Exchange: {args.exchange}")
        print(f"{'='*60}")

        df = fetch_ohlcv_ccxt(pair, args.exchange, args.timeframe, limit=500, since_days=args.days)
        if df is None or len(df) < 60:
            print(f"  Skipping {pair}: insufficient data (< 60 bars)")
            continue

        for strat in strategies_to_run:
            print(f"\n  ── Strategy: {strat} ──")
            grid_cfg = _default_grid_for_strategy(strat)
            results = parameter_sweep(
                df,
                strat,
                args.exchange,
                grid_cfg["param_grid"],
                grid_cfg["tp_range"],
                grid_cfg["sl_range"],
                verbose=True,
            )
            print_report(results, top_n=args.top)
            key = f"{pair}::{strat}"
            all_results[key] = results

    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\n  Results saved → {args.output}")


if __name__ == "__main__":
    main()
