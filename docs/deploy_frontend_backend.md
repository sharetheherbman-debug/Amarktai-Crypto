# Deployment Guide: Frontend & Backend

**Last Updated:** 2026-01-13  
**Version:** Dashboard Overhaul + Wiring Fixes

---

## Overview

This guide provides step-by-step instructions for deploying the Amarktai Network trading platform (FastAPI backend + React frontend) to production.

---

## Prerequisites

### Backend Requirements
- Python 3.9+
- MongoDB 4.4+
- pip or conda
- SSL certificates (for HTTPS)
- Reverse proxy (nginx recommended)

### Frontend Requirements
- Node.js 16+
- npm or yarn
- Web server (nginx, Apache, or serve via backend)

### Environment Variables Required
```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=your-secret-key-change-in-production
ADMIN_PASSWORD=your-admin-password

# Feature Flags (recommended defaults)
ENABLE_REALTIME=true          # SSE real-time updates
ENABLE_TRADING=0              # Safe default, enable after testing
ENABLE_AUTOPILOT=0            # Safe default
ENABLE_CCXT=0                 # Safe default
ENABLE_SCHEDULERS=0           # Safe default

# API Keys (optional, can be set per-user in dashboard)
OPENAI_API_KEY=
FETCHAI_API_KEY=
FLOKX_API_KEY=

# External Services
EXCHANGE_API_KEYS_ENCRYPTED=true  # Use encrypted storage
```

---

## Backend Deployment

### Step 1: Clone and Setup

```bash
# Clone repository
git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git
cd Amarktai-Crypto/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your production values
nano .env  # or vim, or your preferred editor
```

**Critical Settings to Change:**
- `JWT_SECRET` - Generate a strong random secret
- `ADMIN_PASSWORD` - Set a strong admin password
- `MONGO_URL` - Your MongoDB connection string
- `DB_NAME` - Your database name

### Step 3: Database Initialization

```bash
# Ensure MongoDB is running
sudo systemctl status mongod

# Test connection
python3 -c "from motor.motor_asyncio import AsyncIOMotorClient; import asyncio; asyncio.run(AsyncIOMotorClient('mongodb://localhost:27017').admin.command('ping'))"

# Run migrations if any exist
# python3 backend/migrations/run_migrations.py
```

### Step 4: Run Backend Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest backend/tests/test_dashboard_auth.py -v

# Run all tests (optional)
pytest backend/tests/ -v
```

### Step 5: Start Backend Server

#### Development/Testing
```bash
# Direct uvicorn
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload

# Or with environment variables
ENABLE_REALTIME=true uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

#### Production with Gunicorn
```bash
# Install gunicorn
pip install gunicorn uvicorn[standard]

# Run with workers
gunicorn backend.server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  --log-level info
```

#### Production with Systemd Service

Create `/etc/systemd/system/amarktai-backend.service`:

```ini
[Unit]
Description=Amarktai Network Backend
After=network.target mongod.service

[Service]
Type=notify
User=amarktai
Group=amarktai
WorkingDirectory=/opt/amarktai
Environment="PATH=/opt/amarktai/venv/bin"
EnvironmentFile=/opt/amarktai/.env
ExecStart=/opt/amarktai/venv/bin/gunicorn backend.server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --timeout 120
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

---

## Frontend Deployment

### Step 1: Setup and Build

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Build output will be in frontend/build/
```

### Step 2: Configure API Endpoint

Edit `frontend/public/config.js` (if exists) or ensure environment variable:

```javascript
// frontend/public/config.js
window.API_BASE = 'https://your-domain.com/api';
```

Or use environment variable before build:
```bash
REACT_APP_API_BASE=https://your-domain.com/api npm run build
```

### Step 3: Verify Build

```bash
# Check build output
ls -la frontend/build/

# Expected files:
# - index.html
# - static/js/*.js
# - static/css/*.css
# - assets (logo, images, etc.)
```

### Step 4: Deploy Frontend

#### Option A: Serve via Nginx

```nginx
# /etc/nginx/sites-available/amarktai
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL Configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # Frontend (React build)
    root /opt/amarktai/frontend/build;
    index index.html;
    
    # Serve static files
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # Backend API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts for SSE
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    # WebSocket proxy
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
    
    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Option B: Serve via Backend (FastAPI Static Files)

```python
# Add to backend/server.py
from fastapi.staticfiles import StaticFiles

# Mount frontend build
app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="static")
```

---

## Verification Steps

### Backend Health Checks

```bash
# 1. Health endpoint
curl http://localhost:8000/api/health/ping
# Expected: {"status": "ok", ...}

# 2. Root endpoint
curl http://localhost:8000/
# Expected: {"message": "Amarktai Network API", "version": "2.0.0", "status": "operational"}

# 3. OpenAPI docs
curl http://localhost:8000/docs
# Should return HTML

# 4. Auth endpoint (should fail without credentials)
curl http://localhost:8000/api/auth/me
# Expected: 401 or 403 (no authorization)
```

### Frontend Health Checks

```bash
# 1. Check if build files exist
ls frontend/build/index.html
ls frontend/build/static/

# 2. Test locally with serve
npm install -g serve
serve -s frontend/build -l 3000

# 3. Visit http://localhost:3000 in browser
```

### Integration Test (Login Flow)

```bash
# 1. Register user (if needed)
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password_hash": "testpassword123",
    "first_name": "Test",
    "last_name": "User"
  }'

# 2. Login and get token
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }' | jq -r '.token')

# 3. Test /api/auth/me with token
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
# Expected: User profile JSON (no "User not found" error)

# 4. Test bots endpoint
curl http://localhost:8000/api/bots \
  -H "Authorization: Bearer $TOKEN"
# Expected: Array of bots (may be empty)

# 5. Test SSE endpoint
curl http://localhost:8000/api/realtime/events \
  -H "Authorization: Bearer $TOKEN" \
  --no-buffer \
  --max-time 10
# Expected: SSE events stream (heartbeat, updates)
```

---

## Post-Deployment Checklist

### Security
- [ ] Changed JWT_SECRET to production value
- [ ] Changed ADMIN_PASSWORD to strong password
- [ ] SSL/TLS certificates installed and working
- [ ] Firewall configured (only 80/443 exposed)
- [ ] MongoDB authentication enabled
- [ ] Sensitive environment variables not in code

### Functionality
- [ ] Login works
- [ ] `/api/auth/me` returns 200 (not 404)
- [ ] Dashboard loads without errors
- [ ] No 404s in browser console
- [ ] API Setup section shows all keys
- [ ] Real-time updates work (SSE)
- [ ] Admin panel accessible (for admin users)

### Performance
- [ ] Static files served with compression (gzip)
- [ ] CDN configured (optional)
- [ ] Database indexes created
- [ ] Log rotation configured

### Monitoring
- [ ] Application logs accessible
- [ ] Error tracking setup (Sentry, etc.)
- [ ] Uptime monitoring (UptimeRobot, Pingdom, etc.)
- [ ] Prometheus metrics endpoint working (optional)

---

## Troubleshooting

### Issue: "User not found" on /api/auth/me
**Solution:** This was fixed in the latest version. Ensure you have the updated `routes/auth.py` that handles both `id` field and ObjectId lookups.

```python
# Verify the fix is present
grep -A 10 "def get_current_user_profile" backend/routes/auth.py
```

### Issue: Admin endpoints return 403
**Solution:** Ensure user has `is_admin: true` or `role: 'admin'` in database.

```bash
# Set user as admin via MongoDB
mongosh amarktai_trading
db.users.updateOne(
  {email: "admin@example.com"},
  {$set: {is_admin: true, role: "admin"}}
)
```

### Issue: SSE not working (404 on /api/realtime/events)
**Solution:** Ensure `ENABLE_REALTIME=true` in environment.

```bash
# Check if SSE router is loaded
curl http://localhost:8000/api/realtime/events -H "Authorization: Bearer TOKEN"
```

### Issue: Frontend shows "API_BASE not defined"
**Solution:** Create or update `frontend/public/config.js`:

```javascript
window.API_BASE = '/api';  // or full URL: 'https://api.example.com/api'
```

### Issue: Assets not loading after build
**Solution:** Ensure assets are in `frontend/public/` directory and referenced correctly:

```html
<!-- Correct -->
<img src="/logo.png" />

<!-- Incorrect -->
<img src="http://localhost:3000/logo.png" />
```

### Issue: CORS errors
**Solution:** Backend already has CORS middleware configured for all origins. For production, restrict:

```python
# backend/server.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Stop services
sudo systemctl stop amarktai-backend

# 2. Restore previous code version
git checkout <previous-commit-hash>

# 3. Restore database backup (if needed)
mongorestore --db amarktai_trading backup/

# 4. Rebuild and restart
npm run build  # If frontend changed
sudo systemctl start amarktai-backend
```

---

## Performance Tuning

### Backend Optimization
```bash
# Increase workers based on CPU cores
gunicorn --workers $((2 * $(nproc) + 1)) ...

# Use connection pooling for MongoDB
# Set in .env or connection string
MONGO_MAX_POOL_SIZE=100
MONGO_MIN_POOL_SIZE=10
```

### Frontend Optimization
```bash
# Enable production optimizations
npm run build  # Already optimized by default

# Serve with compression
# nginx gzip already configured above
```

### Database Optimization
```javascript
// Create indexes in MongoDB
use amarktai_trading

// User lookups
db.users.createIndex({email: 1}, {unique: true})
db.users.createIndex({id: 1})

// Bot queries
db.bots.createIndex({user_id: 1})
db.bots.createIndex({status: 1})

// Trade queries
db.trades.createIndex({user_id: 1, timestamp: -1})
db.trades.createIndex({bot_id: 1})
```

---

## Backup Strategy

### Database Backup
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mongodump --db amarktai_trading --out /backups/mongo_$DATE
find /backups -mtime +7 -delete  # Keep 7 days
```

### Code Backup
```bash
# Git tags for releases
git tag -a v1.0.0 -m "Dashboard overhaul release"
git push origin v1.0.0
```

---

## Maintenance

### Log Rotation
```bash
# /etc/logrotate.d/amarktai
/opt/amarktai/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 amarktai amarktai
    sharedscripts
    postrotate
        systemctl reload amarktai-backend
    endscript
}
```

### Updates
```bash
# Pull latest code
git pull origin main

# Update dependencies
pip install -r backend/requirements.txt
npm install

# Rebuild frontend
npm run build

# Restart backend
sudo systemctl restart amarktai-backend
```

---

## Support & Contact

For issues or questions:
- GitHub Issues: [Repository Issues](https://github.com/amarktainetwork-blip/Amarktai-Crypto/issues)
- Documentation: `/docs/` directory
- Gap Report: `/docs/reports/gap_report.md`
- Routes Documentation: `/docs/reports/dashboard_routes_used.md`

---

**End of Deployment Guide**
