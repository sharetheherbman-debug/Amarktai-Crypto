# Amarktai Network - Production Deployment Guide

## 🎯 Overview

This guide provides step-by-step instructions for deploying Amarktai Network to a fresh Ubuntu 24.04 VPS (tested on Webdock).

**After following this guide, you will have:**
- ✅ Backend API running on port 8000 via systemd
- ✅ Frontend served via Nginx
- ✅ Real-time SSE and WebSocket support
- ✅ Encrypted API key storage
- ✅ MongoDB integrated
- ✅ Logging to `/var/log/amarktai/`

---

## 📋 Prerequisites

- Ubuntu 24.04 LTS VPS
- Root or sudo access
- Domain name (optional, can use IP)
- Minimum 2GB RAM, 2 CPU cores recommended

---

## 🚀 Quick Start (Automated Installation)

### Option 1: Clone and Install

```bash
# 1. Clone repository
cd /var/amarktai
sudo git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git app
cd app

# 2. Run automated installer (as root)
sudo bash deployment/install.sh

# 3. Create environment config
sudo mkdir -p /etc/amarktai
sudo cp backend/.env.example /etc/amarktai/amarktai.env
sudo nano /etc/amarktai/amarktai.env  # Edit with your values

# 4. Restart service
sudo systemctl restart amarktai-api

# 5. Check status
sudo systemctl status amarktai-api
sudo journalctl -u amarktai-api -f
```

---

## 🔧 Manual Installation

### Step 1: System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12 and build tools
sudo apt install -y python3.12 python3.12-venv python3-pip \
    build-essential git curl nginx mongodb-org

# Start MongoDB
sudo systemctl enable mongod
sudo systemctl start mongod
```

### Step 2: Clone Repository

```bash
# Create directory structure
sudo mkdir -p /var/amarktai
sudo mkdir -p /var/log/amarktai
cd /var/amarktai

# Clone repo
sudo git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git app
cd app

# Set permissions
sudo chown -R www-data:www-data /var/amarktai
sudo chmod -R 755 /var/amarktai
```

### Step 3: Backend Setup

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment/backend

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m compileall . || echo "⚠️ Some files have syntax warnings"
```

### Step 4: Configuration

```bash
# Create environment file directory
sudo mkdir -p /etc/amarktai

# Copy and edit environment file
sudo cp backend/.env.example /etc/amarktai/amarktai.env
sudo nano /etc/amarktai/amarktai.env
```

**Required environment variables:**
```bash
# MongoDB
MONGO_URI=mongodb://localhost:27017/amarktai

# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET=your_secure_random_secret_here

# Fernet encryption key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
AMARKTAI_FERNET_KEY=your_fernet_key_here

# Admin password
ADMIN_PASSWORD=your_secure_admin_password

# API Keys (Optional - for AI features)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...

# Server
PORT=8000
HOST=127.0.0.1
```

### Step 5: Systemd Service

```bash
# Copy systemd service file
sudo cp /var/amarktai/app/Amarktai-Network---Deployment/deployment/systemd/amarktai-api.service \
    /etc/systemd/system/amarktai-api.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable amarktai-api
sudo systemctl start amarktai-api

# Check status
sudo systemctl status amarktai-api

# View logs
sudo journalctl -u amarktai-api -f
```

### Step 6: Nginx Configuration

```bash
# Copy Nginx config
sudo cp /var/amarktai/app/Amarktai-Network---Deployment/deployment/nginx-amarktai.conf \
    /etc/nginx/sites-available/amarktai

# Edit domain/IP
sudo nano /etc/nginx/sites-available/amarktai
# Change: server_name YOUR_DOMAIN_OR_IP;

# Enable site
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Step 7: Build Frontend

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment/frontend

# Install Node.js 18+ (if not installed)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install dependencies
npm install

# Build
npm run build

# Verify build
ls -la build/
```

---

## ✅ Verification & Smoke Tests

### Run Automated Smoke Tests

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment

# Local smoke test (backend must be running)
bash scripts/smoke_api.sh

# Or specify custom API base
API_BASE=http://your-vps-ip bash scripts/smoke_api.sh
```

### Manual Verification

```bash
# 1. Health check
curl http://localhost:8000/api/system/ping
# Expected: {"status":"ok"}

# 2. Check systemd status
sudo systemctl status amarktai-api

# 3. Check logs for errors
sudo tail -f /var/log/amarktai/backend.log

# 4. Test frontend (replace with your IP/domain)
curl http://your-vps-ip/

# 5. Test SSE endpoint (should stream events)
curl -N -H "Authorization: Bearer YOUR_JWT_TOKEN" \
    http://localhost:8000/api/realtime/events
```

---

## 🎮 Admin Access

### Create Admin User

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment/backend
source .venv/bin/activate

# Run bootstrap script
python scripts/bootstrap_admin.py
```

Or manually via MongoDB:

```bash
mongo amarktai
db.users.updateOne(
    {email: "your@email.com"},
    {$set: {is_admin: true, role: "admin"}}
)
```

### Unlock Admin Panel

1. Login to dashboard
2. Press: **Ctrl + Shift + A** (or click hidden area)
3. Enter admin password from environment config
4. Admin panel will appear in navigation

---

## 🔧 Supported Exchanges

**Exactly 7 exchanges are supported:**

1. **Luno** 🇿🇦 (South African fiat on-ramp)
2. **Binance** 🟡 (Global, largest volume)
3. **KuCoin** 🟢 (Requires passphrase)
4. **Bybit** 🟠 (Derivatives focus)
5. **Kraken** 🟣 (US-based)
6. **Bitget** 🔵 (Requires passphrase)
7. **Gate.io** ⚪ (Global)

**Note:** VALR and OVEX have been removed from active code and are archived only.

---

## 🛠️ Troubleshooting

### Backend Won't Start

```bash
# Check logs
sudo journalctl -u amarktai-api -n 100

# Check environment file
sudo cat /etc/amarktai/amarktai.env

# Test manually
cd /var/amarktai/app/Amarktai-Network---Deployment/backend
source .venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

### MongoDB Connection Issues

```bash
# Check MongoDB status
sudo systemctl status mongod

# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log

# Test connection
mongo --eval "db.adminCommand('ping')"
```

### Nginx 502 Bad Gateway

```bash
# Check if backend is running
sudo systemctl status amarktai-api

# Check backend is listening on port 8000
sudo netstat -tlnp | grep 8000

# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Real-time (SSE/WebSocket) Not Working

```bash
# Check Nginx config has correct proxy headers
sudo nginx -T | grep -A 10 "location /api/realtime"

# Test SSE endpoint directly (bypass Nginx)
curl -N -H "Authorization: Bearer JWT_TOKEN" \
    http://127.0.0.1:8000/api/realtime/events
```

---

## 🔐 Security Checklist

- [ ] Changed default admin password
- [ ] Set strong JWT_SECRET (32+ characters)
- [ ] Generated unique AMARKTAI_FERNET_KEY
- [ ] MongoDB authentication enabled (if exposed)
- [ ] Firewall configured (ufw allow 80,443)
- [ ] SSL/TLS certificate installed (Let's Encrypt)
- [ ] Restricted SSH access (key-based auth)
- [ ] Regular backups configured

---

## 📊 Monitoring

### View Logs

```bash
# Backend logs
sudo tail -f /var/log/amarktai/backend.log

# Systemd journal
sudo journalctl -u amarktai-api -f

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Service Management

```bash
# Restart backend
sudo systemctl restart amarktai-api

# Stop backend
sudo systemctl stop amarktai-api

# Check status
sudo systemctl status amarktai-api

# View service file
systemctl cat amarktai-api
```

---

## 🔄 Updates & Maintenance

### Update Application

```bash
cd /var/amarktai/app/Amarktai-Network---Deployment

# Pull latest changes
sudo git pull origin main

# Update backend dependencies
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# Rebuild frontend
cd ../frontend
npm install
npm run build

# Restart services
sudo systemctl restart amarktai-api
sudo systemctl reload nginx
```

### Database Backup

```bash
# Backup MongoDB
sudo mongodump --db=amarktai --out=/var/backups/amarktai-$(date +%Y%m%d)

# Restore MongoDB
sudo mongorestore --db=amarktai /var/backups/amarktai-20240203/amarktai
```

---

## 📞 Support

- **Email:** amarktainetwork@gmail.com
- **GitHub Issues:** https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment/issues

---

## 📝 Acceptance Criteria Checklist

After deployment, verify:

- [ ] `curl http://127.0.0.1:8000/api/health/ping` returns 200
- [ ] Login returns JWT token
- [ ] Dashboard loads at root URL
- [ ] API key save works (no 422 error)
- [ ] API key test works (no 422 error)
- [ ] System mode switch works without user_id query param
- [ ] SSE `/api/realtime/events` emits heartbeat
- [ ] WebSocket `/api/ws` connects with JWT
- [ ] Admin panel accessible after password unlock
- [ ] Chat history persists per-user only
- [ ] No VALR/OVEX in active code paths

---

© 2026 Amarktai Network. For personal use only.
