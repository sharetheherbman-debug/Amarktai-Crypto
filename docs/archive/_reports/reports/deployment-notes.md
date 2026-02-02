# Deployment Notes

**Date:** December 28, 2025  
**Target Environment:** Ubuntu 24.04 LTS  
**Status:** ✅ Production Ready

## Executive Summary

Amarktai Network backend is now fully deployable on Ubuntu 24.04 with automated scripts. All dependency conflicts resolved, code hardened for safe restarts, and feature flags added for gradual enablement.

## Deployment Scripts

### Overview

Four scripts in `/tools/` directory:
1. **backend_setup.sh** - Sets up Python environment and dependencies
2. **frontend_setup.sh** - Builds frontend with Node.js 20
3. **systemd_install.sh** - Installs and configures systemd service
4. **health_check.sh** - Verifies deployment health

### Usage

```bash
# 1. Clone repository
git clone <repo-url> /var/amarktai/app
cd /var/amarktai/app

# 2. Setup backend
sudo bash tools/backend_setup.sh

# 3. Configure environment
sudo nano /var/amarktai/app/backend/.env
# Set: JWT_SECRET, MONGO_URL, OPENAI_API_KEY

# 4. Setup frontend (optional)
sudo bash tools/frontend_setup.sh

# 5. Install systemd service
sudo bash tools/systemd_install.sh

# 6. Verify deployment
bash tools/health_check.sh
```

## Directory Structure

```
/var/amarktai/
├── app/
│   ├── backend/           # Backend source code
│   │   ├── .env          # Configuration (not in git)
│   │   ├── requirements.txt
│   │   ├── requirements-ai.txt (optional)
│   │   └── server.py
│   └── frontend/
│       └── build/        # Production build
├── venv/                 # Python virtual environment
└── logs/                 # Application logs
```

## Environment Configuration

### Required Variables

```bash
# Security (REQUIRED)
JWT_SECRET=<generate with: openssl rand -hex 32>
ADMIN_PASSWORD=<generate with: openssl rand -base64 24>

# Database (REQUIRED)
MONGO_URL=mongodb://127.0.0.1:27017
DB_NAME=amarktai_trading

# AI (REQUIRED for functionality)
OPENAI_API_KEY=<your-openai-api-key>
```

### Feature Flags (Safe Defaults)

```bash
# Trading disabled by default (safe)
ENABLE_TRADING=false
ENABLE_AUTOPILOT=false
ENABLE_CCXT=true          # Safe for price data
ENABLE_UAGENTS=false      # Requires requirements-ai.txt
PAYMENT_AGENT_ENABLED=false
```

### Gradual Enablement Path

1. **Day 1:** Deploy with all flags false
   - Verify health checks pass
   - Test dashboard loads
   - Price data works (ENABLE_CCXT=true)

2. **Day 2-7:** Enable paper trading
   - Set ENABLE_TRADING=true
   - Test paper trades
   - Monitor logs for errors

3. **Day 7+:** Enable autopilot
   - Set ENABLE_AUTOPILOT=true
   - Monitor autonomous actions
   - Review reinvestment logic

4. **After validation:** Enable live trading
   - Configure exchange API keys
   - Enable per-bot live trading (7-day paper requirement)
   - Start with small capital

## MongoDB Setup

### Docker Method (Recommended)

```bash
# Install Docker
sudo apt-get install docker.io

# Run MongoDB container
sudo docker run -d \
  --name amarktai-mongo \
  -p 127.0.0.1:27017:27017 \
  -v /var/amarktai/mongodb:/data/db \
  --restart always \
  mongo:7

# Verify
sudo docker ps | grep amarktai-mongo
```

### Native Installation

```bash
# Install MongoDB 7
sudo apt-get install gnupg curl
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg \
  --dearmor
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org

# Start MongoDB
sudo systemctl start mongod
sudo systemctl enable mongod
```

## Nginx Configuration

### Reverse Proxy Setup

```nginx
# /etc/nginx/sites-available/amarktai
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        root /var/amarktai/app/frontend/build;
        try_files $uri /index.html;
    }

    # API Proxy
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # WebSocket Support
    location /api/ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## SSL/TLS (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal (already configured by certbot)
sudo systemctl status certbot.timer
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u amarktai-api -n 50

# Common issues:
# 1. .env file missing or misconfigured
# 2. MongoDB not running
# 3. Port 8000 already in use
```

### Dependencies Failed to Install

```bash
# Check Python version
python3.12 --version

# Reinstall dependencies
cd /var/amarktai/app/backend
source /var/amarktai/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Frontend Build Failed

```bash
# Check Node version
node --version  # Should be v20.x

# Rebuild
cd /var/amarktai/app/frontend
rm -rf node_modules
npm install
npm run build
```

### MongoDB Connection Error

```bash
# Check MongoDB is running
sudo systemctl status mongod
# OR for Docker:
sudo docker ps | grep amarktai-mongo

# Test connection
mongosh --eval "db.adminCommand('ping')"
```

## Monitoring

### Service Status

```bash
# Check service
sudo systemctl status amarktai-api

# View live logs
sudo journalctl -u amarktai-api -f

# Check resource usage
sudo systemctl status amarktai-api | grep Memory
```

### Health Checks

```bash
# Automated health check
bash /var/amarktai/app/tools/health_check.sh

# Manual checks
curl http://127.0.0.1:8000/api/health/ping
curl http://127.0.0.1:8000/openapi.json | jq '.paths | keys[]'
```

## Backup Strategy

### Database Backups

```bash
# Create backup script
cat > /var/amarktai/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/amarktai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
mongodump --out $BACKUP_DIR/mongo_$DATE
find $BACKUP_DIR -type d -mtime +7 -exec rm -rf {} \;
EOF

chmod +x /var/amarktai/backup_db.sh

# Add to crontab (daily at 2 AM)
echo "0 2 * * * /var/amarktai/backup_db.sh" | sudo crontab -
```

### Code Backups

```bash
# Git-based deployment allows easy rollback
cd /var/amarktai/app
git log --oneline -10  # View recent commits
git checkout <commit-hash>  # Rollback if needed
sudo systemctl restart amarktai-api
```

## Update Procedure

```bash
# 1. Pull latest code
cd /var/amarktai/app
git pull

# 2. Update backend dependencies (if changed)
source /var/amarktai/venv/bin/activate
pip install -r backend/requirements.txt

# 3. Rebuild frontend (if changed)
cd frontend
npm install
npm run build

# 4. Restart service
sudo systemctl restart amarktai-api

# 5. Verify
bash tools/health_check.sh
```

## Security Hardening

### Firewall (UFW)

```bash
# Enable firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# MongoDB should only listen on localhost (default)
```

### File Permissions

```bash
# Ensure proper ownership
sudo chown -R $USER:$USER /var/amarktai/app
sudo chmod 600 /var/amarktai/app/backend/.env
```

### Systemd Security

The systemd service includes security hardening:
- `NoNewPrivileges=true` - Prevent privilege escalation
- `PrivateTmp=true` - Isolated /tmp
- `ProtectSystem=strict` - Read-only system directories
- `ReadWritePaths` - Limited write access

## Performance Tuning

### Uvicorn Workers

For production with multiple CPU cores:

```bash
# Edit systemd service
sudo nano /etc/systemd/system/amarktai-api.service

# Change ExecStart to:
ExecStart=/var/amarktai/venv/bin/uvicorn server:app \
  --host 127.0.0.1 --port 8000 \
  --workers 4 \
  --log-level info

sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

### MongoDB Optimization

```javascript
// Connect to MongoDB
mongosh

// Create indexes
use amarktai_trading
db.bots.createIndex({ user_id: 1, status: 1 })
db.trades.createIndex({ bot_id: 1, timestamp: -1 })
db.users.createIndex({ email: 1 }, { unique: true })
```

## Known Limitations

1. **Single-server deployment:** Not yet configured for multi-server/cluster
2. **No load balancer:** Direct nginx → uvicorn (single instance)
3. **Logs rotation:** Need to configure logrotate for journal logs
4. **No monitoring dashboard:** Consider adding Grafana + Prometheus

## Future Improvements

1. **Docker Compose:** Full stack in containers
2. **Kubernetes:** For large-scale deployments
3. **CI/CD Pipeline:** Automated testing and deployment
4. **Health monitoring:** Prometheus + Grafana
5. **Log aggregation:** ELK stack or similar

## Conclusion

Deployment is production-ready for single-server installations on Ubuntu 24.04. All scripts are tested and idempotent. Feature flags allow safe gradual enablement. Follow the update procedure for ongoing maintenance.

**Support:**
- Check health: `bash tools/health_check.sh`
- View logs: `sudo journalctl -u amarktai-api -f`
- Restart: `sudo systemctl restart amarktai-api`
