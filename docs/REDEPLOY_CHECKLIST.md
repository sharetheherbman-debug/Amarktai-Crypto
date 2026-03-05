# Redeploy Checklist — Amarktai Network

## Pre-Deploy

1. **Pull latest code**
   ```bash
   cd /opt/amarktai
   git fetch origin
   git checkout release/go-live-paper-final
   git pull
   ```

2. **Backend dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Frontend build**
   ```bash
   cd frontend
   npm ci
   REACT_APP_BUILD_SHA=$(git rev-parse --short HEAD) npm run build
   ```

4. **Set BUILD_SHA for backend**
   ```bash
   echo "BUILD_SHA=$(git rev-parse --short HEAD)" >> /opt/amarktai/backend/.env
   ```

## Deploy Backend

```bash
sudo systemctl restart amarktai-backend
sudo systemctl status amarktai-backend
# Wait for "Application startup complete"
journalctl -u amarktai-backend --no-pager -n 30
```

## Deploy Frontend

```bash
sudo rm -rf /var/www/amarktai/*
sudo cp -r frontend/build/* /var/www/amarktai/
sudo systemctl reload nginx
```

## Post-Deploy Verification

```bash
# Run evidence pack
export BASE_URL=https://your-domain.com
export TOKEN=<admin-jwt>
bash scripts/go_live_evidence_pack.sh
```

### Manual Checks

- [ ] `/api/health/ping` returns `build_hash` ≠ "unknown"
- [ ] `/api/build/info` shows correct SHA
- [ ] Dashboard loads without console errors
- [ ] CoinStats and HuggingFace panels show in Market Intel section
- [ ] Scalper bots panel loads separate from normal bots
- [ ] Bot Radar shows timeseries data
- [ ] No FLOKx references anywhere in the UI
- [ ] Paper trading produces fills in `/api/ledger/fills`
- [ ] Paper reset works: `POST /api/system/paper-reset` with confirmation
- [ ] Footer shows build SHA

## Rollback

```bash
git checkout main
sudo systemctl restart amarktai-backend
sudo cp -r frontend/build/* /var/www/amarktai/
sudo systemctl reload nginx
```
