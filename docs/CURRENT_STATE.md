# Amarktai Network - Current State

**Generated:** audit_repo.py
**Date:** 2026-02-01 19:38:43

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
Found 289 VALR/OVEX references

### REMOVED_FEATURES_PRESENT (MEDIUM)
Found 1 references to removed features

### TOS_VIOLATIONS (HIGH)
Found 5 potential ToS violations


## VALR/OVEX References (Must Be Removed)

Found 289 references:

- `backend/server.py:932` - # OVEX and VALR removed - only Luno, Binance, KuCoin supported
- `backend/scripts/endpoint_doctor.sh:297` - # Check for correct exchange enablement (luno, binance, kucoin enabled; ovex, valr disabled)
- `backend/tests/test_critical_fixes.py:313` - assert 'ovex' not in PAPER_SUPPORTED_EXCHANGES, "ovex should not be supported"
- `backend/tests/test_critical_fixes.py:314` - assert 'valr' not in PAPER_SUPPORTED_EXCHANGES, "valr should not be supported"
- `docs/admin_panel.md:100` - "valr": false,
- `docs/admin_panel.md:101` - "ovex": false
- `docs/admin_panel.md:447` - **Allowed Values:** `"luno"`, `"binance"`, `"kucoin"`, `"valr"`, `"ovex"`
- `docs/AUDIT_REPORT.md:14` - - **5 platforms** implemented (Luno, Binance, KuCoin, OVEX, VALR)
- `docs/AUDIT_REPORT.md:38` - **Requirement**: "total 6 platforms. Kraken must be replaced with OVEX"
- `docs/AUDIT_REPORT.md:43` - - **5 platforms defined**: Luno, Binance, KuCoin, OVEX, VALR
- `docs/AUDIT_REPORT.md:52` - | `backend/config.py` | Exchange config | ✅ Has OVEX, no Kraken |
- `docs/AUDIT_REPORT.md:53` - | `frontend/src/config/exchanges.js` | Frontend config | ✅ Has OVEX, no Kraken |
- `docs/AUDIT_REPORT.md:96` - - ✅ OVEX: supports both modes, requires api_key + api_secret
- `docs/AUDIT_REPORT.md:97` - - ✅ VALR: supports both modes, requires api_key + api_secret
- `docs/AUDIT_REPORT.md:340` - 1. ✅ Platform standardization (OVEX present, Kraken removed)
- `docs/AUDIT_REPORT.md:393` - 4. **❓ CLARIFY PLATFORM COUNT**: Comment says "6 platforms" but lists same 5 (Luno, Binance, KuCoin,
- `docs/AUDIT_REPORT.md:477` - 2. **5e5a40e** - Replace Kraken with OVEX
- `docs/IMPLEMENTATION_COMPLETE.md:16` - - **Result**: All 5 exchanges (Luno, Binance, KuCoin, OVEX, VALR) now show as fully supported
- `docs/FINAL_PRODUCTION_AUDIT.md:16` - - **5 Platforms**: Luno (5), Binance (10), KuCoin (10), OVEX (10), VALR (10) = 45 bots total
- `docs/FINAL_PRODUCTION_AUDIT.md:39` - - [x] Exactly 5 platforms defined (Luno, Binance, KuCoin, OVEX, VALR)

... and 269 more

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
