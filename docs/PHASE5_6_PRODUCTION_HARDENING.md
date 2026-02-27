# Phase 5 & 6 Production Hardening

## Phase 5 Definition — Tick Recorder + Close Loop + Diagnostics Truth

Phase 5 establishes that every tick of the scheduler is **truthfully reflected** in diagnostics endpoints, and that open trades are **always closed** when their exit condition is met.

### Core requirements

| Requirement | Implementation |
|---|---|
| `last_tick_at` updates every scheduler tick | `BotRuntimeStateStore.record_tick()` called per evaluated bot in `TradingScheduler.execute_bot_trades()` |
| `engine_running=true` while scheduler is active | `paper-engine` endpoint uses `scheduler.is_running OR paper_engine.is_running` |
| `closes_attempted > 0` when `time_exit_due` trades exist | `_close_open_trade()` fires for trades past `PAPER_MAX_HOLD_MINUTES` |
| `current_price != null` for open trades in diagnostics | `paper-engine` enriches open trades via `price_fallback_service` |

### Files changed

- `backend/services/bot_runtime_state.py` — `record_tick(bot_id, user_id)` added
- `backend/trading_scheduler.py` — calls `record_tick()` for all evaluated bots
- `backend/routes/diagnostics.py` — `last-tick-summary`, `last-tick`, `paper-engine` endpoints updated

---

## Phase 6 Definition — Consistent Bot-Active Filters + Wallet/Mode Contracts

Phase 6 establishes that the same bot definition ("active bot") is used everywhere, and that service contracts are stable.

### Core requirements

| Requirement | Implementation |
|---|---|
| Canonical mode interface | `SystemModeService.get_mode(user_id) -> str` (not `get_mode()` no-arg) |
| Canonical wallet status interface | `PaperWalletService.get_wallet_status(user_id) -> Dict` |
| `NO_ACTIVE_BOTS` false positive eliminated | `why_not_trading` uses `bot_not_deleted_filter()` instead of raw `deleted_at` query |
| No `MODE_CHECK_ERROR` when mode service is healthy | diagnostics calls `get_mode(user_id)` and compares string, not dict |
| No `WALLET_CHECK_ERROR` when wallet is healthy | diagnostics calls `get_wallet_status(user_id)` which now exists |

### Files changed

- `backend/services/system_mode_service.py` — canonical `get_mode(user_id)`, `get_current_mode` delegates
- `backend/services/paper_wallet_service.py` — `get_wallet_status(user_id)` added
- `backend/routes/diagnostics.py` — `why_not_trading` fixed (A3, D)

---

## Go-Live Paper Validation Runbook

After deploying, run the following `curl` commands to confirm Phase 5/6 acceptance criteria.

> Replace `TOKEN` with your Bearer token and `BASE` with your backend URL.

### 1. Check `why-not-trading` — must have no `MODE_CHECK_ERROR` or `WALLET_CHECK_ERROR`

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/why-not-trading" | python3 -m json.tool
```

**Expected:** `"status": "ok"` or only non-error reason codes. Must NOT contain:
- `"MODE_CHECK_ERROR"`
- `"WALLET_CHECK_ERROR"`

### 2. Check `last-tick-summary` — `last_tick_at` must be recent

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/last-tick-summary" | python3 -m json.tool
```

**Expected:**
- `"scheduler_running": true`
- `"last_tick_at"` within the last 60 seconds
- `"tick_count"` > 0

### 3. Check `paper-engine` — engine running + open trades have current prices

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/paper-engine" | python3 -m json.tool
```

**Expected:**
- `"engine_running": true`
- `"last_tick_at"` non-null
- Open trades (if any) have `"current_price"` != null

### 4. Confirm closes happen when open trades are `time_exit_due`

If you have `time_exit_due` trades, wait one tick interval (~10-30s) and re-check:

```bash
# Before
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/last-tick-summary" | python3 -c "import sys,json; d=json.load(sys.stdin); print('closes_done:', d.get('closes_done'), 'closes_attempted:', d.get('closes_attempted'))"

# After one tick
sleep 30

# After
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/last-tick-summary" | python3 -c "import sys,json; d=json.load(sys.stdin); print('closes_done:', d.get('closes_done'), 'closes_attempted:', d.get('closes_attempted'))"
```

**Expected:** `closes_attempted > 0` and `closes_done >= 0` (done may be 0 if `no_price_data`).

### 5. Open trade count should decrease

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/diagnostics/paper-engine" | python3 -c "import sys,json; d=json.load(sys.stdin); print('open_trades_count:', d.get('open_trades_count'))"
```

---

## Deployment Acceptance Checklist (CI / scripted)

After merge and deploy, the following must pass:

- [ ] `GET /api/diagnostics/why-not-trading` response has no `MODE_CHECK_ERROR` or `WALLET_CHECK_ERROR` in `reasons`
- [ ] `GET /api/diagnostics/last-tick-summary` `last_tick_at` is within last 60 seconds
- [ ] `GET /api/diagnostics/last-tick-summary` `scheduler_running` is `true`
- [ ] `GET /api/diagnostics/paper-engine` `engine_running` is `true`
- [ ] `GET /api/diagnostics/paper-engine` open trades include `current_price` != null (when live prices available)
- [ ] After one tick interval: `closes_attempted` > 0 when trades have `next_exit: "time_exit_due"`
- [ ] `GET /api/wallet/paper` returns shape `{balances, total, available_zar, funded, updated_at}`
