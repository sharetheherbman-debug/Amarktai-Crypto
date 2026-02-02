# Amarktai Network - Production Deployment Guide

## Overview

This repository provides a **production-grade, plug-and-play deployment** for the Amarktai Network trading platform. After `git pull`, configuring `.env`, and restarting services, everything works in real-time with zero manual intervention.

## System Requirements

- **Operating System**: Ubuntu 24.04 LTS
- **Python**: 3.10+
- **Node.js**: 18+ (for frontend)
- **MongoDB**: 6.0+
- **Nginx**: 1.24+
- **Systemd**: For service management

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Frontend (/)          Backend API (/api)           │  │
│  │  Static assets         WebSocket (/api/ws)          │  │
│  │  /assets/...           SSE (/api/realtime/events)   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────┐
        │      FastAPI Backend                 │
        │  - Trading Scheduler                 │
        │  - Paper/Live Trading Engines        │
        │  - Autonomous Systems (AI)           │
        │  - WebSocket Manager                 │
        │  - Real-time Events                  │
        └──────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    MongoDB      │
                    │  - Users        │
                    │  - Bots         │
                    │  - Trades       │
                    │  - API Keys     │
                    └─────────────────┘
```

## Quick Start

### 1. Clone Repository

```bash
cd /var/www
git clone https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment.git amarktai
cd amarktai
```

### 2. Configure Environment

Create `.env` file in the root directory:

```bash
cp .env.example .env
nano .env
```

Required environment variables:

```env
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=your-secret-key-change-in-production-min-32-chars

# AI / OpenAI
OPENAI_API_KEY=sk-...

# Email (SMTP) - Optional but recommended
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com
FROM_NAME=Amarktai Network

# Optional Integrations
FETCHAI_API_KEY=
FLOKX_API_KEY=

# Real-time features (default: enabled)
ENABLE_REALTIME=true
```

### 3. Install Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Or use the installation script:

```bash
./deployment/install_backend.sh
```

### 4. Build Frontend

```bash
./deployment/build_frontend.sh
```

### 5. Configure Systemd Service

Copy the systemd service file:

```bash
sudo cp deployment/amarktai-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable amarktai-api
sudo systemctl start amarktai-api
```

Check status:

```bash
sudo systemctl status amarktai-api
```

### 6. Configure Nginx

Copy the nginx configuration:

```bash
sudo cp deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Verify Deployment

Run the smoke test:

```bash
./deployment/smoke_test.sh
```

Expected output:
```
✅ API Health: OK
✅ Database: Connected
✅ WebSocket: Ready
✅ SSE: Enabled
```

## API Endpoints

### Core Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health/ping` | Simple health check |
| GET | `/api/health/indicators` | Comprehensive health indicators |
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/login` | User login |
| GET | `/api/auth/me` | Get current user |
| GET | `/api/bots` | List all bots |
| POST | `/api/bots` | Create new bot |
| POST | `/api/bots/{bot_id}/pause` | Pause bot trading |
| POST | `/api/bots/{bot_id}/resume` | Resume bot trading |
| GET | `/api/overview` | Dashboard overview |
| GET | `/api/trades/recent` | Recent trades |

### WebSocket

Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket(`ws://${location.host}/api/ws?token=${authToken}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Real-time update:', data);
};
```

### Server-Sent Events (SSE)

Subscribe to SSE for live data streams:

```javascript
const eventSource = new EventSource(`/api/realtime/events?token=${authToken}`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Live data:', data);
};
```

## Trading System

### Paper Trading Mode

Safe simulation mode using real market data:

- Real prices from LUNO/Binance/KuCoin
- Realistic fee simulation (0.1-0.25%)
- Slippage modeling (0.1-0.2%)
- Order failure rate (3%)
- 95% accuracy compared to live trading

### Live Trading Mode

Real exchange orders with full risk management:

- Per-user encrypted API keys stored in MongoDB
- Exchange rate limit enforcement
- Budget allocation per bot (fair distribution)
- Stop loss / take profit automation
- Circuit breakers for anomaly detection

### Budget Management

Trade budgets are allocated fairly:

```python
# If 1 bot per exchange → gets full daily budget
# If N bots per exchange → each gets floor(budget/N)

# Example: Binance with 750 trades/day limit
# - 10 bots → each gets 75 trades/day
# - 5 bots → each gets 150 trades/day
```

Exchange limits (from official docs):

- **Binance**: 200,000 orders/24h, 100 orders/10s
- **KuCoin**: 45 orders/3s
- **LUNO**: 300 requests/min
- **Kraken**: 15-20 requests/second (tier-based)
- **VALR**: 100 requests/10s

## Bot Management

### Bot Lifecycle States

- **Active**: Bot is trading
- **Paused**: Bot temporarily stopped (by user or system)
- **Stopped**: Bot permanently stopped

### Pause/Resume Bots

```bash
# Pause a specific bot
curl -X POST http://localhost:8000/api/bots/{bot_id}/pause \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manual maintenance"}'

# Resume a bot
curl -X POST http://localhost:8000/api/bots/{bot_id}/resume \
  -H "Authorization: Bearer $TOKEN"

# Pause all bots
curl -X POST http://localhost:8000/api/bots/pause-all \
  -H "Authorization: Bearer $TOKEN"
```

### Cooldown Periods

Set custom cooldown between trades:

```bash
curl -X POST http://localhost:8000/api/bots/{bot_id}/cooldown \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cooldown_minutes": 30}'
```

Valid range: 5-120 minutes

## Real-time Events

The system broadcasts events via WebSocket:

- `bot_created` - New bot created
- `bot_paused` - Bot paused
- `bot_resumed` - Bot resumed
- `trade_executed` - Trade completed
- `profit_updated` - Profit changed
- `system_mode_update` - Trading mode changed
- `force_refresh` - Dashboard refresh required

## Autonomous Systems

The following autonomous systems run automatically:

1. **Trading Scheduler** - Executes bot trades with staggered timing
2. **Autopilot Engine** - Auto-manages capital and bot spawning
3. **AI Bodyguard** - Detects and pauses rogue bots
4. **Self-Healing** - Recovers from errors automatically
5. **AI Learning** - Learns from trade performance
6. **Bot Lifecycle** - Promotes successful paper bots to live

## Monitoring

### View Logs

```bash
# Backend logs
sudo journalctl -u amarktai-api -f

# Nginx logs
sudo tail -f /var/log/nginx/amarktai_access.log
sudo tail -f /var/log/nginx/amarktai_error.log
```

### System Health

Check comprehensive health:

```bash
curl http://localhost:8000/api/health/indicators
```

Response:
```json
{
  "timestamp": "2025-12-18T17:00:00Z",
  "overall_status": "healthy",
  "overall_rtt": 45.2,
  "indicators": {
    "api": {"status": "healthy", "response_time": 12.5},
    "database": {"status": "healthy", "response_time": 32.7},
    "websocket": {"status": "healthy", "active_connections": 5},
    "sse": {"status": "healthy", "active_streams": 3}
  }
}
```

## Troubleshooting

### Backend won't start

Check logs:
```bash
sudo journalctl -u amarktai-api -n 50
```

Common issues:
- MongoDB not running: `sudo systemctl start mongod`
- Port 8000 in use: `sudo lsof -i :8000`
- Missing dependencies: `pip install -r backend/requirements.txt`

### WebSocket connection fails

Check nginx configuration:
```bash
sudo nginx -t
```

Ensure WebSocket upgrade headers are present:
```nginx
location /api/ws {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### Trading not executing

Check system modes:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/system/mode
```

Ensure `autopilot` or `paperTrading` is enabled.

## Backup and Recovery

### Database Backup

```bash
mongodump --db amarktai_trading --out /backup/$(date +%Y%m%d)
```

### Restore Database

```bash
mongorestore --db amarktai_trading /backup/20250101/amarktai_trading
```

### Configuration Backup

```bash
cp .env .env.backup.$(date +%Y%m%d)
```

## Updates and Maintenance

### Pull Latest Changes

```bash
cd /var/www/amarktai
git pull origin main
```

### Restart Services

```bash
# Restart backend
sudo systemctl restart amarktai-api

# Rebuild frontend if needed
./deployment/build_frontend.sh

# Reload nginx
sudo systemctl reload nginx
```

### Database Migrations

```bash
cd backend
python migrations/add_lifecycle_fields.py
```

## Security Best Practices

1. **JWT Secret**: Use a strong, random 32+ character secret
2. **API Keys**: Store encrypted in MongoDB, never in code
3. **HTTPS**: Always use SSL/TLS in production
4. **Firewall**: Only expose ports 80 and 443
5. **MongoDB**: Bind to localhost only, use authentication
6. **Backups**: Daily automated backups to separate storage
7. **Updates**: Keep all dependencies up to date

## Performance Tuning

### MongoDB Indexes

Ensure indexes are created:

```javascript
db.trades.createIndex({ user_id: 1, timestamp: -1 });
db.bots.createIndex({ user_id: 1, status: 1 });
db.trades.createIndex({ bot_id: 1, timestamp: -1 });
```

### Nginx Caching

Add to nginx config:
```nginx
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### Backend Workers

For high traffic, use multiple workers:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```

Update systemd service to use workers.

## Support

For issues or questions:

- GitHub Issues: https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment/issues
- Documentation: This file
- Logs: Check systemd and nginx logs

## License

[Your License Here]

---

**Last Updated**: December 2025
**Version**: 3.0.0
