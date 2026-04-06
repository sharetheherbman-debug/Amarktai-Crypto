# Production Go-Live Checklist

This checklist ensures the Amarktai Network trading system is ready for production deployment with real-time paper trading.

## Pre-Deployment Checklist

### 1. Code Quality
- [x] All critical blockers fixed (UnboundLocalError, empty trades, etc.)
- [x] No inner `import database as db` statements in functions
- [x] All duplicate code removed
- [x] Exchange filtering implemented (luno, binance, kucoin only)
- [x] Trade validation added
- [ ] All tests passing (`pytest backend/tests/`)
- [ ] No linter errors

### 2. Configuration Review

#### Environment Variables (.env)
```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=<your-secure-secret-key>

# Feature Flags - PRODUCTION SETTINGS
ENABLE_TRADING=true              # ✅ Enable for paper trading
ENABLE_PAPER_TRADING=true        # ✅ Enable paper trading
ENABLE_LIVE_TRADING=false        # ❌ Keep OFF until ready
ENABLE_AUTOPILOT=true            # ✅ Enable autonomous management
ENABLE_BODYGUARD=true            # ✅ Enable AI protection
ENABLE_REALTIME=true             # ✅ Enable SSE/WS events
ENABLE_SELF_HEALING=true         # ✅ Enable auto-recovery
ENABLE_CCXT=true                 # ✅ Enable exchange integration

# Trading Safety
PAPER_TRAINING_DAYS=7            # Minimum 7 days required
REQUIRE_WALLET_FUNDED=true       # Must have funded wallet for live
REQUIRE_API_KEYS_FOR_LIVE=true   # Must have exchange keys for live

# Optional - AI Integrations
OPENAI_API_KEY=<your-openai-key>
FETCHAI_API_KEY=<optional>
COINSTATS_API_KEY=<optional>
```

### 3. Database Setup
- [ ] MongoDB running and accessible
- [ ] Database collections initialized
- [ ] Test connection: `mongosh --eval "db.adminCommand('ping')"`
- [ ] Verify collections exist: `users`, `bots`, `trades`, `system_modes`, `api_keys`

### 4. System Dependencies
- [ ] Python 3.10+ installed
- [ ] All requirements installed: `pip install -r backend/requirements.txt`
- [ ] CCXT library working: `python -c "import ccxt; print(ccxt.__version__)"`
- [ ] systemd service configured (see below)

## Deployment Steps

### 1. Deploy Code
```bash
# Pull latest code
cd /home/amarktai/Amarktai-Network---Deployment
git pull origin main

# Install/update dependencies
pip install -r backend/requirements.txt

# Run tests
pytest backend/tests/test_critical_fixes.py -v
```

### 2. Configure systemd Service

Create/update `/etc/systemd/system/amarktai-api.service`:

```ini
[Unit]
Description=Amarktai Network Trading API
After=network.target mongodb.service

[Service]
Type=simple
User=amarktai
WorkingDirectory=/home/amarktai/Amarktai-Network---Deployment
Environment="PATH=/home/amarktai/.local/bin:/usr/bin"
Environment="PYTHONPATH=/home/amarktai/Amarktai-Network---Deployment"
EnvironmentFile=/home/amarktai/Amarktai-Network---Deployment/.env
ExecStart=/usr/bin/python3 -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 3. Start/Restart Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable amarktai-api

# Start/Restart service
sudo systemctl restart amarktai-api

# Check status
sudo systemctl status amarktai-api
```

### 4. Verify Service Health
```bash
# Check if process is running
sudo systemctl is-active amarktai-api

# View logs
sudo journalctl -u amarktai-api -f

# Check for errors in last 100 lines
sudo journalctl -u amarktai-api -n 100 --no-pager | grep -i error
```

## Post-Deployment Verification

### 1. Health Endpoint
```bash
# Basic health check
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "database": "connected",
  "system_modes": {
    "emergency_stop": false,
    "live_trading_enabled": false,
    "paper_trading_enabled": true,
    "autopilot_enabled": true
  },
  "timestamp": "2024-01-20T17:30:00.000Z",
  "version": "3.0.0"
}
```

### 2. Check Database Connection
```bash
# From Python
python3 << EOF
import asyncio
from backend import database as db

async def test():
    await db.connect()
    result = await db.client.admin.command('ping')
    print(f"✅ DB Connected: {result}")
    
asyncio.run(test())
EOF
```

### 3. Verify Paper Trading is Active
```bash
# Check for paper trading logs
sudo journalctl -u amarktai-api -n 50 | grep -i "paper tick\|paper trading\|trade candidate"

# Should see:
# "📊 Paper tick start"
# "📊 Bots scanned: X active"
# "📊 Trade candidate: BotName on luno"
# "✅ Trade inserted: id=abc123, profit=5.00"
```

### 4. Test SSE/Realtime Events
```bash
# Listen for heartbeat events (should see every 10 seconds)
curl -N http://localhost:8000/api/realtime/events

# Should see periodic output:
# data: {"type":"heartbeat","timestamp":"...","scheduler":"trading_scheduler","status":"running"}
```

### 5. Verify Trade Insertions
```bash
# Check trades collection in MongoDB
mongosh amarktai_trading --eval "
  db.trades.find({is_paper: true}).sort({timestamp: -1}).limit(5).forEach(printjson)
"

# Verify each trade has required fields:
# - id (not just _id)
# - user_id
# - bot_id
# - exchange
# - pair/symbol
# - entry_price
# - exit_price
# - amount
# - profit_loss
# - fees
# - is_paper: true
# - status: "closed"
# - side: "BUY"
```

### 6. Check No 502 Errors
```bash
# Check Nginx logs (if using Nginx)
sudo tail -f /var/log/nginx/error.log

# Should NOT see:
# "upstream timed out"
# "502 Bad Gateway"
```

### 7. Verify Exchange Filtering
```bash
# Check that only luno/binance/kucoin bots are active
sudo journalctl -u amarktai-api -n 100 | grep -i "unsupported exchange"

# Verify ovex/valr bots are paused
mongosh amarktai_trading --eval "
  db.bots.find({
    exchange: {\$in: ['ovex', 'valr']},
    status: 'paused',
    pause_reason: 'UNSUPPORTED_EXCHANGE'
  }).count()
"
```

## Ongoing Monitoring

### Daily Checks
```bash
# 1. Service status
sudo systemctl status amarktai-api

# 2. Error count in last 24h
sudo journalctl -u amarktai-api --since "24 hours ago" | grep -c ERROR

# 3. Trade count today
mongosh amarktai_trading --eval "
  const today = new Date().toISOString().split('T')[0];
  db.trades.countDocuments({
    timestamp: {\$regex: '^' + today},
    is_paper: true
  })
"

# 4. Bot status summary
mongosh amarktai_trading --eval "
  db.bots.aggregate([
    {\$group: {_id: '\$status', count: {\$sum: 1}}}
  ]).forEach(printjson)
"
```

### Weekly Checks
- [ ] Review error logs for patterns
- [ ] Check disk space: `df -h`
- [ ] Check memory usage: `free -h`
- [ ] Review trade quality scores
- [ ] Verify no UnboundLocalError in logs
- [ ] Confirm no empty trade documents

## Live Trading Preparation (Future)

**DO NOT enable live trading until:**

1. [ ] **7+ days of successful paper trading completed**
   ```bash
   # Check paper training duration
   mongosh amarktai_trading --eval "
     db.bots.find({
       lifecycle_stage: 'paper_training'
     }).forEach(bot => {
       const start = new Date(bot.paper_start_date);
       const days = (Date.now() - start) / (1000 * 60 * 60 * 24);
       print(bot.name + ': ' + days.toFixed(1) + ' days');
     })
   "
   ```

2. [ ] **Wallet funded and verified**
   ```bash
   # Check wallet balances
   mongosh amarktai_trading --eval "
     db.users.find({}, {email: 1, wallet_balance: 1}).forEach(printjson)
   "
   ```

3. [ ] **Exchange API keys configured and tested**
   ```bash
   # Verify API keys exist
   mongosh amarktai_trading --eval "
     db.api_keys.find({}, {user_id: 1, exchange: 1, is_valid: 1}).forEach(printjson)
   "
   ```

4. [ ] **Risk engine tested and verified**
5. [ ] **Trade budget limits configured**
6. [ ] **Circuit breakers tested**
7. [ ] **Emergency stop procedure documented and tested**

### Enabling Live Trading
```bash
# 1. Update .env
ENABLE_LIVE_TRADING=true

# 2. Restart service
sudo systemctl restart amarktai-api

# 3. Monitor logs closely for first hour
sudo journalctl -u amarktai-api -f | grep -i "live trading"

# 4. Verify live trading gate enforcement
curl -X POST http://localhost:8000/api/trading/validate-live-ready \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}'
```

## Rollback Procedure

If issues arise:

```bash
# 1. Stop service
sudo systemctl stop amarktai-api

# 2. Disable problematic features via .env
ENABLE_TRADING=false
ENABLE_AUTOPILOT=false

# 3. Restart in safe mode
sudo systemctl start amarktai-api

# 4. Check logs
sudo journalctl -u amarktai-api -n 200 --no-pager

# 5. Restore from backup if needed
mongorestore --db amarktai_trading /path/to/backup
```

## Support Contacts

- **System Admin:** [admin@amarktai.network]
- **Development Team:** [dev@amarktai.network]
- **Emergency Contact:** [emergency@amarktai.network]

## Changelog

- **2024-01-20:** Initial production deployment with critical fixes
  - Fixed UnboundLocalError in risk_engine
  - Fixed empty trade documents
  - Removed duplicate close_exchanges code
  - Added exchange filtering (luno/binance/kucoin only)
  - Added heartbeat for realtime monitoring
  - Enabled all features except live trading

---

**Last Updated:** 2024-01-20  
**Version:** 3.0.0  
**Status:** ✅ Production Ready (Paper Trading Only)
