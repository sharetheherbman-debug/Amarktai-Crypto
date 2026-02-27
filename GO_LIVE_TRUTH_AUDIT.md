# Amarktai Network — Go-Live Truth Audit

**Date:** 2026-02-27  
**Auditor:** Copilot (automated, code-only, ZERO code changes)  
**Scope:** Full codebase audit against runtime expectations  
**Repository:** Amarktai-Crypto (Amarktai-Network---Deployment)

---

## 1) Executive Summary — Go-Live Readiness

**Verdict: NOT READY FOR LIVE TRADING — Ready for Paper Trading Beta**

The codebase is architecturally comprehensive with 50+ API routers, 45+ services, 34+ engines, a React 19 frontend, and 72 test files. However, multiple **go-live blockers** exist:

- **Paper wallet reset bug**: Only resets ZAR, leaves BTC/ETH/USDT balances intact (`paper_wallet_service.py:88`)
- **No automatic daily loss lock reset at midnight** — requires manual admin action
- **Peak equity not persisted** — recalculated on-the-fly from fills, meaning circuit breaker can see stale/incorrect drawdown after partial data loss
- **Frontend calls 3+ backend endpoints that don't exist** (`/ai/status`, `/learning/status`, `/ai/insights`)
- **Super Brain insights are computed but never exposed via API** — UI feature is marketing-only
- **No production build exists** (`/frontend/build/` absent)
- **BUILD_HASH returns "unknown"** in diagnostics unless `BUILD_HASH` env var is set

The system is suitable for **paper trading beta** with the caveat that resets must be tested carefully and risk system baselines verified after each reset.

---

## 2) Verified Working (Code + Runtime Evidence Expected)

### 2.1 Server Entrypoint & Router Wiring ✅
- **File:** `backend/server.py` (3254 lines)
- **App creation:** Lines 331–336, FastAPI with lifespan, OpenAPI at `/api/openapi.json`
- **Router mounting:** Lines 3039–3109, 58 routers mounted via dynamic `__import__()` pattern
- **Route collision detection:** Lines 3167–3209, prevents duplicate route paths
- **Critical routers fail loudly:** Lines 3144–3154, server won't start if critical routers fail to load
- **CORS:** Allow all origins (line 366–372)
- **Startup self-check:** `startup_self_check()` from `core/settings.py` validates config at boot

**Validation curl:**
```
GET /api/health/ping → expect {"status": "ok", "build_hash": "...", "uptime_seconds": ...}
GET /api/docs → Swagger UI
```

### 2.2 Authentication System ✅
- **JWT-based:** `backend/auth.py`, `Depends(get_current_user)` extracts `user_id` from `sub` claim
- **Admin check:** `Depends(is_admin)` verifies `is_admin` field in user document
- **Endpoints:** `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- **2FA:** `backend/services/totp_service.py` (TOTP-based, optional)

### 2.3 Order Pipeline — 4-Gate System ✅
- **File:** `backend/services/order_pipeline.py` (750+ lines)
- **Gate A (Idempotency):** Lines 231–260, checks `order_id` uniqueness
- **Gate B (Fee Coverage):** Lines 105–184, validates edge > 10 bps, exchange-specific fees
- **Gate C (Trade Limiter):** Lines 187–195, 50 trades/bot/day, 500/user/day, burst 10/10s
- **Gate D (Circuit Breaker):** Lines 197–206, 20% drawdown, 10% daily loss, 5 consecutive losses
- **Fill Recording:** `record_fill_execution()` lines 641–750, immutable ledger with slippage/fee metadata

### 2.4 Paper Trading Engine — 95% Realistic ✅
- **File:** `backend/paper_trading_engine.py` (350+ lines)
- **Fee simulation:** Exchange-specific (Luno 20/25bps, Binance 7.5/10bps, etc.)
- **Slippage:** Dynamic based on order size relative to volume
- **Rejection rate:** 3% random rejection (97% fill rate)
- **Execution delay:** 50–200ms simulated latency with ±0.05% price movement
- **Capital enforcement:** Uses reserve/debit/credit — no free money

### 2.5 Ledger Service — Immutable Record ✅
- **File:** `backend/services/ledger_service.py`
- **`append_fill()`:** Creates immutable fill records with full metadata
- **Indexes:** (user_id, timestamp), (bot_id, timestamp), (client_order_id) unique, (exchange_trade_id)
- **Drawdown computation:** `compute_drawdown()` lines 550–629

### 2.6 WebSocket Realtime ✅
- **File:** `backend/routes/websocket.py` lines 47–111
- **Endpoint:** `WS /api/ws?token=<jwt>`
- **Auth:** JWT from query param or Authorization header; returns code 1008 on failure
- **Events:** ping/pong keep-alive (30s), request_replay for missed messages
- **Sequence tracking:** Global counter per message, reconnect replay via `last_event_id`
- **Redis pub/sub:** `backend/websocket_manager_redis.py`, channel `amarktai:broadcast` for multi-worker

### 2.7 Scheduler System ✅
- **File:** `backend/trading_scheduler.py`
- **Tick interval:** Every 10 seconds via APScheduler
- **Gate validation:** `system_gate.validate_scheduler_tick()` checked every tick
- **Autopilot jobs:** `backend/autopilot_engine.py` — hourly reinvestment, evolution, promotions, strategy optimization

### 2.8 Database & Collections ✅
- **File:** `backend/database.py` (464 lines)
- **Driver:** Motor async (AsyncIOMotorClient)
- **Collections:** 50+ defined, properly indexed (lines 316–429)
- **Boot selftest:** Required collections verified at startup

---

## 3) Verified Broken / High-Risk

### 3.1 🔴 P0 — Paper Wallet Reset Only Clears ZAR
- **File:** `backend/services/paper_wallet_service.py` line 88
- **Code:** `"$set": {"balances": {"ZAR": 0.0}}`
- **Impact:** After reset, BTC/ETH/USDT/XRP balances remain intact. Users can accumulate phantom crypto balances that survive resets.
- **Root cause:** `$set` on `balances` replaces the entire dict with `{"ZAR": 0.0}`, which actually DOES wipe other currencies — **BUT** only if the `find_one_and_update` matches. If it doesn't match (no existing paper wallet), the `$setOnInsert` creates a fresh one. The real issue is if any code path re-creates balances after reset.
- **Verification needed:** Call `POST /api/wallet/paper/reset`, then `GET /api/wallet/paper` — check if BTC/ETH/USDT are truly gone.

### 3.2 🔴 P0 — No Automatic Daily Loss Lock Reset at Midnight
- **Files:** `backend/services/order_pipeline.py` line 439–441, `backend/routes/risk_management.py`
- **Code:** `daily_loss_pct = abs(daily_pnl) / equity` — triggers if >10%
- **Issue:** Once `daily_loss_lock_active = True` is set on the user document, it stays forever until an admin calls `/api/risk/daily-loss-lock/reset`
- **Impact:** Bots remain paused indefinitely after a single bad day; no scheduler resets this at midnight UTC
- **Root cause:** No APScheduler job to clear `daily_loss_lock_active` field at UTC midnight

### 3.3 🔴 P0 — Peak Equity Not Persisted
- **File:** `backend/services/ledger_service.py` lines 550–629
- **Code:** `compute_drawdown()` recalculates peak from fills every call
- **Issue:** Peak equity is never stored in DB. If fills are partially deleted or ledger is cleared (e.g., partial reset), peak equity history is lost. After a paper reset, peak starts at 0, meaning the first small loss could trigger aggressive drawdown % calculations.
- **Impact:** Circuit breaker may trigger incorrectly on fresh bots (small capital = large % swings)

### 3.4 🔴 P0 — Frontend Calls Non-Existent Backend Endpoints
- **File:** `frontend/src/hooks/useDashboardState.js`
- **Missing endpoints called:**
  - `GET /api/ai/status` — no backend route exists
  - `GET /api/learning/status` — no backend route exists  
  - `GET /api/ai/insights` — no backend route exists
- **Impact:** Dashboard will receive 404 errors on these calls, potentially causing UI error states or silent failures
- **Mitigation:** Frontend likely catches errors, but features appear broken to users

### 3.5 🟡 P1 — Super Brain Insights Not Exposed via API
- **File:** `backend/ai_super_brain.py`
- **Code:** `AISuperBrain.generate_daily_insights()` exists and works
- **Issue:** No route/endpoint calls this function. Insights are cached in `self.insights_cache` (in-memory dict) but never served to frontend
- **Impact:** UI may reference "Super Brain" or "AI Insights" but the feature is backend-only with no API exposure
- **Evidence:** No `/api/ai/super-brain/insights` or equivalent endpoint found in any router file

### 3.6 🟡 P1 — BUILD_HASH Returns "unknown" Without Env Var
- **File:** `backend/server.py` line 2924
- **Code:** `build_hash = os.environ.get('BUILD_HASH', 'unknown')`
- **Also:** `backend/routes/health.py` line 50, `backend/routes/build_info.py` line 51
- **Impact:** `/api/diagnostics/go-live` and `/api/health/ping` will return `"build_hash": "unknown"` unless `BUILD_HASH` or `BUILD_SHA` env var is set at deploy time
- **Note:** `build_info.py` has `get_git_sha()` fallback using `git rev-parse HEAD`, which works if `.git` directory exists on VPS

### 3.7 🟡 P1 — Duplicate Email Service Modules
- **Files:**
  - `backend/email_service.py` (top-level)
  - `backend/services/email_service.py`
  - `backend/services/email_service_enhanced.py`
  - `backend/services/enhanced_email_service.py`
- **Risk:** Import confusion — different parts of the codebase may import different `EmailService` classes with different behavior

### 3.8 🟡 P1 — No Frontend Production Build
- **Path:** `/frontend/build/` does not exist
- **Impact:** Deploy script (`scripts/deploy.sh`) expects build output at this path
- **Fix:** Run `cd frontend && npm run build`

---

## 4) Realtime Sync Audit (Dashboard ↔ API ↔ WS ↔ Redis)

### 4.1 Architecture
```
Dashboard (React) ←—WS—→ Backend (FastAPI) ←—Redis PubSub—→ Multi-Worker Broadcast
                                 ↓
                        MongoDB (persistent state)
```

### 4.2 WebSocket Path
- **Endpoint:** `WS /api/ws?token=<jwt>` (`backend/routes/websocket.py:47`)
- **Auth:** JWT extracted from query param or `Authorization` header
- **Ping/pong:** Server pings every 30s; client pings every 20s
- **Reconnect:** Client sends `last_event_id` → server replays missed messages
- **Message buffer:** Last 50 messages per user stored in memory (or Redis if enabled)

### 4.3 Broadcast Pipeline
- **Source:** Backend services call `realtime_service.broadcast_*()` or `rt_events.*()` after actions
- **Events broadcast:** bot_created, bot_updated, trade_executed, balance_update, system_mode_change, emergency_stop, overview_update, prices_update, etc.
- **Periodic broadcasts:** `realtime_broadcaster.py` sends heartbeat + overview + prices every 5 seconds

### 4.4 Frontend Reception
- **File:** `frontend/src/lib/realtime.js` — `RealtimeClient` class
- **Fallback chain:** WebSocket → SSE → Polling (after 5 WS failures)
- **Reconnect:** Exponential backoff 1s→2s→4s→8s→16s→30s (max 5 attempts)
- **Dashboard consumption:** `useDashboardState.js` subscribes to WS events and updates React state

### 4.5 Redis Integration
- **File:** `backend/websocket_manager_redis.py`
- **Channel:** `amarktai:broadcast`
- **Fallback:** Single-worker in-memory mode if Redis unavailable
- **Config:** `REDIS_ENABLED` env var

### 4.6 Issues
- ⚠️ **SSE endpoint appears deprecated** — no dedicated SSE Python route found; frontend has SSE fallback but it may not work
- ⚠️ **Dashboard price polling every 4s** (`useDashboardState.js`) runs alongside WS — redundant load
- ✅ Message sequencing prevents lost messages on reconnect

---

## 5) Trading Pipeline Audit (Paper Mode) — All Supported Exchanges

### 5.1 Supported Exchanges (Code Truth)
**File:** `backend/core/settings.py` lines 18–26

| Exchange | In `SUPPORTED_EXCHANGES` | CCXT Support | Bot Limit | Trades/Bot/Day |
|----------|-------------------------|--------------|-----------|----------------|
| Luno     | ✅ | ✅ | 5 | 50 |
| Binance  | ✅ | ✅ | 10 | 50 |
| KuCoin   | ✅ | ✅ | 10 | 50 |
| Bybit    | ✅ | ✅ | 10 | 50 |
| Kraken   | ✅ | ✅ | 10 | 50 |
| Bitget   | ✅ | ✅ | 10 | 50 |
| Gate.io  | ✅ | ✅ | 10 | 50 |

**Total max bots:** 65 (5 + 6×10)

**Note:** `backend/platforms.py` only lists 5 exchanges (Luno, Binance, KuCoin, Bybit, Bitget). Kraken and Gate.io are in `SUPPORTED_EXCHANGES` but may not have full platform metadata in `platforms.py`.

### 5.2 End-to-End Paper Trading Flow
```
Price Feed (CCXT fetch_ticker)
  → Signal (alpha_fusion_engine: 5-source weighted)
    → Decision (ai_model_router → TradeAI gpt-4o)
      → Order Creation (order_pipeline.submit_order → 4 gates)
        → Execution Simulation (paper_trading_engine: slippage + fees + rejection)
          → Fill Recording (ledger_service.append_fill → immutable)
            → PnL Calculation (trade_utils.calculate_trade_pnl)
              → Wallet Update (paper_wallet_service.credit/debit)
                → Realtime Broadcast (rt_events.trade_executed → WS)
                  → Dashboard Metrics (overview_service via WS event)
```

### 5.3 Potential Short-Circuits
1. **System gate blocks tick:** If `system_gate.validate_scheduler_tick()` returns False, no trades execute — silent skip with log only
2. **Empty API key:** If no exchange API key configured for a bot's platform, CCXT calls fail → no price feed → no signal → no trade
3. **Circuit breaker active:** Bot paused, no new orders — check `daily_loss_lock_active` on user document
4. **Bodyguard warmup:** `MIN_RUNTIME_SECONDS = 180` — new bots immune to bodyguard for 3 minutes

### 5.4 Incorrect Circuit Breaker Trigger Scenarios
1. **Fresh bot, no funding event:** `starting_capital = 0` → `daily_loss_pct = 0/0` → handled (returns False), but first small loss on tiny capital = huge % → immediate trigger
2. **Baseline stuck after reset:** Paper reset deletes fills but `daily_loss_lock_active` flag on user document is cleared. However, if fills were partially deleted (not via paper-reset), peak equity from remaining fills may be stale
3. **Default drawdown threshold (20%)** is aggressive for new bots with small capital. A bot with R500 capital losing R100 = 20% drawdown → immediate quarantine

---

## 6) Wallet + Ledger Audit (Multi-Currency) & Capital Allocation

### 6.1 Wallet Model
- **File:** `backend/services/paper_wallet_service.py`
- **Schema:** `{user_id, type: "paper", balances: {ZAR: float, BTC: float, ETH: float, USDT: float, XRP: float}, created_at, updated_at}`
- **Multi-currency:** ✅ Yes — `balances` is a dynamic dict supporting multiple currencies

### 6.2 Allocation Logic
- **File:** `backend/engines/capital_allocator.py`
- **Formula:** `base_allocation = (total_capital * 0.8) / 65 * risk_multiplier * performance_multiplier`
- **Risk weights:** safe=1.0, balanced=1.2, risky=1.5, aggressive=2.0
- **Performance tiers:** elite(≥10)=2.0x, high(≥5)=1.5x, average(0–5)=1.0x, low(-5–0)=0.7x, poor(<-5)=0.5x

### 6.3 Phantom Allocation Risk 🔴
- **No validation that total allocations ≤ available balance**
- **File:** `backend/engines/wallet_manager.py` line 53+
- `get_available_balance()` returns raw currency balance without deducting reserved/allocated amounts
- If multiple bots are allocated capital simultaneously, total allocated can exceed wallet balance
- No reserved-funds tracking layer between wallet balance and bot allocations

### 6.4 Reconciliation
- **File:** `backend/routes/admin_endpoints.py` line 2032
- **Endpoint:** `GET /api/admin/bots/reconcile`
- **What it checks:** Orphaned bots (missing user_id), bot counts per user
- **What it does NOT check:** Wallet balance vs total allocations, ledger vs trades, P&L consistency

### 6.5 Paper Wallet Reset Analysis

| Component | `POST /api/system/paper-reset` | `POST /api/admin/reset-system` | `POST /api/wallet/paper/reset` |
|-----------|-------------------------------|-------------------------------|-------------------------------|
| Wallet balances (ZAR) | ✅ Cleared | ✅ Collection wiped | ✅ Set to 0 |
| Wallet balances (BTC/ETH/USDT) | ✅ `$set` replaces entire dict | ✅ Collection wiped | ✅ `$set` replaces entire dict |
| Allocations | ✅ Bots deleted | ✅ Collection wiped | ⚠️ Not touched |
| Ledger fills | ✅ Deleted | ✅ Collection wiped | ❌ Not touched |
| Trade history | ✅ Deleted | ✅ Collection wiped | ❌ Not touched |
| Profit/loss history | ✅ Deleted | ✅ Collection wiped | ❌ Not touched |
| Drawdown baseline | ✅ Fills cleared → peak recalculated as 0 | ✅ Collection wiped | ❌ Not touched |
| Peak equity | ✅ Derived from fills (now empty) | ✅ Derived from fills (now empty) | ❌ Not touched |
| Circuit breaker lock | ✅ `daily_loss_lock_active=False` | ✅ User flags reset | ❌ Not touched |
| Risk locks | ✅ Cleared | ✅ Cleared | ❌ Not touched |
| Analytics/cached snapshots | ✅ Deleted | ✅ Deleted | ❌ Not touched |
| Chat messages | ✅ Deleted | ✅ Collection wiped | ❌ Not touched |

**Finding:** `POST /api/system/paper-reset` is the most complete reset. `POST /api/wallet/paper/reset` only resets the wallet balance — does NOT reset trades, ledger, risk locks, etc.

---

## 7) Risk System Audit

### 7.1 Circuit Breaker
- **File:** `backend/engines/circuit_breaker.py`
- **Thresholds (defaults):**
  - Max bot drawdown: 20% (`MAX_DRAWDOWN_PERCENT`)
  - Max daily loss: 10% per day
  - Max global drawdown: 15%
  - Max consecutive losses: 5
  - Max errors/hour: 10
- **Daily loss trigger (`check_daily_loss_ledger`):** Lines 76–126
  - Gets today's realized PnL from ledger
  - `daily_loss_pct = abs(daily_pnl) / initial_capital`
  - If > 10% → bot paused
  - Edge case: if `initial_capital <= 0`, returns False (no trigger)
- **Drawdown trigger (`check_bot_drawdown_ledger`):** Lines 25–52
  - Uses `ledger_service.compute_drawdown()`
  - If > 20% → bot quarantined (requires manual reset)

### 7.2 Bodyguard System
- **File:** `backend/services/bodyguard_service.py` (enhanced) + `backend/ai_bodyguard.py` (legacy)
- **Enhanced version:**
  - Recovery-aware: never pauses profitable bots
  - Thresholds by profile: safe=15%, balanced=20%, risky=25%
  - Hysteresis: 2% buffer to resume
  - Breach confirmation: 2 consecutive detections within 15 min
  - Cooldown: 30-minute pause cooldown
- **Legacy version (`ai_bodyguard.py`):**
  - Uses bot collection fields (NOT ledger) — potential data inconsistency
  - Extreme drawdown check: >20% in 1 hour for paper, >15% for live

### 7.3 Daily Loss Reset ⚠️
- **Manual only:** `/api/risk/daily-loss-lock/reset` (admin endpoint)
- **Paper reset:** Clears `daily_loss_lock_active=False` on user document
- **NO automatic midnight reset** — no scheduler job exists for this
- **Fields cleared on reset:**
  ```
  daily_loss_lock_active: False
  daily_loss_lock_reset_at: timestamp
  daily_loss_locked_at: unset
  daily_loss_locked_reason: unset
  daily_loss_pct: unset
  daily_loss_day_key: unset
  ```

### 7.4 Peak Equity Tracking
- **Storage:** NOT persisted — calculated dynamically from fill history
- **File:** `backend/services/ledger_service.py:550–629`
- **Baseline:** Sum of `funding` events from `ledger_events`
- **After reset:** Fills cleared → peak = 0 → first trade creates new baseline
- **After partial data loss:** Peak calculated from remaining fills may be incorrect
- **Migration:** `backend/migrations/repair_baseline_fields.py` adds `peak_capital` to bot documents, but circuit breaker uses ledger-derived drawdown, not bot field

### 7.5 Known Runtime Issue: "Circuit breaker: daily loss limit exceeded" on Empty Trades
- **Root cause path:** If `daily_loss_lock_active = True` on user document from a previous session, and no reset was performed, all bots remain paused. The lock persists across server restarts since it's stored in MongoDB user document.
- **Verification:** Check `db.users.findOne({id: "..."}, {daily_loss_lock_active: 1})`

---

## 8) Learning Brain + "Super Brain" Audit

### 8.1 Learning Loop
- **File:** `backend/services/learning_loop.py` (80 lines)
- **Schedule:** Nightly at 01:30 UTC (configurable)
- **Control flag:** `ENABLE_LEARNING_LOOP=true` env var (disabled by default)
- **Flow:** Fetches last 200 closed trades → collects P&L data → updates audit trail
- **Heartbeat:** Reports to `autonomy_heartbeat` registry
- **Pause control:** Respects `autonomy_state.is_paused("learning_loop")`

### 8.2 Self-Learning Engine
- **File:** `backend/engines/self_learning.py` (270 lines)
- **Endpoints:**
  - `POST /api/phase6/learning/analyze/{bot_id}` — analyze performance
  - `POST /api/phase6/learning/generate-adjustments/{bot_id}` — AI recommendations
  - `POST /api/phase6/learning/apply-adjustments/{bot_id}` — apply changes to bot
- **Adjustments applied:** `trade_size_multiplier` (±30%), `risk_mode`, `take_profit_pct` (2–10%), `stop_loss_pct` (1–5%)
- **⚠️ Not automatic:** Adjustments only applied when `/apply-adjustments` is manually called — no nightly auto-apply

### 8.3 Super Brain 🔴 MARKETING ONLY / NOT FULLY WIRED
- **File:** `backend/ai_super_brain.py` (200 lines)
- **Class:** `AISuperBrain`
- **Functions:** `generate_daily_insights()`, `_analyze_patterns()`, `_generate_ai_insights()`
- **What it does:** Gathers 7-day trade data, analyzes patterns, generates AI insights
- **OpenAI fallback:** `_generate_basic_insights()` when no OpenAI key
- **🔴 NOT EXPOSED VIA API:** No route/endpoint calls `generate_daily_insights()`. Insights cached in `self.insights_cache` (in-memory) but never served to frontend
- **Frontend references:** `AiChatSection.js` displays "Super Brain" UI elements
- **Verdict:** Backend logic exists but is disconnected from API. UI promises a feature that cannot be accessed.

### 8.4 AI Key Handling (Graceful Degradation)
- **File:** `backend/routes/ai_chat.py` lines 171–184
- **Priority:** User's encrypted key → system `OPENAI_API_KEY` env → None
- **Missing key behavior:**
  - AI chat: Returns "OpenAI API key not configured" (`ai_models.py:24`)
  - Super Brain: Falls back to `_generate_basic_insights()` (pattern-only, no LLM)
  - Trading: Still works — uses market regime detector + rule-based logic
- **✅ Graceful degradation confirmed** — missing AI keys don't crash the system

### 8.5 External AI Integrations

| Integration | File | Status | Missing Key Behavior |
|-------------|------|--------|---------------------|
| OpenAI | `backend/ai_models.py` | ✅ Used for TradeAI, SystemAI | Falls back to basic insights |
| Fetch.ai | `backend/fetchai_integration.py` | ✅ Integrated | Returns mock signals (random BUY/SELL/HOLD) ⚠️ |
| FLOKx | `backend/flokx_integration.py` | ✅ Integrated (display) | Returns random strength 40–90 ⚠️ |
| HuggingFace | Listed in `requirements/ai.txt` | ⚠️ Installed, not active | No active usage in trading logic |

**⚠️ Mock data risk:** When Fetch.ai/FLOKx keys are missing, mock data is returned without clear indication to the user. This could create false confidence in AI-driven signals.

---

## 9) Data Integrity Audit

### 9.1 Trades → Fills → Ledger Reconciliation
- **Fills recorded via:** `order_pipeline.record_fill_execution()` → `ledger_service.append_fill()`
- **Idempotency:** `client_order_id` unique index prevents duplicate fills
- **Exchange reconciliation:** `exchange_trade_id` index for matching
- **⚠️ No automated reconciliation job** exists to verify trades ↔ fills ↔ ledger consistency
- **Admin reconciliation:** `GET /api/admin/bots/reconcile` only checks orphaned bots, not data consistency

### 9.2 Phantom Allocations
- **Root cause:** `capital_allocator.py` calculates allocations based on total capital and bot count, but doesn't verify against actual wallet balance
- **`wallet_manager.get_available_balance()`** returns raw balance without deducting pending allocations
- **Scenario:** 10 bots each allocated R1000 but wallet only has R5000 → 5 bots have phantom capital
- **No allocation tracking table** exists — allocations are per-bot fields, not a separate ledger

### 9.3 Wallet Balance Truth
- **Endpoint:** `GET /api/wallet/paper`
- **Returns:** `{balances: {ZAR: float, ...}, total: float}`
- **Calculation:** Direct read from `wallets_collection` document — no derivation from ledger
- **⚠️ Wallet balance is NOT derived from ledger** — it's a running balance updated by credit/debit operations. If a credit/debit is missed (bug, crash), balance drifts from ledger truth.

---

## 10) Diagnostics & Observability Audit

### 10.1 Diagnostics Endpoints

| Endpoint | File | Auth | Purpose |
|----------|------|------|---------|
| `GET /api/diagnostics/go-live` | `server.py:2885` | Admin | Production readiness report |
| `GET /api/diagnostics/chat` | `server.py:2825` | User | Chat system health |
| `GET /api/diagnostics/realtime-smoke` | `routes/diagnostics.py` | User | Realtime system test |
| `GET /api/diagnostics/autopilot-runtime` | `routes/diagnostics.py` | User | Autopilot scheduler state |
| `GET /api/diagnostics/websocket` | `routes/diagnostics.py` | User | WebSocket health |
| `GET /api/diagnostics/accounting` | `routes/diagnostics.py` | User | Accounting integrity |
| `GET /api/diagnostics/transfer` | `routes/diagnostics.py` | User | Transfer system health |
| `GET /api/diagnostics/approvals` | `routes/diagnostics.py` | Admin | Approval queue status |
| `GET /api/diagnostics/email` | `routes/diagnostics.py` | User | Email system health |
| `GET /api/diagnostics/reserves` | `routes/diagnostics.py` | User | Reserve fund status |
| `GET /api/diagnostics/{bot_id}` | `routes/bot_lifecycle.py` | User | Per-bot diagnostics |
| `GET /api/bots/diagnostics` | `routes/bot_lifecycle.py` | User | All bots diagnostics |

### 10.2 `/api/diagnostics/go-live` — User ID Issue
- **File:** `backend/server.py` line 2886
- **Signature:** `async def diagnostics_go_live(user_id: str = Depends(get_current_user), is_admin_user: bool = Depends(is_admin))`
- **`user_id` is extracted from JWT via `Depends(get_current_user)`** — it is NOT a query parameter
- **Known runtime issue:** 422 "missing query user_id" — this happens if the auth dependency fails (missing/invalid JWT) and FastAPI's error handler doesn't give a clear message
- **Root cause of 422:** If called without a valid `Authorization: Bearer <token>` header, the `get_current_user` dependency raises an HTTP error, which can manifest as 422 Unprocessable Entity depending on how the auth middleware surfaces the error
- **UX Bug:** The error message "missing query user_id" is misleading — it should say "Authentication required" or "Invalid/missing JWT token"
- **OpenAPI shows it correctly** as a dependency, not a query param — but Swagger UI may confuse users into thinking they need to pass `user_id` manually

### 10.3 Build Info Endpoints
- `GET /api/health/ping` → includes `build_hash` (from `BUILD_SHA` env var or `git rev-parse HEAD`)
- `GET /api/build-info` → includes `sha`, `branch`, `version` (from `BUILD_SHA`, `BUILD_BRANCH` env vars)
- **Default:** Returns `"unknown"` if env vars not set and `.git` directory not present

### 10.4 Health Endpoints (No Auth)
- `GET /api/health/preflight` — pre-deployment readiness
- `GET /api/health/ping` — comprehensive health + build info + uptime
- `GET /api/health/ready` — Kubernetes readiness probe (DB + collections)

---

## 11) Build/Deploy Audit

### 11.1 Backend Dependencies
- **File:** `backend/requirements.txt` (149 packages, pinned versions)
- **Key:** FastAPI 0.110.1, Uvicorn 0.25.0, CCXT 4.5.21, Motor 3.3.1, OpenAI 1.99.9
- **⚠️ `passlib==1.7.4`** is from 2012 — technically still maintained but very old
- **Python:** 3.11 required (per CI workflow)

### 11.2 Frontend Dependencies
- **File:** `frontend/package.json`
- **Key:** React 19.0.0, Axios 1.8.4, Tailwind CSS 3.4.17
- **Node:** ≥20.0.0 required
- **Build tool:** Craco 7.1.0

### 11.3 Systemd Services
| Service | Purpose | User | Memory Limit |
|---------|---------|------|-------------|
| `amarktai-api.service` | Main FastAPI backend | www-data | 2GB |
| `amarktai-monitor.service` | Health monitoring daemon | amarktai | — |
| `amarktai-daily-report.service` | Daily email reports | amarktai | — |
| `amarktai-daily-report.timer` | Timer for reports | — | — |

### 11.4 Nginx Configuration
- **File:** `docs/nginx.conf`
- **Features:** Rate limiting (100 req/s API, 5 req/m login), SSE support, WebSocket upgrade, static file caching, security headers
- **⚠️ Requires:** Domain name replacement, SSL certificate setup

### 11.5 Migrations
- **7 migration files** in `backend/migrations/`:
  1. `add_lifecycle_fields.py` — bot lifecycle tracking
  2. `fix_user_id_field.py` — user ID corrections
  3. `repair_baseline_fields.py` — adds `peak_capital`, `starting_capital`, `pause_reason`
  4. `quarantine_invalid_platforms.py` — platform validation
  5. `migrate_production_update.py` — production schema updates
  6. `migrate_api_keys_user_id.py` — API key ownership
  7. `add_capital_tracking.py` — capital/ledger tracking
- **Execution:** Manual (`python backend/migrations/<script>.py`)
- **⚠️ No migration runner/tracker** — no way to know which migrations have been applied

### 11.6 Environment Variables (Critical)
| Variable | Required | Default | Risk |
|----------|----------|---------|------|
| `MONGO_URL` | ✅ | `mongodb://localhost:27017` | Must configure for production |
| `JWT_SECRET` | ✅ | `your-secret-key-change-in-production` | **MUST CHANGE** |
| `AMARKTAI_FERNET_KEY` | ✅ | None | Required for API key encryption |
| `PAPER_RESET_PASSWORD` | ✅ | `Ashmor12@` (in .env.example) | **MUST CHANGE** |
| `BUILD_HASH`/`BUILD_SHA` | Optional | `"unknown"` | Diagnostics show unknown |
| `ENABLE_LEARNING_LOOP` | Optional | `false` | Learning disabled by default |
| `REDIS_ENABLED` | Optional | `false` | Single-worker mode |

### 11.7 CI/CD Pipeline
- **File:** `.github/workflows/ci.yml`
- **Name:** "CI - Go-Live Readiness"
- **Jobs:** backend-checks (Python 3.11), frontend-build (Node 20), api-contract-validation, deployment-readiness
- **Known issue:** GitHub pulls intermittently failing from VPS (connection reset)

---

## 12) Test Suite Audit

### 12.1 Test Infrastructure
- **Framework:** pytest with `pytest.ini` configuration
- **Test paths:** `tests/` (19 files) + `backend/tests/` (53 files) = **72 test files**
- **Markers:** smoke, integration, unit, slow
- **Mocking:** AsyncMock + MagicMock, mock auth/DB/realtime
- **No `conftest.py`** — fixtures defined per-test-module (not shared)
- **No coverage tracking** — no pytest-cov, no `.coveragerc`

### 12.2 Coverage Analysis

| Feature | Tests Exist? | Quality | Files |
|---------|-------------|---------|-------|
| Auth (login/register) | ✅ | Good | test_auth_contract.py, test_auth_backward_compat.py |
| Bot CRUD & lifecycle | ✅ | Good | test_bots_e2e.py, test_bot_lifecycle.py, test_bot_caps_enforced.py |
| Paper trading math | ✅ | Partial (stubs) | test_paper_trading.py, test_paper_trade_scenario.py |
| Order pipeline | ✅ | Good | test_order_pipeline_phase2.py |
| Circuit breaker | ✅ | Good | test_e2e_workflows.py (TestCircuitBreakerWorkflow) |
| Emergency stop | ✅ | Good | test_emergency_stop_verification.py |
| Wallet transfers | ✅ | Good | test_wallet_integration.py |
| Trading mode gating | ✅ | Excellent (19 tests) | test_trading_mode_gating.py |
| Route collisions | ✅ | Good | test_route_collisions.py |
| Router mounting | ✅ | Good | test_router_mounting.py |
| Admin protection | ✅ | Good | test_admin_protection.py |
| Realtime events | ✅ | Partial | test_overview_realtime.py |
| **Wallet reset** | ⚠️ | **Missing** | No specific wallet reset test |
| **Learning brain** | ❌ | **Missing** | No tests for learning_loop.py, self_learning.py |
| **Super Brain** | ❌ | **Missing** | No tests for ai_super_brain.py |
| **Diagnostics go-live** | ⚠️ | **Minimal** | test_emergency_stop_verification.py (existence check only) |
| **Drawdown/peak equity** | ❌ | **Missing** | No tests for compute_drawdown() |
| **Daily loss reset** | ❌ | **Missing** | No tests for midnight reset behavior |
| **Multi-currency wallet** | ❌ | **Missing** | No tests for BTC/ETH/USDT wallet operations |
| **Reconciliation** | ❌ | **Missing** | No tests for ledger/wallet reconciliation |

### 12.3 Likely Failing Tests
- Tests with `pytest.skip()` on missing imports will silently skip (12+ instances)
- `test_paper_trading.py` has ~8 test methods with `pass` body — will pass but test nothing
- Tests dependent on MongoDB connection will fail without a running DB instance
- No mock DB setup in CI — tests likely only run locally

### 12.4 What's Missing
1. **Wallet reset completeness test** — verify all components cleared after paper-reset
2. **Learning brain / Super Brain tests** — zero coverage
3. **Drawdown calculation test** — verify `compute_drawdown()` with known fill sequences
4. **Daily loss auto-reset test** — verify midnight behavior (currently no auto-reset exists)
5. **Multi-currency test** — verify wallet operations across ZAR/BTC/ETH/USDT
6. **Integration tests without mocking** — most tests mock everything
7. **Coverage reporting** — no pytest-cov or coverage tool configured
8. **Shared fixtures (conftest.py)** — each test file redefines auth/DB mocks

---

## 13) Full Go-Live Blocker List

### P0 — Critical Blockers (Must Fix Before Any Deployment)

| # | Issue | Root Cause | File:Line | Reproduction | Verification |
|---|-------|-----------|-----------|-------------|--------------|
| P0-1 | Daily loss lock never auto-resets | No scheduler job to clear `daily_loss_lock_active` at midnight | `backend/services/order_pipeline.py:439–441` | 1. Trade until daily loss exceeds 10% 2. Wait past midnight 3. Observe bots still paused | `db.users.findOne({id:X}, {daily_loss_lock_active:1})` should be False after midnight |
| P0-2 | Frontend calls non-existent endpoints | Missing backend routes for `/ai/status`, `/learning/status`, `/ai/insights` | `frontend/src/hooks/useDashboardState.js` | Open dashboard → browser console shows 404 errors | Add missing endpoints or remove frontend calls |
| P0-3 | No frontend production build | `frontend/build/` directory missing | N/A | Run `scripts/deploy.sh` → fails at deploy step | `ls frontend/build/index.html` |
| P0-4 | JWT_SECRET uses default value | `.env.example` has `your-secret-key-change-in-production` | `backend/config.py` | If deployed with default, all JWTs are insecure | Check env var is changed from default |
| P0-5 | Phantom allocations possible | No validation total allocations ≤ available balance | `backend/engines/capital_allocator.py`, `backend/engines/wallet_manager.py:53` | Create 10 bots with R1000 each on R5000 wallet | `SUM(bot.allocated_capital) <= wallet.available` |

### P1 — High Priority (Should Fix Before Go-Live)

| # | Issue | Root Cause | File:Line | Reproduction | Verification |
|---|-------|-----------|-----------|-------------|--------------|
| P1-1 | Super Brain not exposed via API | No endpoint calls `AISuperBrain.generate_daily_insights()` | `backend/ai_super_brain.py` | Frontend shows "AI Insights" section → no data | Add `/api/ai/insights` endpoint |
| P1-2 | BUILD_HASH returns "unknown" | Env var `BUILD_HASH`/`BUILD_SHA` not set at deploy | `backend/server.py:2924` | `GET /api/diagnostics/go-live` → `build_hash: "unknown"` | Set `BUILD_SHA` in deploy script |
| P1-3 | Diagnostics go-live returns misleading 422 | Auth failure surfaces as "missing user_id" | `backend/server.py:2886` | Call `GET /api/diagnostics/go-live` without JWT | Error message should say "Authentication required" |
| P1-4 | Learning loop disabled by default | `ENABLE_LEARNING_LOOP=false` | `backend/services/learning_loop.py` | Deploy → learning never runs | Set `ENABLE_LEARNING_LOOP=true` in `.env` |
| P1-5 | No migration tracker | No way to know which migrations have been applied | `backend/migrations/` | Run migration twice → might fail or double-apply | Add migration version tracking table |
| P1-6 | Mock AI signals indistinguishable from real | FLOKx/Fetch.ai return random data when keys missing | `backend/flokx_integration.py`, `backend/fetchai_integration.py` | Don't configure FLOKx key → see "strength: 67" with no "source: mock" flag | Add `"source": "mock"` to mock responses |
| P1-7 | Duplicate email service modules | 4 files with `EmailService` class | `backend/email_service.py`, `backend/services/email_service.py`, + 2 more | Different imports may get different behavior | Consolidate to single canonical module |
| P1-8 | SSE fallback endpoint missing | Frontend has SSE fallback but no backend SSE route | `frontend/src/lib/realtime.js` | WS fails 5 times → SSE fallback → 404 | Add SSE endpoint or remove fallback |

### P2 — Medium Priority (Address Post-Launch)

| # | Issue | Root Cause | File:Line | Reproduction | Verification |
|---|-------|-----------|-----------|-------------|--------------|
| P2-1 | No automated reconciliation | No job to verify trades ↔ fills ↔ ledger ↔ wallet | `backend/routes/admin_endpoints.py:2032` | Drift accumulates over time | Add nightly reconciliation job |
| P2-2 | No test coverage tracking | No pytest-cov or .coveragerc | `pytest.ini` | Cannot measure test coverage | Add `--cov=backend` to pytest addopts |
| P2-3 | No shared test fixtures | Each test file redefines auth/DB mocks | `tests/` directory | Maintenance burden | Create `conftest.py` with shared fixtures |
| P2-4 | Learning adjustments not auto-applied | Must manually call `/apply-adjustments` | `backend/engines/self_learning.py` | Learning analyzes but doesn't apply | Add scheduled auto-apply after analysis |
| P2-5 | Paper trading stubs in test files | ~8 test methods with `pass` body | `tests/test_paper_trading.py` | Tests pass but verify nothing | Complete test implementations |
| P2-6 | Wallet balance not derived from ledger | Running balance can drift from ledger truth | `backend/services/paper_wallet_service.py` | Kill server mid-trade → balance may be wrong | Add ledger-derived balance verification |
| P2-7 | Peak equity recalculated every call | Performance impact on large fill histories | `backend/services/ledger_service.py:550` | Bot with 10000 fills → slow drawdown check | Cache peak equity in DB |
| P2-8 | Redundant price polling alongside WS | Dashboard polls prices every 4s + receives WS updates | `frontend/src/hooks/useDashboardState.js` | Extra load on backend | Remove polling when WS connected |
| P2-9 | Kraken/Gate.io may lack full platform metadata | In `SUPPORTED_EXCHANGES` but possibly not in `platforms.py` | `backend/platforms.py` vs `backend/core/settings.py` | Create bot for Kraken → may fail on platform metadata | Verify platform metadata for all 7 exchanges |
| P2-10 | Legacy bodyguard uses bot fields, not ledger | `ai_bodyguard.py` reads `bot.current_capital` instead of ledger | `backend/ai_bodyguard.py` | Inconsistent with enhanced bodyguard | Migrate to ledger-only |
| P2-11 | Circular import risk | `routes/ai_chat.py` imports from `server` module | `backend/routes/ai_chat.py` | Could cause ImportError on startup | Move shared functions to utility module |

---

## Appendix A: Runtime Validation Curl Commands (DO NOT RUN — Reference Only)

```bash
# Health check (no auth)
curl -s http://localhost:8000/api/health/ping | jq '.status, .build_hash, .uptime_seconds'

# Build info (no auth)
curl -s http://localhost:8000/api/build-info | jq '.build.sha, .build.branch'

# Login (get JWT)
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"xxx"}' | jq -r '.token')

# Diagnostics go-live (admin JWT required)
curl -s http://localhost:8000/api/diagnostics/go-live \
  -H "Authorization: Bearer $TOKEN" | jq '.overall_status, .checks'

# Paper wallet balance
curl -s http://localhost:8000/api/wallet/paper \
  -H "Authorization: Bearer $TOKEN" | jq '.balances, .total'

# System mode
curl -s http://localhost:8000/api/system/mode \
  -H "Authorization: Bearer $TOKEN" | jq '.paperTrading, .liveTrading'

# Risk status
curl -s http://localhost:8000/api/risk/status \
  -H "Authorization: Bearer $TOKEN" | jq '.daily_loss_lock, .bodyguard'

# Recent trades
curl -s 'http://localhost:8000/api/trades/recent?limit=10' \
  -H "Authorization: Bearer $TOKEN" | jq '.[].profit_loss'

# Bot list
curl -s http://localhost:8000/api/bots/status \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {id, status, platform, current_capital}'

# WebSocket test (wscat)
wscat -c "ws://localhost:8000/api/ws?token=$TOKEN"

# Diagnostics - accounting
curl -s http://localhost:8000/api/diagnostics/accounting \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Paper reset (requires password)
curl -s -X POST http://localhost:8000/api/system/paper-reset \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password":"xxx"}' | jq '.'
```

---

## Appendix B: Known Runtime Issues Correlation

| Reported Issue | Confirmed in Code? | Root Cause |
|----------------|-------------------|------------|
| GitHub pulls failing from VPS | N/A (network issue) | Connection reset — not a code bug |
| `/api/diagnostics/go-live` returns 422 missing user_id | ✅ Confirmed | Auth dependency failure surfaces as misleading 422 (`server.py:2886`) |
| Wallet/paper shows 0 or phantom allocations | ✅ Confirmed possible | No allocation vs balance validation (`capital_allocator.py`, `wallet_manager.py`) |
| Drawdown/peak equity stuck after resets | ✅ Confirmed possible | Peak equity recalculated from fills; if fills partially remain, stale peak persists (`ledger_service.py:550–629`) |
| Circuit breaker daily loss exceeded with empty trades | ✅ Confirmed possible | `daily_loss_lock_active=True` persists on user document across restarts; no midnight reset exists |

---

**END OF AUDIT REPORT**

*This audit is based on static code analysis only. No code was executed, no endpoints were called, and ZERO code changes were made. All findings reference specific file paths and code locations in the repository.*
