# AMARKTAI NETWORK — GO-LIVE AUDIT REPORT

**Date:** 2026-02-24  
**Branch:** `copilot/fix-error-in-code`  
**Scope:** Full backend + frontend code audit — no changes made  
**Purpose:** Complete list of blockers and solutions before go-live

---

## AUDIT SUMMARY

| Category | Count |
|---|---|
| 🔴 CRITICAL blockers (will prevent go-live) | 5 |
| 🟠 HIGH-RISK issues (will cause incorrect behaviour) | 7 |
| 🟡 MEDIUM issues (degrade experience / reliability) | 8 |
| 🟢 LOW / informational | 5 |

---

## 🔴 CRITICAL BLOCKERS

### C1 — `ENABLE_SCHEDULERS=false` in `backend/.env.example`

**File:** `backend/.env.example` line 200  
**Finding:**  
```
ENABLE_SCHEDULERS=false
```
Trading schedulers — the autonomous bot ticks, nightly learning, self-healing — are disabled by the reference `.env.example`. Any deployment that copies this file verbatim will have **zero automated trading**. Bots will be created, paper-funded, and then sit idle forever.

**Evidence:** `backend/config/__init__.py` line 175 reads:
```python
ENABLE_SCHEDULERS = os.getenv('ENABLE_SCHEDULERS', 'true').lower() == 'true'
```
The code default is `true`, but the `.env.example` overrides it to `false`.

**Solution:**  
Change `backend/.env.example`:
```diff
-ENABLE_SCHEDULERS=false
+ENABLE_SCHEDULERS=true
```
Or ensure the production `.env` on VPS explicitly sets `ENABLE_SCHEDULERS=true`.

---

### C2 — `deposit-address` gate uses wrong `env_bool` defaults

**File:** `backend/server.py` line 1809  
**Finding:**
```python
if not env_bool("ENABLE_LIVE_TRADING", False) and not env_bool("ENABLE_PAPER_TRADING", False):
    return {"status": "disabled", ...}
```
`env_bool("ENABLE_PAPER_TRADING", False)` defaults to `False`, so when `ENABLE_PAPER_TRADING` is not set in the environment, this gate incorrectly returns `disabled`. However, the backend elsewhere at line 87 does:
```python
paper_trading = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
```
These two defaults are inconsistent. If the `.env` file was not deployed correctly, the deposit-address endpoint returns `status=disabled` even though paper trading is configured.  

**Solution:**  
Update line 1809 to use the same consistent default as line 87:
```python
if not env_bool("ENABLE_LIVE_TRADING", False) and not env_bool("ENABLE_PAPER_TRADING", True):
```

---

### C3 — Order pipeline gate ordering mismatch (8 failing unit tests)

**File:** `backend/services/order_pipeline.py` lines 247–272  
**Test file:** `tests/test_order_pipeline_production.py`  
**Finding:**  
8 out of 9 order pipeline production tests fail. The tests expect Gate C (`trade_limiter`) to fire when daily caps are exceeded, but Gate B (`fee_coverage`) fires first because fee coverage check runs before trade limiter check in the pipeline order. The tests were written when the gate order was B=trade_limiter, C=fee_coverage, but the code was refactored to swap them.

```
FAILED test_per_exchange_daily_caps_luno    → expected 'trade_limiter', got 'fee_coverage'
FAILED test_per_exchange_daily_caps_binance → expected 'trade_limiter', got 'fee_coverage'
FAILED test_bot_cooldown_15_seconds         → expected 'trade_limiter', got 'fee_coverage'
FAILED test_rolling_window_cap_30_orders    → expected 'trade_limiter', got 'fee_coverage'
FAILED test_user_scaling_caps_with_bot_count → expected 'trade_limiter', got 'fee_coverage'
FAILED test_signal_engine_integration_gate_b → signal engine mock not called
FAILED test_spam_pattern_detection_excessive_cancels → spam detection not triggering
FAILED test_rejection_broadcast_to_realtime → broadcast mock not called
```

**Severity:** These tests were written to validate production order flow. Failing tests mean the order pipeline may not enforce daily trade caps as expected, potentially allowing over-trading.

**Solution (Option A — fix the code to match the intent):**  
Move the trade-limiter check to run *before* the fee-coverage check so caps are enforced first, which is the safer order. This matches what the tests expect.

**Solution (Option B — fix the tests to match the refactored code):**  
Update the 8 test assertions to expect `fee_coverage` as the `gate_failed` value, and fix the mock setup so fee coverage passes before trade limiter is reached. Only use this option if you are certain the current gate order (fee first, then caps) is intentional and safe.

---

### C4 — Email confirmation URLs hardcoded to `your-domain.com`

**Files:**  
- `backend/services/email_service.py` line 202  
- `backend/services/email_service_enhanced.py` lines 149, 200, 445  

**Finding:**
```python
confirmation_url = f"https://your-domain.com/confirm-withdrawal?token={confirmation_token}"
```
Withdrawal confirmation emails sent to users will contain broken links. This means **live trading withdrawals cannot be confirmed via email** — the email is sent but the confirmation link goes to a non-existent domain.

**Solution:**  
Add `APP_DOMAIN` or `FRONTEND_URL` to the environment and use it:
```python
app_domain = os.getenv("FRONTEND_URL", "https://amarktai.online")
confirmation_url = f"{app_domain}/confirm-withdrawal?token={confirmation_token}"
```
Add `FRONTEND_URL=https://amarktai.online` to `backend/.env.example`.

---

### C5 — JWT_SECRET uses insecure default

**File:** `backend/auth.py` line 10  
**Finding:**
```python
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
```
The default is `"your-secret-key"` (17 chars, well-known default). The code emits a warning but **does not refuse to start** in non-production environments. If a VPS `.env` file does not define `JWT_SECRET`, all JWTs are signed with a public default — anyone can forge tokens.

**Note:** The code does check for weak secrets and emits a warning at startup. But since the server does not halt on weak secrets, this warning is easy to miss in deployment logs.

**Solution:**  
1. Ensure `JWT_SECRET` is set in production `.env` using `openssl rand -hex 32`.  
2. Consider making the startup check refuse to boot in production (`ENVIRONMENT=production`) with a weak secret.

---

## 🟠 HIGH-RISK ISSUES

### H1 — `ENABLE_TRADING=false` in root `.env.example`

**File:** `.env.example` line 43  
**Finding:**  
Root `.env.example` still has `ENABLE_TRADING=false`. This is the master trading switch. Any deployment using the root example without overriding will disable **all trading**.

**Solution:**  
```diff
-.ENABLE_TRADING=false
+ENABLE_TRADING=true       # Master switch - required for paper trading
```
(Note: `backend/.env.example` already correctly has `ENABLE_TRADING=true` at line 163.)

---

### H2 — AI Confirmation: no idempotency / "exactly once" guarantee

**File:** `backend/routes/ai_chat.py` lines 1332–1545; `backend/server.py` lines 1361–1367  
**Finding:**  
Many AI actions (`requires_confirmation=True`) tell the user to type "yes" or "confirm" to proceed. There is no server-side state tracking that a specific confirmation was already used. If the user sends "confirm" twice in quick succession (e.g., double-click or network retry), the action could execute twice. There is no `pending_confirmation_id` or one-time token.

**Solution:**  
Store a pending confirmation in MongoDB with a short TTL (60 seconds). When the user confirms, atomically delete the pending record and execute the action. Return an error if the record no longer exists.

---

### H3 — Countdown-to-million uses paper balance fallback for live mode

**File:** `backend/server.py` lines 1611–1618  
**Finding:**
```python
if is_live:
    # For live mode, calculate from real exchange balances
    # For now, use paper as fallback (implement live balance fetching later)
    zar_balance = ccxt_service.get_paper_balance(user_id, 'ZAR')
```
In live mode the countdown to million still reads from the **paper wallet**, so the displayed balance will not reflect the real exchange balance. The UI will show `R0` (or stale paper balance) as current capital while the user actually has real funds deployed.

**Solution:**  
Implement live balance fetching using `ccxt_service.get_live_balance()` or fetch from wallet_manager, and use it when `is_live=True`.

---

### H4 — `ENABLE_LEARNING_LOOP` defaults to `false` — learning never runs

**File:** `backend/routes/learning_jobs.py` line 34  
**Finding:**
```python
enabled = os.getenv("ENABLE_LEARNING_LOOP", "false").lower() == "true"
```
The learning loop is always disabled unless `ENABLE_LEARNING_LOOP=true` is in the environment. This means the system will **never improve** bot parameters from paper trades. The `/api/learning/status` endpoint will always return `state="disabled"`.

**Solution:**  
Add `ENABLE_LEARNING_LOOP=true` to `backend/.env.example` (or `true` by default when schedulers are enabled). Alternatively, auto-enable when `ENABLE_SCHEDULERS=true`.

---

### H5 — HuggingFace probe runs synchronously on every first status call

**File:** `backend/routes/huggingface.py` lines 540–556  
**Finding:**  
The health probe (`client.text_classification(...)`) is a **blocking call** run on the first `/api/hf/status` request. Since FastAPI is async, this blocks the event loop until the HF API responds (up to several seconds). If HF is slow or unreachable, this blocks all API responses on the same worker.

**Solution:**  
Run the probe in `asyncio.to_thread()`:
```python
_ = await asyncio.to_thread(client.text_classification, HF_HEALTH_PROBE_TEXT)
```
Or move the probe to a background startup task and cache the result.

---

### H6 — `paper_wallet_service` does not auto-seed wallet on bot creation

**File:** `backend/services/wallet_summary_service.py` line 87  
**Finding:**
```python
# Do NOT auto-create with PAPER_STARTING_CAPITAL_ZAR; the user must
```
The paper wallet is not automatically funded when the first bot is created. Users who create bots will see `R0` balance and bots will be unable to trade due to insufficient funds. A manual `/api/wallet/paper/deposit` call or admin action is required.

**Evidence:** The `.env.example` has `PAPER_STARTING_CAPITAL_ZAR=30000` but this is only used if the user explicitly funds their wallet.

**Solution:**  
Ensure onboarding flow explicitly triggers `POST /api/wallet/paper/deposit` after first bot creation, or auto-seed on first bot create. The existing `/api/wallet/paper/deposit` endpoint exists — it just needs to be called.

---

### H7 — `bot_lifecycle.py` re-import of `ccxt_service` at server startup causes issues

**File:** `backend/bot_lifecycle.py` line 3  
**Finding:**  
`bot_lifecycle.py` at the root backend directory exists alongside `backend/routes/bot_lifecycle.py`. The root file imports `ccxt_service` and has global state. If both files are loaded, there can be conflicting global state.

**Solution:**  
Verify only one of these files is active in production. The server imports `routes.bot_lifecycle` (confirmed in `server.py` router list), so the root `backend/bot_lifecycle.py` should be removed or renamed with a clear deprecation notice.

---

## 🟡 MEDIUM ISSUES

### M1 — `ENABLE_NIGHTLY_LEARNING=false` and `ENABLE_SELF_LEARNING=true` conflict

**File:** `backend/.env.example`  
**Finding:** Both learning flags exist with contradictory defaults (`ENABLE_SELF_LEARNING=true`, `ENABLE_NIGHTLY_LEARNING=false`, `ENABLE_LIVE_LEARNING=false`). It is unclear which flag controls the learning loop service. Operators may set the wrong flag.

**Solution:**  
Document clearly which flag is canonical. From `learning_jobs.py`, the gate is `ENABLE_LEARNING_LOOP`. Add this flag to `.env.example` with `=true`.

---

### M2 — No API rate limiting on backend endpoints

**Finding:**  
There is no HTTP-level rate limiting (e.g., `slowapi`, nginx rate limiting) applied to any endpoint. Brute-force attacks on `/api/auth/login`, `/api/admin/*`, and order submission are possible.

**Solution:**  
Add `slowapi` rate limiting to auth endpoints and order submission. For immediate protection, configure nginx or the reverse proxy to rate-limit.

---

### M3 — CORS wildcard active when `ENVIRONMENT` is not set

**File:** `backend/server.py` lines 419–427  
**Finding:**  
When `ENVIRONMENT` env var is not set (defaults to `production`), the server uses hardcoded CORS origins `['https://amarktai.online', 'https://www.amarktai.online']`. However, if `ENVIRONMENT=development` is set in production by mistake, a wildcard `['*']` CORS origin is used.

**Solution:**  
Ensure `ENVIRONMENT=production` is set in the production `.env` file. Add it to `.env.example`.

---

### M4 — 53 tests fail due to missing `fastapi` dependency in test runner

**Finding:**  
When running `pytest` from the repository root, 53 tests fail with `ModuleNotFoundError: No module named 'fastapi'` because `pytest.ini` adds `backend/` to the test paths but the test runner does not `cd backend/` first. Tests that import `from server import app` or `from fastapi import ...` all fail.

**Solution:**  
Either:  
a) Add `PYTHONPATH=backend` to pytest invocation: `PYTHONPATH=backend python3 -m pytest tests/`  
b) Or add `pythonpath = backend` to `pytest.ini` under `[pytest]`

---

### M5 — Signal engine not injected into order pipeline in production

**File:** `backend/services/order_pipeline.py` line 38; `test_signal_engine_integration_gate_b` failure  
**Finding:**  
The `OrderPipeline` accepts an optional `signal_engine` parameter. In tests, a mock is passed. In production, it is unknown whether a real `SignalEngine` instance is injected. If `self.signal_engine` is `None`, the pipeline falls back to `self.min_edge_bps` (a static default of 10 bps), meaning no real signal analysis is done on trades.

**Solution:**  
Verify the production `OrderPipeline` instantiation injects a `SignalEngine`. Add a startup log message confirming signal engine is active.

---

### M6 — `SMTP_ENABLED=false` — no email alerts

**File:** `backend/.env.example` line 66  
**Finding:**  
Email alerts (system health, trading errors, withdrawal confirmations) are disabled by default. In production, important events will be silently missed. The email confirmation flow for withdrawals is also broken (see C4).

**Solution:**  
Configure SMTP or a transactional email provider (SendGrid, Mailgun) and set `SMTP_ENABLED=true` with credentials.

---

### M7 — `test_order_pipeline_production.py::test_spam_pattern_detection` and `test_rejection_broadcast` fail

**File:** `tests/test_order_pipeline_production.py`  
**Finding:**  
Two additional failures beyond the gate ordering issue:  
- `test_spam_pattern_detection_excessive_cancels` — spam detection is not firing; `assert True is False` suggests the result is succeeding when it should be rejected.  
- `test_rejection_broadcast_to_realtime` — rejection events are not being broadcast to the realtime system.

These indicate the spam detection logic and realtime broadcast on rejections may not be working in production.

**Solution:**  
Investigate `_check_circuit_breaker` spam detection and ensure the rejection broadcast at line 267–272 is being called. Run tests in the backend directory (`cd backend && python3 -m pytest ...`) to confirm.

---

### M8 — Live trading balance in `countdown-to-million` uses paper fallback

*(Duplicate cross-reference — see H3 above. Marked separately because it directly affects the UI trust.)*

---

## 🟢 LOW / INFORMATIONAL

### L1 — `test@example.com` hardcoded in admin context

**File:** `backend/server.py` line 2387  
**Finding:** `user.get('email', 'test@example.com')` — a fallback test email is used in a system context. Low risk if only used as default display value.

---

### L2 — `datetime.utcnow()` deprecation warnings

**File:** `backend/services/order_pipeline.py` line 888  
**Finding:** 3 deprecation warnings for `datetime.utcnow()` in Python 3.12. Should be replaced with `datetime.now(datetime.UTC)` to avoid future breakage.

---

### L3 — `bot_lifecycle.py` root file vs routes file ambiguity

*(Cross-reference H7. Low priority after route is confirmed.)*

---

### L4 — SSE health endpoint is a placeholder

**File:** `backend/routes/system_health_endpoints.py` line 67  
**Finding:**
```python
# 4. SSE Health (placeholder - would need actual SSE connection tracking)
```
The SSE health check is not implemented. This is low risk for go-live as SSE is non-critical.

---

### L5 — Exchange balance placeholder in wallet status

**File:** `backend/routes/wallet_endpoints.py` line 276  
**Finding:**
```python
# Get exchange balances (placeholder for now - will be populated by wallet monitor job)
```
Live exchange balances in wallet status are placeholder. For paper-only go-live this is acceptable.

---

## GO-LIVE READINESS CHECKLIST

### Paper trading tonight — minimum required actions:

| # | Action | Owner |
|---|---|---|
| 1 | Set `JWT_SECRET=<openssl rand -hex 32>` in production `.env` | Ops |
| 2 | Set `ENABLE_SCHEDULERS=true` in production `.env` | Ops |
| 3 | Set `ENABLE_TRADING=true` in production `.env` | Ops |
| 4 | Set `ENABLE_PAPER_TRADING=true` in production `.env` | Ops |
| 5 | Set `ENABLE_LEARNING_LOOP=true` in production `.env` | Ops |
| 6 | Set `ENVIRONMENT=production` in production `.env` | Ops |
| 7 | Confirm `MONGO_URL` points to production MongoDB | Ops |
| 8 | Fund paper wallet via `POST /api/wallet/paper/deposit` after first bot creation | Product |
| 9 | Fix `backend/server.py` line 1809: `env_bool("ENABLE_PAPER_TRADING", True)` | Dev |
| 10 | Fix order pipeline gate order OR update test assertions (C3) | Dev |

### Live trading gate — additional required before enabling live:

| # | Action |
|---|---|
| 11 | Configure SMTP and set `SMTP_ENABLED=true` (email confirmations) |
| 12 | Fix `email_service.py` `confirmation_url` hardcoded domain (C4) |
| 13 | Set `ENABLE_LIVE_TRADING=false` until paper period completes |
| 14 | Confirm exchange API keys are stored for the trading user |
| 15 | Implement live balance fetching for countdown endpoint (H3) |

---

## FILES AUDITED

```
backend/routes/learning_jobs.py
backend/routes/huggingface.py
backend/routes/wallet_hub.py
backend/routes/wallet_endpoints.py
backend/routes/system_status.py
backend/routes/system_mode.py
backend/routes/ai_chat.py
backend/core/feature_flags.py
backend/services/order_pipeline.py
backend/services/signal_engine.py
backend/services/email_service.py
backend/services/email_service_enhanced.py
backend/services/paper_wallet_service.py
backend/services/wallet_summary_service.py
backend/services/learning_loop.py
backend/server.py (selected sections)
backend/auth.py
backend/database.py
backend/config/__init__.py
backend/.env.example
.env.example
frontend/src/hooks/useDashboardState.js
tests/test_order_pipeline_production.py
tests/test_golive_wallet_learning.py
pytest.ini
```

---

*Report generated by full static code audit — no changes made to repository code.*
