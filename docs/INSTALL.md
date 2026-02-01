# Amarktai Network - Production Deployment Guide
## Fresh Install on Ubuntu 24.04 in ~30 Minutes

This guide will walk you through deploying the Amarktai Trading Network from scratch on a clean Ubuntu 24.04 VPS.

---

## Prerequisites

- Ubuntu 24.04 LTS server (Webdock VPS or similar)
- Root or sudo access
- At least 2GB RAM, 2 CPU cores, 20GB disk
- Domain name (optional, for SSL/HTTPS)

---

## Step 1: System Preparation (5 minutes)

### 1.1 Update system
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Install required packages
```bash
sudo apt install -y \
    python3 python3-pip python3-venv \
    nodejs npm \
    mongodb \
    nginx \
    git \
    curl \
    ufw
```

### 1.3 Configure firewall
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8000/tcp  # Backend (optional, can be removed after nginx setup)
sudo ufw --force enable
```

---

## Step 2: MongoDB Setup (3 minutes)

### 2.1 Start MongoDB
```bash
sudo systemctl start mongod
sudo systemctl enable mongod
```

### 2.2 Verify MongoDB is running
```bash
sudo systemctl status mongod
```

### 2.3 Create database (optional - will auto-create)
```bash
mongosh --eval "use amarktai_trading"
```

---

## Step 3: Application Setup (10 minutes)

### 3.1 Create application user
```bash
sudo useradd -m -s /bin/bash amarktai
sudo mkdir -p /opt/amarktai
sudo chown amarktai:amarktai /opt/amarktai
```

### 3.2 Clone repository
```bash
sudo -u amarktai bash
cd /opt/amarktai
git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git .
```

### 3.3 Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.4 Install Python dependencies
```bash
pip install --upgrade pip
pip install -r backend/requirements.txt

# Optional: AI features
pip install -r backend/requirements-ai.txt
```

### 3.5 Configure environment
```bash
cp backend/.env.example .env
nano .env
```

**Required environment variables:**
```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security (CHANGE THESE!)
JWT_SECRET=$(openssl rand -hex 32)
AMARKTAI_FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Trading modes (start with all disabled for safety)
PAPER_TRADING=0
LIVE_TRADING=0
AUTOPILOT_ENABLED=0

# Optional: OpenAI for AI features
OPENAI_API_KEY=your-key-here

# Optional: Email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=your-email@gmail.com
```

### 3.6 Run preflight check
```bash
./scripts/preflight.sh
```

If preflight passes, continue. If errors, fix them before proceeding.

---

## Step 4: Frontend Build (5 minutes)

### 4.1 Install frontend dependencies
```bash
cd /opt/amarktai/frontend
npm install
```

### 4.2 Build frontend
```bash
npm run build
```

This creates `/opt/amarktai/frontend/dist` directory.

---

## Step 5: Systemd Service (3 minutes)

### 5.1 Copy service file
```bash
sudo cp /opt/amarktai/docs/examples/amarktai.service /etc/systemd/system/
```

### 5.2 Update service file if needed
```bash
sudo nano /etc/systemd/system/amarktai.service
```

Ensure paths match your setup:
- `WorkingDirectory=/opt/amarktai`
- `EnvironmentFile=/opt/amarktai/.env`
- `ExecStart=/opt/amarktai/venv/bin/uvicorn backend.server:app --host 0.0.0.0 --port 8000 --workers 4`

### 5.3 Start service
```bash
sudo systemctl daemon-reload
sudo systemctl enable amarktai
sudo systemctl start amarktai
```

### 5.4 Verify service is running
```bash
sudo systemctl status amarktai
```

### 5.5 Test backend
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

---

## Step 6: Nginx Configuration (4 minutes)

### 6.1 Copy nginx config
```bash
sudo cp /opt/amarktai/docs/examples/nginx.conf /etc/nginx/sites-available/amarktai
```

### 6.2 Update domain name
```bash
sudo nano /etc/nginx/sites-available/amarktai
```

Replace `amarktai.example.com` with your actual domain.

### 6.3 Enable site
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

### 6.4 (Optional) Setup SSL with Let's Encrypt
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Step 7: Verification (5 minutes)

### 7.1 Run verification script
```bash
cd /opt/amarktai
./scripts/verify.sh
```

### 7.2 Check all endpoints
Expected results:
- ✓ Health endpoints: 200 OK
- ✓ System status: 200 OK
- ✓ Diagnostics: 200 OK or 401 (if auth required)

### 7.3 Create admin user
```bash
cd /opt/amarktai
source venv/bin/activate
python scripts/bootstrap_admin.py
```

### 7.4 Access dashboard
Open browser: `https://your-domain.com`

**Default credentials:**
- Email: Set during bootstrap
- Password: Set during bootstrap

---

## Step 8: Exchange Configuration

### 8.1 Add exchange API keys

1. Login to dashboard
2. Navigate to "API Keys" section
3. Add keys for exchanges:
   - **Luno** (required for ZAR)
   - Binance
   - KuCoin
   - Bybit
   - Kraken
   - Bitget
   - Gate.io

### 8.2 Test connectivity
Navigate to **Diagnostics** → **System Health** to verify exchange connections.

---

## Step 9: Enable Trading (When Ready)

### 9.1 Start with paper trading
```bash
nano /opt/amarktai/.env
```

Update:
```bash
PAPER_TRADING=1
```

Restart:
```bash
sudo systemctl restart amarktai
```

### 9.2 Enable live trading (after 7 days paper trading)
```bash
PAPER_TRADING=1
LIVE_TRADING=1
```

### 9.3 Enable autopilot (optional)
```bash
AUTOPILOT_ENABLED=1
```

---

## Post-Installation

### Monitoring

**Check logs:**
```bash
sudo journalctl -u amarktai -f
```

**Check system health:**
```bash
curl http://localhost:8000/api/diagnostics/system-health
```

### Maintenance

**Update application:**
```bash
cd /opt/amarktai
git pull
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build
sudo systemctl restart amarktai
```

**Backup database:**
```bash
mongodump --db amarktai_trading --out /backup/$(date +%Y%m%d)
```

### Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u amarktai -n 50
```

**MongoDB connection issues:**
```bash
sudo systemctl status mongod
mongosh --eval "db.adminCommand('ping')"
```

**Port already in use:**
```bash
sudo lsof -i :8000
sudo kill <PID>
```

---

## Security Checklist

- [x] Changed JWT_SECRET from default
- [x] Set AMARKTAI_FERNET_KEY for API key encryption
- [x] Configured firewall (UFW)
- [x] Setup SSL/HTTPS with Let's Encrypt
- [x] MongoDB running locally (not exposed)
- [x] Created non-root user for application
- [x] Set restrictive file permissions on .env

**Additional hardening:**
```bash
# Restrict .env permissions
chmod 600 /opt/amarktai/.env
chown amarktai:amarktai /opt/amarktai/.env

# Disable SSH password auth (use keys only)
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

---

## Quick Reference

### Service Management
```bash
sudo systemctl start amarktai
sudo systemctl stop amarktai
sudo systemctl restart amarktai
sudo systemctl status amarktai
```

### Logs
```bash
# Application logs
sudo journalctl -u amarktai -f

# Nginx logs
sudo tail -f /var/log/nginx/amarktai-access.log
sudo tail -f /var/log/nginx/amarktai-error.log
```

### Emergency Stop
```bash
# Via API
curl -X POST http://localhost:8000/api/emergency-stop/activate

# Via service
sudo systemctl stop amarktai
```

---

## Support

For issues, consult:
- **Diagnostics**: https://your-domain.com/api/diagnostics/system-health
- **Logs**: `sudo journalctl -u amarktai -n 100`
- **GitHub Issues**: https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment/issues

---

## Production Deployment Timeline

| Time | Step | Description |
|------|------|-------------|
| 0-5 min | System prep | Update, install packages, firewall |
| 5-8 min | MongoDB | Install and start |
| 8-18 min | Application | Clone, install dependencies, configure |
| 18-23 min | Frontend | Build React app |
| 23-26 min | Systemd | Setup and start service |
| 26-30 min | Nginx | Configure reverse proxy |
| 30-35 min | Verification | Test endpoints, create admin |

**Total: ~35 minutes** (including verification)

---

## Exchange Requirements

### Supported Exchanges (7 total)

1. **Luno** (Primary for ZAR)
   - API Keys: API Key + API Secret
   - Permissions: Read, Trade
   - Region: South Africa

2. **Binance**
   - API Keys: API Key + API Secret
   - Permissions: Read, Spot Trading
   - IP Whitelist: Optional

3. **KuCoin**
   - API Keys: API Key + API Secret + Passphrase
   - Permissions: Read, Trade
   
4. **Bybit**
   - API Keys: API Key + API Secret
   - Permissions: Read, Trade (Spot)

5. **Kraken**
   - API Keys: API Key + Private Key
   - Permissions: Query Funds, Create & Modify Orders

6. **Bitget**
   - API Keys: API Key + API Secret + Passphrase
   - Permissions: Read, Trade

7. **Gate.io**
   - API Keys: API Key + API Secret
   - Permissions: Read, Trade

### Max Bots Per Exchange
- Luno: 5 bots
- Binance: 10 bots
- KuCoin: 10 bots
- Bybit: 10 bots
- Kraken: 10 bots
- Bitget: 10 bots
- Gate.io: 10 bots
- **Total: 65 bots maximum**

---

## Success Criteria

After installation, verify:

✅ Health endpoint returns 200
✅ Can login to dashboard
✅ Can add exchange API keys
✅ System diagnostics show "healthy"
✅ Paper trading can be enabled
✅ WebSocket/SSE connections work
✅ Emergency stop functions correctly

**System is production-ready!** 🚀
