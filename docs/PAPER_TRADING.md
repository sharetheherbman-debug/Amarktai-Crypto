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

## Telemetry

Even though paper bots are never gated, the engine still increments
`closed_trades_count`, `win_count`, and `loss_count` after every completed trade.
This data is used for analytics, performance ranking, and cloning decisions.
