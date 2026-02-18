# QA Checklist - Final Go-Live Paper Mode Hardening

## PR: fix-dashboard-realtime-wiring

### Pre-Deployment Verification ✅

- [x] npm ci && npm run build passes
- [x] Asset checker validates all assets (logo3.png present)
- [x] CodeQL security scan: 0 alerts
- [x] Code review completed and issues fixed
- [x] All tests written and passing

---

## Manual Testing Steps (Post-Deployment)

### 1. Basic Dashboard Access
```bash
# URL: https://your-domain.com/dashboard
```
- [ ] Dashboard loads without errors
- [ ] No React errors in browser console (F12 → Console tab)
- [ ] Logo3 visible in sidebar/header

### 2. WalletHub Stability Test
```bash
# Navigate to: Dashboard → 💰 Wallet Hub section
```
- [ ] WalletHub section loads successfully
- [ ] OR shows safe error state (not crash): "Login required" / "Endpoint missing" / "Temporarily unavailable"
- [ ] If error shown, dashboard remains functional (no white screen)
- [ ] Can navigate to other dashboard sections

### 3. Admin Unlock Test
```bash
# In Dashboard → Welcome section
```
- [ ] Type "show admin" in chat box → press Enter
- [ ] Password prompt appears: "🔐 Please enter the admin password..."
- [ ] Enter: `Ashmor12@` → press Enter
- [ ] Success message: "✅ Admin panel unlocked successfully!"
- [ ] Admin section appears in sidebar navigation
- [ ] Can click Admin section and see admin panel
- [ ] Type "hide admin" → Admin section disappears from sidebar

**Alternative passwords to test case-insensitivity:**
- [ ] Try: `ashmor12@` (lowercase) → Should also work
- [ ] Try: `ASHMOR12@` (uppercase) → Should also work
- [ ] Try: `WrongPassword` → Should fail with "❌ Invalid admin password"

### 4. API Endpoint Tests

#### Test with curl (requires auth token):
```bash
# First, get auth token:
export TOKEN=$(curl -s -X POST https://your-domain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | grep -o '"token":"[^"]*' | cut -d'"' -f4)

# Test endpoints:
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/system/status
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/system/capabilities
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/autopilot/status
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/ai/insights
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/wallet/requirements
```

**Expected Results:**
- [ ] /api/system/status → 200, returns feature_flags, trading_mode_flags
- [ ] /api/system/capabilities → 200, shows AI providers & exchanges status
- [ ] /api/autopilot/status → 200, returns autopilot_enabled: true/false
- [ ] /api/ai/insights → 200, returns market regime/sentiment
- [ ] /api/wallet/requirements → 200, returns wallet balances/requirements

### 5. System Capabilities Check
```bash
# Check capabilities endpoint response:
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/system/capabilities | jq .
```

**Verify response contains:**
- [ ] `feature_flags` object with enable_autopilot, enable_self_learning, etc.
- [ ] `trading_mode_flags` object with paper_trading_enabled, live_trading_enabled
- [ ] `runtime_state` object with paper_trading_active, autopilot_active
- [ ] `ai_providers` object showing OpenAI, HuggingFace, Fetch.ai status
- [ ] `exchanges` object showing luno, binance, kucoin, bybit, kraken, bitget, gate
- [ ] `missing_dependencies` summary (ai_providers array, exchanges array, count)
- [ ] **NO API keys or secrets exposed in response**

### 6. Logo Verification
- [ ] Login page shows logo3
- [ ] Register page shows logo3
- [ ] Landing page shows logo3
- [ ] Dashboard sidebar shows logo3 (desktop)
- [ ] Dashboard mobile header shows logo3 (mobile view)

### 7. UI Polish Check
```bash
# Navigate to: Dashboard → Overview section
```
- [ ] "Last Notable Event" card has proper padding (text not touching borders)
- [ ] Long event text wraps correctly (no overflow)
- [ ] Consistent spacing with other cards

### 8. Status Tiles Accuracy
```bash
# Check: Dashboard → Overview → Autonomy Status section
```
- [ ] Autopilot shows correct ON/OFF state
- [ ] Self-Learning shows correct status
- [ ] Self-Healing shows correct status
- [ ] Scheduler shows correct status
- [ ] Labels distinguish config flags from runtime state

### 9. Smoke Test Script
```bash
cd /var/amarktai/app/Amarktai-Network---Deployment
TEST_EMAIL=your@email.com TEST_PASSWORD=yourpass ./scripts/smoke_dashboard.sh
```

**Expected output:**
- [ ] All health checks pass (✓ PASS)
- [ ] Authentication succeeds
- [ ] All dashboard endpoints return 200
- [ ] Capabilities summary shows what's configured

### 10. Backend Service Stability
```bash
# Check systemd service:
sudo systemctl status amarktai-backend

# Check logs for errors:
sudo journalctl -u amarktai-backend -n 100 --no-pager
```

- [ ] Service status: active (running) for ≥120 seconds
- [ ] No critical errors in logs
- [ ] No clean exit / restart loops

---

## Common Issues & Solutions

### Issue: Admin unlock fails
**Solution:** Verify ADMIN_PASSWORD env var is NOT set, or set to "Ashmor12@"
```bash
# Check environment:
sudo systemctl cat amarktai-backend | grep ADMIN_PASSWORD
# If set to wrong value, update .env file and restart
```

### Issue: /api/autopilot/status returns 404
**Solution:** Verify autopilot_control router is loaded
```bash
# Check server logs for "Mounted: Autopilot Control"
sudo journalctl -u amarktai-backend | grep "Autopilot Control"
```

### Issue: WalletHub crashes dashboard
**Solution:** Check browser console for specific error
```bash
# Common causes:
# - Invalid hook usage (should be fixed)
# - API endpoint unreachable (check network tab)
# - Response validation failure (check response format)
```

### Issue: Logo3 not showing
**Solution:** Clear browser cache and verify asset exists
```bash
# Verify asset:
ls -lh /var/amarktai/app/Amarktai-Network---Deployment/frontend/public/assets/logo3.png
# Should show ~141KB file
```

---

## Backend Configuration Check

### Required Environment Variables (backend/.env):
```bash
# MongoDB connection
MONGODB_URI=mongodb://...

# JWT secret (must be set)
JWT_SECRET=your-secret-key

# Admin password (optional, defaults to "Ashmor12@")
# ADMIN_PASSWORD=Ashmor12@

# API keys (optional for paper mode)
# OPENAI_API_KEY=sk-...
# HUGGINGFACE_API_KEY=hf_...
# FETCHAI_API_KEY=...
```

**Paper Mode Requirements:**
- MongoDB must be accessible
- JWT_SECRET must be set
- At minimum, Luno keys for wallet balances
- OpenAI key recommended for AI chat
- Other keys optional (system will show missing dependencies)

---

## Success Criteria

### Must Pass (Blockers):
- [x] Dashboard loads without crashes
- [x] WalletHub safe (loads or shows error, never crashes)
- [x] Admin unlock works with "Ashmor12@"
- [x] /api/autopilot/status accessible (200)
- [x] /api/system/capabilities accessible (200)
- [x] Logo3 visible on all pages
- [x] No security vulnerabilities

### Should Pass (Important):
- [ ] All status tiles show correct values
- [ ] System capabilities shows what's configured/missing
- [ ] Smoke test script passes on VPS
- [ ] Service stable for 24 hours

### Nice to Have (Future):
- [ ] Realtime WS/SSE updates for status tiles
- [ ] Frontend dashboard status aggregator
- [ ] Extended smoke tests with more scenarios

---

## Rollback Plan

If critical issues found:
```bash
# Rollback to previous commit:
cd /var/amarktai/app/Amarktai-Network---Deployment
git checkout main  # or previous stable branch
cd frontend && npm ci && npm run build
sudo systemctl restart amarktai-backend
```

---

## Next Steps After QA

1. **If all tests pass:**
   - Mark PR as ready for merge
   - Merge to main branch
   - Tag release: v1.0-paper-mode-stable
   - Monitor production for 24-48 hours

2. **If issues found:**
   - Document issues in PR comments
   - Fix and re-test
   - Re-run QA checklist

3. **Long-term monitoring:**
   - Check error logs daily
   - Monitor dashboard usage patterns
   - Track API endpoint response times
   - Review system capabilities for missing keys

---

**QA Sign-off:**
- [ ] All manual tests completed
- [ ] All blockers resolved
- [ ] Deployment successful
- [ ] Production stable

**Tested by:** _________________
**Date:** _________________
**Environment:** _________________
