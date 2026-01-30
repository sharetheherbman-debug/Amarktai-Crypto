# Amarktai Network - Production Deployment Guide

This guide covers deploying the Amarktai Network application to production.

## System Requirements

- Ubuntu 20.04+ or similar Linux distribution
- Python 3.8+
- Node.js 16+
- MongoDB 4.4+
- Nginx (for reverse proxy and static file serving)
- systemd (for process management)

## Pre-Deployment Checklist

Before deploying, ensure:

1. ✅ MongoDB is running and accessible
2. ✅ Firewall allows ports 80/443 (HTTP/HTTPS)
3. ✅ SSL certificates are configured (Let's Encrypt recommended)
4. ✅ Environment variables are configured
5. ✅ Backend dependencies are installed
6. ✅ Frontend is built

## Directory Structure

Production directory structure:
```
/var/amarktai/app/
├── backend/           # Backend Python application
│   ├── server.py      # FastAPI application
│   ├── routes/        # API routes
│   ├── scripts/       # Utility scripts
│   │   └── doctor.sh  # Health check script
│   └── ...
├── frontend/          # Frontend React application
│   ├── build/         # Production build
│   └── ...
└── .env               # Environment configuration
```

## 1. Environment Configuration

Create `/var/amarktai/app/.env` with the following variables:

```bash
# Database
MONGODB_URL=mongodb://localhost:27017/amarktai

# JWT Authentication (REQUIRED - change from default!)
JWT_SECRET=your-very-long-random-secret-key-minimum-32-characters-change-this-in-production
JWT_ALGORITHM=HS256

# Admin Password (for admin panel access)
ADMIN_PASSWORD=your-secure-admin-password-change-this

# Feature Flags
ENABLE_TRADING=true
ENABLE_AUTOPILOT=false
ENABLE_SCHEDULERS=true
ENABLE_CCXT=true
ENABLE_REALTIME=true

# API Keys (optional - can be set per-user in UI)
OPENAI_API_KEY=sk-...
LUNO_API_KEY=...
LUNO_API_SECRET=...

# Application Settings
WORKDIR=/var/amarktai/app/backend
LOG_LEVEL=INFO
```

**IMPORTANT**: Change `JWT_SECRET` and `ADMIN_PASSWORD` from defaults!

## 2. Backend Setup

### Install Dependencies

```bash
cd /var/amarktai/app/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Run Pre-Flight Health Check

Before starting the backend, run the doctor script:

```bash
cd /var/amarktai/app/backend
./scripts/doctor.sh
```

This will check:
- Python syntax (compile check)
- Required dependencies
- Environment variables
- Database connectivity
- Server startup and health endpoints

If the doctor script passes, proceed to systemd setup.

### Create systemd Service

Create `/etc/systemd/system/amarktai-backend.service`:

```ini
[Unit]
Description=Amarktai Network Backend API
After=network.target mongodb.service
Wants=mongodb.service

[Service]
Type=simple
User=amarktai
Group=amarktai
WorkingDirectory=/var/amarktai/app/backend
Environment="PATH=/var/amarktai/app/backend/venv/bin"
Environment="WORKDIR=/var/amarktai/app/backend"
EnvironmentFile=/var/amarktai/app/.env

# Start command
ExecStart=/var/amarktai/app/backend/venv/bin/uvicorn server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --log-level info

# Restart policy
Restart=always
RestartSec=10s
StartLimitInterval=300
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=amarktai-backend

[Install]
WantedBy=multi-user.target
```

### Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable amarktai-backend

# Start service
sudo systemctl start amarktai-backend

# Check status
sudo systemctl status amarktai-backend

# View logs
sudo journalctl -u amarktai-backend -f
```

### Verify Backend Health

```bash
# Check ping endpoint
curl http://localhost:8000/api/health/ping

# Check readiness endpoint
curl http://localhost:8000/api/health/ready

# Check preflight endpoint
curl http://localhost:8000/api/health/preflight
```

Expected response from `/api/health/ready`:
```json
{
  "status": "ready",
  "ready": true,
  "db": "connected",
  "collections": ["users", "bots", "trades", "api_keys"],
  "timestamp": "2024-01-28T10:00:00Z"
}
```

## 3. Frontend Setup

### Build Production Frontend

```bash
cd /var/amarktai/app/frontend
npm install
npm run build
```

This creates an optimized production build in `frontend/build/`.

## 4. Nginx Configuration

### Main Site Configuration

Create `/etc/nginx/sites-available/amarktai`:

```nginx
# Upstream backend API
upstream amarktai_backend {
    server 127.0.0.1:8000 fail_timeout=0;
}

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name amarktai.online www.amarktai.online;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name amarktai.online www.amarktai.online;

    # SSL configuration (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/amarktai.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/amarktai.online/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Root directory for static files
    root /var/amarktai/app/frontend/build;
    index index.html;

    # Logs
    access_log /var/log/nginx/amarktai-access.log;
    error_log /var/log/nginx/amarktai-error.log;

    # API proxy (backend)
    location /api/ {
        proxy_pass http://amarktai_backend;
        proxy_http_version 1.1;
        
        # WebSocket support (REQUIRED for /api/ws)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts (important for SSE and WebSocket)
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;  # 5 minutes for long-polling/SSE
        
        # Disable buffering for SSE
        proxy_buffering off;
        proxy_cache off;
        
        # Add CORS headers if needed
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    }

    # Static files (React app)
    location / {
        try_files $uri $uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://amarktai_backend/api/health/ping;
        access_log off;
    }
}
```

### Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## 5. Post-Deployment Verification

### Run Smoke Tests

```bash
cd /var/amarktai/app
./scripts/smoke.sh
```

The smoke test will:
1. Test login endpoint
2. Test /api/auth/me
3. Test /api/bots
4. Test /api/portfolio/summary
5. Test SSE connection for 5 seconds
6. Optionally test WebSocket handshake

### Manual Verification

1. **Health Endpoints**:
   ```bash
   curl https://amarktai.online/api/health/ping
   curl https://amarktai.online/api/health/ready
   ```

2. **Authentication**:
   ```bash
   # Login
   curl -X POST https://amarktai.online/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"yourpass"}'
   
   # Get current user (requires token from login)
   curl https://amarktai.online/api/auth/me \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

3. **Dashboard**: Open https://amarktai.online in browser
   - Should load without console errors
   - Login should work
   - Dashboard should display properly

4. **WebSocket/SSE**: Check browser console for:
   ```
   ✅ SSE connected: [object EventSource]
   or
   ✅ WebSocket connected
   ```

## 6. Monitoring and Maintenance

### View Logs

```bash
# Backend logs (systemd)
sudo journalctl -u amarktai-backend -f

# Nginx access logs
sudo tail -f /var/log/nginx/amarktai-access.log

# Nginx error logs
sudo tail -f /var/log/nginx/amarktai-error.log
```

### Restart Services

```bash
# Restart backend only
sudo systemctl restart amarktai-backend

# Restart nginx only
sudo systemctl restart nginx

# Full restart
sudo systemctl restart amarktai-backend nginx
```

### Update Application

```bash
# 1. Pull latest code
cd /var/amarktai/app
git pull origin main

# 2. Update backend dependencies (if needed)
cd backend
source venv/bin/activate
pip install -r requirements.txt

# 3. Rebuild frontend
cd ../frontend
npm install
npm run build

# 4. Run doctor script
cd ../backend
./scripts/doctor.sh

# 5. Restart services
sudo systemctl restart amarktai-backend
sudo systemctl reload nginx

# 6. Verify
curl https://amarktai.online/api/health/ready
```

## 7. Troubleshooting

### Backend Won't Start (502 Bad Gateway)

1. Check systemd status:
   ```bash
   sudo systemctl status amarktai-backend
   ```

2. Check logs for errors:
   ```bash
   sudo journalctl -u amarktai-backend -n 100
   ```

3. Common issues:
   - MongoDB not running: `sudo systemctl status mongodb`
   - JWT_SECRET not set: Check `.env` file
   - Port 8000 already in use: `sudo lsof -i :8000`
   - Import errors: Re-run `pip install -r requirements.txt`

### WebSocket Connection Fails

1. Check nginx has WebSocket headers configured (see nginx config above)
2. Check browser console for error message
3. Verify backend WebSocket endpoint: `curl http://localhost:8000/api/ws`
4. Check nginx error logs: `sudo tail -f /var/log/nginx/amarktai-error.log`

### Dashboard Shows Console Errors

1. Open browser DevTools (F12)
2. Check Console tab for specific errors
3. Common issues:
   - 401 Unauthorized: Token expired, re-login
   - 404 Not Found: API endpoint doesn't exist, check version
   - CORS errors: Check nginx CORS headers

### Database Connection Issues

1. Check MongoDB status:
   ```bash
   sudo systemctl status mongodb
   ```

2. Test connection:
   ```bash
   mongo amarktai --eval "db.stats()"
   ```

3. Check MongoDB logs:
   ```bash
   sudo tail -f /var/log/mongodb/mongodb.log
   ```

## 8. Security Hardening

1. **Change default credentials**: Update `JWT_SECRET` and `ADMIN_PASSWORD` in `.env`
2. **Enable firewall**:
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 22/tcp
   sudo ufw enable
   ```
3. **SSL/TLS**: Use Let's Encrypt for free SSL certificates
4. **Rate limiting**: Configure nginx rate limiting (see nginx docs)
5. **Database security**: Configure MongoDB authentication
6. **Regular updates**: Keep system packages updated

## 9. Backup and Recovery

### Database Backup

```bash
# Backup MongoDB
mongodump --db amarktai --out /backup/mongo/$(date +%Y%m%d)

# Restore MongoDB
mongorestore --db amarktai /backup/mongo/20240128/amarktai
```

### Application Backup

```bash
# Backup application code and config
tar -czf /backup/app/amarktai-$(date +%Y%m%d).tar.gz /var/amarktai/app
```

## Support

For issues or questions:
- Check logs first (systemd, nginx, browser console)
- Run doctor script: `./backend/scripts/doctor.sh`
- Run smoke tests: `./scripts/smoke.sh`
- Review this guide for common troubleshooting steps

---

**Last Updated**: 2024-01-28
**Version**: 1.0.6
