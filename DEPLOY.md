# Amarktai Crypto - Production Deployment Guide

Quick reference for deploying updates to the Amarktai Crypto trading platform on Ubuntu 24.04.

## Prerequisites

- Root or sudo access to VPS
- Backend running as systemd service: `amarktai-api`
- Frontend deployed to `/var/www/amarktai-frontend`
- Nginx configured and running

## Deployment Steps

### 1. Git Pull/Reset

Navigate to the repository and pull latest changes:

```bash
cd /home/amarktai/Amarktai-Network---Deployment
git fetch origin
git reset --hard origin/main  # or your deployment branch
git pull origin main
```

### 2. Backend: Install Dependencies

Activate virtual environment and install/update dependencies:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
```

If `.venv` doesn't exist, create it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Backend: Restart Service

Restart the systemd service to apply backend changes:

```bash
sudo systemctl restart amarktai-api
sudo systemctl status amarktai-api  # Verify it started successfully
```

Check logs if service fails to start:

```bash
sudo journalctl -u amarktai-api -n 50 --no-pager
```

### 4. Nginx: Verify Configuration

Test nginx configuration before reload:

```bash
sudo nginx -t
```

If configuration is valid, reload nginx:

```bash
sudo systemctl reload nginx
sudo systemctl status nginx  # Verify it reloaded successfully
```

### 5. Frontend: Build and Deploy

Build frontend with production settings:

```bash
cd ../frontend
npm install  # Install/update dependencies
npm run build
```

Deploy built frontend to nginx directory:

```bash
sudo rsync -av --delete build/ /var/www/amarktai-frontend/
```

Alternative using cp:

```bash
sudo rm -rf /var/www/amarktai-frontend/*
sudo cp -r build/* /var/www/amarktai-frontend/
```

Set correct permissions:

```bash
sudo chown -R www-data:www-data /var/www/amarktai-frontend
sudo chmod -R 755 /var/www/amarktai-frontend
```

### 6. Health Checks

Verify deployment with health check commands:

#### Local Backend Health Check
```bash
curl http://localhost:8000/api/health/ping
# Expected: {"status":"ok","message":"pong"}
```

#### Production Domain Health Check
```bash
curl https://amarktai.online/api/health/ping
# Expected: {"status":"ok","message":"pong"}
```

#### Verify Platforms Endpoint (7 exchanges)
```bash
curl http://localhost:8000/api/platforms | jq '.platforms | length'
# Expected: 7
```

#### Run Comprehensive Smoke Test
```bash
cd scripts
./smoke_test.sh
```

### 7. Post-Deployment Verification

- [ ] Backend API responds on port 8000
- [ ] Frontend loads at https://amarktai.online
- [ ] Login functionality works
- [ ] Dashboard displays correctly
- [ ] All 7 exchanges visible (luno, binance, kucoin, bybit, kraken, bitget, gate)
- [ ] WebSocket connections established
- [ ] No console errors in browser

## Quick Commands Reference

### Service Management
```bash
# Restart backend
sudo systemctl restart amarktai-api

# Check backend status
sudo systemctl status amarktai-api

# View backend logs
sudo journalctl -u amarktai-api -f

# Reload nginx
sudo systemctl reload nginx
```

### Health Checks
```bash
# Local API health
curl localhost:8000/api/health/ping

# Production health
curl https://amarktai.online/api/health/ping

# Port check
netstat -tuln | grep 8000
# or
ss -tuln | grep 8000

# Full smoke test
./scripts/smoke_test.sh
```

### Frontend Deployment
```bash
# Build and deploy frontend
cd frontend
npm run build
sudo rsync -av --delete build/ /var/www/amarktai-frontend/
sudo chown -R www-data:www-data /var/www/amarktai-frontend
```

## Rollback Procedure

If deployment fails, rollback to previous version:

```bash
# 1. Find previous commit
git log --oneline -10

# 2. Checkout previous version
git checkout <previous-commit-hash>

# 3. Restart services
cd backend
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart amarktai-api

cd ../frontend
npm install
npm run build
sudo rsync -av --delete build/ /var/www/amarktai-frontend/
```

## Environment Configuration

Critical environment variables in `/home/amarktai/Amarktai-Network---Deployment/backend/.env`:

- `MONGO_URL` - MongoDB connection string
- `JWT_SECRET` - JWT signing secret
- `AMARKTAI_FERNET_KEY` - Encryption key for API keys
- `PAPER_TRADING` - Enable paper trading (0 or 1)
- `LIVE_TRADING` - Enable live trading (0 or 1)

After changing `.env`, always restart the backend service.

## Troubleshooting

### Backend won't start
```bash
# Check logs
sudo journalctl -u amarktai-api -n 100 --no-pager

# Check Python errors
cd /home/amarktai/Amarktai-Network---Deployment/backend
source .venv/bin/activate
python main.py  # Run directly to see errors
```

### Frontend not updating
```bash
# Clear browser cache
# Verify files were copied
ls -la /var/www/amarktai-frontend/

# Check nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Database connection issues
```bash
# Check MongoDB status
sudo systemctl status mongodb
# or for mongod
sudo systemctl status mongod

# Test connection
mongo --eval "db.adminCommand('ping')"
```

## Support

- Check logs: `/var/log/amarktai/`
- System logs: `sudo journalctl -u amarktai-api -f`
- Nginx logs: `/var/log/nginx/`

## Security Notes

- Never commit `.env` files to git
- Rotate `JWT_SECRET` and `AMARKTAI_FERNET_KEY` regularly
- Use `HTTPS` for all production traffic
- Keep Ubuntu and dependencies updated

---

**Last Updated:** 2026-02-04  
**Platform Version:** Amarktai Crypto v3.0  
**Target OS:** Ubuntu 24.04 LTS
