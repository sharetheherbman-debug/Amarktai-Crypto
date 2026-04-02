# Amarktai Crypto — Go-Live Run Book
# Paper-Trading Beta (7-Day) — Start Today
#
# Run these commands as root (or sudo) on the VPS.
# All paths assume: /var/amarktai/app/Amarktai-Crypto
# ============================================================================

APP_ROOT=/var/amarktai/app/Amarktai-Crypto
BACKEND=$APP_ROOT/backend
FRONTEND=$APP_ROOT/frontend
ENV_FILE=/etc/amarktai/amarktai.env

# ── STEP 1: Pull latest code ─────────────────────────────────────────────────
cd $APP_ROOT
git pull origin main

# ── STEP 2: Install/update Python dependencies ───────────────────────────────
cd $BACKEND
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
echo "Backend dependencies OK"

# Confirm all four ML libraries are available:
.venv/bin/python -c "
import pandas_ta, xgboost, river, optuna
print('pandas-ta:', pandas_ta.__version__)
print('xgboost:  ', xgboost.__version__)
print('river:    ', river.__version__)
print('optuna:   ', optuna.__version__)
print('All ML libraries OK')
"

# Confirm XGBoost model loads:
.venv/bin/python -c "
import xgboost as xgb
m = xgb.XGBClassifier()
m.load_model('models/xgb_predictor.json')
print('XGBoost model loaded, classes_:', list(m.classes_))
"

# ── STEP 3: Configure environment ────────────────────────────────────────────
mkdir -p /etc/amarktai
# If /etc/amarktai/amarktai.env does not exist, create from template:
#   cp deployment/etc-amarktai-env.template /etc/amarktai/amarktai.env
#
# Ensure these values are set (minimum required for paper-trading beta):
grep -E "^(PAPER_TRADING|LIVE_TRADING|ENABLE_TRADING|ENABLE_SCHEDULERS|MAX_DAILY_LOSS)" $ENV_FILE || {
    echo "WARNING: Some critical flags missing in $ENV_FILE — please set:";
    echo "  PAPER_TRADING=1";
    echo "  LIVE_TRADING=0";
    echo "  ENABLE_TRADING=1";
    echo "  ENABLE_SCHEDULERS=1";
    echo "  MAX_DAILY_LOSS_PERCENT=0.05";
}
chmod 600 $ENV_FILE

# ── STEP 4: Build frontend ────────────────────────────────────────────────────
cd $FRONTEND
npm ci --legacy-peer-deps
CI=false npm run build
echo "Frontend build OK"
ls -la build/index.html

# ── STEP 5: Install systemd service ──────────────────────────────────────────
cp $APP_ROOT/deployment/systemd/amarktai-api.service /etc/systemd/system/amarktai-api.service
systemctl daemon-reload
systemctl enable amarktai-api
systemctl restart amarktai-api
sleep 3
systemctl status amarktai-api --no-pager | head -20

# ── STEP 6: Verify backend health ────────────────────────────────────────────
curl -sf http://127.0.0.1:8000/api/health | python3 -m json.tool
echo "Backend health OK"

# ── STEP 7: Install nginx config ─────────────────────────────────────────────
cp $APP_ROOT/deployment/nginx/amarktai.conf /etc/nginx/sites-available/amarktai
ln -sf /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/amarktai
nginx -t && systemctl reload nginx
echo "Nginx OK"

# ── STEP 8: Verify public site ───────────────────────────────────────────────
curl -sI http://localhost/ | head -5
# Expected: HTTP/1.1 200 OK

# ── STEP 9: (Optional) HTTPS with certbot ────────────────────────────────────
# If domain is configured and pointing to this VPS:
#   certbot --nginx -d yourdomain.com --non-interactive --agree-tos -m admin@yourdomain.com
# This will auto-update nginx to redirect HTTP to HTTPS.

# ── STEP 10: Setup MongoDB backup cron ───────────────────────────────────────
# Add to root's crontab (crontab -e):
#   0 3 * * * /var/amarktai/app/Amarktai-Crypto/deployment/backup_mongo.sh >> /var/log/amarktai/backup.log 2>&1

# ── STEP 10b: Enable daily XGBoost retraining (systemd timer) ────────────────
cp $APP_ROOT/deployment/systemd/amarktai-retrain.service /etc/systemd/system/amarktai-retrain.service
cp $APP_ROOT/deployment/systemd/amarktai-retrain.timer  /etc/systemd/system/amarktai-retrain.timer
systemctl daemon-reload
systemctl enable amarktai-retrain.timer
systemctl start  amarktai-retrain.timer
systemctl status amarktai-retrain.timer --no-pager | head -10
echo "Daily retraining timer enabled (runs 02:00 UTC)"

# ── STEP 10c: Enable daily learning loop (already runs inside backend scheduler)
# Ensure /etc/amarktai/amarktai.env contains:
#   ENABLE_LEARNING_LOOP=true

# ── STEP 11: Verify paper trading is running ─────────────────────────────────
sleep 10
journalctl -u amarktai-api -n 50 --no-pager | grep -E "TradingScheduler|ENABLE_TRADING|CRITICAL|ERROR|paper" | head -20
echo ""
echo "============================================================"
echo " GO-LIVE VERIFICATION CHECKLIST"
echo "============================================================"
curl -sf http://127.0.0.1:8000/api/health && echo "  ✅ Backend healthy"
systemctl is-active amarktai-api && echo "  ✅ Service running"
ls $FRONTEND/build/index.html && echo "  ✅ Frontend build present"
curl -sI http://localhost/ | grep -q "200 OK" && echo "  ✅ Public site 200 OK"
echo "  📋 PAPER_TRADING=1 — verify in env"
echo "  📋 LIVE_TRADING=0  — trading with real funds is LOCKED"
echo "============================================================"
