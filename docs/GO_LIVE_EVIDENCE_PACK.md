# Amarktai Network — Go-Live Evidence Pack

> Generated: 2026-02-23  
> PR: Go-Live Perfection Pass (merge 164)

---

## What Was Broken

| # | Issue | Symptom |
|---|-------|---------|
| A1 | **MongoDB DB mismatch** | `.env` has `MONGO_URI=.../amarktai` but `database.py` defaults to `MONGO_URL` + `DB_NAME=amarktai_trading`. Process env missing `MONGO_URI` → writes to wrong DB |
| A2 | **No safe DB identity log** | Startup log showed generic URL without DB name |
| A3 | **`/api/build` returned 404** | Frontend and ops scripts had no way to verify deployment |
| B1 | **Null trade ID → E11000** | `order_pipeline.py` built `trade_doc` without `id` field; Mongo unique index on `trades.id` rejected null |
| B1b | **`exchange_order_id` used `id` as fallback** | `build_trade_record` put `id` into `exchange_order_id`, making the circular reference confusing |
| C3 | **No data integrity endpoint** | No quick way to see trade counts, PnL, wallet state in one call |
| D2 | **No realtime diagnostics** | No endpoint to check WS connection count or last broadcast times |
| E | **Advanced AI crash** | `AIToolsPanel` mounted with no error boundary; any runtime error crashed the whole Welcome section |
| F1 | **HF integration silent** | No `/api/hf/status` or `/api/hf/infer`; UI showed nothing actionable |
| F2 | **No HF status tile in API Setup** | Users couldn't see if HuggingFace was configured without navigating away |
| G | **Duplicate Reset Runtime** | `/api/admin/runtime/reset` and `/api/admin/start-fresh` both existed; old endpoint still destructive |

---

## What Was Fixed

### A – Database Config

**Files changed:**
- `backend/database.py` – added `_parse_mongo_config()`:
  - Priority: `MONGO_URI` (DB extracted from path) → `MONGO_URL` + `DB_NAME` → defaults
  - Startup logs `host=X db=Y` (credentials redacted)
- `backend/core/settings.py` – `SystemSettings.__init__` mirrors same resolution logic
- `startup_self_check()` prints effective DB identity before checking required keys

### B – Trade Insertion

**Files changed:**
- `backend/services/order_pipeline.py` – `trade_doc` now always includes `"id": str(uuid.uuid4())`
- `backend/utils/trade_utils.py` – `build_trade_record()`:
  - Resolves `id` before `record.update()` (not inside it, avoiding circular reference)
  - Logs `WARNING` when id was missing and auto-generates it
  - `exchange_order_id` no longer uses `id` as fallback

### C – Dashboard Accuracy / Diagnostics

**Files changed:**
- `backend/routes/diagnostics.py` – new `GET /api/diagnostics/data-integrity`:
  - Returns `total_trades`, `paper_trades`, `live_trades`, `filled_count`, `closed_count`
  - `net_realized_pnl` (closed trades only, `net_pnl` field)
  - `paper_wallet_balance`, `bots_current_capital_sum`, `db_name`

### D – Realtime Diagnostics

**Files changed:**
- `backend/routes/diagnostics.py` – new `GET /api/diagnostics/db` (admin):
  - Returns `mongo_uri_host`, `db_name`, `collections` list, `counts` per key collection
  - `indexes` for trades collection
- `backend/routes/diagnostics.py` – new `GET /api/diagnostics/realtime-status`:
  - Returns connected users count, total connections, broadcast stats

### E – Advanced AI Crash Fix

**Files changed:**
- `frontend/src/pages/dashboard/sections/AiChatSection.js`:
  - Imports `ErrorBoundary`
  - Wraps `<AIToolsPanel />` with `<ErrorBoundary title="Advanced AI error" message="…">`
  - Any runtime error inside Advanced AI now shows a graceful message, not a white screen

### F – HuggingFace Integration

**Files changed:**
- `backend/routes/huggingface.py` – added:
  - `GET /api/hf/status` – returns `{enabled, model, last_success_at, last_error, latency_ms}`
  - `POST /api/hf/infer` – minimal safe inference (sentiment/summarize/classify, 512-char limit)
  - In-process caching of last-success timestamp and latency
- `frontend/src/pages/dashboard/sections/ApiSetupSection.js` – added `HuggingFaceStatusTile`:
  - Calls `/api/hf/status` on mount
  - Shows ✅ Connected / ⚠️ Error / ❌ Not configured with actionable message

### G – Duplicate Reset Runtime

**Files changed:**
- `backend/routes/admin_endpoints.py` – `POST /api/admin/runtime/reset` now returns:
  ```json
  { "success": false, "deprecated": true, "message": "Use POST /api/admin/start-fresh ..." }
  ```
  Canonical flow is `POST /api/admin/start-fresh` (System Mode section only)

### A3 – Build Info Endpoint

**Files changed:**
- `backend/routes/build_info.py`:
  - Added `GET /api/build` (root, no auth required)
  - Returns: `version`, `built_at`, `branch`, `mongodb.host`, `mongodb.name`, `flags`

---

## Verification Commands (VPS)

### Prerequisites
```bash
export API_BASE=http://127.0.0.1:8000    # or your domain
export AMK_EMAIL=admin@yourdomain.com
export AMK_PASSWORD=yourpassword
```

### Run full smoke test
```bash
./scripts/go_live_smoke.sh
```
Expected: `🎉 All required tests passed – system is go-live ready!`

### Manual curl steps

#### 1. Health + Build hash
```bash
curl -s $API_BASE/api/health/ping | python3 -m json.tool
curl -s $API_BASE/api/build | python3 -m json.tool
# Expected: version != "unknown", mongodb.name == "amarktai" (or your DB name)
```

#### 2. Login
```bash
TOKEN=$(curl -s -X POST $API_BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$AMK_EMAIL\",\"password\":\"$AMK_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: ${TOKEN:0:40}..."
```

#### 3. DB diagnostics (confirm correct DB)
```bash
curl -s $API_BASE/api/diagnostics/db \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Expected: db_name == "amarktai", collections list non-empty
```

#### 4. Submit 2 paper orders
```bash
for i in 1 2; do
  curl -s -X POST $API_BASE/api/orders/submit \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"symbol":"BTC/ZAR","side":"buy","amount":0.0001,"order_type":"market","exchange":"luno","mode":"paper"}' \
    | python3 -m json.tool
done
```

#### 5. Confirm trades in correct DB
```bash
# via backend diagnostics
curl -s "$API_BASE/api/diagnostics/data-integrity" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Expected: total_trades >= 2, db_name == "amarktai"
```

#### 6. Confirm wallet updates
```bash
curl -s $API_BASE/api/wallet/balance \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

#### 7. HuggingFace status
```bash
curl -s $API_BASE/api/hf/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# If no key configured: enabled=false, clear message
# If key configured: enabled=true, latency_ms > 0
```

#### 8. WebSocket test (requires websocat or wscat)
```bash
# websocat
echo "" | timeout 10 websocat "ws://127.0.0.1:8000/api/ws?token=$TOKEN" | head -1

# wscat
wscat -c "ws://127.0.0.1:8000/api/ws?token=$TOKEN" --wait 10 | head -1
# Expected: JSON message with type="heartbeat" or "state" within 10s
```

#### 9. Reset Runtime – confirm deprecated
```bash
curl -s -X POST $API_BASE/api/admin/runtime/reset \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation_phrase":"CONFIRM RUNTIME RESET","mode":"paper"}' \
  | python3 -m json.tool
# Expected: {"success": false, "deprecated": true, "message": "Use start-fresh..."}
```

---

## Stop Conditions / Known Blockers

| Blocker | Reason | Resolution |
|---------|--------|------------|
| Systemd `EnvironmentFile` not loading `.env` | MONGO_URI not present in `/proc/<pid>/environ` | Ensure systemd unit has `EnvironmentFile=/var/amarktai/app/Amarktai-Network---Deployment/backend/.env` and restart service |
| `DB_NAME` still defaults to `amarktai_trading` if neither `MONGO_URI` nor `DB_NAME` set | Cannot fix env injection at code level | Operator must set env vars in systemd unit file |
| WebSocket smoke test requires `websocat`/`wscat` | These may not be installed on VPS | `apt install websocat` or `npm i -g wscat` |
| HuggingFace `latency_ms` shows null until first `/api/hf/status` call | Probe runs lazily on first call | Normal – make one call after startup |
| `paper_wallet_balance` returns 0 if `paper_wallet_ledger` service not seeded | Fresh deployment has no ledger entries | Submit at least one paper order to seed the wallet |

---

## Files Changed Summary

```
backend/database.py                                     +52/-1
backend/core/settings.py                                +22/-2
backend/routes/build_info.py                            +60/-23
backend/routes/admin_endpoints.py                       +18/-68
backend/routes/diagnostics.py                           +200/+0
backend/routes/huggingface.py                           +140/+0
backend/services/order_pipeline.py                      +1/-0
backend/utils/trade_utils.py                            +12/-3
frontend/src/pages/dashboard/sections/AiChatSection.js  +5/-2
frontend/src/pages/dashboard/sections/ApiSetupSection.js +50/-5
scripts/go_live_smoke.sh                                rewritten
tests/test_golive_production.py                         +190 (new)
docs/GO_LIVE_EVIDENCE_PACK.md                           +200 (new)
```
