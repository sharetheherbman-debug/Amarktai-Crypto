# Paper Trading

## Overview

Paper (simulated) bots trade immediately upon creation — there is **no training gate**.
Paper mode is designed to be a realistic simulation of live trading from the very first tick.

## No Training Gate

Paper bots are **never** held in a `training` state or blocked from trading because of
a "needs N closed trades" requirement.  That gating applies only to live bots that must
demonstrate stability before risking real capital.

| Bot type | `training_complete` on creation | Trades freely? |
|----------|---------------------------------|----------------|
| Paper    | `true`                          | ✅ immediately  |
| Live     | `false` (set after N trades)    | ❌ until graduated |

### What changed (2026-02)

Previously, paper bots could appear in `state=training` due to `training_complete=False`
in the database.  The following fixes were applied:

1. **`routes/bot_lifecycle.py` — `get_bots_status`**  
   Paper bots (`trading_mode == 'paper'`) are excluded from the training-state logic.
   A paper bot with `status=active` always reports `state=active`.

2. **`routes/bot_lifecycle.py` — `_check_bot_blockers`**  
   The training block is skipped for paper bots, so start/resume actions are never
   rejected because of missing training.

3. **`routes/bot_lifecycle.py` — `seed_luno_paper_bots`**  
   New paper bots are seeded with `training_complete=true` and
   `training_in_progress=false`.

4. **`backend/paper_trading_engine.py` — `_close_open_trade`**  
   The `is_training` flag and `TRAINING_MAX_HOLD_MINUTES` / `training_timeout`
   close-reason have been removed.  All paper bot trades exit only via the standard
   rules:  `take_profit`, `stop_loss`, `time_exit`, `safety_exit`, or `stale_exit`.

5. **`backend/paper_trading_engine.py` — `run_trading_cycle`**  
   Training graduation checks are skipped for paper bots (`trading_mode == 'paper'`).
   Live bots that use `is_training=True` still graduate automatically once
   `closed_trades_count >= TRAINING_TRADES_REQUIRED`.

## Exit Rules for Paper Bots

| Exit type     | Trigger                                      |
|---------------|----------------------------------------------|
| `take_profit` | Price ≥ take-profit price                    |
| `stop_loss`   | Price ≤ stop-loss price                      |
| `time_exit`   | Age ≥ `PAPER_MAX_HOLD_MINUTES` (default 120) |
| `safety_exit` | Age ≥ `PAPER_SAFETY_EXIT_MINUTES` AND P&L > 0 |
| `stale_exit`  | Age ≥ `PAPER_STALE_EXIT_MINUTES` AND P&L ≤ 0 |

## Close Lifecycle

Every paper bot trade follows this lifecycle:

1. **BUY** — `run_trading_cycle` is called by the scheduler.  A new trade doc is inserted
   with `status: "open"`.
2. **EVAL** — On the next scheduler tick the engine finds the open trade and calls
   `_close_open_trade`.  It logs `PAPER_TICK` and `PAPER_EVAL` to journal.
3. **CLOSE** — When an exit condition is met, the trade doc is updated to
   `status: "closed"`, all realised PnL fields are written, the ledger is updated,
   and bot stats (`closed_trades_count`, `win_count`, `loss_count`) are incremented.

### Structured log lines to grep on VPS

```
# One line per scheduler cycle per bot (shows open trade count)
journalctl -u amarktai-backend -g "PAPER_TICK"

# Per-trade evaluation (price vs TP/SL, age, time-to-exit)
journalctl -u amarktai-backend -g "PAPER_EVAL"

# Successful close events
journalctl -u amarktai-backend -g "CLOSE_TP_HIT\|CLOSE_SL_HIT\|CLOSE_TIME_EXIT\|CLOSE_SAFETY_EXIT"
```

## Diagnostics Endpoint

`GET /api/diagnostics/paper` (alias of `/api/diagnostics/paper-engine`) returns a
real-time snapshot of engine state for every open trade.

```json
{
  "success": true,
  "engine_running": true,
  "last_tick_at": "2026-02-27T06:00:00Z",
  "last_close_at": "2026-02-27T05:58:00Z",
  "close_loop_enabled": true,
  "tick_interval_seconds": 30,
  "open_trades_count": 2,
  "open_trades": [
    {
      "id": "trade_abc",
      "bot_id": "bot_xyz",
      "age_minutes": 45.2,
      "next_exit": "time_exit_in_74.8min"
    }
  ],
  "last_20_actions": [...],
  "timestamp": "2026-02-27T06:00:05Z"
}
```

### How to verify on VPS

```bash
# 1. Check /api/diagnostics/paper returns 200 with open trades
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"YOUR_PASS"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/diagnostics/paper | python -m json.tool

# 2. Check OpenAPI JSON is valid and includes /api/diagnostics/paper
curl -s http://127.0.0.1:8000/openapi.json | python -m json.tool | grep -A2 "diagnostics/paper"

# 3. Confirm close loop fires (watch for CLOSE_ lines in journal)
journalctl -u amarktai-backend -f | grep -E "PAPER_TICK|PAPER_EVAL|CLOSE_"
```

## Telemetry

Even though paper bots are never gated, the engine still increments
`closed_trades_count`, `win_count`, and `loss_count` after every completed trade.
This data is used for analytics, performance ranking, and cloning decisions.
