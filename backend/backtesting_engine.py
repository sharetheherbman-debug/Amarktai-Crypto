"""
Backtesting Engine
- Replays real OHLCV candle data fetched from CCXT exchanges
- Applies indicator-driven rule-based signals (same as live MLPredictor)
- NO random numbers — results are fully deterministic and reproducible
- Falls back to an explicit error if OHLCV data is unavailable (never fakes data)
"""

import asyncio
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from logger_config import logger

# Reuse the real indicator + rule-based engine from ml_predictor
try:
    from ml_predictor import fetch_ohlcv, compute_indicators, _rule_based_prediction
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    logger.warning("ml_predictor not available — backtesting disabled")


_RISK_STOP_LOSS: Dict[str, float] = {
    "safe": 0.005,       # 0.5 %
    "balanced": 0.010,   # 1.0 %
    "risky": 0.015,      # 1.5 %
    "aggressive": 0.020, # 2.0 %
}
_RISK_TAKE_PROFIT: Dict[str, float] = {
    "safe": 0.008,
    "balanced": 0.015,
    "risky": 0.020,
    "aggressive": 0.030,
}


class BacktestingEngine:
    def __init__(self):
        self.results_cache: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def backtest_strategy(
        self,
        strategy_params: dict,
        start_date: str,
        end_date: str,
        initial_capital: float = 1000,
    ) -> dict:
        """Backtest a strategy using real OHLCV data.

        Parameters
        ----------
        strategy_params : dict
            Keys: exchange (str), pair (str), risk_mode (str),
                  timeframe (str, default "1h")
        start_date, end_date : str  ISO-8601 date strings
        initial_capital : float

        Returns a result dict with ``trades`` and ``metrics`` keys or
        an ``error`` key if data is unavailable.
        """
        if not _ML_AVAILABLE:
            return {"error": "ml_predictor (OHLCV + indicators) not available"}

        exchange_id = strategy_params.get("exchange", "binance")
        pair = strategy_params.get("pair", "BTC/USDT")
        risk_mode = strategy_params.get("risk_mode", "balanced")
        timeframe = strategy_params.get("timeframe", "1h")

        logger.info(
            f"Starting backtest: {pair} on {exchange_id} "
            f"({start_date} → {end_date}, risk={risk_mode})"
        )

        try:
            # Fetch OHLCV in executor so we don't block the event loop
            df_raw = await asyncio.get_event_loop().run_in_executor(
                None, fetch_ohlcv, pair, timeframe, 500, exchange_id
            )
            df = compute_indicators(df_raw)
            df = df.dropna(subset=["rsi", "macd"]).reset_index(drop=True)

            if df.empty:
                return {"error": f"Not enough OHLCV data for {pair} on {exchange_id}"}

            # Filter by date range if timestamp column exists
            if "timestamp" in df.columns:
                try:
                    start_dt = datetime.fromisoformat(start_date).replace(
                        tzinfo=timezone.utc
                    )
                    end_dt = datetime.fromisoformat(end_date).replace(
                        tzinfo=timezone.utc
                    )
                    mask = (df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)
                    df = df[mask].reset_index(drop=True)
                except Exception:
                    pass  # keep full dataset if date parse fails

            trades = self._replay_candles(df, initial_capital, risk_mode)
            metrics = self._calculate_metrics(trades, initial_capital)

            result = {
                "strategy": strategy_params,
                "period": {"start": start_date, "end": end_date},
                "initial_capital": initial_capital,
                "candles_used": len(df),
                "data_source": "real_ohlcv",
                "trades": trades,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            cache_key = f"{exchange_id}:{pair}:{risk_mode}:{start_date}:{end_date}"
            self.results_cache[cache_key] = result
            return result

        except Exception as exc:
            logger.error(f"Backtesting failed for {pair} on {exchange_id}: {exc}")
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _replay_candles(
        self, df, initial_capital: float, risk_mode: str
    ) -> List[dict]:
        """Walk through candles and apply indicator signals deterministically."""
        trades: List[dict] = []
        capital = initial_capital
        stop_pct = _RISK_STOP_LOSS.get(risk_mode, 0.010)
        take_pct = _RISK_TAKE_PROFIT.get(risk_mode, 0.015)

        in_position = False
        entry_price: float = 0.0
        entry_ts: Optional[str] = None
        position_side = "buy"

        for _, row in df.iterrows():
            close = float(row.get("close", 0))
            if close <= 0:
                continue

            if not in_position:
                direction, confidence, _ = _rule_based_prediction(row)
                if direction == "up" and confidence >= 0.6:
                    in_position = True
                    entry_price = close
                    entry_ts = str(row.get("timestamp", ""))
                    position_side = "buy"
            else:
                # Check stop-loss / take-profit
                change = (close - entry_price) / entry_price
                if change <= -stop_pct or change >= take_pct:
                    gross_pnl = capital * change * 0.10  # 10% position size
                    fee = abs(capital * 0.10) * 0.001 * 2  # 0.1% round-trip
                    net_pnl = gross_pnl - fee
                    capital = max(0.0, capital + net_pnl)
                    trades.append({
                        "entry_date": entry_ts,
                        "exit_date": str(row.get("timestamp", "")),
                        "side": position_side,
                        "entry_price": round(entry_price, 6),
                        "exit_price": round(close, 6),
                        "pnl": round(net_pnl, 4),
                        "capital_after": round(capital, 4),
                        "exit_reason": "take_profit" if change >= take_pct else "stop_loss",
                    })
                    in_position = False

        return trades

    def _calculate_metrics(self, trades: list, initial_capital: float) -> dict:
        """Calculate performance metrics from a list of replay trades."""
        if not trades:
            return {"total_trades": 0, "note": "no_trades_in_period"}

        final_capital = trades[-1]["capital_after"]
        total_return = ((final_capital - initial_capital) / initial_capital) * 100

        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] < 0]
        win_rate = (len(winning) / len(trades)) * 100 if trades else 0

        total_profit = sum(t["pnl"] for t in winning)
        total_loss = abs(sum(t["pnl"] for t in losing))
        profit_factor = total_profit / total_loss if total_loss > 0 else total_profit

        # Max drawdown
        peak = initial_capital
        max_drawdown = 0.0
        for t in trades:
            c = t["capital_after"]
            if c > peak:
                peak = c
            dd = ((peak - c) / peak) * 100
            if dd > max_drawdown:
                max_drawdown = dd

        # Simplified Sharpe ratio (annualised, daily returns proxy)
        returns = [t["pnl"] / initial_capital for t in trades]
        avg_r = sum(returns) / len(returns)
        variance = sum((r - avg_r) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        sharpe = (avg_r / std_dev) * math.sqrt(252) if std_dev > 0 else 0

        return {
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(win_rate, 2),
            "total_return": round(total_return, 2),
            "final_capital": round(final_capital, 4),
            "profit_factor": round(profit_factor, 4),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 4),
            "avg_trade_pnl": round(sum(t["pnl"] for t in trades) / len(trades), 4),
        }

    async def optimize_strategy(
        self, base_params: dict, start_date: str, end_date: str
    ) -> dict:
        """Run backtest across all risk modes and return the best performing one."""
        best_result: Optional[dict] = None
        best_return = float("-inf")

        for risk_mode in ("safe", "balanced", "risky", "aggressive"):
            params = {**base_params, "risk_mode": risk_mode}
            result = await self.backtest_strategy(params, start_date, end_date)
            if "metrics" in result:
                total_return = result["metrics"].get("total_return", float("-inf"))
                if total_return > best_return:
                    best_return = total_return
                    best_result = result

        return best_result or {"error": "all_risk_modes_failed"}


# Global instance
backtesting_engine = BacktestingEngine()
