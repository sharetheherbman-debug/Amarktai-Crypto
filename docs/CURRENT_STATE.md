# Amarktai Network - Current State

**Generated:** audit_repo.py
**Date:** 2026-02-07 20:40:32

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

Total: 64 routers

| Router | Prefix | File |
|--------|--------|------|
| admin_endpoints | /api/admin | backend/routes/admin_endpoints.py |
| admin_enhanced | /api/admin | backend/routes/admin_enhanced.py |
| admin_start_fresh | None | backend/routes/admin_start_fresh.py |
| admin_whitelist | /api/admin/whitelist | backend/routes/admin_whitelist.py |
| advanced_trading_endpoints | /api/advanced | backend/routes/advanced_trading_endpoints.py |
| ai_chat | /api/ai | backend/routes/ai_chat.py |
| alerts | /api | backend/routes/alerts.py |
| analytics_api | /api/analytics | backend/routes/analytics_api.py |
| auth | None | backend/routes/auth.py |
| autopilot_control | None | backend/routes/autopilot_control.py |
| backtesting | /api/backtest | backend/routes/backtesting.py |
| bot_control | None | backend/routes/bot_control.py |
| bot_lifecycle | /api/bots | backend/routes/bot_lifecycle.py |
| build_info | /api/build | backend/routes/build_info.py |
| capital_tracking_endpoints | /api/capital | backend/routes/capital_tracking_endpoints.py |
| chat_endpoints | /api/chat | backend/routes/chat_endpoints.py |
| chat_enhanced | /api/chat | backend/routes/chat_enhanced.py |
| compat | /api | backend/routes/compat.py |
| compatibility_endpoints | /api | backend/routes/compatibility_endpoints.py |
| daily_report | /api/reports | backend/routes/daily_report.py |
| dashboard_aliases | /api | backend/routes/dashboard_aliases.py |
| dashboard_endpoints | /api | backend/routes/dashboard_endpoints.py |
| dashboard_overview | None | backend/routes/dashboard_overview.py |
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
| market_api | /api/market | backend/routes/market_api.py |
| metrics_api | /api/metrics | backend/routes/metrics_api.py |
| notifications | /api/notifications | backend/routes/notifications.py |
| order_endpoints | /api | backend/routes/order_endpoints.py |
| payment_agent_endpoints | /api/payment | backend/routes/payment_agent_endpoints.py |
| phase5_endpoints | /api/phase5 | backend/routes/phase5_endpoints.py |
| phase6_endpoints | /api/phase6 | backend/routes/phase6_endpoints.py |
| phase8_endpoints | /api/phase8 | backend/routes/phase8_endpoints.py |
| platforms | /api/platforms | backend/routes/platforms.py |
| quarantine | /api/quarantine | backend/routes/quarantine.py |
| realtime | /api/realtime | backend/routes/realtime.py |
| risk_management | None | backend/routes/risk_management.py |
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
| user_whitelist | /api/wallet/whitelist | backend/routes/user_whitelist.py |
| wallet_addresses | /api/wallet | backend/routes/wallet_addresses.py |
| wallet_endpoints | /api/wallet | backend/routes/wallet_endpoints.py |
| wallet_hub | /api/wallet | backend/routes/wallet_hub.py |
| wallet_transfers | /api/wallet | backend/routes/wallet_transfers.py |
| wallet_transfers_enhanced | /api/wallet | backend/routes/wallet_transfers_enhanced.py |
| websocket | None | backend/routes/websocket.py |

## API Endpoints

Total: 346 endpoints

### By Method
- **DELETE:** 10 endpoints
- **GET:** 203 endpoints
- **PATCH:** 1 endpoints
- **POST:** 123 endpoints
- **PUT:** 9 endpoints

## Frontend API Calls

Total: 0 API calls from frontend

## TODO Markers

Total: 110 TODO/FIXME/XXX/HACK markers

### By Type
- **BUG:** 102
- **HACK:** 2
- **TODO:** 2
- **XXX:** 4

## Production Blockers

Total: 2 blockers identified

### VALR_OVEX_PRESENT (HIGH)
Found 383 VALR/OVEX references

### TOS_VIOLATIONS (HIGH)
Found 6 potential ToS violations


## VALR/OVEX References (Must Be Removed)

Found 383 references:

- `backend/tests/test_wallet_production_features.py:210` - # Check no VALR/OVEX
- `backend/tests/test_wallet_production_features.py:211` - assert 'valr' not in SUPPORTED_PLATFORMS, "VALR should not be in SUPPORTED_PLATFORMS"
- `backend/tests/test_wallet_production_features.py:212` - assert 'ovex' not in SUPPORTED_PLATFORMS, "OVEX should not be in SUPPORTED_PLATFORMS"
- `backend/tests/test_wallet_production_features.py:214` - print("✅ Platform config has exactly 7 exchanges (no VALR/OVEX)")
- `backend/tests/test_route_uniqueness_and_platforms.py:7` - 3. VALR and OVEX only exist in _archive directories
- `backend/tests/test_route_uniqueness_and_platforms.py:92` - Test that VALR and OVEX only exist in _archive directories
- `backend/tests/test_route_uniqueness_and_platforms.py:98` - assert 'valr' not in SUPPORTED_PLATFORMS, \
- `backend/tests/test_route_uniqueness_and_platforms.py:99` - "VALR should not be in SUPPORTED_PLATFORMS"
- `backend/tests/test_route_uniqueness_and_platforms.py:100` - assert 'ovex' not in SUPPORTED_PLATFORMS, \
- `backend/tests/test_route_uniqueness_and_platforms.py:101` - "OVEX should not be in SUPPORTED_PLATFORMS"
- `backend/tests/test_route_uniqueness_and_platforms.py:102` - assert 'valr' not in PLATFORM_CONFIG, \
- `backend/tests/test_route_uniqueness_and_platforms.py:103` - "VALR should not be in PLATFORM_CONFIG"
- `backend/tests/test_route_uniqueness_and_platforms.py:104` - assert 'ovex' not in PLATFORM_CONFIG, \
- `backend/tests/test_route_uniqueness_and_platforms.py:105` - "OVEX should not be in PLATFORM_CONFIG"
- `backend/tests/test_route_uniqueness_and_platforms.py:107` - print("✅ VALR/OVEX exclusion check passed")
- `docs/IMPLEMENTATION_COMPLETE.md:9` - - ✅ Clean codebase (VALR/OVEX/Legacy AI removed)
- `docs/IMPLEMENTATION_COMPLETE.md:94` - - Removed VALR/OVEX references from 5 active docs
- `docs/IMPLEMENTATION_COMPLETE.md:98` - - ✅ No VALR/OVEX in active backend code
- `docs/IMPLEMENTATION_COMPLETE.md:122` - - ✅ No VALR/OVEX in active code
- `docs/IMPLEMENTATION_COMPLETE.md:178` - - 5 active docs cleaned of VALR/OVEX

... and 363 more

## Potential ToS Violations (Must Be Removed)

Found 6 potential violations:

- **proxy_rotation** in `backend/utils/edge_gate.py:5`
- **proxy_rotation** in `backend/utils/edge_gate.py:5`
- **fingerprint** in `backend/utils/edge_gate.py:5`
- **wash_trading** in `backend/paper_trading_engine.py:142`
- **wash_trading** in `backend/utils/edge_gate.py:5`
- **wash_trading** in `backend/utils/edge_gate.py:5`
