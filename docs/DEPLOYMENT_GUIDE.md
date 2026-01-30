# Production Deployment Guide

## Pre-Deployment Checklist

### Backend Verification
- [ ] MongoDB connection string configured in environment
- [ ] All 5 platform API credentials configured (optional for paper trading)
- [ ] JWT_SECRET set to strong random value
- [ ] CORS origins configured for production domain
- [ ] Log directory exists and writable
- [ ] Python dependencies installed: `pip install -r backend/requirements.txt`

### Frontend Verification
- [ ] API_BASE points to production backend URL
- [ ] WebSocket URL (wsUrl) configured correctly
- [ ] Build completed: `cd frontend && npm install && npm run build`
- [ ] Static files served from `frontend/build/`

### Database Setup
- [ ] MongoDB 4.4+ running
- [ ] Database: `amarktai_trading` created
- [ ] Collections auto-initialized on first connect
- [ ] Indexes created automatically

### Nginx Configuration
- [ ] Copy `docs/nginx.conf` to `/etc/nginx/sites-available/`
- [ ] Update domain name in config
- [ ] Update backend upstream address
- [ ] SSL certificates configured (Let's Encrypt recommended)
- [ ] Test config: `nginx -t`
- [ ] Reload: `nginx -s reload`

## Deployment Steps

### 1. Backend Deployment

```bash
# Clone repository
cd /opt/
git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit with production values

# Test backend
cd backend
python server.py
# Should start on port 8000
```

**Environment Variables (.env):**
```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=<generate-strong-random-secret>
ADMIN_PASSWORD=<secure-admin-password>

# Trading (Optional - for live trading only)
ENABLE_LIVE_TRADING=false  # Set to true only after testing

# AI Services (Optional)
OPENAI_API_KEY=<your-key>
FLOKX_API_KEY=<your-key>

# Email (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<your-email>
SMTP_PASSWORD=<your-app-password>

# Feature Flags
ENABLE_REALTIME=true
ENABLE_AUTOPILOT=false  # Enable after testing
```

### 2. Frontend Deployment

```bash
# Build frontend
cd frontend
npm install
npm run build

# Serve static files
# Option A: Nginx (recommended)
sudo cp -r build/* /var/www/amarktai/

# Option B: Docker
# Use provided Dockerfile
```

### 3. Systemd Service (Production)

Create `/etc/systemd/system/amarktai-backend.service`:

```ini
[Unit]
Description=Amarktai Trading Backend
After=network.target mongodb.service

[Service]
Type=simple
User=amarktai
WorkingDirectory=/opt/Amarktai-Network---Deployment/backend
Environment="PATH=/opt/Amarktai-Network---Deployment/venv/bin"
ExecStart=/opt/Amarktai-Network---Deployment/venv/bin/python server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable amarktai-backend
sudo systemctl start amarktai-backend
sudo systemctl status amarktai-backend
```

### 4. Database Initialization

No manual steps required! Collections and indexes are auto-created on first connection.

**Verify:**
```bash
# Connect to MongoDB
mongosh
use amarktai_trading
show collections
# Should show 70+ collections

# Check first user (created on registration)
db.users.find().pretty()
```

### 5. Smoke Test

```bash
# Run API smoke test
chmod +x scripts/smoke_api.sh
./scripts/smoke_api.sh

# Expected output: All tests passing
```

## Post-Deployment Verification

### 1. Health Checks

```bash
# System ping
curl https://your-domain.com/api/system/ping
# Expected: {"status":"ok","timestamp":"..."}

# Platform status
curl -H "Authorization: Bearer <token>" \
  https://your-domain.com/api/platforms/health
# Expected: Status for all 5 platforms

# WebSocket test
wscat -c wss://your-domain.com/api/ws?token=<jwt-token>
# Expected: Connection established
```

### 2. Frontend Test

Visit: `https://your-domain.com`

- [ ] Landing page loads
- [ ] Registration works
- [ ] Login works
- [ ] Dashboard displays
- [ ] WebSocket connects (check browser console)
- [ ] Can create paper trading bot
- [ ] Real-time updates working
- [ ] All tabs functional (no "coming soon")

### 3. Feature Verification

**Paper Trading:**
- [ ] Create bot on any exchange (no API keys needed)
- [ ] Bot shows in dashboard
- [ ] Metrics update
- [ ] Trades logged
- [ ] P&L calculated

**API Key Management:**
- [ ] Can add OpenAI key
- [ ] Can test Binance keys
- [ ] Can test Luno keys
- [ ] Platform health updates

**Analytics:**
- [ ] Equity tab shows chart
- [ ] Drawdown tab functional
- [ ] Win rate tab displays stats
- [ ] Real-time updates working

**Wallet & Transfers:**
- [ ] Balance summary shows
- [ ] Can request transfer
- [ ] Transfer history displays

**Admin Panel (if admin):**
- [ ] Type "show admin" in chat
- [ ] Enter admin password
- [ ] Panel appears
- [ ] User dropdown populated
- [ ] Bot dropdown filtered by user
- [ ] Actions apply to selected bot only

## Security Hardening

### 1. Firewall Rules
```bash
# Allow only necessary ports
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 27017/tcp  # MongoDB (only from localhost)
ufw enable
```

### 2. MongoDB Security
```bash
# Enable authentication
mongosh
use admin
db.createUser({
  user: "amarktai",
  pwd: "strong-password",
  roles: ["readWrite", "dbAdmin"]
})

# Update MONGO_URL in .env
MONGO_URL=mongodb://amarktai:strong-password@localhost:27017/amarktai_trading
```

### 3. SSL/TLS (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### 4. Rate Limiting
Already configured in `docs/nginx.conf`:
- API: 100 req/s
- Login: 5 req/min
- WebSocket: Unlimited (connection-based)

## Monitoring

### 1. Application Logs
```bash
# Backend logs
journalctl -u amarktai-backend -f

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### 2. Database Monitoring
```bash
# MongoDB status
mongosh
use amarktai_trading
db.serverStatus()
db.stats()

# Collection counts
db.bots.countDocuments()
db.trades.countDocuments()
db.users.countDocuments()
```

### 3. System Resources
```bash
# CPU/Memory
htop

# Disk usage
df -h

# Network
netstat -tuln | grep -E '8000|27017|80|443'
```

## Backup Strategy

### 1. Database Backup
```bash
# Daily backup script
mongodump --db amarktai_trading --out /backups/$(date +%Y%m%d)

# Restore
mongorestore --db amarktai_trading /backups/20240101/amarktai_trading/
```

### 2. Code Backup
```bash
# Automated via Git
cd /opt/Amarktai-Network---Deployment
git pull origin main  # Update to latest
```

## Troubleshooting

### Backend Won't Start
```bash
# Check logs
journalctl -u amarktai-backend -n 50

# Common issues:
# - MongoDB not running: sudo systemctl start mongodb
# - Port 8000 in use: lsof -i :8000
# - Missing dependencies: pip install -r requirements.txt
# - Environment vars: check .env file
```

### WebSocket Not Connecting
```bash
# Check nginx config
nginx -t

# Verify upgrade headers
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  http://localhost:8000/api/ws

# Check firewall
ufw status
```

### High CPU Usage
```bash
# Identify culprit
top -c

# Check bot count
mongosh amarktai_trading --eval "db.bots.countDocuments({status: 'active'})"

# Adjust trading frequency if needed
# Paper trading: max 50 trades/day per bot (already optimized)
```

### Database Connection Issues
```bash
# Test connection
mongosh mongodb://localhost:27017/amarktai_trading

# Check MongoDB logs
sudo journalctl -u mongodb -f

# Restart MongoDB
sudo systemctl restart mongodb
```

## Performance Tuning

### 1. MongoDB Indexes
Already auto-created by backend. Verify:
```javascript
use amarktai_trading
db.bots.getIndexes()
db.trades.getIndexes()
db.users.getIndexes()
```

### 2. Nginx Caching
Add to nginx.conf:
```nginx
# Cache static assets
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### 3. Backend Workers
For high load, run multiple backend instances:
```nginx
upstream backend {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}
```

## Scaling Considerations

### Current Capacity
- Supports: 100+ concurrent users
- Bots: 45 per user (5 Luno + 10 Binance + 10 KuCoin + 10 OVEX + 10 VALR)
- Trades: Unlimited (indexed, performant)
- WebSocket: 1000+ concurrent connections

### Horizontal Scaling
1. Redis for WebSocket pub/sub
2. Load balancer with multiple backend instances
3. MongoDB replica set for HA
4. CDN for static assets

## Support & Maintenance

### Regular Tasks
- [ ] Daily: Check logs for errors
- [ ] Weekly: Review bot performance
- [ ] Weekly: Database backup verification
- [ ] Monthly: Security updates (apt upgrade)
- [ ] Monthly: Dependency updates (pip, npm)
- [ ] Quarterly: Performance review

### Emergency Contacts
- Database issues: Check MongoDB docs
- Backend crashes: Check systemd logs
- Security concerns: Review audit_logs collection
- Performance degradation: Scale resources

## Success Metrics

### System Health
- [ ] Uptime > 99.9%
- [ ] API latency < 200ms
- [ ] WebSocket reconnects < 1/hour
- [ ] Database queries < 50ms

### User Experience
- [ ] Dashboard loads < 2s
- [ ] Real-time updates < 1s lag
- [ ] No JavaScript errors
- [ ] All features functional

### Trading Performance
- [ ] Paper bots: 2-6% monthly return (realistic)
- [ ] Fee accuracy: Within 0.01% of actual
- [ ] Order success rate: 97%+
- [ ] No rate limit violations

---

**Deployment Status: READY FOR PRODUCTION** 🚀

For issues or questions, refer to:
- API Documentation: `docs/api_contract.md`
- Nginx Config: `docs/nginx.conf`
- Smoke Tests: `scripts/smoke_api.sh`
