# AUDIT REPORT

## Frontend routes/components calling backend endpoints

### Landing/Login/Register/Dashboard flows (observed)
- `frontend/src/pages/Login.js` -> `POST /api/auth/login`
- `frontend/src/pages/Register.js` -> `POST /api/auth/register`
- `frontend/src/pages/Dashboard.js` ->
  - `GET /api/system/mode`
  - `PUT /api/system/mode`
  - `POST /api/system/paper-reset`
  - `POST /api/system/paper-reset/validate`
  - `GET /api/system/status`
  - `GET /api/risk/status`
  - `GET /api/keys/status`
  - `POST /api/system/emergency-stop`
  - `GET /api/admin/users`
  - `GET /api/admin/bots`
  - `GET /api/admin/system-stats`
  - `GET /api/admin/emergency-stop/status`
  - `POST /api/admin/emergency-stop/global`
  - `POST /api/admin/emergency-stop/user`
  - `POST /api/admin/emergency-stop/clear-user`

## Backend endpoints existing but unused/broken (audit scope)
- `GET /api/system/emergency-gates`: existed, now updated to include override-aware emergency state.
- `GET /api/risk/status`: existed, but bot projection missed `id` and lacked explicit bodyguard summary fields.

## Endpoint mismatches found
- Risk status payload lacked explicit `bodyguard_active`, `bodyguard_reason`, and per-bot status map required for dashboard clarity.
- Emergency-stop status evaluated raw `emergencyStop` only; admin override semantics were not applied.
- Trading mode normalization was duplicated (`mode` vs `trading_mode`) across bodyguard/quarantine/scheduler paths.

## Runtime errors reproducible locally
- `python -m pytest -q --maxfail=25 --disable-warnings` -> `/usr/bin/python: No module named pytest`
- `npm run build` (frontend) -> `sh: 1: craco: not found`

## Checklist of implemented changes
- [x] Added centralized trading mode normalization utility and wired it into bodyguard/quarantine/scheduler paths. **Fixed ✅**
- [x] Added bodyguard warmup guardrails (`MIN_TRADES_FOR_BODYGUARD`, `BODYGUARD_MIN_RUNTIME_SECONDS`) and breach streak env alias support (`BODYGUARD_BREACH_STREAK`). **Fixed ✅**
- [x] Added configurable paper/live quarantine first-duration defaults for retry-friendly paper mode. **Fixed ✅**
- [x] Enhanced `/api/risk/status` with explicit bodyguard fields and per-bot risk status payload. **Fixed ✅**
- [x] Implemented admin emergency-stop override storage/service and admin endpoints:
  - `GET /api/admin/emergency-stop/status`
  - `POST /api/admin/emergency-stop/global`
  - `POST /api/admin/emergency-stop/user`
  - `POST /api/admin/emergency-stop/clear-user`
  **Fixed ✅**
- [x] Applied emergency override evaluation to emergency stop status/gates responses. **Fixed ✅**
- [x] Added admin-only frontend Emergency Stop Overrides panel in Dashboard admin section (hidden behind existing admin unlock). **Fixed ✅**
- [x] Updated footer copy casing to exact required phrase segment: `Part of Amarktai Network`. **Fixed ✅**
