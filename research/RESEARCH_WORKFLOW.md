# Strategy Research & Validation Workflow

## Purpose

This document describes the **A → B → C promotion workflow** for strategy parameter changes in Amarktai Crypto.

**RULE:** No strategy change reaches the live paper engine without passing all three stages.

---

## Stage A — Research (VectorBT)

**Tool:** `research/vectorbt_runner.py`

Run a parameter sweep on historical OHLCV data to find parameter sets with positive expected value.

### Prerequisites

```bash
pip install vectorbt ccxt pandas numpy
```

### Run a sweep

```bash
# Sweep BTC/USDT momentum strategy on Binance (90 days, 1h bars)
python research/vectorbt_runner.py \
    --pair BTC/USDT \
    --exchange binance \
    --strategy momentum \
    --timeframe 1h \
    --days 90 \
    --top 10 \
    --output research/results/momentum_btc_usdt.json

# Sweep all Luno ZAR pairs for mean_reversion
python research/vectorbt_runner.py \
    --exchange luno \
    --strategy mean_reversion \
    --all-pairs

# Compare normal vs scalper on Binance
python research/vectorbt_runner.py \
    --pair ETH/USDT \
    --exchange binance \
    --compare-modes
```

### Acceptance criteria (Stage A → B)

A parameter set passes Stage A when:
- `expectancy_pct > 0` (positive expected value after fees)
- `win_rate_pct >= 45%`
- `total_trades >= 30` (enough statistical sample)
- `max_drawdown_pct <= 20%`
- `sharpe >= 0.5`

Register the winner:

```bash
python research/strategy_registry.py promote momentum v1 experimental validated
```

---

## Stage B — Validation (Freqtrade)

**Tool:** `validation/freqtrade/`

Runs the same logic as an independent external benchmark using Freqtrade's dry-run or backtesting.

```bash
cd validation/freqtrade
bash setup.sh                    # install freqtrade in venv
freqtrade backtesting \
    --config config.json \
    --strategy AmarktaiBaseline \
    --timerange 20240101-20240401
```

### Acceptance criteria (Stage B → C)

A strategy passes Stage B when:
- Freqtrade backtesting shows `profit_factor > 1.2`
- `max_drawdown <= 15%`
- `win_rate >= 45%`
- Our engine's entry frequency is within 20% of Freqtrade's entry count
  (large divergence = one engine is over-filtering or under-filtering)

If our engine is **more conservative** than Freqtrade (fewer trades): audit the spread filter, confidence gate, or edge buffer.  
If our engine is **less conservative** (more trades): audit the expectancy gate and regime filter.

---

## Stage C — Promotion to Live Paper Engine

When a strategy passes both A and B:

```bash
# 1. Promote to active in registry
python research/strategy_registry.py promote momentum v1 validated active

# 2. Verify active.json was updated
python research/strategy_registry.py active momentum

# 3. Update the corresponding JSON in research/strategies/ if parameters changed
# 4. Update backend/engines/regime_playbooks.py _PLAYBOOK_PARAMS if TP/SL changed
# 5. Update backend/config/__init__.py thresholds if filters changed
# 6. Commit with message: "strategy: promote <name>/<version> to active"
# 7. Deploy and monitor for 24h before any further changes
```

---

## Strategy Registry Commands

```bash
# List all registered strategies
python research/strategy_registry.py list

# Show config for a specific version
python research/strategy_registry.py show momentum v1

# Show all currently active configs
python research/strategy_registry.py active

# Promote a strategy forward
python research/strategy_registry.py promote scalper v2 experimental validated
python research/strategy_registry.py promote scalper v2 validated active
```

---

## Current Strategy Status

| Name | Version | Stage | Notes |
|------|---------|-------|-------|
| momentum | v1 | experimental | Initial EMA-cross + RSI config |
| mean_reversion | v1 | experimental | RSI fade extremes config |
| scalper | v1 | experimental | MACD histogram + volume filter |

---

## Exchange-Specific Notes

### Luno (ZAR pairs)
- Round-trip cost: **0.64%** (0.25% × 2 fees + 0.06% spread + 0.08% slippage)
- **Scalpers are NOT viable on Luno** — expected move for scalping is 0.3–0.8%, which doesn't clear 0.64% cost
- Minimum viable TP: `TP > SL + 1.28%` for positive EV at 50% win rate
- Safe TP/SL pairs: TP=3.0%/SL=1.5%, TP=4.0%/SL=1.8%, TP=5.5%/SL=2.5%

### Binance (USDT pairs)
- Round-trip cost: **0.25%** (0.10% × 2 fees + 0.03% slippage × 2 + 0.02% spread)
- Scalpers viable: expected move 0.35–1.5% easily clears 0.25% cost
- `SCALPER_EDGE_BUFFER_PCT = 0.04%` (configured in backend/config/__init__.py)

---

## DO NOT

- Modify `_PLAYBOOK_PARAMS` in `backend/engines/regime_playbooks.py` without running Stage A + B first
- Change `BASE_CONFIDENCE_THRESHOLD` or `SCALPER_CONFIDENCE_THRESHOLD` without a parameter sweep
- Push strategy changes directly to main without the promotion checklist above
- Add `vectorbt` to `backend/requirements.txt` — it is a research-only dependency
