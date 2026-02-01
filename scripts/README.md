# Production Verification Scripts

This directory contains scripts to verify the production readiness of the Amarktai Network trading system.

## Scripts Overview

### 1. verify_production_ready.py

**Purpose:** Comprehensive production readiness verification before go-live

**What it checks:**
- Server is running and reachable
- Health endpoint returns 200
- OpenAPI spec includes all required endpoints
- User registration and login work correctly
- JWT tokens are properly minted and validated
- Protected endpoints require authentication (return 401/403)
- API key save endpoint works with authentication
- API key test endpoint is mounted and secured
- Price endpoint doesn't crash when API keys are missing
- ML prediction endpoint is mounted

**Usage:**
```bash
# Default (localhost:8001)
python3 scripts/verify_production_ready.py

# Custom backend URL
python3 scripts/verify_production_ready.py http://localhost:8001

# Production server
BACKEND_URL=http://prod:8001 python3 scripts/verify_production_ready.py
```

**Expected output:**
```
==================================================================
PRODUCTION READINESS VERIFICATION
==================================================================
Backend: http://localhost:8001
Time: 2026-01-18T10:00:00.000000

🔍 Running tests...

✅ Server is running
✅ Health endpoint returns 200
✅ OpenAPI includes required endpoints
✅ Auth registration and login work
✅ Token can access protected endpoint
✅ Protected endpoints return 401 without token
✅ API keys save requires auth
✅ API keys save works with token
✅ API keys test endpoint exists
✅ Prices endpoint doesn't crash without keys
✅ ML predict endpoint is mounted

==================================================================
RESULTS
==================================================================
✅ PASS Server is running
✅ PASS Health endpoint returns 200
...

==================================================================

📊 11/11 tests passed

🎉 ALL CHECKS PASSED - Production Ready!

✅ System is ready for PAPER trading with:
   - Rock-solid auth with backward compatibility
   - JWT tokens working correctly
   - API key save/test endpoints functional
   - Price endpoint resilient to missing keys
   - All protected endpoints properly secured
```

**Exit codes:**
- `0` - All checks passed
- `1` - One or more checks failed

---

### 2. verify_go_live.py

**Purpose:** Quick verification that all required endpoints are mounted and respond correctly

**What it checks:**
- OpenAPI spec includes required endpoints
- Protected endpoints return 401/403 (not 404)
- Public health endpoint returns 200

**Usage:**
```bash
# Default (localhost:8001)
python3 scripts/verify_go_live.py

# Custom backend URL
python3 scripts/verify_go_live.py http://localhost:8001

# Production server
BACKEND_URL=http://prod:8001 python3 scripts/verify_go_live.py
```

**Expected output:**
```
==============================================================
Production Go-Live Verification
==============================================================
Backend: http://localhost:8001

✅ Server is running

=== OpenAPI Spec Check ===
✅ GET /api/health/ping
✅ POST /api/auth/login
✅ GET /api/auth/me
✅ POST /api/api-keys
✅ POST /api/api-keys/{provider}/test
✅ GET /api/ml/predict/{pair}
✅ GET /api/bots
✅ GET /api/profits

✅ All 8 required endpoints in OpenAPI

=== Auth Protection Check ===
✅ GET /api/auth/me → 401 (protected)
✅ POST /api/api-keys → 401 (protected)
✅ GET /api/bots → 401 (protected)
✅ GET /api/profits → 401 (protected)
✅ POST /api/api-keys/luno/test → 401 (protected)

=== Public Endpoints Check ===
✅ /api/health/ping → 200

==============================================================
RESULTS
==============================================================
✅ PASS OpenAPI Spec
✅ PASS Auth Protection
✅ PASS Public Endpoints
==============================================================

🎉 ALL CHECKS PASSED - Production Ready
```

**Exit codes:**
- `0` - All checks passed
- `1` - One or more checks failed

---

### 3. verify_auth_contract.py

**Purpose:** Verify auth contract with backward compatibility (requires running MongoDB)

**What it checks:**
- Registration with different password field variations
- Login returns consistent token structure
- Profile endpoints exclude sensitive fields
- Invite code handling

**Usage:**
```bash
# Requires MongoDB running
cd backend
python3 ../scripts/verify_auth_contract.py
```

---

## Deployment Workflow

### Pre-Deployment Verification

1. **Before deploying to production:**
   ```bash
   # Start backend locally
   cd backend
   uvicorn server:app --host 0.0.0.0 --port 8001
   
   # In another terminal, run verification
   python3 scripts/verify_production_ready.py
   ```

2. **Fix any failures** before proceeding with deployment

### Post-Deployment Verification

3. **After deploying to production:**
   ```bash
   # Verify production server
   python3 scripts/verify_production_ready.py https://your-domain.com
   
   # Quick endpoint check
   python3 scripts/verify_go_live.py https://your-domain.com
   ```

### CI/CD Integration

Add to your CI/CD pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Verify Production Readiness
  run: |
    python3 scripts/verify_production_ready.py
  env:
    BACKEND_URL: http://localhost:8001
```

---

## Troubleshooting

### "Server not reachable"
- Ensure backend is running: `curl http://localhost:8001/api/health/ping`
- Check firewall rules
- Verify correct port in URL

### "Missing endpoints"
- Check that all router modules are properly mounted in server.py
- Verify OpenAPI spec: `curl http://localhost:8001/openapi.json`

### "Authentication failures"
- Verify JWT_SECRET is set in .env
- Check database connection
- Ensure MongoDB is running

### "API key endpoints failing"
- Verify routes/api_keys_canonical.py is mounted
- Check database collections exist
- Verify user authentication works

---

## Environment Variables

These scripts respect the following environment variables:

- `BACKEND_URL` - Backend server URL (default: http://localhost:8001)
- `INVITE_CODE` - Invite code for registration tests (optional)

---

## Development

To modify these scripts:

1. Update the test functions in the script
2. Test locally with a running backend
3. Update this README with any new checks or requirements
4. Ensure exit codes are correct (0 for success, 1 for failure)

---

## Support

For issues with these scripts:
1. Check the backend logs: `journalctl -u amarktai-backend -f`
2. Verify MongoDB is running: `sudo systemctl status mongod`
3. Test individual endpoints manually with curl
4. Review the script output for specific error messages

---

**Last Updated:** 2026-01-18

---

## 🔍 Audit & Compliance Tools (Added 2026-02-01)

### audit_repo.py
**Purpose:** Comprehensive repository scanner and analyzer

**What it does:**
- Scans all backend routers and endpoints
- Detects supported exchanges
- Finds TODO/FIXME markers
- Checks for VALR/OVEX references
- Identifies removed features
- Detects potential ToS violations

**Usage:**
```bash
python3 scripts/audit_repo.py
```

**Outputs:**
- `audit_report.json` - Machine-readable audit data
- `docs/CURRENT_STATE.md` - Human-readable current state
- `docs/API_CONTRACT.md` - Backend/frontend API contract

---

### run_audit.sh
**Purpose:** Wrapper script to run audit_repo.py

**Usage:**
```bash
./scripts/run_audit.sh
```

---

### compliance_checks.sh
**Purpose:** Automated compliance verification

**What it checks:**
- ✅ No VALR/OVEX references in active code
- ✅ No removed features (walk-forward, Monte Carlo, etc.)
- ✅ No ToS-breaking keywords (proxy rotation, wash trading, etc.)
- ✅ Exactly 7 exchanges configured

**Usage:**
```bash
./scripts/compliance_checks.sh
```

---

### preflight.sh (Enhanced)
**Purpose:** Pre-deployment validation and environment check

**What it checks:**
- Python 3.8+ and Node.js 16+ installed
- MongoDB accessible
- Required packages installed
- Environment variables configured
- Exchange registry (exactly 7 exchanges)
- No VALR/OVEX references
- Backend Python files compile

**Usage:**
```bash
./scripts/preflight.sh
```

---

## �� Additional Documentation (Added 2026-02-01)

- **Production Summary:** `docs/PRODUCTION_PERFECT_SUMMARY.md` - Executive summary
- **Implementation Status:** `docs/IMPLEMENTATION_STATUS.md` - Current state
- **Wallet Implementation:** `docs/WALLET_IMPLEMENTATION_GUIDE.md` - Wallet roadmap
- **Current State:** `docs/CURRENT_STATE.md` - Generated audit output
- **API Contract:** `docs/API_CONTRACT.md` - Endpoint documentation

---

**Last Updated:** 2026-02-01
