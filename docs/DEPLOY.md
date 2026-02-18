# Amarktai Network - Deployment Guide

## Overview

This guide covers deploying and maintaining Amarktai Network on Ubuntu 24.04 with FastAPI/Uvicorn, systemd, nginx reverse proxy, MongoDB, and Redis.

## Supported Exchanges

**EXACTLY 7 EXCHANGES (IMMUTABLE):**
- luno
- binance
- kucoin
- bybit
- kraken
- bitget
- gate

⚠️ **VALR and OVEX are NOT supported** and have been removed from all production codepaths.

---

## Required Environment Variables

Create `/etc/amarktai/amarktai.env` with the following variables:

### Core Configuration (REQUIRED)

```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security (MUST CHANGE IN PRODUCTION)
JWT_SECRET=your-secret-key-change-in-production
ENCRYPTION_KEY=your-fernet-key-here  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AMARKTAI_FERNET_KEY=your-fernet-key-here  # Same as ENCRYPTION_KEY

# Server
HOST=127.0.0.1
PORT=8000
ENVIRONMENT=production
LOG_LEVEL=info
LOG_FILE=/var/log/amarktai/backend.log
```

### Trading Mode Toggles

```bash
# Trading Modes
ENABLE_PAPER_TRADING=true    # Paper trading in sandbox mode
ENABLE_LIVE_TRADING=false    # Live trading with real funds (requires validated keys)
ENABLE_AUTOPILOT=false       # Autonomous bot spawning and management
ENABLE_TRADING=true          # Master trading switch
```

### Optional Services

```bash
# AI Chat (Optional but recommended)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Email Alerts (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=alerts@amarktai.online
FROM_NAME=Amarktai Network

# Optional Integrations
FETCHAI_API_KEY=
FLOKX_API_KEY=

# Redis (Optional - for WebSocket pub/sub)
REDIS_URL=redis://localhost:6379
```

### Trading Limits

```bash
# Bot Capacity (Total: 65 bots across 7 exchanges)
MAX_TOTAL_BOTS=65
BOT_SPAWN_PROFIT_ZAR=1000
NEW_BOT_SEED_CAPITAL_ZAR=500

# Risk Management
STOP_LOSS_SAFE=0.05
STOP_LOSS_BALANCED=0.10
STOP_LOSS_AGGRESSIVE=0.15
MAX_DAILY_LOSS_PERCENT=0.15
MAX_DRAWDOWN_PERCENT=0.25
```

---

## Clean Deployment

Use the provided deployment script for safe, repeatable deployments:

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment
sudo ./scripts/deploy_clean.sh
```

### What `deploy_clean.sh` Does

1. **Git Operations**
   - Fetches latest code from `origin/main`
   - Resets to clean state (`git reset --hard`)
   - Removes untracked files (`git clean -fd`)

2. **Backend Deployment**
   - Creates/refreshes Python venv
   - Installs dependencies from `requirements.txt`
   - Runs Python syntax checks

3. **Frontend Deployment**
   - Runs `npm ci` for clean dependency install
   - Builds production assets with `npm run build`

4. **Service Restart**
   - Restarts `amarktai-api` systemd service
   - Reloads nginx configuration

5. **Health Checks**
   - Tests internal endpoint: `http://127.0.0.1:8000/api/health/ping`
   - Tests external endpoint: `https://www.amarktai.online/api/health/ping`
   - Displays last 150 journal lines on failure

---

## Manual Deployment Steps

If you need to deploy manually:

### 1. Update Code

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment
git fetch --all --prune
git reset --hard origin/main
git clean -fd
```

### 2. Backend

```bash
cd backend
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Run smoke checks
python -m py_compile server.py
python -m py_compile database.py
```

### 3. Frontend

```bash
cd ../frontend
npm ci
npm run build
```

### 4. Restart Services

```bash
sudo systemctl restart amarktai-api
sudo systemctl reload nginx
```

### 5. Verify

```bash
# Check service status
sudo systemctl status amarktai-api

# Test internal endpoint
curl http://127.0.0.1:8000/api/health/ping

# Test external endpoint
curl -k https://www.amarktai.online/api/health/ping
```

---

## API Key Management

### How API Key Status Works

API keys have the following status lifecycle:

1. **not_configured** - No key exists for this provider
2. **saved_untested** - Key saved but never tested
3. **test_ok** - Key tested successfully, ready to use
4. **test_failed** - Last test failed (key invalid or expired)

### Status Transitions

```
User saves key → saved_untested
User tests key (success) → test_ok
User tests key (failure) → test_failed
User updates key → saved_untested (resets test status)
```

### Required Fields by Provider

**Exchange APIs (all 7):**
- luno: `api_key`, `api_secret`
- binance: `api_key`, `api_secret`
- kucoin: `api_key`, `api_secret`, `passphrase`
- bybit: `api_key`, `api_secret`
- kraken: `api_key`, `api_secret`
- bitget: `api_key`, `api_secret`
- gate: `api_key`, `api_secret`

**AI APIs:**
- openai: `api_key`
- fetchai: `api_key`
- flokx: `api_key`

### API Key Repair

If API keys have schema issues (missing `id` fields), run the repair script:

```bash
cd backend
source .venv/bin/activate
python scripts/repair_api_keys.py
```

This script runs automatically on startup but can be executed manually for troubleshooting.

---

## Boot-Safe Server Entrypoint

Two ways to start the server:

### Option 1: Direct Uvicorn (systemd default)

```bash
ExecStart=/path/to/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

### Option 2: Boot-Safe Entrypoint (recommended for debugging)

```bash
ExecStart=/path/to/.venv/bin/python run_server.py
```

The `run_server.py` entrypoint provides:
- Safe import handling with better error messages
- Environment variable validation
- Python version checks
- Clearer startup logs

---

## Troubleshooting

### Service Won't Start

1. **Check logs:**
   ```bash
   sudo journalctl -u amarktai-api -n 150 --no-pager
   tail -f /var/log/amarktai/backend.log
   ```

2. **Verify environment variables:**
   ```bash
   sudo cat /etc/amarktai/amarktai.env
   ```

3. **Check MongoDB:**
   ```bash
   sudo systemctl status mongod
   mongo --eval "db.adminCommand('ping')"
   ```

4. **Test Python imports:**
   ```bash
   cd /var/amarktai/app/Amarktai-Network---Deployment/backend
   source .venv/bin/activate
   python -c "import server"
   ```

### Nginx 502 Bad Gateway

1. **Check if backend is running:**
   ```bash
   curl http://127.0.0.1:8000/api/health/ping
   ```

2. **Check nginx error logs:**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

3. **Verify upstream configuration:**
   ```bash
   sudo nginx -t
   ```

### API Keys Not Working

1. **Check encryption key:**
   ```bash
   # Verify ENCRYPTION_KEY or AMARKTAI_FERNET_KEY is set
   grep ENCRYPTION_KEY /etc/amarktai/amarktai.env
   ```

2. **Run repair script:**
   ```bash
   cd backend
   source .venv/bin/activate
   python scripts/repair_api_keys.py
   ```

3. **Check API key status:**
   ```bash
   # Use the dashboard or API
   curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/keys/list
   ```

---

## Smoke Tests

Run comprehensive smoke tests after deployment:

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment
./scripts/smoke.sh
```

Tests include:
- Health check endpoint
- OpenAPI schema
- Providers list (verifies all 10 providers: 3 AI + 7 exchanges)
- Authentication flow
- API keys endpoints
- System modes endpoint
- (Optional) AI chat with valid OpenAI key

---

## Security Checklist

Before going live:

- [ ] Change `JWT_SECRET` from default
- [ ] Generate and set `ENCRYPTION_KEY` / `AMARKTAI_FERNET_KEY`
- [ ] Restrict MongoDB access (bind to localhost or use authentication)
- [ ] Enable UFW firewall
- [ ] Set up SSL/TLS certificates (Let's Encrypt)
- [ ] Review and set trading limits
- [ ] Enable 2FA for admin accounts
- [ ] Set up email alerts
- [ ] Review and adjust systemd resource limits

---

## Monitoring

### Check Service Health

```bash
# Service status
sudo systemctl status amarktai-api

# Recent logs
sudo journalctl -u amarktai-api -n 100

# Follow logs in real-time
sudo journalctl -u amarktai-api -f
```

### Application Logs

```bash
# Backend logs
tail -f /var/log/amarktai/backend.log

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### System Resources

```bash
# Memory usage
systemctl show amarktai-api --property=MemoryCurrent

# CPU usage
systemctl show amarktai-api --property=CPUUsageNSec
```

---

## Backup and Recovery

### Database Backup

```bash
# Backup MongoDB
mongodump --db amarktai_trading --out /backup/mongo/$(date +%Y%m%d)

# Restore MongoDB
mongorestore --db amarktai_trading /backup/mongo/20240206/amarktai_trading
```

### Configuration Backup

```bash
# Backup environment file
sudo cp /etc/amarktai/amarktai.env /backup/amarktai.env.$(date +%Y%m%d)

# Backup nginx config
sudo cp /etc/nginx/sites-available/amarktai /backup/nginx-amarktai.$(date +%Y%m%d)

# Backup systemd service
sudo cp /etc/systemd/system/amarktai-api.service /backup/amarktai-api.service.$(date +%Y%m%d)
```

---

## Support

For issues or questions:
1. Check logs first: `journalctl -u amarktai-api -n 150`
2. Run smoke tests: `./scripts/smoke.sh`
3. Review this deployment guide
4. Check GitHub Issues: https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment/issues

---

**Last Updated:** 2024-02-06  
**Version:** Go-Live Stabilization Release
