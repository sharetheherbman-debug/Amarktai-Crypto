# Amarktai Full Upgrade List

Produced by deep repo audit on 2026-02-21.

---

## Legend
- 🔴 **Critical** — Breaking in production right now or blocks live trading
- 🟠 **High** — Significant degradation without it
- 🟡 **Medium** — Useful improvement, safe to defer
- 🟢 **Low** — Nice-to-have / future roadmap

---

## 1. AI Chat & Command System

### Fixed in this PR
| # | Severity | Item | File |
|---|----------|------|------|
| 1 | 🔴 | **Deprecated OpenAI v0 API** (`openai.ChatCompletion.create` / `openai.api_key`) replaced with `AsyncOpenAI` client — was throwing `AttributeError` with `openai>=1.0` | `ai_super_brain.py`, `engines/ai_model_router.py` |
| 2 | 🟠 | Added 8 missing AI commands to `ACTION_REGISTRY`: `get_portfolio_summary`, `get_win_rate`, `get_drawdown`, `get_countdown`, `trigger_reinvestment`, `delete_bot`, `evolve_bots`, `predict_price` | `routes/ai_chat.py` |

### Still Missing — AI Commands Not Yet Wired
| # | Severity | Missing Command | Backend Exists At | Natural Language |
|---|----------|-----------------|-------------------|-----------------|
| 1 | 🟠 | `run_backtest` | `routes/backtesting.py` | "Backtest this strategy", "Run a backtest from Jan to Mar" |
| 2 | 🟠 | `get_trade_history` | `db.trades_collection` | "Show my recent trades", "Last 10 trades" |
| 3 | 🟠 | `get_bot_detail` | `routes/bot_lifecycle.py` | "Show details for bot Alpha", "What is bot X doing?" |
| 4 | 🟠 | `get_analytics_summary` | `routes/analytics_api.py` | "Analytics summary", "Show me my full stats" |
| 5 | 🟠 | `get_equity_curve` | `routes/analytics_api.py` | "Show equity curve", "Graph my equity" |
| 6 | 🟡 | `rename_bot` | `routes/bot_lifecycle.py` | "Rename bot Alpha to Beta" |
| 7 | 🟡 | `get_alerts` | `db.alerts_collection` | "Show my alerts", "Any warnings?" |
| 8 | 🟡 | `run_learning_cycle` | `engines/self_learning.py` | "Run learning now", "Trigger learning cycle for all bots" |
| 9 | 🟡 | `get_learning_report` | `db.learning_logs_collection` | "What did the AI learn today?", "Show learning report" |
| 10 | 🟡 | `create_countdown_goal` | `routes/user_countdowns.py` | "Set a goal of R50,000 in 90 days" |
| 11 | 🟡 | `get_capital_breakdown` | `routes/analytics_api.py` | "Capital breakdown", "Where is my money?" |
| 12 | 🟢 | `send_test_email` | `routes/daily_report.py` | "Send me a test report email" |
| 13 | 🟢 | `get_exchange_comparison` | `routes/analytics_api.py` | "Compare exchanges", "Which exchange is best?" |
| 14 | 🟢 | `optimize_strategy` | `routes/backtesting.py` | "Optimize my strategy parameters" |

---

## 2. Self-Learning System

### Current State
The platform has **two separate self-learning systems** that are not fully connected:
- `backend/self_learning.py` — older daily analysis system
- `backend/engines/self_learning.py` — newer adaptive parameter tuning engine

### Improvements Needed
| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🔴 | **Fix `adjust_strategies_based_on_learning` bug** | Uses `self.db.bots` (wrong) instead of `self.db.bots_collection` — will fail with `AttributeError` | `backend/self_learning.py:227` |
| 2 | 🔴 | **Fix `generate_weekly_summary` bug** | Uses `self.db.alerts` (wrong) instead of `self.db.alerts_collection` | `backend/self_learning.py:272` |
| 3 | 🟠 | **Consolidate the two self-learning systems** | `backend/self_learning.py` and `backend/engines/self_learning.py` should be unified under one entry point. Currently the `run_daily_learning` in `engines/self_learning.py` is the better one but `SelfLearningSystem` in `backend/self_learning.py` is not always called |
| 4 | 🟠 | **Learning cycle doesn't persist strategy adjustments to DB** | `engines/self_learning.py::apply_adjustments` updates `trade_size_multiplier` and `take_profit_pct` but these fields are not read back by the trading engine in `trading_engine_live.py` or `paper_trading_engine.py` |
| 5 | 🟠 | **No feedback loop from adjustments to results** | After adjustments are applied, there is no mechanism to track whether they improved or degraded performance (A/B comparison) |
| 6 | 🟡 | **Add win-rate trend tracking** | The system computes win rate per-cycle but does not track the trend over time (improving/degrading). Needed for smarter adjustment decisions |
| 7 | 🟡 | **Missing pair-level learning** | Learning only adjusts `trade_size_multiplier` globally per bot. It should reduce/increase exposure on specific underperforming pairs while keeping the bot running |
| 8 | 🟡 | **No schedule integration for `run_daily_learning`** | `services/nightly_learning_scheduler.py` exists but it is unclear if it is started on server boot. Should be wired to `autonomous_scheduler.py` |
| 9 | 🟢 | **Episodic memory (Reflexion Loop)** | `engines/reflexion_loop.py` uses LangChain + Chroma for episodic memory but `LANGCHAIN_AVAILABLE` check disables it when keys are missing. Graceful degradation to SQLite-backed memory would keep it functional |

---

## 3. AI Super Brain (ai_super_brain.py)

| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🔴 | **Fixed: Deprecated OpenAI API** | Was `openai.ChatCompletion.create` — now uses `AsyncOpenAI.chat.completions.create` |
| 2 | 🟠 | **Expand insight analysis window** | Currently only uses last 7 days. Should offer configurable windows (24h, 7d, 30d, all-time) |
| 3 | 🟠 | **Add regime awareness to insights** | `_analyze_patterns` has no market regime context. Should integrate `engines/regime_detector.py` output to contextualize why win rate is what it is |
| 4 | 🟠 | **Cache invalidation is missing** | `insights_cache[user_id]` is set but never expires — stale insights could be served indefinitely |
| 5 | 🟡 | **`_generate_basic_insights` only covers win rate, best pair, best hour** | Should also comment on drawdown, fee drag, and worst performing bots |
| 6 | 🟡 | **No cross-user pattern aggregation** | The super brain analyzes each user in isolation. Aggregated signals (anonymized) could improve recommendations |
| 7 | 🟡 | **`pnl` vs `profit_loss` vs `net_pnl` field inconsistency** | `_analyze_patterns` checks `t.get('pnl', 0)` but the canonical field name is `net_pnl` (with fallback to `profit_loss`) |

---

## 4. AI Model Router (engines/ai_model_router.py)

| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🔴 | **Fixed: Deprecated OpenAI v0 API** | Now uses `AsyncOpenAI` via resolver |
| 2 | 🟠 | **Model names are hardcoded** | `gpt-5.1` is not yet a real model ID. Should use `gpt-4o` or `gpt-4-turbo` until verified | `engines/ai_model_router.py:21-26` |
| 3 | 🟠 | **No retry/backoff on API errors** | A single failed API call raises immediately. Should use `tenacity` (already in requirements) for exponential backoff with max 3 retries |
| 4 | 🟡 | **No token budget tracking** | Each call gets `max_tokens=1000` regardless of context. A token budget manager would avoid overspending on OpenAI |
| 5 | 🟡 | **`confidence: 0.7` is hardcoded** | In `analyze_trade_opportunity` the confidence is hard-coded instead of being extracted from the model's response |

---

## 5. Trading Logic

| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🟠 | **`MLPredictor` uses `random` instead of real ML** | `ml_predictor.py` generates random direction and confidence values — described as "Simplified (would use actual LSTM in production)". Needs real LSTM/XGBoost implementation using historical price data | `ml_predictor.py:19-35` |
| 2 | 🟠 | **`FetchAI` integration uses mock signals** | `fetchai_integration.py:_mock_signals` returns random signals when the FetchAI uAgent is unavailable — production should fail gracefully rather than trade on random data | `fetchai_integration.py:76-101` |
| 3 | 🟠 | **Sentiment analyzer fetches simulated news** | `engines/sentiment_analyzer.py:_fetch_news` is marked "simulated for now" — needs integration with a real news API (CryptoCompare, NewsAPI, or CoinGecko) | `engines/sentiment_analyzer.py:255` |
| 4 | 🟠 | **Backtesting grid-search optimization is stubbed** | `routes/backtesting.py` `optimize_strategy` has `# TODO: Implement full grid search optimization` | `routes/backtesting.py:146` |
| 5 | 🟠 | **`server.py` WebSocket sends mock trade decisions** | `server.py:458-469` explicitly comments "In production, this would come from the actual trading engine / For now, send sample decision data" |
| 6 | 🟡 | **Live balance fetching is placeholder** | `server.py:1597` — "Fallback to simulated if ticker fetch fails" and "implement live balance fetching later" |
| 7 | 🟡 | **`risk_engine.py` asset extraction** | `risk_engine.py:60-61` — asset parameter is assumed from context rather than being explicitly passed, causing potential wrong-pair risk calculations |
| 8 | 🟡 | **`reflexion_loop.py` action handlers are stubs** | The reflexion loop comments "In production: update configuration / update rate limiter / clear connection pool / send pause signal" but takes no actual action | `engines/reflexion_loop.py:390-413` |
| 9 | 🟡 | **`engines/signal_engine.py` uses `alpha_fusion_engine` but comments note it** | `signal_engine.py:213` — "In production, this would call engines/alpha_fusion_engine.py" but currently uses a simpler signal |
| 10 | 🟢 | **Alpha Fusion Engine signal weights are static** | `engines/alpha_fusion_engine.py` weights (`regime_weight=0.25`, `ofi_weight=0.20`, etc.) are constructor constants. They should be tunable per-user and auto-adjusted by the learning system |

---

## 6. Dashboard — Missing Frontend Functions

| # | Severity | Missing Function | Description |
|---|----------|-----------------|-------------|
| 1 | 🟠 | `handleViewBotDetail(botId)` | Navigate to bot detail view with full performance metrics |
| 2 | 🟠 | `handleRunBacktest()` | UI trigger for running a strategy backtest with date range picker |
| 3 | 🟠 | `handleExportTrades()` | Export trade history as CSV |
| 4 | 🟡 | `handleSetGoal()` | Set a financial goal / countdown target via the dashboard |
| 5 | 🟡 | `handleSendTestEmail()` | Trigger a test daily report email |
| 6 | 🟡 | `handleViewLearningReport()` | Open the AI learning report for a specific date |
| 7 | 🟢 | `handleToggleTheme()` | Dark/light mode toggle (CSS variables are ready, just needs wiring) |
| 8 | 🟢 | `handleBulkBotAction(action, botIds)` | Bulk pause/resume/delete multiple bots at once |

---

## 7. Backend Security & Stability

| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🔴 | **JWT secret defaults to `"your-secret-key"`** | `backend/auth.py:10` — if `JWT_SECRET` env var is missing, uses insecure default. Should fail fast with a startup error | `backend/auth.py` |
| 2 | 🟠 | **No input sanitization on bot `name` field** | Bot names are stored and displayed without XSS sanitization. A user could inject `<script>` via bot name | `routes/bot_lifecycle.py` |
| 3 | 🟠 | **`ADMIN_PASSWORD` is not validated at startup** | If empty, admin endpoints silently fail authentication. Should validate at startup | `backend/config.py` |
| 4 | 🟠 | **Transfer amount limit `CHAT_MAX_TRANSFER_AMOUNT` defaults to 10,000** | This is fine as a ceiling but should also validate against actual wallet balance before creating the transfer request | `routes/ai_chat.py` |
| 5 | 🟡 | **Rate limiting is per-exchange for trades but not for AI chat** | The AI chat endpoint has no rate limit — a user could exhaust the OpenAI key. Should add a per-user rate limit (e.g., 60 messages/hour) |
| 6 | 🟡 | **`asyncio.to_thread` replaced with async calls** | Confirmed now using `AsyncOpenAI` in all AI paths — no more blocking threads |

---

## 8. Infrastructure / Ops

| # | Severity | Improvement | Details |
|---|----------|-------------|---------|
| 1 | 🟠 | **No health-check for MongoDB connection** | `GET /api/health` doesn't verify DB connectivity. Should ping MongoDB and surface the failure |
| 2 | 🟠 | **Prometheus metrics endpoint is behind auth** | `GET /metrics` requires JWT which breaks standard Prometheus scraping. Should use a separate port or shared secret |
| 3 | 🟡 | **No database index migration runner** | `backend/migrations/` has migration scripts but they're not auto-run on startup |
| 4 | 🟡 | **Frontend build has 48 high npm vulnerability alerts** | All in dev/test tooling (jest, eslint, ejs, svgo) — not shipped to browser, but should be upgraded |
| 5 | 🟢 | **No Docker health check defined** | `deployment/` directory exists but no `HEALTHCHECK` instruction in Dockerfile |

---

## Summary: Priority Order for Next Sprint

### Immediate (Before Go-Live)
1. ~~Fix OpenAI v0 API calls~~ ✅ **Done this PR**
2. Fix `self_learning.py` attribute bugs (`.bots` → `.bots_collection`, `.alerts` → `.alerts_collection`)
3. Validate JWT_SECRET at startup — refuse to start without it
4. Replace `MLPredictor` random outputs with real price data

### Short-Term (Week 1-2 Post-Launch)
5. ~~Add 8 missing AI commands~~ ✅ **Done this PR**
6. Add remaining 6 high-value AI commands (trade history, bot detail, backtest, analytics summary, equity curve, learning report)
7. Wire `run_daily_learning` into `autonomous_scheduler` startup
8. Add per-user AI chat rate limiting

### Medium-Term (Month 1)
9. Consolidate two self-learning systems into one
10. Integrate real news API for sentiment analyzer
11. Add pair-level learning (not just bot-level adjustments)
12. Implement backtest grid-search optimization (un-stub the TODO)
13. Add frontend `handleRunBacktest()` and `handleExportTrades()`

### Long-Term (Roadmap)
14. Real LSTM/XGBoost price predictor replacing random `MLPredictor`
15. Episodic memory with SQLite fallback when Chroma/LangChain unavailable
16. Cross-user anonymized signal aggregation in super brain
17. Auto-tuning alpha fusion signal weights via learning system
18. A/B comparison of strategy adjustments (track if adjustments helped)
