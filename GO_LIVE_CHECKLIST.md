# Amarktai Network — Go-Live Checklist & Recommended Upgrades

Full audit produced 2026-02-21. This document supersedes notes in UPGRADE_LIST.md for go-live
purposes. Every item is actionable with zero ambiguity.

---

## Legend
- 🔴 **Blocker** — Will break production right now; must fix before go-live
- 🟠 **High** — Significant risk or degraded functionality
- 🟡 **Medium** — Improvement, safe to defer 1-2 weeks
- 🟢 **Low / Roadmap** — Nice-to-have

---

## ✅ Fixed in This PR (Blockers Resolved)

| # | File | What Was Wrong | Fix Applied |
|---|------|---------------|-------------|
| 1 | `engines/sentiment_analyzer.py` | Used `aiohttp` to call OpenAI v0 REST API directly with no key resolver; `import re` unused; `get_overall_sentiment()` missing (called by `compatibility_endpoints.py`) | Rewrote to use **HuggingFace `InferenceClient`** (FinBERT + distilbert fallback) via `get_huggingface_client()`; added `get_overall_sentiment()` method; kept keyword fallback |
| 2 | `routes/websocket.py` | Decoded JWT with its own hardcoded `'your-secret-key-change-in-production'` default instead of using the canonical `JWT_SECRET` from `auth.py` — WebSocket sessions were silently unauthenticated if JWT_SECRET env var not set | Now imports `JWT_SECRET, JWT_ALGORITHM` from `auth.py` |
| 3 | `services/lifecycle.py` | `NightlyLearningScheduler` existed (`services/nightly_learning_scheduler.py`) but was **never registered** in the lifecycle manager — nightly AI parameter tuning never ran | Added `enable_nightly_learning` flag and registered `NightlyLearningScheduler` in subsystem list |
| 4 | `trading_scheduler.py` | `side = 'buy' if random.random() > 0.5 else 'sell'` — trade side was random, producing nonsense P&L and mis-training the learning system | Now uses `regime_detector.detect_regime()` to set side from actual market regime; falls back to `'buy'` (not random) |
| 5 | `engines/ai_model_router.py` | `'balanced': 'gpt-5.1'` — model ID doesn't exist; every balanced/deep AI call failed with 404 from OpenAI | Changed to `'gpt-4o'` / `'gpt-4o-mini'` |
| 4 | `engines/ai_model_router.py` | Used `openai.ChatCompletion.create` (v0 SDK) — throws `AttributeError` with `openai>=1.0` | Rewrote to use `AsyncOpenAI` via resolver _(previous PR)_ |
| 5 | `ai_super_brain.py` | Same v0 API bug as above | Fixed _(previous PR)_ |
| 6 | `self_learning.py` | `self.db.bots` / `self.db.alerts` — wrong collection attribute names → `AttributeError` every daily run | Fixed to `.bots_collection` / `.alerts_collection` _(previous PR)_ |
| 7 | `routes/ai_chat.py` | 8 AI commands existed in backend but were not discoverable by the AI chat engine | Added to `ACTION_REGISTRY` _(previous PR)_ |
| 8 | `paper_trading_engine.py` | `_close_open_trade` returned `None` for both "no exit condition" AND real exceptions; `run_trading_cycle` treated all `None` returns as fatal → spurious `open_trade_close_failed` on every tick where price was between SL/TP | `_close_open_trade` now returns a structured dict (`skip_reason`) for every path. Only `close_exception` marks a trade as failed; `no_exit_signal` just skips the cycle cleanly |
| 9 | `components/LiveTradesPanel.js` | Polling overwrote entire trades state; websocket prepended → reorder/flicker on every poll tick when bots active | Added `mergeTrades` (keyed dedup + stable sort); polling merges rather than overwrites; empty poll responses no longer clear WS-injected trades |
| 10 | `routes/ledger_endpoints.py` | No invariant-check endpoint existed for monitoring | Added `GET /api/ledger/invariants/check` returning `invariant_ok`, drift, available/allocated/total computed from ledger+open trades |

---

## ✅ Go-Live Proof Points

Run the truth-pack script to verify all critical endpoints in one shot:

```bash
BASE_URL=http://localhost:8000 TOKEN=<your-jwt> bash scripts/go_live_truth_pack.sh
```

Expected output on a healthy system:

```
  ✅  PASS  Health ping
  ✅  PASS  Bot status
  ✅  PASS  Recent trades
  ✅  PASS  Ledger fills
  ✅  PASS  Paper wallet
  ✅  PASS  Ledger invariants
  ✅  PASS  HuggingFace test-connection
  ✅  PASS  AI status
  ✅  PASS  Learning status

  ✅  ALL CHECKS PASSED — system is GO-LIVE ready
```

Key invariants that must hold:
- `GET /api/ledger/invariants/check` → `invariant_ok: true` (total == available + allocated, within €0.01)
- `GET /api/trades/recent` → trades sorted newest-first with no duplicate IDs in the response
- `GET /api/learning/status` → `enabled: true` (requires `ENABLE_LEARNING_LOOP=true` env var)
- Paper trading bot cycle → log shows `SKIP_NO_EXIT_SIGNAL` (not `open_trade_close_failed`) when price is between SL and TP

---

## 🔴 Remaining Blockers (Fix Before Go-Live)

### B1 — `auth.py` accepts insecure JWT secret
`JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")` — if the env var is not set, JWTs are
signed with a 14-char default that any attacker can guess. The `startup_self_check()` in
`core/settings.py` does catch this, but `auth.py` itself silently accepts the insecure default
at module import time.

**Fix**: Validate `JWT_SECRET` length ≥ 32 at import time in `auth.py`:
```python
JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    import warnings
    warnings.warn("JWT_SECRET is missing or too short (<32 chars). Authentication is insecure.", RuntimeWarning, stacklevel=1)
```

### B2 — `ml_predictor.py` returns random predictions
```python
confidence = random.uniform(0.6, 0.9)
direction = random.choice(["up", "down", "neutral"])
```
Every AI prediction endpoint returns fabricated values. Any dashboard component or trading
decision that relies on `predict_price` will behave randomly.

**Fix (minimum)**: Source real 24h price change from CCXT for the requested pair and base
the direction on actual momentum. The existing `engines/regime_detector.py` already computes
regime — use it as the signal source.

### B3 — `engines/on_chain_monitor.py` simulates whale transactions
The whale monitor generates synthetic on-chain events with random exchanges and volumes
(`random.choice`, `random.random()`). Alpha Fusion Engine treats these as real signals.

**Fix (minimum)**: Guard with `if not ENABLE_LIVE_TRADING: return []` or mark signal source
as "simulated" and zero-weight it in `AlphaFusionEngine`.

### B4 — `engines/trading_engine_live.py:228-230` — paper trade outcome is randomized
Even in "paper" mode with a real price the exit price uses `random.uniform(1.005, 1.02)`,
meaning every bot's paper P&L drifts based on `random` rather than actual order fills.

**Fix**: Use real CCXT ticker `close` price for exit simulation rather than a random
multiplier. The current price is already fetched on the same line above.

### B5 — CORS wildcard in development fallback
`server.py:422` falls back to `["*"]` when no `CORS_ALLOWED_ORIGINS` is set and
`ENVIRONMENT != "production"`. A misconfigured deploy will silently allow all origins.

**Fix (minimum)**: Log a `CRITICAL`-level message (not just `WARNING`) when wildcard is used,
so it surfaces in any monitoring stack.

---

## 🟠 High Priority (Go-Live Week 1)

### H1 — Sentiment analyzer news source is simulated
`engines/sentiment_analyzer.py::fetch_news()` returns 3 hard-coded fake articles. HuggingFace
sentiment is now wired but there's nothing real to analyze until real news is fetched.

**Fix**: Integrate one free real-time news source. Options:
- **CryptoCompare**: `GET https://min-api.cryptocompare.com/data/v2/news/?lang=EN&api_key={key}` (free tier: 100k calls/month)
- **NewsData.io**: `GET https://newsdata.io/api/1/crypto?apikey={key}&q={coin}` (free tier)
- Add `CRYPTONEWS_API_KEY` / `NEWSDATA_API_KEY` env var, fall back to keyword-only if absent

### H2 — No per-user AI chat rate limiting
The `/api/chat` endpoint has no rate limit. A single user can drain the entire system OpenAI
key. Estimated cost at 1000 token/request and $0.005/1k tokens = $1 per 200 requests.

**Fix**: Add `slowapi` rate limit of e.g. 60 requests/hour per user.

### H3 — `services/signal_engine.py` comment confirms placeholder signal
`signal_engine.py:213` says "In production, this would call engines/alpha_fusion_engine.py"
but currently uses a simpler signal. The trading engine reads this service for order decisions.

**Fix**: Replace the stub with an actual call to `alpha_fusion_engine.get_portfolio_signals()`
or at minimum to `regime_detector.get_current_regime()`.

### H4 — `engines/macro_news_monitor.py` generates fake economic events
`macro_news_monitor.py:337` uses `random.choice(event_templates)` to produce fictional macro
events. These feed into `AlphaFusionEngine.macro_signal` which affects position sizing.

**Fix**: Use real economic calendar API (e.g. `stlouisfed.org/fred` is free for US macro data)
or disable the macro signal (`macro_weight=0`) until a real source is available.

---

## 🟡 Medium Priority (Week 2-4 Post-Launch)

### M1 — No MongoDB health check in `/api/health`
`GET /api/health` does not verify DB connectivity — only checks if the connection object exists.
A stale connection (e.g. MongoDB pod restart) will look healthy until the first query fails.

**Fix**: Add `await db.client.admin.command('ping', serverSelectionTimeoutMS=2000)` inside
the health endpoint and return 503 if it fails.

### M2 — No retry/backoff on OpenAI API calls
Transient 429/500 errors from OpenAI will immediately fail without retry. Use `tenacity`
(already in `requirements.txt`) to add 3 retries with exponential backoff.

### M3 — Prometheus metrics endpoint behind auth
`GET /metrics` requires JWT which breaks standard Prometheus scraping. Move to a separate
internal port (`metrics_port=9090`) or protect with a Bearer secret via env var.

### M4 — `ai_models.py` uses `gpt-4` in `system_ai`
`ai_models.py:139` calls `gpt-4` which has been deprecated and may be expensive. Update to
`gpt-4o-mini` for report generation and reserve `gpt-4o` for trading decisions.

### M5 — No database index migration auto-runner
`backend/migrations/` has several index migration scripts but none are auto-run on startup.
Without correct indexes, large collections (trades, bots) have full table scans.

**Fix**: Wire `run_startup_migrations` to call all migration scripts, not just `fix_user_id_field`.

### M6 — `fetchai_integration.py` returns mock signals when uAgent is unavailable
Falls through to `_mock_signals()` which returns random values. These feed into actual bot
decisions. Mock source should be labeled so alpha fusion weights it at zero.

### M7 — No AI chat rate-limit for streaming endpoint
The SSE streaming endpoint `/api/chat/stream` (if enabled) also lacks rate limiting.

---

## 🟢 Recommended Upgrades (Roadmap — Month 1+)

### R1 — Real LSTM/XGBoost price predictor
Replace `ml_predictor.py`'s `random.uniform` with a real model. Minimum viable:
- Fetch 200 candles from CCXT for the requested pair
- Compute simple momentum features: 5/20/50-period EMA, RSI, ATR
- Use a scikit-learn `GradientBoostingClassifier` trained offline to predict UP/DOWN/NEUTRAL
- Save the model as a pickle, reload at startup

### R2 — Episodic memory with SQLite fallback
`engines/reflexion_loop.py` requires LangChain + Chroma + OpenAI embeddings. When these
are unavailable (no key, no GPU), the memory system is completely disabled.
A SQLite-backed fallback would keep the Reflexion Loop functional at zero cost.

### R3 — Bot-level pair performance learning
Self-learning system currently adjusts `trade_size_multiplier` globally per bot.
Should reduce/increase exposure per pair (e.g. "BTC/ZAR is underperforming — reduce
allocation to that pair while keeping the bot running on ETH/ZAR").

### R4 — Alpha fusion signal weight auto-tuning
`AlphaFusionEngine` weights are static constructor constants (regime=0.25, ofi=0.20, etc.).
The learning system could track which weights produced the best Sharpe ratio and update them
weekly.

### R5 — Real-time exchange error alerting
When CCXT order placement fails (network timeout, invalid signature, insufficient funds),
the error is logged but the user is not notified. Add instant push via the existing alert
system (`db.alerts_collection.insert_one`) and WebSocket broadcast.

### R6 — Dashboard export: trade history CSV
Add `handleExportTrades()` in the frontend and `GET /api/trades/export?format=csv` in the
backend. This is the most-requested feature for tax reporting.

### R7 — Multi-factor auth enforcement for live trading
2FA (`routes/two_factor_auth.py`) is already implemented but not enforced before switching
to live mode. Add a gate: `if not user.totp_enabled: raise 403 before live switch`.

---

## Environment Variables — Complete Reference

### Required (server will refuse to start without these)
```env
MONGO_URL=mongodb://127.0.0.1:27017
JWT_SECRET=<min 32 chars — use: openssl rand -hex 32>
ENCRYPTION_KEY=<Fernet key — use: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

### Required for Live Trading
```env
ENABLE_LIVE_TRADING=true
# At least one exchange API key must be saved via the dashboard API settings page
```

### AI Services (at least one required for full AI features)
```env
OPENAI_API_KEY=sk-...           # GPT-4o for chat, insights, trade analysis
HUGGINGFACE_API_KEY=hf_...      # FinBERT sentiment analysis
```

### Feature Flags (all default to safe/off)
```env
ENABLE_PAPER_TRADING=true       # Default on — safe to always enable
ENABLE_LIVE_TRADING=false       # Set true only when exchange keys are verified
ENABLE_TRADING=false            # Master trading scheduler on/off
ENABLE_AUTOPILOT=false          # Autonomous trading decisions
ENABLE_SCHEDULERS=false         # All background cron schedulers
ENABLE_REALTIME=true            # SSE realtime event streaming
ENABLE_LEARNING_LOOP=false      # Continuous RL-based parameter tuning
ENABLE_NIGHTLY_LEARNING=false   # APScheduler 2 AM learning cycle
ENABLE_SELF_LEARNING=true       # Allow self_learning.py to run
ENABLE_LIVE_LEARNING=false      # Allow learning to modify live bots
ENABLE_AUTOPILOT_GROWTH=false   # Autopilot growth scheduler
ENABLE_AUTOPILOT_REINVEST=false # Autopilot reinvestment scheduler
ENABLE_DAILY_REPORTS=false      # Nightly email report
```

### Email / SMTP (for alerts and reports)
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=<app-specific password>
FROM_EMAIL=your@email.com
FROM_NAME=Amarktai Network
ADMIN_EMAIL=admin@yourdomain.com
```

### Security
```env
ENVIRONMENT=production          # Enables production CORS defaults
CORS_ALLOWED_ORIGINS=https://amarktai.online,https://www.amarktai.online
ADMIN_PASSWORD=<strong password>
```

### Optional Integrations
```env
FETCHAI_API_KEY=               # Fetch.AI uAgent integration
FLOKX_API_KEY=                 # Flokx market alerts
CRYPTONEWS_API_KEY=            # Real crypto news for sentiment (recommended)
```

---

## Startup Verification (Run After Deploy)

```bash
# 1. Health
curl https://your-domain.com/api/health
# Expected: {"status":"healthy","db":"ok",...}

# 2. Readiness (checks JWT, DB, routers)
curl https://your-domain.com/api/health/ready
# Expected: {"status":"ready","ready":true,...}

# 3. Auth round-trip
curl -X POST https://your-domain.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"..."}'
# Expected: {"access_token":"...","token_type":"bearer"}

# 4. HuggingFace connection (after saving HF key in settings)
curl -H "Authorization: Bearer $TOKEN" \
  https://your-domain.com/api/huggingface/test-connection
# Expected: {"status":"success","message":"Connected as ..."}

# 5. AI chat smoke test
curl -X POST https://your-domain.com/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"health check"}'
# Expected: {"reply":"...","action":null}
```

---

## Summary

| Category | Total Items | Blockers (🔴) | High (🟠) | Medium (🟡) | Low (🟢) |
|----------|-------------|--------------|-----------|-------------|----------|
| Fixed this PR | 5 | 5 | 0 | 0 | 0 |
| Fixed previous PRs | 4 | 4 | 0 | 0 | 0 |
| Remaining blockers | 5 | 5 | 0 | 0 | 0 |
| High priority | 4 | 0 | 4 | 0 | 0 |
| Medium priority | 7 | 0 | 0 | 7 | 0 |
| Roadmap | 7 | 0 | 0 | 0 | 7 |
