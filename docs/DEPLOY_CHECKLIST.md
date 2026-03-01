# Amarktai Crypto — VPS Deploy Checklist

> Branch: `copilot/fix-paper-mode-bot-integration`  
> Always pull the latest from this branch before running any step.

---

## 1. Pull latest code

```bash
cd ~/Amarktai-Crypto          # or wherever the repo lives
git fetch origin
git checkout copilot/fix-paper-mode-bot-integration
git pull origin copilot/fix-paper-mode-bot-integration
```

---

## 2. Install / update backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

---

## 3. Build frontend

```bash
cd frontend
npm ci --no-audit
npm run build            # output goes to frontend/build/
```

Copy `frontend/build/` to wherever your web server (nginx / static host) serves it.

---

## 4. Restart backend

```bash
# If using systemd
sudo systemctl restart amarktai-backend

# If using PM2
pm2 restart amarktai-api

# Manual (for debugging)
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

---

## 5. Verify endpoints agree (truth smoke test)

```bash
export TOKEN="<paste JWT from a logged-in admin session>"
bash scripts/verify_truth.sh http://localhost:8000
```

Expected output:
```
✅ All counts agree. No wallet contradictions.
```

---

## 6. Spot-check API endpoints

```bash
BASE="http://localhost:8000"
H="Authorization: Bearer $TOKEN"

# Bot counts
curl -s -H "$H" $BASE/api/bots/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('bots/status active_bots=', d['active_bots'])"

# Paper status
curl -s -H "$H" $BASE/api/diagnostics/paper-status | python3 -c "import sys,json; d=json.load(sys.stdin); print('paper-status active_bots=', d['active_bots'])"

# Snapshot
curl -s -H "$H" $BASE/api/overview/snapshot | python3 -c "import sys,json; d=json.load(sys.stdin); print('snapshot activeBots=', d['activeBots'])"

# Wallet (no contradiction)
curl -s -H "$H" $BASE/api/wallet/paper | python3 -c "import sys,json; d=json.load(sys.stdin); print('wallet status=', d['status'], 'funded_status=', d['funded_status'])"

# Diagnostics/truth (admin only)
curl -s -H "$H" $BASE/api/diagnostics/truth | python3 -m json.tool | head -30
```

---

## 7. Scalper bots

- Navigate to dashboard → **⚡ Scalper Bots** in the sidebar.
- Create a scalper bot via the panel (calls `POST /api/bots/scalper/create`).
- Verify it appears in `/api/scalper/summary`.

---

## 8. Paper reset (when needed for fresh state)

```bash
# Via API (admin)
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
     -d '{"confirm":true,"password":"<paper-reset-password>"}' \
     $BASE/api/system/paper-reset/execute
```

After reset, re-run `verify_truth.sh` to confirm clean state.

---

## Environment variables required (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | ✅ | JWT signing secret — must match between restarts |
| `MONGO_URL` | ✅ | MongoDB connection URI |
| `DB_NAME` | ✅ | MongoDB database name |
| `PAPER_TRADING` | ✅ | Set to `1` for paper mode |
| `LIVE_TRADING` | ✅ | Set to `0` to disable live mode |
| `AUTOPILOT_ENABLED` | ✅ | Set to `0` unless autopilot is ready |
| `PAPER_RESET_PASSWORD` | recommended | Secure password for paper reset endpoint |

---

## Rollback

```bash
git checkout copilot/add-frontend-audit-doc  # previous default branch
git pull
# rebuild frontend + restart backend as above
```
