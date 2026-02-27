# Amarktai Strategy Documentation

> **Scope**: Entry / exit logic, symbol selection, learning loop, rate-limit budgeting.
> This document reflects the live codebase.  All parameters are configurable via
> environment variables and stored in the DB (`strategy_params` collection).

> **Design principle**: The system optimises for *expectancy* (net profit per trade
> after fees, spread, and slippage) under strict drawdown limits.  **Win-rate is
> not a target** — a high win rate with tiny wins and large losses is worse than a
> moderate win rate with positive expectancy.  When conditions do not support
> positive expectancy, bots trade less or stand down entirely rather than forcing
> trades to meet an arbitrary win rate goal.

---

## 1. Entry Logic — Expectancy + Edge Model

A trade is opened only when **all three conditions** are met:

1. **Edge gate**: estimated move exceeds total round-trip cost + buffer
2. **Expectancy gate**: estimated ZAR expectancy > `MIN_EXPECTANCY_ZAR` (default 0)
3. **Drawdown gate**: current drawdown < `MAX_DRAWDOWN_PCT` (default 10 %)

### Edge calculation

```
edge_required = fees_pct + spread_pct + slippage_pct + EDGE_BUFFER_PCT
```

### Expectancy calculation

```
expectancy_zar = (expected_move_pct - estimated_cost_pct) / 100 × trade_value_zar
```

This is the **estimated per-trade profit in ZAR**.  If `expectancy_zar ≤ MIN_EXPECTANCY_ZAR`
the trade is skipped with reason `expectancy_gate`.

### Drawdown stand-down

If the user's current equity drawdown (from peak) reaches `MAX_DRAWDOWN_PCT`,
**no new trades are opened** — skip reason `drawdown_limit`.  Closing existing
trades is never blocked.

| Input | Source |
|---|---|
| `fees_pct` | Exchange fee table (per-exchange, tiered) |
| `spread_pct` | Live order-book mid vs ask |
| `slippage_pct` | Estimated from depth notional |
| `EDGE_BUFFER_PCT` | Config default 0.2 %; env `EDGE_BUFFER_PCT` |
| `MIN_EXPECTANCY_ZAR` | Min expectancy (ZAR); default 0 (must be positive) |
| `MAX_DRAWDOWN_PCT` | Max drawdown before stand-down; default 0.10 (10 %) |

Additional entry modifiers (not hard blockers unless toggled):

* **ML prediction**: directional probability from the ML predictor
* **Market regime**: bullish / bearish / neutral via `market_regime_detector`
* **CoinStats sentiment**: used as a _modifier_ (boosts or reduces expected move,
  never single point of failure)

Low confidence → skip **opening** a new trade.  It **never** blocks closing.

---

## 2. Exit Logic — Priority Order

Each trade carries three computed deadlines stored in the trade document:

| Field | Purpose | Default |
|---|---|---|
| `stagnation_deadline` | Close if price hasn't moved beyond round-trip cost | `STAGNATION_EXIT_MINUTES` (10 min) |
| `planned_exit_deadline` | Soft close: spread-permitting | `SOFT_MAX_HOLD_SECONDS` (900 s / 15 min) |
| `hard_exit_deadline` | Force-close unconditionally | `HARD_MAX_HOLD_SECONDS` (1500 s / 25 min) |

### Close priority (evaluated each tick)

```
1. take_profit        — price ≥ TP price
2. stop_loss          — price ≤ SL price
3. hard_max_hold      — age ≥ HARD_MAX_HOLD_SECONDS  → FORCE CLOSE (no exceptions)
4. soft_max_hold      — age ≥ SOFT_MAX_HOLD_SECONDS AND spread OK → close
5. time_exit          — age ≥ PAPER_MAX_HOLD_MINUTES (legacy, default 120 min)
6. safety_exit        — trade is profitable AND age ≥ PAPER_SAFETY_EXIT_MINUTES
7. stagnation_exit    — age ≥ STAGNATION_EXIT_MINUTES AND |pnl_pct| < round_trip_cost
8. stale_exit         — age ≥ PAPER_STALE_EXIT_MINUTES AND pnl ≤ 0
```

> **Important**: Steps 3–8 cannot be blocked by low AI confidence or rate-limit pressure.
> The close loop runs every scheduler tick regardless of confidence gates.

---

## 3. Symbol Selection & Diversification

Implemented in `services/symbol_universe.py`.

### Universe per exchange

| Exchange | Default universe |
|---|---|
| Luno | BTC/ZAR, ETH/ZAR, XRP/ZAR |
| Binance/KuCoin/Bybit/Bitget | BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, BNB/USDT, ADA/USDT |
| Kraken | BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, ADA/USDT |

Overridable: set `symbol_universe` field on the bot document.

### Scoring

Each candidate symbol is scored from 0–1; penalties reduce the score:

| Condition | Multiplier |
|---|---|
| Recently closed by this bot (within `SYMBOL_COOLDOWN_MINUTES`) | 0.15 (85% penalty) |
| User already has an open trade on this symbol | 0.05 (95% penalty) |
| Symbol not in exchange universe | filtered out entirely |

**Portfolio guard (C3)**: at most `PORTFOLIO_GUARD_MAX_SAME_SYMBOL` (default 1)
concurrent open trades per symbol per user.

---

## 4. Self-Learning Loop

### Overview

The nightly (or periodic) learning loop in `services/learning_loop.py`:

1. Reads closed trades from the last window
2. Computes win rate, net PnL, profit factor, drawdown
3. Updates the **RL Agent** (policy-gradient) with a reward signal
4. Updates the **Strategy Tuner** (UCB1) per `(exchange, risk_mode)` combination

### UCB1 Strategy Tuner (`services/strategy_tuner.py`)

Tunes six parameters using Upper Confidence Bound 1:

| Parameter | Safe | Balanced | Aggressive |
|---|---|---|---|
| `take_profit_pct` | 0.005–0.05 | 0.008–0.08 | 0.01–0.15 |
| `stop_loss_pct` | 0.005–0.03 | 0.008–0.05 | 0.01–0.08 |
| `min_edge_pct` | 0.001–0.01 | 0.001–0.015 | 0.001–0.02 |
| `time_exit_minutes` | 5–30 | 5–25 | 3–20 |
| `max_spread_allowed` | 0.05–0.50 % | 0.05–0.50 % | 0.05–0.60 % |
| `confidence_threshold` | 0.55–0.85 | 0.50–0.80 | 0.45–0.75 |

#### Update rule

* **Reward = EXPECTANCY** = `(win_rate × avg_win) − (loss_rate × avg_loss) − round_trip_cost`
  in ZAR per trade.  This is computed by `compute_expectancy()` in `strategy_tuner.py`.
  **Win-rate alone is never used as a reward signal** — a parameter set that produces
  high win rate but negative expectancy receives a negative reward.
* Each arm accumulates `pulls` and `total_reward`
* UCB1 score: `mean_reward + C * sqrt(ln(total_pulls) / arm_pulls)` where `C = 1.4`
* After `_MIN_PULLS` (3) data points, the arm value is nudged ±10 % (`_STEP_PERCENT`)
  in the direction of the reward signal
* **Maximum change per cycle**: 10 % of current value
* Changes are bounded by hard min/max per risk mode — no runaway values

#### Persistence

State is stored in `strategy_params` MongoDB collection, keyed by
`(user_id, exchange, risk_mode)`.  Loaded at each learning run to preserve
history across restarts.

#### Diagnostics

`GET /api/diagnostics/strategy-params` returns:
* `current_params` per `(exchange, risk_mode)` combo
* `recent_changes` (last 20 adjustments)
* `rate_limit_budgets` per exchange

---

## 5. Rate-Limit Budgeting

Implemented in `services/rate_limit_budget.py`.

### Per-exchange limits (conservative)

| Exchange | Burst (req/s) | Per-minute |
|---|---|---|
| Luno | 3 | 40 |
| Binance | 15 | 400 |
| KuCoin | 15 | 400 |
| Bybit | 12 | 400 |
| Kraken | 15 | 400 |
| Other | 4 | 60 |

### Backoff algorithm

**Full-jitter exponential backoff** on 429 / 418 / 5xx responses:

```
jitter = random.uniform(min_backoff, min(cap, base * 2^streak))
```

* `base` = 10 s for 429/418, 3 s for 5xx
* `cap` = 120 s
* `streak` = consecutive error count

2xx responses reset the error streak.  Maximum lockout = 120 s — bots are
**never permanently locked**.

### Usage

```python
from services.rate_limit_budget import rate_limit_budget

budget = rate_limit_budget.for_exchange("binance")
ok, wait = budget.acquire(bot_id="my_bot")
if not ok:
    await asyncio.sleep(wait)

# After exchange call:
budget.record_response(status_code=response.status_code)
```

---

## 6. Command Synonyms

The AI command router (`services/ai_command_router_enhanced.py`) maps natural-language
variants to canonical intents via `SYNONYMS` dict + regex patterns:

| Synonyms | Canonical intent |
|---|---|
| start / begin / launch / go / run | `resume` |
| pause / freeze / hold / halt / suspend | `pause` |
| start all bots / begin all bots / run all | `resume_all` |
| pause all / halt all | `pause_all` |

Fuzzy bot-name matching (Levenshtein) is applied when exact name lookup fails.

---

## 7. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `SOFT_MAX_HOLD_SECONDS` | 900 | Soft close window (15 min) |
| `HARD_MAX_HOLD_SECONDS` | 1500 | Hard force-close window (25 min) |
| `STAGNATION_EXIT_MINUTES` | 10 | Stagnation/no-progress exit |
| `SYMBOL_COOLDOWN_MINUTES` | 15 | Anti-repeat cooldown per bot |
| `SYMBOL_COOLDOWN_HISTORY` | 3 | Symbols tracked for cooldown |
| `PORTFOLIO_GUARD_MAX_SAME_SYMBOL` | 1 | Max concurrent opens per symbol per user |
| `PORTFOLIO_GUARD_WINDOW_MINUTES` | 10 | Portfolio guard window |
| `MAX_DRAWDOWN_PCT` | 0.10 | Drawdown fraction triggering stand-down (10 %) |
| `MIN_EXPECTANCY_ZAR` | 0 | Min per-trade expectancy (ZAR) to open a trade |
| `ENABLE_LEARNING_LOOP` | false | Enable nightly UCB1 tuner |
| `LEARNING_MIN_TRADES` | 50 | Min trades before parameter updates |
| `LEARNING_MAX_CHANGE_PCT` | 0.10 | Max fractional change per update |
