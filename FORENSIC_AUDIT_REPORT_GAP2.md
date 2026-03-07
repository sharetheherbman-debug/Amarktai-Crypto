# FORENSIC GO-LIVE AUDIT — FINAL GAP-FINDING REPORT
## Amarktai Network — Second-Pass "What Have We Still Not Seen?" Audit
**Date:** 2026-03-07  
**Auditor:** Copilot Coding Agent  
**Branch:** copilot/full-forensic-audit  
**Prior Audit:** FORENSIC_AUDIT_REPORT.md (same branch)  
**Scope:** Deep inspection beyond duplicate-system and dead-code analysis — focusing on silent failures, missing capabilities, env var traps, security gaps, and partial implementations

---

## 1. Executive Summary — What Was Still Missing from Previous Audits

The first audit pass was thorough about **visible structural issues** (duplicate files, dead sections, env var naming conflicts). This second pass reveals a different category of problems:

**Six new CRITICAL blockers beyond what the previous audit found:**

1. **`utils/trading_gates.py` reads the wrong env variable names** — `PAPER_TRADING`/`LIVE_TRADING` — while `config.py` reads `ENABLE_PAPER_TRADING`/`ENABLE_LIVE_TRADING`. The gate that enforces paper mode before trades execute will be open in any deployment that follows `backend/.env.example`, which only sets `PAPER_TRADING=1`. Paper trades can execute even with `ENABLE_PAPER_TRADING` not set.

2. **`services/keys_service.py` imports from the "REMOVED" module** `routes/api_key_management.py`, AND its `SUPPORTED_PROVIDERS` list only has 5 of the 7 exchanges — `kraken` and `gate` are missing. Any Kraken or Gate.io key management via `keys_service` will silently fail.

3. **Go-live diagnostics scheduler check always returns `WARN`** — the endpoint tries `from engines.scheduler import trading_scheduler` (the module does not exist) and falls back to `WARN`. The scheduler's true running state (`trading_scheduler.is_running`) is never reported. Go-live health check permanently lies about scheduler state.

4. **`auth:unauthorized` event is dispatched but never listened to** — `apiClient.js` dispatches a custom browser event when a 401 is received, but no component or hook adds an event listener for it. Token expiry will silently continue firing API calls returning 401 in the background. Only the specific call paths that check `err.response?.status === 401` manually redirect to `/login`.

5. **`admin_start_fresh.py` Start Fresh does not reset the paper wallet balance** — `perform_paper_reset()` in `system_mode.py` calls `paper_wallet_service.reset()`, but `start_fresh()` in `admin_start_fresh.py` does not. After an admin "Start Fresh" wipe, the paper wallet still holds the old balance. Bots are deleted but the money they held is not restored to the wallet.

6. **CI env check validates old variable names** (line 306 of `ci.yml`): checks `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED` in the env example — the same wrong names that `trading_gates.py` reads but `config.py` ignores. This means the CI env check passes against the wrong variable names, giving false confidence.

---

## 2. Newly Identified Critical Blockers

### 2.1 Trading Gates Read Wrong Env Variable Names — CRITICAL

**File:** `backend/utils/trading_gates.py` lines 29–30
```python
paper_trading = env_bool('PAPER_TRADING', False)
live_trading = env_bool('LIVE_TRADING', False)
```

**File:** `backend/config.py` lines 49–50
```python
ENABLE_PAPER_TRADING = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
ENABLE_LIVE_TRADING = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'
```

**File:** `backend/services/trading_mode_validator.py` line 91
```python
if not env_bool('PAPER_TRADING', False):
    # blocks paper
```
and line 139:
```python
live_enabled = env_bool('ENABLE_LIVE_TRADING', False) or env_bool('LIVE_TRADING', False)
```

**Issue:** The trading gate that runs BEFORE every paper trade (`enforce_trading_gates()` in `utils/trading_gates.py`) reads `PAPER_TRADING`. The system config (`config.py`) reads `ENABLE_PAPER_TRADING` (default `true`). This means:
- A server that sets `ENABLE_PAPER_TRADING=true` but NOT `PAPER_TRADING=1` will have trading gates that return `False, "No trading mode enabled"` and block ALL paper trades.
- Conversely, a server that sets `PAPER_TRADING=1` but NOT `ENABLE_PAPER_TRADING` will have `config.py` see `ENABLE_PAPER_TRADING=true` (default!) but `trading_gates.py` pass the gate check.
- `trading_mode_validator.py` is inconsistent: live mode checks BOTH variable names but paper mode only checks `PAPER_TRADING`.

**Why missed:** Previous audit identified the env naming conflict at the `.env.example` level. It did not inspect the individual gate files to confirm which exact variable names each reads.  
**Domain:** Paper trading execution  
**Blocker:** YES — paper trades silently blocked OR incorrectly gate-passed depending on which variable is set

---

### 2.2 keys_service.py SUPPORTED_PROVIDERS Missing 2 Exchanges — CRITICAL

**File:** `backend/services/keys_service.py` lines 20–23
```python
SUPPORTED_PROVIDERS = [
    'openai', 'fetchai', 'coinstats', 'huggingface',  # AI providers
    'luno', 'binance', 'kucoin', 'bybit', 'bitget'  # Exchange providers
]
```
`kraken` and `gate` are **absent**.

**Downstream impact:**
- `test_openai_key()` and `get_user_api_key()` in keys_service only validate against 5 exchanges
- The diagnostics endpoint calls `keys_service.get_user_api_key(user_id, 'kraken')` and `keys_service.get_user_api_key(user_id, 'gate')` — these will silently return `None` or fail validation
- The go-live check for `api_keys` will show `gate` and `kraken` as `not_configured` even if keys are saved, because the service doesn't know about them

**File also imports from the REMOVED module:**
```python
from routes.api_key_management import encrypt_api_key, decrypt_api_key, get_decrypted_key
```
`routes/api_key_management.py` file still exists and exports these functions, but the file is marked as removed from router mounting. If it's ever actually deleted, `keys_service.py` will crash on import.

**Why missed:** Previous audit identified `api_key_management.py` as a dead file but did not inspect its callers. The SUPPORTED_PROVIDERS gap was not inspected.  
**Domain:** API key truth, exchange coverage  
**Blocker:** YES — Kraken and Gate.io keys can't be properly managed/validated via keys_service

---

### 2.3 Go-Live Diagnostics Scheduler Check Always Returns WARN — CRITICAL

**File:** `backend/server.py` lines 2863–2870
```python
try:
    from engines.scheduler import trading_scheduler  # DOES NOT EXIST
    scheduler_running = trading_scheduler.running if hasattr(trading_scheduler, 'running') else False
    report["checks"]["scheduler"] = {"status": "PASS" if scheduler_running else "WARN", "running": scheduler_running}
except Exception as e:
    report["checks"]["scheduler"] = {"status": "WARN", "error": str(e)}
```

**Issue:** `engines/scheduler.py` does not exist. The import always raises `ModuleNotFoundError`, so `report["checks"]["scheduler"]` always contains `{"status": "WARN", "error": "No module named 'engines.scheduler'"}`. Even when the trading scheduler IS running (imported at line 51 as `from trading_scheduler import trading_scheduler`), the go-live diagnostic will always report it as `WARN`.

Additionally, even if the import were fixed to `from trading_scheduler import trading_scheduler`, the attribute check fails: `hasattr(trading_scheduler, 'running')` → False because the class uses `is_running`, not `running`. So the status would still be `False`/WARN.

**Why missed:** Previous audit identified the duplicate scheduler import but did not trace through the diagnostic logic that uses `engines.scheduler`.  
**Domain:** Scheduler diagnostic truth, go-live health check  
**Blocker:** YES — go-live check permanently reports scheduler as unhealthy even when running

---

### 2.4 auth:unauthorized Event Dispatched But Never Handled — CRITICAL

**File dispatching:** `frontend/src/lib/apiClient.js` line 84
```js
window.dispatchEvent(new CustomEvent('auth:unauthorized'));
```

**No file listening:** Zero `addEventListener('auth:unauthorized', ...)` calls anywhere in the frontend codebase.

**Effect:** When a JWT expires:
- `apiClient.js` logs an error message and dispatches the event
- But nothing is listening, so NO redirect to `/login` happens
- Background polling intervals (every 30–60 seconds in `useDashboardState.js`) continue firing 401 requests indefinitely
- The dashboard appears frozen/broken but doesn't redirect

Only manual per-call checks (like `if (err.response?.status === 401) navigate('/login')` at line 1158) handle the 401 inline for specific operations. Background polling never does.

**Why missed:** Previous audit examined apiClient.js structure but did not trace the event dispatch to check if it was consumed.  
**Domain:** Frontend auth state  
**Blocker:** YES — session expiry causes silent dashboard lockout without redirect

---

### 2.5 admin_start_fresh Does Not Reset Paper Wallet Balance — CRITICAL

**File:** `backend/routes/admin_start_fresh.py` — `start_fresh()` function

The function:
- ✅ Deletes bot records
- ✅ Deletes trade/order/fill records
- ✅ Resets risk locks
- ✅ Deletes training sessions
- ❌ Does NOT call `paper_wallet_service.reset(user_id)`
- ❌ Does NOT clear `wallet_balances_collection`
- ❌ Does NOT clear `wallets_collection` (where paper wallet balances live)
- ❌ Does NOT clear `paper_ledger_collection`

Compare with `perform_paper_reset()` in `system_mode.py` which does reset all of these.

**Result:** After an admin "Start Fresh":
- All bots are deleted
- All trades are deleted
- But paper wallet shows old balance (possibly negative from bad trades)
- Paper ledger shows allocations for bots that no longer exist
- New bots created will have conflicting ledger state

**Why missed:** Previous audit noted the paper-reset fragmentation but did not read the `start_fresh()` implementation in detail to compare scope.  
**Domain:** Reset truth, wallet truth  
**Blocker:** YES — admin reset creates phantom wallet state

---

### 2.6 CI Env Check Validates Wrong Variable Names — CRITICAL

**File:** `.github/workflows/ci.yml` lines 306–307
```yaml
REQUIRED_VARS="JWT_SECRET MONGO_URL DB_NAME PAPER_TRADING LIVE_TRADING AUTOPILOT_ENABLED"
```

This checks for `PAPER_TRADING`, `LIVE_TRADING`, `AUTOPILOT_ENABLED` — exactly the wrong variable names that `config.py` does not read. The CI check passes and gives false confidence that the env is correct, while the actual runtime reads `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT`.

**Why missed:** Previous audit noted the env naming conflict at the .env.example level but did not check if CI itself perpetuates the wrong names.  
**Domain:** Deployment/configuration truth, CI truth  
**Blocker:** YES — false CI pass masks critical configuration error

---

## 3. Newly Identified High-Risk Gaps

### 3.1 REPO_TRUTH.md Service Name Contradicts Actual Service File — HIGH

**File:** `docs/REPO_TRUTH.md` line 10
```
| **Backend Service** | `systemd: amarktai-backend.service` |
```
**Actual file:** `ops/systemd/amarktai-api.service`  
**Deploy script default:** `BACKEND_SERVICE="${BACKEND_SERVICE:-amarktai-api}"` (ops/deploy.sh)

Running `systemctl status amarktai-backend.service` will report "Unit not found". Running `sudo systemctl restart amarktai-backend` will silently do nothing. Any VPS operations following REPO_TRUTH.md will target the wrong service.

**Domain:** Deployment/operations truth  
**Severity:** HIGH — blocker for any manual VPS service management

---

### 3.2 REPO_TRUTH.md Deployment Path Contradicts ops/deploy.sh Path — HIGH

**REPO_TRUTH.md:** `VPS: /opt/amarktai (backend), /var/www/amarktai (frontend)`  
**ops/systemd/amarktai-api.service:** `WorkingDirectory=/var/amarktai/app/backend`  
**ops/deploy.sh:** `VENV_PATH="${VENV_PATH:-/var/amarktai/venv}"` (uses `/var/amarktai/`)  
**docs/examples/amarktai.service:** `WorkingDirectory=/opt/amarktai` (uses `/opt/amarktai/`)

Three different backend deployment paths across authoritative documents. Any new VPS setup will use a path that conflicts with at least two other documents.

**Domain:** Deployment path truth  
**Severity:** HIGH

---

### 3.3 HuggingFacePanel and CoinStatsPanel Use Different API URL Variable — HIGH

**Files:** `frontend/src/pages/dashboard/sections/HuggingFacePanel.js` line 3 and `CoinStatsPanel.js` line 3
```js
const API = process.env.REACT_APP_API_URL || '';
```

**Frontend `.env.example`:** sets `REACT_APP_API_BASE=http://localhost:8000` (NOT `REACT_APP_API_URL`)

**`lib/api.js`:** reads `process.env.REACT_APP_API_BASE || process.env.REACT_APP_API_URL`

**Issue:** If only `REACT_APP_API_BASE` is set (as per `.env.example`), then `API` in these panels = `''` (empty string), and URLs become `/api/huggingface/status` (relative). That works in production behind nginx. But if `REACT_APP_API_URL` is NOT set and the panels default to `''`, they use `${API}/api/...` which equals `/api/...` — this IS correct for production but breaks in development if you point to a different API server via `REACT_APP_API_BASE`.

Also: `HuggingFacePanel.js` bypasses `apiClient.js` entirely (uses raw `fetch`), meaning its requests bypass the JWT auth interceptor. If the user's session expires, HuggingFace/CoinStats panel API calls don't get the JWT header automatically refreshed or the 401 handler triggered.

**Domain:** Frontend API contract, auth propagation  
**Severity:** HIGH

---

### 3.4 Three Independent Profit/Metrics Services with No Reconciliation — HIGH

**Services:**
1. `services/accounting.py` (`AccountingService`) — claims "single source of truth", computes from `trades_collection`
2. `services/metrics_service.py` (`MetricsService`) — uses `accounting_service.get_unified_metrics()`
3. `services/overview_service.py` (`OverviewService`) — independently computes from `trades_collection`

**Consumers:**
- `routes/dashboard_overview.py` → uses `overview_service`
- `routes/analytics_api.py` → uses `metrics_service` (which wraps `accounting_service`)
- `routes/compatibility_endpoints.py` → uses `metrics_service`
- `server.py` → uses `metrics_service`

**Issue:** `overview_service.get_snapshot()` computes profit directly from the DB rather than delegating to `accounting_service`. The two implementations may produce different results if their query logic diverges. The dashboard Overview tile uses `overview_service` while the Analytics/Profits page uses `metrics_service` which wraps `accounting_service`. Profit shown on the Overview tile can differ from profit shown in the Analytics section.

**Domain:** Profit truth, dashboard consistency  
**Severity:** HIGH

---

### 3.5 FLock.io AI Client Still Present Despite FLOKx Removal — HIGH

**File:** `backend/engines/flock_ai_client.py`

The file comment says "FLock.io API Integration" with model `flock-trading-specialist-v1`. The FLOKx regression test in `tests/test_flokx_removal.py` checks for brand-name "FLOKx" but NOT for "flock" or "FLock.io". The client is in `engines/` and may be imported by components that use AI services.

**Issue:** "FLOKx" the brand is removed, but `flock_ai_client.py` (the FLock.io API wrapper, unrelated to the FLOKx brand) is still present. The regression test does not check for this file, so it wouldn't catch a re-integration. However, if flock_ai_client.py IS imported somewhere in the active AI pipeline, it makes external calls to flock.io API, which:
- Requires a separate API key not in any env example
- Is not listed in the 11-provider registry
- Is not in the keys management UI

**Domain:** AI provider truth, external dependency  
**Severity:** HIGH — hidden external dependency

---

### 3.6 Daily Loss Lock Auto-Reset Depends on jobs/ Module That May Not Start — HIGH

**File:** `backend/server.py` lines 238–239
```python
from jobs.daily_loss_reset import run_daily_loss_reset_loop
asyncio.create_task(run_daily_loss_reset_loop(db.db))
```

**Issue:** This runs in the startup lifespan context. If this task crashes or is not started (e.g., because the jobs module has an import error), daily loss locks will NEVER auto-reset at midnight. Bots will remain locked indefinitely until manual admin action.

There is no health check or diagnostic endpoint that verifies the midnight reset job is running. If the task silently exits after an exception, no alert is triggered.

**Domain:** Risk lock truth, scheduler health  
**Severity:** HIGH

---

## 4. Missing Services / Managers / Canonical Layers

### 4.1 No Canonical Paper-Reset Orchestrator — HIGH

**Issue:** Paper reset logic is scattered across four endpoints and two files:
- `POST /api/system/paper-reset` → `perform_paper_reset()` in `system_mode.py` (most complete)
- `POST /api/system/reset-paper` → same function but with password auth wrapper
- `POST /api/wallet/paper/reset` → only resets wallet balance via `paper_wallet_service.reset()`
- `POST /api/admin/start-fresh` → does NOT call `perform_paper_reset()` or `paper_wallet_service.reset()`

There is no single `PaperResetOrchestrator` service that any path calls. Each call site has different scope. No single "canonical reset" service exists.

**What's missing:** A `services/paper_reset_service.py` that defines the complete and authoritative reset sequence, called by all four endpoints.

**Domain:** Reset truth  
**Blocker:** YES

---

### 4.2 No Scheduler Health Manager — HIGH

**Issue:** Three schedulers run as asyncio background tasks: `trading_scheduler`, `autonomous_scheduler`, and `ai_scheduler`. There is no service that:
- Tracks whether each scheduler is running
- Detects task crashes and restarts them
- Provides a unified health endpoint reporting all scheduler states
- Emits realtime events when a scheduler goes down

The `trading_scheduler` uses `self.is_running` but does not emit any events if the task crashes. `autonomous_scheduler` uses `self.is_running` similarly. A crashed scheduler will silently fail — no bots will trade, no autopilot will run, but the system will appear "healthy".

**What's missing:** A `SchedulerHealthManager` or a background watchdog that monitors asyncio tasks and restarts/alerts on failure.  
**Domain:** Scheduler truth  
**Severity:** HIGH

---

### 4.3 No Canonical Bot Summary Endpoint — MEDIUM

**Issue:** Bot counts are computed differently in:
- `GET /api/dashboard/overview` → `overview_service.get_snapshot()`
- `GET /api/bots/status` → direct DB query
- `GET /api/scalper/summary` → direct DB query, scalper-only
- `GET /api/diagnostics/truth` → `get_canonical_bot_counts()` from `services/canonical.py`

`services/canonical.py` exists and has `get_canonical_bot_counts()`, but it's only used by `dashboard_overview.py` and `diagnostics.py`. `bot_lifecycle.py`'s `/api/bots/status` computes its own counts directly.

**What's missing:** All bot count endpoints should call `get_canonical_bot_counts()`. Currently only 2 of 4 count sources do.  
**Domain:** Bot count truth  
**Severity:** MEDIUM

---

### 4.4 No Canonical Risk Summary Endpoint — MEDIUM

**Issue:** Risk state is scattered across:
- `services/risk_lock_service.py` → daily loss lock (authoritative per previous audit)
- `services/bodyguard_service.py` → bodyguard lock
- `engines/circuit_breaker.py` → circuit breaker state
- `services/truth_kernel.py` → assembles risk state from all of the above

There is no canonical `GET /api/risk/summary` endpoint that returns the complete risk state (daily lock status, bodyguard status, circuit breaker states, drawdown) in one call. The frontend piecing together risk state from multiple calls creates race conditions.

**What's missing:** A `GET /api/risk/summary` canonical endpoint that returns all risk states in one atomic snapshot.  
**Domain:** Risk state truth  
**Severity:** MEDIUM

---

### 4.5 No Queue/Trade Execution Observability — HIGH

**Issue:** The trading scheduler executes trades asynchronously but there is no:
- Trade execution queue diagnostic endpoint
- Count of trades queued vs executed vs rejected
- Latency measurement for execution cycles
- Mechanism to detect stalled execution (scheduler running but no trades completing)

If the trading scheduler is running but `paper_trading_engine.execute_paper_trade()` is silently returning `None` on every call (due to market data unavailability, risk blocks, or any other cause), there is no observable signal — no counter, no metric, no alert.

**Domain:** Execution observability  
**Severity:** HIGH

---

## 5. Silent Failure Paths

### 5.1 Paper Trade execute_paper_trade Returns None Without Persistent Trace — HIGH

**File:** `backend/paper_trading_engine.py` — `execute_paper_trade()` returns `None` in 15+ code paths

**Code path in trading_scheduler.py:**
```python
result = await self.execute_paper_trade(bot, ...)
if result and isinstance(result, dict):
    # handle success
# else: silently do nothing
```

When `execute_paper_trade()` returns `None`:
- No trade is recorded
- No event is emitted
- No counter is incremented
- No log entry at WARNING or above is guaranteed

A bot can be "active" and the scheduler "running", but if every execution returns `None` (e.g., due to a market data failure defaulting to fallback prices that don't meet edge criteria), the system will appear operational while producing zero trades forever.

**Domain:** Paper execution truth  
**Severity:** HIGH

---

### 5.2 Daily Loss Reset Job Silently Exits on Exception — HIGH

**File:** `backend/jobs/daily_loss_reset.py`

The job runs as an asyncio task started at server startup. If it encounters any unhandled exception, the task will terminate silently. No restart mechanism exists. The `daily_loss_reset_loop` will appear to be running in the task list until it isn't, with no observable signal.

**Domain:** Risk lock auto-reset  
**Severity:** HIGH

---

### 5.3 Realtime Force Refresh on Paper Reset Races With DB Deletion — MEDIUM

**File:** `backend/routes/system_mode.py` — `perform_paper_reset()` end:
```python
await manager.send_message(user_id, {"type": "paper_reset", ...})
await rt_events.force_refresh(user_id, reason="Paper trading reset completed.")
```

This fires the realtime refresh immediately after DB operations. However, the DB deletions use `await collection.delete_many(...)` calls that are all sequential. If any deletion is slow (e.g., large learning_data collection), the force refresh fires before deletion is complete. The frontend will poll for fresh data while some collections still contain old data, receiving a partially-reset snapshot.

**Domain:** Reset data consistency  
**Severity:** MEDIUM

---

### 5.4 Startup Migration calls repair_api_keys.py Every Boot — MEDIUM

**File:** `backend/migrations/fix_user_id_field.py` — `migrate_api_keys_repair()`:
```python
from repair_api_keys import repair_api_keys
stats = await repair_api_keys()
```

The `repair_api_keys` function is called on EVERY startup without any guard that checks whether migration was already completed. This means it scans and potentially modifies the `api_keys_collection` on every server restart. For a production system with many keys, this adds startup latency and risks modifying already-correct data.

**Domain:** Startup reliability, data integrity  
**Severity:** MEDIUM

---

### 5.5 Autonomous Scheduler Tasks Not Restarted on Crash — HIGH

**File:** `backend/autonomous_scheduler.py` — `start()` method:
```python
self.tasks = [
    asyncio.create_task(self._hourly_tasks()),
    asyncio.create_task(self._daily_tasks()),
    asyncio.create_task(self._regime_monitor())
]
```

If any of these three tasks crashes, the exception is swallowed by the asyncio event loop and the task is simply not running. `self.is_running` remains `True` but the actual work stops. No monitoring, no restart, no alert.

**Domain:** Autonomous scheduler truth  
**Severity:** HIGH

---

### 5.6 WebSocket send_message Silently Ignores Disconnected Clients — LOW

**File:** `backend/websocket_manager.py`

Standard pattern: iterate connections, catch `WebSocketDisconnect`, remove from set. This is correct behavior, but after a disconnect the frontend's `realtime.js` SSE client and `useRealtime.js` WebSocket hook both attempt reconnection independently. If the SSE reconnects but WebSocket doesn't (or vice versa), the frontend will have a split realtime feed — some events via SSE, some via WebSocket — potentially processing the same event twice or missing events.

**Domain:** Realtime event deduplication  
**Severity:** LOW

---

## 6. Missing Diagnostics / Proof Mechanisms

### 6.1 No Endpoint Verifying Scheduler is Actually Running — CRITICAL

**Gap:** The existing `GET /api/diagnostics/go-live` checks scheduler state via a broken module import (see Section 2.3). There is no working endpoint that:
- Reads `trading_scheduler.is_running` (the actual attribute)
- Reports the last heartbeat timestamp
- Reports when the last trade execution attempt was made
- Reports the last successful trade completion

**What's needed:** Either fix the go-live diagnostic or add `GET /api/diagnostics/scheduler-health` that reads `trading_scheduler.is_running`, `trading_scheduler.last_heartbeat`, and returns a `PASS`/`WARN`/`FAIL` status.

**Domain:** Scheduler observability  
**Severity:** CRITICAL

---

### 6.2 No "Paper Trading Active" Proof Endpoint — HIGH

**Gap:** There is no endpoint that proves paper trading is actively executing, distinct from "the scheduler is running". Specifically no endpoint confirms:
- When the last paper trade was executed (timestamp)
- How many paper trades have executed in the last N minutes
- Whether any bots have been skipped due to gate failures
- Whether execution is blocked by environment variables

**Domain:** Paper execution observability  
**Severity:** HIGH

---

### 6.3 No Reset Completion Proof Endpoint — HIGH

**Gap:** After calling `POST /api/system/paper-reset`, the response returns a summary dict with counts. But there is no:
- `GET /api/diagnostics/reset-proof` endpoint that independently verifies the DB is in a clean post-reset state
- Validation that paper wallet balance is at the correct starting value
- Verification that no orphaned bot records exist
- Confirmation that circuit breaker state was cleared

**Domain:** Reset proof  
**Severity:** HIGH

---

### 6.4 No API Key Readiness Endpoint for All 11 Providers — MEDIUM

**Gap:** `GET /api/keys/status` lists key statuses, but there is no endpoint that returns a simple boolean readiness check for each of the 11 providers in a format suitable for a go-live pre-flight. The closest is the go-live diagnostic's API keys check (which uses `keys_service` — which is missing `kraken` and `gate` per Section 2.2).

**Domain:** API key readiness  
**Severity:** MEDIUM

---

### 6.5 /api/health/ready Never Returns FAIL — MEDIUM

**File:** `backend/routes/health.py` — `GET /api/health/ready`

Review: most readiness checks return status/WARN but very few conditions result in a hard `FAIL` or non-200 HTTP status. A Kubernetes readiness probe or nginx health check calling `/ready` will always get a 200 OK, even when:
- MongoDB is degraded
- The scheduler is not running
- Paper wallet is not initialized

**Domain:** Deployment readiness  
**Severity:** MEDIUM

---

## 7. Partial Implementations / Half-Wired Features

### 7.1 BotRadarSection Uses /api/radar/snapshot — Backend Exists, But Not in Dashboard Nav — HIGH

**Frontend:** `BotRadarSection.js` calls `GET /api/radar/snapshot`  
**Backend:** `routes/radar.py` has `GET /api/radar/snapshot` and `GET /api/radar/timeseries`  
**Issue:** The BotRadarSection is not imported in `Dashboard.js` and not in any `NAV` constant. The backend exists and appears functional, but users can never see it. This is a complete UI-to-backend feature that exists in both layers but is not connected via navigation.

**Domain:** Dashboard feature completeness  
**Severity:** HIGH — complete but inaccessible feature

---

### 7.2 TruthConsoleSection Uses /api/admin/truth/summary — Works But Not Nav-Connected — HIGH

**Frontend:** `TruthConsoleSection.js` calls `GET /api/admin/truth/summary`  
**Backend:** `routes/admin_truth.py` has the endpoint, uses Truth Kernel  
**Issue:** `TruthConsoleSection` IS rendered — it's included inside `AdminTruthSection`, which IS mounted in `Dashboard.js`. However, `AdminTruthSection` is only shown when `activeSection === NAV.HIDDEN_ADMIN`, which requires the admin tab to be visible. The admin tab is conditionally shown based on `user.is_admin` — but the Dashboard.js code that checks this is missing. There is no `user.is_admin` check in the rendered nav.

**What this means:** Admin access to the truth console depends on backend returning `is_admin=true` in user data, but the frontend nav does not filter admin tab by this field.

**Domain:** Admin truth console access  
**Severity:** HIGH

---

### 7.3 ExchangeStatusSection Uses /api/exchanges/status — Backend Has Different Endpoint — MEDIUM

**Frontend:** `ExchangeStatusSection.js` calls `GET /api/exchanges/status`  
**Backend:** `routes/exchange_status.py` defines `GET /status` under prefix... let's check.

`exchange_status.py` has `@router.get("/status")`. If the router is mounted with `prefix="/api/exchanges"`, this maps to `GET /api/exchanges/status` — correct. If mounted without prefix or different prefix, it's broken.

**Domain:** Exchange status feature  
**Severity:** MEDIUM — needs mounting verification

---

### 7.4 ScalperBotsPanel Uses Raw `fetch` Without JWT Headers Correctly — MEDIUM

**File:** `frontend/src/pages/dashboard/sections/ScalperBotsPanel.js`
```js
fetch('/api/scalper/caps', { headers }),
```
Where `headers = axiosConfig?.headers || {}`.

**Issue:** This panel receives `axiosConfig` as a prop but uses raw `fetch()` instead of the authenticated `apiClient`. If `axiosConfig` is not passed (or passed as `{}`), the requests have no JWT Authorization header. The backend `/api/scalper/caps` is protected by `Depends(get_current_user)`. Anonymous calls will return 401.

The panel does error handling on `capsRes.ok` and `summaryRes.ok` but does not distinguish 401 (auth failure) from other errors.

**Domain:** Scalper panel auth, frontend API contract  
**Severity:** MEDIUM

---

### 7.5 AiChatSection Has Two Entry Points With Different API Targets — MEDIUM

**File:** `AiChatSection.js` is imported by:
1. `WelcomeSection.js` — which is actually rendered in Dashboard.js
2. `AiCommandSection.js` — which is NOT in Dashboard.js

`WelcomeSection` renders `AiChatSection` inline. But `AiChatSection` calls... what backend endpoint? It's part of the "welcome" view but connects to the chat backend. If the chat backend is `/api/chat/message` (chat_endpoints.py) but the AI page shows responses from `/api/ai/chat` (ai_chat.py), the user sees messages from one endpoint history and sends to a different endpoint.

**Domain:** Chat truth, AI integration  
**Severity:** MEDIUM

---

## 8. State Drift / Cache / Realtime Risks

### 8.1 Overview Service Called by Multiple Realtime Paths Independently — HIGH

**Files:** `services/realtime_broadcaster.py` and `services/realtime_service.py` both instantiate `OverviewService` independently:
```python
# realtime_broadcaster.py:
from services.overview_service import OverviewService  # imported at module level

# realtime_service.py:
from services.overview_service import OverviewService  # imported inside method
```

Both create fresh `OverviewService()` instances and call `get_snapshot()` on potentially overlapping push cycles. If the realtime broadcaster and the SSE service both trigger a push simultaneously, two different snapshots with slightly different data can be computed from the same DB at slightly different times, sent to the frontend as two different "current state" events.

**Domain:** Realtime state consistency  
**Severity:** HIGH

---

### 8.2 analytics_api.py Cache Survives Paper Reset — HIGH

**File:** `backend/routes/analytics_api.py` — uses `metrics_service` which wraps `accounting_service`. Neither the reset endpoint nor the paper reset notify `metrics_service` or `accounting_service` to invalidate any in-memory state.

If `metrics_service` or `accounting_service` have any instance-level caching (check: `MetricsService` and `AccountingService` are module-level singletons), their cached data from before the reset will be served until the next natural refresh cycle.

**Domain:** Analytics truth after reset  
**Severity:** HIGH

---

### 8.3 Frontend Polling and WebSocket Can Deliver Conflicting Bot Counts — HIGH

**Pattern:** `useDashboardState.js` has two update sources for bot counts:
1. Polling every 30 seconds via `refreshAllDashboardData()` → calls `GET /api/dashboard/overview`
2. WebSocket messages that trigger `refreshBotState()` → may call different endpoints

If a bot state change arrives via WebSocket and triggers `refreshBotState()`, the bot list is updated from `GET /api/bots/status`. Meanwhile, the overview panel still shows bot counts from the last `GET /api/dashboard/overview` poll. The sidebar counter can show `3 active` while the bot management section shows `2 active` for up to 30 seconds.

**Domain:** Dashboard state consistency  
**Severity:** HIGH

---

### 8.4 system_modes_collection Not Invalidated After Server Restart — MEDIUM

**Issue:** The system mode (paper/live/autopilot) is stored per-user in `system_modes_collection`. When the server restarts, the trading scheduler reads mode from this collection. However, if the server crashed while in live trading mode, the DB still shows `liveTrading: true`. On restart, the trading scheduler will immediately start live trading without user confirmation.

**Domain:** Trading mode safety on restart  
**Severity:** MEDIUM — safety risk

---

### 8.5 Bot Count Snapshot Includes "Deleted" Bots During Race Condition — LOW

**Issue:** When paper reset runs, bots are soft-deleted (status="deleted") before trades are deleted. During the brief window between soft-deletion and trade deletion, if a realtime push fires, the bot count from `get_canonical_bot_counts()` will exclude the deleted bots (correct), but `trades_collection` still has old trades, making profit figures inconsistent for a brief window.

**Domain:** Reset atomicity  
**Severity:** LOW

---

## 9. Testing Gaps That Still Matter for Go-Live

### 9.1 No Test That Verifies Trading Gates Read Correct Env Vars — CRITICAL

**Gap:** `tests/test_trading_mode_gating.py` exists, but it likely mocks the trading gate check. There is no test that specifically verifies that `utils/trading_gates.py` and `config.py` read the SAME env variable names. A test of the form:
```python
# Set ENABLE_PAPER_TRADING=true (what config.py reads)
# Do NOT set PAPER_TRADING=1 (what trading_gates reads)
# Assert that paper trade execution is allowed
```
This test would currently FAIL, exposing the env var name split.

**Domain:** Paper trading execution  
**Severity:** CRITICAL

---

### 9.2 No End-to-End Paper Trade Execution Test That Completes a Full Cycle — HIGH

**Gap:** `tests/test_paper_trade_deterministic.py` and `tests/test_paper_trade_scenario.py` exist but the scenario test is permanently IGNORED. There is no test that:
1. Creates a bot
2. Sets paper mode
3. Calls `execute_paper_trade()` with real (not mocked) trading gate checks
4. Verifies a trade record is written to `trades_collection`
5. Verifies paper wallet balance is updated
6. Verifies the overview snapshot reflects the new trade

**Domain:** Paper trade execution E2E  
**Severity:** HIGH

---

### 9.3 No Test That Verifies go-live Diagnostic Returns Correct Scheduler State — HIGH

**Gap:** No test verifies that `GET /api/diagnostics/go-live` returns `PASS` (not `WARN`) for the scheduler check when the scheduler is running. Given that the module import is broken (Section 2.3), this test would currently fail.

**Domain:** Diagnostic truth  
**Severity:** HIGH

---

### 9.4 No Test for JWT Expiry Handling — HIGH

**Gap:** No frontend test verifies the behavior when a 401 is returned from any API call. Specifically: does the dashboard redirect to `/login` or silently freeze?

**Domain:** Frontend auth safety  
**Severity:** HIGH

---

### 9.5 No Test for keys_service SUPPORTED_PROVIDERS Coverage — HIGH

**Gap:** No test verifies that `keys_service.SUPPORTED_PROVIDERS` covers all 7 exchanges. A simple test:
```python
from services.keys_service import SUPPORTED_PROVIDERS
assert 'kraken' in SUPPORTED_PROVIDERS
assert 'gate' in SUPPORTED_PROVIDERS
```
Would currently FAIL.

**Domain:** API key management coverage  
**Severity:** HIGH

---

### 9.6 test_canonical_truth.py Permanently Ignored — HIGH

**File:** `tests/test_canonical_truth.py` is permanently skipped (pytest.ini `--ignore` flag).

This test is the most important test for go-live correctness — it verifies that canonical bot counts, wallet state, and truth kernel outputs are consistent across subsystems. It cannot run because of async plugin issues. Fixing the async infrastructure for this one test is required before go-live.

**Domain:** Canonical truth verification  
**Severity:** HIGH

---

## 10. Safety / Security / Operational Risks

### 10.1 JWT Secret Has Dangerous Default Value in auth.py — HIGH

**File:** `backend/auth.py` line 10
```python
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
```

**File:** `backend/config.py` line 21
```python
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
```

Both files have a hardcoded default JWT secret. In a deployment where `JWT_SECRET` is accidentally omitted from the env file, the server will start and APPEAR to work, but ALL tokens will be signed with `"your-secret-key"` — a well-known public default. Any attacker who knows this default can forge valid JWTs for any user.

**Why missed:** Previous audit noted config contradictions but did not inspect auth.py for the default JWT secret value.  
**Domain:** Authentication security  
**Severity:** HIGH — security risk, not just operational

---

### 10.2 Paper-to-Live Mode Switch Has No Cooldown — HIGH

**File:** `backend/routes/system_mode.py` — `switch_mode()` endpoint

The mode switch from paper to live trading has an admin-only check and a confirmation token but **no time-based cooldown**. An admin can:
1. Switch to paper mode
2. Immediately switch to live mode
3. Switch back to paper
... in rapid succession with no rate limiting.

Each mode switch triggers bot state transitions. Rapid switching can leave bots in indeterminate states where some receive the mode change event and others don't.

**Domain:** Mode safety  
**Severity:** HIGH

---

### 10.3 Admin `start_fresh` Endpoint Has No Rate Limit — HIGH

**File:** `backend/routes/admin_start_fresh.py`

`POST /api/admin/start-fresh` is admin-only but has no rate limiting. Multiple rapid calls with the confirmation phrase "DELETE ALL TRADING DATA" will delete all bots multiple times. The second call will find no bots to delete (all already soft-deleted) but will still wipe all associated collections again, including the wallet.

**Domain:** Admin safety  
**Severity:** HIGH

---

### 10.4 Paper Reset Password Mechanism — Weak Security Pattern — MEDIUM

**File:** `backend/routes/system_mode.py` lines 28–55

`PAPER_RESET_PASSWORD` is read from environment. The same password is used for ALL users. Rate limiting (5 attempts) applies per-user but the shared password means:
- If one user learns the password, any user can reset any other user's paper data... 
- Wait: the reset endpoint uses `user_id: str = Depends(get_current_user)`, so it only resets the authenticated user's data. The password requirement is additional security, not the only gate.

However, if `PAPER_RESET_PASSWORD` is not set in the environment, `get_paper_reset_password()` may return an empty string or raise an error. An empty password would mean any string matches or `is_paper_reset_password_valid("")` depends on the implementation.

**Domain:** Paper reset security  
**Severity:** MEDIUM

---

### 10.5 AI Bodyguard enabled_flag Logic is Inverted — MEDIUM

**File:** `backend/services/lifecycle.py` lines 72 and 190–194

```python
SubsystemDefinition(
    name="AI Bodyguard",
    enabled_flag="disable_ai_bodyguard",  # Note: inverted logic
    ...
)
```

The logic: if `DISABLE_AI_BODYGUARD=true`, skip the bodyguard. This means:
- Default `DISABLE_AI_BODYGUARD=false` → bodyguard IS started (correct)
- `DISABLE_AI_BODYGUARD=true` → bodyguard is skipped

But the lifecycle manager's general logic at line 207:
```python
elif not self.feature_flags.get(flag_name, False):
    # disabled
```
Without the `if flag_name == "disable_ai_bodyguard":` special case, the inverted logic would cause the bodyguard to start only when disabled. The special case handles it, but this pattern is fragile — if someone adds another inverted flag without the special case, the AI bodyguard pattern will be silently wrong.

**Domain:** Risk management safety  
**Severity:** MEDIUM

---

## 11. Documentation / Runbook Gaps

### 11.1 No Single Operational Runbook — CRITICAL

**Gap:** Despite 92+ docs, there is no single "RUNBOOK.md" that answers:
- How to restart a crashed service
- How to check which scheduler is actually running
- How to diagnose why no trades are executing
- What to do when daily loss lock fires
- How to perform a paper reset and verify it completed
- How to check if the JWT secret is correctly configured
- How to verify a deployment is live and all components are healthy

There are 28+ verification scripts, 12+ deploy guides, but no single operations runbook that a live VPS admin can consult when something goes wrong at 3am.

**Domain:** Operational readiness  
**Severity:** CRITICAL

---

### 11.2 REPO_TRUTH.md Has Three Contradictions With Deployed Files — HIGH

As noted in Sections 3.1 and 3.2:
1. Service name: `amarktai-backend.service` (docs) vs `amarktai-api.service` (actual)
2. Backend path: `/opt/amarktai` (docs) vs `/var/amarktai/app/backend` (actual service)
3. Frontend path: correct (`/var/www/amarktai`) — consistent with ops/deploy.sh

REPO_TRUTH.md claims to be the canonical source of truth but has contradictions with the actual deployed infrastructure. Any new team member reading REPO_TRUTH.md will target the wrong paths.

**Domain:** Deployment truth  
**Severity:** HIGH

---

### 11.3 No Post-Deploy Verification Checklist That Accounts for All 11 Providers — MEDIUM

**Gap:** `VERIFICATION.md` and various verify scripts check basic health, login, and diagnostics. None of them:
- Verify all 11 provider endpoints are responding correctly
- Verify HuggingFace/CoinStats panels load without 401 errors
- Verify the scalper summary returns correct data
- Verify the bot radar endpoint is accessible
- Confirm paper reset completes cleanly and wallet balance is restored

**Domain:** Post-deploy verification  
**Severity:** MEDIUM

---

### 11.4 No Document Describing the Env Var Name Split — HIGH

**Gap:** The split between `PAPER_TRADING` (used by trading_gates.py) and `ENABLE_PAPER_TRADING` (used by config.py) is nowhere documented. There is no env variable reference document that maps: "this file reads this variable" for all critical modules. An operator setting up the env file based on any single document will only configure SOME of the variables correctly.

**Domain:** Configuration truth  
**Severity:** HIGH

---

## 12. Final "What We Still Need Before Perfect Go-Live" List

### MUST FIX (Blockers)

| # | Fix Required | Primary File(s) |
|---|-------------|-----------------|
| M1 | Unify env var names: `trading_gates.py` must read `ENABLE_PAPER_TRADING`/`ENABLE_LIVE_TRADING` OR root config must map both names | `utils/trading_gates.py`, `services/trading_mode_validator.py` |
| M2 | Add `kraken` and `gate` to `keys_service.SUPPORTED_PROVIDERS` | `services/keys_service.py` |
| M3 | Fix go-live diagnostic scheduler check: use `from trading_scheduler import trading_scheduler; trading_scheduler.is_running` | `server.py` lines 2863–2870 |
| M4 | Add `addEventListener('auth:unauthorized', ...)` in Dashboard.js or App.js to redirect to `/login` | `frontend/src/pages/Dashboard.js` or `App.js` |
| M5 | `admin_start_fresh` must call `paper_wallet_service.reset()` and clear paper ledger on full wipe | `routes/admin_start_fresh.py` |
| M6 | CI env check must validate `ENABLE_PAPER_TRADING`, `ENABLE_LIVE_TRADING`, `ENABLE_AUTOPILOT` — not the old var names | `.github/workflows/ci.yml` line 306 |
| M7 | `REPO_TRUTH.md` must be updated: service name `amarktai-api.service`, path `/var/amarktai/app/backend` | `docs/REPO_TRUTH.md` |

### SHOULD FIX (High-Risk)

| # | Fix Required | Domain |
|---|-------------|--------|
| S1 | Add scheduler watchdog / health endpoint using `trading_scheduler.is_running` | Scheduler truth |
| S2 | Add JWT secret validation at startup — fail fast if `JWT_SECRET == "your-secret-key"` | Security |
| S3 | Add time-based cooldown to paper→live mode switching | Mode safety |
| S4 | Rate-limit `start_fresh` endpoint | Admin safety |
| S5 | Fix `overview_service` and `metrics_service` to both delegate to `accounting_service` | Profit truth |
| S6 | Add event listener in frontend for token expiry on ALL background polling intervals | Auth state |
| S7 | Route `BotRadarSection` into Dashboard nav | Feature completeness |
| S8 | Add `flock_ai_client.py` to FLOKx regression test scope OR add it to provider registry | AI provider truth |
| S9 | Fix `test_canonical_truth.py` async infrastructure so it runs in CI | Testing coverage |
| S10 | Create `services/paper_reset_service.py` as canonical reset orchestrator | Reset truth |
| S11 | Unify audit logger — choose `engines/audit_logger.py` OR `services/safe_audit_logger.py`, not both | Audit truth |

### NICE TO HAVE (Required Enhancement for Clean Go-Live)

| # | Enhancement | Domain |
|---|-------------|--------|
| N1 | Add `GET /api/diagnostics/scheduler-health` endpoint | Scheduler observability |
| N2 | Add `GET /api/diagnostics/reset-proof` endpoint | Reset proof |
| N3 | Add `GET /api/risk/summary` canonical endpoint | Risk state truth |
| N4 | Add migration run-once guard to startup migrations | Startup reliability |
| N5 | Create RUNBOOK.md (single operational guide) | Operational readiness |
| N6 | Create ENV_REFERENCE.md mapping each variable to the file that reads it | Config documentation |
| N7 | Add paper trade execution counter to overview snapshot | Execution observability |
| N8 | Add `REACT_APP_BUILD_SHA` to frontend `.env.example` | Build metadata |

---

*End of Final Gap-Finding Audit Report.*  
*This report must be read in conjunction with FORENSIC_AUDIT_REPORT.md (Pass 1).*  
*Both reports can be handed directly to an LLM for final go-live recovery plan generation.*
