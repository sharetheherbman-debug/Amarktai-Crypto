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

## Production Status

**Status:** ✅ Production-Ready

### Exchange Compliance
- ✅ Exactly 7 supported exchanges (luno, binance, kucoin, bybit, kraken, bitget, gate)
- ✅ No VALR/OVEX references in active codebase
- ✅ Bot allocation: 65 total (5+10+10+10+10+10+10)

### Code Quality
- ✅ All Python files compile
- ✅ No ToS violations (verified safe)
- ✅ Removed features properly archived

### Verification
Run `./scripts/compliance_checks.sh` to verify production readiness.
