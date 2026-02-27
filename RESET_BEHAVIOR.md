# Paper Reset Truth — Amarktai Network

## Overview

All paper reset surfaces now delegate to a single authoritative service:
`backend/services/paper_reset_orchestrator.py`

This document describes exactly what each reset does, the required confirmation
phrases/tokens, and the guaranteed post-reset state.

---

## Reset Surfaces

### 1. Admin Start-Fresh — `POST /api/admin/start-fresh`

| Field | Value |
|---|---|
| **Auth required** | `require_admin` (admin JWT) |
| **Confirmation phrase** | `"START FRESH"` (exact, case-sensitive) |
| **Scope options** | `"paper_only"` (default) · `"paper_and_bots"` |
| **Body** | `{"confirmation_phrase": "START FRESH", "scope": "paper_only", "also_reset_risk_locks": true}` |

**What it resets (paper_only scope):**
- Paper bots → soft-deleted (`status: "deleted"`)
- Surviving paper bots → equity_peak, daily_capital_baseline reset to current_capital
- Trades, orders, fills_ledger, ledger_events (paper-tagged)
- equity_series, drawdown_series, profit_ledger, circuit_breaker_state
- Bot runtime state, lifecycle, metrics, balance snapshots, performance metrics
- Wallet balances, capital injections, user countdowns
- Paper wallet → reset to 0
- Risk locks (daily_loss_lock_active, emergency_stop) → cleared
- Training jobs → deleted (admin only)

---

### 2. User Paper Start-Fresh — `POST /api/user/paper-start-fresh`

| Field | Value |
|---|---|
| **Auth required** | `get_current_user` (any logged-in user) |
| **Confirmation phrase** | `"START FRESH"` (exact, case-sensitive) |
| **Scope** | Always `"paper_only"` — cannot wipe live bots |
| **Body** | `{"confirmation_phrase": "START FRESH"}` |

Identical to admin start-fresh with `paper_only` scope, but:
- No training job deletion
- User can only reset their own data

---

### 3. Paper Sandbox Reset — `POST /api/system/paper-sandbox/reset`

| Field | Value |
|---|---|
| **Auth required** | `get_current_user` |
| **Confirmation phrase** | `"RESET PAPER SANDBOX"` |
| **Scope** | Always `"paper_only"` |
| **Body** | `{"confirmed": true, "confirmation_phrase": "RESET PAPER SANDBOX"}` |

Delegates to the same orchestrator as the other reset surfaces.
Also clears in-memory ccxt paper balances.

---

### 4. AI Chat Paper Session Reset

Triggered when the AI chat detects reset intent (`reset paper session`, etc.).
Calls the same orchestrator with `"paper_only"` scope.
No additional confirmation phrase required (user intent is inferred).

---

## What Resets in Every Case

Regardless of which surface triggered the reset, the orchestrator guarantees:

### Per-Bot Fields Reset (surviving bots)
| Field | New Value |
|---|---|
| `equity_peak` | `current_capital` (drawdown → 0%) |
| `current_drawdown_pct` | `0.0` |
| `daily_capital_baseline` | `current_capital` |
| `daily_baseline_date` | Today (UTC, `YYYY-MM-DD`) |
| `daily_pnl` | `0.0` |
| `daily_loss_pct` | `0.0` |
| `trades_today` | `0` |
| `paused_by_bodyguard` | `false` |
| `paused_by_system` | `false` |
| `pause_reason` | `$unset` |
| `paused_reason` | `$unset` |
| `last_order_error` | `$unset` |
| `last_order_attempt_at` | `$unset` |
| `circuit_breaker_tripped` | `$unset` |

### Per-User Risk Locks Reset
| Field | New Value |
|---|---|
| `daily_loss_lock_active` | `false` |
| `emergency_stop` | `false` |
| `daily_loss_locked_at` | `$unset` |
| `daily_loss_locked_reason` | `$unset` |
| `daily_loss_pct` | `$unset` |
| `daily_loss_day_key` | `$unset` |

### Collections Deleted (user-scoped)
- `fills_ledger` (where `is_paper: true` for user)
- `fills_ledger` (where `bot_id` in deleted bots)
- `ledger_events` (paper-tagged: `event_type: "paper_capital_bootstrap"` or `metadata.mode: "paper"`)
- `equity_series`
- `drawdown_series`
- `profit_ledger`
- `circuit_breaker_state`
- `balance_snapshots`
- `paper_ledger`
- `bot_metrics`
- `bot_runtime_state`
- `bot_lifecycle`
- `performance_metrics`
- `wallet_balances`
- `capital_injections`
- `user_countdowns`

### Post-Reset Invariants Checked
- `ledger_equity == 0` after reset
- `active_bots == 0` (paper bots deleted)
- `open_positions == 0`

---

## Return Object

All reset endpoints return a result object with:
```json
{
  "bots_soft_deleted": 5,
  "bots_performance_reset": 0,
  "trades_deleted": 20,
  "orders_deleted": 15,
  "fills_deleted": 30,
  "telemetry_deleted": 5,
  "risk_locks_reset": 1,
  "wallet_before": {},
  "wallet_after": {},
  "post_reset": {
    "active_bots": 0,
    "open_positions": 0,
    "ledger_equity": 0.0,
    "ledger_fills": 0
  },
  "warnings": []
}
```

---

## Why Drawdown Was 50% Before Reset

The `drawdown_pct` shown in `/api/risk/status` was calculated as:
```
drawdown = (equity_peak - current_capital) / equity_peak × 100
```

If `equity_peak = 1000` (old high-water mark) and `current_capital = 500`,
then `drawdown = 50%`.

After any reset, the orchestrator sets `equity_peak = current_capital` for all
surviving bots, making drawdown = 0% immediately.

## Why Circuit Breaker Tripped

The circuit breaker computes daily loss as:
```
daily_pnl_pct = (current_capital - daily_capital_baseline) / daily_capital_baseline
```

If `daily_capital_baseline` was set to 1000 (yesterday's value) and
`current_capital` is 500 today, then `daily_pnl_pct = -50%`, which exceeds
the default 10% daily loss limit.

After reset, `daily_capital_baseline` is set to `current_capital` and
`daily_baseline_date` is set to today, so the next tick computes 0% daily loss.

---

## Diagnostics

Use `/api/bots/{bot_id}/diagnostics` (or alias `/api/diagnostics/bot/{bot_id}`)
to see:
- `performance.equity_peak` — current high-water mark
- `performance.computed_drawdown_pct` — drawdown from peak
- `performance.daily_capital_baseline` — today's baseline
- `circuit_breaker.would_trip_daily_loss` — whether CB would fire
- `circuit_breaker.next_action` — what to do to recover
