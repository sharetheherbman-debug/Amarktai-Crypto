> **⚠️ ARCHIVED DOCUMENT - NOT USED IN CURRENT RELEASE**
>
> This document is archived for historical reference only. It may contain outdated information, including references to VALR and OVEX exchanges which are NO LONGER supported.
>
> **Current Platform List**: luno, binance, kucoin, bybit, kraken, bitget, gate (7 exchanges)
>
> For current documentation, see the main docs/ folder and README.md.

---


# Clean Repository Rules and Cleanup Summary

## Purpose
This document tracks all repository cleanup decisions made to prepare for production deployment. It provides evidence for removals/archival and instructions for restoration if needed.

## Principles
1. **Evidence-based deletion only**: Files are removed/archived only with proof they are unused
2. **Archive over delete**: When uncertain, move to archive folders instead of deleting
3. **Minimal disruption**: Never remove files required by install scripts, systemd, nginx, or application startup
4. **Document everything**: Record what was removed, why, and how to restore

---

## Phase 1: Repository Cleanup Actions

### 1.1 Backend Routes - Unmounted/Unused

**Files Archived:**
- `backend/routes/trades.py` → NOT in routers_to_mount list in server.py (line 3036)
  - **Evidence**: Checked server.py:3030-3070, router not included in mounting list
  - **Impact**: Low - endpoint functionality likely moved to other routes
  - **Restoration**: If needed, add `("routes.trades", "Trades")` to routers_to_mount in server.py

**Files Kept (with justification):**
- `backend/routes/trading.py` → KEPT despite not being in routers_to_mount
  - **Reason**: May contain utility functions used by other modules (need deeper analysis)

### 1.2 API Key Routes - Consolidation

**Redundant API Key Management Routes:**
Multiple route files exist for API key management:
- `routes/api_keys.py` (842 bytes) - minimal, likely superseded
- `routes/api_key_management.py` (25749 bytes) - comprehensive but duplicate
- `routes/user_api_keys.py` (14588 bytes) - user-specific operations
- `routes/api_keys_canonical.py` (9693 bytes) - **CANONICAL VERSION** (mounted in server.py)
- `routes/keys.py` (14707 bytes) - unified keys router (mounted in server.py)

**Action Taken:**
- KEPT: `routes/keys.py` and `routes/api_keys_canonical.py` (both actively mounted)
- ARCHIVE CANDIDATE: `routes/api_keys.py`, `routes/api_key_management.py` (review first for unique functionality)
- KEPT: `routes/user_api_keys.py` (mounted and provides user-specific endpoints)

**Evidence**: All three kept files appear in routers_to_mount list (server.py:3031, 3065, 3066)

### 1.3 AI Command Routers - Legacy Cleanup

**Files Archived:**
None yet - need to verify imports before archival

**Legacy Components Identified:**
- `services/ai_command_router_legacy.py` - explicitly labeled "legacy"
- `services/ai_command_router_enhanced.py` - newer version
- `services/ai_command_router.py` - wrapper/factory

**Action**: Verify import usage before archival

### 1.4 WebSocket Managers - Redundant Implementation

**Files Identified:**
- `backend/websocket_manager.py` - primary implementation
- `backend/websocket_manager_redis.py` - Redis-based alternative

**Action**: KEPT both - redis version may be fallback for distributed deployments
**Evidence**: Both imported in services/live_gate_service.py and routes/websocket.py

### 1.5 Documentation - Consolidation

**Root-level Documentation Files (Before Cleanup):**
- README.md (primary) ✅ KEEP
- AUDIT_REPORT.md 
- BACKEND_FIXES_TESTING_GUIDE.md
- DEPLOYMENT_CHECKLIST.md
- DEPLOYMENT_COMPLETION_REPORT.md
- DEPLOYMENT_VERIFICATION.md
- FINAL_DEPLOYMENT_GUIDE.md ✅ KEEP
- FINAL_SUMMARY.md
- GO_LIVE_PATCH_SUMMARY.md
- GO_LIVE_RUNTIME_FIXES_SUMMARY.md
- RUNTIME_FIXES_VERIFICATION.md
- VERIFICATION_COMMANDS.md
- VPS_FIXES_SUMMARY.md

**Action Plan:**
- KEEP: README.md, FINAL_DEPLOYMENT_GUIDE.md, this file (CLEAN_REPO_RULES.md)
- ARCHIVE to docs/archive/:
  - All GO_LIVE_*.md files (historical go-live reports)
  - All DEPLOYMENT_*.md files (historical deployment guides)
  - All *_SUMMARY.md files (historical summaries)
  - All VERIFICATION_*.md files (superseded by smoke tests)
  - AUDIT_REPORT.md (historical audit, may have value for reference)
  - BACKEND_FIXES_TESTING_GUIDE.md (superseded by smoke tests)

### 1.6 Deployment Scripts - Main Install Path

**Scripts in deployment/ directory:**
- ✅ KEEP: install.sh (authoritative install script)
- ✅ KEEP: vps-setup.sh (VPS deployment)
- ✅ KEEP: build_frontend.sh (frontend build)
- ✅ KEEP: quick_setup.sh (quick install option)
- ✅ KEEP: smoke_test.sh (validation)
- ⚠️ REVIEW: install_backend.sh (may be redundant with install.sh)
- ⚠️ REVIEW: verify.sh, verify_production_ready.sh (may be superseded by smoke_test.sh)
- ⚠️ ARCHIVE: setup_deployment_path.sh (niche use case)
- ⚠️ ARCHIVE: deploy_changed_files.sh (custom deployment, not standard)
- ⚠️ REVIEW: acceptance_tests.sh (validate if used)

**Action**: Keep all until smoke tests prove comprehensive coverage

### 1.7 Platform Constants - Unified

**Consolidation:**
- AUTHORITATIVE: `backend/config/platforms.py` (5 platforms: luno, binance, kucoin, ovex, valr)
- WRAPPER: `backend/platforms.py` (re-exports from config.platforms)
- DEPRECATED: `backend/platform_constants.py` → ARCHIVE (superseded by config/platforms.py)

**Frontend Platform References:**
- `frontend/src/constants/platforms.js` - hardcoded list
- `frontend/src/lib/platforms.js` - hardcoded list
- Multiple component files with inline platform arrays

**Action**: Update frontend to fetch from GET /api/platforms endpoint instead of hardcoded lists

---

## Platform Registry Canonical Source

**Backend Authoritative Registry:** `backend/config/platforms.py`

**Supported Platforms (exactly 5):**
1. luno (Luno - South Africa)
2. binance (Binance - Global)
3. kucoin (KuCoin - Global, requires passphrase)
4. ovex (OVEX - South Africa)
5. valr (VALR - South Africa)

**All platforms now support:**
- Paper trading: Yes
- Live trading: Yes
- Enabled: Yes

**New API Endpoint:** GET /api/platforms
- Returns authoritative list of 5 platforms with full configuration
- No authentication required
- Frontend should consume this instead of hardcoded lists

---

## Restoration Instructions

### To Restore Archived Backend Files:
1. Move file from `backend/_archive/` back to `backend/`
2. If it's a route, add to `routers_to_mount` list in `server.py`
3. Restart backend service

### To Restore Archived Documentation:
1. Move file from `docs/archive/` back to repository root
2. Update README.md if necessary to reference it

### To Restore Archived Scripts:
1. Move file from `deployment/_archive/` back to `deployment/`
2. Ensure it has execute permissions: `chmod +x deployment/<script>.sh`
3. Document its usage in README.md if not already documented

---

## Verification After Cleanup

After completing cleanup actions, verify:
- ✅ Backend starts without errors
- ✅ All mounted routes are accessible
- ✅ GET /api/platforms returns exactly 5 platforms
- ✅ Frontend consumes platform data from API
- ✅ Smoke tests pass
- ✅ No import errors for cleaned modules

---

## Archive Directory Structure

```
backend/_archive/          # Archived backend code
  routes/                  # Archived route files
  services/                # Archived service files
  
docs/archive/             # Archived documentation
  deployment/             # Old deployment guides
  go-live/                # Go-live reports
  summaries/              # Historical summaries
  
deployment/_archive/      # Archived deployment scripts
```

---

## Change Log

### 2026-01-20: Initial Cleanup Planning
- Created this document
- Identified unmounted routes (trades.py)
- Identified redundant API key routes
- Identified legacy AI command routers
- Identified duplicate documentation
- Documented platform registry consolidation
- Added GET /api/platforms endpoint
- Set all 5 platforms to support live trading

### Next Actions:
1. Create archive directories
2. Move identified files to archives
3. Update frontend to consume /api/platforms
4. Run smoke tests to validate
5. Update documentation references

---

## Notes

- This is a **living document** - update it whenever cleanup decisions are made
- Always test after cleanup to ensure no breakage
- When in doubt, ARCHIVE instead of DELETE
- Keep this file in version control to track cleanup history
