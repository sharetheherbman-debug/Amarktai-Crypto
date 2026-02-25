# Production Go-Live Guide

This guide covers the production deployment checklist for Amarktai Network on Ubuntu 24.04 with Nginx reverse proxy.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Nginx Configuration](#nginx-configuration)
- [Deployment Steps](#deployment-steps)
- [Smoke Testing](#smoke-testing)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements
- Ubuntu 24.04 LTS
- Nginx 1.18+ (for WebSocket support)
- Python 3.10+
- Node.js 18+ (for frontend build)
- MongoDB 6.0+
- SSL Certificate (Let's Encrypt recommended)

### Dependencies
```bash
# System packages
sudo apt update
sudo apt install -y nginx python3-pip python3-venv nodejs npm mongodb-org

# Python dependencies
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend dependencies
cd ../frontend
npm install
```

## Environment Variables

### Critical Security Keys (REQUIRED)

These MUST be changed from defaults in production:

```bash
# JWT Secret (REQUIRED - generate with: openssl rand -hex 32)
JWT_SECRET=your-secret-key-change-in-production-min-32-chars

# Admin Password (REQUIRED - generate with: openssl rand -base64 24)
ADMIN_PASSWORD=your-secure-admin-password

# Invite Code for Registration
INVITE_CODE=AMARKTAI2024
```

### Database Configuration (REQUIRED)

```bash
# MongoDB connection string
MONGO_URL=mongodb://localhost:27017

# Database name
DB_NAME=amarktai_trading
```

### Trading Mode Gates (CRITICAL SAFETY)

These control whether the system can place orders:

```bash
# Paper Trading Mode (simulated trades, no real money)
# Set to 1 to enable, 0 to disable
PAPER_TRADING=1

# Live Trading Mode (DANGER: Uses REAL funds!)
# Set to 1 to enable, 0 to disable
# WARNING: Only enable after thorough testing in paper mode
LIVE_TRADING=0

# Autopilot Mode (automated bot management)
# Set to 1 to enable, 0 to disable
AUTOPILOT_ENABLED=0
```

**Safe Deployment Path:**
1. Start with ALL flags = 0 (no trading)
2. Set `PAPER_TRADING=1` for testing (safe)
3. After 7 days paper trading, set `LIVE_TRADING=1` (requires API keys)
4. Set `AUTOPILOT_ENABLED=1` for autonomous operation (optional)

### Feature Flags

```bash
# Enable/disable system features
ENABLE_TRADING=false      # Master switch for trading operations
ENABLE_SCHEDULERS=true    # Background jobs (AI, learning, self-healing)
ENABLE_AUTOPILOT=false    # Autonomous bot management
ENABLE_CCXT=true          # Exchange connections (safe for price data)
ENABLE_REALTIME=true      # WebSocket realtime events
```

### Optional Services

```bash
# OpenAI API (for AI features)
OPENAI_API_KEY=

# Email notifications (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
FROM_EMAIL=

# CoinStats & Fetch.ai (market intelligence)
COINSTATS_API_KEY=
FETCHAI_API_KEY=
```

### Frontend Environment Variables

Create `frontend/.env`:

```bash
# API Base URL (optional - defaults to /api)
REACT_APP_API_BASE=/api

# Or specify full URL for cross-origin:
# REACT_APP_API_BASE=https://amarktai.online/api
```

## Nginx Configuration

### WebSocket Support (REQUIRED)

Copy the Nginx configuration template:

```bash
sudo cp ops/nginx/amarktai-websocket.conf /etc/nginx/sites-available/amarktai
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
```

### SSL Certificate Setup

Using Let's Encrypt (recommended):

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d amarktai.online -d www.amarktai.online

# Certificate auto-renewal is configured automatically
```

### Update Nginx Config

Edit `/etc/nginx/sites-available/amarktai`:

1. Update `server_name` to your domain
2. Update SSL certificate paths if different
3. Update `root` path to your frontend build directory
4. Update upstream backend port if not 8000

### Test and Reload Nginx

```bash
# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Check status
sudo systemctl status nginx
```

### Key Nginx Directives for WebSocket

The critical section in your Nginx config:

```nginx
location = /api/ws {
    proxy_pass http://127.0.0.1:8000;
    
    # WebSocket upgrade headers (REQUIRED)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Timeouts
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    
    # Disable buffering
    proxy_buffering off;
}
```

## Deployment Steps

### 1. Clone Repository

```bash
cd /var/www
sudo git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git amarktai
sudo chown -R $USER:$USER amarktai
cd amarktai
```

### 2. Configure Environment

```bash
# Backend
cp backend/.env.example backend/.env
nano backend/.env  # Edit with your values

# Frontend
cp frontend/.env.example frontend/.env
nano frontend/.env  # Edit with your values
```

### 3. Build Frontend

```bash
cd frontend
npm install
npm run build

# Verify build
ls -la build/
```

### 4. Setup Backend Service

Create systemd service file `/etc/systemd/system/amarktai-backend.service`:

```ini
[Unit]
Description=Amarktai Network Backend
After=network.target mongodb.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/amarktai/backend
Environment="PATH=/var/www/amarktai/backend/venv/bin"
ExecStart=/var/www/amarktai/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable amarktai-backend
sudo systemctl start amarktai-backend
sudo systemctl status amarktai-backend
```

### 5. Configure Frontend Path

Update Nginx config to point to frontend build:

```nginx
root /var/www/amarktai/frontend/build;
```

### 6. Set Permissions

```bash
# Backend logs directory
sudo mkdir -p /var/log/amarktai
sudo chown www-data:www-data /var/log/amarktai

# AI memory storage (if using)
sudo mkdir -p /var/amarktai/data/ai_memory
sudo chown www-data:www-data /var/amarktai/data/ai_memory
```

## Smoke Testing

Run the production smoke test script to verify deployment:

```bash
cd /var/www/amarktai

# Test against production
./scripts/smoke_prod.sh https://amarktai.online AMARKTAI2024

# Or test against local
./scripts/smoke_prod.sh http://localhost:8000 AMARKTAI2024
```

### Expected Output

```
============================================================================
Amarktai Network - Production Smoke Test
============================================================================

[PASS] Health check returned 200 OK
[PASS] User registration succeeded with invite header
[PASS] User login succeeded, token obtained
[PASS] System status endpoint returned valid response
[PASS] System status includes trading_mode_flags
[PASS] API keys list endpoint accessible (HTTP 200)
[PASS] WebSocket diagnostics endpoint returned valid response
[PASS] WebSocket endpoint path is /api/ws
[PASS] No /api/api/ double path issue detected

============================================================================
Test Summary
============================================================================
Tests Passed: 9
Tests Failed: 0

✅ ALL SMOKE TESTS PASSED
```

### What the Smoke Test Checks

1. **Health Check** - Backend is running
2. **Registration** - Invite-only registration works via header
3. **Login** - Authentication and token generation
4. **System Status** - Feature flags and trading modes
5. **API Keys** - Endpoint accessibility and auth
6. **WebSocket** - Diagnostics and configuration
7. **URL Bug** - No /api/api/ double paths
8. **WebSocket Connection** (optional) - Live connection test

## Troubleshooting

### Backend Not Starting

Check logs:
```bash
sudo journalctl -u amarktai-backend -f
```

Common issues:
- Missing environment variables
- Database connection failed
- Port 8000 already in use
- Python dependencies missing

### WebSocket Connection Failed

1. **Check Nginx logs:**
```bash
sudo tail -f /var/log/nginx/amarktai-error.log
```

2. **Verify WebSocket diagnostics:**
```bash
curl https://amarktai.online/api/diagnostics/ws
```

3. **Test WebSocket endpoint directly:**
```bash
# Requires wscat: npm install -g wscat
wscat -c "wss://amarktai.online/api/ws?token=YOUR_JWT_TOKEN"
```

4. **Common issues:**
   - Nginx not configured for WebSocket upgrade
   - Missing `Upgrade` or `Connection` headers
   - Firewall blocking WebSocket connections
   - SSL certificate issues

### Frontend /api/api/ Errors

If you see 404 errors for `/api/api/*` paths:

1. **Check browser console:**
   - Look for red errors with `/api/api/`
   - Should see warning: "DETECTED /api/api/ DOUBLE PATH"

2. **Clear browser cache:**
   ```bash
   # Hard refresh in browser
   Ctrl+Shift+R (Linux/Windows)
   Cmd+Shift+R (Mac)
   ```

3. **Verify API_BASE configuration:**
   ```javascript
   // In browser console:
   localStorage.clear()  // Clear any cached config
   location.reload()
   ```

### 401/403 Errors

1. **Token expired:**
   - Login again to get fresh token
   - Check JWT_SECRET matches between deployments

2. **Admin endpoint requires admin privileges:**
   - Verify user has `is_admin: true` in database
   - Check ADMIN_PASSWORD environment variable

3. **Invite code invalid:**
   - Verify INVITE_CODE in backend .env
   - Try passing in X-Invite-Code header

### Database Connection Issues

```bash
# Check MongoDB status
sudo systemctl status mongodb

# Check connection
mongosh mongodb://localhost:27017/amarktai_trading

# View backend logs
sudo journalctl -u amarktai-backend -n 100
```

## Post-Deployment Checklist

- [ ] All environment variables configured
- [ ] Nginx configuration applied and tested
- [ ] SSL certificate installed and auto-renewal configured
- [ ] Backend service running and enabled
- [ ] Frontend built and accessible
- [ ] Smoke test script passes all tests
- [ ] WebSocket connection working
- [ ] Admin login working
- [ ] API keys can be configured
- [ ] No console errors in browser
- [ ] Logs are being written correctly
- [ ] Monitoring/alerting configured (optional)
- [ ] Backup strategy in place (database + .env files)

## Production Safety Checklist

Before enabling live trading:

- [ ] Paper trading tested for at least 7 days
- [ ] All API keys tested and verified
- [ ] Risk limits configured and tested
- [ ] Circuit breakers tested
- [ ] Emergency stop procedure documented
- [ ] Team trained on admin panel
- [ ] Monitoring alerts configured
- [ ] Backup and recovery tested
- [ ] Security audit completed
- [ ] Legal/compliance review completed

## Support

For issues or questions:
- Check logs: `/var/log/amarktai/` and `journalctl -u amarktai-backend`
- Review documentation in `docs/` directory
- Run diagnostics: `curl https://amarktai.online/api/diagnostics/ws`
- Run smoke test: `./scripts/smoke_prod.sh`
