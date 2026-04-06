# Production Verification Guide

## How to Verify on VPS

After deploying the fixes, run these commands on your VPS to verify everything is working:

### 1. Quick Health Check
```bash
# Check if backend is running
curl -fsS https://www.amarktai.online/api/health/ping
# Expected: {"status":"ok"} or similar
```

### 2. OpenAPI Verification (TASK A)
```bash
# Check OpenAPI JSON is valid and contains auth routes
curl -fsS https://www.amarktai.online/api/openapi.json | jq . | grep "/api/auth/login"
# Expected: Should find "/api/auth/login" in the output

# Check OpenAPI size (should be >50KB, not 716 bytes)
curl -fsS https://www.amarktai.online/api/openapi.json | wc -c
# Expected: Number > 50000 (bytes)

# Access Swagger UI
curl -I https://www.amarktai.online/api/docs
# Expected: HTTP/1.1 200 OK

# Access ReDoc UI
curl -I https://www.amarktai.online/api/redoc
# Expected: HTTP/1.1 200 OK
```

### 3. Auth Response Consistency (TASK B)
```bash
# Test login endpoint (use your actual test credentials)
curl -X POST https://www.amarktai.online/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' | jq .

# Expected response should have:
# - "access_token": "..."
# - "token_type": "bearer"
# - NO "token" field (that would be duplicate)
```

### 4. API Keys Endpoints (TASK C/D/E)
```bash
# Get list of supported providers (no auth required)
curl -fsS https://www.amarktai.online/api/keys/providers | jq .
# Expected: JSON with providers array including openai, luno, binance, kucoin, etc.

# Try accessing status without auth (should fail)
curl -I https://www.amarktai.online/api/keys/status
# Expected: HTTP/1.1 401 Unauthorized
```

### 5. Admin Endpoints Protection (TASK F)
```bash
# All admin endpoints should require authentication
curl -I https://www.amarktai.online/api/admin/users
# Expected: HTTP/1.1 401 Unauthorized

curl -I https://www.amarktai.online/api/admin/overview
# Expected: HTTP/1.1 401 Unauthorized

curl -I https://www.amarktai.online/api/admin/unlock
# Expected: HTTP/1.1 401 Unauthorized
```

#### Admin Reset (Reset System to Zero)
```bash
# Requires admin JWT token (unlock first)
bash scripts/reset_system_zero.sh https://www.amarktai.online <ADMIN_TOKEN>
```

### 6. Frontend Verification
```bash
# Check frontend loads
curl -I https://www.amarktai.online/
# Expected: HTTP/1.1 200 OK with Content-Type: text/html

# Check footer (should show copyright, NOT build date by default)
curl -fsS https://www.amarktai.online/ | grep -i "amarktai network"
# Expected: Should find copyright text
```

### 7. Run Complete Verification Script
```bash
# On VPS, run the automated verification
cd /path/to/Amarktai-Crypto
bash scripts/verify_live.sh

# Expected: All checks should PASS
```

### 7b. API Contract Smoke (New)
```bash
# Verifies health ping, login token, bots status empty + meta exchanges
bash scripts/smoke_api_contract.sh https://www.amarktai.online you@example.com yourpassword
```

### 8. Check Backend Logs for Route Collisions
```bash
# Check backend logs for route collision detection
tail -f /var/log/amarktai/backend.log | grep "Route collision"
# Expected: "✅ Route collision check passed - X unique routes registered"

# If you see "❌ ROUTE COLLISION DETECTED", the server won't start
```

### 9. Manual Frontend Testing

Open https://www.amarktai.online in a browser and verify:

1. **Login Page**: Can log in successfully
2. **Dashboard Footer**: Shows "Part of Amarktai Network — For personal use only." (no build date visible)
3. **API Setup Section**:
   - OpenAI shows only API Key field
   - Luno/Binance/Bybit/Kraken/Gate show API Key + Secret
   - KuCoin shows API Key + Secret + Passphrase (NOT duplicated)
   - Bitget shows API Key + Secret + Passphrase
   - Save button works and shows clear success/failure
   - Test button works and shows result
4. **Admin Section**:
   - NOT visible by default
   - Type "show admin" in AI Chat
   - Enter admin password
   - Admin section becomes visible
   - Footer now shows build badge (only in admin view)
5. **No VALR or OVEX** mentioned anywhere in UI

### 10. Expected Supported Exchanges

The system should support exactly these 7 exchanges:
- Luno 🇿🇦
- Binance 🟡
- KuCoin 🟢
- Bybit 🟠
- Kraken 🟣
- Bitget 🔵
- Gate.io ⚪

**NOT supported**: VALR, OVEX (should not appear anywhere)

### Troubleshooting

If any checks fail:

1. **OpenAPI returns HTML (716 bytes)**:
   - Backend may not have restarted after changes
   - Check nginx proxy configuration for `/api/*`

2. **Login returns 401 with valid credentials**:
   - Check backend logs for authentication errors
   - Verify JWT secret is set in environment

3. **Route collision on startup**:
   - Check backend/server.py logs for duplicate route details
   - Review routers_to_mount list for duplicates

4. **Admin endpoints return 200 without auth**:
   - CRITICAL SECURITY ISSUE
   - Check that `require_admin` dependency is applied to all `/api/admin/*` endpoints

## Summary of Changes

This PR fixes all production blockers:

✅ **TASK A**: OpenAPI routing fixed (nginx can now serve `/api/openapi.json`)
✅ **TASK B**: Auth response standardized (`access_token` only, no duplicate `token`)
✅ **TASK C**: Frontend API base verified (no double `/api/api` bugs)
✅ **TASK D**: KuCoin form duplication removed, Bitget passphrase added
✅ **TASK E**: API key status mapping uses canonical statuses
✅ **TASK F**: Admin gating already implemented, all endpoints protected
✅ **TASK G**: Footer fixed (copyright only, build badge in admin view only)
✅ **TASK H**: Regression test script added (`scripts/verify_live.sh`)

All changes are minimal and surgical. No redesign. Dark glass UI preserved.
