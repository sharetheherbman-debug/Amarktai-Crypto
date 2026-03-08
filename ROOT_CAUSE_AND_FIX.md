# Root Cause Analysis & Fix — Paper Trading Truth Model

## Why Trading Was Not Happening

The trading scheduler ticked every 10 seconds but silently produced zero
trades because the **bots collection had 0 active bots**:

| Collection state (live VPS forensic dump) | Count |
|---|---|
| bots total | 38 |
| bots active | 0 |
| bots paused | 1 |
| bots deleted | 37 |
| trades total | 0 |

The scheduler's query `{"status": "active"}` returned an empty result set,
causing it to log `"No active bots found"` at **DEBUG** level (invisible in
production logs) and return immediately every tick.

### Secondary cause: runtime-state drift

The one remaining paused bot (`bb67cf44-...`) had:
- `bots.status = paused` with `pause_reason_code = BODYGUARD_DRAWDOWN_BREACH`
- `bot_runtime_state.state = active`

This disagreement meant no single component could definitively decide
whether the bot should trade.  The scheduler correctly deferred to the
`bots` collection (paused → skip), but the runtime-state row was never
cleaned up after the bodyguard paused the bot.

### Tertiary cause: no canonical reset path

Multiple reset endpoints (`/api/admin/start-fresh`, `/api/bots/reset`,
`/api/paper-reset`) each had **separate, incomplete implementations**.
None of them cleaned `bot_runtime_state`.  A prior partial reset left
37 bots with `status=deleted` but their runtime-state rows intact,
creating phantom "active" rows in the runtime store for deleted bots.

### Quaternary cause: index conflict at startup

`database.init_db()` wrapped all index creation in a **single**
`try/except`.  On the VPS an old `id_1 sparse:true` index conflicted with
the code requesting `id_1 sparse:false`, throwing `IndexKeySpecsConflict`
(code 86).  The single `except` block caught the error, logged it, and
**skipped all remaining indexes** for every collection.  This did not break
the application directly but added noise and risk to startup.

---

## What the Canonical Source of Truth Is Now

### Bot lifecycle state

> **`bots` collection (`bots.status`) is the single source of truth.**

All read paths (scheduler, dashboard, `/api/bots/status`,
`/api/overview/snapshot`) must filter out documents where
`status ∈ {deleted, marked_for_deletion}` or `deleted_at` exists.

`bot_runtime_state` is a **secondary cache** used by the scheduler for
intra-tick state (e.g. paused mid-tick).  It must **never contradict** the
bot document.  `BotRuntimeStateStore.reconcile_with_bot_doc()` is the
authoritative reconciliation method.

### Reset guarantee

All reset flows now call the single `perform_paper_reset(user_id)` function
in `backend/routes/system_mode.py`.  After a successful call:

- Zero runtime-state rows remain for the user
- Every bot document for the user has `status=deleted` + `deleted_at`
- All trades, orders, positions, fills, ledger entries, wallet balances,
  and paper-ledger rows for the user are deleted
- Circuit-breaker and bodyguard state is reset
- `daily_loss_lock_active = False`, `emergency_stop = False`
- Paper wallet is reset to the configured starting capital
- `system_modes.autopilot = False` (safe-by-default)

### Scheduler eligibility

The scheduler now logs at **INFO** level for every tick, including:

```
📊 Scheduler tick — Bots scanned: N active | Final runnable bots: M | ...
Noop reason: <reason>
```

Possible noop reasons:

| Reason | Meaning |
|---|---|
| `no_active_bots` | `bots` collection returned 0 active docs |
| `no_supported_bots` | All bots are on unsupported exchanges or blocked by runtime state |
| `all_bots_paused` | System mode / loss-lock / emergency stop blocked all bots |
| `no_trades_executed` | Bots were runnable but no trade window opened this tick |

---

## What Was Fixed

| File | Change |
|---|---|
| `backend/database.py` | Per-index `_safe_create_index()` helper — handles `IndexKeySpecsConflict` by dropping the stale index and recreating it; each index is now independent so one conflict cannot block others |
| `backend/trading_scheduler.py` | `"No active bots found"` promoted from DEBUG to INFO; structured noop-reason log lines added to every early-exit path |
| `backend/routes/admin_start_fresh.py` | All three reset endpoints (`/api/admin/start-fresh`, `/api/admin/reset-user-data`, `/api/bots/reset`) now delegate to `perform_paper_reset` — one canonical path, nothing skipped |
| `backend/routes/system_mode.py` | `perform_paper_reset` now collects **all** bot IDs (including already-deleted ones) before cleaning linked records so ghost rows from prior partial resets are always removed |
| `backend/services/bot_runtime_state.py` | Added `remove_for_user(user_id)` and `reconcile_with_bot_doc(bot_id, bot_doc)` — resolves state drift deterministically |

---

## VPS Verification Checklist

Run these commands on the VPS after deploying to confirm the fix:

```bash
# 1. Confirm zero ghost bots after reset
mongosh amarktai --eval "
  db.bots.aggregate([
    { \$group: { _id: '\$status', count: { \$sum: 1 } } }
  ]).toArray()
"
# Expected after reset: only { _id: 'deleted', count: N } — NO active/paused rows

# 2. Confirm zero runtime-state rows after reset
mongosh amarktai --eval "db.bot_runtime_state.countDocuments()"
# Expected: 0

# 3. Create a new bot via the API and confirm it becomes active
curl -s -X POST https://<vps>/api/bots \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"VPS-Check","exchange":"luno","pair":"BTC/ZAR","trading_mode":"paper"}' \
  | python3 -m json.tool | grep '"status"'
# Expected: "status": "active"

# 4. Confirm the scheduler sees the new bot within 10 seconds
# Tail the service log:
sudo journalctl -u amarktai-api -f | grep "Bots scanned"
# Expected: "📊 Scheduler tick — Bots scanned: 1 active | ..."

# 5. Confirm at least one paper trade executes (wait ~30–60 s)
mongosh amarktai --eval "db.trades.countDocuments()" 
# Expected: > 0 within 60 seconds of bot creation

# 6. Confirm dashboard counts match Mongo truth
curl -s https://<vps>/api/overview/snapshot \
  -H "Authorization: Bearer <token>" | python3 -m json.tool | grep "activeBots"
# Must equal db.bots.countDocuments({status:"active"})

# 7. Confirm no startup index errors
sudo journalctl -u amarktai-api --since "$(date -d '1 minute ago' '+%Y-%m-%d %H:%M:%S')" \
  | grep -i "IndexKeySpecsConflict\|index conflict"
# Expected: no output (errors are now resolved automatically)
```
