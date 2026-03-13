# AMARKTAI CRYPTO FORENSIC AUDIT

**Date:** 2026-03-13
**Scope:** Full repository forensic audit — code truth only
**Repository:** amarktainetwork-blip/Amarktai-Crypto
**Auditor:** Automated deep-code inspection

---

## 1. Executive Summary

### Overall Repo Health: MODERATE — Production-grade backend with significant documentation debt and CI gaps

**Backend:** The backend is genuinely substantial — 382 Python files, 70 services, 56 engines, 61 route modules. The paper trading engine (3,139 lines), trading scheduler (904 lines), and autopilot engine (754 lines) are real, functional implementations — not stubs. The trading brain v2 subsystem (13 files) implements real economics-first gating with Kelly sizing, cost modeling, and feasibility checks.

**Frontend:** React 19 SPA with 33 dashboard sections, 60+ API endpoint integrations, and a 3-tier realtime fallback chain (WebSocket → SSE → HTTP polling). The frontend is genuinely wired to real backend data for most sections, with ~5% using fallback/placeholder data.

**Paper Trading:** Mechanically functional. The paper trading engine fetches real market prices, simulates realistic fees/slippage, enforces capital constraints, and records to an immutable ledger. Entry/exit economics use multi-gate validation. However, the system has never been proven via CI integration tests against a live database.

**Deployment Readiness:** NOT READY for clean deployment. CI runs only syntax checks and frontend build — zero pytest execution, zero integration tests, zero database validation. 209 markdown documentation files create conflicting "COMPLETE" and "READY" claims. Duplicate route files and legacy deployment configs remain.

---

## 2. Repo Truth Map

### Authoritative Files/Folders

| Path | Status | Role |
|------|--------|------|
| `backend/server.py` (3,282 lines) | **AUTHORITATIVE** | Main FastAPI app, inline routes, router mounting |
| `backend/paper_trading_engine.py` (3,139 lines) | **AUTHORITATIVE** | Paper trade execution engine |
| `backend/trading_scheduler.py` (904 lines) | **AUTHORITATIVE** | Bot scheduling/tick system |
| `backend/autopilot_engine.py` (754 lines) | **AUTHORITATIVE** | Autopilot growth/reinvest/promotion |
| `backend/database.py` (500+ lines) | **AUTHORITATIVE** | MongoDB connection, 55 collections |
| `backend/models.py` (402 lines) | **AUTHORITATIVE** | Pydantic data models |
| `backend/auth.py` | **AUTHORITATIVE** | JWT HS256 auth |
| `backend/services/` (70 files) | **AUTHORITATIVE** | Core service layer |
| `backend/engines/` (56 files) | **AUTHORITATIVE** | Trading/AI engines |
| `backend/routes/` (76 files) | **MIXED** — some stale/duplicate | API endpoints |
| `frontend/src/` | **AUTHORITATIVE** | React frontend |
| `ops/` | **AUTHORITATIVE** | Production deployment (nginx, systemd) |
| `.github/workflows/ci.yml` | **AUTHORITATIVE** | CI pipeline |

### Stale/Legacy/Duplicate Files

| Path | Issue |
|------|-------|
| `backend/routes/wallet_endpoints.py` (535 lines) | **DUPLICATE** of `wallet_hub.py` (793 lines). Both define `/api/wallet` routes. `wallet_hub.py` is canonical. |
| `backend/routes/wallet_transfers.py` (327 lines) | **SUPERSEDED** by `wallet_transfers_enhanced.py` (498 lines, state machine pattern) |
| `backend/routes/phase5_endpoints.py` (7,182 lines) | **LEGACY** — phase-based development checkpoint, unclear if still mounted |
| `backend/routes/phase6_endpoints.py` (5,471 lines) | **LEGACY** — same issue |
| `backend/routes/phase8_endpoints.py` (5,645 lines) | **LEGACY** — same issue |
| `deployment/` directory | **STALE** — `ops/` is production-canonical per `docs/REPO_TRUTH.md`. `deployment/systemd/amarktai-api.service` uses old repo paths. |
| `deployment/nginx/amarktai.conf` (12 lines) | **STALE** — `ops/nginx/amarktai.conf` (300+ lines) is production config |
| 209 markdown docs | **CONFLICTING** — 11+ files claim "COMPLETE" or "READY" with contradictory dates/statuses |
| `backend/_archive/` | **PROPERLY ARCHIVED** — not imported, not interfering |
| `docs/archive/` (200+ files) | **HEAVY DOCUMENTATION DEBT** — nested 4 levels deep |
| `AUDIT_REPORT.json` / `audit_report.json` | Only one JSON exists (lowercase). No damaging duplication. |

### Multiple Truths

1. **Wallet routes:** `wallet_endpoints.py` vs `wallet_hub.py` — both active, unclear precedence to newcomers
2. **Transfer routes:** `wallet_transfers.py` vs `wallet_transfers_enhanced.py` — both potentially mounted
3. **Deployment configs:** `deployment/` vs `ops/` — two competing deployment directories
4. **Documentation claims:** Multiple docs claim "COMPLETE" from different dates, some contradicting each other
5. **Requirements files:** `requirements.txt` (22 pkgs) vs `requirements.lock.txt` (60+ pkgs) — lock file includes `web3` not in main requirements

---

## 3. What Is Solid / Working Well

These assessments are based on actual code inspection, not documentation claims.

### Genuinely Solid Systems

1. **Paper Trading Engine** — Real market price fetching via CCXT, realistic fee simulation (exchange-specific rates), dynamic slippage modeling, 3% order failure rate, 50-200ms latency simulation. Uses 4-source AI signal consensus. Multi-gate entry validation (confidence, edge, spread, depth, profit floor, regime, concentration, risk). Priority-based exit management (TP → SL → trailing → V2 manager → time-decay → max-hold → stale).

2. **Trading Brain V2** — 13-file subsystem implementing real economics: `cost_model.py` (all-in round-trip costs with venue fees + slippage + adverse selection), `kelly_sizing.py` (quarter-Kelly with strategy-specific caps), `trade_feasibility_gate.py` (9-point hard gate), `regime_scorer.py`, `bot_contracts.py` (behavioral contracts with scalper re-entry cooldown).

3. **FX Normalizer** — Single canonical path for ZAR↔USDT conversion. `resolve_capital_for_exchange()` is the authoritative function. Rate priority: runtime cache → env var → fallback 19.0. Used consistently in bot creation, wallet display, and trade PnL.

4. **Paper Wallet System** — No-free-money model. Wallet starts empty, requires explicit funding. Per-bot capital tracking via `paper_wallet_ledger.py`. Cross-currency reserve (ZAR wallet → USDT bot ledger). Atomic MongoDB operations.

5. **Ledger Service** — Immutable append-only `fills_ledger`. FIFO-matched realized PnL. Equity = Starting Capital + Realized + Unrealized - Fees. Proper integrity verification.

6. **Bot Quarantine** — Progressive escalation: 60s → 3h → 24h → delete+regenerate. Non-strategy reasons excluded. Auto-regeneration preserves bot config.

7. **Authentication** — JWT HS256 with 24h expiry. Bcrypt password hashing. Fast-fail on unsafe JWT secrets. Email normalization to lowercase.

8. **Emergency Stop** — Instant halt of all active bots. Admin override capability (global + per-user). Proper audit trail.

9. **Daily Loss Lock** — UTC-day-keyed lock. Auto-reset at midnight via background job. Scheduler blocks all user bots while locked.

10. **Canonical Data Sources** — `canonical.py` provides single-source-of-truth functions for bot activity, wallet truth, trade counts, and open positions.

### Hidden Strengths

- **Trade Feasibility Gate** absolute profit floors are venue-aware and equity-bucket-aware (small/medium/large × ZAR/USDT × strategy). This prevents economically nonsensical trades.
- **Hold policy** caps paper-mode normal bots at 1200s (20 min) for fast validation cycles.
- **Scalper re-entry cooldown** (300s after weak exits) with early-allow on confidence improvement — prevents churn.
- **Route collision detection** at server startup prevents duplicate endpoint registration.

---

## 4. What Is Partially Working

### 4.1 Autopilot Engine
**What works:** Feature-gated startup, hourly reinvestment cycle, hourly evolution cycle, 7-day paper-to-live promotion check, 6-hour strategy optimization.
**What doesn't:** Promotion requires `ENABLE_LIVE_TRADING=true` which is `false` by default. Live trading path is untested. Reinvestment logic depends on positive profit which may rarely occur in early paper trading.
**Classification:** WORKING BUT INCOMPLETE

### 4.2 Learning Loop
**What works:** Nightly parameter tuning (1:30 UTC). Bounded adjustments (±10% max change). Rollback if PnL drops >10%. Stores results in 4 MongoDB collections.
**What doesn't:** No tests. No A/B testing framework. Adjustments are rule-based (not ML). The 5-trade minimum is low — could tune on noise. No scheduler integration visible — needs manual trigger or external cron.
**Classification:** PARTIALLY WORKING — real logic but unvalidated

### 4.3 Self-Healing Engine
**What works:** 30-minute monitoring loop. 4 detection rules (excessive loss >15%/hr, stuck bot >24hr, abnormal trading >50/day, capital anomaly). Auto-pause with WebSocket notification.
**What doesn't:** No tests for any detection rule. False positive guard only exists for 0-trade bots. No backtest of detection thresholds.
**Classification:** PARTIALLY WORKING — logic exists but untested

### 4.4 Bodyguard Service
**What works:** Win-aware drawdown protection (15-25% thresholds by risk mode). Requires 2 breach confirmations within 15 minutes. Never pauses profitable bots.
**What doesn't:** No automated tests. Threshold values not empirically validated.
**Classification:** WORKING BUT INCOMPLETE

### 4.5 WebSocket/SSE Realtime
**What works:** WebSocket endpoint at `/api/ws` with connection manager. SSE at `/api/realtime/events`. 3-tier fallback (WS → SSE → polling). Redis pub/sub support for multi-worker (optional).
**What doesn't:** No backpressure handling. Redis is optional (graceful degradation) but untested under load. No integration tests for concurrent broadcasts.
**Classification:** WORKING BUT INCOMPLETE

### 4.6 Exchange Support (non-Luno)
**What works:** All 7 exchanges configured in `exchange_config.py`. CCXT integration for price fetching and order simulation. Exchange-specific fee rates.
**What doesn't:** Binance/KuCoin/Bybit/Kraken/Bitget/Gate are configured but real API key testing depends on user-supplied credentials. No integration tests against any exchange sandbox.
**Classification:** WORKING BUT INCOMPLETE for paper; UNPROVEN for live

### 4.7 AI Chat
**What works:** User memory persistence, action logging (audit trail), 7-day trading summary, bot fuzzy matching, confirmation token system for dangerous actions.
**What doesn't:** The 112KB `ai_chat.py` file is enormous. Depends on `AISuperBrain()` class whose implementation wasn't fully audited. Real LLM integration (OpenAI/Gemini) requires API keys. Minimal test coverage (`test_ai_chat_missing_key.py` only).
**Classification:** PARTIALLY WORKING — framework exists, LLM integration unverified

---

## 5. What Is Broken

### 5.1 CI/CD Pipeline — BROKEN (Misleading)
**Problem:** The CI workflow (`ci.yml`) claims "GO-LIVE READY" on success, but it only validates:
- Python syntax compilation of 4 files
- Import of 3 route modules
- grep for 2 endpoint patterns
- Frontend npm build
- File existence checks

**Not validated:** Zero pytest execution. Zero integration tests. Zero database connectivity. Zero API contract tests against a running server (the "API Contract Tests" job only prints echo statements). The "Deployment Readiness" job checks for file existence only.

**Impact:** Bugs can ship to production undetected. The CI "GO-LIVE READY" message is misleading.
**Classification:** BROKEN — misleading pass/fail signal

### 5.2 CORS Configuration — BROKEN (Insecure)
**Problem:** `allow_origins=["*"]` in server.py CORS middleware. This allows any website to make authenticated requests to the API.
**Impact:** Cross-site request forgery risk for authenticated endpoints.
**Classification:** BROKEN — security vulnerability for production

### 5.3 WebSocket `/ws/decisions` — BROKEN (No Auth)
**Problem:** The `/ws/decisions` WebSocket endpoint in server.py appears to lack authentication, potentially exposing trading decision data.
**Classification:** BROKEN — potential information leak

---

## 6. What Is Missing

### Missing from Backend

1. **Pytest execution in CI** — 133 test files exist but are never run in CI
2. **Integration tests against MongoDB** — all tests use mocks
3. **Exchange sandbox testing** — no tests against exchange test environments
4. **Rate limiting middleware** — no request rate limiting on API endpoints
5. **Request size limits** — no documented max request body size
6. **CORS origin restriction** — currently allows all origins
7. **Health check database ping** — health endpoint doesn't verify DB connectivity
8. **Structured logging** — uses Python logging but no structured JSON format for log aggregation
9. **Backtesting completion** — `backtesting.py` has 18 TODOs

### Missing from Frontend

1. **API key setup workflow** — `ApiSetupSection.js` is 20 lines (stub)
2. **Performance section** — `PerformanceSection.js` is 9 lines (stub)
3. **Wallet Treasury section** — `WalletTreasurySection.js` is 19 lines (stub)
4. **Bot Operations section** — `BotOperationsSection.js` is 18 lines (minimal wrapper)
5. **Error boundary per section** — global ErrorBoundary exists but sections can crash each other
6. **Offline indicator** — no visual indication when realtime connection drops
7. **Loading skeletons** — some sections show "0" values during load rather than skeleton states
8. **FX rate display** — hardcoded 18.5 USD→ZAR in `MarketDataFallback.js` (stale)

### Missing from End-to-End Wiring

1. **Backtest results display** — backend endpoint exists, no frontend section
2. **Genetic algorithm results** — backend engine exists, frontend `HuggingFacePanel.js` partially wired
3. **Transfer state machine UI** — `wallet_transfers_enhanced.py` has state machine, frontend only shows basic transfers
4. **2FA setup flow** — backend `two_factor_auth.py` route exists, no frontend setup wizard
5. **Bot training/learning results display** — backend stores in 4 collections, frontend `learning/status` is fetch-only
6. **Email notification preferences** — backend has email service, no frontend preferences UI
7. **Daily report subscription** — backend has daily report scheduler, no frontend opt-in

---

## 7. Backend Audit by Subsystem

| Subsystem | File(s) | Classification | Evidence |
|-----------|---------|----------------|----------|
| **Auth** | `auth.py`, `routes/auth.py` | WORKING / SOLID | JWT HS256, bcrypt, fast-fail on unsafe secrets, email normalization |
| **User Management** | `routes/auth.py`, `routes/admin_endpoints.py` | WORKING / SOLID | Registration, profile, admin CRUD |
| **API Key Management** | `routes/keys.py` | WORKING / SOLID | Unified provider registry, encryption, per-exchange validation |
| **Paper Wallet** | `services/paper_wallet_service.py`, `paper_wallet_ledger.py` | WORKING / SOLID | No-free-money, multi-currency, atomic operations |
| **Bot CRUD** | `server.py` (inline), `routes/bot_lifecycle.py` | WORKING / SOLID | Create/update/delete, batch-create, validation |
| **Bot Runtime State** | `trading_scheduler.py`, `utils/bot_state.py` | WORKING / SOLID | 10s tick, staggered execution, diagnostic tracking |
| **Trading Scheduler** | `trading_scheduler.py` | WORKING / SOLID | 8 gate checks, quarantine integration, error handling |
| **Paper Trading Engine** | `paper_trading_engine.py` | WORKING / SOLID | Real prices, realistic simulation, multi-gate validation |
| **Live Trading Gate** | `routes/live_trading_gate.py` | WORKING BUT INCOMPLETE | 7-day validation, win rate check, but live path untested |
| **Ledger/Fills** | `services/ledger_service.py` | WORKING / SOLID | Immutable append-only, FIFO PnL, integrity verification |
| **Diagnostics** | `routes/diagnostics.py` (96KB) | WORKING BUT INCOMPLETE | Provider health real, whale/sentiment have graceful fallbacks |
| **Overview/Dashboard** | `services/overview_service.py`, `routes/dashboard_overview.py` | WORKING / SOLID | Snapshot endpoint, Luno ticker cache |
| **Portfolio Summary** | Ledger-derived | WORKING / SOLID | Entirely from fills_ledger, no separate collection |
| **Risk Management** | `routes/risk_management.py` | WORKING / SOLID | 9 endpoints, daily loss lock, bodyguard reset |
| **AI Bodyguard** | `services/bodyguard_service.py` | WORKING BUT INCOMPLETE | Real drawdown protection, win-aware, but no tests |
| **Daily Loss Lock** | `jobs/daily_loss_reset.py` | WORKING / SOLID | UTC-keyed, auto-reset at midnight, scheduler integration |
| **Emergency Stop** | `routes/emergency_stop_endpoints.py` | WORKING / SOLID | Instant halt, admin override, audit trail |
| **Bot Quarantine** | `services/bot_quarantine.py` | WORKING / SOLID | Progressive escalation, auto-regeneration |
| **Autopilot** | `autopilot_engine.py` | WORKING BUT INCOMPLETE | Feature-gated, real logic, but live path untested |
| **Learning Loop** | `services/learning_loop.py` | PARTIALLY WORKING | Real tuning logic, bounded, rollback — but no tests, no scheduler |
| **Self-Healing** | `engines/self_healing.py` | PARTIALLY WORKING | Real detection rules, auto-pause — but no tests |
| **AI Chat** | `routes/ai_chat.py` (114KB) | PARTIALLY WORKING | Framework exists, depends on LLM API keys |
| **WebSocket/Realtime** | `websocket_manager.py`, `routes/realtime.py` | WORKING BUT INCOMPLETE | 3-tier fallback, optional Redis — no load testing |
| **Balance Sync** | `services/balance_sync_service.py` | WORKING BUT INCOMPLETE | 5-min CCXT fetch, change detection — requires API keys |
| **Exchange Adapters** | `config/exchange_config.py`, CCXT | WORKING BUT INCOMPLETE | All 7 configured, paper simulation real — live unproven |
| **Market Data/Pricing** | `routes/market_api.py`, `luno_ticker_cache.py` | WORKING / SOLID | TTL cache with stale fallback, 429 handling |
| **Email/SMTP** | `engines/email_reporter.py`, `services/email_service.py` | WORKING BUT INCOMPLETE | Real implementation, but requires SMTP config |
| **Admin Panel** | `routes/admin_endpoints.py` (111KB) | WORKING / SOLID | User management, key monitoring, system stats |
| **Backtesting** | `routes/backtesting.py` | UNUSED / DEAD / STALE | 18 TODOs, incomplete implementation |
| **Genetic Algorithm** | `routes/genetic_algorithm.py`, `engines/genetic_optimizer.py` | CLAIMED BUT NOT PROVEN | Engine exists but no tests or proven execution path |
| **Sentiment Analyzer** | `engines/sentiment_analyzer.py` | PARTIALLY WORKING | Real code, but returns fallback when no external data |
| **On-Chain Monitor** | `engines/on_chain_monitor.py` | CLAIMED BUT NOT PROVEN | Engine exists, requires blockchain RPC access |

---

## 8. Frontend Audit by Section

| Section | File | Lines | UI Exists? | Wired to Live Data? | Backend Exists? | Classification |
|---------|------|-------|-----------|---------------------|----------------|----------------|
| **Landing/Auth** | `Landing.js`, `Login.js`, `Register.js` | ~300 | ✅ | ✅ JWT auth | ✅ | FULLY IMPLEMENTED |
| **Dashboard Layout** | `Dashboard.js` | 641 | ✅ | ✅ Nav + sections | ✅ | FULLY IMPLEMENTED |
| **Overview** | `OverviewSection.js` | 373 | ✅ | ✅ `/overview/snapshot` (4s) | ✅ | FULLY IMPLEMENTED |
| **AI Chat** | `AiChatSection.js` | 241 | ✅ | ✅ `/chat/message` | ✅ | PRESENT BUT PARTIAL — depends on LLM keys |
| **Bot Fleet** | `BotFleetSection.js` | 887 | ✅ | ✅ realtime bots_update | ✅ | FULLY IMPLEMENTED |
| **Bot Operations** | `BotOperationsCenter.js` | 167 | ✅ | ✅ via BotFleet state | ✅ | FULLY IMPLEMENTED |
| **Bot Management** | `BotManagementSection.js` | 228 | ✅ | ✅ pause/resume/restart | ✅ | FULLY IMPLEMENTED |
| **Bot Radar** | `BotRadarSection.js` | 323 | ✅ | ✅ bots state | ✅ | FULLY IMPLEMENTED |
| **Scalper Panel** | `ScalperBotsPanel.js` | 130 | ✅ | ✅ bots filtered | ✅ | FULLY IMPLEMENTED |
| **Growth Engine** | `GrowthEngineSection.js` | 492 | ✅ | ✅ `/autopilot/growth/status` | ✅ | PRESENT BUT PARTIAL — shows status, no active controls |
| **Profits** | `ProfitsSection.js` | 831 | ✅ | ✅ `/analytics/profit-history` etc | ✅ | FULLY IMPLEMENTED |
| **Live Trades** | `LiveTradesSection.js` | 412 | ✅ | ✅ `/trades/recent` + realtime | ✅ | FULLY IMPLEMENTED |
| **Countdown** | `CountdownSection.js` | 492 | ✅ | ✅ `/analytics/countdown-to-million` | ✅ | FULLY IMPLEMENTED |
| **Wallet Hub** | `WalletHubSection.js` | 25 | ✅ | ⚠️ Minimal wrapper | ✅ | PRESENT BUT PARTIAL |
| **Wallet Treasury** | `WalletTreasurySection.js` | 19 | ✅ | ⚠️ Stub | ✅ | PRESENT BUT MISLEADING |
| **System Mode** | `SystemModeSection.js` | 154 | ✅ | ✅ `/system/mode` | ✅ | FULLY IMPLEMENTED |
| **Profile** | `ProfileSection.js` | 100 | ✅ | ✅ `/auth/me` | ✅ | FULLY IMPLEMENTED |
| **Admin Panel** | `AdminPanelSection.js` | 1,123 | ✅ | ✅ `/admin/*` endpoints | ✅ | FULLY IMPLEMENTED |
| **Admin Truth Console** | `TruthConsoleSection.js` | 450 | ✅ | ✅ `/admin/truth/*` | ✅ | FULLY IMPLEMENTED |
| **Intelligence Panels** | `DashboardIntelligencePanels.js` | 430 | ✅ | ⚠️ Partial — fallbacks | ✅ | PRESENT BUT PARTIAL |
| **Market Intelligence** | `MarketIntelligencePanel.js` | 289 | ✅ | ✅ `/diagnostics/regime-summary` | ✅ | PRESENT BUT PARTIAL — data depends on running engine |
| **CoinStats** | `CoinStatsPanel.js` | 189 | ✅ | ✅ `/market/prices` | ✅ | FULLY IMPLEMENTED |
| **HuggingFace** | `HuggingFacePanel.js` | 202 | ✅ | ⚠️ `/diagnostics/genetics-summary` | ⚠️ | PRESENT BUT PARTIAL |
| **Exchange Status** | `ExchangeStatusSection.js` | 94 | ✅ | ⚠️ From bot state | ✅ | PRESENT BUT PARTIAL |
| **API Setup** | `ApiSetupSection.js` | 20 | ✅ | ❌ Stub | ✅ | FRONTEND EXISTS BUT BACKEND NOT WIRED |
| **Performance** | `PerformanceSection.js` | 9 | ✅ | ❌ Stub | ✅ | FRONTEND EXISTS BUT NOT IMPLEMENTED |
| **Trading Monitor** | `TradingMonitorSection.js` | 47 | ✅ | ⚠️ Minimal | ✅ | PRESENT BUT PARTIAL |
| **Welcome** | `WelcomeSection.js` | 56 | ✅ | ✅ Static | N/A | FULLY IMPLEMENTED |
| **Metrics Tabs** | `MetricsWithTabsSection.js` | 83 | ✅ | ⚠️ Wrapper | ✅ | PRESENT BUT PARTIAL |
| **2FA Setup** | N/A | 0 | ❌ | N/A | ✅ `routes/two_factor_auth.py` | BACKEND EXISTS BUT FRONTEND MISSING |
| **Backtest Results** | N/A | 0 | ❌ | N/A | ⚠️ Incomplete backend | MISSING |
| **Email Preferences** | N/A | 0 | ❌ | N/A | ✅ Email service exists | BACKEND EXISTS BUT FRONTEND MISSING |

---

## 9. Trading Engine Truth Audit

### Mechanical Truth (Does it execute?)
**VERDICT: YES — mechanically functional**

- Scheduler ticks every 10 seconds, staggering bot execution
- Paper trading engine fetches real prices via CCXT public endpoints
- Entry decisions pass through 9+ gates (confidence, edge, cost-to-edge ratio, spread, depth, absolute profit floor, regime, concentration, risk)
- Exit management uses priority chain: TP → SL → trailing → V2 manager → time-decay → max-hold → stale
- Fills are recorded to immutable ledger
- Paper wallet is debited/credited atomically
- Bot capital is updated post-trade

### Economic Truth (Does it make sound decisions?)
**VERDICT: MOSTLY SOUND — with caveats**

**Sound:**
- All-in cost modeling (fees + slippage + spread + adverse selection) before entry
- Quarter-Kelly position sizing with strategy-specific caps
- Cost-to-edge ratio cap at 55% — won't enter if costs eat most of edge
- Exchange-specific fee rates (not generic)
- Absolute profit floors prevent economically nonsensical trades

**Caveats:**
- AI signal sources (regime HMM/GMM, ML predictor, CoinStats, Fetch.ai) need real data. Cold-start produces regime=unknown, confidence=0. Fallback values (trend=2.0%, vol=2.5%) prevent deadlock but may not be economically meaningful.
- Paper edge floor of 100 BPS is artificially high — may block many real opportunities
- Notional cap removed in paper mode (paper_capital × 1.0 instead of × 0.10) — paper trades can use full capital, making paper results non-representative of live behavior with 10% notional cap
- Slippage heuristic (5.0 bps base) is reasonable but not validated against actual exchange data

### Paper-Go-Live Truth
**VERDICT: NOT READY — key gaps remain**

1. No CI test execution — can't verify nothing is broken before deploying
2. No integration test against real MongoDB
3. No proven end-to-end flow (bot creation → trade → close → PnL) in automated testing
4. Paper-mode notional cap difference (100% vs 10%) means paper results overstate live performance
5. FX rate fallback (19.0) could drift significantly from actual USDT/ZAR rate
6. No monitoring/alerting for scheduler failures

### Live-Go-Live Truth
**VERDICT: NOT READY — significant blockers**

1. All paper-go-live blockers plus:
2. Live trading gated by `ENABLE_LIVE_TRADING=false` (correct safety) but live execution path never tested
3. Live order execution (`trading_engine_live.py`) exists but is a thin wrapper
4. No exchange sandbox integration tests
5. No withdrawal/deposit flow testing
6. CORS `allow_origins=["*"]` is a production security risk
7. No rate limiting on API endpoints

---

## 10. Wallet / Ledger / Portfolio Truth Audit

### Real Sources of Truth

| Domain | Source | Collection | Authoritative? |
|--------|--------|-----------|----------------|
| User wallet balance | `paper_wallet_service.py` | `wallets_collection` | ✅ YES |
| Per-bot capital | `paper_wallet_ledger.py` | `paper_ledger_collection` | ✅ YES |
| Trade fills | `ledger_service.py` | `fills_ledger` | ✅ YES (immutable) |
| Realized PnL | `ledger_service.py` (FIFO) | Derived from `fills_ledger` | ✅ YES |
| Unrealized PnL | `ledger_service.py` | Derived (needs live price) | ⚠️ DEPENDS on price feed |
| Portfolio summary | `/portfolio/summary` endpoint | Derived from ledger | ✅ YES |
| Bot equity | `ledger_service.compute_equity()` | Derived from ledger | ✅ YES |

### Mismatches and Concerns

1. **Multiple financial collections:** `wallets_collection`, `paper_ledger_collection`, `fills_ledger`, `ledger_collection`, `profits_collection`, `profit_ledger_collection`, `capital_injections_collection`. Some may be legacy/unused but their existence creates confusion.

2. **ZAR display conversion:** `fx_normalizer.to_display_zar()` uses runtime cache → env var → fallback 19.0. The fallback is reasonable but stale over time. Frontend `MarketDataFallback.js` hardcodes 18.5 — different from backend's 19.0.

3. **Canonical wallet truth** (`canonical.py:get_canonical_wallet_truth`) sums available + allocated ZAR. This is the authoritative function but requires `paper_wallet_ledger` to be in sync with actual bot states.

4. **Dashboard total display** uses `/overview/snapshot` which calls `overview_service.py`. This is separate from `/portfolio/summary` — two different aggregation paths that should agree but could diverge.

### Unreliable Surfaces

- **Frontend hardcoded FX rate** (18.5) in `MarketDataFallback.js` — used when backend is unavailable
- **Multiple profit collections** (`profits_collection`, `profit_ledger_collection`) — unclear which is authoritative
- **`wallet_balances_collection`** vs `wallets_collection` — naming suggests overlap

---

## 11. Multi-Exchange Support Audit

| Exchange | Configured | Paper Price Fetch | Paper Order Sim | Live Order | Wallet/Funding | Pair Resolution | Diagnostics | Frontend Visibility | Verdict |
|----------|-----------|-------------------|-----------------|-----------|----------------|-----------------|-------------|--------------------|---------| 
| **Luno** | ✅ | ✅ Public + ticker cache | ✅ Realistic | ⚠️ Code exists, untested | ✅ ZAR native | ✅ BTC/ZAR, ETH/ZAR, XRP/ZAR | ✅ | ✅ | **TRULY USABLE (paper)** |
| **Binance** | ✅ | ✅ CCXT public | ✅ Realistic | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |
| **KuCoin** | ✅ | ✅ CCXT public | ✅ Realistic | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |
| **Bybit** | ✅ | ✅ CCXT public | ✅ Realistic | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |
| **Kraken** | ✅ | ✅ CCXT public | ✅ Realistic (higher fees: 0.16/0.26%) | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |
| **Bitget** | ✅ | ✅ CCXT public | ✅ Realistic | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |
| **Gate.io** | ✅ | ✅ CCXT public | ✅ Realistic (higher fees: 0.20/0.20%) | ⚠️ Code exists, untested | ✅ USDT via FX | ✅ BTC/USDT, ETH/USDT | ✅ | ✅ | **TRULY USABLE (paper)** |

**Summary:** All 7 exchanges are truly usable for paper trading with real public price data. Live trading code exists but is unproven. Each exchange has correct fee rates, proper CCXT configuration, and consistent capital handling via `fx_normalizer`.

---

## 12. Realtime / Sync Audit

| Feature | Mechanism | Classification |
|---------|-----------|----------------|
| **Live prices** | Polling 4s + realtime `prices_update` event | Pseudo-realtime (4s polling with WS overlay) |
| **Bot status updates** | Realtime `bots_update` event | Genuinely realtime |
| **Trade execution notifications** | Realtime `trade_executed` etc | Genuinely realtime |
| **Overview metrics** | Polling 4s + realtime `overview_update` | Pseudo-realtime |
| **System mode** | Polling 4s | Polling only |
| **Countdown** | Polling 4s | Polling only — aggressive for slowly-changing data |
| **Wallet balances** | Polling 15s (fallback) | Polling only |
| **Dashboard analytics** | On-demand fetch | Not realtime |
| **Risk status** | On-demand | Not realtime |
| **AI chat** | WebSocket messages | Genuinely realtime |

**Key Finding:** The system claims realtime but many critical surfaces (prices, overview, mode) are actually 4-second polling with optional WebSocket overlay. True WebSocket-first delivery exists for bot updates, trade notifications, and chat. The 4-second polling for slowly-changing data (countdown, system mode) is unnecessarily aggressive and could stress the server.

---

## 13. AI / Autopilot / Learning / Bodyguard Audit

| System | Claim | Reality | Assessment |
|--------|-------|---------|------------|
| **Autopilot** | Autonomous bot management | Feature-gated real implementation with hourly cycles. Reinvestment, evolution, promotion logic exists. | **Partially real — live path untested** |
| **Growth/Spawn** | Auto-spawn new bots | Logic exists in `autopilot_engine.py`. Spawns via `bot_spawner.py`. | **Partially real — gated by feature flag** |
| **Reinvestment** | Auto-reinvest profits | `daily_reinvestment.py` and `autopilot_reinvest.py` exist with real logic. | **Partially real — requires positive PnL** |
| **Promotion** | Paper → Live promotion | 7-day validation with win rate/profit checks in `promotion_engine.py`. | **Real but blocked — ENABLE_LIVE_TRADING=false** |
| **Learning Loop** | Self-learning parameter tuning | Nightly 1:30 UTC run, ±10% bounded adjustments, rollback mechanism. | **Real logic, no tests, rule-based not ML** |
| **AI Bodyguard** | Drawdown protection | Win-aware, 2-confirmation, progressive thresholds. | **Real and solid — no tests though** |
| **Emergency Stop** | Instant halt | Immediate bot pause, admin override, audit trail. | **Real and solid** |
| **Daily Loss Lock** | Daily loss protection | UTC-keyed, auto-reset, scheduler blocking. | **Real and solid** |
| **Self-Healing** | Rogue bot detection | 4 detection rules, 30-min scan, auto-pause. | **Real logic, no tests** |
| **AI Chat** | Natural language trading commands | Framework with memory, audit trail, confirmation tokens. | **Framework exists — LLM integration unverified** |
| **Market Intelligence** | 4-source AI consensus | Regime HMM/GMM, ML predictor, CoinStats, Fetch.ai. | **Real code — depends on data feeds/API keys** |
| **Sentiment Analysis** | News/social sentiment | `sentiment_analyzer.py` exists (13,881 lines). | **Real code — returns fallback without external data** |

**Honest Assessment:** The AI/autonomous systems are NOT marketing smoke. They contain real implementation logic with bounded parameters and safety mechanisms. However, they are also NOT proven to work end-to-end. The learning loop has no tests. The bodyguard has no tests. Self-healing has no tests. The "AI" in AI chat depends on external LLM APIs. The market intelligence depends on external data feeds. None of these have been validated in CI.

---

## 14. Frontend vs Backend Gap List

### A. Backend Exists, Frontend Missing
1. **2FA management** — `routes/two_factor_auth.py` exists, no frontend setup wizard
2. **Email notification preferences** — email services exist, no frontend opt-in UI
3. **Daily report subscription** — `routes/daily_report.py` exists, no frontend subscription
4. **Backtest execution** — `POST /backtest/strategy` exists, no results display
5. **Order management** — `routes/order_endpoints.py` exists, limited frontend integration
6. **Transfer state machine** — enhanced transfer state machine in backend, basic UI only
7. **Learning job trigger** — `routes/learning_jobs.py` exists, no manual trigger in frontend

### B. Frontend Exists, Backend Missing
1. None identified — all frontend sections have corresponding backend endpoints

### C. Both Exist, Wiring Incomplete
1. **API Setup** — Backend key management is solid, frontend `ApiSetupSection.js` is a 20-line stub
2. **Wallet Hub** — Backend `wallet_hub.py` is comprehensive (793 lines), frontend is a 25-line wrapper
3. **Wallet Treasury** — Backend has wallet data, frontend is a 19-line stub
4. **Performance section** — Backend has analytics endpoints, frontend is a 9-line stub
5. **Intelligence panels** — Backend has diagnostics, frontend shows data but many fallback to defaults
6. **HuggingFace genetics** — Backend has genetics summary endpoint, frontend partially displays

### D. Both Exist, Truth Semantics Differ
1. **FX Rate** — Backend fallback: 19.0 ZAR/USD. Frontend fallback: 18.5 ZAR/USD (MarketDataFallback.js)
2. **Overview vs Portfolio** — Two aggregation paths (`/overview/snapshot` vs `/portfolio/summary`) that should agree

### E. Duplicate Features
1. **Wallet endpoints** — `wallet_endpoints.py` + `wallet_hub.py` both serve `/api/wallet`
2. **Transfer endpoints** — `wallet_transfers.py` + `wallet_transfers_enhanced.py`
3. **Admin endpoints** — `admin_endpoints.py` + `admin_enhanced.py` (supplementary, not true duplicate)

### F. Features Shown That Should Not Be Shown Yet
1. **Live trading toggle** in System Mode section — backend gate prevents activation, but UI shows the option
2. **Autopilot controls** — shown in Growth Engine section even when all autopilot features are disabled
3. **Intelligence panels** — show "Unavailable" fallback data that could confuse users into thinking system is broken

---

## 15. Stale / Duplicate / Legacy Truths To Clean Up

### File-Level Cleanup

| Item | Action Needed |
|------|--------------|
| `backend/routes/wallet_endpoints.py` | Remove or explicitly mark as deprecated — superseded by `wallet_hub.py` |
| `backend/routes/wallet_transfers.py` | Remove or explicitly mark — superseded by `wallet_transfers_enhanced.py` |
| `backend/routes/phase5_endpoints.py` | Verify if mounted; if not, archive |
| `backend/routes/phase6_endpoints.py` | Verify if mounted; if not, archive |
| `backend/routes/phase8_endpoints.py` | Verify if mounted; if not, archive |
| `deployment/` directory | Archive or remove — `ops/` is canonical |
| `deployment/systemd/amarktai-api.service` | Uses stale paths — remove |
| `frontend/src/lib/MarketDataFallback.js` hardcoded 18.5 | Should use dynamic FX or match backend's 19.0 |
| 11+ docs claiming "COMPLETE" | Consolidate into one authoritative status doc |
| `docs/archive/` (200+ files in 4 levels) | Flatten or remove unnecessary nesting |
| Root-level audit/forensic markdown files (8+) | Archive all but the latest |
| `backend/requirements.lock.txt` including `web3` | Verify if web3 is actually used; if not, remove from lock file |
| Multiple financial collections (profits, profit_ledger, ledger, capital_injections) | Audit usage and consolidate or clearly document which is authoritative |

### System-Level Cleanup

1. **Server.py inline routes** — 2,600+ lines of inline route handlers in `server.py` should be extracted to route modules for maintainability
2. **76 mounted routers** — review which are actually needed; some may be legacy
3. **55 MongoDB collections** — audit which are actively used vs legacy
4. **CI "GO-LIVE READY" claim** — remove or gate behind actual test execution

---

## 16. Paper Go-Live Blockers

These must be resolved before paper trading can be considered reliably operational:

1. **CI must run pytest** — at minimum, syntax + import + unit tests for core trading logic
2. **FX rate disagreement** — backend 19.0 vs frontend 18.5 must be unified
3. **Duplicate wallet routes** — must have single canonical wallet route module
4. **Overview vs Portfolio divergence risk** — must verify both aggregation paths agree or consolidate
5. **Frontend stubs must be honest** — `ApiSetupSection` (20 lines), `PerformanceSection` (9 lines), `WalletTreasurySection` (19 lines) should show "Coming Soon" not pretend to function
6. **Paper-mode notional cap transparency** — if paper mode uses 100% capital but live will use 10%, this must be documented/displayed to users
7. **Cold-start regime fallback validation** — verify fallback trend=2.0%/vol=2.5% produces reasonable trading behavior, not just "not deadlocked"
8. **CORS restriction** — change from `allow_origins=["*"]` to specific allowed origins before any deployment with real users
9. **At least one proven e2e test** — bot creation → trade entry → trade close → PnL recorded → wallet updated

---

## 17. Live Go-Live Blockers

All paper go-live blockers plus:

1. **Live trading execution path must be tested** — `trading_engine_live.py` is a thin wrapper with no integration tests
2. **Exchange sandbox testing** — at least one exchange (Luno or Binance) tested against sandbox/testnet API
3. **Rate limiting** — must be implemented on all API endpoints
4. **Request signing for sensitive operations** — emergency stop, live mode activation, fund transfers
5. **CORS must be restricted** to production domain only
6. **WebSocket auth on `/ws/decisions`** — must require authentication
7. **Withdrawal/deposit flow testing** — transfer state machine must be proven end-to-end
8. **Monitoring/alerting** — scheduler failures, trading engine errors, database connectivity must have alerts
9. **Bodyguard + self-healing tests** — protection systems must be proven before real money
10. **Learning loop validation** — must prove parameter adjustments improve or at least don't degrade performance
11. **User data backup strategy** — no backup/restore procedure validated
12. **FX rate must be live** — cannot rely on env var or fallback for real-money currency conversion
13. **Audit logging completeness** — verify all financial operations have audit trail

---

## 18. Deployment Readiness Verdict

### **NOT READY**

**Justification:**

1. **CI is misleading.** The pipeline claims "GO-LIVE READY" but runs zero functional tests. 133 test files exist but none execute in CI. This means any code change could break core functionality without detection.

2. **Documentation creates false confidence.** 11+ documents claim "COMPLETE" or "READY" from various dates. The repo has no single authoritative status document. New team members cannot determine what actually works.

3. **Duplicate route files create maintenance risk.** `wallet_endpoints.py` vs `wallet_hub.py` and `wallet_transfers.py` vs `wallet_transfers_enhanced.py` could cause confusion or accidental regression.

4. **Security issues exist.** CORS `allow_origins=["*"]`, potentially unauthenticated WebSocket endpoint, no rate limiting.

5. **Frontend stubs pretend to be features.** Three dashboard sections (ApiSetup, Performance, WalletTreasury) are single-digit-line stubs that could mislead users.

6. **FX rate inconsistency.** Backend uses 19.0, frontend uses 18.5 as fallback — could cause displayed values to disagree.

The repository is surprisingly close to "READY FOR LIMITED PAPER VALIDATION" — the core trading mechanics are genuinely solid. But the CI gaps, documentation debt, and security issues prevent recommending deployment.

---

## 19. Recommended Cleanup / Repair Order

**IMPORTANT: This is NOT code. This is only the recommended order of workstreams.**

1. **Fix CI to run actual tests** — add pytest execution for at least core trading, wallet, and ledger tests. Remove the "GO-LIVE READY" claim until tests pass.

2. **Unify FX rate fallback** — frontend MarketDataFallback.js must match backend fx_normalizer.py fallback value (or both must use a dynamic source).

3. **Remove or archive duplicate route files** — designate `wallet_hub.py` as canonical wallet routes, archive `wallet_endpoints.py`. Designate `wallet_transfers_enhanced.py` as canonical, archive `wallet_transfers.py`. Verify and archive phase*_endpoints.py if not mounted.

4. **Restrict CORS** — change `allow_origins=["*"]` to specific allowed origins.

5. **Secure WebSocket endpoints** — ensure `/ws/decisions` requires authentication.

6. **Consolidate documentation** — create one `STATUS.md` that is the single authoritative status document. Archive all "COMPLETE"/"READY" docs to `docs/archive/`.

7. **Fix frontend stubs** — `ApiSetupSection`, `PerformanceSection`, `WalletTreasurySection` should either be implemented or show "Coming Soon" with proper messaging.

8. **Archive `deployment/` directory** — `ops/` is canonical per existing documentation.

9. **Add integration test for e2e paper trading flow** — bot creation → wallet funding → trade entry → trade close → PnL in ledger → wallet updated.

10. **Add tests for protection systems** — bodyguard, self-healing, daily loss lock, quarantine.

11. **Add rate limiting middleware** — protect API endpoints from abuse.

12. **Validate learning loop** — add tests proving parameter adjustments are bounded and rollback works.

13. **Audit MongoDB collections** — determine which of the 55 collections are actively used vs legacy.

14. **Add monitoring/alerting** — scheduler health, trading engine errors, database connectivity.

15. **Test live trading path** — when ready, test `trading_engine_live.py` against exchange sandbox/testnet.

---

*End of Forensic Audit*
*This document reflects code truth as of 2026-03-13. No code was changed during this audit.*
