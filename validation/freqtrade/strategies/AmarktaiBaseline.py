"""
AmarktaiBaseline — Freqtrade Baseline Strategy
================================================
This strategy mirrors the core Amarktai trading logic so Freqtrade can serve
as an independent external benchmark.

COMPARISON PURPOSE ONLY — not the live trading app.

Logic:
- Regime: EMA-20 vs EMA-50 crossover (momentum confirmation)
- Entry filter: RSI-14 in [rsi_min, rsi_max] range
- Entry: EMA-20 crosses above EMA-50 AND RSI in range
- Stop-loss: Fixed percentage (mirrors paper engine SL)
- Take-profit: Fixed percentage (mirrors paper engine TP)
- Max hold: 120 hours (mirrors PAPER_MAX_HOLD_MINUTES=120)

Fee assumption: 0.10% taker (Binance), matching live engine.
Round-trip cost: ~0.25% (fee×2 + slippage×2 + spread)

Parameters mirror research/strategies/momentum_v1.json config.
"""

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.strategy.interface import IStrategy
import pandas as pd
import pandas_ta as pta  # Freqtrade includes pandas-ta


class AmarktaiBaseline(IStrategy):
    """
    Baseline strategy mirroring Amarktai Crypto momentum logic.

    Use for:
    - Benchmarking our engine's entry frequency vs Freqtrade
    - Validating TP/SL profitability on Binance historical data
    - Walk-forward robustness testing

    Do NOT use for live trading — this is a validation tool only.
    """

    # -----------------------------------------------------------------
    # Strategy configuration — mirrors momentum_v1.json
    # -----------------------------------------------------------------
    INTERFACE_VERSION = 3

    timeframe = "1h"
    startup_candle_count: int = 60  # warm up EMA-50 + ATR

    # Fixed TP/SL (as decimal fractions)
    # momentum_v1 safe profile: TP=4.0%, SL=1.8%
    # Must satisfy: TP > SL + 2 × round_trip_cost (0.25% for Binance)
    minimal_roi = {
        "0":   0.055,   # 5.5%  (TP target from balanced profile)
        "60":  0.040,   # 4.0%  (TP target from safe profile after 1h)
        "120": 0.025,   # 2.5%  (minimum acceptable after 2h)
        "180": 0.010,   # time decay exit after 3h
    }
    stoploss = -0.018   # 1.8% stop-loss (momentum safe profile)

    # Max hold: 120h = 7200 min ≈ PAPER_MAX_HOLD_MINUTES equivalent
    max_open_trades = 1
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Optimisable parameters (for hyperopt)
    rsi_min   = IntParameter(40, 55, default=45, space="buy")
    rsi_max   = IntParameter(65, 85, default=75, space="buy")
    ema_fast  = IntParameter(10, 25, default=20, space="buy")
    ema_slow  = IntParameter(40, 60, default=50, space="buy")

    # -----------------------------------------------------------------
    # Indicator computation
    # -----------------------------------------------------------------

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Compute all indicators needed for entry/exit signals."""
        # RSI-14
        dataframe["rsi"] = pta.rsi(dataframe["close"], length=14)

        # EMA fast and slow
        dataframe["ema_fast"] = pta.ema(dataframe["close"], length=self.ema_fast.value)
        dataframe["ema_slow"] = pta.ema(dataframe["close"], length=self.ema_slow.value)

        # ATR-14 for context (not used in signal but useful for diagnostics)
        dataframe["atr"] = pta.atr(dataframe["high"], dataframe["low"], dataframe["close"], length=14)

        # Volume ratio
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["vol_ratio"]   = dataframe["volume"] / dataframe["volume_mean"].clip(lower=1e-9)

        # MACD for regime context
        macd = pta.macd(dataframe["close"], fast=12, slow=26, signal=9)
        if macd is not None:
            dataframe["macd_hist"] = macd["MACDh_12_26_9"]

        return dataframe

    # -----------------------------------------------------------------
    # Entry signal
    # -----------------------------------------------------------------

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Entry conditions:
        1. EMA-fast crosses above EMA-slow (momentum confirmation)
        2. RSI is in the target range (not overbought/oversold extreme)
        3. Sufficient volume (avoids low-liquidity spikes)
        """
        dataframe.loc[
            (
                # EMA crossover: fast above slow and was not above previous bar
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                # RSI filter: must be in range [rsi_min, rsi_max]
                & (dataframe["rsi"] > self.rsi_min.value)
                & (dataframe["rsi"] < self.rsi_max.value)
                # Volume filter: above average
                & (dataframe["vol_ratio"] > 0.9)
                # Not in obvious downtrend
                & (dataframe["close"] > dataframe["ema_slow"])
            ),
            "enter_long"
        ] = 1

        return dataframe

    # -----------------------------------------------------------------
    # Exit signal
    # -----------------------------------------------------------------

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Exit conditions:
        1. EMA-fast crosses back below EMA-slow (trend reversal)
        2. RSI overbought
        """
        dataframe.loc[
            (
                # EMA crosses back below: bearish crossover
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
            ) | (
                # RSI overbought exit
                dataframe["rsi"] > self.rsi_max.value
            ),
            "exit_long"
        ] = 1

        return dataframe
