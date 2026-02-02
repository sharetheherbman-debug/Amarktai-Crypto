# Deployment Guide - Ubuntu 24.04

**Date:** December 27, 2025  
**Target:** Ubuntu 24.04 LTS  
**Repository:** Amarktai-Network---Deployment

---

## Overview

This guide provides step-by-step instructions for deploying the Amarktai Network trading platform on Ubuntu 24.04.

---

## Prerequisites

- Ubuntu 24.04 LTS server
- Root or sudo access
- Domain name (optional but recommended)
- MongoDB installed or accessible
- Minimum 2GB RAM, 20GB disk space

---

## Quick Start (Single Command)

```bash
# Clone repository
git clone https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment

# Run setup
./deployment/vps-setup.sh

# Fix deployment paths
./deployment/setup_deployment_path.sh
```

---

## Detailed Installation Steps

### 1. System Updates

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Required Dependencies

```bash
# Python 3.12 (default in Ubuntu 24.04)
sudo apt install -y python3 python3-venv python3-pip

# MongoDB (if not already installed)
sudo apt install -y mongodb-org

# Node.js 20.x (for frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Nginx (reverse proxy)
sudo apt install -y nginx

# Other dependencies
sudo apt install -y git curl build-essential
```

### 3. Clone Repository

```bash
cd ~
git clone https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment
```

### 4. Setup Backend

```bash
cd backend

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables

```bash
# Create .env file
cp .env.example .env  # If example exists, or create manually

# Edit .env file
nano .env
```

**Required environment variables:**

```ini
# MongoDB
MONGODB_URL=mongodb://localhost:27017/amarktai

# JWT Secret
JWT_SECRET=your-super-secret-jwt-key-change-this

# API Keys Encryption
ENCRYPTION_KEY=your-32-character-encryption-key

# SMTP (for email reports)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@amarktai.com
SMTP_TO=admin@amarktai.com

# Environment
ENVIRONMENT=production
DEBUG=false

# Frontend URL (for CORS)
FRONTEND_URL=https://your-domain.com
```

### 6. Fix Deployment Path

The systemd service expects code at `/var/amarktai/app`, but you've cloned to `~/Amarktai-Network---Deployment`. Fix this:

**Option A: Quick Fix (Symlink) - Recommended for Development**

```bash
cd ~/Amarktai-Network---Deployment
./deployment/setup_deployment_path.sh

# Choose option 1 when prompted
# This creates a symlink: /var/amarktai/app -> ~/Amarktai-Network---Deployment
```

**Option B: Production Install - Recommended for Production**

```bash
cd ~/Amarktai-Network---Deployment
./deployment/setup_deployment_path.sh

# Choose option 2 when prompted
# This copies files to /var/amarktai/app with proper ownership
```

**Option C: Update Systemd Service**

```bash
cd ~/Amarktai-Network---Deployment
./deployment/setup_deployment_path.sh

# Choose option 3 when prompted
# This creates a custom service file pointing to current location
# Then manually copy it:
sudo cp deployment/amarktai-api.service.local /etc/systemd/system/amarktai-api.service
```

### 7. Setup Systemd Service

```bash
# Copy service file (if not done by setup script)
sudo cp deployment/amarktai-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable amarktai-api

# Start service
sudo systemctl start amarktai-api

# Check status
sudo systemctl status amarktai-api
```

### 8. Setup Frontend

```bash
cd ~/Amarktai-Network---Deployment/frontend

# Install dependencies
npm install

# Build for production
npm run build

# Copy build to web server
sudo cp -r build /var/www/amarktai
sudo chown -R www-data:www-data /var/www/amarktai
```

### 9. Configure Nginx

```bash
# Create Nginx configuration
sudo nano /etc/nginx/sites-available/amarktai
```

**Nginx configuration:**

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Frontend
    location / {
        root /var/www/amarktai;
        try_files $uri $uri/ /index.html;
    }
    
    # Backend API
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket
    location /api/ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
```

**Enable site:**

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

### 10. Setup SSL (Optional but Recommended)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal is configured automatically
```

---

## Verification

### Check Services

```bash
# Backend API
sudo systemctl status amarktai-api

# MongoDB
sudo systemctl status mongodb

# Nginx
sudo systemctl status nginx
```

### Check Logs

```bash
# Backend logs
sudo journalctl -u amarktai-api -f

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/api/health/ping

# Should return: {"status":"ok","timestamp":"..."}

# Portfolio summary (requires authentication)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/portfolio/summary
```

---

## Troubleshooting

### Service Won't Start

**Problem:** `amarktai-api.service` fails to start

**Solution:**

```bash
# Check logs
sudo journalctl -u amarktai-api -n 50

# Common issues:
# 1. Path mismatch - Run deployment/setup_deployment_path.sh
# 2. Missing .env file - Check /var/amarktai/app/backend/.env exists
# 3. MongoDB not running - sudo systemctl start mongodb
# 4. Port already in use - Check: sudo lsof -i :8000
```

### Python Import Errors

**Problem:** `ModuleNotFoundError` in logs

**Solution:**

```bash
# Activate venv and reinstall
cd /var/amarktai/app/backend
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart amarktai-api
```

### Frontend Not Loading

**Problem:** Nginx returns 404 or blank page

**Solution:**

```bash
# Check frontend build exists
ls -la /var/www/amarktai

# If missing, rebuild:
cd ~/Amarktai-Network---Deployment/frontend
npm run build
sudo cp -r build /var/www/amarktai
sudo systemctl restart nginx
```

### API Endpoints Return 404

**Problem:** Backend is running but endpoints return 404

**Solution:**

```bash
# Check if routers are mounted
cd /var/amarktai/app/backend
source .venv/bin/activate
python3 -c "
from server import app
for route in app.routes:
    print(route.path)
" | grep -E "portfolio|profits|countdown|keys"

# Should show:
# /api/portfolio/summary
# /api/profits
# /api/countdown/status
# /api/keys/test
# /api/keys/save
```

### MongoDB Connection Failed

**Problem:** Backend can't connect to MongoDB

**Solution:**

```bash
# Check MongoDB is running
sudo systemctl status mongodb

# Start if stopped
sudo systemctl start mongodb

# Test connection
mongosh --eval "db.adminCommand('ping')"

# Check .env has correct MONGODB_URL
cat /var/amarktai/app/backend/.env | grep MONGODB_URL
```

---

## Maintenance

### Update Application

```bash
# Navigate to repository
cd ~/Amarktai-Network---Deployment  # or /var/amarktai/app if using option 2

# Pull latest changes
git pull

# Update backend dependencies
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# Rebuild frontend
cd ../frontend
npm install
npm run build
sudo cp -r build /var/www/amarktai

# Restart service
sudo systemctl restart amarktai-api
sudo systemctl restart nginx
```

### Backup

```bash
# Backup MongoDB
mongodump --out=/backup/mongodb-$(date +%Y%m%d)

# Backup .env file
sudo cp /var/amarktai/app/backend/.env /backup/env-$(date +%Y%m%d).bak

# Backup Nginx config
sudo cp /etc/nginx/sites-available/amarktai /backup/nginx-$(date +%Y%m%d).conf
```

### Monitor

```bash
# Real-time logs
sudo journalctl -u amarktai-api -f

# Check disk space
df -h

# Check memory usage
free -h

# Check processes
ps aux | grep uvicorn
```

---

## Security Checklist

- [ ] Changed default JWT_SECRET in .env
- [ ] Changed default ENCRYPTION_KEY in .env
- [ ] MongoDB has authentication enabled
- [ ] Firewall configured (ufw or iptables)
- [ ] SSL certificate installed
- [ ] Regular backups configured
- [ ] Log rotation configured
- [ ] System updates automated

---

## Performance Optimization

### Backend (Uvicorn)

```bash
# Edit service file to use multiple workers
sudo nano /etc/systemd/system/amarktai-api.service

# Change ExecStart to:
ExecStart=/var/amarktai/app/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 --workers 4

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

### MongoDB

```bash
# Enable MongoDB authentication
# Edit MongoDB config
sudo nano /etc/mongod.conf

# Add:
security:
  authorization: enabled

# Create admin user
mongosh
use admin
db.createUser({
  user: "admin",
  pwd: "your-strong-password",
  roles: ["root"]
})
```

### Nginx Caching

Add to Nginx config:

```nginx
# Cache static assets
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## Support

- **Documentation:** See PRODUCTION_READINESS_ASSESSMENT.md
- **Frontend Integration:** See FRONTEND_INTEGRATION_GUIDE.md
- **API Endpoints:** See BACKEND_FRONTEND_PARITY_REPORT.md
- **Issues:** GitHub Issues

---

**Last Updated:** December 27, 2025  
**Maintained By:** Amarktai Network Development Team
