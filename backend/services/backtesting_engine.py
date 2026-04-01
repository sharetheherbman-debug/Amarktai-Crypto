"""
Backtesting Engine.
Validates trading strategies against historical data.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

# Fee schedules per exchange (maker+taker round-trip in basis points)
_EXCHANGE_FEES_BPS: Dict[str, float] = {
    "binance": 20.0,
    "luno": 50.0,
    "kraken": 32.0,
    "coinbase": 40.0,
    "bybit": 20.0,
}

_DEFAULT_FEE_BPS = 30.0


async def run_backtest(
    symbol: str,
    exchange: str,
    strategy: str = "normal",
    days: int = 90,
    initial_capital: float = 10000,
) -> dict:
    """Run a backtest on historical data using rule-based signals.

    Parameters
    ----------
    symbol : str
        Trading pair, e.g. "BTC/USDT".
    exchange : str
        Exchange id for CCXT, e.g. "binance".
    strategy : str
        Strategy type — "normal" or "scalper".
    days : int
        Number of historical days to backtest.
    initial_capital : float
        Starting capital in quote currency.

    Returns
    -------
    dict with performance metrics.
    """
    try:
        from ml_predictor import fetch_ohlcv, compute_indicators, _rule_based_prediction

        # Fetch historical data — hourly candles
        limit = min(days * 24, 1000)
        df = fetch_ohlcv(
            pair=symbol,
            timeframe="1h",
            limit=limit,
            exchange_id=exchange.lower(),
        )
        df = compute_indicators(df)
        df = df.dropna(subset=["rsi", "macd"]).reset_index(drop=True)

        if df.empty:
            return _empty_result(symbol, exchange, strategy, days, initial_capital,
                                 reason="Insufficient data after indicator computation")

        return _simulate(df, symbol, exchange, strategy, initial_capital)

    except RuntimeError as exc:
        # ccxt not installed — use synthetic simulation
        logger.warning("CCXT unavailable (%s), using synthetic backtest", exc)
        return _synthetic_backtest(symbol, exchange, strategy, days, initial_capital)
    except Exception as exc:
        logger.error("Backtest failed for %s on %s: %s", symbol, exchange, exc)
        return _empty_result(symbol, exchange, strategy, days, initial_capital,
                             reason=str(exc))


def _simulate(
    df,
    symbol: str,
    exchange: str,
    strategy: str,
    initial_capital: float,
) -> dict:
    """Simulate trades on indicator-enriched OHLCV data."""
    from ml_predictor import _rule_based_prediction

    fee_bps = _EXCHANGE_FEES_BPS.get(exchange.lower(), _DEFAULT_FEE_BPS)
    fee_pct = fee_bps / 10000.0

    capital = initial_capital
    trades: List[dict] = []
    position = None  # None or {"entry_price": ..., "entry_idx": ...}
    peak_capital = capital
    max_drawdown = 0.0

    hold_limit = 6 if strategy == "scalper" else 24  # candles

    for idx in range(len(df)):
        row = df.iloc[idx]
        direction, confidence, predicted_change = _rule_based_prediction(row)

        if position is None:
            # Entry signal
            if direction == "up" and confidence >= 0.60:
                position = {
                    "entry_price": float(row["close"]),
                    "entry_idx": idx,
                    "direction": "long",
                    "confidence": confidence,
                }
        else:
            # Check exit conditions
            entry_price = position["entry_price"]
            current_price = float(row["close"])
            hold_candles = idx - position["entry_idx"]

            pnl_pct = (current_price - entry_price) / entry_price

            # Exit rules
            should_exit = False
            exit_reason = ""

            stop_loss = -0.015 if strategy == "normal" else -0.007
            take_profit = 0.02 if strategy == "normal" else 0.01

            if pnl_pct <= stop_loss:
                should_exit = True
                exit_reason = "stop_loss"
            elif pnl_pct >= take_profit:
                should_exit = True
                exit_reason = "take_profit"
            elif hold_candles >= hold_limit:
                should_exit = True
                exit_reason = "max_hold_exceeded"
            elif direction == "down" and confidence >= 0.65:
                should_exit = True
                exit_reason = "signal_reversal"

            if should_exit:
                gross_pnl = capital * pnl_pct
                fee_cost = capital * fee_pct
                net_pnl = gross_pnl - fee_cost

                capital += net_pnl
                if capital > peak_capital:
                    peak_capital = capital
                dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
                if dd > max_drawdown:
                    max_drawdown = dd

                trades.append({
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "pnl_pct": round(pnl_pct * 100, 4),
                    "net_pnl": round(net_pnl, 4),
                    "fee_cost": round(fee_cost, 4),
                    "exit_reason": exit_reason,
                    "hold_candles": hold_candles,
                })
                position = None

    # Close any remaining position at last price
    if position is not None and len(df) > 0:
        last_price = float(df.iloc[-1]["close"])
        entry_price = position["entry_price"]
        pnl_pct = (last_price - entry_price) / entry_price
        gross_pnl = capital * pnl_pct
        fee_cost = capital * fee_pct
        net_pnl = gross_pnl - fee_cost
        capital += net_pnl
        trades.append({
            "entry_price": entry_price,
            "exit_price": last_price,
            "pnl_pct": round(pnl_pct * 100, 4),
            "net_pnl": round(net_pnl, 4),
            "fee_cost": round(fee_cost, 4),
            "exit_reason": "end_of_data",
            "hold_candles": len(df) - 1 - position["entry_idx"],
        })

    return _build_metrics(trades, initial_capital, capital, max_drawdown,
                          symbol, exchange, strategy)


def _synthetic_backtest(
    symbol: str,
    exchange: str,
    strategy: str,
    days: int,
    initial_capital: float,
) -> dict:
    """Deterministic synthetic backtest when live data is unavailable."""
    import hashlib

    seed_bytes = hashlib.sha256(f"{symbol}{exchange}{strategy}{days}".encode()).digest()
    seed_val = int.from_bytes(seed_bytes[:4], "big")

    fee_bps = _EXCHANGE_FEES_BPS.get(exchange.lower(), _DEFAULT_FEE_BPS)
    fee_pct = fee_bps / 10000.0

    trades_per_day = 2 if strategy == "scalper" else 1
    total_trades = days * trades_per_day
    win_rate = 0.55

    capital = initial_capital
    peak_capital = capital
    max_drawdown = 0.0
    trades: List[dict] = []

    for i in range(total_trades):
        # Deterministic pseudo-random using seed
        h = int.from_bytes(
            hashlib.sha256(f"{seed_val}{i}".encode()).digest()[:4], "big"
        )
        is_win = (h % 100) < int(win_rate * 100)

        if is_win:
            pnl_pct = 0.008 + (h % 12) / 1000.0
        else:
            pnl_pct = -(0.005 + (h % 10) / 1000.0)

        gross_pnl = capital * pnl_pct
        fee_cost = capital * fee_pct
        net_pnl = gross_pnl - fee_cost
        capital += net_pnl

        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        trades.append({
            "pnl_pct": round(pnl_pct * 100, 4),
            "net_pnl": round(net_pnl, 4),
            "fee_cost": round(fee_cost, 4),
            "exit_reason": "synthetic",
        })

    return _build_metrics(trades, initial_capital, capital, max_drawdown,
                          symbol, exchange, strategy, source="synthetic")


def _build_metrics(
    trades: List[dict],
    initial_capital: float,
    final_capital: float,
    max_drawdown: float,
    symbol: str,
    exchange: str,
    strategy: str,
    source: str = "historical",
) -> dict:
    """Compute performance metrics from trade list."""
    total = len(trades)
    if total == 0:
        return _empty_result(symbol, exchange, strategy, 0, initial_capital,
                             reason="No trades generated")

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    net_pnl = sum(t["net_pnl"] for t in trades)

    returns = [t["net_pnl"] / initial_capital for t in trades]
    avg_return = sum(returns) / len(returns)
    std_dev = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 0.0
    sharpe = (avg_return / std_dev) * math.sqrt(252) if std_dev > 0 else 0.0

    return {
        "symbol": symbol,
        "exchange": exchange,
        "strategy": strategy,
        "data_source": source,
        "initial_capital": initial_capital,
        "final_capital": round(final_capital, 2),
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / total * 100, 2) if total else 0.0,
        "net_pnl": round(net_pnl, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 4),
        "total_fees": round(sum(t.get("fee_cost", 0) for t in trades), 2),
        "avg_trade_pnl": round(net_pnl / total, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _empty_result(
    symbol: str,
    exchange: str,
    strategy: str,
    days: int,
    initial_capital: float,
    reason: str = "",
) -> dict:
    return {
        "symbol": symbol,
        "exchange": exchange,
        "strategy": strategy,
        "data_source": "none",
        "initial_capital": initial_capital,
        "final_capital": initial_capital,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "net_pnl": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "total_fees": 0.0,
        "avg_trade_pnl": 0.0,
        "reason": reason,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
