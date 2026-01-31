# Amarktai Network - Frontend

Production-ready React frontend (CRA/CRACO) for the Amarktai Network trading platform. Integrates with the backend API at `https://amarktai.online` with real-time WebSocket/SSE dashboard updates.

## Quick Start

```bash
# Install dependencies
npm install

# Development server
npm start

# Production build
npm run build
```

## Architecture

### API Integration

**Base URL**: `/api` (proxied by nginx to backend)

All API calls use the unified client in `src/lib/apiClient.js`:
- Automatic JWT authentication via `Authorization: Bearer <token>` header
- Retry logic with exponential backoff
- Consistent error normalization (displays backend `detail` field where present)

### Real-Time System

The frontend supports **WebSocket (primary)** with **SSE fallback** and **polling** as a last resort:

1. **WebSocket**: `wss://amarktai.online/api/ws?token=<JWT>`
   - Ping/pong every 20 seconds
   - Auto-reconnect with backoff (max 5 attempts)
   - On failure → SSE fallback

2. **SSE**: `GET /api/realtime/events` (Bearer auth)
   - Server-Sent Events for one-way streaming
   - On failure → polling fallback

3. **Polling**: Falls back to REST endpoints every 5-30s

**Real-time Client**: `src/lib/realtime.js`

### Supported Providers

**Exchanges (7)**:
- luno
- binance
- kucoin
- bybit
- kraken
- bitget
- gate

**AI Providers (3)**:
- openai
- flokx
- fetchai

All defined in `src/constants/platforms.js` (single source of truth)

## API Endpoints

### Authentication
```
POST /api/auth/login
  → { access_token, token }
```

### System
```
GET /api/system/status
  → { feature_flags, scheduler_status, database, trading_activity }

GET /api/system/since-last-login
  → { last_login, notes[], active_bots, paperTrading, liveTrading }
```

### API Keys
```
GET  /api/keys/list
  → { keys: [{provider, status, status_display}] }

GET  /api/keys/providers
  → { providers: [{ id, name, required_fields }] }

POST /api/keys/save
  body: { provider, api_key, api_secret?, passphrase? }

POST /api/keys/test
  body: { provider }

DELETE /api/keys/{provider}
```

### Trades
```
GET /api/trades/recent?limit=50
  → { trades: [{id, symbol, side, quantity, price, pnl, platform, status, timestamp}] }

GET /api/trades/metrics
  → { total_pnl, total_fees, win_rate }
```

### Real-Time
```
WebSocket: wss://amarktai.online/api/ws?token=<JWT>
  Messages: { type, data, timestamp }
  Types: trades, bots, balances, metrics, system_health

SSE: GET /api/realtime/events (Authorization: Bearer <JWT>)
  Events: heartbeat, overview_update, bot_update, trade_update
```

## Key Components

- **Dashboard** (`src/pages/Dashboard.js`): Main trading interface
- **LiveTradesPanel** (`src/components/LiveTradesPanel.js`): Real-time trade feed
- **AIChatPanel** (`src/components/AIChatPanel.js`): AI assistant with daily reports
- **APIKeySettings** (`src/components/APIKeySettings.js`): Key management for all 10 providers

## Features

### Real-Time Updates
- WebSocket-first with SSE/polling fallback
- Automatic reconnection with exponential backoff
- Live trades, bot status, system health

### AI Chat
- Fresh start on each login/refresh (no localStorage persistence)
- Daily report from `/api/system/since-last-login` shown once per day
- Optional "Load Previous Chat" button

### System Overview
- Calls `/api/system/status` to show:
  - Database connection status
  - Feature flags
  - Scheduler status & errors
  - Trading activity (active bots, last trade)

### API Key Management
- All 10 providers (3 AI + 7 exchanges)
- Save, test, delete operations
- Proper field validation (api_key + api_secret + passphrase where required)

## Build & Deploy

```bash
# Production build
npm run build

# Output: build/ directory ready for deployment
```

The build is optimized and minified, ready to be served behind nginx at `https://amarktai.online`.

## Development

```bash
# Start dev server
npm start
# → http://localhost:3000

# Build production
npm run build
```

## Environment

- **Node**: >= 20.0.0
- **Framework**: React 19 (CRA + CRACO)
- **UI**: Radix UI + Tailwind CSS
- **Charts**: Chart.js + Recharts
- **HTTP**: Axios
- **Routing**: React Router v7

## License

Proprietary - Amarktai Network
