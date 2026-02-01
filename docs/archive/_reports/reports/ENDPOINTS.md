# Amarktai Network - Complete API Endpoints Reference

**Version**: 3.2.1 - Production Ready  
**Last Updated**: December 27, 2025  
**Audit Status**: ✅ FULLY COMPLIANT (Backend Truth + REST Parity Verified)

This document lists all mounted endpoints in the Amarktai Network API.

> **Audit Note**: All endpoints have been audited and verified to maintain backend as single source of truth.  
> See [AUDIT_REPORT.md](./AUDIT_REPORT.md) for detailed compliance verification.

## Table of Contents

- [Backend Truth Compliance](#backend-truth-compliance)
- [Core Endpoints](#core-endpoints)
- [Authentication](#authentication)
- [Bot Management](#bot-management)
- [Trading & Orders](#trading--orders)
- [Ledger & Accounting](#ledger--accounting)
- [Limits & Circuit Breaker](#limits--circuit-breaker)
- [Analytics & Reporting](#analytics--reporting)
- [AI & Chat](#ai--chat)
- [Admin](#admin)
- [System & Health](#system--health)

---

## Backend Truth Compliance

**Audit Date**: December 27, 2025  
**Status**: ✅ All endpoints maintain backend as single source of truth

### Primary Frontend Endpoints (Verified)

| Endpoint | Method | Backend Truth | Status |
|----------|--------|---------------|--------|
| `/api/analytics/profit-history` | GET | MongoDB direct query | ✅ VERIFIED |
| `/api/analytics/countdown-to-million` | GET | MongoDB + wallet data | ✅ VERIFIED |
| `/api/autonomous/reinvest-profits` | POST | Capital allocator service | ✅ VERIFIED |

### Bot Control REST Parity (Verified)

| Endpoint | Methods | State Persistence | Status |
|----------|---------|-------------------|--------|
| `/api/bots/{bot_id}/pause` | POST, PUT | MongoDB | ✅ VERIFIED |
| `/api/bots/{bot_id}/stop` | POST | MongoDB | ✅ VERIFIED |
| `/api/bots/{bot_id}/resume` | POST, PUT | MongoDB | ✅ VERIFIED |
| `/api/bots/{bot_id}/start` | POST | MongoDB | ✅ VERIFIED |

**Note**: No client-side approximations or business logic exist. All calculations performed server-side.

---

## Core Endpoints

### Health & Status
- `GET /` - Root endpoint
- `GET /api/health` - Production health check
- `GET /api/health/ping` - Simple health check
- `GET /api/health/indicators` - Comprehensive health indicators

### Real-time
- `WS /api/ws` - WebSocket connection for real-time updates
- `GET /api/realtime/events` - Server-Sent Events (SSE) stream
- `GET /api/sse/overview` - SSE stream for overview data
- `GET /api/sse/live-prices` - SSE stream for live prices

---

## Authentication

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user profile
- `PUT /api/auth/profile` - Update user profile

---

## Bot Management

### Bot CRUD
- `GET /api/bots` - List all user bots
- `POST /api/bots` - Create single bot
- `POST /api/bots/batch-create` - Batch create bots
- `PUT /api/bots/{bot_id}` - Update bot
- `DELETE /api/bots/{bot_id}` - Delete bot

### Bot Lifecycle
- `POST /api/bots/{bot_id}/start` - Start bot trading
- `POST /api/bots/{bot_id}/pause` - Pause bot
- `POST /api/bots/{bot_id}/resume` - Resume bot
- `POST /api/bots/{bot_id}/stop` - Stop bot permanently
- `POST /api/bots/{bot_id}/cooldown` - Set cooldown period
- `GET /api/bots/{bot_id}/status` - Get bot status with performance
- `POST /api/bots/pause-all` - Pause all user bots
- `POST /api/bots/resume-all` - Resume all user bots

### Bot Promotion
- `POST /api/bots/{bot_id}/promote` - Promote bot to live trading
- `GET /api/bots/{bot_id}/promotion-status` - Check promotion eligibility
- `GET /api/bots/eligible-for-promotion` - List eligible bots
- `POST /api/bots/confirm-live-switch` - Confirm live trading switch
- `POST /api/bots/evolve` - Trigger bot DNA evolution

---

## Trading & Orders

### Trades
- `GET /api/trades/recent` - Get recent trades
- `GET /api/analytics/profit-history` - Profit history

### Prices
- `GET /api/prices/live` - Get live crypto prices
- `GET /api/wallet/deposit-address` - Get deposit address (placeholder)

### Advanced Orders
- `POST /api/orders/stop-loss` - Create stop-loss order
- `POST /api/orders/trailing-stop` - Create trailing stop order

### Trading Modes
- `POST /api/trading/paper/start` - Start paper trading
- `POST /api/trading/live/start` - Start live trading (requires confirmation)

---

## Ledger & Accounting

### Portfolio
- `GET /api/portfolio/summary` - Portfolio summary from ledger
- `GET /api/wallet/mode-stats` - Paper/live mode wallet stats
- `GET /api/overview/mode-stats` - Separate paper/live statistics

### Profits & PnL
- `GET /api/profits` - Profit time series (daily/weekly/monthly)
- `GET /api/analytics/countdown-to-million` - Countdown to R1M with projections
- `GET /api/countdown/status` - Countdown status (alias)

### Ledger Queries
- `GET /api/ledger/fills` - Query fill records
- `GET /api/ledger/audit-trail` - Get audit trail
- `POST /api/ledger/funding` - Record funding event

---

## Limits & Circuit Breaker

### Limits Configuration
- `GET /api/limits/config` - Get current limits configuration
- `GET /api/limits/usage` - Check usage against limits
- `GET /api/limits/health` - Overall limits health status

### Circuit Breaker
- `POST /api/limits/circuit-breaker/check` - Manual circuit breaker check
- `GET /api/limits/quarantined` - List quarantined bots
- `POST /api/limits/quarantine/reset/{bot_id}` - Reset quarantined bot

---

## Analytics & Reporting

### Analytics
- `GET /api/overview` - Dashboard overview
- `GET /api/metrics` - Metrics (alias for overview)
- `GET /api/analytics/pnl_timeseries` - PnL timeseries
- `GET /api/analytics/capital_breakdown` - Capital breakdown
- `GET /api/analytics/performance_summary` - Performance summary

### Reports
- `POST /api/reports/daily/send-test` - Send test daily report
- `POST /api/reports/daily/send-all` - Send reports to all users (admin)
- `GET /api/reports/daily/config` - Get SMTP configuration

### Performance
- `GET /api/autonomous/performance-rankings` - Get bot performance rankings

---

## AI & Chat

### Chat
- `POST /api/chat` - Send message to AI (includes command router)
- `GET /api/chat/history` - Get chat history

### AI Commands (Natural Language)
Trigger these via chat interface:
- Bot lifecycle: "start bot X", "pause bot X", "resume bot X", "stop bot X"
- Emergency: "emergency stop"
- Status: "show portfolio", "show profits", "status of bot X"
- Reinvest: "reinvest" (paper only)
- Admin: "send test report" (admin only)

### AI Features
- `GET /api/insights/daily` - Get AI-generated daily insights
- `GET /api/ml/predict/{pair}` - ML-based price prediction
- `GET /api/ml/sentiment/{pair}` - Sentiment analysis
- `GET /api/ml/anomalies` - Detect anomalous patterns

---

## Admin

### User Management
- `GET /api/admin/users` - Get all users
- `GET /api/admin/user-profile/{user_email}` - Get user profile
- `DELETE /api/admin/users/{user_id}` - Delete user
- `PUT /api/admin/users/{user_id}/block` - Block/unblock user
- `PUT /api/admin/users/{user_id}/password` - Change user password (admin)

### System Admin
- `GET /api/admin/backend-health` - Comprehensive backend health
- `GET /api/admin/system-stats` - System statistics
- `GET /api/admin/health-check` - System health check
- `GET /api/admin/storage` - Get storage usage per user
- `POST /api/admin/emergency-stop` - EMERGENCY: Stop all trading
- `POST /api/admin/email-all-users` - Email all users
- `POST /api/admin/test-email` - Send test email

### Monitoring
- `GET /api/admin/bodyguard-status` - AI Bodyguard status
- `GET /api/admin/ai-learning-status` - AI learning status

---

## System & Health

### System Modes
- `GET /api/system/mode` - Get current system mode states
- `PUT /api/system/mode` - Update system mode

### Autopilot
- `GET /api/autopilot/settings` - Get autopilot settings
- `POST /api/autopilot/enable` - Enable autopilot
- `POST /api/autopilot/disable` - Disable autopilot
- `POST /api/autonomous/reallocate-capital` - Manually trigger capital reallocation
- `POST /api/autonomous/reinvest-profits` - Manually trigger profit reinvestment
- `POST /api/autonomous/promote-bots` - Manually trigger bot promotion check

### Autonomous Systems
- `POST /api/autonomous/learning/trigger` - Trigger AI learning analysis
- `POST /api/autonomous/bodyguard/system-check` - Run system health check
- `GET /api/autonomous/market-regime` - Get market regime

---

## API Keys

### Key Management
- `GET /api/api-keys` - List saved API keys (masked)
- `POST /api/api-keys` - Create/update API key
- `POST /api/api-keys/{provider}/test` - Test API key connection
- `DELETE /api/api-keys/{provider}` - Delete API key

---

## External Integrations

### FLOKx
- `GET /api/flokx/test-connection` - Test FLOKx connection
- `GET /api/flokx/coefficients/{pair}` - Get market intelligence coefficients
- `POST /api/flokx/create-alert` - Create alert from FLOKx intelligence
- `GET /api/flokx/alerts` - Get FLOKx market alerts

### Fetch.ai
- `GET /api/fetchai/test-connection` - Test Fetch.ai connection
- `GET /api/fetchai/signals/{pair}` - Get market signals
- `GET /api/fetchai/recommendation/{pair}` - Get trading recommendation

---

## Backtesting

- `POST /api/backtest/strategy` - Backtest a trading strategy

---

## Routers Mounted in Server

The following routers are mounted in `server.py`:

1. **api_router** - Core endpoints (prefix: `/api`)
2. **phase5_router** - Phase 5 features
3. **phase6_router** - Phase 6 features
4. **phase8_router** - Phase 8 features
5. **capital_router** - Capital tracking
6. **emergency_router** - Emergency stop
7. **wallet_router** - Wallet management
8. **health_router** - Health checks
9. **admin_router** - Admin functions
10. **bot_lifecycle_router** - Bot lifecycle management
11. **system_limits_router** - System limits
12. **live_gate_router** - Live trading gate
13. **analytics_router** - Analytics
14. **ai_chat_router** - AI chat
15. **twofa_router** - Two-factor authentication
16. **genetic_router** - Genetic algorithm
17. **dashboard_router** - Dashboard endpoints
18. **api_key_mgmt_router** - API key management
19. **daily_report_router** - Daily reports
20. **ledger_router** - Ledger endpoints
21. **order_router** - Order pipeline
22. **alerts_router** - Alerts
23. **limits_router** - Limits management (NEW)
24. **system_router** - System endpoints
25. **trades_router** - Trades endpoints
26. **realtime_router** - Real-time SSE

---

## Authentication

Most endpoints require JWT authentication via Bearer token:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/endpoint
```

Get token via `/api/auth/login` endpoint.

---

## Rate Limiting

Rate limits are enforced per exchange:
- **Binance**: 1200 requests/minute
- **Luno**: 60 requests/minute
- **KuCoin**: 1800 requests/minute
- **Kraken**: 15 requests/second
- **VALR**: 120 requests/minute

Burst protection limits orders per exchange (configurable).

---

## WebSocket Events

WebSocket sends real-time events:
- `trade_executed` - Trade completed
- `bot_created` - Bot created
- `bot_status_changed` - Bot status changed
- `chat_message` - AI chat response
- `system_mode_update` - System mode changed
- `force_refresh` - UI should refresh
- `command_executed` - AI command completed (NEW)

---

## Environment Variables

Key configuration variables:

```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=<your-secret>

# AI
OPENAI_API_KEY=<your-key>

# SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<your-email>
SMTP_PASSWORD=<your-password>
DAILY_REPORT_TIME=08:00

# Limits
MAX_TRADES_PER_BOT_DAILY=50
MAX_TRADES_PER_USER_DAILY=500
MAX_DRAWDOWN_PERCENT=0.20
MAX_DAILY_LOSS_PERCENT=0.10
MAX_CONSECUTIVE_LOSSES=5
MAX_ERRORS_PER_HOUR=10

# Fee Coverage
MIN_EDGE_BPS=10
SAFETY_MARGIN_BPS=5
SLIPPAGE_BUFFER_BPS=10

# Features
ENABLE_REALTIME=true
USE_ORDER_PIPELINE=true
```

---

## Testing

```bash
# Run all tests
cd backend
source venv/bin/activate
pytest tests/ -v

# Run specific test suites
pytest tests/test_production_features.py -v
pytest tests/test_ledger_phase1.py -v
pytest tests/test_order_pipeline_phase2.py -v
```

---

## Support

For issues and questions:
1. Check logs: `journalctl -u amarktai-api -f`
2. Review configuration: `.env` and nginx config
3. Run smoke tests: `bash deployment/smoke_test.sh`
4. Check API docs: `http://localhost:8000/docs`

---

**End of Endpoint Reference**
