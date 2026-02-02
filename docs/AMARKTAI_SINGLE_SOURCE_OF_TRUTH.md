# Amarktai Network - Single Source of Truth

**Version:** 1.0.0  
**Last Updated:** 2026-01-27  
**Status:** Production Ready

This document is the **authoritative reference** for Amarktai Network deployment, configuration, and operations on Ubuntu 24.04 VPS.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Environment Variables Reference](#environment-variables-reference)
3. [Deployment Steps (Fresh VPS)](#deployment-steps-fresh-vps)
4. [Verification Steps](#verification-steps)
5. [Rollback Procedures](#rollback-procedures)
6. [Operational Runbook](#operational-runbook)
7. [Safety Constraints](#safety-constraints)
8. [Common Failures & Solutions](#common-failures--solutions)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx (Port 80/443)                 │
│  - Reverse proxy for frontend & API                        │
│  - SSL termination                                          │
│  - Static asset serving                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
       ┌───────────┴──────────┐
       │                      │
       ▼                      ▼
┌─────────────┐      ┌──────────────────┐
│  Frontend   │      │   FastAPI Backend │
│  (React)    │      │   127.0.0.1:8000  │
│  /var/...   │      │   (uvicorn)       │
└─────────────┘      └────────┬──────────┘
                              │
                 ┌────────────┼────────────┐
                 │            │            │
                 ▼            ▼            ▼
           ┌─────────┐  ┌────────┐  ┌─────────┐
           │ MongoDB │  │ Redis  │  │ Docker  │
           │  27017  │  │  6379  │  │  (Mongo)│
           └─────────┘  └────────┘  └─────────┘
```

### Canonical VPS Layout

```
/var/amarktai/
├── app/                          # Repository root
│   ├── backend/                  # FastAPI application
│   │   ├── .venv/                # Python virtual environment
│   │   ├── .env                  # Environment configuration
│   │   ├── server.py             # Main FastAPI server
│   │   ├── requirements.txt      # Python dependencies
│   │   └── ...
│   ├── frontend/                 # React application
│   │   ├── build/                # Production build
│   │   └── ...
│   └── deployment/               # Deployment scripts
│       ├── install.sh            # Main installation script
│       ├── verify.sh             # Verification script
│       ├── amarktai-api.service  # Systemd service template
│       └── nginx-amarktai.conf   # Nginx configuration
│
/etc/amarktai/                    # Secrets storage
├── mongo_password                # MongoDB password (chmod 600)
└── ...
│
/etc/systemd/system/
└── amarktai-api.service          # Systemd service
│
/etc/nginx/sites-available/
└── amarktai                      # Nginx site configuration
```

### Supported Exchanges

**ONLY** the following 7 exchanges are supported (as defined in `backend/config/platforms.py`):
- **Luno** (South African exchange, primary, 5 bots max)
- **Binance** (International, 10 bots max)
- **KuCoin** (International, 10 bots max)
- **Bybit** (Derivatives and spot, 10 bots max)
- **Kraken** (US-based regulated, 10 bots max)
- **Bitget** (Global crypto and derivatives, 10 bots max)
- **Gate.io** (Altcoin specialist, 10 bots max)

**Total Bot Capacity:** 65 bots (5+10+10+10+10+10+10)

### Bot Distribution

- Maximum total bots: **65**
- Per exchange distribution:
  - Luno: 5 bots
  - Binance: 10 bots
  - KuCoin: 10 bots
  - Bybit: 10 bots
  - Kraken: 10 bots
  - Bitget: 10 bots
  - Gate.io: 10 bots

---

## Environment Variables Reference

### Critical Security Keys (REQUIRED)

```bash
# JWT secret for token signing
# Generate with: openssl rand -hex 32
JWT_SECRET=your-secret-key-change-in-production-min-32-chars

# API Key Encryption Key (for encrypting exchange API keys in database)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=

# Invite Code for User Registration
INVITE_CODE=AMARKTAI2024
```

### Trading Mode Gates (CRITICAL)

```bash
# Paper Trading Mode (default: 0 for safety)
# Set to 1 to enable simulated trading with paper money
PAPER_TRADING=0

# Live Trading Mode (default: 0 for safety)
# Set to 1 to enable REAL trading with actual funds
# WARNING: Only enable after successful paper trading period
LIVE_TRADING=0

# Autopilot Mode (default: 0 for safety)
# Set to 1 to enable autonomous bot management and spawning
# REQUIRES: Either PAPER_TRADING=1 OR LIVE_TRADING=1
AUTOPILOT_ENABLED=0
```

**Safe Deployment Path:**
1. Start with ALL flags = 0 (no trading)
2. Set `PAPER_TRADING=1` for testing (safe)
3. After 7 days paper trading, set `LIVE_TRADING=1` (requires keys)
4. Set `AUTOPILOT_ENABLED=1` for autonomous operation (optional)

### Feature Flags

```bash
# Trading Feature Flags
ENABLE_TRADING=false       # Master switch for all trading operations (legacy)
ENABLE_AUTOPILOT=false     # Autonomous bot management (legacy, use AUTOPILOT_ENABLED)
ENABLE_CCXT=true           # CCXT exchange connections (safe for price data)
ENABLE_REALTIME=true       # WebSocket realtime events (recommended)
ENABLE_SCHEDULERS=true     # Background jobs (AI, learning, self-healing)
```

### Database Configuration

```bash
# MongoDB connection string
# Auto-configured during installation if using Docker
MONGO_URL=mongodb://amarktai:PASSWORD@localhost:27017

# Database name
DB_NAME=amarktai_trading
```

### Optional Services

```bash
# OpenAI API Key (optional system default for AI trading decisions)
OPENAI_API_KEY=

# Email Configuration (optional but recommended)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
```

---

## Deployment Steps (Fresh VPS)

### Prerequisites

- Ubuntu 24.04 LTS VPS
- Root or sudo access
- At least 2GB RAM, 20GB disk
- Domain name (optional, for SSL)

### Step 1: Clone Repository

```bash
sudo mkdir -p /var/amarktai
cd /var/amarktai
sudo git clone <repository-url> app
cd app
```

### Step 2: Run Installation Script

```bash
cd deployment
sudo ./install.sh
```

The install script will:
1. Install OS dependencies (Python 3.12, Docker, Nginx, Redis)
2. Setup MongoDB via Docker (bound to 127.0.0.1 only)
3. Create Python virtual environment
4. Install Python dependencies
5. Validate Python syntax with compileall
6. Configure systemd service
7. Start the service
8. Run health checks

**Installation time:** 5-10 minutes

### Step 3: Configure Environment

```bash
# Edit backend/.env with your values
cd /var/amarktai/app/backend
sudo nano .env

# MINIMUM required changes:
# 1. JWT_SECRET - generate new secret
# 2. ENCRYPTION_KEY - generate encryption key
# 3. Trading mode flags (start with all 0)
# 4. Add exchange API keys through dashboard (not .env)
```

### Step 4: Configure Nginx (Optional)

```bash
# Copy nginx config
sudo cp /var/amarktai/app/deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai

# Edit with your domain
sudo nano /etc/nginx/sites-available/amarktai
# Change: server_name YOUR_DOMAIN_OR_IP;

# Enable site
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### Step 5: Setup SSL (Recommended)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal is configured automatically
```

---

## Verification Steps

### Automated Verification

```bash
cd /var/amarktai/app/deployment
sudo ./verify.sh
```

The verify script checks:
1. ✅ Python syntax validation (compileall)
2. ✅ Systemd service status
3. ✅ Port binding (127.0.0.1:8000)
4. ✅ Health endpoints responding
5. ✅ OpenAPI spec available
6. ✅ Deployment files present

**Expected result:** All checks pass ✅

### Manual Smoke Tests

```bash
# 1. Check service status
sudo systemctl status amarktai-api.service

# 2. Check logs (last 50 lines)
sudo journalctl -u amarktai-api.service -n 50

# 3. Check port binding
ss -lntp | grep :8000
# Should show: 127.0.0.1:8000

# 4. Test health endpoint
curl http://127.0.0.1:8000/api/health/ping
# Should return: {"status":"healthy"}

# 5. Test OpenAPI spec
curl -s http://127.0.0.1:8000/openapi.json | python3 -m json.tool | head -20
```

---

## Rollback Procedures

### Emergency Rollback (Service Issues)

```bash
# 1. Stop the service
sudo systemctl stop amarktai-api.service

# 2. Checkout previous version
cd /var/amarktai/app
sudo git log --oneline -10  # Find previous commit
sudo git checkout <commit-hash>

# 3. Restart service
sudo systemctl restart amarktai-api.service

# 4. Verify
sudo systemctl status amarktai-api.service
curl http://127.0.0.1:8000/api/health/ping
```

### Database Rollback

```bash
# MongoDB backups (if configured)
# Restore from backup:
docker exec -i amarktai-mongo mongorestore --drop /backup/latest

# Or restore specific collection:
docker exec -i amarktai-mongo mongorestore --drop \
  --collection=bots --db=amarktai_trading /backup/bots.bson
```

### Full System Restore

```bash
# 1. Stop all services
sudo systemctl stop amarktai-api.service nginx

# 2. Restore from VPS snapshot (if available)
# Follow your VPS provider's snapshot restore procedure

# 3. Or reinstall from scratch
cd /var/amarktai/app
sudo git pull origin main
cd deployment
sudo ./install.sh
```

---

## Operational Runbook

### Daily Operations

**Monitor Service Health:**
```bash
# Check service status
sudo systemctl status amarktai-api.service

# Check logs (follow in real-time)
sudo journalctl -u amarktai-api.service -f

# Check resource usage
htop  # Look for python/uvicorn process
```

**Monitor MongoDB:**
```bash
# Check MongoDB status
docker ps | grep amarktai-mongo

# MongoDB logs
docker logs amarktai-mongo --tail 50
```

### Emergency Stop (Trading Halt)

**Via API:**
```bash
# Emergency stop all trading
curl -X POST http://127.0.0.1:8000/api/admin/emergency-stop \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Via Service:**
```bash
# Stop the entire service
sudo systemctl stop amarktai-api.service
```

**What happens:**
- All active bots paused immediately
- Trading engine stopped
- Autopilot stopped
- No new trades executed

**Resume trading:**
```bash
curl -X POST http://127.0.0.1:8000/api/admin/emergency-resume \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Restart Service

```bash
# Graceful restart
sudo systemctl restart amarktai-api.service

# Force restart if hung
sudo systemctl kill amarktai-api.service
sudo systemctl restart amarktai-api.service

# Check startup logs
sudo journalctl -u amarktai-api.service -n 100 --no-pager
```

### Update Deployment

```bash
# 1. Pull latest code
cd /var/amarktai/app
sudo git pull origin main

# 2. Update dependencies (if changed)
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# 3. Restart service
sudo systemctl restart amarktai-api.service

# 4. Verify
cd /var/amarktai/app/deployment
sudo ./verify.sh
```

---

## Safety Constraints

### ⛔ BLOCKED Operations

The following operations are **HARD-BLOCKED** for safety:

1. **Automatic Fund Transfers Between Exchanges**
   - Function: `transfer_funds_between_exchanges()`
   - Returns: `TRANSFER_BLOCKED` error
   - Reason: Could result in loss of funds
   - Future: Manual approval workflow required

2. **Live Mode Wallet Transfers**
   - In live trading mode, wallet allocation performs balance checks ONLY
   - No funds are transferred automatically
   - Returns: `INSUFFICIENT_BALANCE` if balance check fails

### ✅ ALLOWED Operations

1. **Paper Mode Allocation**
   - Writes allocation events to ledger
   - No actual funds moved
   - Safe for testing

2. **Live Mode Balance Checks**
   - Read-only verification
   - Ensures sufficient balance before trading
   - No transfers executed

### Trading Mode Safety

- **Paper Mode:** Simulated trading with virtual money (safe)
- **Live Mode:** Real trading with actual funds (requires API keys)
- **Autopilot:** Autonomous bot spawning (requires profit > 1000 ZAR)

**Bot Spawning Safety:**
- Requires realized profit (after fees) >= 1000 ZAR
- Profit reserved atomically via ledger
- Returns `PROFIT_INSUFFICIENT` if insufficient
- Enforces bot caps (max 45 total, 15 per exchange)

---

## Common Failures & Solutions

### 1. Service Won't Start

**Symptoms:**
```bash
sudo systemctl status amarktai-api.service
# Shows: failed or inactive
```

**Diagnosis:**
```bash
# Check logs for error
sudo journalctl -u amarktai-api.service -n 50 --no-pager
```

**Common causes:**
- MongoDB not running
- Missing/invalid .env variables
- Python syntax errors
- Port 8000 already in use

**Solutions:**
```bash
# Check MongoDB
docker ps | grep amarktai-mongo
docker start amarktai-mongo  # If stopped

# Validate Python syntax
cd /var/amarktai/app/backend
python3 -m compileall . -q

# Check port availability
ss -lntp | grep :8000
# If occupied, kill process or change port

# Check .env file
cat /var/amarktai/app/backend/.env | grep -E "MONGO_URL|JWT_SECRET"
```

### 2. Database Connection Errors

**Symptoms:**
```
ERROR: Failed to connect to MongoDB
```

**Solutions:**
```bash
# Check MongoDB is running
docker ps | grep amarktai-mongo

# Check MongoDB logs
docker logs amarktai-mongo --tail 50

# Restart MongoDB
docker restart amarktai-mongo

# Check connection string in .env
grep MONGO_URL /var/amarktai/app/backend/.env
# Should be: mongodb://amarktai:PASSWORD@localhost:27017
```

### 3. Health Endpoint Not Responding

**Symptoms:**
```bash
curl http://127.0.0.1:8000/api/health/ping
# Connection refused or timeout
```

**Solutions:**
```bash
# Check if service is running
sudo systemctl status amarktai-api.service

# Check if port is bound
ss -lntp | grep :8000

# Check firewall
sudo ufw status
# If blocking port 8000, allow it (or use nginx proxy)

# Check service logs
sudo journalctl -u amarktai-api.service -f
```

### 4. Nginx 502 Bad Gateway

**Symptoms:**
Browser shows "502 Bad Gateway" when accessing site

**Solutions:**
```bash
# Check backend is running
curl http://127.0.0.1:8000/api/health/ping

# Check nginx config
sudo nginx -t

# Check nginx logs
sudo tail -50 /var/log/nginx/error.log

# Restart nginx
sudo systemctl restart nginx
```

### 5. Bot Spawning Fails

**Symptoms:**
Autopilot tries to spawn bot but fails

**Check logs:**
```bash
sudo journalctl -u amarktai-api.service | grep "spawn_bot"
```

**Common errors:**
- `PROFIT_INSUFFICIENT`: Not enough realized profit (need >= 1000 ZAR)
- `BOT_LIMIT_REACHED`: Already at maximum 65 bots
- `EXCHANGE_LIMIT_REACHED`: All exchanges at capacity
- `NO_EXCHANGES`: No exchange API keys configured

**Solutions:**
- Wait for more profit accumulation
- Delete underperforming bots to free slots
- Add exchange API keys via dashboard

---

## Quick Reference

### Key Paths

```
Repository:     /var/amarktai/app
Backend:        /var/amarktai/app/backend
Env file:       /var/amarktai/app/backend/.env
Venv:           /var/amarktai/app/backend/.venv
Service:        /etc/systemd/system/amarktai-api.service
Nginx config:   /etc/nginx/sites-available/amarktai
Secrets:        /etc/amarktai/
```

### Key Commands

```bash
# Service management
sudo systemctl start amarktai-api.service
sudo systemctl stop amarktai-api.service
sudo systemctl restart amarktai-api.service
sudo systemctl status amarktai-api.service

# View logs
sudo journalctl -u amarktai-api.service -f      # Follow
sudo journalctl -u amarktai-api.service -n 50   # Last 50 lines

# Verification
cd /var/amarktai/app/deployment && sudo ./verify.sh

# Health check
curl http://127.0.0.1:8000/api/health/ping
```

### Important URLs

```
Health:    http://127.0.0.1:8000/api/health/ping
Docs:      http://127.0.0.1:8000/docs
OpenAPI:   http://127.0.0.1:8000/openapi.json
Frontend:  http://YOUR_DOMAIN (via nginx)
```

---

## Support & Troubleshooting

For issues not covered in this document:

1. Check service logs: `sudo journalctl -u amarktai-api.service -n 100`
2. Run verification script: `sudo ./deployment/verify.sh`
3. Check MongoDB logs: `docker logs amarktai-mongo --tail 50`
4. Review error codes in response messages

---

**Document Maintenance:**
- Update this document when making system changes
- Keep environment variable reference current
- Add new failure modes as discovered
- This is the ONLY authoritative deployment documentation

**Last reviewed:** 2026-01-27
