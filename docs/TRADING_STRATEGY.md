# Amarktai Network — Trading Strategy

## Overview

This document describes the **strategy framework** implemented in Phase 2 of the Amarktai Network trading system. It covers the expectancy gate, regime playbooks, exit system, learning guardrails, and how to interpret skip codes and decision traces.

> **Key principle:** The system optimises for **expectancy** (net profit after fees, spread, and slippage) — not win-rate.  A 90 % win-rate with bad risk-reward is still a losing strategy.  Bots only trade when edge is demonstrably present.

---

## 1. Expectancy Gate

Every potential trade is evaluated against a conservative expectancy model **before** any order is placed.

### Formula

```
expected_edge = expected_move_pct * confidence_adjusted
costs         = fees_pct + spread_pct + slippage_pct + safety_buffer_pct
```

A trade is allowed **only if** `expected_edge > costs`.

### Inputs

| Input | Source |
|-------|--------|
| `spread_pct` | Live order-book snapshot (bid/ask) |
| `slippage_pct` | Slippage model based on order size |
| `fee_rate` | Exchange-specific fee table |
| `expected_move_pct` | ML predictor predicted change |
| `confidence` | Combined regime + ML + Fetch.ai confidence |
| `safety_buffer_pct` | Configurable per risk mode (increases in poor liquidity) |

### Adaptive Safety Buffer

The `safety_buffer_pct` is the extra margin required on top of fees+spread+slippage.  In poor liquidity conditions (spread > 60% of `PAPER_MAX_SPREAD_PCT`) the buffer is multiplied by `SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER` (default 2×) to make the gate stricter.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SAFETY_BUFFER_PCT` | `0.10` % | Base safety buffer |
| `SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER` | `2.0` | Multiplier in wide-spread regime |
| `MIN_EXPECTANCY_ZAR` | `0` | Minimum absolute ZAR expectancy per trade |
| `EDGE_BUFFER_PCT` | `0.15` % | Legacy edge buffer (used when no risk-mode config) |

---

## 2. Regime Playbooks

The engine maps the current market regime to one of three **playbooks**:

### Playbook Types

| Playbook | Regimes | Entry Style | TP/SL | Hold Time |
|----------|---------|-------------|-------|-----------|
| `momentum` | stable_uptrend, volatile_uptrend, bullish | Breakouts, pullbacks | Higher TP, trailing stop | Longer |
| `mean_reversion` | consolidation, sideways, stable_downtrend | Fade extremes | Tight TP/SL | Short |
| `stand_down` | choppy, volatile_downtrend, unknown, low-confidence | **No new entries** | — | — |

### Stand-Down Trigger

In addition to regime label, a `stand_down` is also triggered when:
- Regime confidence is below 15 % (too uncertain to trade)
- Volatility spike or wide spread detects a risk event

### Clean Interface

```python
from engines.regime_playbooks import select_playbook, get_playbook_params

playbook_info = select_playbook(regime_dict)
# Returns: {"playbook": "momentum", "regime": "stable_uptrend",
#           "strength": 0.8, "confidence": 0.75}

params = get_playbook_params(risk_mode="safe", playbook="momentum")
# Returns: {"take_profit_pct": 0.020, "stop_loss_pct": 0.012,
#           "max_hold_minutes": 60, "safety_exit_minutes": 35,
#           "position_size_multiplier": 1.0}
```

---

## 3. Exit System

Every open trade has a full exit path assigned at entry.  The `decision_trace.planned_exit` field in the trade record shows:

```json
{
  "take_profit_pct": 0.025,
  "stop_loss_pct": 0.015,
  "time_exit_minutes": 90,
  "safety_exit_minutes": 45,
  "hard_max_hold_seconds": 1500,
  "soft_max_hold_seconds": 900,
  "time_to_forced_exit_seconds": 1500,
  "next_exit_reason": "take_profit_or_stop_loss"
}
```

### Exit Priority (evaluated in order)

1. `take_profit` — price hit TP
2. `stop_loss` — price hit SL
3. `hard_max_hold` — unconditional force-close at `HARD_MAX_HOLD_SECONDS`
4. `soft_max_hold` — close at `SOFT_MAX_HOLD_SECONDS` if spread is acceptable
5. `time_exit` — unconditional close at `PAPER_MAX_HOLD_MINUTES`
6. `safety_exit` — profitable trade closed at `PAPER_SAFETY_EXIT_MINUTES`
7. `stale_exit` — losing trade closed at `PAPER_STALE_EXIT_MINUTES`
8. `stagnation_exit` — price not moved beyond round-trip cost after `STAGNATION_EXIT_MINUTES`

### Per-Risk-Mode Defaults

| Mode | max_hold | safety_exit | position_size |
|------|----------|-------------|---------------|
| safe | 60 min | 30 min | 20 % |
| balanced | 90 min | 45 min | 30 % |
| aggressive | 120 min | 60 min | 45 % |

### Close Urgency

The `no_exit_signal` response includes:
- `next_exit_reason` — the most likely exit trigger based on current state
- `time_to_forced_exit_seconds` — seconds until `hard_max_hold` fires unconditionally

---

## 4. Daily Learning Loop

The system runs a nightly learning pass (01:30 UTC) that analyses the last 7 days of closed trades and proposes small parameter adjustments.

### Bounded Knobs

Only these parameters may be tuned, within strict bounds:

| Parameter | Bound | Direction on Poor Performance | Direction on Good Performance |
|-----------|-------|------------------------------|-------------------------------|
| `trade_size_multiplier` | 0.8 – 1.1 | Decrease | Increase |
| `cooldown_multiplier` | 0.8 – 1.5 | Increase | No change |
| `stop_loss_pct` | 0.01 – 0.05 | Tighten | No change |
| `max_hold_minutes` | 15 – 240 | Decrease | Increase |
| `safety_exit_minutes` | 10 – 120 | Decrease | No change |
| `position_size_multiplier` | 0.5 – 1.5 | Decrease | Increase |

Maximum change per cycle: **5 % relative** per parameter (controlled by `LEARNING_MAX_CHANGE_PCT`).

### Rollback

If `net_pnl < last_run_net_pnl × LEARNING_ROLLBACK_THRESHOLD` (default 0.9), the system rolls back to the last known-good parameter set and records a `rolled_back=true` event.

### Versioning

Every applied change creates a `strategy_params_version` record with:
- `version_id` (UUID)
- `previous_version_id`
- `applied_params`
- `reason` (`nightly_learning_update`)
- `created_by` (`learning_loop`)

---

## 5. Skip Code Reference

| Code | Meaning | Action |
|------|---------|--------|
| `edge_gate` | Expected move < fees + spread + slippage + safety_buffer | No trade |
| `expectancy_gate` | Estimated ZAR expectancy ≤ `MIN_EXPECTANCY_ZAR` | No trade |
| `spread_too_wide` | Spread > `PAPER_MAX_SPREAD_PCT` | No trade |
| `low_liquidity` | Order-book depth < `PAPER_MIN_ORDERBOOK_NOTIONAL` | No trade |
| `portfolio_guard` | Already `PORTFOLIO_GUARD_MAX_SAME_SYMBOL` open on this pair | No trade |
| `drawdown_limit` | Current drawdown ≥ `MAX_DRAWDOWN_PCT` | Stand down |
| `regime_standdown` | Playbook = stand_down (choppy / low-confidence market) | No trade |
| `cooldown` | Rate limiter or bot min-interval in effect | Retry later |
| `budget_exhausted` | Daily trade budget reached | No trade today |
| `no_exit_signal` | No exit condition met for open trade | Hold (check next tick) |

### Diagnostics in Skip Responses

All skip responses include a `details` dict with relevant diagnostics, e.g.:

```json
{
  "skip_reason": "edge_gate",
  "details": {
    "expected_move_pct": 0.05,
    "estimated_cost_pct": 0.32,
    "safety_buffer_pct": 0.20,
    "regime": "consolidation",
    "playbook": "mean_reversion"
  }
}
```

---

## 6. Decision Trace

When a trade is successfully opened, the `decision_trace` field in the response provides full transparency:

```json
{
  "decision_trace": {
    "evaluated_pairs_count": 5,
    "top_candidates": [
      {"symbol": "BTC/USDT", "score": 1.0, "notes": []},
      {"symbol": "ETH/USDT", "score": 0.85, "notes": ["cooldown_penalty(15min)"]}
    ],
    "chosen_pair": "BTC/USDT",
    "expectancy_estimate": 12.50,
    "cost_estimate": 0.32,
    "regime": "stable_uptrend",
    "playbook": "momentum",
    "planned_exit": {
      "take_profit_pct": 0.025,
      "stop_loss_pct": 0.015,
      "time_exit_minutes": 90,
      "safety_exit_minutes": 45,
      "hard_max_hold_seconds": 1500,
      "time_to_forced_exit_seconds": 1500,
      "next_exit_reason": "take_profit_or_stop_loss"
    }
  }
}
```

---

## 7. Anti-Spam / Rate Limiting

- **Per exchange**: Daily order budget (`EXCHANGE_DAILY_TRADE_LIMITS`)
- **Per bot**: Max 50 trades/day (`MAX_TRADES_PER_BOT_PER_DAY`)
- **Burst limit**: 10 orders per 10 seconds per exchange
- **Consecutive loss cooldown**: Enforced via `cooldown_multiplier` in learning params

High-frequency *decision evaluation* is allowed; only *execution* is rate-limited.

---

## 8. Pair Rotation

The symbol universe service (`services/symbol_universe.py`) selects trading pairs with:

1. **Universe filter**: Only pairs in the exchange whitelist are considered
2. **Anti-repeat penalty**: Recently closed pairs get an 85 % score penalty during `SYMBOL_COOLDOWN_MINUTES`
3. **Diversity guard**: Pairs already open for the user get a 95 % score penalty
4. **Top-5 scoring**: Full scored list in diagnostics for transparency

Luno ZAR pairs (BTC/ZAR, ETH/ZAR, XRP/ZAR) are always included in the Luno universe to preserve ZAR-denominated bot functionality.

---

## 9. Metrics Truth

All metrics are derived from **closed trade records** and the **profit ledger**:

- Win-rate = closed trades with `net_profit > 0` / total closed trades
- Expectancy = `(win_rate × avg_win) - (loss_rate × avg_loss) - round_trip_cost`
- Drawdown = peak-to-trough on equity curve from ledger
- Profit factor = gross wins / gross losses

The system **never**:
- Refuses to record losing trades
- Closes only winners while holding losers
- Hides fees or slippage from metrics
- Inflates win-rate through selective recording
