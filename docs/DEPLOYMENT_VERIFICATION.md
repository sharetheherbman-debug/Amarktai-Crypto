# Deployment Verification Checklist

## Pre-Deployment Checklist

Before deploying to production, ensure:

- [ ] All tests pass locally
- [ ] Backend starts without route collisions
- [ ] Frontend builds successfully
- [ ] `.env` files are configured correctly
- [ ] Database connection string is correct
- [ ] API keys for exchanges are configured (if going live)

## Post-Deployment Verification

### Step 1: Verify Backend is Running

```bash
# Check service status
sudo systemctl status amarktai-api.service

# Should show:
# ● amarktai-api.service - Amarktai Network API
#    Active: active (running) since ...
```

### Step 2: Check Route Registration

```bash
# Check startup logs for wallet routes
sudo journalctl -u amarktai-api.service -n 200 | grep "WALLET ROUTES"

# Expected output:
# 📋 WALLET ROUTES REGISTERED:
#    GET /api/wallet/balances                      -> get_all_balances
#    POST /api/wallet/transfer                     -> transfer_funds
#    GET /api/wallet/transfers                     -> get_transfers
#    POST /api/wallet/transfers                    -> create_transfer
#    ...
# ✅ Total wallet routes: X
```

### Step 3: Test Critical Endpoints

```bash
# 1. Health check (no auth required)
curl https://your-domain.com/api/health/ping

# Expected: {"status": "ok", ...}

# 2. Build info (no auth required)
curl https://your-domain.com/api/build/info

# Expected: {"version": "...", "built_at": "...", "env": "production"}

# 3. Get JWT token (replace with valid credentials)
TOKEN=$(curl -X POST https://your-domain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' \
  | jq -r '.access_token')

echo "Token: $TOKEN"

# 4. Test wallet balances
curl https://your-domain.com/api/wallet/balances \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"user_id": "...", "master_wallet": {...}, ...}

# 5. Test unified profit metrics
curl https://your-domain.com/api/profits/metrics \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"success": true, "metrics": {...}, "data_source": "accounting_service"}

# 6. Test overview (should use accounting service)
curl https://your-domain.com/api/overview \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"data_source": "accounting_service", "net_realised_pnl_zar": ..., ...}
```

### Step 4: Run Automated Smoke Tests

```bash
# Set up environment
export API_BASE_URL=https://your-domain.com
export TEST_USERNAME=your@email.com
export TEST_PASSWORD=yourpassword

# Run smoke tests
python3 smoke_test.py

# Expected output:
# ✅ Health Check                                      [PASS]
# ✅ Build Info                                        [PASS]
# ✅ Authentication                                    [PASS]
# ✅ Wallet Balances                                   [PASS]
# ✅ Wallet Transfer Endpoint                          [PASS]
# ✅ Profit Metrics (Unified)                          [PASS]
# ✅ Overview Metrics (Unified)                        [PASS]
# 
# ✅ ALL SMOKE TESTS PASSED
```

### Step 5: Verify Frontend

1. **Open the application in a browser**: https://your-domain.com
2. **Check for version badge** in footer/header
3. **Verify it matches backend version**:
   ```bash
   # Get backend version
   curl https://your-domain.com/api/build/info | jq -r '.version'
   
   # Should match frontend version badge
   ```
4. **Test key functionality**:
   - [ ] Login works
   - [ ] Overview page shows metrics
   - [ ] Profits page shows consistent numbers
   - [ ] Live Trades page shows consistent numbers
   - [ ] Wallet page loads without errors

### Step 6: Verify Metrics Consistency

The most critical verification is that profit numbers match across pages:

```bash
TOKEN="your_jwt_token"

# Get metrics from three endpoints and compare
echo "=== Overview Metrics ==="
curl -s https://your-domain.com/api/overview \
  -H "Authorization: Bearer $TOKEN" \
  | jq '{net_realised_pnl_zar, executed_trades_count, total_fees_zar}'

echo "=== Profits Metrics ==="
curl -s https://your-domain.com/api/profits/metrics \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.metrics | {net_realised_pnl_zar, executed_trades_count, total_fees_zar}'

echo "=== Trades Metrics ==="
curl -s https://your-domain.com/api/trades/metrics \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.metrics | {net_realised_pnl_zar, executed_trades_count, total_fees_zar}'

# All three should return THE SAME VALUES
```

### Step 7: Check for Errors

```bash
# Check recent errors in logs
sudo journalctl -u amarktai-api.service -p err -n 50

# Should show NO errors or only acceptable warnings

# Check for route collision errors specifically
sudo journalctl -u amarktai-api.service | grep -i "collision"

# Should show:
# ✅ "Route collision check passed"
# ❌ NOT "ROUTE COLLISION DETECTED"
```

## Common Issues

### Issue: Route Collision Detected

**Symptoms**: Server won't start, logs show "ROUTE COLLISION DETECTED"

**Fix**:
1. Check which routes are colliding in logs
2. Verify wallet_endpoints.py uses `-legacy` and `-manual` suffixes
3. Verify no duplicate router includes in server.py
4. Restart server

### Issue: Metrics Don't Match

**Symptoms**: Overview shows different profit than Profits page

**Fix**:
1. Check logs for errors in accounting_service
2. Verify all endpoints use `accounting_service.get_unified_metrics()`
3. Check that `data_source` field says "accounting_service"
4. Restart backend to reload service

### Issue: Frontend Shows Old Version

**Symptoms**: Frontend version badge shows old commit SHA

**Fix**:
1. Rebuild frontend: `cd frontend && npm run build`
2. Clear nginx cache: `sudo nginx -s reload`
3. Hard refresh browser: Ctrl+Shift+R
4. Check build files have new timestamps: `ls -lh /path/to/frontend/build`

## Success Criteria

Deployment is successful when:

- ✅ Backend starts without errors
- ✅ No route collisions detected
- ✅ All smoke tests pass
- ✅ Frontend version matches backend version
- ✅ Profit metrics consistent across Overview, Profits, and Trades pages
- ✅ All `data_source` fields show "accounting_service"
- ✅ Wallet endpoints respond correctly
- ✅ Authentication works
- ✅ No critical errors in logs

## Rollback Procedure

If deployment fails verification:

```bash
# 1. Stop the service
sudo systemctl stop amarktai-api.service

# 2. Restore previous version
cd /opt/amarktai
git checkout <previous-commit>

# 3. Restart
sudo systemctl start amarktai-api.service

# 4. Verify rollback
curl https://your-domain.com/api/build/info

# 5. Investigate issue before retrying deployment
```

## Contact

If issues persist after following this checklist, check:
1. Backend logs: `sudo journalctl -u amarktai-api.service -f`
2. Nginx logs: `sudo tail -f /var/log/nginx/error.log`
3. Database connectivity: Verify MongoDB connection string
4. Network: Ensure ports 8000 (backend) and 80/443 (nginx) are open
