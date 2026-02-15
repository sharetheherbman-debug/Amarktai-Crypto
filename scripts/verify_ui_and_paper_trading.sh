#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment"
FRONTEND_DIR="$ROOT_DIR/frontend"
BASE_URL="${BASE_URL:-http://localhost:8000}"
INVITE_CODE="${INVITE_CODE:-${X_INVITE_CODE:-AMARKTAI2024}}"
LOG_FILE="${LOG_FILE:-$ROOT_DIR/backend/logs/backend.log}"

EMAIL="paper-verify-$(date +%s)@example.com"
PASSWORD="VerifyPass123!"

printf "\n[1/6] Frontend build...\n"
cd "$FRONTEND_DIR"
npm run build

printf "\n[2/6] Register + login API flow...\n"
cd "$ROOT_DIR"

curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Invite-Code: $INVITE_CODE" \
  -d "{\"first_name\":\"Paper\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"invite_code\":\"$INVITE_CODE\"}" >/tmp/register_response.json || true

LOGIN_JSON=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

TOKEN=$(python - <<'PY' "$LOGIN_JSON"
import json,sys
raw=sys.argv[1]
try:
    data=json.loads(raw)
except Exception:
    print("")
    raise SystemExit
print(data.get("access_token") or data.get("token") or "")
PY
)

if [ -z "$TOKEN" ]; then
  echo "Login failed: $LOGIN_JSON"
  exit 1
fi

echo "Login OK"

printf "\n[3/6] Create 5 Luno paper bots...\n"
for i in 1 2 3 4 5; do
  BODY="{\"name\":\"Verify Luno Paper Bot $i\",\"exchange\":\"luno\",\"risk_mode\":\"balanced\",\"trading_mode\":\"paper\",\"initial_capital\":1000}"
  RESP=$(curl -s -X POST "$BASE_URL/api/bots" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$BODY")
  echo "Bot $i response: $RESP" | sed 's/"access_token":"[^"]*"/"access_token":"***"/g'
done

printf "\n[4/6] Wait for scheduler ticks...\n"
sleep "${SCHEDULER_WAIT_SECONDS:-25}"

printf "\n[5/6] Confirm no immediate MODE_DISABLED quarantine for paper bots...\n"
QUARANTINE_JSON=$(curl -s -X GET "$BASE_URL/api/quarantine/status" -H "Authorization: Bearer $TOKEN")
echo "$QUARANTINE_JSON"

echo "$QUARANTINE_JSON" | python - <<'PY'
import json,sys
payload=json.load(sys.stdin)
bots=payload.get("quarantined_bots", []) if isinstance(payload, dict) else []
mode_disabled=[b for b in bots if str(b.get("quarantine_reason_code") or b.get("quarantine_reason") or "").upper().find("MODE_DISABLED") >= 0]
if mode_disabled:
    print("Found MODE_DISABLED quarantines:", mode_disabled)
    raise SystemExit(1)
print("No MODE_DISABLED quarantine entries for current user paper bots")
PY

printf "\n[6/6] Last 200 log lines filtered for quarantine/bodyguard reasons...\n"
if [ -f "$LOG_FILE" ]; then
  tail -n 200 "$LOG_FILE" | grep -E "quarantine|bodyguard|MODE_DISABLED|circuit_breaker|trading_scheduler|pause_reason" || true
else
  echo "Log file not found at $LOG_FILE"
fi

printf "\nVerification complete.\n"
