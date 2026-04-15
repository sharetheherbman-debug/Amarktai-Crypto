# Freqtrade Validation Harness

## Purpose

This directory contains an external **Freqtrade** sidecar for validating trading strategies
before they are promoted to the live Amarktai paper engine.

Freqtrade serves as an **independent benchmark** — it doesn't share code with the live app.
If both engines (Amarktai and Freqtrade) agree on entry frequency and profitability,
the strategy is considered validated.

## Strategy: AmarktaiBaseline

`strategies/AmarktaiBaseline.py` mirrors the core Amarktai logic:
- EMA-20/EMA-50 crossover for momentum entries
- RSI-14 filter (45-75 range)
- ATR-based stop-loss
- Fixed TP/SL aligned with `research/strategies/momentum_v1.json`

## Setup

```bash
cd validation/freqtrade
bash setup.sh
```

This installs Freqtrade in a local Python virtual environment. The live app's
dependencies are not affected.

## Running a Backtest

```bash
source freqtrade_venv/bin/activate

# Download Binance USDT data (90 days, 1h)
freqtrade download-data \
    --exchange binance \
    --pairs BTC/USDT ETH/USDT SOL/USDT BNB/USDT \
    --timeframes 1h \
    --timerange 20240101-

# Run backtest
freqtrade backtesting \
    --config config.json \
    --strategy AmarktaiBaseline \
    --timerange 20240101-20240401

# Run dry-run (live market, no real orders)
freqtrade trade \
    --config config.json \
    --strategy AmarktaiBaseline
```

## Comparing Results

After running a backtest, compare these metrics to our engine's paper trading performance:

| Metric | Freqtrade Target | Amarktai Target | Decision |
|--------|-----------------|-----------------|----------|
| Total profit % | > 5% / quarter | > 5% / quarter | Both must pass |
| Win rate | >= 45% | >= 45% | Both must pass |
| Max drawdown | <= 15% | <= 15% | Both must pass |
| Entry count delta | - | Within 20% of Freqtrade | Large delta = audit filters |
| Profit factor | >= 1.2 | >= 1.2 | Both must pass |

If Amarktai enters **fewer** trades than Freqtrade:
- Check `SCALPER_EDGE_BUFFER_PCT` — may be too high
- Check `PAPER_MAX_SPREAD_PCT` — may be filtering real opportunities
- Check `BASE_CONFIDENCE_THRESHOLD` — may be over-blocking

If Amarktai enters **more** trades than Freqtrade:
- Check `MIN_EXPECTANCY_ZAR` — may be too low
- Check regime filter — may not be filtering choppy regimes

## File Structure

```
validation/freqtrade/
├── README.md              (this file)
├── config.json            (Freqtrade exchange + strategy config)
├── setup.sh               (install script)
├── strategies/
│   └── AmarktaiBaseline.py  (comparable baseline strategy)
└── user_data/
    ├── data/              (downloaded OHLCV data)
    ├── backtest_results/  (backtest output)
    └── logs/              (trade logs)
```

## Luno Note

Freqtrade does not natively support Luno ZAR pairs. To validate Luno strategies:
1. Download Luno BTC/ZAR data via the custom CCXT wrapper in `research/vectorbt_runner.py`
2. Import into Freqtrade's data format or compare directly using VectorBT results
3. Manually verify TP/SL clears the 0.64% Luno round-trip cost
