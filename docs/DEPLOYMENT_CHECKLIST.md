# Go-Live Deployment Checklist

## Pre-Deployment Verification

### 1. Repository Preparation
- [ ] Pull latest code from main branch
- [ ] Verify all three runtime errors are fixed:
  - [ ] AUTO_PROMOTE_LIVE import error
  - [ ] Hourly task dict/int comparison error  
  - [ ] scan_all_users method missing error
- [ ] Run quick smoke tests: `bash quick_smoke_tests.sh`

### 2. Backend Setup

#### Environment Setup
```bash
# Navigate to backend directory
cd /var/amarktai/backend

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Configuration
```bash
# Copy and configure environment file
cp .env.example .env

# Edit .env with production settings
nano .env
```

**Critical .env Settings:**
```bash
# Paper Trading (ENABLED)
ENABLE_PAPER_TRADING=true
ENABLE_TRADING=true

# Live Trading (DISABLED until trained + confirmed)
ENABLE_LIVE_TRADING=false
AUTO_PROMOTE_LIVE=false

# Training Requirements
PAPER_TRAINING_DAYS=7
MIN_WIN_RATE=0.52
MIN_PROFIT_PERCENT=0.03
MIN_TRADES_FOR_PROMOTION=25

# Safety Gates
REQUIRE_WALLET_FUNDED=true
REQUIRE_API_KEYS_FOR_LIVE=true

# Background Tasks
ENABLE_SCHEDULERS=true
ENABLE_SELF_HEALING=true
ENABLE_AUTOPILOT=true

# Database
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=amarktai_prod
```

#### Database Setup
```bash
# Ensure MongoDB is running
sudo systemctl status mongod
sudo systemctl start mongod
sudo systemctl enable mongod

# Verify connection
mongo --eval "db.adminCommand('ping')"
```

### 3. Systemd Service Setup

#### Create Service File
```bash
sudo nano /etc/systemd/system/amarktai-api.service
```

**Service Configuration:**
```ini
[Unit]
Description=Amarktai Trading API (FastAPI/Uvicorn)
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/amarktai/backend
Environment="PATH=/var/amarktai/backend/venv/bin"
ExecStart=/var/amarktai/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10
StandardOutput=append:/var/log/amarktai/api.log
StandardError=append:/var/log/amarktai/api-error.log

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Service
```bash
# Create log directory
sudo mkdir -p /var/log/amarktai
sudo chown www-data:www-data /var/log/amarktai

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable amarktai-api

# Start service
sudo systemctl start amarktai-api

# Check status
sudo systemctl status amarktai-api
```

#### Monitor Logs
```bash
# Watch API logs
sudo tail -f /var/log/amarktai/api.log

# Check for errors
sudo tail -f /var/log/amarktai/api-error.log

# Check for the three fixed errors (should NOT appear):
# 1. "cannot import name 'AUTO_PROMOTE_LIVE'"
# 2. "'>' not supported between instances of 'dict' and 'int'"
# 3. "'SelfHealingSystem' object has no attribute 'scan_all_users'"
```

### 4. Nginx Configuration

#### Create Nginx Config
```bash
sudo nano /etc/nginx/sites-available/amarktai
```

**Nginx Configuration:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend (static build)
    location / {
        root /var/amarktai/frontend/build;
        try_files $uri $uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, max-age=3600";
    }

    # API backend
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Assets
    location /assets {
        root /var/amarktai/frontend/build;
        expires 7d;
        add_header Cache-Control "public, max-age=604800, immutable";
    }
}
```

#### Enable and Test
```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 5. Frontend Build and Deploy

```bash
# Navigate to frontend directory
cd /var/amarktai/frontend

# Install dependencies (use exact versions)
npm ci

# Build production bundle
npm run build

# Verify build output
ls -lh build/
ls -lh build/assets/

# Verify logo2.png is included
ls -lh build/assets/logo2.png

# Deploy to Nginx directory
sudo mkdir -p /var/amarktai/frontend/build
sudo cp -r build/* /var/amarktai/frontend/build/
sudo chown -R www-data:www-data /var/amarktai/frontend/build
```

## Post-Deployment Testing

### 1. Health Check
```bash
# Test API health endpoint
curl http://localhost:8000/api/health/ping

# Expected response:
# {"status":"ok","timestamp":"..."}
```

### 2. Config Validation
```bash
# Verify AUTO_PROMOTE_LIVE is accessible
curl http://localhost:8000/api/system/mode

# Expected: should return system mode with live trading OFF
```

### 3. Paper Trading Test
```bash
# Create test user (if not exists)
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}'

# Check paper trading status
curl http://localhost:8000/api/bots \
  -H "Authorization: Bearer <token>"
```

### 4. Monitor Background Tasks
```bash
# Watch logs for hourly/daily tasks
sudo tail -f /var/log/amarktai/api.log | grep -E "(hourly|daily|self-healing)"

# Should see:
# - "⏰ Running hourly autonomous tasks..."
# - "✅ Hourly tasks completed"
# - "🌅 Running daily autonomous tasks..."
# - "✅ Daily tasks completed"
# - "🛡️ Starting daily self-healing scan"

# Should NOT see:
# - "cannot import name 'AUTO_PROMOTE_LIVE'"
# - "'>' not supported between instances of 'dict' and 'int'"
# - "'SelfHealingSystem' object has no attribute 'scan_all_users'"
```

### 5. Frontend Visual Check
- [ ] Navigate to http://your-domain.com
- [ ] Verify logo2.png appears on landing page
- [ ] Login and check dashboard
- [ ] Verify logo2.png appears in:
  - [ ] Navbar/header
  - [ ] Sidebar
  - [ ] Login page
  - [ ] Register page
  - [ ] Mobile logo button

## Live Trading Gate Verification

### Before Enabling Live Trading

**Training Requirements Must Be Met:**
```bash
# Check training status
curl http://localhost:8000/api/training/status \
  -H "Authorization: Bearer <admin_token>"

# Requirements:
# - Paper trading for minimum 7 days
# - Win rate >= 52%
# - Profit >= 3%
# - Minimum 25 trades
```

**Manual Confirmation Required:**
```bash
# Live trading CANNOT be enabled automatically
# Must be explicitly confirmed by admin:

# 1. Check requirements
curl http://localhost:8000/api/admin/live-trading/eligibility

# 2. Explicit confirmation (only if eligible)
curl -X POST http://localhost:8000/api/admin/live-trading/enable \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true,"acknowledge_risk":true}'
```

## Rollback Procedure

If issues occur:

```bash
# 1. Stop service
sudo systemctl stop amarktai-api

# 2. Check logs
sudo tail -100 /var/log/amarktai/api-error.log

# 3. Revert code (if needed)
cd /var/amarktai/backend
git checkout <previous-commit>

# 4. Restart service
sudo systemctl start amarktai-api
```

## Monitoring Checklist

### Daily Monitoring (First Week)
- [ ] Check system logs for errors
- [ ] Verify paper trading is executing
- [ ] Monitor background task completion
- [ ] Check database size and performance
- [ ] Verify no repeating errors

### Metrics to Track
- [ ] Paper trading win rate
- [ ] Number of trades per day
- [ ] System uptime
- [ ] API response times
- [ ] Memory/CPU usage

### Alert Thresholds
- System down for > 5 minutes
- Error rate > 10 errors/hour
- Memory usage > 90%
- Disk usage > 85%

## Security Checklist
- [ ] Firewall configured (UFW)
- [ ] SSH key-only authentication
- [ ] Database access restricted to localhost
- [ ] API keys stored in environment variables (not in code)
- [ ] HTTPS/SSL configured (certbot)
- [ ] Regular security updates scheduled

## Backup Strategy
- [ ] Database backup schedule (daily)
- [ ] Code repository backup (GitHub)
- [ ] Environment config backup (secure location)
- [ ] Disaster recovery plan documented

## Support Contacts
- VPS Provider: Webdock
- Repository: github.com/sharetheherbman-debug/Amarktai-Network---Deployment
- Deployment Issues: Check /var/log/amarktai/

---

**Deployment Date:** _______________  
**Deployed By:** _______________  
**Go-Live Status:** ⬜ Paper Mode | ⬜ Live Mode (after training)  
**Issues Encountered:** _______________
