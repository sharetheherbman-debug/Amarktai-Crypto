# Complete API Endpoints Reference

Comprehensive documentation of all API endpoints in the Amarktai Network Adaptive Paper Trading System.

## Table of Contents

1. [Authentication](#authentication)
2. [Ledger & Portfolio](#ledger--portfolio)
3. [Order Execution](#order-execution)
4. [Bot Lifecycle](#bot-lifecycle)
5. [Limits & Circuit Breaker](#limits--circuit-breaker)
6. [Daily Reinvestment](#daily-reinvestment)
7. [Reports](#reports)
8. [AI Chat](#ai-chat)
9. [System Management](#system-management)

---

## Authentication

### Register User
```http
POST /api/auth/register
```
**Request Body:**
```json
{
  "first_name": "John",
  "email": "user@example.com",
  "password": "password123",
  "invite_code": "optional_invite_code"
}
```
**Notes:**
- `password` is preferred (sent as plain text, hashed server-side)
- `password_hash` is supported for backward compatibility (also treated as plain password)
- Exactly one of `password` or `password_hash` must be provided
- `invite_code` can also be provided via `X-Invite-Code` header
- Email is normalized to lowercase

**Response:**
```json
{
  "access_token": "jwt_token_here",
  "token_type": "bearer",
  "token": "jwt_token_here",
  "user": { "id": "...", "email": "...", "first_name": "..." }
}
```
**Note:** Both `access_token` (standard) and `token` (legacy) are provided for backward compatibility.

### Login
```http
POST /api/auth/login
```
**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```
**Response:**
```json
{
  "access_token": "jwt_token_here",
  "token_type": "bearer",
  "token": "jwt_token_here",
  "user": { "id": "...", "email": "..." }
}
```
**Note:** Both `access_token` (standard) and `token` (legacy) are provided for backward compatibility.

### Get Current User
```http
GET /api/auth/me
```
**Headers:** `Authorization: Bearer {token}`

---

## Ledger & Portfolio

### Portfolio Summary
```http
GET /api/portfolio/summary
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "equity": 10500.50,
  "realized_pnl": 1500.00,
  "unrealized_pnl": 200.50,
  "fees_total": 150.00,
  "net_pnl": 1550.50,
  "drawdown_current": 5.00,
  "drawdown_max": 15.00,
  "total_fills": 100,
  "total_volume": 50000.00,
  "data_source": "ledger",
  "phase": "1_read_only"
}
```

**Description:** Returns complete portfolio metrics from immutable ledger. Single source of truth for all financial data.

### Get Profits Time Series
```http
GET /api/profits?period={period}&limit={limit}
```
**Headers:** `Authorization: Bearer {token}`
**Parameters:**
- `period` (string): "daily", "weekly", or "monthly"
- `limit` (integer): Number of periods to return (default: 30)

**Response:**
```json
{
  "period": "daily",
  "limit": 30,
  "series": [
    {
      "date": "2025-01-15",
      "trades": 10,
      "fees": 15.50,
      "volume": 5000.00,
      "realized_pnl": 0,
      "net_profit": -15.50
    }
  ],
  "data_source": "ledger"
}
```

### Countdown to Target
```http
GET /api/countdown/status?target={target}
```
**Headers:** `Authorization: Bearer {token}`
**Parameters:**
- `target` (float): Target amount (default: 1000000)

**Response:**
```json
{
  "current_equity": 10500.50,
  "target": 1000000,
  "remaining": 989499.50,
  "progress_pct": 1.05,
  "avg_daily_profit_30d": 50.00,
  "days_to_target_linear": 19790,
  "days_to_target_compound": 2500,
  "data_source": "ledger"
}
```

### Query Fills
```http
GET /api/ledger/fills?bot_id={bot_id}&since={since}&until={until}&limit={limit}
```
**Headers:** `Authorization: Bearer {token}`
**Parameters:**
- `bot_id` (string, optional): Filter by bot ID
- `since` (ISO timestamp, optional): Start date
- `until` (ISO timestamp, optional): End date
- `limit` (integer): Max results (default: 100, max: 1000)

### Record Funding Event
```http
POST /api/ledger/funding
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "amount": 10000,
  "currency": "USDT",
  "description": "Initial capital deposit"
}
```

### Ledger Reconciliation
```http
GET /api/ledger/reconcile
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "status": "ok",
  "ledger_equity": 10500.50,
  "trades_equity": 10450.00,
  "discrepancy": 50.50,
  "discrepancy_pct": 0.48,
  "ledger_fills_count": 100,
  "trades_count": 98,
  "issues": ["Fill count mismatch"],
  "recommendations": ["Review ledger fills for missing entries"],
  "timestamp": "2025-01-15T12:00:00Z"
}
```

**Description:** Compares ledger-based accounting with legacy trades collection. Identifies discrepancies and provides recommendations.

### Verify Ledger Integrity
```http
GET /api/ledger/verify-integrity
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "status": "ok",
  "checks_passed": 6,
  "checks_failed": 0,
  "total_checks": 6,
  "issues": ["All integrity checks passed"],
  "details": {
    "total_fills": 100,
    "equity": 10500.50,
    "user_id": "user_123"
  },
  "timestamp": "2025-01-15T12:00:00Z"
}
```

**Description:** Performs comprehensive integrity checks on ledger data including equity recomputation, fee completeness, duplicate detection, and chronological ordering.

### Audit Trail
```http
GET /api/ledger/audit-trail?bot_id={bot_id}&limit={limit}
```
**Headers:** `Authorization: Bearer {token}`

---

## Order Execution

### Submit Order (4-Gate Pipeline)
```http
POST /api/orders/submit
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "bot_id": "bot_123",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "side": "buy",
  "amount": 1000.00,
  "order_type": "market",
  "price": null,
  "idempotency_key": "unique_key_123",
  "is_paper": true
}
```

**Response (Success):**
```json
{
  "success": true,
  "order_id": "order_456",
  "idempotency_key": "unique_key_123",
  "gates_passed": ["idempotency", "fee_coverage", "trade_limiter", "circuit_breaker"],
  "gate_failed": null,
  "rejection_reason": null,
  "execution_summary": {
    "total_cost_bps": 25.5,
    "has_coverage": true
  },
  "timestamp": "2025-01-15T12:00:00Z",
  "data_source": "order_pipeline",
  "phase": "2_guardrails"
}
```

**Response (Rejected):**
```json
{
  "success": false,
  "order_id": null,
  "gates_passed": ["idempotency", "fee_coverage"],
  "gate_failed": "trade_limiter",
  "rejection_reason": "Daily trade limit exceeded (50/50 trades)",
  "timestamp": "2025-01-15T12:00:00Z"
}
```

**Description:** All orders pass through 4 safety gates:
1. **Idempotency** - Prevents duplicate executions
2. **Fee Coverage** - Rejects unprofitable trades
3. **Trade Limiter** - Enforces bot/user/burst limits
4. **Circuit Breaker** - Auto-pauses on danger signals

### Get Order Status
```http
GET /api/orders/{order_id}/status
```
**Headers:** `Authorization: Bearer {token}`

### Get Pending Orders
```http
GET /api/orders/pending
```
**Headers:** `Authorization: Bearer {token}`

---

## Bot Lifecycle

### List Bots
```http
GET /api/bots
```
**Headers:** `Authorization: Bearer {token}`

### Create Bot
```http
POST /api/bots
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "name": "My Trading Bot",
  "exchange": "binance",
  "risk_mode": "safe",
  "initial_capital": 1000.00,
  "trading_mode": "paper"
}
```

### Start Bot
```http
POST /api/bots/{bot_id}/start
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "message": "Bot 'My Trading Bot' started successfully",
  "bot": {
    "id": "bot_123",
    "status": "active",
    "started_at": "2025-01-15T12:00:00Z"
  }
}
```

### Pause Bot
```http
POST /api/bots/{bot_id}/pause
```
**Headers:** `Authorization: Bearer {token}`
**Request Body (optional):**
```json
{
  "reason": "Manual pause for maintenance"
}
```

### Resume Bot
```http
POST /api/bots/{bot_id}/resume
```
**Headers:** `Authorization: Bearer {token}`

### Stop Bot (Permanent)
```http
POST /api/bots/{bot_id}/stop
```
**Headers:** `Authorization: Bearer {token}`
**Request Body (optional):**
```json
{
  "reason": "Bot underperforming"
}
```

### Pause All Bots
```http
POST /api/bots/pause-all
```
**Headers:** `Authorization: Bearer {token}`

### Resume All Bots
```http
POST /api/bots/resume-all
```
**Headers:** `Authorization: Bearer {token}`

### Get Bot Status
```http
GET /api/bots/{bot_id}/status
```
**Headers:** `Authorization: Bearer {token}`

---

## Limits & Circuit Breaker

### Get Limits Configuration
```http
GET /api/limits/config
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "config": {
    "trade_limits": {
      "max_trades_per_bot_daily": 50,
      "max_trades_per_user_daily": 500,
      "burst_limit_orders": 10,
      "burst_limit_window_seconds": 10
    },
    "circuit_breaker": {
      "max_drawdown_percent": 0.20,
      "max_daily_loss_percent": 0.10,
      "max_consecutive_losses": 5,
      "max_errors_per_hour": 10
    },
    "fee_coverage": {
      "min_edge_bps": 10.0,
      "safety_margin_bps": 5.0,
      "slippage_buffer_bps": 10.0
    },
    "exchange_fees": {
      "binance": {"maker": 7.5, "taker": 10.0},
      "luno": {"maker": 20.0, "taker": 25.0}
    }
  },
  "timestamp": "2025-01-15T12:00:00Z"
}
```

### Get Limits Usage
```http
GET /api/limits/usage?bot_id={bot_id}
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "user_usage": {
    "trades_today": 150,
    "max_trades": 500,
    "usage_pct": 30.0,
    "remaining": 350
  },
  "bot_usage": [
    {
      "bot_id": "bot_123",
      "bot_name": "My Bot",
      "trades_today": 25,
      "max_trades": 50,
      "usage_pct": 50.0,
      "remaining": 25
    }
  ],
  "timestamp": "2025-01-15T12:00:00Z"
}
```

### Get Quarantined Bots
```http
GET /api/limits/quarantined
```
**Headers:** `Authorization: Bearer {token}`

### Reset Quarantined Bot
```http
POST /api/limits/quarantine/reset/{bot_id}
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "reason": "Issue investigated and resolved"
}
```

### Check Circuit Breaker Status
```http
GET /api/circuit-breaker/status?bot_id={bot_id}
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "is_tripped": false,
  "entity_type": "bot",
  "entity_id": "bot_123",
  "metrics": {
    "current_drawdown": 0.05,
    "daily_loss": 0.02,
    "consecutive_losses": 1,
    "errors_per_hour": 0
  },
  "thresholds": {
    "max_drawdown": 0.20,
    "max_daily_loss": 0.10,
    "max_consecutive_losses": 5,
    "max_errors_per_hour": 10
  },
  "timestamp": "2025-01-15T12:00:00Z"
}
```

### Reset Circuit Breaker
```http
POST /api/circuit-breaker/reset
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "bot_id": "bot_123",
  "reason": "Manual reset after review"
}
```

### Get Circuit Breaker History
```http
GET /api/circuit-breaker/history?bot_id={bot_id}&limit={limit}
```
**Headers:** `Authorization: Bearer {token}`

### Get Limits Health
```http
GET /api/limits/health
```
**Headers:** `Authorization: Bearer {token}`

---

## Daily Reinvestment

### Trigger Manual Reinvestment (Admin)
```http
POST /api/admin/reinvest/trigger
```
**Headers:** `Authorization: Bearer {token}`
**Request Body (optional):**
```json
{
  "user_id": "user_123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Reinvestment cycle triggered",
  "result": {
    "success": true,
    "user_id": "user_123",
    "total_profit": 900.00,
    "allocated_amount": 720.00,
    "allocation_per_bot": 240.00,
    "bots_allocated": 3,
    "allocations": [
      {
        "bot_id": "bot_1",
        "bot_name": "Top Bot 1",
        "allocated_amount": 240.00,
        "new_capital": 1240.00,
        "event_id": "event_123"
      }
    ],
    "timestamp": "2025-01-15T12:00:00Z",
    "message": "Successfully allocated 720.00 to 3 top bots"
  }
}
```

**Description:** Manually triggers the daily reinvestment cycle. If `user_id` is provided, runs for that user only; otherwise runs for all users.

### Get Reinvestment Status (Admin)
```http
GET /api/admin/reinvest/status
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "is_running": true,
  "daily_time": "02:00",
  "last_run": "2025-01-15T02:00:00Z",
  "config": {
    "reinvest_threshold": 500,
    "reinvest_top_n": 3,
    "reinvest_percentage": 80
  }
}
```

---

## Reports

### Send Test Daily Report
```http
POST /api/reports/daily/send-test
```
**Headers:** `Authorization: Bearer {token}`

**Response:**
```json
{
  "success": true,
  "message": "Test daily report sent to user@example.com"
}
```

### Send Daily Reports to All Users (Admin)
```http
POST /api/reports/daily/send-all
```
**Headers:** `Authorization: Bearer {token}`

### Get Report Configuration
```http
GET /api/reports/daily/config
```

**Response:**
```json
{
  "success": true,
  "config": {
    "enabled": true,
    "report_time": "08:00",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_from": "reports@amarktai.com",
    "smtp_configured": true
  }
}
```

---

## AI Chat

### Send Chat Message
```http
POST /api/chat
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "content": "show portfolio",
  "confirmed": false
}
```

**Response:** AI-generated response string

**Supported Commands:**
- Bot lifecycle: `start bot <name>`, `pause bot <name>`, `resume bot <name>`, `stop bot <name>`
- Bulk actions: `pause all bots`, `resume all bots`
- Emergency: `emergency stop` (requires confirmation)
- Status: `show portfolio`, `show profits`, `status of bot <name>`
- Reinvestment: `reinvest` (paper mode only, requires confirmation)
- Admin: `send test report` (admin only)

### Get Chat History
```http
GET /api/chat/history?limit={limit}
```
**Headers:** `Authorization: Bearer {token}`

---

## System Management

### Get System Health
```http
GET /api/health/ping
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T12:00:00Z"
}
```

### Get Health Indicators
```http
GET /api/health/indicators
```

### Get System Modes
```http
GET /api/system/mode
```
**Headers:** `Authorization: Bearer {token}`

### Update System Mode
```http
PUT /api/system/mode
```
**Headers:** `Authorization: Bearer {token}`
**Request Body:**
```json
{
  "mode": "paperTrading",
  "enabled": true
}
```

---

## Environment Variables

All environment variables for configuration:

### Required
- `MONGO_URL` - MongoDB connection string
- `JWT_SECRET` - JWT token secret (generate with `openssl rand -hex 32`)
- `OPENAI_API_KEY` - OpenAI API key for AI features

### Optional
- `SMTP_HOST` - SMTP server (default: smtp.gmail.com)
- `SMTP_PORT` - SMTP port (default: 587)
- `SMTP_USER` - SMTP username
- `SMTP_PASSWORD` - SMTP password
- `SMTP_FROM_EMAIL` - From email address
- `DAILY_REPORT_TIME` - Daily report time (default: "08:00" UTC)

### Trading Configuration
- `MAX_TRADES_PER_BOT_DAILY` - Bot daily limit (default: 50)
- `MAX_TRADES_PER_USER_DAILY` - User daily limit (default: 500)
- `BURST_LIMIT_ORDERS_PER_EXCHANGE` - Burst limit (default: 10)
- `BURST_LIMIT_WINDOW_SECONDS` - Burst window (default: 10)

### Circuit Breaker
- `MAX_DRAWDOWN_PERCENT` - Max drawdown (default: 0.20)
- `MAX_DAILY_LOSS_PERCENT` - Max daily loss (default: 0.10)
- `MAX_CONSECUTIVE_LOSSES` - Max losses (default: 5)
- `MAX_ERRORS_PER_HOUR` - Max errors (default: 10)

### Fee Coverage
- `MIN_EDGE_BPS` - Minimum edge (default: 10.0)
- `SAFETY_MARGIN_BPS` - Safety margin (default: 5.0)
- `SLIPPAGE_BUFFER_BPS` - Slippage buffer (default: 10.0)

### Reinvestment
- `REINVEST_THRESHOLD` - Min profit (default: 500)
- `REINVEST_TOP_N` - Top bots (default: 3)
- `REINVEST_PERCENTAGE` - Reinvest % (default: 80)
- `DAILY_REINVEST_TIME` - Reinvest time (default: "02:00" UTC)

---

## Router Prefixes in server.py

All routers are mounted with these prefixes:

```python
# Main API router
app.include_router(api_router, prefix="/api")

# Additional routers (all under /api)
- ledger_router (ledger_endpoints.py)
- order_router (order_endpoints.py)
- bot_lifecycle_router (bot_lifecycle.py)
- limits_router (limits_management.py)
- daily_report_router (daily_report.py)
- phase5_router, phase6_router, phase8_router
- capital_router, emergency_router, wallet_router
- health_router, admin_router, analytics_router
- ai_chat_router, twofa_router, genetic_router
- dashboard_router, api_key_mgmt_router, alerts_router
- system_router, trades_router, realtime_router
```

All endpoints are accessible under the `/api` prefix.

---

## Rate Limits

- **Per Bot**: 50 trades/day
- **Per User**: 500 trades/day
- **Burst Protection**: 10 orders per 10 seconds per exchange
- **Circuit Breaker**: Auto-triggers on excessive drawdown, losses, or errors

---

## Error Codes

- `400` - Bad Request (validation errors)
- `401` - Unauthorized (missing or invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found (resource doesn't exist)
- `402` - Payment Required (insufficient capital)
- `500` - Internal Server Error
- `429` - Too Many Requests (rate limit exceeded)

---

**Version:** 3.2.0 - Adaptive Paper Trading System
**Last Updated:** December 2025
