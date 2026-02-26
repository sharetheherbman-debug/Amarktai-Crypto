# AutoSpawn — Platform-Scoped Bot Cloning

## Overview

When realized profit on a trading platform reaches `BOT_SPAWN_PROFIT_THRESHOLD_ZAR`
(default **R 1 000**), the Autopilot Engine spawns exactly **one new bot** on that
same platform by cloning the top-performing bot already active there.

**Key rules:**
- Cloning is **platform-scoped** — a Luno bot is cloned only to Luno, never to Binance.
- The cloned bot inherits strategy params, risk profile, and learned weights.
- New bots start `status=active`, `training_complete=true` — no training gate.

## How it works

```
AutopilotEngine.spawn_bot_if_profit_allows(user_id)
  │
  ├─ 1. Compute available profit pool (realized PnL − fees − reserved)
  ├─ 2. Check overall profit threshold (if ENABLE_OVERALL_PROFIT_THRESHOLD)
  ├─ 3. Check bot caps (MAX_TOTAL_BOTS)
  ├─ 4. Find target exchange with available slots
  ├─ 5. Check per-exchange profit ≥ BOT_SPAWN_PROFIT_ZAR
  ├─ 6. Reserve seed capital via ledger
  └─ 7. _clone_top_bot_for_platform(user_id, seed_amount, target_exchange)
          │
          ├─ Query bots WHERE exchange = target_exchange (no cross-platform)
          ├─ Sort by total_profit DESC, win_rate DESC
          ├─ Copy: risk_mode, stop_loss_pct, take_profit_pct, strategy,
          │        learned_weights, learned_insights, trading_mode
          └─ Insert new bot: status=active, training_complete=true
```

## Configuration

| Env var                          | Default | Description |
|----------------------------------|---------|-------------|
| `BOT_SPAWN_PROFIT_ZAR`           | `1000`  | Per-exchange profit needed to spawn |
| `ENABLE_PER_EXCHANGE_BOT_SPAWN`  | varies  | Enable per-exchange profit gate |
| `ENABLE_OVERALL_PROFIT_THRESHOLD`| varies  | Enable global profit gate |
| `OVERALL_PROFIT_THRESHOLD_ZAR`   | varies  | Global profit threshold |
| `MAX_TOTAL_BOTS`                 | varies  | Hard cap on total bots per user |

## Exchange Limits

| Exchange | Max bots |
|----------|----------|
| luno     | 5        |
| binance  | 10       |
| kucoin   | 10       |
| bybit    | 10       |
| kraken   | 10       |
| bitget   | 10       |
| gate     | 10       |

## Cloned Bot Fields

| Field              | Source                         |
|--------------------|--------------------------------|
| `exchange`         | Same as source bot             |
| `trading_mode`     | Same as source bot             |
| `risk_mode`        | Source bot (default: balanced) |
| `stop_loss_pct`    | Source bot (default: 0.02)     |
| `take_profit_pct`  | Source bot (default: 0.03)     |
| `strategy`         | Source bot                     |
| `learned_weights`  | Source bot (if set)            |
| `learned_insights` | Source bot (default: [])       |
| `initial_capital`  | seed_amount (from profit pool) |
| `status`           | `active`                       |
| `training_complete`| `true`                         |
| `cloned_from`      | Source bot ID                  |

## Verification

To verify a spawn cycle manually:

```bash
# Check per-exchange profit
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/analytics/platform-profit"

# Trigger autopilot tick (admin)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/autopilot/tick"

# Confirm new bot appeared on same platform
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/bots/status" | jq '.bots[] | select(.cloned_from != null)'
```
