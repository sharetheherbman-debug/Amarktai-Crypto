# Repo Truth — Amarktai Network Canonical Source

## Canonical Repository

| Field | Value |
|---|---|
| **Repository URL** | `https://github.com/amarktainetwork-blip/Amarktai-Crypto` |
| **Canonical Branch** | `main` (release branches: `release/go-live-paper-final`) |
| **Deployment Path** | VPS: `/opt/amarktai` (backend), `/var/www/amarktai` (frontend) |
| **Backend Service** | `systemd: amarktai-backend.service` |
| **Frontend Build** | `npm run build` → served by nginx |

## How to Verify Build SHA on Server

### Backend

```bash
# The backend /api/health/ping endpoint reports build_sha
curl -s https://YOUR_DOMAIN/api/health/ping | jq .build_sha

# Or check the environment on the VPS directly
ssh vps 'systemctl show amarktai-backend --property=Environment' | grep BUILD_SHA
```

### Frontend

```bash
# The frontend embeds REACT_APP_BUILD_SHA in the footer diagnostics
# Check in browser DevTools console:
#   window.__BUILD_SHA__
# Or inspect the footer of the dashboard page.

# On the VPS, check the static build:
ssh vps 'grep -o "BUILD_SHA:[a-f0-9]*" /var/www/amarktai/static/js/main.*.js'
```

## Rules

1. **Never patch production from a local ZIP** — all changes go through this repo.
2. **Every release branch must pass the evidence pack** (`scripts/go_live_evidence_pack.sh`).
3. **FLOKx is permanently removed** — do not re-add under any name.
4. **CoinStats + Hugging Face** are the approved market intelligence integrations.
