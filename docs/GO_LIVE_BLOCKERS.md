# Go-Live Blockers & Incomplete Requirements

> Generated: 2026-03-01 | Branch: copilot/upgrade-amarktai-network-again
> Status: **NOT READY FOR LIVE** — Paper mode operational, live mode gated by training + funding checks

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 P0 | **BLOCKER** — Must fix before ANY live trading |
| 🟡 P1 | **Required** — Must fix before production deployment |
| 🟢 P2 | **Recommended** — Should fix but not blocking |
| ✅ | Implemented and tested |

---

## 1. BLOCKERS (P0) — Must Fix Before Live Trading

### 🔴 1.1 Paper Test Harness Script Missing
- **File needed:** `scripts/paper_harness.sh` (or `.py`)
- **What it should do:** Create 1 normal + 1 scalper bot in paper mode, run controlled tick stream for 60-120s, force decision → order → fill, verify diagnostics/paper-status, ledger fills, radar snapshot, wallet balances
- **Why it blocks:** Without a deterministic paper test harness, there is no automated way to prove end-to-end trading works before going live. Manual testing is insufficient for a trading system.
- **Evidence requirement:** The harness must produce a JSON report in `/docs/evidence/`

### 🔴 1.2 Scalper Bots Do Not Actually Trade Yet
- **Current state:** Scalper bot models, caps, EV gating, and dashboard UI are implemented. The **scheduler** and **decision engine** do not yet differentiate between normal and scalper bots for trade execution.
- **What's missing:**
  - Scalper-specific decision logic (short horizon, EV gate enforcement before every trade)
  - Scalper-specific forced exit enforcement in the execution loop (TIME_EXIT, STAGNATION_EXIT)
  - Scalper trade lifecycle integration with the existing paper trading engine
  - Scalper scheduler counters (separate from normal bot counters)
- **Why it blocks:** Creating a scalper bot through the UI produces a record in the DB, but no trades will execute with scalper-specific behavior (max hold, stagnation exit, EV gating).

### 🔴 1.3 Training Gate Does Not Differentiate Bot Types
- **File:** `backend/routes/training.py`
- **Current state:** Training criteria (MIN_TRADES=20, MIN_RUNTIME_HOURS=6, MAX_DRAWDOWN=25%) are generic and apply identically to all bots. No `bot_type` awareness.
- **What's missing:**
  - Configurable training criteria per bot type (scalpers may need different thresholds — e.g., MIN_TRADES=50, MIN_RUNTIME_HOURS=2 for high-frequency)
  - Training evaluation function should check `bot_type` field
  - Training UI should show normal AND scalper training queues separately
- **Why it blocks:** Scalper bots would train under normal bot criteria, which may not be appropriate for short-horizon trading.

### 🔴 1.4 Live Funding Readiness Check Not Implemented
- **Current state:** `services/funding_router.py` supports `is_paper=True/False` parameter, but no endpoint checks whether real Luno wallet has sufficient ZAR to fund live operations.
- **What's missing:**
  - Endpoint or check: "Does user have enough real ZAR on Luno to fund USDT for exchange X?"
  - If insufficient → keep bot in paper with reason code `INSUFFICIENT_LIVE_FUNDS`
  - This check must be part of the paper→live promotion gate
- **Why it blocks:** A bot could be promoted to live trading without verified real funding, leading to failed orders.

---

## 2. REQUIRED (P1) — Must Fix Before Production Deployment

### 🟡 2.1 LiveTradesSection Missing bot_type Filter + Exit Reason Codes
- **File:** `frontend/src/pages/dashboard/sections/LiveTradesSection.js`
- **Current state:** Filters by exchange, bot name, pair. No `bot_type` filter. Exit reason codes (TIME_EXIT, STAGNATION_EXIT, etc.) are not displayed.
- **Fix:** Add a normal/scalper filter toggle and display `trade_close_reason` field prominently.

### 🟡 2.2 OverviewSection Does Not Show Normal vs Scalper Breakdown
- **File:** `frontend/src/pages/dashboard/sections/OverviewSection.js`
- **Current state:** Shows unified metrics (Total Profit, Today Profit, Trades, Win Rate). No separation by bot type.
- **Fix:** Add split tiles: Normal PnL vs Scalper PnL, Normal bots vs Scalper bots, or a toggle.

### 🟡 2.3 WalletHub Does Not Show Per-Program Allocation
- **File:** `frontend/src/pages/dashboard/sections/WalletHubSection.js`
- **Current state:** Shows ZAR + USDT balances. No breakdown of NORMAL allocated/reserved vs SCALPER allocated/reserved.
- **Fix:** Backend should return per-program wallet allocation; frontend should display it.

### 🟡 2.4 Realtime Radar Channel Not Implemented (WS/SSE)
- **Current state:** Radar data is available via REST `GET /api/radar/snapshot` (polled every 10s by frontend). No WebSocket/SSE channel for real-time radar updates.
- **What's missing:** A WS/SSE "radar" channel broadcasting: price ticks, position open/close, TP/SL updates, forced exit events.
- **Impact:** Dashboard radar view has 10s latency instead of real-time updates. Acceptable for paper, not ideal for live scalping.

### 🟡 2.5 Wallet Reconciliation Across Endpoints
- **Affected endpoints:** `/api/wallet/paper`, `/api/system/status`, `/api/diagnostics/data-integrity`, `/api/radar/snapshot`
- **Current state:** These endpoints may compute wallet values independently. The Truth Kernel computes canonical values, but not all endpoints read from it yet.
- **Fix:** All wallet-related endpoints should read from Truth Kernel `compute_wallet_balances()` output.

### 🟡 2.6 Bot Status Disagreement (bots/status vs per-bot /status)
- **Reported issue:** `bots/status` can disagree with per-bot `/status` (paused vs active; lifecycle/paper_training split).
- **Current state:** `normalize_bot_state()` in `utils/bot_state.py` resolves many discrepancies, but the root cause (multiple status sources) persists.
- **Fix:** Per-bot status should be derived from a single canonical source (Truth Kernel bot_eligibility).

### 🟡 2.7 diagnostics/paper-status Shows active_bots=0
- **Reported issue:** Even with bots created, `diagnostics/paper-status` shows `active_bots=0` and no decisions/orders/fills.
- **Root cause:** The paper trading engine scheduler may not be running, or the diagnostics endpoint queries different collections.
- **Fix:** Paper-status should use Truth Kernel bot counts; scheduler must be running for paper bots to produce fills.

---

## 3. RECOMMENDED (P2) — Should Fix But Not Blocking

### 🟢 3.1 Scalper Profit Routing Ledger Integration
- **Current state:** `profit_routing` field exists on Bot model. `/api/scalper/routing` can set the mode. But no actual profit routing logic executes on fill.
- **What's missing:** When a scalper bot realizes profit:
  - If SCALPER_GROWTH: check if new scalper can be spawned (within caps) and fund it
  - If RETURN_TO_MAIN: transfer profit to main wallet pool via ledger entry
- **Impact:** Profit routing mode is stored but not acted upon.

### 🟢 3.2 Correlation Awareness / Portfolio Brain
- **Current state:** No correlation guardrail exists. Multiple bots can hold overlapping positions.
- **What's missing:** Exposure caps per coin, per exchange, per side. Correlation detection.
- **Impact:** Risk of concentrated exposure. Not critical for paper mode.

### 🟢 3.3 Controlled Learning + A/B Harness
- **Current state:** Learning engine exists (`routes/learning_jobs.py`) but no bounded parameter adjustments, rollback on degradation, or A/B testing.
- **Impact:** Learning can make unbounded changes. Low priority for initial go-live.

### 🟢 3.4 Safe Mode Automation
- **Current state:** Self-healing detection exists (`engines/self_healing.py`), circuit breaker exists. But no automated: "if scheduler stalls → restart once → else pause trading."
- **Impact:** Requires manual intervention for certain failure modes.

### 🟢 3.5 Decision Trace Panel / Exposure Map / Growth Plan
- **Current state:** Decision trace endpoint exists (`routes/decision_trace.py`). No dedicated Exposure Map or Growth Plan dashboard sections.
- **Impact:** Operator transparency is reduced but functional data is available via existing endpoints.

### 🟢 3.6 Phase 3 Visual Redesign
- **Current state:** Dashboard is functional with all sections. No premium "cyber crypto" redesign.
- **Impact:** Purely cosmetic. Not blocking functionality.

### 🟢 3.7 UI Smoke Tests (Playwright)
- **Current state:** No Playwright or equivalent UI smoke tests exist.
- **Impact:** Frontend changes cannot be automatically verified for regressions.

---

## 4. WHAT IS COMPLETE ✅

| Feature | Status | Files |
|---------|--------|-------|
| Truth Kernel (14 subsystems) | ✅ | `services/truth_kernel.py` |
| Contradiction Detector (8 checks) | ✅ | `services/contradiction_detector.py` |
| Admin Truth Console (backend) | ✅ | `routes/admin_truth.py` |
| Admin Truth Console (frontend) | ✅ | `TruthConsoleSection.js` |
| Go-live uses Truth Kernel | ✅ | `server.py` (go-live endpoint) |
| AI Chat "truth check" | ✅ | `routes/ai_chat.py` |
| AI Chat scalper commands (5) | ✅ | `routes/ai_chat.py` |
| BotType + ScalperProfitRouting enums | ✅ | `models.py` |
| Bot/BotCreate include bot_type | ✅ | `models.py` |
| Scalper exchange caps | ✅ | `exchange_limits.py` |
| EV gating function | ✅ | `exchange_limits.py` |
| Exit reason codes (6) | ✅ | `exchange_limits.py` |
| Scalper throttle constants | ✅ | `exchange_limits.py` |
| Scalper router (4 endpoints) | ✅ | `routes/scalper.py` |
| Bot Radar with bot_type filter | ✅ | `routes/radar.py`, `BotRadarSection.js` |
| ScalperBotsPanel UI | ✅ | `ScalperBotsPanel.js` |
| BotManagement Scalper tab | ✅ | `BotManagementSection.js` |
| Scalper panel CSS | ✅ | `scalper-panel.css` |
| Funding Router (ZAR→USDT) | ✅ | `services/funding_router.py` |
| Training gate (generic) | ✅ | `routes/training.py` |
| Evidence pack (18 endpoints) | ✅ | `scripts/evidence_pack.sh` |
| Rule precedence (8 levels) | ✅ | `services/truth_kernel.py` |
| 101 tests passing | ✅ | `tests/test_truth_kernel.py` + others |
| Frontend builds | ✅ | Verified with `npm run build` |

---

## 5. RECOMMENDED GO-LIVE SEQUENCE

1. **Paper Mode Only (SAFE NOW):**
   - Deploy current state
   - All bots start in paper mode
   - Training gate prevents live promotion
   - Run `scripts/evidence_pack.sh` to collect baseline evidence
   - Monitor via Truth Console + AI Chat "truth check"

2. **Before Enabling Live Trading:**
   - Fix P0 blockers (1.1–1.4)
   - Fix P1 items (2.1–2.7)
   - Run paper test harness successfully
   - Verify evidence pack shows all PASS
   - Run `scripts/evidence_pack.sh` and store in `/docs/evidence/`

3. **Live Trading Activation:**
   - Verify Luno API key configured with real funds
   - Verify training gate passed for at least 1 bot
   - Verify funding readiness check passes
   - Enable live mode via AI Chat or System Mode toggle
   - Monitor via Truth Console for first 24 hours

---

## 6. COMMANDS TO VERIFY CURRENT STATE

```bash
# Run tests
cd /home/runner/work/Amarktai-Crypto/Amarktai-Crypto
python -m pytest tests/ -q --no-header

# Build frontend
cd frontend && npm run build

# Python syntax check (key files)
cd backend
python -m py_compile server.py
python -m py_compile services/truth_kernel.py
python -m py_compile routes/scalper.py
python -m py_compile routes/ai_chat.py

# Run evidence pack (requires running server)
bash scripts/evidence_pack.sh

# Check go-live diagnostics (requires running server)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/diagnostics/go-live
```

---

## Production Fixes Applied — 2026-03-01

The following issues (found via VPS smoke testing) were fixed in
`copilot/fix-paper-mode-bot-integration`:

| # | Symptom | Fix location |
|---|---------|-------------|
| 1 | `db.database` AttributeError in `/api/diagnostics/go-live` and `/api/admin/truth/summary` | `server.py`, `routes/admin_truth.py` |
| 2 | `active_bots` count differs across endpoints | `services/canonical.py` (new), wired into `diagnostics.py`, `dashboard_overview.py`, `wallet_hub.py` |
| 3 | `status` vs `funded_status` contradiction in `/api/wallet/paper` | `services/canonical.get_canonical_wallet_truth`, `routes/wallet_hub.py` |
| 4 | Circuit breaker trips with zero fills (stale state) | `services/order_pipeline._gate_d_circuit_breaker` |
| 5 | Paper reset does not clear `fills_ledger` / `circuit_breaker_state` | `routes/system_mode.perform_paper_reset` |
| 6 | Scalper bots not visible in dashboard | `frontend/src/pages/Dashboard.js` |

Run `scripts/verify_truth.sh` on the VPS after deploying to confirm all counts agree.

