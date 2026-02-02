# Amarktai Network - Current State

**Generated:** audit_repo.py
**Date:** 2026-02-01 19:42:32

## Supported Exchanges

Total: 7 exchanges

| Exchange | Max Bots | Source |
|----------|----------|--------|
| binance | 10 | exchange_limits.py |
| bitget | 10 | exchange_limits.py |
| bybit | 10 | exchange_limits.py |
| gate | 10 | exchange_limits.py |
| kraken | 10 | exchange_limits.py |
| kucoin | 10 | exchange_limits.py |
| luno | 5 | exchange_limits.py |

**Total Bot Capacity:** 65

## Backend Routers

Total: 53 routers

| Router | Prefix | File |
|--------|--------|------|
| admin_endpoints | /api/admin | backend/routes/admin_endpoints.py |
| admin_enhanced | /api/admin | backend/routes/admin_enhanced.py |
| advanced_trading_endpoints | /api/advanced | backend/routes/advanced_trading_endpoints.py |
| ai_chat | /api/ai | backend/routes/ai_chat.py |
| alerts | /api | backend/routes/alerts.py |
| analytics_api | /api/analytics | backend/routes/analytics_api.py |
| auth | None | backend/routes/auth.py |
| autopilot_control | None | backend/routes/autopilot_control.py |
| backtesting | /api/backtesting | backend/routes/backtesting.py |
| bot_control | None | backend/routes/bot_control.py |
| bot_lifecycle | /api/bots | backend/routes/bot_lifecycle.py |
| build_info | /api/build | backend/routes/build_info.py |
| capital_tracking_endpoints | /api/capital | backend/routes/capital_tracking_endpoints.py |
| chat_endpoints | /api/chat | backend/routes/chat_endpoints.py |
| chat_enhanced | /api/chat | backend/routes/chat_enhanced.py |
| compatibility_endpoints | /api | backend/routes/compatibility_endpoints.py |
| daily_report | /api/reports | backend/routes/daily_report.py |
| dashboard_aliases | /api | backend/routes/dashboard_aliases.py |
| dashboard_endpoints | /api | backend/routes/dashboard_endpoints.py |
| decision_trace | /api/decisions | backend/routes/decision_trace.py |
| diagnostics | /api/diagnostics | backend/routes/diagnostics.py |
| emergency_stop_endpoints | /api/system | backend/routes/emergency_stop_endpoints.py |
| execution_quality | /api/execution-quality | backend/routes/execution_quality.py |
| genetic_algorithm | /api/genetic | backend/routes/genetic_algorithm.py |
| health | /api/health | backend/routes/health.py |
| keys | /api/keys | backend/routes/keys.py |
| ledger_endpoints | /api | backend/routes/ledger_endpoints.py |
| limits_management | /api/limits | backend/routes/limits_management.py |
| live_trading_gate | /api/system | backend/routes/live_trading_gate.py |
| order_endpoints | /api | backend/routes/order_endpoints.py |
| payment_agent_endpoints | /api/payment | backend/routes/payment_agent_endpoints.py |
| phase5_endpoints | /api/phase5 | backend/routes/phase5_endpoints.py |
| phase6_endpoints | /api/phase6 | backend/routes/phase6_endpoints.py |
| phase8_endpoints | /api/phase8 | backend/routes/phase8_endpoints.py |
| platforms | /api/platforms | backend/routes/platforms.py |
| quarantine | /api/quarantine | backend/routes/quarantine.py |
| realtime | /api/realtime | backend/routes/realtime.py |
| system | /api/system | backend/routes/system.py |
| system_health_endpoints | /api/health | backend/routes/system_health_endpoints.py |
| system_limits | /api/system | backend/routes/system_limits.py |
| system_mode | /api/system | backend/routes/system_mode.py |
| system_status | /api/system | backend/routes/system_status.py |
| trades | /api/trades | backend/routes/trades.py |
| trading | None | backend/routes/trading.py |
| training | /api/training | backend/routes/training.py |
| training_quarantine | /api/training-quarantine | backend/routes/training_quarantine.py |
| treasury | /api/treasury | backend/routes/treasury.py |
| two_factor_auth | /api/auth/2fa | backend/routes/two_factor_auth.py |
| user_countdowns | /api/countdowns | backend/routes/user_countdowns.py |
| wallet_endpoints | /api/wallet | backend/routes/wallet_endpoints.py |
| wallet_hub | /api/wallet | backend/routes/wallet_hub.py |
| wallet_transfers | /api/wallet | backend/routes/wallet_transfers.py |
| websocket | None | backend/routes/websocket.py |

## API Endpoints

Total: 284 endpoints

### By Method
- **DELETE:** 6 endpoints
- **GET:** 172 endpoints
- **PATCH:** 1 endpoints
- **POST:** 99 endpoints
- **PUT:** 6 endpoints

## Frontend API Calls

Total: 0 API calls from frontend

## TODO Markers

Total: 99 TODO/FIXME/XXX/HACK markers

### By Type
- **BUG:** 75
- **HACK:** 1
- **TODO:** 20
- **XXX:** 3

## Production Blockers

Total: 3 blockers identified

### VALR_OVEX_PRESENT (HIGH)
Found 283 VALR/OVEX references

### REMOVED_FEATURES_PRESENT (MEDIUM)
Found 1 references to removed features

### TOS_VIOLATIONS (HIGH)
Found 5 potential ToS violations


## VALR/OVEX References (Must Be Removed)

Found 283 references:

- `docs/CURRENT_STATE.md:112` - Found 286 VALR/OVEX references
- `docs/CURRENT_STATE.md:121` - ## VALR/OVEX References (Must Be Removed)
- `docs/CURRENT_STATE.md:125` - - `docs/CURRENT_STATE.md:112` - Found 286 VALR/OVEX references
- `docs/CURRENT_STATE.md:126` - - `docs/CURRENT_STATE.md:121` - ## VALR/OVEX References (Must Be Removed)
- `docs/CURRENT_STATE.md:128` - - `docs/CURRENT_STATE.md:127` - - `docs/api_keys.md:15` - | **valr** | Exchange | `api_key`, `api_se
- `docs/CURRENT_STATE.md:129` - - `docs/CURRENT_STATE.md:128` - - `docs/api_keys.md:16` - | **ovex** | Exchange | `api_key`, `api_se
- `docs/CURRENT_STATE.md:130` - - `docs/CURRENT_STATE.md:129` - - `docs/api_keys.md:169` - - Provider must be recognized (openai, lu
- `docs/CURRENT_STATE.md:131` - - `docs/CURRENT_STATE.md:130` - - `docs/api_keys.md:319` - ### VALR
- `docs/CURRENT_STATE.md:132` - - `docs/CURRENT_STATE.md:131` - - `docs/api_keys.md:332` - ### OVEX
- `docs/CURRENT_STATE.md:133` - - `docs/CURRENT_STATE.md:132` - - `docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md:92` - ❌ **REMOVED:** OVEX
- `docs/CURRENT_STATE.md:134` - - `docs/CURRENT_STATE.md:133` - - `docs/COMPLETE_FEATURE_LIST.md:15` - - ✅ **OVEX** - South African 
- `docs/CURRENT_STATE.md:135` - - `docs/CURRENT_STATE.md:134` - - `docs/COMPLETE_FEATURE_LIST.md:16` - - ✅ **VALR** - Local ZAR trad
- `docs/CURRENT_STATE.md:136` - - `docs/CURRENT_STATE.md:135` - - `docs/SYSTEM_RULES_AND_AI_LEARNING.md:120` - "ovex": 10,     # 10 
- `docs/CURRENT_STATE.md:137` - - `docs/CURRENT_STATE.md:136` - - `docs/SYSTEM_RULES_AND_AI_LEARNING.md:121` - "valr": 10      # 10 
- `docs/CURRENT_STATE.md:138` - - `docs/CURRENT_STATE.md:137` - - `docs/SYSTEM_RULES_AND_AI_LEARNING.md:153` - **OVEX:**
- `docs/CURRENT_STATE.md:139` - - `docs/CURRENT_STATE.md:138` - - `docs/SYSTEM_RULES_AND_AI_LEARNING.md:162` - **VALR:**
- `docs/CURRENT_STATE.md:140` - - `docs/CURRENT_STATE.md:139` - - `docs/WORLD_CLASS_GAP_ANALYSIS.md:130` - - ✅ 5 exchanges (Luno, Bi
- `docs/CURRENT_STATE.md:141` - - `docs/CURRENT_STATE.md:140` - - `docs/DEPLOYMENT_GUIDE.md:411` - - Bots: 45 per user (5 Luno + 10 
- `docs/CURRENT_STATE.md:142` - - `docs/CURRENT_STATE.md:141` - - `docs/AI_LEARNING_SUMMARY.md:97` - ├─ OVEX: 10 bots
- `docs/CURRENT_STATE.md:143` - - `docs/CURRENT_STATE.md:142` - - `docs/AI_LEARNING_SUMMARY.md:98` - └─ VALR: 10 bots

... and 263 more

## Removed Features (Must Be Deleted)

Found 1 references to removed features:

- **Advanced Backtesting** in `backend/routes/backtesting.py`

## Potential ToS Violations (Must Be Removed)

Found 5 potential violations:

- **proxy_rotation** in `backend/utils/edge_gate.py:5`
- **proxy_rotation** in `backend/utils/edge_gate.py:5`
- **fingerprint** in `backend/utils/edge_gate.py:5`
- **wash_trading** in `backend/utils/edge_gate.py:5`
- **wash_trading** in `backend/utils/edge_gate.py:5`
