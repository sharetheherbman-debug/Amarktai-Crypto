# Amarktai Crypto – Deployment Runbook

> **Single source of truth for deployment.**
> Last updated: 2026-04-03
> Repository: https://github.com/amarktainetwork-blip/Amarktai-Crypto

---

## Canonical Paths (DO NOT CHANGE without updating ALL configs)

| Resource | Path |
|---|---|
| App root (git clone) | `/var/amarktai/app` |
| Backend | `/var/amarktai/app/backend` |
| Python venv | `/var/amarktai/app/backend/.venv` |
| Frontend source | `/var/amarktai/app/frontend` |
| **Frontend build (nginx root)** | **`/var/amarktai/app/frontend/build`** |
| Environment file | `/etc/amarktai/amarktai.env` |
| Systemd service | `/etc/systemd/system/amarktai-api.service` |
| Nginx config | `/etc/nginx/sites-available/amarktai` |
| Nginx symlink | `/etc/nginx/sites-enabled/amarktai` |
| Log directory | `/var/log/amarktai/` |
| SSL certificates | `/etc/letsencrypt/live/amarktai.online/` |

### Architecture

- **Backend**: FastAPI (uvicorn)
- **Frontend**: React SPA (Create React App)
- **Database**: MongoDB
- **Realtime**: Redis
- **Runtime**: systemd + nginx reverse proxy

### NOT used (do not introduce)

Next.js, PostgreSQL, Prisma, PM2, duplicate app directories, alternate build
outputs, `/var/www/amarktai`, `/opt/amarktai`.

---

## Fresh Install (one-time)

```bash
# 1. Create directory structure
sudo mkdir -p /var/amarktai/app
sudo mkdir -p /etc/amarktai
sudo mkdir -p /var/log/amarktai
sudo chown www-data:www-data /var/log/amarktai

# 2. Clone repo (into /var/amarktai/app directly, no subdirectory)
sudo git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git /var/amarktai/app
sudo chown -R www-data:www-data /var/amarktai/app

# 3. Create environment file from template
sudo cp /var/amarktai/app/deployment/etc-amarktai-env.template /etc/amarktai/amarktai.env
sudo chmod 600 /etc/amarktai/amarktai.env
sudo chown www-data:www-data /etc/amarktai/amarktai.env
# IMPORTANT: Edit this file and fill in real secrets
sudo nano /etc/amarktai/amarktai.env

# 4. Backend: create venv and install deps
cd /var/amarktai/app/backend
sudo -u www-data python3 -m venv .venv
sudo -u www-data .venv/bin/pip install --upgrade pip
sudo -u www-data .venv/bin/pip install -r requirements.txt

# 5. Frontend: install and build
cd /var/amarktai/app/frontend
sudo -u www-data npm ci --legacy-peer-deps
sudo -u www-data CI=false npm run build

# 6. Install systemd service
sudo cp /var/amarktai/app/deployment/systemd/amarktai-api.service /etc/systemd/system/amarktai-api.service
sudo systemctl daemon-reload
sudo systemctl enable amarktai-api
sudo systemctl start amarktai-api

# 7. Install nginx config
sudo cp /var/amarktai/app/deployment/nginx/amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -sf /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/amarktai
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 8. Verify
curl http://127.0.0.1:8000/api/health/ping
```

---

## Redeploy (update to latest code)

This is the minimal command sequence to safely redeploy.

```bash
cd /var/amarktai/app

# 1. Pull latest code
sudo -u www-data git fetch --all --prune
sudo -u www-data git checkout main
sudo -u www-data git reset --hard origin/main

# 2. Backend deps (only if requirements changed)
cd backend
sudo -u www-data .venv/bin/pip install -r requirements.txt

# 3. Frontend rebuild
cd ../frontend
sudo -u www-data npm ci --legacy-peer-deps
sudo -u www-data CI=false npm run build

# 4. Restart backend
sudo systemctl restart amarktai-api

# 5. Reload nginx (picks up new static files from build/)
sudo nginx -t && sudo systemctl reload nginx

# 6. Verify
sleep 3
curl -s http://127.0.0.1:8000/api/health/ping
curl -s http://127.0.0.1/  | head -5
```

> **Why this works**: nginx root points directly at `frontend/build/`.
> After `npm run build`, the new files are immediately what nginx serves.
> No rsync, no copy, no separate webroot. Zero drift.

---

## Verify Deployment

```bash
# Backend health
curl -s http://127.0.0.1:8000/api/health/ping | python3 -m json.tool

# Frontend: confirm index.html references current JS bundle
curl -s http://127.0.0.1/ | grep -oP 'main\.[a-f0-9]+\.js'

# Compare with actual build output
ls /var/amarktai/app/frontend/build/static/js/main.*.js

# Service status
sudo systemctl status amarktai-api --no-pager

# Nginx config test
sudo nginx -t
```

---

## Troubleshooting: Old Frontend Being Served

If nginx serves an old JS bundle after a rebuild:

1. **Check nginx root** — must be `/var/amarktai/app/frontend/build`:
   ```bash
   sudo nginx -T 2>/dev/null | grep 'root '
   ```

2. **Check for stale nginx configs** that might point elsewhere:
   ```bash
   ls -la /etc/nginx/sites-enabled/
   # Should contain ONLY: amarktai -> ../sites-available/amarktai
   ```

3. **Check for stale sites-enabled symlinks**:
   ```bash
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo rm -f /etc/nginx/sites-enabled/amarktai-spa
   sudo rm -f /etc/nginx/sites-enabled/amarktai-websocket
   ```

4. **Verify index.html on disk matches what nginx serves**:
   ```bash
   # On-disk bundle name
   grep -oP 'main\.[a-f0-9]+\.js' /var/amarktai/app/frontend/build/index.html
   # Served bundle name
   curl -s http://127.0.0.1/ | grep -oP 'main\.[a-f0-9]+\.js'
   # These MUST match
   ```

5. **Force nginx to drop cached responses**:
   ```bash
   sudo systemctl restart nginx
   ```

---

## Cleanup: Remove Stale Deployment Artifacts

If a previous deployment left stale paths, clean them up:

```bash
# Remove old separate webroot (if it exists)
sudo rm -rf /var/www/amarktai

# Remove old project directory (if it exists under wrong name)
sudo rm -rf /var/amarktai/app/Amarktai-Network---Deployment

# Remove stale nginx configs
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/amarktai-spa
sudo rm -f /etc/nginx/sites-enabled/amarktai-websocket
sudo rm -f /etc/nginx/sites-available/amarktai-spa
sudo rm -f /etc/nginx/sites-available/amarktai-websocket

# Remove stale systemd service files
sudo rm -f /etc/systemd/system/amarktai-monitor.service
sudo rm -f /etc/systemd/system/amarktai-daily-report.service
sudo systemctl daemon-reload

# Remove old venv outside repo (if it exists)
sudo rm -rf /var/amarktai/venv

# Verify only canonical configs remain
ls -la /etc/nginx/sites-enabled/
sudo systemctl list-unit-files 'amarktai*'
```

---

## Config File Source Mapping

When installing/updating config files on VPS, use these canonical sources:

| VPS Target | Repo Source |
|---|---|
| `/etc/systemd/system/amarktai-api.service` | `deployment/systemd/amarktai-api.service` |
| `/etc/nginx/sites-available/amarktai` | `deployment/nginx/amarktai.conf` |
| `/etc/amarktai/amarktai.env` | `deployment/etc-amarktai-env.template` (template only) |

> **Note**: The `ops/` directory contains an alternative nginx config with
> production SSL and HTTPS redirect. Use `ops/nginx/amarktai.conf` instead
> of the deployment/ version when SSL is configured with Let's Encrypt.
> Both now use the same canonical frontend root path.

---

## Why This Architecture Is Deterministic

1. **One frontend build path** — `frontend/build/` is both the npm output
   AND the nginx root. No copy/sync step means no drift.

2. **One systemd service** — `amarktai-api.service` always uses
   `/var/amarktai/app/backend` with `.venv` inside.

3. **One env file** — `/etc/amarktai/amarktai.env` is external to the repo,
   never wiped by `git pull` or `git clean`.

4. **Rebuild = instant live** — After `npm run build`, the new `index.html`
   with new content-hashed JS filenames is immediately what nginx serves.

5. **No rsync required** — Eliminates the #1 source of frontend drift.
