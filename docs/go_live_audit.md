# Go-Live Audit — Phase 0 Baseline Snapshot

**Branch:** `copilot/fix-paper-trading-issues`  
**SHA:** `6865c80b77d96273a105eff9628289a81676889f`  
**Audit date:** 2026-02-24

---

## What is Already Working (Will Not Be Changed)

The following have been confirmed correct and are left untouched:

| Area | Status | Evidence |
|------|--------|----------|
| Authentication (JWT, 2FA) | ✅ Working | `routes/auth.py`, `routes/two_factor_auth.py` |
| Bot CRUD (create/update/delete) | ✅ Working | `routes/bot_lifecycle.py` — standard lifecycle endpoints |
| Paper trading scheduler loop | ✅ Running | `trading_scheduler.py` — logs "Paper tick start" every 10s |
| Paper trading engine execution | ✅ Present | `paper_trading_engine.py` — `run_trading_cycle` writes to `trades_collection` |
| `/api/system/mode` | ✅ Working | Returns `paperTrading`, `autopilot`, `live` flags |
| `/api/system/ping` | ✅ Working | Simple health check |
| `/api/system/gates` | ✅ Working | Returns `safe_to_trade_paper` etc. |
| `/api/wallet/paper` (base) | ✅ Working | Returns balance breakdown |
| `/api/wallet/status` | ✅ Working | Returns wallet hub status |
| `/api/trades/recent` | ✅ Working | Returns trades from `trades_collection` |
| `/api/learning/status` | ✅ Working (patched) | Returns `trades_analyzed` from real closed trades |
| `/api/bots` (list/create/start/stop) | ✅ Working | Standard bot management |
| Risk engine + circuit breakers | ✅ Working | `risk_engine.py` |
| Realtime WS/SSE | ✅ Working | `websocket_manager.py`, `realtime_events.py` |
| Admin panel + whitelist | ✅ Working | `routes/admin_endpoints.py` |
| Email alerts | ✅ Working | `services/email_alerts.py` |
| AI chat | ✅ Working | `routes/ai_chat.py`, `routes/chat_enhanced.py` |
| Backtesting | ✅ Working | `routes/backtesting.py` |
| Build info | ✅ Working | `routes/build_info.py` — reads `BUILD_SHA`/`BUILD_BRANCH` env or `git` |

---

## Known Issues (User-Reported)

### 1. `/api/trades/recent` always empty
**Root cause (identified):** The paper trading engine (`run_trading_cycle`) correctly writes trades to `trades_collection`, but the scheduler's `execute_bot_trades` only calls `paper_engine.run_trading_cycle` for bots in `PAPER_SUPPORTED_EXCHANGES`. If no bots exist or wallet has 0 balance, no trades are written. The collection is empty because:
- No bots are active, OR
- Wallet balance is 0 (funds not added via dashboard), OR
- Bots are on unsupported exchanges for paper mode.

**Fix:** Diagnostics endpoints (`/api/diagnostics/why-not-trading`, `/api/diagnostics/last-tick`) now surface the exact reason so users can resolve via dashboard.

### 2. `/api/learning/status` shows `trades_analyzed=0`, `last_run_at=null`
**Root cause:** Learning loop only runs at 01:30 UTC (configurable). Before any closed trades exist, `trades_analyzed` was counting only if the loop had run. The field was never populated from DB.

**Fix (already applied in PR):** `/api/learning/status` now queries `trades_collection` directly to count closed trades, making `trades_analyzed` immediately truthful.

### 3. Wallet hub shows `FUNDED/not configured` inconsistently
**Root cause:** `funded_status` was not a computed field — it depended on cached state that could go stale.

**Fix (already applied in PR):** `funded_status` is now computed on every request: `total == 0 → UNFUNDED`, `total > 0 → FUNDED`.

### 4. Reset endpoint missing or incomplete
**Root cause:** No canonical per-user reset endpoint existed for paper sandbox.

**Fix (already applied in PR):** `POST /api/system/paper-sandbox/reset` (requires `confirmed=true` + `confirmation_phrase="RESET PAPER SANDBOX"`) clears all paper artifacts with per-collection delete counts.

### 5. AI tools return generic placeholders
**Status:** AI chat is wired to real state via `ai_command_router.py` and `ai_command_router_enhanced.py`. The tools call real services. If responses appear generic, it is because the underlying data (trades, bots, wallet) is empty — not a code bug.

**No code change required.** The AI truthfully reflects missing data.

### 6. CoinStats: DNS failure but UI says "add key"
**Root cause:** CoinStats base URL was hardcoded and the key-status check returned "not configured" even if DNS failed.

**Fix (already applied in PR):**
- `FLOKX_BASE_URL` env var (default: `https://api.coinstats.io/v1`)
- `GET /api/coinstats/status` probes DNS + HTTP, returns `service_unreachable` with URL when DNS fails

### 7. Reset doesn't reset graphs and countdown completely
**Fix (already applied in PR):** `POST /api/system/paper-sandbox/reset` clears: bots, bot_runtime_state, bot_lifecycle, trades, orders, ledger, paper_ledger, bot_events, fills, equity_series, drawdown_series, user_countdowns, wallet_balances.

### 8. `seed-paper-luno` endpoint was added (violates no-hardwired-bots rule)
**Fix:** Removed in this audit. The dashboard remains the only way to create bots.

---

## Phase 1 — Diagnostics Endpoints Added

All three are read-only with no side effects:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/diagnostics/why-not-trading` | Ranked reasons why bots may not be trading (mode flags, scheduler, wallet, risk locks, quarantine, exchange support) |
| `GET /api/diagnostics/last-tick` | Summary of last scheduler tick: scheduler running, tick count, last_tick_at, trades opened/closed/failed in last 5 min, reject reasons |
| `GET /api/diagnostics/decision-trace?bot_id=...` | Read-only trace of last bot decisions from `bot_runtime_state` + recent trades |

These are appended to the existing `backend/routes/diagnostics.py` (prefix `/api/diagnostics`).

---

## Phase 2 — Defect Checklist

| # | Area | Status | Change Made |
|---|------|--------|-------------|
| 1 | Trading pipeline end-to-end | ✅ Already correct | Engine writes trades; diagnostics surface why it might not |
| 2 | Wallet/ledger truth model | ✅ Fixed | `funded_status` computed from real balance |
| 3 | Paper sandbox reset | ✅ Fixed | `/api/system/paper-sandbox/reset` implemented |
| 4 | Bot lifecycle/training/quarantine | ✅ Appears correct | `bot_lifecycle.py`, `bot_quarantine.py`, `training_quarantine.py` already handle these |
| 5 | AI tools wired to real data | ✅ Appears correct | AI uses real state; returns truthful "no data" if empty |
| 6 | CoinStats/HF/external integrations | ✅ Fixed | CoinStats URL configurable, health endpoint added |
| 7 | Realtime pipeline | ✅ Appears correct | `rt_events.trade_opened`, `rt_events.trade_executed` called in scheduler |
| 8 | Hard go-live gates | ✅ Appears correct | `live_trading_gate.py`, `system_gate.py` enforce gates |
| 9 | Smoke tests (no hardcoded bots) | ✅ Fixed | Scripts rewritten to validate state and prompt dashboard use |
| 10 | Build metadata | ✅ Appears correct | `build_info.py` reads `BUILD_SHA`/`BUILD_BRANCH` env or git at startup |

---

## Acceptance Criteria Evidence

### Reset clears everything
- `POST /api/system/paper-sandbox/reset` returns `deleted_counts` per collection
- Post-reset invariants: `trades_empty=true`, `bots_empty=true`, `wallet_total=0`
- Endpoint: `backend/routes/system.py` lines 207+

### Wallet funded_status is truthful
- `GET /api/wallet/paper` → `funded_status: "FUNDED"` if `total > 0`, else `"UNFUNDED"`
- Endpoint: `backend/routes/wallet_hub.py` lines 195, 351

### CoinStats service unreachable reported correctly
- `GET /api/coinstats/status` → `status: "service_unreachable"` when DNS fails
- `reachability_error` field shows the actual error message
- Endpoint: `backend/server.py` lines 2464+

### Diagnostics show truthful reasons
- `GET /api/diagnostics/why-not-trading` → ranked reasons with severity codes
- `GET /api/diagnostics/last-tick` → scheduler state + trade counts in last 5 min
- `GET /api/diagnostics/decision-trace` → runtime state + recent trades

### No regressions
- All existing endpoints preserved with backward-compatible additions only
- `seed-paper-luno` alias removed (was added in error — dashboard is the only bot creation path)
- Smoke tests rewritten to be non-destructive and dashboard-directed
