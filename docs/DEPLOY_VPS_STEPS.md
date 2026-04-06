# VPS Deployment Steps - Amarktai Network

**Last Updated:** 2026-01-13  
**Purpose:** Step-by-step guide for deploying backend + frontend to production VPS

---

## Prerequisites

- Ubuntu 20.04+ VPS with root access
- Domain name pointing to VPS IP
- At least 2GB RAM, 2 CPU cores
- MongoDB installed or accessible
- SSL certificate (Let's Encrypt recommended)

---

## Step 1: Server Preparation

### Update System
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx python3-pip python3-venv nodejs npm mongodb-server
```

### Create Application User
```bash
sudo useradd -m -s /bin/bash amarktai
sudo usermod -aG sudo amarktai
su - amarktai
```

---

## Step 2: Clone Repository

```bash
cd /home/amarktai
git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git
cd Amarktai-Crypto
```

---

## Step 3: Backend Deployment

### 3.1 Create Python Virtual Environment
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

### 3.2 Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.3 Create Environment File
```bash
cat > .env << 'EOF'
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=CHANGE_THIS_TO_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS
ADMIN_PASSWORD=CHANGE_THIS_TO_STRONG_PASSWORD

# Feature Flags (Safe defaults for initial deployment)
ENABLE_REALTIME=true
ENABLE_TRADING=0
ENABLE_AUTOPILOT=0
ENABLE_CCXT=0
ENABLE_SCHEDULERS=0

# Optional API Keys (can be set per-user in dashboard)
OPENAI_API_KEY=
FETCHAI_API_KEY=
COINSTATS_API_KEY=
EOF
```

### 3.4 Generate Strong Secrets
```bash
# Generate JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy output and paste into .env as JWT_SECRET

# Generate admin password
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
# Copy output and paste into .env as ADMIN_PASSWORD
```

### 3.5 Test Backend Startup
```bash
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
# Press Ctrl+C after verifying it starts without errors
```

### 3.6 Create Systemd Service
```bash
sudo tee /etc/systemd/system/amarktai-backend.service > /dev/null << 'EOF'
[Unit]
Description=Amarktai Network Backend
After=network.target mongodb.service

[Service]
Type=notify
User=amarktai
Group=amarktai
WorkingDirectory=/home/amarktai/Amarktai-Crypto/backend
Environment="PATH=/home/amarktai/Amarktai-Crypto/backend/venv/bin"
EnvironmentFile=/home/amarktai/Amarktai-Crypto/backend/.env
ExecStart=/home/amarktai/Amarktai-Crypto/backend/venv/bin/gunicorn server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --timeout 120 \
  --access-logfile /home/amarktai/logs/access.log \
  --error-logfile /home/amarktai/logs/error.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 3.7 Create Log Directory
```bash
mkdir -p /home/amarktai/logs
```

### 3.8 Install Gunicorn
```bash
source venv/bin/activate
pip install gunicorn
```

### 3.9 Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable amarktai-backend
sudo systemctl start amarktai-backend
sudo systemctl status amarktai-backend
```

---

## Step 4: Frontend Build

### 4.1 Install Dependencies
```bash
cd /home/amarktai/Amarktai-Crypto/frontend
npm install
```

### 4.2 Build for Production
```bash
npm run build
```

### 4.3 Verify Build
```bash
ls -la build/
# Should see index.html, static/, etc.
```

---

## Step 5: Nginx Configuration

### 5.1 Create Nginx Site Config
```bash
sudo tee /etc/nginx/sites-available/amarktai << 'EOF'
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Redirect to HTTPS (add after SSL cert is obtained)
    # return 301 https://$server_name$request_uri;
    
    # Frontend (React build)
    root /home/amarktai/Amarktai-Crypto/frontend/build;
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
        proxy_buffering off;
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
    gzip_min_length 1000;
}
EOF
```

### 5.2 Enable Site
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
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

### 6.3 Auto-renewal Test
```bash
sudo certbot renew --dry-run
```

---

## Step 7: Database Setup

### 7.1 Secure MongoDB
```bash
sudo systemctl start mongodb
sudo systemctl enable mongodb

# Create admin user
mongosh
```

```javascript
use admin
db.createUser({
  user: "admin",
  pwd: "STRONG_PASSWORD_HERE",
  roles: ["userAdminAnyDatabase", "dbAdminAnyDatabase", "readWriteAnyDatabase"]
})

use amarktai_trading
// Database will be created automatically by the application
```

### 7.2 Create First Admin User
```javascript
use amarktai_trading

db.users.insertOne({
  id: "admin-" + new Date().getTime(),
  email: "admin@yourdomain.com",
  password_hash: "$2b$12$HASH_HERE",  // Will be set after first login
  first_name: "Admin",
  last_name: "User",
  is_admin: true,
  role: "admin",
  created_at: new Date().toISOString()
})
```

---

## Step 8: Verification & Testing

### 8.1 Health Checks
```bash
# Test backend directly
curl http://localhost:8000/api/health/ping

# Test through nginx
curl http://your-domain.com/api/health/ping

# Test frontend
curl http://your-domain.com/
```

### 8.2 Smoke Test Script
Create `/home/amarktai/smoke-test.sh`:

```bash
#!/bin/bash
echo "🔍 Amarktai Network Smoke Test"
echo "================================"

# Test 1: Health endpoint
echo "1. Testing health endpoint..."
HEALTH=$(curl -s http://localhost:8000/api/health/ping)
if echo "$HEALTH" | grep -q "status"; then
    echo "   ✅ Health check passed"
else
    echo "   ❌ Health check failed"
fi

# Test 2: Login endpoint
echo "2. Testing login endpoint..."
LOGIN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}')
if echo "$LOGIN" | grep -q "token\|Invalid"; then
    echo "   ✅ Login endpoint responding"
else
    echo "   ❌ Login endpoint not responding"
fi

# Test 3: Frontend
echo "3. Testing frontend..."
FRONTEND=$(curl -s http://localhost:80/ | head -c 100)
if echo "$FRONTEND" | grep -q "html\|DOCTYPE"; then
    echo "   ✅ Frontend serving"
else
    echo "   ❌ Frontend not serving"
fi

# Test 4: SSE endpoint
echo "4. Testing SSE endpoint..."
timeout 3 curl -s http://localhost:8000/api/realtime/events > /dev/null 2>&1
if [ $? -eq 124 ]; then
    echo "   ✅ SSE endpoint streaming (timed out after 3s, expected)"
else
    echo "   ⚠️ SSE endpoint may not be working"
fi

echo "================================"
echo "✅ Smoke test complete"
```

Make executable and run:
```bash
chmod +x /home/amarktai/smoke-test.sh
./smoke-test.sh
```

---

## Step 9: Monitoring & Logs

### 9.1 View Backend Logs
```bash
# System logs
sudo journalctl -u amarktai-backend -f

# Application logs
tail -f /home/amarktai/logs/error.log
tail -f /home/amarktai/logs/access.log
```

### 9.2 View Nginx Logs
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 9.3 Check Service Status
```bash
sudo systemctl status amarktai-backend
sudo systemctl status nginx
sudo systemctl status mongodb
```

---

## Step 10: Post-Deployment Tasks

### 10.1 Create Admin User in Dashboard
1. Visit https://your-domain.com
2. Register with admin email
3. Manually set admin flag in MongoDB:
   ```bash
   mongosh amarktai_trading
   db.users.updateOne(
     {email: "admin@yourdomain.com"},
     {$set: {is_admin: true, role: "admin"}}
   )
   ```

### 10.2 Test All Features
- [ ] Login works
- [ ] Dashboard loads without errors
- [ ] API Setup section shows all keys
- [ ] Metrics submenu expands (4 items)
- [ ] Platform comparison shows exchanges
- [ ] Profit graphs display
- [ ] Admin panel accessible (admin only)
- [ ] Real-time updates work

### 10.3 Configure API Keys
In dashboard, go to API Setup and add:
- OpenAI API key (required for AI features)
- Exchange keys (Luno, Binance, KuCoin as needed)
- Flokx key (optional)
- FetchAI key (optional)

---

## Step 11: Maintenance

### 11.1 Update Application
```bash
cd /home/amarktai/Amarktai-Crypto
git pull origin main

# Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart amarktai-backend

# Frontend
cd ../frontend
npm install
npm run build
sudo systemctl reload nginx
```

### 11.2 Database Backup
Create `/home/amarktai/backup.sh`:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mongodump --db amarktai_trading --out /home/amarktai/backups/mongo_$DATE
find /home/amarktai/backups -mtime +7 -delete
```

Add to crontab:
```bash
crontab -e
# Add line:
0 2 * * * /home/amarktai/backup.sh
```

### 11.3 Log Rotation
```bash
sudo tee /etc/logrotate.d/amarktai << 'EOF'
/home/amarktai/logs/*.log {
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
EOF
```

---

## Troubleshooting

### Backend Won't Start
```bash
# Check logs
sudo journalctl -u amarktai-backend -n 50

# Check if port is in use
sudo netstat -tulpn | grep 8000

# Check permissions
ls -la /home/amarktai/Amarktai-Crypto/backend/.env

# Test manually
cd /home/amarktai/Amarktai-Crypto/backend
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

### Frontend Not Loading
```bash
# Check nginx config
sudo nginx -t

# Check build exists
ls -la /home/amarktai/Amarktai-Crypto/frontend/build/

# Check permissions
sudo chown -R amarktai:amarktai /home/amarktai/Amarktai-Crypto
```

### Database Connection Issues
```bash
# Check MongoDB status
sudo systemctl status mongodb

# Test connection
mongosh amarktai_trading --eval "db.users.countDocuments()"

# Check MongoDB logs
sudo journalctl -u mongodb -n 50
```

### 404 Errors on API Calls
```bash
# Check backend is running
curl http://localhost:8000/api/health/ping

# Check nginx proxy
sudo tail -f /var/log/nginx/error.log

# Check backend logs
sudo journalctl -u amarktai-backend -f
```

---

## Security Checklist

- [ ] Changed JWT_SECRET to strong random value
- [ ] Changed ADMIN_PASSWORD to strong password
- [ ] MongoDB authentication enabled
- [ ] Firewall configured (ufw allow 80,443)
- [ ] SSH key-based auth only
- [ ] Regular security updates scheduled
- [ ] Backups automated and tested
- [ ] SSL certificate auto-renewal working
- [ ] API keys stored encrypted
- [ ] Admin users properly flagged in database

---

## Performance Optimization

### Backend
```bash
# Increase workers based on CPU
# Edit /etc/systemd/system/amarktai-backend.service
# Change --workers 4 to --workers $((2 * CPU_CORES + 1))
```

### Database
```javascript
// Create indexes
use amarktai_trading
db.users.createIndex({email: 1}, {unique: true})
db.users.createIndex({id: 1})
db.bots.createIndex({user_id: 1})
db.trades.createIndex({user_id: 1, timestamp: -1})
db.decisions.createIndex({user_id: 1, timestamp: -1})
```

### Nginx
```nginx
# Add to http block in /etc/nginx/nginx.conf
client_max_body_size 10M;
keepalive_timeout 65;
worker_processes auto;
```

---

## Support

- Documentation: `/home/amarktai/Amarktai-Crypto/docs/`
- Gap Report: `docs/reports/FINAL_GO_LIVE_GAP_REPORT.md`
- Backend logs: `/home/amarktai/logs/`
- System logs: `sudo journalctl -u amarktai-backend`

---

**Deployment Complete** ✅  
**Dashboard Ready for Production** 🚀
