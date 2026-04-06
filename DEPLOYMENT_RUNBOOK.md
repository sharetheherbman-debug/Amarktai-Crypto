# Amarktai Crypto – Deployment Runbook

> **Single source of truth for deployment.**
> Last updated: 2026-04-03
> Repository: https://github.com/amarktainetwork-blip/Amarktai-Crypto

---

## ONE-COMMAND REDEPLOY

```bash
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh
```

## ONE-COMMAND VERIFY

```bash
sudo bash ops/verify_production.sh
```

---

## Canonical Paths (DO NOT CHANGE without updating ALL configs)

| Resource | Path |
|---|---|
| App root (git clone) | `/var/amarktai/app/Amarktai-Crypto` |
| Backend | `/var/amarktai/app/Amarktai-Crypto/backend` |
| Python venv | `/var/amarktai/app/Amarktai-Crypto/backend/.venv` |
| Frontend source | `/var/amarktai/app/Amarktai-Crypto/frontend` |
| **Frontend build (nginx root)** | **`/var/amarktai/app/Amarktai-Crypto/frontend/build`** |
| Environment file | `/etc/amarktai/amarktai.env` |
| Systemd service | `amarktai-api` (`/etc/systemd/system/amarktai-api.service`) |
| Nginx config | `/etc/nginx/sites-available/amarktai` |
| Nginx symlink | `/etc/nginx/sites-enabled/amarktai` |
| Log directory | `/var/log/amarktai/` |
| SSL certificates | `/etc/letsencrypt/live/amarktai.online/` |

### Architecture

- **Backend**: FastAPI (uvicorn) in Python 3.12
- **Frontend**: React SPA (Create React App)
- **Database**: MongoDB
- **Realtime**: Redis
- **Runtime**: systemd + nginx reverse proxy

### NOT used (do not introduce)

Next.js, PostgreSQL, Prisma, PM2, duplicate app directories, alternate build
outputs, `/var/www/amarktai`, `/opt/amarktai`, `/var/amarktai/venv`.

### Config file source of truth

| VPS Target | Repo Source (canonical) |
|---|---|
| `/etc/systemd/system/amarktai-api.service` | `ops/systemd/amarktai-api.service` |
| `/etc/nginx/sites-available/amarktai` | `ops/nginx/amarktai.conf` |
| `/etc/amarktai/amarktai.env` | `ops/etc-amarktai-env.template` (template only, fill in secrets) |

---

## Fresh Install (one-time VPS setup)

```bash
# 1. Create directory structure
sudo mkdir -p /var/amarktai/app
sudo mkdir -p /etc/amarktai
sudo mkdir -p /var/log/amarktai
sudo chown www-data:www-data /var/log/amarktai

# 2. Clone repo into canonical path
sudo git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git \
  /var/amarktai/app/Amarktai-Crypto
sudo chown -R www-data:www-data /var/amarktai/app/Amarktai-Crypto

# 3. Create environment file from template (fill in REAL secrets)
sudo cp /var/amarktai/app/Amarktai-Crypto/ops/etc-amarktai-env.template \
  /etc/amarktai/amarktai.env
sudo chmod 600 /etc/amarktai/amarktai.env
sudo chown root:www-data /etc/amarktai/amarktai.env
sudo nano /etc/amarktai/amarktai.env    # ← fill in secrets now

# 4. Run the one-command deploy (builds everything, installs service + nginx)
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh

# 5. Verify
sudo bash ops/verify_production.sh
```

---

## Redeploy (update to latest code)

```bash
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh
```

That single command deploys the **currently checked-out commit** and:
1. Records the checked-out commit SHA (does NOT auto-pull `origin/main`)
2. Installs locked backend dependencies from `requirements.production.lock.txt`
3. Rebuilds frontend
4. Installs canonical systemd unit and nginx config
5. Removes stale nginx sites and old systemd services
6. Restarts backend and nginx
7. Compares built JS filename vs served JS filename (fails if mismatch)
8. Runs health checks
9. Prints PASS/FAIL summary

> **To pull new code first:**
> ```bash
> cd /var/amarktai/app/Amarktai-Crypto
> sudo git pull                          # or: sudo git reset --hard <sha>
> sudo bash ops/redeploy_production.sh   # then deploy
> ```

---

## Verify Deployment

```bash
sudo bash ops/verify_production.sh
```

Checks:
- `amarktai-api` service is active
- ExecStart path uses canonical venv
- uvicorn process path is correct
- nginx root is canonical `frontend/build` path
- Built JS filename equals served JS filename
- `/api/health` and `/api/health/ping` return OK
- No stale `amarktai.service` remains
- No stale nginx sites remain enabled
- Public domain HTTPS response

---

## Rollback

```bash
cd /var/amarktai/app/Amarktai-Crypto

# Find the previous SHA
sudo git log --oneline -10

# Roll back
sudo git reset --hard <prev_sha>

# Rebuild and restart
sudo bash ops/redeploy_production.sh
```

---

## Cleanup Stale Deployment Artifacts

```bash
# Dry run first:
sudo bash ops/cleanup_stale_deployment.sh --dry-run

# Apply:
sudo bash ops/cleanup_stale_deployment.sh
```

This safely removes:
- Stale `amarktai.service` (old unit name)
- Stale nginx symlinks: `default`, `amarktai-spa`, `amarktai-websocket`
- Old venv at `/var/amarktai/venv`
- Old webroots `/var/www/amarktai`, `/opt/amarktai` (if not in use)

---

## Troubleshooting: Old Frontend Being Served

If nginx serves a stale JS bundle after a rebuild:

1. **Run the full redeploy** — it will detect and fail on mismatch:
   ```bash
   sudo bash ops/redeploy_production.sh
   ```

2. **Or verify manually**:
   ```bash
   # Built JS (should be the latest hash)
   ls /var/amarktai/app/Amarktai-Crypto/frontend/build/static/js/main.*.js

   # Served JS (from index.html)
   grep -oP 'main\.[a-f0-9]+\.js' \
     /var/amarktai/app/Amarktai-Crypto/frontend/build/index.html

   # These must match
   ```

3. **Check nginx root** — must be canonical path:
   ```bash
   sudo nginx -T 2>/dev/null | grep 'root '
   # Expected: root /var/amarktai/app/Amarktai-Crypto/frontend/build;
   ```

4. **Check for stale nginx sites** — only `amarktai` should be enabled:
   ```bash
   ls -la /etc/nginx/sites-enabled/
   ```

---

## Backend Dependency Management

Production installs from the locked file:
```bash
backend/requirements.production.lock.txt
```

This file pins every package including trading/ML packages (xgboost, river,
optuna, redis, web3) with no version ranges. Dev tools
(pytest, black, flake8, mypy) are excluded.

> **Note:** `pandas-ta` was removed from all requirements files because
> version `0.3.14b0` is no longer published on PyPI. `ml_predictor.py`
> contains a full manual fallback for all technical indicators
> (RSI, MACD, ATR, Bollinger Bands, VWAP, SMA).
> `langchain`/`chromadb` are not installed in production; they are optional
> and guarded by `try/except` in `engines/reflexion_loop.py`.

### ⚠️ Critical: numpy constraint

**DO NOT upgrade numpy to >=2.0 without verifying langchain-chroma.**

| Package | numpy requirement |
|---|---|
| `langchain-chroma==0.1.4` | `numpy<2.0.0` |
| `langchain-chroma` new versions | may support numpy 2.x — check before upgrading |

`numpy` is pinned to `==1.26.4` in `requirements.production.lock.txt`.

If you see `ResolutionImpossible` or `resolution-too-deep` during `pip install`,
the root cause is this conflict. **Always install from the lock file.**

### Dependency file layout

| File | Purpose |
|---|---|
| `requirements.production.lock.txt` | **Production single source of truth** – exact pins, no dev tools |
| `requirements.core.txt` | Minimal trading API subset (no LangChain/RAG) |
| `requirements.txt` | Full package list with version ranges (for development) |
| `requirements/base.txt` | Core FastAPI/MongoDB/auth packages |
| `requirements/ai.txt` | ML/LangChain/transformers (numpy<2.0 constraint) |
| `requirements/constraints.txt` | Version constraint pins |
| `requirements-ai.txt` | Optional Fetch.ai agents (protobuf conflicts – separate install) |

### Updating the lock file after requirements.txt changes

```bash
pip install pip-tools
cd backend
pip-compile --constraint requirements/constraints.txt \
            -o requirements.production.lock.txt requirements.txt
# Review changes carefully – watch for numpy version bumps
git add backend/requirements.production.lock.txt
git commit -m "chore: update production lock file"
# Then redeploy:
sudo bash ops/redeploy_production.sh
```

---

## Why This Architecture Is Deterministic

1. **One frontend build path** — `frontend/build/` is both the npm output
   AND the nginx root. No copy/sync step means no drift.

2. **One systemd service** — `amarktai-api` always uses
   `/var/amarktai/app/Amarktai-Crypto/backend` with `.venv` inside.

3. **One env file** — `/etc/amarktai/amarktai.env` is external to the repo,
   never wiped by `git pull` or `git reset`.

4. **One locked requirements file** — `requirements.production.lock.txt`
   eliminates pip resolver backtracking and numpy/langchain/chromadb conflicts.

5. **Preflight checks** — systemd unit runs 4 preflight checks before
   starting uvicorn. Deploy script also verifies before restart.

6. **JS filename cross-check** — deploy script compares built JS hash to
   the hash referenced in `index.html`. Fails if they do not match.
