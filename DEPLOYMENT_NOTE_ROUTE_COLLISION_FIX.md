# Deployment Note: Route Collision Fix

## Date: 2026-02-05

## Issue Fixed
Fixed fatal route collision error preventing backend from starting:
- **Route collision**: `DELETE /api/api-keys/{provider}` was registered twice
- Server would crash on startup with RuntimeError

## Changes Made

### 1. Removed Duplicate API Key Endpoints (server.py)
Removed ALL inline API key endpoints from `server.py` to maintain "one truth" architecture:

**Removed routes:**
- `GET    /api-keys` 
- `POST   /api-keys`
- `POST   /api-keys/{provider}/test`
- `DELETE /api-keys/{provider}`

**Why:** These were duplicates causing collisions and confusion. All functionality is now in dedicated routers.

### 2. API Key Architecture (Clean)

**Canonical routes** (new code should use these):
- Location: `routes/keys.py`
- Prefix: `/api/keys/*`
- Examples:
  - `GET  /api/keys/list`
  - `POST /api/keys/save`
  - `POST /api/keys/test`
  - `DELETE /api/keys/{provider}`

**Legacy compatibility routes** (for old frontend code):
- Location: `routes/compat.py`
- Prefix: `/api/api-keys/*`
- Proxies to canonical routes in `routes/keys.py`
- Will be phased out eventually

### 3. Enhanced Collision Detection
Improved error messages to show both locations (module:function) when collisions occur.

### 4. Permission Hardening Scripts
Created two new scripts to prevent `.venv` permission issues:

**`scripts/fix_perms.sh`**
- Fixes permissions after recursive chmod/chown
- Sets code directories to 755, files to 644
- Ensures `.venv/bin/*` executables remain 755
- Can set ownership to www-data (if run with sudo)

**`scripts/bootstrap_backend.sh`**
- Creates virtual environment
- Installs dependencies
- Runs syntax checks
- Runs route collision test
- Fixes permissions

## If You Previously Ran Recursive chmod/chown

If your deployment broke with "Permission denied" errors on pip or other executables:

```bash
# Run the permission fix script
sudo ./scripts/fix_perms.sh

# OR re-bootstrap the entire backend
./scripts/bootstrap_backend.sh
```

## Deployment Checklist

After pulling this update:

1. **Update code**:
   ```bash
   cd /home/amarktai/Amarktai-Network---Deployment
   git pull origin main
   ```

2. **Fix permissions** (if needed):
   ```bash
   sudo ./scripts/fix_perms.sh
   ```

3. **Restart service**:
   ```bash
   sudo systemctl restart amarktai-api
   ```

4. **Verify**:
   ```bash
   # Check service is running
   sudo systemctl status amarktai-api
   
   # Check server is listening
   ss -lntp | grep :8000
   
   # Test health endpoint
   curl -sS http://127.0.0.1:8000/api/health/ping
   ```

Expected results:
- ✅ Service status: `active (running)`
- ✅ Port 8000 listening
- ✅ Health check returns 200 OK
- ✅ No "ROUTE COLLISION" errors in logs

## Testing Route Collisions

To run the route collision test manually:

```bash
cd /home/amarktai/Amarktai-Network---Deployment
source backend/.venv/bin/activate
pytest -q tests/test_route_collisions.py
```

## Breaking Changes

**None for properly written code.**

The removed inline endpoints in `server.py` were:
- Not used by the current frontend (confirmed by code inspection)
- Duplicates of routes in `routes/keys.py`
- Causing route collisions

If you have any custom scripts or external integrations calling:
- `GET /api/api-keys` → Use `GET /api/keys/list` instead
- `POST /api/api-keys` → Use `POST /api/keys/save` instead
- `DELETE /api/api-keys/{provider}` → Use `DELETE /api/keys/{provider}` instead

Or use the legacy compat endpoints which are still available:
- `GET /api/api-keys/list`
- `POST /api/api-keys/save`
- `POST /api/api-keys/test`
- `DELETE /api/api-keys/{provider}`

## Files Changed
- `backend/server.py` - Removed duplicate API key endpoints, enhanced collision detection
- `scripts/fix_perms.sh` - New: Permission hardening script
- `scripts/bootstrap_backend.sh` - New: Backend setup and verification script
- `DEPLOYMENT_NOTE_ROUTE_COLLISION_FIX.md` - This file

## Support

If you encounter any issues after this update:

1. Check logs: `sudo journalctl -u amarktai-api -f`
2. Run permission fix: `sudo ./scripts/fix_perms.sh`
3. Verify route collision test passes: `pytest tests/test_route_collisions.py`

## Success Metrics

After deployment, verify:
- [ ] Server starts without route collision errors
- [ ] Service remains active (no crash loop)
- [ ] Port 8000 is listening
- [ ] Health check returns 200
- [ ] Frontend API key management works
- [ ] No "ROUTE COLLISION DETECTED" in logs
