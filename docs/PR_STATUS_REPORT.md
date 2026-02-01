# PR STATUS REPORT - Amarktai Network Production Deployment

**Date**: 2026-02-01  
**Branch**: copilot/remove-obsolete-trading-features  
**Target**: Ubuntu 24.04 (Webdock VPS) + Nginx + systemd + MongoDB 7 + Redis (optional)

---

## ✅ COMPLETED MODULES

### A. Critical Blockers - PARTIALLY COMPLETE
- ✅ **Login KeyError Fix**: Auth payload normalized (hashed_password, password_hash, hashedPassword all handled)
- ✅ **AI Memory Path Fix**: Configurable via `AI_MEMORY_PATH` env var, creates dirs with proper permissions
- ⚠️ **Paper Trading**: Engine exists (1071 lines, 95% realistic), needs diagnostic endpoint
- ⚠️ **Auto-spawn**: Needs profit gate implementation and diagnostic endpoint
- ⚠️ **Live Trading Gates**: Partial implementation, needs server-side enforcement endpoints
- ⚠️ **Emergency Stop**: Needs implementation (POST /api/system/emergency-stop, resume, GET status)
- ⚠️ **Realtime**: Exists (websocket_manager.py, realtime_events.py), needs Nginx config validation
- ⚠️ **Diagnostics**: Partial (/api/diagnostics exists), needs specific endpoints

### B. Absolute Removals - COMPLETE
- ✅ **DeFi/DEX Removed**: Deleted `backend/routes/defi_trading.py`, `backend/services/web3_service.py`
- ✅ **Marketplace Removed**: Deleted `backend/routes/marketplace.py`
- ✅ **TradingView/Telegram Removed**: Deleted `backend/routes/signals.py`
- ✅ **VALR/OVEX**: Not found in active code (only in `_archive/`)
- ✅ **No Proxy/Stealth**: No references found to proxy rotation, fingerprinting, fake trades

### C. Exchange List - CORRECT
- ✅ **7 Exchanges Configured**: Luno(5), Binance(10), KuCoin(10), Bybit(10), Kraken(10), Bitget(10), Gate.io(10)
- ✅ **Configuration**: `backend/config/platforms.py` is canonical source
- ✅ **CCXT IDs**: All mapped correctly (gate→gateio)

---

## ⚠️ MODULES REQUIRING COMPLETION

### PHASE 1: Core Trading Infrastructure (HIGH PRIORITY)

#### 1.1 Paper Trading Diagnostics
**Status**: Engine complete, diagnostics missing  
**Required**:
- [ ] GET /api/diagnostics/paper-status
  - Returns: last_tick, last_decision, last_order_attempt, last_fill, last_error
  - Implementation: ~50 lines in `backend/routes/diagnostics.py`

#### 1.2 Auto-Spawn System
**Status**: Partial implementation in autonomous_scheduler.py  
**Required**:
- [ ] Profit gate: `ENABLE_AUTO_SPAWN=1`, `AUTO_SPAWN_MIN_PROFIT_ZAR=1000`
- [ ] Capital availability check (wallet + reserved funds)
- [ ] Quiet logging (only state changes + daily summary)
- [ ] GET /api/diagnostics/auto-spawn
  - Returns: enabled, last_spawn_time, next_eligibility, profit_threshold, available_capital
  - Implementation: ~100 lines

#### 1.3 Live Trading Safety Gates
**Status**: Mode flags exist, server-side enforcement incomplete  
**Required**:
- [ ] POST /api/system/emergency-stop (halts all trading, persists state)
- [ ] POST /api/system/emergency-resume (resumes trading)
- [ ] GET /api/system/status (returns emergency_stop, live_enabled, autopilot_enabled)
- [ ] Server-side enforcement in ALL execution paths
  - Implementation: ~150 lines in `backend/routes/system_status.py`

#### 1.4 Realtime Nginx Compatibility
**Status**: WebSocket/SSE exist, Nginx config needed  
**Required**:
- [ ] GET /api/diagnostics/realtime
  - Returns: ws_connected, sse_connected, last_event, connection_count
- [ ] Nginx config with proper headers (Upgrade, Connection, timeouts)
  - Implementation: ~50 lines diagnostic + nginx.conf example

---

### PHASE 2: PROFIT-CORE + SUPER BRAIN (MEDIUM PRIORITY)

#### 2.1 Edge Gate (EV after costs)
**Status**: NOT IMPLEMENTED  
**Required**:
- [ ] Pre-trade gate: reject if `EV < (fees + spread + slippage + buffer)`
- [ ] Reason codes: EDGE_TOO_LOW, SPREAD_TOO_WIDE, VOL_TOO_HIGH, EXEC_QUALITY_RED
- [ ] Implementation: ~200 lines in `backend/utils/edge_gate.py`
- [ ] Integration: Add to paper_trading_engine.py and any live execution

#### 2.2 Market Regime + Strategy Router
**Status**: PARTIAL (`backend/market_regime.py` exists)  
**Required**:
- [ ] Regime detector: trending/mean-reverting/high-vol/low-vol
- [ ] Strategy router: bot.strategy = f(regime)
- [ ] Cache regime (avoid latency)
- [ ] GET /api/diagnostics/regime
  - Returns: current_regime, confidence, strategy_recommendation, last_update
- [ ] Implementation: ~150 lines enhancement to market_regime.py

#### 2.3 Self-Learning
**Status**: Partial (`backend/self_learning.py` exists)  
**Required**:
- [ ] Nightly learning loop (evaluate performance by regime)
- [ ] Adjust parameters within bounds (no drastic jumps)
- [ ] Blacklist failed DNA patterns
- [ ] Never change exchange list or risk limits
- [ ] Audit logs with rollback
- [ ] GET /api/learning/status (last_run, adjustments_made, blacklisted_dna)
- [ ] POST /api/learning/run (admin only, dry-run support)
- [ ] Implementation: ~200 lines enhancement

#### 2.4 Self-Healing
**Status**: Partial (`backend/self_healing.py` exists)  
**Required**:
- [ ] Watchdog for schedulers/trading loops
- [ ] Auto-recovery from transient API errors
- [ ] Backoff + cooldown on error spikes
- [ ] Circuit breaker with reason codes
- [ ] GET /api/diagnostics/health-detail
  - Returns: circuit_status, error_rate, backoff_seconds, recovery_attempts
- [ ] Implementation: ~150 lines enhancement

#### 2.5 Execution Quality Monitor
**Status**: NOT IMPLEMENTED  
**Required**:
- [ ] Track: order placement latency p50/p95, fill latency, reject rate, slippage
- [ ] Degradation actions: reduce size, widen cooldowns, pause bots, alert (WS + email)
- [ ] GET /api/execution-quality/status
  - Returns: metrics per exchange, degradation_alerts
- [ ] Implementation: ~250 lines in `backend/engines/execution_quality.py`

#### 2.6 Bot-to-Bot Communication
**Status**: NOT IMPLEMENTED  
**Required**:
- [ ] "Dibs & Pivot" coordination system
- [ ] Bots publish trade intent
- [ ] Coordinator grants lock TTL
- [ ] Other bots pivot/reduce/skip
- [ ] Realtime events feed
- [ ] Implementation: ~300 lines in `backend/engines/bot_coordinator.py`

#### 2.7 Treasury + Compounding
**Status**: PARTIAL (capital_allocator.py exists)  
**Required**:
- [ ] BOT_MAX_CAPITAL_ZAR=10000 per bot cap
- [ ] Excess swept to Treasury bucket (ledger-first)
- [ ] Daily reinvestment: top 3 performers (respecting caps)
- [ ] Safe reserves enforcement
- [ ] GET /api/treasury/status
  - Returns: total_treasury, allocations, reinvestment_plan
- [ ] POST /api/treasury/rebalance (dry-run option)
- [ ] Implementation: ~250 lines enhancement to capital_allocator.py

---

### PHASE 3: WALLET ARCHITECTURE (CRITICAL - NON-NEGOTIABLE)

**Status**: PARTIAL IMPLEMENTATION EXISTS  
**Existing Files**:
- `backend/engines/wallet_manager.py` (426 lines)
- `backend/services/wallet_transfers_service.py` (701 lines)
- `backend/routes/wallet_endpoints.py` (448 lines)
- `backend/routes/wallet_hub.py` (307 lines)
- `backend/routes/wallet_transfers.py`
- `backend/jobs/wallet_balance_monitor.py`

**CRITICAL GAP**: Current implementation is NOT production-ready per requirements:
- ❌ No idempotency keys for transfers
- ❌ No state machine for transfer jobs
- ❌ No 2FA enforcement for withdrawals
- ❌ No approval thresholds
- ❌ No REAL exchange API transfers (may be simulated)
- ❌ No reserved funds tracking
- ❌ No comprehensive safety limits

**REQUIRED IMPLEMENTATION** (per new requirement):

> **"Wallet transfers must be REAL (exchange API), not simulated, and must be robustly guarded with idempotency, 2FA, approval thresholds, and clear reason codes."**

#### 3.1 MongoDB Collections
**Required Collections**:
- [ ] `wallets` (per user, per exchange, per asset)
- [ ] `wallet_addresses` (deposit addresses per exchange/asset)
- [ ] `transfers_ledger` (immutable transfer events)
- [ ] `transfer_jobs` (state machine: requested→approved→queued→broadcast→confirmed/failed)
- [ ] `balances_snapshots` (polling + diffs)
- [ ] `audit_log` (who/what triggered transfer)

**Implementation**: ~100 lines migration script

#### 3.2 Transfer State Machine with Idempotency
**Required**:
- [ ] Every transfer has unique `transfer_id` and `idempotency_key`
- [ ] Retries cannot double-send
- [ ] All steps recorded to `transfers_ledger`
- [ ] Process restart mid-transfer resumes safely
- [ ] Implementation: ~300 lines in `backend/services/transfer_state_machine.py`

#### 3.3 Luno as Hub + Working Capital Model
**Required**:
- [ ] User deposits ONLY to Luno (mother wallet)
- [ ] Configurable working reserves per exchange
- [ ] Bot/exchange requests funds from Luno
- [ ] Excess swept back to Luno
- [ ] Implementation: ~200 lines in wallet_manager.py enhancement

#### 3.4 Safety Guards (SERVER-SIDE ENFORCEMENT)
**Required Environment Variables**:
```bash
ENABLE_WALLET_AUTOPILOT=0  # Default OFF
ENABLE_WITHDRAWALS=0  # Default OFF (hard gate)
WALLET_MAX_TRANSFER_ZAR_PER_TX=10000
WALLET_MAX_TRANSFER_ZAR_PER_DAY=50000
WALLET_MAX_TRANSFER_ZAR_PER_MONTH=200000
WALLET_MIN_RESERVE_LUNO_ZAR=2000
WALLET_MIN_RESERVE_PER_EXCHANGE_ZAR=500
REQUIRE_2FA_FOR_WITHDRAWALS=1
REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR=25000
```

**Enforcement Rules**:
- [ ] No transfers if Emergency Stop active
- [ ] No transfers if `ENABLE_WALLET_AUTOPILOT=0`
- [ ] No withdrawals unless `ENABLE_WITHDRAWALS=1`
- [ ] No withdrawals without valid TOTP 2FA
- [ ] Transfers above threshold require admin approval queue
- [ ] Dry-run mode support

**Implementation**: ~200 lines in wallet_transfers_service.py enhancement

#### 3.5 Real-Time Balance Sync (All 7 Exchanges)
**Required**:
- [ ] Poll balances (or WebSocket if available) on interval
- [ ] Store `balances_snapshots`
- [ ] Detect deltas (deposit arrived, withdrawal confirmed)
- [ ] Publish realtime events:
  - `wallet_balance_updated`
  - `transfer_job_updated`
  - `transfer_required` (autopilot request)
  - `transfer_blocked` (with reason codes)

**Implementation**: ~250 lines in wallet_balance_monitor.py enhancement

#### 3.6 Transfer Execution (REAL CCXT API)
**Required**:
- [ ] Use CCXT `exchange.withdraw()` for real withdrawals
- [ ] Prefer internal transfers (subaccounts) when supported
- [ ] Handle exchange-specific requirements (network tags, memos, whitelists)
- [ ] Enforce whitelist of withdrawal addresses (Luno addresses stored)
- [ ] Retry with exponential backoff (never double-send)
- [ ] Implementation: ~300 lines in `backend/services/transfer_executor.py`

**CRITICAL**: Must NOT be simulated. Must use actual exchange APIs.

#### 3.7 Diagnostics Endpoints
**Required**:
- [ ] GET /api/diagnostics/wallet-status
  - Returns: per exchange (last_sync, last_error, balances_summary, sync_lag_seconds)
- [ ] GET /api/diagnostics/transfers
  - Returns: recent transfer jobs (id, state, from_exchange, to_exchange, amount, reason_code, created_at, updated_at)

**Implementation**: ~100 lines in routes/diagnostics.py

#### 3.8 Frontend Wallet UI
**Required**:
- [ ] "Deposit to Luno" instructions (addresses/QR)
- [ ] Live balances per exchange + total portfolio value
- [ ] Working Capital allocations per exchange
- [ ] Transfer queue with live status + reason codes
- [ ] Manual "Request Transfer" (creates job requiring approval/2FA)
- [ ] Admin approval UI (approve/reject large transfers)
- [ ] Last sync times + errors per exchange
- [ ] Implementation: ~500 lines in `frontend/src/components/WalletHub.js` enhancement

#### 3.9 Autopilot Integration
**Required**:
- [ ] Only request transfers when needed for bot operations/reinvestment
- [ ] Never exceed bot caps or exposure caps
- [ ] Never allocate more than available Luno balance minus reserves
- [ ] Track reserved funds (prevent double-spending)
- [ ] When bots reach `BOT_MAX_CAPITAL_ZAR`, sweep excess to treasury then Luno
- [ ] Implementation: ~200 lines in autopilot_engine.py enhancement

#### 3.10 Wallet Tests
**Required**:
- [ ] Test: Transfer idempotency prevents duplicates
- [ ] Test: Transfer policy respects limits/reserves
- [ ] Test: Withdrawal blocked without 2FA
- [ ] Test: Withdrawal blocked when `ENABLE_WITHDRAWALS=0`
- [ ] Test: Emergency stop blocks transfers
- [ ] Test: Wallet status endpoint reports sync status
- [ ] Test: Realtime events emitted on balance changes
- [ ] Implementation: ~400 lines in `backend/tests/test_wallet_transfers.py`

**ESTIMATED TOTAL WALLET WORK**: ~3,000 lines across 10+ files

---

### PHASE 4: Frontend Requirements (LOW PRIORITY)

#### 4.1 AI Chat Layout Fix
**Status**: Component exists (`frontend/src/components/AIChatPanel.js`)  
**Required**:
- [ ] No double-scrollbars
- [ ] No page scroll caused by chat
- [ ] AI Chat panel fixed within viewport
- [ ] Implementation: ~50 lines CSS/layout fix

#### 4.2 Messages Behavior
**Status**: Messages saved to MongoDB  
**Required**:
- [ ] Clean on login/refresh (no previous messages)
- [ ] Optional "Restore last session" button (default off)
- [ ] Confirm: messages disappear visually but stored
- [ ] Implementation: ~100 lines in AIChatPanel.js

#### 4.3 Endpoint Alignment
**Required**:
- [ ] Audit all frontend API calls
- [ ] Fix route mismatches
- [ ] Standardize JSON shapes
- [ ] Implementation: ~varies per endpoint

---

### PHASE 5: Repo Tidy/Restructure (LOW PRIORITY)

#### 5.1 File Organization
**Current**: Scripts/docs in root (cluttered)  
**Required**:
```
/docs/
  - DEPLOYMENT.md
  - DEPLOYMENT_CHECKLIST.md
  - CURRENT_STATE.md
  - PR_STATUS_REPORT.md (THIS FILE)
  - INDEX.md

/scripts/
  - verify_*.py
  - verify_*.sh
  - smoke_*.sh
  - preflight.sh (NEW)
  - verify.sh (NEW)

/tools/
  - doctor.py
  - analyze_todos.py
  - scanners
```

**Implementation**: ~git mv commands + README updates

#### 5.2 Documentation Consolidation
**Required**:
- [ ] Remove outdated duplicate docs
- [ ] Consolidate into CURRENT_STATE.md
- [ ] Update all doc paths in README
- [ ] Implementation: ~varies

---

### PHASE 6: Clean Deploy (HIGH PRIORITY)

#### 6.1 Environment Configuration
**Status**: `.env.example` exists (19KB)  
**Required**:
- [ ] Verify all new wallet env vars present
- [ ] Verify all safety gates env vars present
- [ ] Add comments for production values
- [ ] Implementation: ~50 lines additions

#### 6.2 Preflight Script
**Required**: `scripts/preflight.sh`
```bash
# Compile/import check
# Env var validation
# DB connectivity check
# Exchange registry == 7 check
# Python dependencies check
```
**Implementation**: ~150 lines bash

#### 6.3 Verification Script
**Required**: `scripts/verify.sh`
```bash
# Health check
# Login test
# Bots schema validation
# Realtime diagnostics
# Paper trading status
# Auto-spawn status
# Wallet status
```
**Implementation**: ~200 lines bash

#### 6.4 Systemd + Nginx Examples
**Required**:
- [ ] `docs/examples/amarktai.service` (systemd unit)
- [ ] `docs/examples/nginx.conf` (reverse proxy + WebSocket)
- [ ] Implementation: ~100 lines config

---

## 📊 COMPLETION SUMMARY

| Phase | Status | Completion | Estimated Remaining Work |
|-------|--------|------------|--------------------------|
| **A. Critical Blockers** | ⚠️ Partial | 40% | ~650 lines |
| **B. Absolute Removals** | ✅ Complete | 100% | 0 lines |
| **C. Exchange List** | ✅ Complete | 100% | 0 lines |
| **Phase 1: Core Trading** | ⚠️ Partial | 50% | ~550 lines |
| **Phase 2: Super Brain** | ⚠️ Partial | 30% | ~1,450 lines |
| **Phase 3: Wallet** | ❌ Not Production-Ready | 20% | ~3,000 lines |
| **Phase 4: Frontend** | ⚠️ Needs Polish | 70% | ~150 lines |
| **Phase 5: Repo Tidy** | ❌ Not Done | 0% | ~varies (file moves) |
| **Phase 6: Clean Deploy** | ⚠️ Partial | 50% | ~500 lines |

**TOTAL ESTIMATED REMAINING WORK**: ~6,300 lines + file organization

---

## 🔥 CRITICAL GAPS (Must Fix Before Production)

### 1. **WALLET TRANSFERS NOT PRODUCTION-READY** ⚠️
Current implementation LACKS:
- Idempotency (risk of double-sends)
- State machine (transfers can fail mid-process)
- 2FA enforcement (insecure withdrawals)
- Approval thresholds (no large transfer gates)
- Reserved funds tracking (bots can spawn without capital)
- REAL CCXT API calls (may be simulated)

**Risk**: FUNDS LOSS, double-withdrawals, bot spawn failures  
**Priority**: CRITICAL - Must implement before ANY autopilot usage

### 2. **Emergency Stop Not Enforced** ⚠️
Current state unclear if emergency stop:
- Halts paper trading
- Halts live trading
- Halts wallet transfers
- Persists across restarts

**Risk**: Trading continues during emergency  
**Priority**: HIGH

### 3. **No Live Trading Safety Verification** ⚠️
No clear server-side validation that:
- Live trading requires `ENABLE_LIVE_TRADING=1` AND user toggle
- Autopilot requires `ENABLE_AUTOPILOT=1` AND user toggle

**Risk**: Accidental live trading  
**Priority**: HIGH

---

## ✅ HOW TO VERIFY

### Verify Exchange List (7 Only)
```bash
# Backend check
cd backend
python3 -c "from config.platforms import SUPPORTED_PLATFORMS; print(f'Exchanges: {len(SUPPORTED_PLATFORMS)}'); print(SUPPORTED_PLATFORMS)"
# Expected: 7 exchanges

# Frontend check
cd frontend/src
grep -r "VALR\|OVEX" . --include="*.js" --include="*.jsx"
# Expected: No results
```

### Verify Forbidden Modules Removed
```bash
# Check DeFi/DEX
ls backend/routes/defi_trading.py 2>&1 | grep "No such file"
ls backend/services/web3_service.py 2>&1 | grep "No such file"

# Check Marketplace
ls backend/routes/marketplace.py 2>&1 | grep "No such file"

# Check Signals
ls backend/routes/signals.py 2>&1 | grep "No such file"

# Expected: All return "No such file or directory"
```

### Verify Paper Trading
```bash
# Start backend
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000

# In another terminal
curl http://localhost:8000/api/diagnostics/paper-status
# Expected: JSON with last_tick, last_decision, last_order_attempt
```

### Verify Emergency Stop
```bash
# Test emergency stop
curl -X POST http://localhost:8000/api/system/emergency-stop \
  -H "Authorization: Bearer $TOKEN"

# Verify status
curl http://localhost:8000/api/system/status
# Expected: {"emergency_stop": true, ...}

# Verify trading blocked
curl -X POST http://localhost:8000/api/bots/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"platform":"luno","pair":"BTC/ZAR",...}'
# Expected: 403 with "Emergency stop active"
```

### Verify Wallet Safety
```bash
# Test withdrawal without ENABLE_WITHDRAWALS
curl -X POST http://localhost:8000/api/wallet/transfer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from":"binance","to":"luno","amount":1000}'
# Expected: 403 with "Withdrawals disabled"

# Test wallet status
curl http://localhost:8000/api/diagnostics/wallet-status \
  -H "Authorization: Bearer $TOKEN"
# Expected: JSON with per-exchange sync status
```

---

## 🚀 DEPLOYMENT READINESS: ⚠️ NOT READY

**Blockers**:
1. ❌ Wallet transfers not production-safe (idempotency, 2FA, real API)
2. ❌ Emergency stop not verified
3. ❌ Live trading gates not fully server-enforced
4. ⚠️ Many "SUPER BRAIN" modules incomplete
5. ⚠️ No preflight/verify scripts
6. ⚠️ No systemd/nginx examples

**Can Deploy For**:
- ✅ Paper trading (with monitoring)
- ✅ API key management
- ✅ Bot creation (paper mode)
- ✅ Dashboard viewing
- ✅ AI chat

**Cannot Deploy For**:
- ❌ Live trading (not safe)
- ❌ Autopilot with wallet transfers (not safe)
- ❌ Production-grade auto-healing
- ❌ Advanced execution quality monitoring

---

## 📝 RECOMMENDATIONS

### Immediate (Week 1)
1. **Fix Wallet Transfers** (3,000 lines)
   - Add idempotency keys
   - Add state machine
   - Add 2FA enforcement
   - Verify REAL CCXT API usage
   - Add reserved funds tracking

2. **Add Emergency Stop Endpoints** (150 lines)
   - POST /api/system/emergency-stop
   - POST /api/system/emergency-resume
   - GET /api/system/status

3. **Add Critical Diagnostics** (200 lines)
   - GET /api/diagnostics/paper-status
   - GET /api/diagnostics/auto-spawn
   - GET /api/diagnostics/wallet-status
   - GET /api/diagnostics/realtime

### Short-Term (Week 2-3)
4. **Implement Core Super Brain** (1,000 lines)
   - Edge Gate (EV calculator)
   - Execution Quality Monitor
   - Self-Healing enhancements

5. **Create Deploy Scripts** (500 lines)
   - scripts/preflight.sh
   - scripts/verify.sh
   - Systemd + Nginx examples

### Medium-Term (Week 4-6)
6. **Complete Super Brain** (1,500 lines)
   - Market Regime Router
   - Self-Learning enhancements
   - Bot-to-Bot coordination
   - Treasury + Compounding

7. **Polish Frontend** (500 lines)
   - Wallet UI enhancements
   - AI Chat layout fixes
   - Endpoint alignment

8. **Repo Tidy** (file moves)
   - Organize /docs, /scripts, /tools
   - Update README

---

## 🔐 FORBIDDEN MODULES CONFIRMATION

**Explicitly Removed**:
- ✅ DeFi/DEX Trading (`defi_trading.py`, `web3_service.py`)
- ✅ Strategy Marketplace (`marketplace.py`)
- ✅ TradingView/Telegram Signals (`signals.py`)

**Not Found in Active Code**:
- ✅ VALR exchange (only in `_archive/`)
- ✅ OVEX exchange (only in `_archive/`)
- ✅ Proxy rotation / IP masking
- ✅ Fingerprint obfuscation
- ✅ Stealth user-agent
- ✅ Noise trades / fake trades
- ✅ Walk-forward backtesting (TODO comment only)
- ✅ Monte Carlo simulation (not implemented)
- ✅ Stripe payment processing

**Commitment**: These systems will NOT be re-added, will NOT be feature-flagged, and will NOT exist in any form in this repository going forward.

---

## 📋 FUNCTIONS AND FEATURES STILL NEEDED

### CRITICAL PRIORITY (Must Complete)

1. **Wallet Transfer State Machine** (~300 lines)
   - Function: `create_transfer_job(user_id, from_exchange, to_exchange, amount, idempotency_key)`
   - Function: `execute_transfer_job(transfer_id)` - REAL CCXT API
   - Function: `retry_failed_transfer(transfer_id)`
   - Function: `cancel_transfer(transfer_id, reason)`
   - State transitions: requested→approved→queued→broadcast→confirmed/failed

2. **2FA Enforcement for Withdrawals** (~150 lines)
   - Function: `require_2fa_for_withdrawal(user_id, transfer_id, totp_code)`
   - Function: `validate_totp(user_id, totp_code)`
   - Enforcement: Block ALL withdrawals without valid 2FA

3. **Transfer Approval Queue** (~200 lines)
   - Function: `create_approval_request(transfer_id, amount_zar)`
   - Function: `approve_transfer(admin_id, transfer_id)`
   - Function: `reject_transfer(admin_id, transfer_id, reason)`
   - Trigger: Any transfer > `REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR`

4. **Reserved Funds Tracking** (~200 lines)
   - Function: `reserve_funds(user_id, exchange, amount, bot_id)`
   - Function: `release_funds(user_id, exchange, amount, bot_id)`
   - Function: `get_available_capital(user_id, exchange)`
   - Prevent: Bots spawning when capital unavailable

5. **Real-Time Balance Sync** (~250 lines)
   - Function: `sync_exchange_balances(user_id, exchange)` - REAL CCXT API
   - Function: `detect_balance_delta(user_id, exchange, previous_snapshot)`
   - Function: `publish_balance_update_event(user_id, exchange, delta)`
   - Frequency: Every 60 seconds per exchange

6. **Emergency Stop System** (~150 lines)
   - Endpoint: POST /api/system/emergency-stop
   - Endpoint: POST /api/system/emergency-resume
   - Endpoint: GET /api/system/status
   - Function: `enforce_emergency_stop()` in ALL execution paths

7. **Paper Trading Diagnostics** (~50 lines)
   - Endpoint: GET /api/diagnostics/paper-status
   - Fields: last_tick, last_decision, last_order_attempt, last_fill, last_error

8. **Auto-Spawn Diagnostics** (~100 lines)
   - Endpoint: GET /api/diagnostics/auto-spawn
   - Function: `check_spawn_eligibility(user_id)`
   - Fields: enabled, profit_threshold, available_capital, next_eligibility

9. **Wallet Diagnostics** (~100 lines)
   - Endpoint: GET /api/diagnostics/wallet-status
   - Endpoint: GET /api/diagnostics/transfers
   - Per exchange: last_sync, sync_lag, last_error, balance_summary

10. **Realtime Diagnostics** (~50 lines)
    - Endpoint: GET /api/diagnostics/realtime
    - Fields: ws_connected, sse_connected, connection_count, last_event

### HIGH PRIORITY

11. **Edge Gate (EV Calculator)** (~200 lines)
    - Function: `calculate_expected_value(price, size, fees, spread, slippage)`
    - Function: `should_trade(ev, buffer)` - Returns: bool + reason_code
    - Reason codes: EDGE_TOO_LOW, SPREAD_TOO_WIDE, VOL_TOO_HIGH, EXEC_QUALITY_RED

12. **Execution Quality Monitor** (~250 lines)
    - Function: `track_order_latency(exchange, latency_ms)`
    - Function: `track_fill_quality(exchange, slippage_bps, reject_rate)`
    - Function: `check_execution_degradation(exchange)` - Returns: alerts
    - Actions: Reduce size, widen cooldowns, pause bots, send WS alert

13. **Market Regime Router** (~150 lines)
    - Function: `detect_regime(pair, timeframe)` - Returns: trending/mean-reverting/high-vol/low-vol
    - Function: `select_strategy_for_regime(regime)` - Returns: strategy_name
    - Function: `update_bot_strategy(bot_id, strategy_name)`
    - Endpoint: GET /api/diagnostics/regime

14. **Self-Healing Enhancements** (~150 lines)
    - Function: `watchdog_check_schedulers()` - Restart if dead
    - Function: `handle_api_error_with_backoff(exchange, error)`
    - Function: `open_circuit_breaker(exchange, reason)` - Stop trading temporarily
    - Endpoint: GET /api/diagnostics/health-detail

15. **Bot-to-Bot Coordination** (~300 lines)
    - Function: `publish_trade_intent(bot_id, pair, side, size)`
    - Function: `request_dibs_lock(bot_id, pair, ttl_seconds)`
    - Function: `pivot_on_conflict(bot_id, reason)`
    - Realtime events: dibs_granted, dibs_conflict, pivot_triggered

16. **Treasury + Compounding** (~250 lines)
    - Function: `sweep_excess_to_treasury(bot_id)` - When capital > BOT_MAX_CAPITAL_ZAR
    - Function: `calculate_reinvestment_plan()` - Top 3 performers
    - Function: `execute_reinvestment(plan, dry_run=False)`
    - Endpoint: GET /api/treasury/status
    - Endpoint: POST /api/treasury/rebalance

17. **Self-Learning Enhancements** (~200 lines)
    - Function: `evaluate_bot_performance_by_regime()`
    - Function: `adjust_parameters_within_bounds(bot_id, adjustments)`
    - Function: `blacklist_dna_pattern(dna_hash, reason)`
    - Function: `rollback_learning_change(change_id)`
    - Endpoint: GET /api/learning/status
    - Endpoint: POST /api/learning/run

### MEDIUM PRIORITY

18. **Frontend Wallet UI** (~500 lines)
    - Component: DepositInstructions (Luno addresses, QR codes)
    - Component: BalancesGrid (per exchange + total)
    - Component: TransferQueue (live status, reason codes)
    - Component: ManualTransferRequest (form with 2FA input)
    - Component: AdminApprovalUI (approve/reject large transfers)

19. **AI Chat Layout Fix** (~50 lines)
    - Fix: Remove double-scrollbars
    - Fix: Make chat panel fixed within viewport
    - CSS: Prevent page scroll caused by chat

20. **Messages Clean on Refresh** (~100 lines)
    - Feature: Start clean on login/refresh
    - Feature: Optional "Restore last session" button (default off)
    - Backend: Messages still saved to MongoDB

21. **Preflight Script** (~150 lines bash)
    - Check: Python dependencies installed
    - Check: MongoDB connectivity
    - Check: Environment variables set
    - Check: Exchange registry == 7
    - Check: No syntax errors in Python files

22. **Verification Script** (~200 lines bash)
    - Test: Health endpoint responds
    - Test: Login succeeds
    - Test: Bots schema valid
    - Test: Realtime diagnostics pass
    - Test: Paper trading status retrieves
    - Test: Auto-spawn status retrieves
    - Test: Wallet status retrieves

23. **Systemd Unit File** (~50 lines)
    - Service: amarktai-backend.service
    - User: amarktai
    - WorkingDirectory: /opt/amarktai/backend
    - ExecStart: uvicorn server:app
    - Restart: on-failure

24. **Nginx Configuration** (~100 lines)
    - Proxy: / → http://localhost:8000
    - WebSocket: /ws → ws://localhost:8000
    - SSE: /api/realtime/* → http://localhost:8000
    - Headers: Upgrade, Connection, timeouts

### LOW PRIORITY

25. **Repo File Organization** (git mv commands)
    - Move: verify_*.py → scripts/
    - Move: verify_*.sh → scripts/
    - Move: DEPLOYMENT*.md → docs/
    - Move: doctor.py → tools/
    - Update: README.md paths

26. **Documentation Consolidation** (varies)
    - Remove: Outdated duplicate docs
    - Consolidate: Into CURRENT_STATE.md
    - Update: All cross-references

27. **Endpoint Alignment** (varies per route)
    - Audit: All frontend API calls
    - Fix: Route mismatches (404s)
    - Standardize: JSON response shapes

---

## 🎯 ESTIMATED TOTAL REMAINING WORK

- **Lines of Code**: ~6,300
- **Configuration Files**: ~250 lines
- **Documentation**: ~varies
- **File Organization**: ~git mv commands
- **Testing**: ~400 lines tests

**Time Estimate** (1 developer):
- Critical Priority (items 1-10): 2-3 weeks
- High Priority (items 11-17): 2-3 weeks
- Medium Priority (items 18-24): 1-2 weeks
- Low Priority (items 25-27): 1 week

**Total**: 6-9 weeks for complete implementation

---

**END OF REPORT**
