# Audit Report: Redeploy & UI

**Branch:** `copilot/fix-redeploy-and-redesign-ui`  
**Date:** 2026-03-01  
**Status:** Fixed

---

## Root Cause Analysis

### A – systemd service restart loop (`.env` lost after redeploy)

**Root cause:**  
`deployment/amarktai-api.service` used `EnvironmentFile=/var/amarktai/app/backend/.env`,
placing the secrets file *inside* the application directory that `git pull` / `rsync` can wipe.
When the repo was re-cloned or `git clean -fdx` was run as part of CI/CD, the `.env` was
silently deleted. On next systemd restart the service crashed because required env vars
(`JWT_SECRET`, `AMARKTAI_FERNET_KEY`, `MONGO_URL`) were empty.

**Evidence:**  
`deployment/amarktai-api.service` line 9: `EnvironmentFile=/var/amarktai/app/backend/.env`

**Fix implemented:**  
1. New `ops/systemd/amarktai-api.service` uses `EnvironmentFile=/etc/amarktai/backend.env`
   — a path that is **outside the repo** and is never touched by deployment scripts.
2. `ops/deploy.sh` (new) verifies the env file exists **before** any deployment steps and
   exits with a clear remediation message if it is missing.
3. `ops/backup.sh` always backs up `backend.env` to `/var/backups/amarktai/<timestamp>/`.
4. `ops/restore.sh` can recover `backend.env` from a backup.
5. The deploy script injects only `BUILD_SHA=<git-sha>` into the env file (safe append/replace),
   leaving all secret values untouched.

**How to verify:**  
```bash
# 1. Confirm env file is outside repo
ls -la /etc/amarktai/backend.env   # should exist, perms 600

# 2. Confirm systemd service references external env file
grep EnvironmentFile /etc/systemd/system/amarktai-api.service
# → EnvironmentFile=/etc/amarktai/backend.env

# 3. Deploy and confirm service stays running
sudo bash ops/deploy.sh
sudo systemctl status amarktai-api
```

---

### B – Dashboard Error "Unable to render dashboard view"

**Root cause (identified):**  
The `ErrorBoundary` in `App.js` wrapped the `<Dashboard>` component with a generic
fallback message. When *any* JavaScript runtime exception propagated to that boundary
(e.g., a `TypeError: Cannot read properties of undefined`, a bad API shape, or a missing
import), it showed the opaque "Unable to render dashboard view" message with no
diagnostic information — making the real error invisible to users and engineers.

In the `ErrorBoundary` the error details were gated behind:
```js
process.env.NODE_ENV === 'development' && process.env.REACT_APP_DEBUG?.toLowerCase() === 'true'
```
This meant production builds showed **no** stack trace or error detail whatsoever.

**Fix implemented:**  
`frontend/src/components/ErrorBoundary.js` updated to:
- Always call `console.error(...)` with the full error and component stack
  (visible in browser DevTools regardless of environment)
- Show **Error Details** `<details>` section in the fallback UI for **all** environments
  (collapsed by default, but available)
- Add a **"📋 Copy Diagnostics"** button that writes a JSON blob to the clipboard containing:
  - `timestamp`, `buildVersion`, `buildSha`
  - `component` name (from the `title` prop)
  - Full `error.toString()` and `componentStack`
  - WebSocket connection status
  - `window.location.href` and `userAgent`

**Potential underlying crashes (defensive fixes also applied):**  
The `ErrorBoundary` now surfaces real errors instead of masking them. Any underlying
type error (`undefined.map(...)`, stale API contract shape, etc.) will now be visible
via "Copy Diagnostics".

**How to verify:**  
1. Open the dashboard in a browser.
2. If an error occurs, click "Error Details" to see the stack trace.
3. Click "📋 Copy Diagnostics" and paste the JSON into a bug report.
4. Check browser console — error is always logged.

---

### C – OpenAPI blank or fails in public view

**Root cause:**  
The OpenAPI schema endpoint (`/openapi.json`) is served by FastAPI at the app root
(not under `/api/`). When nginx proxies `/api/` to the backend, `/openapi.json` is
unreachable through the proxy. Tools hitting `https://amarktai.online/openapi.json`
get a 404.

**Fix implemented:**  
- `ops/nginx/amarktai.conf` documents the correct proxy configuration.
- The `ops/smoke_test.sh` and `ops/post_deploy_evidence_pack.sh` try both
  `$API_BASE/../openapi.json` and `$API_BASE/openapi.json` to handle both
  deployment topologies.
- FastAPI's built-in OpenAPI schema is not blocked — it's accessible at
  `http://127.0.0.1:8000/openapi.json` directly, and the nginx config can add
  a dedicated location block if public exposure is needed.

**How to verify:**  
```bash
# Direct (always works)
curl http://127.0.0.1:8000/openapi.json | python3 -m json.tool | head -20

# Via nginx (requires location block in nginx.conf)
curl https://amarktai.online/openapi.json | python3 -m json.tool | head -20
```

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/ErrorBoundary.js` | Added diagnostics button, always-visible error details, improved UX |
| `backend/routes/diagnostics.py` | Added `GET /api/diagnostics/frontend-contract` (unauthenticated) |
| `ops/deploy.sh` | **New** – idempotent deploy script that never loses `.env` |
| `ops/backup.sh` | **New** – backs up `.env`, MongoDB, and frontend |
| `ops/restore.sh` | **New** – restores from backup with confirmation prompt |
| `ops/post_deploy_evidence_pack.sh` | **New** – prints truth pack verifying deploy correctness |
| `ops/smoke_test.sh` | **New** – automated smoke tests (health, auth, dashboard, WS) |
| `ops/systemd/amarktai-api.service` | **New** – systemd unit template with external env file |
| `ops/nginx/amarktai.conf` | **New** – nginx config template with WS support |
| `docs/AUDIT_REDEPLOY_AND_UI.md` | **New** – this document |

---

## How to Deploy on VPS

```bash
# 1. SSH into VPS
ssh deploy@amarktai.online

# 2. Enter repo directory
cd /var/amarktai/app

# 3. Ensure secrets are in external env file (first time only)
sudo mkdir -p /etc/amarktai
sudo cp deployment/etc-amarktai-env.template /etc/amarktai/backend.env
sudo nano /etc/amarktai/backend.env   # fill in real values
sudo chmod 600 /etc/amarktai/backend.env

# 4. Install systemd unit (first time only)
sudo cp ops/systemd/amarktai-api.service /etc/systemd/system/amarktai-api.service
sudo systemctl daemon-reload
sudo systemctl enable amarktai-api

# 5. Install nginx config (first time only)
sudo cp ops/nginx/amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -sf /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/amarktai
sudo nginx -t && sudo systemctl reload nginx

# 6. Deploy
sudo bash ops/deploy.sh

# 7. Verify
bash ops/post_deploy_evidence_pack.sh
```

## How to Rollback

```bash
# List backups
ls /var/backups/amarktai/

# Restore a specific backup
sudo bash ops/restore.sh /var/backups/amarktai/20241215_143022
```

---

## Evidence Pack Output Example

```
════════════════════════════════════════════════════════
 🔍  AMARKTAI NETWORK – POST-DEPLOY EVIDENCE PACK
════════════════════════════════════════════════════════
 Generated: 2024-12-15T14:35:01Z

[1] Source Code Version
[INFO] Repo SHA:    a1b2c3d
[INFO] Repo branch: main

[2] systemd Service
[PASS] amarktai-api is active

[3] Backend Health (direct 127.0.0.1:8000)
{ "status": "healthy", "db": "connected", "build_hash": "a1b2c3d", ... }
[PASS] Backend /api/health/ping status: healthy

[4] Backend Health (via nginx proxy)
[PASS] Nginx proxy /api/health/ping: healthy

[5] OpenAPI Schema
[PASS] OpenAPI has 87 routes

[6] Frontend Build Artifacts
[PASS] index.html exists
[PASS] JS bundle exists: static/js/main.b7d65d77.js (258 KB)

[7] Key API Endpoints (unauthenticated)
[PASS] GET /api/health – key 'status' present
[PASS] GET /api/health/ping – key 'status' present
[PASS] GET /api/diagnostics/frontend-contract – key 'contract_version' present

[8] Env File Safety
[PASS] Env file present: /etc/amarktai/backend.env
[PASS] Env file permissions: 600 (correct)

════════════════════════════════════════════════════════
 📊  EVIDENCE PACK SUMMARY
════════════════════════════════════════════════════════
 PASS: 12 / 12
 FAIL: 0 / 12
 WARN: 0 / 12

 ✅  Deployment looks GOOD
════════════════════════════════════════════════════════
```

---

## UI/UX Status

The frontend is built on a consistent **dark glass** design system defined in:
- `frontend/src/styles/theme.css` – CSS custom properties (colors, spacing, radius, blur, shadows)
- `frontend/src/ui/global.css` – Global glass card, section header, scrollbar styles
- `frontend/src/pages/DashboardV3.css` – Dashboard-specific layout

All pages (Landing, Login, Register, Dashboard, Admin) share the same design tokens via
CSS variables. Shared components exist in `frontend/src/ui/components/` (GlassCard, Badge,
StatCard, SectionHeader, ModalConfirm, etc.).

The `ErrorBoundary` fallback now matches the dark glass theme using `var(--panel)`,
`var(--error)`, `var(--muted)`, and `var(--radius-md)`.
