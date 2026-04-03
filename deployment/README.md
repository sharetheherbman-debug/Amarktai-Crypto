# deployment/ – ARCHIVED

> ⚠️ All scripts in this directory are **archived** and superseded.
> **Do not use any script from this directory for production deployment.**

## Canonical deployment is in `ops/`

| Purpose | Canonical file |
|---|---|
| **Deploy** | `ops/redeploy_production.sh` |
| **Verify** | `ops/verify_production.sh` |
| **Cleanup stale** | `ops/cleanup_stale_deployment.sh` |
| **Systemd unit** | `ops/systemd/amarktai-api.service` |
| **Nginx config** | `ops/nginx/amarktai.conf` |
| **Env template** | `ops/etc-amarktai-env.template` |
| **Runbook** | `DEPLOYMENT_RUNBOOK.md` (repo root) |

## One-command deploy

```bash
cd /var/amarktai/app/Amarktai-Crypto
sudo bash ops/redeploy_production.sh
```

## Why these files are archived

The `_archive/` subdirectory contains earlier-generation scripts that referenced
inconsistent VPS paths (`/var/amarktai/app` without the `Amarktai-Crypto`
subdirectory, `/var/www/amarktai`, etc.) and competing deploy flows.
They are kept for historical reference only and must not be executed.
