# Amarktai Crypto – Ops Deployment Quick Reference

> **Single source of truth for production deployment.**
> Full runbook: [DEPLOYMENT_RUNBOOK.md](../DEPLOYMENT_RUNBOOK.md)

---

## ⚠️ numpy Constraint – DO NOT IGNORE

`numpy` is pinned to `1.x` (==1.26.4). Do **not** upgrade to numpy 2.x.

- `langchain-chroma==0.1.4` requires `numpy<2.0.0`
- `pandas-ta==0.3.14b0` requires numpy 1.x (pre-dates numpy 2)
- Upgrading numpy to >=2.0 causes `ResolutionImpossible` on pip install

Production deploy installs from `backend/requirements.production.lock.txt`
which has all packages at exact versions. This avoids the live-resolve conflict.

---

## Canonical Paths

| Resource | Path |
|---|---|
| App root (git clone) | `/var/amarktai/app/Amarktai-Crypto` |
| Backend | `/var/amarktai/app/Amarktai-Crypto/backend` |
| Python venv | `/var/amarktai/app/Amarktai-Crypto/backend/.venv` |
| Frontend source | `/var/amarktai/app/Amarktai-Crypto/frontend` |
| **Frontend build (nginx root)** | **`/var/amarktai/app/Amarktai-Crypto/frontend/build`** |
| Environment file | `/etc/amarktai/amarktai.env` |
| Systemd service | `amarktai-api` (unit: `/etc/systemd/system/amarktai-api.service`) |
| Nginx config | `amarktai` (`/etc/nginx/sites-available/amarktai`) |
| Log directory | `/var/log/amarktai/` |

---

## One-Command Redeploy

```bash
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh
```

## One-Command Verify

```bash
sudo bash ops/verify_production.sh
```

## Stale Deployment Cleanup

```bash
# Dry run first (see what would be removed):
sudo bash ops/cleanup_stale_deployment.sh --dry-run

# Apply cleanup:
sudo bash ops/cleanup_stale_deployment.sh
```

---

## Files in This Directory

| File | Purpose |
|---|---|
| `redeploy_production.sh` | **Master deploy script** – one command to pull, build, install, restart, verify |
| `verify_production.sh` | Post-deploy verification – checks service, nginx, JS match, API health |
| `cleanup_stale_deployment.sh` | Safe removal of stale services, nginx links, old venvs |
| `deploy.sh` | Lightweight incremental deploy (skip frontend/backend flags) |
| `smoke_test.sh` | Quick smoke test after deploy |
| `backup.sh` | Backup current deployment state |
| `restore.sh` | Restore from backup |
| `systemd/amarktai-api.service` | Canonical systemd unit (source of truth) |
| `nginx/amarktai.conf` | Canonical nginx config (source of truth) |

---

## Fresh Install (first time)

```bash
# 1. Create directories
sudo mkdir -p /var/amarktai/app
sudo mkdir -p /etc/amarktai
sudo mkdir -p /var/log/amarktai
sudo chown www-data:www-data /var/log/amarktai

# 2. Clone repo
sudo git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git \
  /var/amarktai/app/Amarktai-Crypto
sudo chown -R www-data:www-data /var/amarktai/app/Amarktai-Crypto

# 3. Create env file from template
sudo cp /var/amarktai/app/Amarktai-Crypto/deployment/etc-amarktai-env.template \
  /etc/amarktai/amarktai.env
sudo chmod 600 /etc/amarktai/amarktai.env
sudo chown root:www-data /etc/amarktai/amarktai.env
sudo nano /etc/amarktai/amarktai.env    # fill in real secrets

# 4. Run production deploy
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh
```

---

## Rollback

```bash
cd /var/amarktai/app/Amarktai-Crypto

# Roll back to previous commit
sudo git log --oneline -10          # find the previous SHA
sudo git reset --hard <prev_sha>

# Rebuild and restart
sudo bash ops/redeploy_production.sh
```

---

## Useful Commands

```bash
# Check service status
sudo systemctl status amarktai-api

# Tail live logs
sudo journalctl -u amarktai-api -f

# Check nginx config
sudo nginx -t

# Manual health check
curl http://127.0.0.1:8000/api/health/ping
```
