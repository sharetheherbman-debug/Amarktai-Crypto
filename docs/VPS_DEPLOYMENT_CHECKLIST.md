# VPS Deployment Checklist - Webdock

This checklist ensures a smooth deployment of Amarktai Network on a Webdock VPS running Ubuntu 24.04.

## Prerequisites

- [x] Ubuntu 24.04 VPS (Webdock or compatible)
- [x] Root/sudo access
- [x] Minimum 2GB RAM, 20GB disk
- [x] Internet connectivity

## Step-by-Step Deployment

### 1. System Preparation

```bash
# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
sudo apt-get install -y git python3 python3-venv python3-pip \
  build-essential curl nginx mongodb-org
```

### 2. Clone Repository

```bash
# Clone to recommended location
sudo mkdir -p /var/amarktai
cd /var/amarktai
sudo git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git app
cd app
```

### 3. Backend Setup

```bash
# Create Python virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Frontend Setup

```bash
# Install Node.js 20+ (if not already installed)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Build frontend
cd ../frontend
npm install
npm run build
cd ..
```

### 5. Environment Configuration

```bash
# Generate encryption key
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

# Create and configure .env file
cd backend
cp .env.example .env
nano .env
```

**Required environment variables:**
- `AMARKTAI_FERNET_KEY` - from step above
- `JWT_SECRET` - random secure string
- `MONGO_URL` - MongoDB connection string

### 6. MongoDB Setup

```bash
# Create required directories
sudo mkdir -p /var/lib/mongodb /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb
sudo chmod 755 /var/lib/mongodb /var/log/mongodb

# Start MongoDB
sudo systemctl enable mongod
sudo systemctl start mongod
sudo systemctl status mongod
```

### 7. Run Preflight Checks

```bash
cd /var/amarktai/app
./scripts/doctor.sh
```

**Expected:** Mostly passing checks (MongoDB directory warnings are OK if created)

### 8. Setup Systemd Service

```bash
# Copy service file
sudo cp deployment/amarktai-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable amarktai-api
sudo systemctl start amarktai-api
sudo systemctl status amarktai-api
```

### 9. Configure Nginx

```bash
# Copy nginx configuration
sudo cp deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### 10. Verify Deployment

```bash
# Test API health endpoint
curl http://127.0.0.1:8000/api/health/ping

# Run smoke test
./scripts/smoke_local.sh

# Check service logs
sudo journalctl -u amarktai-api -f
```

## Success Criteria

- ✅ Backend service running: `sudo systemctl status amarktai-api`
- ✅ MongoDB running: `sudo systemctl status mongod`
- ✅ Nginx running: `sudo systemctl status nginx`
- ✅ Health endpoint returns 200: `curl http://127.0.0.1:8000/api/health/ping`
- ✅ Frontend accessible via Nginx
- ✅ No critical errors in logs: `sudo journalctl -u amarktai-api -n 100`

## Troubleshooting

### Backend won't start

```bash
# Check logs
sudo journalctl -u amarktai-api -n 100 --no-pager

# Verify environment
sudo cat /var/amarktai/app/backend/.env | grep -v "SECRET\|KEY"

# Test manual start
cd /var/amarktai/app/backend
source .venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

### Frontend build failed

```bash
# Rebuild frontend
cd /var/amarktai/app/frontend
rm -rf node_modules build
npm install
npm run build
```

### MongoDB won't start

```bash
# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log

# Verify directories exist
ls -la /var/lib/mongodb /var/log/mongodb

# Recreate if needed
sudo mkdir -p /var/lib/mongodb /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb
sudo systemctl restart mongod
```

## Post-Deployment

1. **SSL Certificate** - Setup Let's Encrypt for HTTPS
2. **Firewall** - Configure UFW to allow only necessary ports
3. **Monitoring** - Setup log aggregation and alerting
4. **Backups** - Configure automated MongoDB backups
5. **Updates** - Schedule regular security updates

## Quick Reference Commands

```bash
# Restart services
sudo systemctl restart amarktai-api
sudo systemctl restart mongod
sudo systemctl restart nginx

# View logs
sudo journalctl -u amarktai-api -f
sudo tail -f /var/log/mongodb/mongod.log
sudo tail -f /var/log/nginx/error.log

# Update code
cd /var/amarktai/app
sudo git pull
cd frontend && npm install && npm run build
cd ../backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart amarktai-api
```
