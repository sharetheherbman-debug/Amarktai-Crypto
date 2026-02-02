# VPS Verification Guide

## Overview
This guide provides commands to verify the fixes for route collisions and 7-exchange enforcement on your Ubuntu 24.04 Webdock VPS.

## Prerequisites
- Backend FastAPI/Uvicorn running via systemd `amarktai-api` service
- Service should bind to 127.0.0.1:8000

## Step 1: Start the Service

```bash
# Start the amarktai-api service
sudo systemctl start amarktai-api

# Check service status
sudo systemctl status amarktai-api

# If there are issues, check logs
sudo journalctl -u amarktai-api -f
```

**Expected Result:** Service should start successfully without "Route collision detected" error.

## Step 2: Verify Health & System Endpoints

```bash
# Test basic health endpoint
curl http://127.0.0.1:8000/api/health/ping

# Test system status endpoint (canonical)
curl http://127.0.0.1:8000/api/system/status

# Test emergency gates endpoint (renamed to avoid collision)
curl http://127.0.0.1:8000/api/system/emergency-gates
```

**Expected Results:**
- `/api/health/ping` should return 200 with "pong" message
- `/api/system/status` should return system status with feature flags
- `/api/system/emergency-gates` should return emergency stop gates status

## Step 3: Verify Platform Configuration

```bash
# Test platforms endpoint returns exactly 7 exchanges
curl http://127.0.0.1:8000/api/platforms | jq '.total_count'

# List all platform IDs
curl http://127.0.0.1:8000/api/platforms | jq '.platforms[].id'

# Verify specific platforms exist
curl http://127.0.0.1:8000/api/platforms | jq '.platforms[].id' | grep -E "(luno|binance|kucoin|bybit|kraken|bitget|gate)"
```

**Expected Results:**
- `total_count` should be 7
- Platform IDs should include: luno, binance, kucoin, bybit, kraken, bitget, gate
- VALR and OVEX should NOT appear

## Step 4: Verify Wallet Transfers Endpoint

```bash
# Test wallet transfers endpoint (enhanced version, canonical)
# Note: This requires authentication, so you may get 401 without token
curl -i http://127.0.0.1:8000/api/wallet/transfers
```

**Expected Result:** Should return either 401 (needs auth) or 200 (if public). Should NOT return 404.

## Step 5: Run Smoke Tests

```bash
# Run the comprehensive smoke test
cd /path/to/repo
bash tools/smoke_test.sh

# Run go-live verification script
bash scripts/verify_go_live.sh

# Run go-live smoke test
bash scripts/go_live_smoke.sh
```

**Expected Results:**
- All scripts should run without bash syntax errors
- Scripts should check for exactly 7 exchanges
- Scripts should pass when Kraken is present (it's required)

## Step 6: Run Backend Tests (Optional)

If you have Python environment set up:

```bash
cd /path/to/repo/backend

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Run the new automated test
python3 tests/test_route_uniqueness_and_platforms.py

# Or with pytest
pytest tests/test_route_uniqueness_and_platforms.py -v
```

**Expected Results:**
- All tests should pass
- Route uniqueness check should pass
- Platform count check should pass (7 exchanges)
- VALR/OVEX exclusion check should pass

## Verification Checklist

- [ ] Service starts without "Route collision detected" error
- [ ] `curl http://127.0.0.1:8000/api/health/ping` returns 200
- [ ] `curl http://127.0.0.1:8000/api/system/status` returns 200
- [ ] `curl http://127.0.0.1:8000/api/system/emergency-gates` returns 200
- [ ] `curl http://127.0.0.1:8000/api/platforms` returns exactly 7 platforms
- [ ] Platform list includes all 7: luno, binance, kucoin, bybit, kraken, bitget, gate
- [ ] Platform list does NOT include valr or ovex
- [ ] `bash -n scripts/*.sh` passes without syntax errors
- [ ] `bash -n tools/*.sh` passes without syntax errors
- [ ] Smoke tests pass and check for 7 exchanges

## Troubleshooting

### Service Won't Start
```bash
# Check for Python syntax errors
cd backend
python3 -m py_compile server.py

# Check specific error in logs
sudo journalctl -u amarktai-api -n 50
```

### Route Collision Still Occurring
```bash
# Search for duplicate route definitions
cd backend
grep -r "@router.get(\"/status\")" routes/
grep -r "@router.get(\"/transfers\")" routes/
```

### Wrong Number of Platforms
```bash
# Check canonical platform source
cat backend/config/platforms.py | grep "SUPPORTED_PLATFORMS ="

# Check if modules import from canonical source
grep -r "from config.platforms import" backend/
```

## Success Criteria

✅ All items in the verification checklist should be complete
✅ Server runs without route collisions
✅ Exactly 7 exchanges supported everywhere
✅ All scripts pass syntax checks and logic tests
✅ Automated tests catch future issues
