---
**⚠️ ARCHIVED DOCUMENT - DO NOT TRUST**

This document is archived and may contain outdated information.
It references VALR and OVEX which are NO LONGER supported.

Current supported exchanges (7): luno, binance, kucoin, bybit, kraken, bitget, gate

---

# GO-LIVE CHECKLIST

**Date:** _____________
**Deployed By:** _____________
**Environment:** Production

---

## CRITICAL ENVIRONMENT VARIABLES

### Required for Production:

```bash
# Admin access
ADMIN_PASSWORD=Ashmor12@

# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading

# Security
JWT_SECRET=your-production-secret-change-this
API_KEY_ENCRYPTION_KEY=your-encryption-key-base64

# Feature flags
ENABLE_TRADING=false      # Start with paper trading only, set to true for live
ENABLE_AUTOPILOT=false    # Enable after testing
ENABLE_CCXT=true          # Required for price data
ENABLE_SCHEDULERS=false   # Enable after testing

# Optional (for full functionality)
OPENAI_API_KEY=your-openai-key
FETCHAI_API_KEY=your-fetchai-key
COINSTATS_API_KEY=your-coinstats-key
```

### Setting Environment Variables on Ubuntu Systemd:

1. Edit systemd service file:
```bash
sudo nano /etc/systemd/system/amarktai-api.service
```

2. Add environment variables:
```ini
[Service]
Environment="ADMIN_PASSWORD=Ashmor12@"
Environment="MONGO_URL=mongodb://localhost:27017"
Environment="ENABLE_CCXT=true"
# Add other vars...
```

3. Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

---

## PRE-DEPLOYMENT VERIFICATION

### 1. Run Verification Script ✓

```bash
cd /path/to/Amarktai-Network---Deployment
bash scripts/verify_go_live.sh
```

**Expected Output:**
- ✓ All platform checks pass (OVEX present, Kraken removed)
- ✓ Platform constants verified (exactly 5 platforms, TOTAL_BOT_CAPACITY=45)
- ✓ Admin endpoints exist
- ✓ Dashboard PlatformSelector not duplicated
- ✓ No Kraken references in code
- ✓ No hardcoded platform arrays in Dashboard
- ✓ Frontend build successful
- ✓ Bundle contains required strings (OVEX, Win Rate, Trade Count)
- ✓ Bundle does NOT contain Kraken
- ✓ All required files present
- ✓ LiveTradesView removed (was unused)

**Script must show:** `✓ ALL CHECKS PASSED - READY FOR GO-LIVE! 🎉`

If any checks fail, review and fix before proceeding.

---

## DEPLOYMENT STEPS

### 2. Backend Deployment ✓

```bash
cd /path/to/Amarktai-Network---Deployment/backend

# 1. Pull latest code
git pull origin main

# 2. Activate virtual environment (if using)
source venv/bin/activate

# 3. Install/update dependencies
pip install -r requirements.txt

# 4. Verify environment variables are set
printenv | grep -E "ADMIN_PASSWORD|MONGO_URL|JWT_SECRET"

# 5. Test backend starts without errors
python server.py &
sleep 5
curl http://localhost:8000/api/health/ping
pkill -f "python server.py"

# 6. Restart via systemd
sudo systemctl restart amarktai-api
sudo systemctl status amarktai-api

# 7. Check logs for errors
sudo journalctl -u amarktai-api -f --lines=50
```

### 3. Frontend Build & Deployment ✓

```bash
cd /path/to/Amarktai-Network---Deployment/frontend

# 1. Pull latest code (if not already done)
git pull origin main

# 2. Install/update dependencies
npm install

# 3. Build production bundle
npm run build

# 4. Verify build succeeded
ls -lh build/
# Should see index.html, static/, assets/, etc.

# 5. Deploy to web server
# Option A: Copy to nginx root
sudo rm -rf /var/www/amarktai/*
sudo cp -r build/* /var/www/amarktai/

# Option B: Use rsync
sudo rsync -av --delete build/ /var/www/amarktai/

# 6. Set correct permissions
sudo chown -R www-data:www-data /var/www/amarktai
sudo chmod -R 755 /var/www/amarktai

# 7. Restart nginx
sudo systemctl reload nginx
sudo systemctl status nginx
```

---

## POST-DEPLOYMENT VALIDATION

### 4. Backend Health Checks ✓

```bash
API="http://localhost:8000/api"

# Health check
curl $API/health/ping
# Expected: {"status":"ok"}

# Paper trading status
curl $API/health/paper-trading
# Expected: {"status":"ok", "paper_trading": {...}}

# System health indicators
curl $API/health/indicators
# Expected: {"overall_status":"healthy"}

# Note: /api/prices/live requires authentication token
# curl $API/prices/live -H "Authorization: Bearer $TOKEN"
# Expected: {"btc": 1234567.89, ...}
```

### 5. Admin Access Test ✓

```bash
# Get auth token first (login as admin user)
TOKEN="your-jwt-token"

# Test admin unlock
curl -X POST http://localhost:8000/api/admin/unlock \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"password":"Ashmor12@"}'
  
# Expected: {"success": true, "token": "..."}
```

### 6. Platform Verification ✓

Check that all 5 platforms are available:
- Luno (max 5 bots)
- Binance (max 10 bots)
- KuCoin (max 10 bots)
- OVEX (max 10 bots)
- VALR (max 10 bots)

```bash
# Check backend config
grep -A 20 "BOT_ALLOCATION" backend/exchange_limits.py

# Check frontend (access site and inspect bot creation dropdown)
```

### 7. Frontend Access ✓

```bash
# Check nginx is serving frontend
curl -I http://localhost/
# Expected: 200 OK

# Check assets load
curl -I http://localhost/assets/logo.png
# Expected: 200 OK
```

### 8. Paper Trading Execution Test ✓

1. Login to dashboard
2. Navigate to Autopilot section
3. Enable Autopilot with Paper Trading mode
4. Wait 60 seconds
5. Check trades appear in Live Trades section
6. Verify paper trading status shows trades executing

### 9. WebSocket Connection Test ✓

1. Open browser developer console
2. Navigate to dashboard
3. Check Network tab for WebSocket connection
4. Should see: `ws://` or `wss://` connection established
5. Verify real-time updates work (bots, trades, metrics)

### 10. Metrics Tabs Test ✓

Navigate to Metrics section and verify all tabs work:
- [ ] Flokx Alerts - No errors, shows data or empty state
- [ ] Decision Trace - No blank screen, shows placeholder if empty
- [ ] Whale Flow - No errors, handles missing data gracefully
- [ ] System Metrics - Loads without crashes

---

## PRE-DEPLOYMENT CHECKS (Detailed)

### 1. Assets ✓
- [ ] All assets exist in `frontend/public/assets/`
- [ ] Run `npm run check:assets` passes
- [ ] logo.png, poster.jpg, background.mp4 all non-empty
- [ ] Assets accessible at `/assets/*` URLs

### 2. Build & Dependencies ✓
- [ ] `npm install` completes without errors
- [ ] `npm run build` succeeds
- [ ] Build output in `frontend/build/`
- [ ] No console errors in build output
- [ ] Build size reasonable (<10MB)

### 3. Environment Variables ✓
- [ ] Backend `.env` configured:
  - `MONGODB_URI`
  - `JWT_SECRET`
  - `ENABLE_TRADING=1` (for production)
  - `ENABLE_SCHEDULERS=1`
  - Exchange API keys configured
- [ ] Frontend environment (if using):
  - `REACT_APP_API_BASE=/api` (or appropriate)

---

## BACKEND VALIDATION

### 4. Database & Connectivity ✓
- [ ] MongoDB accessible
- [ ] Run: `curl http://localhost:8000/api/health/ping`
  - Expect: `{"status":"healthy","db":"connected"}`
- [ ] Collections created: users, bots, trades, api_keys, etc.

### 5. Critical Endpoints ✓
Test all critical endpoints with authenticated token:

```bash
TOKEN="<your-jwt-token>"
API="http://localhost:8000/api"

# Health
curl -H "Authorization: Bearer $TOKEN" $API/health/ping

# Platforms (must return 5)
curl -H "Authorization: Bearer $TOKEN" $API/system/platforms

# User
curl -H "Authorization: Bearer $TOKEN" $API/auth/me

# Bots
curl -H "Authorization: Bearer $TOKEN" $API/bots

# Trades
curl -H "Authorization: Bearer $TOKEN" $API/trades/recent?limit=10

# Wallet
curl -H "Authorization: Bearer $TOKEN" $API/wallet/balances

# Metrics
curl -H "Authorization: Bearer $TOKEN" $API/portfolio/summary

# System Health
curl -H "Authorization: Bearer $TOKEN" $API/system/health
```

- [ ] All endpoints return 200 or expected status
- [ ] No 500 errors
- [ ] All return valid JSON

### 6. WebSocket ✓
- [ ] WebSocket endpoint accessible: `ws://localhost:8000/api/ws?token=$TOKEN`
- [ ] Connection accepts and sends ping/pong
- [ ] Connection survives 60+ seconds
- [ ] Test with tool: `websocat ws://localhost:8000/api/ws?token=$TOKEN`

---

## FRONTEND VALIDATION

### 7. Login & Authentication ✓
- [ ] Navigate to `/login`
- [ ] Login form renders correctly
- [ ] Can login with valid credentials
- [ ] JWT token stored in localStorage
- [ ] Redirected to dashboard on success
- [ ] Invalid credentials show error

### 8. Dashboard Sections ✓
Test all main sections load without errors:

- [ ] **Welcome/Overview**: Metrics display
- [ ] **Bot Management**: Bots list, can create bot
- [ ] **Live Trades**: Trades stream visible
- [ ] **Wallet Hub**: Balances load, no "Not Found"
- [ ] **Intelligence > Whale Flow**: Component loads
- [ ] **Intelligence > Decision Trace**: Component loads
- [ ] **Intelligence > Metrics**: Prometheus metrics load
- [ ] **API Setup**: Keys management works
- [ ] **Settings**: Profile update works

### 9. Platform Selector ✓
- [ ] Platform selector shows all 5 platforms:
  - 🌙 Luno
  - 🔶 Binance  
  - 🔷 KuCoin
  - 🐙 Kraken
  - 💎 VALR
- [ ] "All Platforms" option present
- [ ] Selecting platform filters views

### 10. Real-Time Updates ✓
- [ ] Open browser DevTools → Console
- [ ] Look for: `✅ WebSocket connected`
- [ ] Connection status shows "Connected (WS)" or "Connected (Polling)"
- [ ] Last update timestamps visible
- [ ] Ping/pong messages in console (every 30s)
- [ ] Create a test trade → see it appear in dashboard

### 11. Assets Loading ✓
- [ ] Logo displays correctly
- [ ] Background video plays (if applicable)
- [ ] No broken image icons
- [ ] Check browser DevTools → Network → no 404s for assets

---

## DEPLOYMENT VALIDATION

### 12. Nginx Configuration ✓
- [ ] Nginx config includes proxy_pass to backend
- [ ] WebSocket upgrade headers configured:
  ```nginx
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  ```
- [ ] Static files served from `/var/amarktai/app/frontend/build`
- [ ] `/api/*` proxied to backend
- [ ] SSL certificate valid (if HTTPS)
- [ ] Test: `curl https://your-domain.com/api/health/ping`

### 13. Systemd Services ✓
- [ ] Backend service running: `systemctl status amarktai-backend`
- [ ] Service set to auto-start: `systemctl is-enabled amarktai-backend`
- [ ] Check logs: `journalctl -u amarktai-backend -f`
- [ ] No critical errors in logs

### 14. Firewall & Security ✓
- [ ] Firewall allows HTTP/HTTPS (ports 80, 443)
- [ ] Backend port (8000) not exposed externally
- [ ] SSH access restricted (if applicable)
- [ ] Rate limiting configured in Nginx (if applicable)

---

## FUNCTIONAL TESTING

### 15. Create Bot Flow ✓
- [ ] Navigate to Bot Management
- [ ] Click "Create Bot"
- [ ] Select platform (e.g., Luno)
- [ ] Configure symbol, capital, risk
- [ ] Submit → bot appears in list
- [ ] Bot shows correct status

### 16. Live Trading Toggle ✓
- [ ] Paper trading mode works
- [ ] Can promote bot to live (if conditions met)
- [ ] Confirmation dialog appears
- [ ] Live trading requires explicit enable

### 17. AI Tools ✓
Test AI tool buttons (if configured):
- [ ] AI Bodyguard → runs system check
- [ ] Learning System → triggers learning
- [ ] Evolve Bots → shows result
- [ ] Insights → fetches insights
- [ ] Predict → shows prediction
- [ ] Reinvest Profits → confirms action
- [ ] If not configured → shows "not configured" message (no crash)

### 18. Admin Panel ✓
- [ ] Type "show admin" in chat
- [ ] Prompted for admin password
- [ ] Enter correct password → admin panel appears
- [ ] Admin panel shows users, stats
- [ ] Type "hide admin" → panel hides
- [ ] Refresh page → admin panel stays hidden (not persisted)

---

## PERFORMANCE & MONITORING

### 19. Performance ✓
- [ ] Dashboard loads in <3 seconds
- [ ] No memory leaks (check DevTools → Memory)
- [ ] WebSocket reconnects after disconnect
- [ ] Page responsive on mobile

### 20. Error Handling ✓
- [ ] Disconnect internet → see "Disconnected" status
- [ ] Reconnect → see "Connected" status
- [ ] Invalid API calls → show error toast, don't crash
- [ ] Empty states render (no bots, no trades, etc.)

### 21. Monitoring Setup ✓
- [ ] Prometheus metrics accessible: `/api/metrics`
- [ ] System health endpoint: `/api/system/health`
- [ ] Logs aggregated (e.g., journalctl, file logs)
- [ ] Alert mechanisms configured (email, etc.)

---

## FINAL SIGN-OFF

### 22. Documentation ✓
- [ ] README.md updated with setup instructions
- [ ] ENDPOINTS.md lists all endpoints
- [ ] Deployment guide complete
- [ ] Known issues documented (if any)

### 23. Backup & Recovery ✓
- [ ] Database backup created
- [ ] Backup restoration tested
- [ ] Config files backed up
- [ ] Rollback plan documented

### 24. Handoff ✓
- [ ] Stakeholders notified
- [ ] Support contacts documented
- [ ] Emergency procedures documented
- [ ] Go-live announcement prepared

---

## POST-DEPLOYMENT MONITORING

### First Hour ✓
- [ ] Monitor CPU/RAM usage
- [ ] Watch logs for errors
- [ ] Test all critical flows
- [ ] Verify real-time updates working

### First 24 Hours ✓
- [ ] Check error rates
- [ ] Monitor WebSocket stability
- [ ] Verify no data loss
- [ ] User feedback collected

### First Week ✓
- [ ] Performance metrics reviewed
- [ ] No critical bugs reported
- [ ] System stable under load
- [ ] Backup schedule working

---

**SIGN-OFF**

- [ ] All checks completed
- [ ] System ready for production
- [ ] Stakeholders approved

**Signed:** _____________  
**Date:** _____________  
**Status:** [ ] APPROVED [ ] PENDING [ ] FAILED

---

## Emergency Contacts

- **Backend Issues:** _____________
- **Frontend Issues:** _____________
- **Database Issues:** _____________
- **Infrastructure:** _____________

## Rollback Procedure

If critical issues occur:

1. Stop nginx: `sudo systemctl stop nginx`
2. Stop backend: `sudo systemctl stop amarktai-backend`
3. Restore previous build: `mv build.backup build`
4. Restore database: (restore from backup)
5. Start services
6. Notify stakeholders
