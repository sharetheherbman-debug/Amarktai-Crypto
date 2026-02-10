# Feature Inventory (Source of Truth)

This document lists every user-visible feature and the canonical backend endpoints.
All realtime updates must be sourced from the WebSocket/SSE events listed below.

## ✅ Supported Exchanges (Exactly 7)
- luno
- binance
- kucoin
- bybit
- kraken
- bitget
- gate

## �� Authentication
- Login: `POST /api/auth/login` → `{access_token, token_type}`
- Register: `POST /api/auth/register` (invite code supported via header)
- Me/Profile: `GET /api/auth/me`, `PUT /api/auth/profile`
- Logout: client-side token removal

## 📊 Dashboard Overview
- Overview metrics: `GET /api/overview`
- Consolidated dashboard overview: `GET /api/dashboard/overview`
- Snapshot (single source of truth): `GET /api/overview/snapshot`
- Tiles include: total profit, today profit, trades, win rate, active/paused bots, system mode, last trade time, risk lock status.

## 💹 Live Prices
- Endpoint: `GET /api/prices/live` (auth required)
- Response: array of `{pair, price, change_24h, last_update, source}`
- Pairs shown in UI: BTC/ZAR, ETH/ZAR, XRP/ZAR
- Refresh cadence: frontend polling every 5 seconds + realtime events

## 🤖 Bots (CRUD + Lifecycle)
- List bots: `GET /api/bots/status`
- Create bot: `POST /api/bots`
- Batch create: `POST /api/bots/batch-create`
- Update bot: `PUT /api/bots/{bot_id}`
- Delete bot: `DELETE /api/bots/{bot_id}`
- Start bot: `POST /api/bots/{bot_id}/start`
- Pause bot: `POST|PUT /api/bots/{bot_id}/pause`
- Resume bot: `POST|PUT /api/bots/{bot_id}/resume`
- Resume all (risk-gated): `POST /api/risk/resume-all`
- Promotion status: `GET /api/bots/{bot_id}/promotion-status`
- Promote to live: `POST /api/bots/{bot_id}/promote`

### Bot Status Fields (UI Contract)
Each bot item includes:
- `status`, `state`, `trading_mode`, `risk_mode`
- `paused_reason_code`, `paused_reason_message`, `paused_next_action`
- `paused_at`, `paused_by_user`, `paused_by_system`
- `quarantine_release_at`, `quarantine_remaining_seconds`
- `training_in_progress`, `training_failed_reason`

## 🎓 Bot Training + Quarantine
- Training queue: `GET /api/training/queue`
- Training reports: `GET /api/training/report/{bot_id}`
- Unified training/quarantine view: `GET /api/training-quarantine/bots`
- Quarantine status: `GET /api/quarantine/status`
  - Returns reason + `retraining_until` + `remaining_seconds`

## 🛡️ Risk Locks + Safety Gates
- Daily loss lock: `GET /api/risk/daily-loss-lock`
- Reset daily loss lock (admin): `POST /api/risk/daily-loss-lock/reset?confirmation=RESET_RISK_LOCK`
- Consolidated risk status: `GET /api/risk/status`
  - `daily_loss_lock`, `emergency_stop`, `bodyguard_lock`, `quarantine_active`
- Emergency stop controls: `POST /api/system/emergency-stop`, `POST /api/system/emergency-resume`

## ⚙️ System Modes
- System mode flags: `GET /api/system/mode`
- Update mode flags: `PUT /api/system/mode`
- System health: `GET /api/system/status`

## 🔑 API Keys
- Providers list: `GET /api/keys/providers`
- Status map: `GET /api/keys/status`
- List (masked): `GET /api/keys/list`
- Save: `POST /api/keys/save`
- Test: `POST /api/keys/test`
- Delete: `DELETE /api/keys/{provider}`
- UI displays `last_test_error` and `updated_at`

## 🧑‍💼 Admin Panel
- Unlock (AI chat command): `POST /api/admin/unlock`
- Admin overview: `GET /api/admin/overview`
- Admin users list: `GET /api/admin/users`
- Admin bots list: `GET /api/admin/bots`
- Admin system stats: `GET /api/admin/system-stats`
- Admin actions: block/unblock/reset/delete, bot mode/exchange changes
- Start fresh: `POST /api/admin/start-fresh`
- API key migration: `POST /api/admin/migrate-api-keys`

## 💼 Wallet + Transfers
- Wallet balances: `GET /api/wallet/balances`
- Deposit address: `GET /api/wallet/deposit-address`
- Transfer state machine: `POST /api/wallet/transfer`
- Diagnostics: `GET /api/diagnostics/wallet-status`
- Idempotency keys and approvals enforced in transfer state machine

## 📈 Reports + Analytics
- Profit history: `GET /api/analytics/profit-history`
- Performance summary: `GET /api/analytics/performance`
- Countdown to R1M: `GET /api/analytics/countdown-to-million`
- Equity/Drawdown/Win rate: `GET /api/analytics/equity`, `/api/analytics/drawdown`, `/api/analytics/win_rate`
- Daily report emails: `services/email_alerts.py` (scheduler driven)

## 🤖 AI Chat Actions
- Chat: `POST /api/ai/chat`
- History: `GET /api/ai/chat/history`
- Clear: `POST /api/ai/chat/clear`
- AI actions include emergency stop, show admin, training triggers

## 🤖 Autopilot + Scheduler
- Autopilot enable/disable: `POST /api/autopilot/enable`, `POST /api/autopilot/disable`
- Autopilot actions broadcast over realtime events

## 📡 Realtime (WebSocket/SSE)
- WebSocket: `GET /api/ws?token=JWT` or `Authorization: Bearer <token>`
- SSE: `GET /api/realtime/events` (auth required, fallback)
- Reconnect: client reconnects and calls `refreshAll()` after connect

### Realtime Event Types (Payloads)
- `connection`: `{status, mode}`
- `live_prices`: `{prices}` (array or normalized map)
- `metrics`: `{payload}`
- `overview_updated`: `{overview}`
- `bot_created|bot_updated|bot_deleted|bot_status_changed`: bot updates
- `bot_paused|bot_resumed`: `{bot, message}`
- `trade_executed`: `{trade, bot_id, bot_name}`
- `profit_updated`: `{total_profit}`
- `system_mode_update`: `{modes}`
- `api_key_update|key_saved|key_tested|key_deleted`: key updates
- `autopilot_action`, `self_healing`, `countdown_update`, `ai_evolution`, `system_update`
- `force_refresh`: instructs client to reload all data

### Realtime Coverage Targets
- Overview tiles, prices, bot lifecycle, quarantine, admin lists, API key status
- Risk lock banners, wallet balances, reports, scheduler/autopilot actions

## 📊 Metrics/Prometheus
- Prometheus metrics: `GET /metrics` (if enabled)

## 🧠 Paper Trading Realism
- Paper trading uses real market price feeds and ledger entries.
- Slippage, fees, precision clamps, rate limits enforced by paper engine.
- If trading blocked, UI displays reason and next action from bot/risk endpoints.
