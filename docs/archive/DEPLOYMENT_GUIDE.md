> **⚠️ ARCHIVED DOCUMENT - NOT USED IN CURRENT RELEASE**
>
> This document is archived for historical reference only. It may contain outdated information, including references to VALR and OVEX exchanges which are NO LONGER supported.
>
> **Current Platform List**: luno, binance, kucoin, bybit, kraken, bitget, gate (7 exchanges)
>
> For current documentation, see the main docs/ folder and README.md.

---


# Production Deployment Guide

## Overview
This guide provides step-by-step instructions for deploying Amarktai Network on a fresh Ubuntu 24.04 VPS.

## Prerequisites
- Ubuntu 24.04 Server (fresh install)
- Root access (sudo)
- At least 2GB RAM, 20GB disk space
- Open ports: 80 (HTTP), 443 (HTTPS), 8000 (API - internal only)

## One-Command Installation

```bash
sudo bash deployment/install.sh
```

This script will:
1. Install all OS dependencies (Python 3.12, Node.js, Nginx, Redis, Docker)
2. Setup MongoDB via Docker
3. Create Python virtual environment and install requirements
4. Validate Python syntax with compileall
5. Configure and start systemd service
6. Run comprehensive smoke tests
7. Report PASS/FAIL status

## Manual Setup Steps

### 1. Clone Repository

```bash
git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment
```

### 2. Configure Environment

```bash
cp .env.example backend/.env
nano backend/.env
```

**Required Variables (MUST be set):**

```bash
# Database
MONGO_URL=mongodb://amarktai:amarktai2024@localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
INVITE_CODE=AMARKTAI2024

# Feature Flags (start safe, enable gradually)
ENABLE_TRADING=false
ENABLE_AUTOPILOT=false
ENABLE_CCXT=true
```

### 3. Run Installation

```bash
sudo bash deployment/install.sh
```

### 4. Verify Installation

```bash
# Check service status
sudo systemctl status amarktai-api.service

# Check logs
sudo journalctl -u amarktai-api.service -f

# Run smoke tests
bash tools/smoke_test.sh
```

## Post-Installation

### Configure Nginx Reverse Proxy

```bash
sudo cp deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Setup SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Create First Admin User

1. Register a user via API or frontend
2. Connect to MongoDB and set is_admin flag:

```bash
docker exec -it amarktai-mongo mongosh -u amarktai -p amarktai2024
use amarktai_trading
db.users.updateOne(
  { "email": "admin@example.com" },
  { $set: { "is_admin": true } }
)
```

## Platform Support

The system supports exactly **5 platforms**:

1. **Luno** - South African exchange
2. **Binance** - Global exchange
3. **KuCoin** - Global exchange (requires passphrase)
4. **OVEX** - South African exchange
5. **VALR** - South African exchange

Get platform info: `GET /api/platforms`

## API Key Management

### Supported Services
- Platforms: luno, binance, kucoin, ovex, valr
- AI: openai

### Encryption
All API keys are encrypted at rest using Fernet encryption.
**ENCRYPTION_KEY must be set in .env or the backend will fail.**

### Endpoints
- `GET /api/user/api-keys/{service}` - Get encrypted keys for service
- `POST /api/user/api-keys` - Save new API keys
- `DELETE /api/user/api-keys/{service}` - Remove keys
- `POST /api/user/api-keys/test` - Test key validity (future)

## Authentication

### Registration
- Endpoint: `POST /api/auth/register`
- Requires invite code (set in INVITE_CODE env var)
- Accepts both `name` (legacy) and `first_name`
- Returns: `{access_token, token_type:"bearer", token:<alias>, user:{...}}`
- **Never returns password fields**

### Login
- Endpoint: `POST /api/auth/login`
- Returns: Same structure as registration

### Profile
- `GET /api/auth/profile` - Get user profile (no password fields)
- `PUT /api/auth/profile` - Update profile

## Admin Access

### Admin Field
Users have an `is_admin` boolean field (no roles system).

### Admin Endpoints
Available at `/api/admin/*` (requires is_admin=true):
- User management
- Bot management
- System resources
- Per-user storage

## Mobile UI

Mobile users (screen width < 768px) see only:
- **Overview** - Dashboard with key metrics
- **AI Chat** - Chat interface for bot interaction

All other sections are hidden on mobile to maintain simplicity.

## Realtime Events

### Connection
- Endpoint: `/api/realtime/events` (WebSocket/SSE)
- Message format: `{type, ts, payload}`
- Supports heartbeat/ping for connection health
- Frontend reconnects with exponential backoff on disconnect

## Bodyguard System

The AI Bodyguard monitors trading performance and automatically pauses underperforming bots.

### States
- **ACTIVE** - Normal operation, monitoring trades
- **WATCH** - Performance degrading, increased monitoring
- **PAUSED** - Bot paused due to poor performance
- **BLOCKED** - Persistent losses, requires admin review

### Metrics Tracked
- Win rate
- Profit factor
- Average win/loss
- Max drawdown
- Winning/losing streaks

### Recovery
Bots can recover from PAUSED state after cooldown period and improved performance.
Admin can override and manually resume/unblock bots.

## Smoke Test

Run comprehensive validation:

```bash
bash tools/smoke_test.sh
```

**Tests performed:**
1. ✅ Health check (`/api/health/ping`)
2. ✅ Platform registry (exactly 5 platforms)
3. ✅ User registration with invite code
4. ✅ User login
5. ✅ Profile retrieval (no password leaks)
6. ✅ API key management endpoints
7. ✅ Realtime connectivity
8. ✅ Bodyguard status

**Exit codes:**
- 0 = PASS (all tests successful)
- 1 = FAIL (one or more tests failed)

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u amarktai-api.service -n 100

# Common issues:
# - MongoDB not running
# - Missing .env file
# - Invalid ENCRYPTION_KEY
# - Missing dependencies
```

### MongoDB connection failed
```bash
# Check MongoDB container
docker ps | grep amarktai-mongo

# Check logs
docker logs amarktai-mongo

# Restart if needed
docker restart amarktai-mongo
```

### Health check fails
```bash
# Wait 30 seconds after starting service
sleep 30
curl http://localhost:8000/api/health/ping

# If still fails, check if port is in use
sudo netstat -tlnp | grep 8000
```

### Smoke tests fail
```bash
# Run with verbose output
bash -x tools/smoke_test.sh

# Common issues:
# - Wrong INVITE_CODE
# - Service not fully started
# - Database not accessible
```

## Useful Commands

```bash
# Service management
sudo systemctl start amarktai-api
sudo systemctl stop amarktai-api
sudo systemctl restart amarktai-api
sudo systemctl status amarktai-api

# View logs
sudo journalctl -u amarktai-api -f       # Follow logs
sudo journalctl -u amarktai-api -n 100   # Last 100 lines

# Database
docker exec -it amarktai-mongo mongosh -u amarktai -p amarktai2024

# Backend shell
cd backend
source .venv/bin/activate
python  # Access to all modules
```

## Security Checklist

- [ ] JWT_SECRET changed from default
- [ ] ENCRYPTION_KEY generated and set
- [ ] INVITE_CODE set (or registration disabled)
- [ ] MongoDB password changed
- [ ] Firewall configured (only 80/443 open)
- [ ] SSL certificates installed
- [ ] First admin user created
- [ ] Regular backups configured
- [ ] .env file not in version control
- [ ] Production secrets stored securely (not in plain text)

## Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| MONGO_URL | Yes | MongoDB connection string |
| JWT_SECRET | Yes | Secret for JWT signing (min 32 chars) |
| ENCRYPTION_KEY | Yes | Fernet key for API key encryption |
| INVITE_CODE | Optional | Code for invite-only registration |
| ENABLE_TRADING | No | Enable live trading (default: false) |
| ENABLE_AUTOPILOT | No | Enable autonomous systems (default: false) |
| ENABLE_CCXT | No | Enable exchange connections (default: true) |

## Support

For issues, check:
1. Service logs: `sudo journalctl -u amarktai-api -n 100`
2. Application logs: `backend/logs/` directory
3. MongoDB logs: `docker logs amarktai-mongo`
4. Smoke test output: `bash tools/smoke_test.sh`

## Next Steps After Installation

1. Configure Nginx reverse proxy
2. Setup SSL certificates
3. Create first admin user
4. Test registration and login
5. Configure user API keys for exchanges
6. Start with paper trading
7. Monitor for 7 days before enabling live trading
8. Enable autopilot when confident

---

**Installation Status:** ✅ Ready for production deployment

**Last Updated:** 2026-01-20
