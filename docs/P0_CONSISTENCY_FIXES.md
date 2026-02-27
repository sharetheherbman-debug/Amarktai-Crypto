# P0 Consistency Fixes: Canonical Bot States, Wallet Fields, and Forced Exit Precedence

## Canonical Bot States

### Definition

A bot's canonical state is determined by the following precedence rules:

| DB `status` | `paused_by_user` | `paused_by_system` | Canonical state |
|-------------|------------------|--------------------|-----------------|
| `active`    | `false`          | `false`            | `active`        |
| `active`    | `true`           | any                | `paused_ready`  |
| `active`    | any              | `true`             | `paused`        |
| `paused`    | `true`           | any                | `paused_ready`  |
| `paused`    | any              | any                | `paused`        |
| `stopped`   | any              | any                | `stopped`       |
| `deleted`   | any              | any                | `deleted`       |

**Rule**: A bot cannot be simultaneously `active` and `paused`. The `paused_by_user` and `paused_by_system` flags take precedence over any `runtime_state` override.

### API Behaviour

- `GET /api/bots/status`: Returns `state`/`lifecycle_state`/`display_state` based on the canonical rules above.
- `wallet_summary_service.get_summary()`: Uses `normalize_bot_state()` which respects the canonical rules.
- Active bot count in `/api/wallet/paper`: Reflects only truly active bots (not paused).

### Bot State Fields

| Field | Description |
|-------|-------------|
| `status` | Raw DB status (`active`, `paused`, `stopped`, `deleted`) |
| `state` | Enriched canonical state (may differ from `status` due to paused flags) |
| `lifecycle_state` | Alias for `state` (canonical) |
| `display_state` | Alias for `state` (shown in frontend) |
| `paused_by_user` | `true` if user explicitly paused this bot |
| `paused_by_system` | `true` if system auto-paused this bot |
| `paused_reason_code` | Reason code: `manual_pause`, `system_pause`, `quarantine`, etc. |

---

## Wallet Field Definitions (`GET /api/wallet/paper`)

| Field | Description |
|-------|-------------|
| `available_wallet_zar` | ZAR available for NEW trades (unallocated). **Invariant**: equals `available["ZAR"]`. |
| `available` | Dict `{"ZAR": float}` — unallocated funds in paper wallet service |
| `allocated_funds_zar` | ZAR currently reserved in open bot ledger entries |
| `allocated` | Dict `{"ZAR": float}` — same as `allocated_funds_zar` per currency |
| `initial_funding_zar` | Sum of `initial_capital` across all non-deleted bots (initial deposit amount) |
| `balances` | Dict `{"ZAR": float}` — total (available + allocated) |
| `total` | Float — total paper wallet value (available + allocated) |
| `required_funds_zar` | Minimum capital needed to run all active bots |
| `shortfall_zar` | `max(0, required_funds_zar - available_wallet_zar)` |
| `status` | `"FUNDED"` or `"UNDERFUNDED"` |
| `active_bots` | Count of bots with canonical state `active` |

### Key Invariants

1. `available_wallet_zar == available["ZAR"]` (guaranteed by endpoint)
2. `total == available_wallet_zar + allocated_funds_zar` (within rounding)
3. `balances["ZAR"] == total`

---

## Forced Exit Precedence

The paper trading engine evaluates exit conditions in the following priority order:

1. **take_profit** — `current_price >= take_profit_price`
2. **stop_loss** — `current_price <= stop_loss_price`
3. **hard_max_hold** — `age_seconds >= HARD_MAX_HOLD_SECONDS` (default 1500s / 25 min) — **forced, unconditional**
4. **soft_max_hold** — `age_seconds >= SOFT_MAX_HOLD_SECONDS` (default 900s / 15 min) — if spread acceptable
5. **time_exit** — `age_minutes >= PAPER_MAX_HOLD_MINUTES` (default 120 min)
6. **safety_exit** — profitable trade past safety window
7. **stale_exit** — losing trade past stale window
8. **stagnation_exit** — no meaningful price movement
9. **fee_break_even_fail** / **time_decay_exit** — supplementary fee-aware exits

**Rule**: Steps 1–3 fire unconditionally. `no_exit_signal` is only returned if NONE of the above conditions apply. A trade can never be "skipped" with `no_exit_signal` if `hard_exit_triggered` is true.

### Overdue Trade Sweep

The trading scheduler calls `paper_engine.close_overdue_trades(user_id)` at the end of each tick. This sweeps ALL open trades (including those from paused bots) and force-closes any that have exceeded `HARD_MAX_HOLD_SECONDS`, ensuring trades are never stuck open indefinitely.

---

## Diagnostics Endpoints

### `GET /api/diagnostics/wallet-status`

**Scope**: LIVE exchange balance snapshots only. Does NOT include paper wallet balances.  
For paper wallet, use `GET /api/wallet/paper`.

Response includes `"scope": "live_exchanges_only"` field.

### `GET /api/diagnostics/why-not-trading`

**`NO_ACTIVE_BOTS`**: Only fires when there are no bots with `status=active` AND `paused_by_user != true` AND `paused_by_system != true`. Bots that are bulk-paused by user will NOT trigger this error.

**`WALLET_UNFUNDED`**: Only fires when `available_wallet_zar + allocated_funds_zar == 0`. A wallet with all funds allocated to bots (available=0, allocated=5000) is correctly treated as funded.

---

## curl Verification Steps

```bash
# 1. Check bot states are consistent (no active + paused simultaneously)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/bots/status | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
bots = data.get('bots', [])
for b in bots:
    state = b.get('state') or b.get('lifecycle_state')
    paused = b.get('paused_by_user') or b.get('paused_by_system')
    if state == 'active' and paused:
        print(f'BUG: Bot {b[\"id\"]} is active AND paused')
    else:
        print(f'OK: {b[\"name\"]} state={state} paused_by_user={b.get(\"paused_by_user\")}')
"

# 2. Verify wallet/paper invariant: available_wallet_zar == available[ZAR]
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/wallet/paper | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
avail_zar = float((d.get('available') or {}).get('ZAR', 0))
avail_wallet_zar = float(d.get('available_wallet_zar', 0))
if abs(avail_zar - avail_wallet_zar) > 0.01:
    print(f'BUG: available_wallet_zar={avail_wallet_zar} != available[ZAR]={avail_zar}')
else:
    print(f'OK: available_wallet_zar={avail_wallet_zar} == available[ZAR]={avail_zar}')
print(f'     allocated_funds_zar={d.get(\"allocated_funds_zar\")} (ledger-based)')
print(f'     initial_funding_zar={d.get(\"initial_funding_zar\")} (sum of bot capitals)')
"

# 3. Check diagnostics wallet-status scope label
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/diagnostics/wallet-status | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('scope:', d.get('scope'))"

# 4. Check why-not-trading is not falsely critical
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/diagnostics/why-not-trading | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
print('status:', d.get('status'))
for r in d.get('reasons', []):
    print(f'  [{r[\"severity\"]}] {r[\"code\"]}: {r[\"message\"]}')
"
```
