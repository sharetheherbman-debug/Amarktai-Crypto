# Production Fixes Test Suite

Automated test suite for verifying all production fixes are working correctly.

## Quick Start

### Prerequisites
- Backend server running (localhost:8000 or custom URL)
- Python 3.8+
- `aiohttp` library installed

### Install Dependencies
```bash
pip install aiohttp
```

### Run Tests
```bash
# Default (localhost:8000)
python tests/test_production_fixes.py

# Custom API URL
API_BASE=https://api.amarktai.online python tests/test_production_fixes.py

# With custom test credentials
TEST_EMAIL=test@example.com TEST_PASSWORD=testpass123 python tests/test_production_fixes.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE` | `http://localhost:8000` | Backend API URL |
| `TEST_EMAIL` | `test@example.com` | Test user email |
| `TEST_PASSWORD` | `testpass123` | Test user password |

## Test Coverage

The test suite validates:

### ✅ Security Tests
1. **Login Security** - Verifies no password hashes in login response
2. **Register Security** - Verifies no sensitive fields in register response
3. **Profile Security** - Verifies forbidden fields cannot be updated

### ✅ Endpoint Availability Tests
4. **Wallet Requirements** - Verifies endpoint returns 200 (not 500)
5. **Emergency Stop** - Verifies activation/deactivation works
6. **AI Insights** - Verifies new endpoint is accessible
7. **ML Predict** - Verifies query param compatibility
8. **Profits Reinvest** - Verifies reinvestment endpoint works
9. **Advanced Decisions** - Verifies decision trace endpoint works

### ✅ API Compatibility Tests
10. **OpenAI Key Test** - Verifies uses openai>=1.x (not deprecated API)
11. **OpenAPI Schema** - Verifies new endpoints in schema

## Expected Output

```
============================================================
Production Fixes Verification Test Suite
============================================================

=== Authentication Test ===
✅ Login successful - no sensitive fields in response

=== Profile Update Test ===
✅ Profile update successful
✅ Forbidden fields properly rejected

=== Wallet Requirements Test ===
✅ Wallet requirements endpoint working

=== Emergency Stop Test ===
✅ Emergency stop activated
✅ Emergency stop deactivated

=== OpenAI Key Test ===
✅ OpenAI key test using new API (openai>=1.x)

=== AI Insights Test ===
✅ AI insights endpoint working

=== ML Predict (Query Params) Test ===
✅ ML predict endpoint working with query params

=== Profits Reinvest Test ===
✅ Profits reinvest endpoint working

=== Advanced Decisions Recent Test ===
✅ Advanced decisions endpoint working

=== OpenAPI Schema Test ===
✅ All new endpoints in OpenAPI schema

============================================================
Test Summary
============================================================
✅ Passed: 11
❌ Failed: 0
⚠️  Warnings: 0
============================================================
```

## Exit Codes

- `0` - All tests passed (or only warnings)
- `1` - One or more tests failed

## Troubleshooting

### Backend Not Running
```
❌ Login error: Cannot connect to host localhost:8000
```
**Solution:** Start the backend server first
```bash
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Authentication Failed
```
❌ Login failed, trying to register...
❌ Register failed (403): Invalid invite code
```
**Solution:** Set or disable invite code
```bash
# Option 1: Disable invite code in .env
INVITE_CODE=

# Option 2: Set invite code
INVITE_CODE=your-code python tests/test_production_fixes.py
```

### Connection Refused
```
❌ Login error: [Errno 111] Connect call failed
```
**Solutions:**
1. Check backend is running: `curl http://localhost:8000/api/health`
2. Check firewall allows port 8000
3. Try different port: `API_BASE=http://localhost:8001 python tests/test_production_fixes.py`

### Test User Already Exists
This is normal. The script will use the existing user for testing.

## Manual Testing

If you prefer manual testing, use these curl commands:

### Test Security (No Password Hashes)
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' \
  | grep -i password_hash

# Should return nothing (no password_hash in response)
```

### Test New Endpoints
```bash
# Get auth token first
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' \
  | jq -r .access_token)

# AI Insights
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/ai/insights

# ML Predict
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/ml/predict?symbol=BTC-ZAR&platform=luno"

# Profits Reinvest
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/profits/reinvest

# Advanced Decisions
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/advanced/decisions/recent?limit=10"
```

### Test Fixed Endpoints
```bash
# Emergency Stop (should not 500)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/system/emergency-stop?reason=Test"

# Wallet Requirements (should not 500)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/wallet/requirements

# Profile Update (should validate)
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Test User"}' \
  http://localhost:8000/api/auth/profile
```

## Continuous Integration

To use in CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Production Fixes Tests
  run: |
    python tests/test_production_fixes.py
  env:
    API_BASE: http://localhost:8000
    TEST_EMAIL: ci-test@example.com
    TEST_PASSWORD: ci-test-pass
```

## Contributing

When adding new tests:

1. Add test method to `ProductionFixesTest` class
2. Follow naming convention: `test_<feature_name>`
3. Use appropriate assertions:
   - `self.passed += 1` for success
   - `self.failed += 1` for failure
   - `self.warnings += 1` for non-critical issues
4. Print clear status messages with color codes
5. Update this README

## Support

For issues with the test suite:
1. Check backend logs for errors
2. Verify environment variables are set correctly
3. Try manual testing with curl commands
4. Review `PRODUCTION_FIXES_ENDPOINTS.md` for endpoint details

---

**Last Updated:** 2026-01-17  
**Test Suite Version:** 1.0
