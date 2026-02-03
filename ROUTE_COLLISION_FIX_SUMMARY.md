# Route Collision Fix Summary - PUT /api/system/mode

## Problem
Fatal route collision detected at server startup preventing the application from running.

**Duplicate Endpoints:**
- `routes/system_mode.py`: `@router.put("/mode")` mounted under `/api/system` → `PUT /api/system/mode`
- `server.py`: `@api_router.put("/system/mode")` → `PUT /api/system/mode`

**Error Message:**
```
ROUTE COLLISION DETECTED: PUT /api/system/mode
Previously registered at: update_system_mode
RuntimeError: Route collision detected - cannot start server
```

## Solution
Removed the duplicate endpoint from `server.py` (lines 692-753, 62 lines total) and kept the canonical implementation in `routes/system_mode.py`.

### Changes Made
**File:** `backend/server.py`
- **Removed:** Duplicate `@api_router.put("/system/mode")` endpoint function `update_system_mode()`
- **Added:** Documentation comment explaining removal and pointing to canonical implementation

### Why routes/system_mode.py is Canonical
The `routes/system_mode.py` implementation is more comprehensive:
- ✅ Live readiness checks (7-day paper trading requirement)
- ✅ Luno balance validation (minimum R500)
- ✅ User eligibility validation
- ✅ Proper real-time event broadcasting via `rt_events.mode_switched()`
- ✅ Auto-revert to paper mode with email notification if balance insufficient
- ✅ Per-user mode management
- ✅ Mutual exclusivity enforcement (paper vs live)

The `server.py` version had:
- Basic mutual exclusivity
- Bot promotion logic (better handled by schedulers)
- Older WebSocket manager (direct `manager.send_message`)

## Verification

### 1. Route Collision Check ✅
```
✅ Route collision check passed - 363 unique routes registered
```

### 2. Endpoint Verification ✅
```
PUT /api/system/mode                     -> toggle_mode
```
Exactly ONE PUT endpoint exists, handled by `toggle_mode` from `routes/system_mode.py`

### 3. Server Import ✅
Server module imports successfully without RuntimeError

### 4. All System Mode Routes Present ✅
- `GET /api/system/mode` → get_mode
- `PUT /api/system/mode` → toggle_mode (canonical)
- `POST /api/system/mode/switch` → switch_mode
- `GET /api/system/mode/readiness` → check_readiness

## Testing
The repository already has route collision detection:
1. **Runtime check** in `server.py` (lines 3063-3095) - raises RuntimeError if collisions detected
2. **Unit test** in `tests/test_route_collisions.py` - CI/CD test to prevent future collisions

## Impact
- ✅ Server starts successfully
- ✅ No route collisions
- ✅ PUT /api/system/mode works with full functionality
- ✅ Frontend/backend alignment maintained
- ✅ CI/CD will catch future collisions

## Files Modified
- `backend/server.py` (-62 lines, +4 lines documentation)

## Acceptance Criteria Met
- [x] No ROUTE COLLISION DETECTED logs
- [x] Server imports without RuntimeError
- [x] PUT /api/system/mode exists exactly once
- [x] Canonical endpoint has comprehensive functionality
- [x] Existing collision detection test prevents future issues
