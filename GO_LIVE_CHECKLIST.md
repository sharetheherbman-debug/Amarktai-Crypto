# Final Go-Live Verification Checklist

## Pre-Deployment Checklist

### Critical Requirements ✅

- [x] **Endpoint Alignment**
  - [x] `/api/analytics/performance` endpoint exists (no 404s)
  - [x] Compatibility layer (`routes/compat.py`) created and mounted
  - [x] All legacy endpoints have compat aliases
  - [x] Warnings logged when compat endpoints used

- [x] **Platform Configuration**
  - [x] Exactly 7 exchanges: luno, binance, kucoin, bybit, kraken, bitget, gate
  - [x] NO VALR or OVEX in production code
  - [x] Platform config in `config/platforms.py` verified

- [x] **API Key Security**
  - [x] Fernet encryption implemented
  - [x] Keys stored encrypted at rest
  - [x] List endpoint returns masked keys only (last 4 chars)
  - [x] Test, save, delete endpoints all functional
  - [x] Compat aliases for `/api/api-keys/*` added

- [x] **Realtime System**
  - [x] `broadcast()` method added to ConnectionManager
  - [x] `/api/diagnostics/realtime-smoke` endpoint verified
  - [x] WebSocket, SSE, and broadcast channels tested

- [x] **Admin Authentication**
  - [x] `resolve_current_user()` helper created
  - [x] Admin guard normalizes user_id reliably
  - [x] Notifications endpoints fixed to use helper
  - [x] No more "User not found" errors

- [x] **Trading Mode Gating**
  - [x] Paper trading requires initial_capital > 0
  - [x] Paper wallet ledger service implemented
  - [x] Live trading requires API keys + balance + confirmation
  - [x] Global gate: trading blocked if both modes false
  - [x] Autopilot respects all safety checks
  - [x] 15+ comprehensive tests added

- [x] **UI Cleanup**
  - [x] Duplicate "Realtime Connection" widget removed
  - [x] Landing page copyright updated with "Personal Use Only"
  - [x] Dark glassmorphism design preserved

- [x] **2FA System**
  - [x] Enrollment endpoint verified
  - [x] Verification endpoint verified
  - [x] Status endpoint verified
  - [x] Ready for wallet transfer enforcement

- [x] **SMTP & Notifications**
  - [x] SMTP config reads from environment
  - [x] `/api/notifications/test-email` endpoint exists (admin-only)
  - [x] Email service properly configured

- [x] **Smoke Tests**
  - [x] `scripts/go_live_smoke.sh` enhanced
  - [x] Tests: health, login, platforms, API keys, realtime, analytics, admin
  - [x] Script executable and ready to run

- [x] **Documentation**
  - [x] `UPGRADE_NOTES.md` created with full deployment guide
  - [x] Rollback plan documented
  - [x] Post-deployment verification steps included
  - [x] Environment variables documented

---

## Deployment Steps

### 1. Pre-Deployment
```bash
# Verify all changes committed
git status

# Pull latest
git pull origin copilot/final-repo-update-amarktai

# Backup database
mongodump --db amarktai --out /backup/pre-golive-$(date +%Y%m%d)
```

### 2. Backend Deployment
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Verify environment variables
python -c "import os; print('✓ AMARKTAI_FERNET_KEY' if os.getenv('AMARKTAI_FERNET_KEY') else '✗ Missing FERNET_KEY')"
python -c "import os; print('✓ JWT_SECRET' if os.getenv('JWT_SECRET') else '✗ Missing JWT_SECRET')"
python -c "import os; print('✓ MONGODB_URI' if os.getenv('MONGODB_URI') else '✗ Missing MONGODB_URI')"

# Run migrations
python -m migrations.fix_user_id_field

# Start backend (or restart systemd service)
python server.py
# OR: sudo systemctl restart amarktai-backend
```

### 3. Frontend Deployment
```bash
cd frontend

# Install dependencies
npm install

# Build
npm run build

# Deploy build (or restart systemd service)
# sudo systemctl restart amarktai-frontend
```

### 4. Run Smoke Tests
```bash
# Set test credentials
export AMK_EMAIL=admin@example.com
export AMK_PASSWORD=your-admin-password

# Run smoke tests
chmod +x scripts/go_live_smoke.sh
./scripts/go_live_smoke.sh

# Expected output:
# ✅ All critical tests passed!
# System is ready for go-live.
```

### 5. Post-Deployment Verification
```bash
# Health check
curl https://your-domain.com/api/health/ping
# Expected: {"status": "ok"}

# Platform count
curl https://your-domain.com/api/platforms | jq '.platforms | length'
# Expected: 7

# Check logs for errors
tail -100 /var/log/amarktai/backend.log | grep ERROR
# Expected: No critical errors
```

---

## Manual Verification Tests

### Test 1: Login & Dashboard
1. Navigate to https://your-domain.com
2. Click "Login"
3. Enter credentials
4. Verify dashboard loads without 404 errors
5. Check console for errors (F12)
   - Expected: No 404s for `/api/analytics/performance`

### Test 2: Realtime Connection
1. On dashboard, check header status indicators
2. Verify WebSocket shows "Connected" (green dot)
3. Create a test bot
4. Verify bot appears immediately (realtime update)

### Test 3: API Keys (if admin)
1. Navigate to API Keys section
2. Add a test key for any exchange
3. Verify key is masked in the list (shows only last 4 chars)
4. Test the key
5. Verify test result shows (success/fail)
6. Delete the key
7. Verify it's removed from list

### Test 4: Analytics
1. Navigate to Analytics section
2. Verify performance metrics load
3. Check for win rate, total trades, P&L
4. Expected: All data displays correctly, no 404s

### Test 5: Admin Panel (if admin)
1. Navigate to Admin section
2. Click "Users List"
3. Verify list loads without "User not found" error
4. Expected: User list displays correctly

### Test 6: Trading Mode
1. Check system mode in dashboard
2. Verify paper_trading or live_trading is enabled
3. Try creating a bot with 0 capital
4. Expected: Error message about minimum capital requirement
5. Create bot with valid capital (e.g., 100)
6. Expected: Bot created successfully

---

## Rollback Procedure (If Needed)

### Quick Rollback
```bash
# Stop services
sudo systemctl stop amarktai-backend
sudo systemctl stop amarktai-frontend

# Checkout previous version
git checkout <previous-commit-sha>

# Restore database
mongorestore --drop --db amarktai /backup/pre-golive-YYYYMMDD/amarktai

# Restart services
sudo systemctl start amarktai-backend
sudo systemctl start amarktai-frontend

# Verify
curl http://localhost:8000/api/health/ping
```

---

## Known Good State

**Commit:** 578a890 (or latest on copilot/final-repo-update-amarktai)
**Branch:** copilot/final-repo-update-amarktai
**Date:** 2026-02-04

**Files Modified:**
- backend/routes/compat.py (NEW)
- backend/routes/analytics_api.py (MODIFIED)
- backend/routes/notifications.py (MODIFIED)
- backend/websocket_manager.py (MODIFIED)
- backend/server.py (MODIFIED)
- frontend/src/pages/Landing.js (MODIFIED)
- frontend/src/pages/Dashboard.js (MODIFIED)
- scripts/go_live_smoke.sh (ENHANCED)
- UPGRADE_NOTES.md (NEW)

**Files Added by Task Agents:**
- backend/services/paper_wallet_ledger.py
- backend/services/trading_mode_validator.py
- backend/tests/test_admin_auth_fix.py
- backend/tests/test_admin_auth_integration.py
- backend/tests/test_trading_mode_gating.py
- docs/ADMIN_AUTH_FIX.md
- docs/TRADING_MODE_GATING.md
- Various implementation summaries

---

## Success Criteria

✅ All smoke tests pass (exit code 0)
✅ No 404 errors on frontend
✅ Exactly 7 exchanges listed
✅ Realtime events working
✅ Admin panel accessible
✅ API keys encrypted and masked
✅ Trading gates enforced
✅ Zero critical errors in logs

---

## Emergency Contacts

**Technical Lead:** development@amarktai.com
**DevOps:** devops@amarktai.com
**24/7 Support:** support@amarktai.com

---

## Sign-Off

- [ ] All pre-deployment checks completed
- [ ] Smoke tests passed
- [ ] Manual verification tests passed
- [ ] Post-deployment verification completed
- [ ] Logs reviewed, no critical errors
- [ ] Rollback plan reviewed and understood
- [ ] Team notified of go-live

**Deployed By:** _____________
**Date/Time:** _____________
**Sign-Off:** _____________

---

**Status:** ✅ READY FOR PRODUCTION GO-LIVE
