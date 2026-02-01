# Webdock VPS Deployment Guide - Plug & Play Ready

## Pre-Deployment Checklist ✅

### System Requirements
- [ ] Ubuntu 20.04/22.04 LTS or Debian 11/12
- [ ] Minimum 4GB RAM (8GB recommended)
- [ ] 40GB storage minimum
- [ ] Python 3.10+ installed
- [ ] Node.js 18+ and npm installed
- [ ] MongoDB 6.0+ running
- [ ] nginx or Apache for reverse proxy
- [ ] SSL certificate (Let's Encrypt recommended)

### Required API Keys & Secrets
- [ ] `OPENAI_API_KEY` - OpenAI API key for AI features
- [ ] `JWT_SECRET` - Strong JWT secret (32+ characters)
- [ ] `FLOCK_API_KEY` - FLock.io API key for trading specialist
- [ ] `FETCH_WALLET_SEED` - 24-word Fetch wallet mnemonic (if using Payment Agent)
- [ ] `SMTP_*` credentials - Email configuration (optional)
- [ ] Exchange API keys (stored per user in database)

---

## Step 1: Server Preparation

### 1.1 Update System
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx mongodb python3-pip python3-venv nodejs npm
```

### 1.2 Create Application User
```bash
sudo useradd -m -s /bin/bash amarktai
sudo usermod -aG sudo amarktai
```

### 1.3 Clone Repository
```bash
cd /home/amarktai
sudo -u amarktai git clone https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment
```

---

## Step 2: Backend Setup

### 2.1 Create Python Virtual Environment
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

### 2.2 Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.3 Configure Environment
```bash
cp ../.env.example ../.env
nano ../.env
```

**CRITICAL - Edit these values:**
```env
# Database
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB_NAME=amarktai

# Security
JWT_SECRET=YOUR_STRONG_SECRET_HERE_32_CHARS_MIN
ADMIN_PASSWORD=YOUR_SECURE_ADMIN_PASSWORD

# AI Services
OPENAI_API_KEY=sk-your-openai-key-here

# FLock.io (Advanced Trading)
FLOCK_API_KEY=your-flock-api-key-here
FLOCK_ENABLED=true

# Payment Agent (Optional)
PAYMENT_AGENT_ENABLED=false
FETCH_WALLET_SEED=  # Only if using Payment Agent
FETCH_NETWORK=testnet

# Email (Optional)
SMTP_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
FROM_EMAIL=your-email@gmail.com

# Production Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
HOST=127.0.0.1
PORT=8000
```

### 2.4 Generate Secrets
```bash
# Generate JWT secret
openssl rand -hex 32

# Generate Fetch wallet (if using Payment Agent)
python3 << EOF
from cosmpy.aerial.wallet import LocalWallet
wallet = LocalWallet.generate()
print(f"Mnemonic: {wallet.mnemonic()}")
print(f"Address: {wallet.address()}")
EOF
```

### 2.5 Initialize Database
```bash
# Start MongoDB
sudo systemctl start mongodb
sudo systemctl enable mongodb

# Create database and indexes (run from backend directory)
python3 << EOF
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def init_db():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.amarktai
    
    # Create collections and indexes
    await db.users.create_index('email', unique=True)
    await db.bots.create_index([('user_id', 1), ('bot_id', 1)])
    await db.trades.create_index([('bot_id', 1), ('timestamp', -1)])
    
    print("Database initialized successfully")

asyncio.run(init_db())
EOF
```

---

## Step 3: Frontend Setup

### 3.1 Install Frontend Dependencies
```bash
cd ../frontend
npm install
```

### 3.2 Configure Frontend Environment
```bash
cat > .env << EOF
REACT_APP_API_BASE=https://your-domain.com
REACT_APP_WS_URL=wss://your-domain.com
EOF
```

### 3.3 Build Frontend
```bash
npm run build
```

---

## Step 4: Systemd Service Setup

### 4.1 Create Backend Service
```bash
sudo nano /etc/systemd/system/amarktai-backend.service
```

```ini
[Unit]
Description=Amarktai Network Backend
After=network.target mongodb.service

[Service]
Type=simple
User=amarktai
WorkingDirectory=/home/amarktai/Amarktai-Network---Deployment/backend
Environment="PATH=/home/amarktai/Amarktai-Network---Deployment/backend/venv/bin"
ExecStart=/home/amarktai/Amarktai-Network---Deployment/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4.2 Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable amarktai-backend
sudo systemctl start amarktai-backend
sudo systemctl status amarktai-backend
```

---

## Step 5: Nginx Configuration

### 5.1 Create Nginx Config
```bash
sudo nano /etc/nginx/sites-available/amarktai
```

```nginx
# Amarktai Network - Nginx Configuration

# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=ws_limit:10m rate=5r/s;

# Upstream backend
upstream amarktai_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;
    
    # SSL Configuration (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Frontend (React Build)
    root /home/amarktai/Amarktai-Network---Deployment/frontend/build;
    index index.html;
    
    # Frontend Routes
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API Routes
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        
        proxy_pass http://amarktai_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # WebSocket Routes
    location ~ ^/(ws|api/ws)/ {
        limit_req zone=ws_limit burst=10 nodelay;
        
        proxy_pass http://amarktai_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket timeouts
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
    
    # Prometheus Metrics (Optional - restrict access)
    location /api/metrics {
        # Uncomment to restrict to specific IPs
        # allow 127.0.0.1;
        # deny all;
        
        proxy_pass http://amarktai_backend;
        proxy_set_header Host $host;
    }
    
    # Static Assets Caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
}
```

### 5.2 Enable Site and Restart Nginx
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Step 6: SSL Certificate (Let's Encrypt)

### 6.1 Install Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 6.2 Obtain Certificate
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

### 6.3 Auto-Renewal
```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Step 7: Firewall Configuration

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

---

## Step 8: Monitoring Setup (Optional)

### 8.1 Prometheus Installation
```bash
# Download and install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*
sudo mv prometheus promtool /usr/local/bin/
sudo mv prometheus.yml /etc/prometheus/

# Create service
sudo nano /etc/systemd/system/prometheus.service
```

```ini
[Unit]
Description=Prometheus
After=network.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.path=/var/lib/prometheus/ \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries

[Install]
WantedBy=multi-user.target
```

### 8.2 Configure Prometheus
```bash
sudo nano /etc/prometheus/prometheus.yml
```

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'amarktai'
    static_configs:
      - targets: ['127.0.0.1:8000']
    metrics_path: '/api/metrics'
```

---

## Step 9: Post-Deployment Verification

### 9.1 Check Services
```bash
sudo systemctl status amarktai-backend
sudo systemctl status mongodb
sudo systemctl status nginx
```

### 9.2 Check Logs
```bash
# Backend logs
sudo journalctl -u amarktai-backend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 9.3 Test Endpoints
```bash
# Health check
curl https://your-domain.com/api/health

# Payment agent status (if enabled)
curl https://your-domain.com/api/payment/status

# Prometheus metrics
curl https://your-domain.com/api/metrics
```

### 9.4 Frontend Verification
- Navigate to `https://your-domain.com`
- Register a new user account
- Create a trading bot
- Navigate to 🎬 Decision Trace
- Navigate to 🐋 Whale Flow
- Navigate to 📊 Metrics

---

## Step 10: Backup Configuration

### 10.1 Database Backup Script
```bash
sudo nano /home/amarktai/backup-mongodb.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/amarktai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
mongodump --db amarktai --out $BACKUP_DIR/mongodb_$DATE
tar -czf $BACKUP_DIR/mongodb_$DATE.tar.gz -C $BACKUP_DIR mongodb_$DATE
rm -rf $BACKUP_DIR/mongodb_$DATE
find $BACKUP_DIR -name "mongodb_*.tar.gz" -mtime +7 -delete
```

```bash
chmod +x /home/amarktai/backup-mongodb.sh
```

### 10.2 Add to Crontab
```bash
crontab -e
```

```
0 2 * * * /home/amarktai/backup-mongodb.sh
```

---

## Step 11: Security Hardening

### 11.1 Secure MongoDB
```bash
sudo nano /etc/mongodb/mongod.conf
```

```yaml
security:
  authorization: enabled

net:
  bindIp: 127.0.0.1
```

```bash
# Create admin user
mongosh
use admin
db.createUser({
  user: "admin",
  pwd: "STRONG_PASSWORD_HERE",
  roles: ["userAdminAnyDatabase", "dbAdminAnyDatabase", "readWriteAnyDatabase"]
})
```

### 11.2 Secure .env File
```bash
chmod 600 /home/amarktai/Amarktai-Network---Deployment/.env
chown amarktai:amarktai /home/amarktai/Amarktai-Network---Deployment/.env
```

### 11.3 Enable Fail2Ban (SSH Protection)
```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## Step 12: Final Checklist

### Security
- [ ] JWT_SECRET is strong and unique
- [ ] Admin password is strong
- [ ] MongoDB has authentication enabled
- [ ] .env file has restrictive permissions (600)
- [ ] SSL certificate is installed and auto-renewing
- [ ] Firewall is configured (only 22, 80, 443 open)
- [ ] Fail2Ban is running
- [ ] No secrets in git repository

### Services
- [ ] Backend service is running
- [ ] MongoDB service is running
- [ ] Nginx service is running
- [ ] Prometheus service is running (if enabled)
- [ ] All services set to auto-start on boot

### Functionality
- [ ] Frontend loads at https://your-domain.com
- [ ] User registration works
- [ ] Login works
- [ ] Bot creation works
- [ ] API endpoints respond correctly
- [ ] WebSocket connections work
- [ ] Decision Trace component loads
- [ ] Whale Flow Heatmap loads
- [ ] Prometheus Metrics dashboard loads
- [ ] Email alerts work (if configured)
- [ ] Payment Agent works (if enabled)

### Monitoring
- [ ] Prometheus scraping metrics
- [ ] Logs are being written
- [ ] Backup script runs nightly
- [ ] SSL certificate auto-renewal configured

---

## Troubleshooting

### Backend won't start
```bash
sudo journalctl -u amarktai-backend -n 100
# Check for missing dependencies or config errors
```

### Can't connect to MongoDB
```bash
sudo systemctl status mongodb
# Check /var/log/mongodb/mongod.log
```

### Frontend shows connection error
```bash
# Check nginx config
sudo nginx -t
# Check backend is running
curl http://127.0.0.1:8000/api/health
```

### Payment Agent not working
```bash
# Check PAYMENT_AGENT_ENABLED=true in .env
# Check FETCH_WALLET_SEED is set
# Check cosmpy is installed: pip list | grep cosmpy
```

---

## Maintenance

### Update Application
```bash
cd /home/amarktai/Amarktai-Network---Deployment
git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
sudo systemctl restart amarktai-backend
```

### View Logs
```bash
# Real-time backend logs
sudo journalctl -u amarktai-backend -f

# Last 100 lines
sudo journalctl -u amarktai-backend -n 100

# Nginx access logs
sudo tail -f /var/log/nginx/access.log
```

### Restart Services
```bash
sudo systemctl restart amarktai-backend
sudo systemctl restart nginx
sudo systemctl restart mongodb
```

---

## Support

- Documentation: `/home/amarktai/Amarktai-Network---Deployment/ADVANCED_TRADING_SYSTEM.md`
- GitHub: https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment
- Logs: `sudo journalctl -u amarktai-backend`

---

**Deployment Complete! 🚀**

Your Amarktai Network trading platform is now live and ready for use.
