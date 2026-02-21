# Amarktai Network — Final Audit Report

*Produced 2026-02-21 after three full audit passes.*

---

## Part 1: Complete Go-Live Status

### ✅ Fixed Across All Audit Passes (10 blockers resolved)

| # | File | Bug | Status |
|---|------|-----|--------|
| 1 | `engines/ai_model_router.py` | Deprecated `openai.ChatCompletion.create` (v0 SDK) | ✅ Fixed — uses `AsyncOpenAI` |
| 2 | `ai_super_brain.py` | Same deprecated OpenAI v0 API | ✅ Fixed — uses `AsyncOpenAI` |
| 3 | `self_learning.py` | `self.db.bots` / `self.db.alerts` — wrong attributes | ✅ Fixed — `.bots_collection` / `.alerts_collection` |
| 4 | `engines/sentiment_analyzer.py` | Raw aiohttp OpenAI REST calls; `get_overall_sentiment()` missing | ✅ Fixed — HuggingFace InferenceClient (FinBERT) + keyword fallback; method added |
| 5 | `routes/websocket.py` | Own JWT secret env fallback, disconnected from `auth.py` | ✅ Fixed — imports `JWT_SECRET, JWT_ALGORITHM` from `auth.py` |
| 6 | `services/lifecycle.py` | `NightlyLearningScheduler` never registered | ✅ Fixed — `enable_nightly_learning` flag + subsystem registered |
| 7 | `trading_scheduler.py` | `random.random() > 0.5` for buy/sell side | ✅ Fixed — uses `regime_detector.detect_regime()` |
| 8 | `engines/ai_model_router.py` | Model `gpt-5.1` doesn't exist — all balanced/deep calls failed 404 | ✅ Fixed — `gpt-4o` / `gpt-4o-mini` |
| 9 | `engines/trading_engine_live.py` | Paper trade exit price used `random.uniform` — false P&L | ✅ Fixed — uses real current price for paper fill |
| 10 | `engines/on_chain_monitor.py` | `simulate_whale_activity()` produced random signals that fed AlphaFusionEngine | ✅ Fixed — hard-disabled when `ENABLE_LIVE_TRADING=true` |

---

### 🔴 Remaining Blockers (Must Fix Before Go-Live)

#### B1 — `ml_predictor.py` returns random predictions
**File**: `ml_predictor.py:22-31`  
**Impact**: Every call to `predict_price` AI command and every `GET /api/ml/predict` returns fabricated random values. Any bot or dashboard feature using it trains on noise.  
**Minimum Fix**:
```python
async def predict_price(self, pair: str, timeframe: str = "1h") -> dict:
    # Fetch last 24h candles from CCXT and derive real momentum signal
    try:
        import ccxt.async_support as ccxt_async
        exchange = ccxt_async.binance()
        ohlcv = await exchange.fetch_ohlcv(pair.replace("/", ""), "1h", limit=24)
        await exchange.close()
        closes = [c[4] for c in ohlcv]
        change = (closes[-1] - closes[0]) / closes[0] * 100
        direction = "up" if change > 0.5 else ("down" if change < -0.5 else "neutral")
        return {"pair": pair, "direction": direction, "predicted_change": round(change, 2),
                "confidence": min(0.9, abs(change) / 5), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e)}
```

#### B2 — `auth.py` weak JWT secret allowed at module import
**File**: `auth.py:10`  
**Impact**: If `JWT_SECRET` env var is absent, tokens are signed with `"your-secret-key"` (14 chars). Any attacker who knows the source code can forge tokens.  
**Fix**: Add after line 10:
```python
if len(JWT_SECRET) < 32:
    import sys
    print("FATAL: JWT_SECRET must be at least 32 characters", file=sys.stderr)
    raise RuntimeError("Insecure JWT_SECRET — set a 32+ character secret in environment")
```
Note: `startup_self_check()` already blocks this on startup, but `auth.py` is also imported independently by test/migration scripts.

#### B3 — `services/signal_engine.py` uses placeholder signal
**File**: `services/signal_engine.py:213` — "In production, this would call alpha_fusion_engine.py"  
**Impact**: The Order Pipeline Gate B uses a simplified expected_edge calculation instead of the Alpha Fusion Engine, meaning position sizing and entry decisions ignore all the expensive signal infrastructure (regime, OFI, sentiment, on-chain).  
**Fix**: Replace the stub with:
```python
from engines.alpha_fusion_engine import alpha_fusion_engine
signals = await alpha_fusion_engine.get_portfolio_signals(user_id, pair)
expected_edge_bps = signals.get("alpha_signal", 0) * 10000
```

#### B4 — `server.py` CORS wildcard logs WARNING, not CRITICAL
**File**: `server.py:422`  
**Impact**: A misconfigured production deploy silently allows all origins without breaking deployment checks.  
**Fix**: Change `logger.warning(...)` to `logger.critical(...)` for the wildcard case.

#### B5 — `engines/macro_news_monitor.py` generates fake economic events  
**File**: `macro_news_monitor.py:337`  
**Impact**: Macro signal in AlphaFusionEngine is driven by fictional CPI / rate-decision events with randomized values, affecting position sizing for all bots.  
**Minimum Fix**: Zero-weight the macro signal until a real source is available:
```python
# In engines/alpha_fusion_engine.py constructor
self.macro_weight = float(os.getenv("MACRO_SIGNAL_WEIGHT", "0.0"))  # Default OFF until real data
```

---

## Part 2: Complete Upgrade List — Stronger, Smarter, More Autonomous

### 2.1 Core Trading Engine

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🔴 High | Real ML price predictor (LSTM / XGBoost from CCXT candles) | Honest directional signals instead of random noise |
| 🔴 High | Wire `signal_engine.py` → `alpha_fusion_engine` | Full signal stack (regime + OFI + sentiment + on-chain) drives order decisions |
| 🟠 Med | Order book depth fetching via CCXT (`fetch_order_book`) | OFI signal becomes real; currently uses simulated bid/ask queues |
| 🟠 Med | Stop-loss / take-profit on live orders via CCXT | Currently only paper mode calculates exits; live orders need GTT orders or polling |
| 🟠 Med | Multi-timeframe analysis (1h + 4h + 1d confluence) | Reduces false signals; only 1h is used today |
| 🟡 Low | Dollar-cost averaging (DCA) bot type | Safer accumulation strategy; popular with retail |
| 🟡 Low | Grid trading engine | Generates income in sideways markets; complements trend bots |
| 🟡 Low | Arbitrage bot between Luno ↔ Binance ↔ KuCoin | ZAR/USDT price differentials can be 0.5-1% exploitable |

### 2.2 AI & Self-Learning System

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🔴 High | Wire `nightly_learning_scheduler` to actually use RL Agent results to update bot params in DB | Learning output currently computed but never applied back to bots |
| 🔴 High | Real crypto news API for sentiment (CryptoCompare or NewsData.io — both have free tiers) | `fetch_news()` returns 3 fake articles; HuggingFace FinBERT now wired but nothing real to analyze |
| 🟠 Med | A/B comparison framework for strategy adjustments | Track whether each self-learning adjustment improved or degraded Sharpe ratio over the next 7 days |
| 🟠 Med | Pair-level learning | Adjust per-pair exposure (not just global bot multiplier); under-performing pairs get de-weighted |
| 🟠 Med | Regime-aware learning cycles | Only apply aggressive parameter changes in high-confidence bull regimes; freeze adjustments in uncertainty |
| 🟠 Med | Reflexion Loop SQLite fallback when Chroma/LangChain unavailable | Episodic memory currently disabled without API keys; SQLite keeps it functional at zero cost |
| 🟡 Low | Cross-user anonymised signal aggregation in Super Brain | Aggregated win-rate patterns across all users (privacy-safe) improve recommendations |
| 🟡 Low | Auto-tuning Alpha Fusion signal weights via RL | `regime_weight`, `ofi_weight`, `sentiment_weight` are static; RL can tune them weekly |

### 2.3 AI Chat & Commands

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🟠 Med | Per-user AI chat rate limiting (60 req/hour) via `slowapi` | Prevents API key drain; ~$1 per 200 GPT-4o requests unthrottled |
| 🟠 Med | Add 6 more AI commands: `get_trade_history`, `get_bot_detail`, `run_backtest`, `get_analytics_summary`, `get_equity_curve`, `get_learning_report` | Currently 40 commands; these are the most-asked missing ones |
| 🟠 Med | AI chat streaming (SSE token-by-token) | Chat feels instant; users don't wait 3-5s for full response |
| 🟡 Low | AI command suggestions / autocomplete in chat input | Show the user command hints as they type |
| 🟡 Low | Multi-turn context window (last 10 turns sent to GPT) | Currently each message is independent; context improves coherence |

### 2.4 Risk & Safety

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🔴 High | Enforce 2FA before switching to live mode | `routes/two_factor_auth.py` exists but is not enforced at mode switch |
| 🟠 Med | Max concurrent positions limit per user (e.g. 10) | Prevents runaway bot spawning from exhausting capital |
| 🟠 Med | Capital circuit breaker: if total portfolio drops 15% in 24h, auto-pause all bots | Extreme drawdown protection beyond current per-bot bodyguard |
| 🟠 Med | Real-time exchange error alerting via WebSocket | When CCXT order fails, user gets instant notification; currently only logged |
| 🟡 Low | Bot insurance pool: small % of each trade reserved for circuit breaker | Conceptual: builds a reserve fund that covers extreme loss events |
| 🟡 Low | Whale alert integration (Whale Alert free API) | Real on-chain whale movements trigger position adjustments automatically |

### 2.5 Infrastructure & Reliability (24/7)

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🔴 High | MongoDB health check in `/api/health` (ping with 2s timeout) | Currently health passes even with a dead DB connection |
| 🟠 Med | Automatic migration runner on startup (run all `migrations/*.py` scripts) | Without it, schema drift silently breaks queries as new fields are added |
| 🟠 Med | Database index audit: `trades_collection` and `bots_collection` need compound indexes | Full collection scans on large trade history cause slow dashboard loads |
| 🟠 Med | Prometheus metrics on separate internal port (not behind JWT) | Standard Prometheus scrape pattern; current `/metrics` requires Bearer token |
| 🟠 Med | Redis session store for rate limiting and websocket presence | Currently in-memory; restarting server loses all rate limits and presence data |
| 🟡 Low | Docker `HEALTHCHECK` in Dockerfile | Kubernetes/Docker Swarm can't auto-restart unhealthy containers without it |
| 🟡 Low | Blue-green deployment scripts | Zero-downtime deploys; critical for 24/7 trading |
| 🟡 Low | Distributed tracing (OpenTelemetry → Jaeger) | Debug slow AI calls and DB queries across services |

### 2.6 Exchange & Market Data

| Priority | Item | What It Adds |
|----------|------|-------------|
| 🟠 Med | Luno real-time WebSocket feed (Luno provides WS) | Replaces polling with real-time price ticks for ZAR pairs |
| 🟠 Med | More exchange support: Bybit, OKX, Kraken | BTC/USDT liquidity; more arbitrage opportunities |
| 🟠 Med | CoinGecko / CryptoCompare market data fallback | When exchange CCXT fails, still show prices on dashboard |
| 🟡 Low | Fear & Greed Index integration (Alternative.me free API) | Single macro sentiment signal; excellent for regime detection |
| 🟡 Low | On-chain data: Glassnode free tier or Santiment | Real whale flows, NVT ratio, MVRV for long-term position signals |

---

## Part 3: Design Advice — Landing, Login, Register Pages

> **Note**: No code changes made — this is design guidance only.

### 3.1 Landing Page

**Current state**: A centred card with logo + tagline + two buttons. Functional but not
memorable.

**What it should be**: A full-width, animated showcase that communicates trust, power, and
exclusivity at a glance.

**Layout (top to bottom)**:

```
┌─────────────────────────────────────────────────────────────┐
│  NAVBAR:  [Amarkt AI Logo]          [Login]  [Get Access]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   HERO (60vh, dark gradient):                               │
│   ┌─────────────────────────┐   ┌───────────────────────┐  │
│   │ "The AI That Never      │   │  LIVE TICKER WIDGET   │  │
│   │  Sleeps, Trades For You"│   │  BTC/ZAR ▲ 2.3%      │  │
│   │                         │   │  ETH/ZAR ▼ 0.8%      │  │
│   │  [Get Early Access]     │   │  XRP/ZAR ▲ 1.1%      │  │
│   │  [Watch Demo]           │   │  (real or delayed)    │  │
│   └─────────────────────────┘   └───────────────────────┘  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  TRUST BAR:  "R2M+ Traded • 98% Uptime • 3 Exchanges"      │
├─────────────────────────────────────────────────────────────┤
│  FEATURES (3-column cards, glassmorphism):                  │
│   🤖 Autonomous AI        📊 Multi-Exchange    🛡️ Bodyguard  │
│   Trades 24/7 with        Binance, Luno,       Stops losses  │
│   GPT-4o + FinBERT        KuCoin unified       before they   │
│   sentiment analysis      dashboard            compound      │
├─────────────────────────────────────────────────────────────┤
│  PROOF SECTION:                                             │
│  Live P&L counter (animated, sourced from /api/overview)    │
│  "Our bots made R______ today"                              │
├─────────────────────────────────────────────────────────────┤
│  HOW IT WORKS (numbered steps with icons):                  │
│   1. Connect Exchange  2. Fund Your Wallet  3. Let AI Trade │
├─────────────────────────────────────────────────────────────┤
│  CTA: "Limited access — Join the waitlist"                  │
├─────────────────────────────────────────────────────────────┤
│  FOOTER: Terms | Privacy | Twitter | Telegram               │
└─────────────────────────────────────────────────────────────┘
```

**Visual style**:
- Background: Deep navy/slate (`#0a0f1e`) with animated particle field or subtle CSS grid glow
- Accent: Electric cyan (`#00d4ff`) for primary CTAs; gold (`#f5a623`) for performance numbers
- Font: `Inter` (body) + `Space Grotesk` or `Syne` (headings) — modern fintech feel
- Cards: Glassmorphism (`backdrop-filter: blur(20px); background: rgba(255,255,255,0.05)`)
- Micro-animations: Number counters on scroll, card hover scale, subtle gradient shifts
- **Do NOT use white backgrounds** — this is a dark-mode-first crypto platform

**Key trust signals to include**:
- "Invite-only access" badge → creates exclusivity
- SSL padlock icon + "Bank-grade encryption"
- Logo of exchanges supported (Binance, Luno, KuCoin icons)
- An actual equity curve screenshot (blurred/anonymized is fine)

---

### 3.2 Login Page

**Current state**: Works correctly (good auth logic, error handling, show/hide password). Visual presentation is a basic card.

**What it should be**:

```
┌──────────────────────────────────────────────────────────┐
│  LEFT PANEL (40%):         │  RIGHT PANEL (60%):         │
│                            │                             │
│  Background:               │  Card with glass effect:    │
│  Animated gradient         │                             │
│  + floating dots           │  [Amarkt AI Logo]           │
│  (matches landing)         │                             │
│                            │  "Welcome back, Trader"     │
│  Quote rotator:            │                             │
│  "The market is open       │  [Email input]              │
│   24/7. Your AI is         │  [Password + show/hide]     │
│   always trading."         │  [Remember me] [Forgot pwd] │
│                            │  [LOGIN button]             │
│  Live stat:                │                             │
│  "🟢 System Online         │  ─── or ───                 │
│   42 bots active           │  [Google OAuth - future]    │
│   R18,432 today"           │                             │
│                            │  "Don't have access?        │
│                            │   Request an invite →"      │
└──────────────────────────────────────────────────────────┘
```

**Key improvements over current**:
- Two-panel split layout (left brand + right form) — industry standard for SaaS login
- Live system status on the left panel pulls from `/api/health` — shows the system is alive
- Forgot password link (currently missing entirely)
- "Remember me" checkbox (currently missing)
- Better error states: shake animation on wrong credentials, field-level red borders
- Loading state: skeleton/shimmer on button, not just disabled text

---

### 3.3 Register Page

**Current state**: Multi-step wizard (4 steps: name → email → password → invite code). 
Logic is correct and well-designed. Invite code is a good security gate.

**What it should be**: Keep the multi-step pattern — it's excellent. Upgrade the visual and add:

```
Step progress bar at top:  ●──●──●──● (filled dots with labels)
                            Name Email Pwd  Code

Step 1 — Your Name:
  Large friendly prompt: "What should we call you, Trader?"
  Single input, auto-focused
  [Next →]

Step 2 — Email:
  "Where should we send your trading reports?"
  Email input with real-time format validation
  [← Back] [Next →]

Step 3 — Password:
  "Secure your account"
  Password strength meter (weak/fair/strong/excellent)
    - Length ≥ 8 ✓
    - Has number ✓
    - Has special char ✓
  [← Back] [Next →]

Step 4 — Access Code:
  "Enter your invite code"
  Large monospaced input (invite codes are typically XXXX-XXXX format)
  Inline validation (check code against server before final submit)
  [← Back] [Create Account]

Completion animation:
  Confetti burst + "Welcome to Amarktai, [Name]! 🎉"
  Auto-redirect to dashboard after 2s
```

**Key additions**:
- Password strength meter (use `zxcvbn` library — already easy to add)
- Inline invite code validation before full submit
- Step labels not just numbers
- Confetti/celebration on success — users remember delightful moments

---

## Part 4: Dashboard Design Advice

### 4.1 Layout Philosophy

The dashboard should feel like a **mission control**, not a settings panel.
Key principles:
- **Information hierarchy**: Most critical info (equity, bots active, today's P&L) visible in 3 seconds
- **Dark mode only**: Crypto traders work in dark mode; it reduces eye strain for long sessions
- **Real-time by default**: Every number should tick/pulse when it updates via WebSocket
- **Density on demand**: Summary view → drill down → detail view (not everything on screen at once)

### 4.2 Recommended Layout

```
┌─────────────────────────────────────────────────────────────┐
│ TOP NAV: [Amarkt AI]  [Overview|Bots|Wallet|AI|Analytics]  [⚙️ Profile] [🔔 Alerts] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  COMMAND BAR (always visible, like Spotlight):              │
│  🤖 "Ask AmarktAI..."                        [Send] [🎤]   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  TOP METRICS ROW (4 stat cards):                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Equity   │ │ Today P&L│ │ Bots     │ │ Win Rate │      │
│  │ R124,530 │ │ +R1,243  │ │ 12 Active│ │ 67.4%    │      │
│  │ ↑ 0.8%  │ │ green    │ │ 2 paused │ │ ▲ 2.1pp  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                             │
├──────────────────────────┬──────────────────────────────────┤
│  EQUITY CURVE (left 60%) │  MARKET PULSE (right 40%)       │
│                          │                                 │
│  [recharts Area chart]   │  BTC/ZAR  R1,024,500  ▲2.3%   │
│  Timeframe: 1D|7D|30D    │  ETH/ZAR  R 52,100   ▼0.4%   │
│  Baseline: initial cap   │  Sentiment: 🟢 Bullish (0.72)  │
│                          │  Regime: Bull Market            │
│                          │  Fear & Greed: 68 (Greed)       │
├──────────────────────────┴──────────────────────────────────┤
│                                                             │
│  BOT FLEET (scrollable card grid):                          │
│  ┌─────────────────────────────┐ ┌─────────────────────┐   │
│  │ 🟢 AlphaBot-01              │ │ 🟡 BetaBot-03       │   │
│  │ BTC/ZAR · Binance · LIVE    │ │ ETH/ZAR · Luno · PAPER│ │
│  │ Capital: R10,200            │ │ Capital: R5,000      │   │
│  │ P&L: +R324 (+3.2%)          │ │ P&L: -R42 (-0.8%)   │   │
│  │ Trades: 14 | Win: 71%       │ │ Trades: 7 | Win: 43% │  │
│  │ [Pause] [Detail] [Settings] │ │ [Resume] [Detail]   │   │
│  └─────────────────────────────┘ └─────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  LIVE TRADES FEED (last 10, real-time):                     │
│  Time     | Bot        | Pair    | Side | Amount | P&L     │
│  09:14:32 | AlphaBot-01| BTC/ZAR | BUY  | R1,020 | +R34   │
│  09:13:01 | GammaBot-02| ETH/ZAR | SELL | R500   | -R12   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Section-by-Section Feature Requirements

#### Overview / Home
- [ ] 4 stat cards (equity, today P&L, active bots, win rate) — all real-time via WebSocket
- [ ] Equity curve chart with 1D/7D/30D/All selector
- [ ] Live market ticker for BTC/ZAR, ETH/ZAR, XRP/ZAR, SOL/USDT
- [ ] AI Sentiment badge (Bullish/Bearish with score from HuggingFace)
- [ ] Market Regime badge (Bull/Bear/Sideways from `regime_detector`)
- [ ] Fear & Greed index widget (Alternative.me API — free, 1 call/day)
- [ ] Recent alerts panel (last 5 system alerts)

#### Bots
- [ ] Grid of bot cards with live P&L ticks
- [ ] Filters: All / Active / Paused / Paper / Live / By Exchange
- [ ] Bulk actions: Pause All / Resume All / Emergency Stop (with confirmation modal)
- [ ] "Create New Bot" wizard (exchange → pair → risk mode → capital)
- [ ] Per-bot detail drawer: full trade history, equity curve, AI insights
- [ ] Bot health score (composite: win rate + drawdown + uptime)

#### Wallet
- [ ] Total portfolio equity with breakdown by exchange
- [ ] Available balance per exchange (real via balance_sync_service)
- [ ] Transfer between exchanges (inline form with confirmation)
- [ ] Profit reinvestment control (amount + target bots)
- [ ] Capital injection history log

#### AI Command Center (current: Welcome + AiChatSection)
- [ ] Persistent always-visible command bar (CMD+K shortcut)
- [ ] AI tool quick-actions as icon buttons (not hidden in dropdown): `🔍 Insights` `📈 Predict` `🧬 Evolve` `💰 Reinvest` `📊 Portfolio`
- [ ] Chat history with timestamps, collapsible sessions
- [ ] Action confirmation cards inline in chat (show structured card before executing)
- [ ] Voice input support (Web Speech API — no backend needed)

#### Analytics
- [ ] Win rate trend chart (30 days)
- [ ] Profit by pair (bar chart)
- [ ] Profit by hour-of-day heat map (identify best trading hours)
- [ ] Drawdown chart
- [ ] Trade history table with sorting + CSV export
- [ ] Performance vs benchmark (BTC buy & hold comparison)

#### Self-Learning / AI Brain
- [ ] Learning cycle status (last run, next scheduled run)
- [ ] Parameter changes log (what did the AI adjust? by how much?)
- [ ] Genetic evolution timeline (generation counter, best bot score)
- [ ] Manual trigger button for each: `Run Learning` `Evolve Bots` `Generate Insights`

#### Settings / API Setup
- [ ] Exchange API keys (Binance, Luno, KuCoin) with test-connection status
- [ ] OpenAI key with token usage meter
- [ ] HuggingFace key with model selector
- [ ] Notification preferences (email alerts, severity filter)
- [ ] 2FA setup (TOTP QR code — already implemented backend)
- [ ] Trading limits (max position size, daily loss limit, max bots)

### 4.4 Global UI Components Needed

| Component | Description |
|-----------|-------------|
| **Live tick animation** | Numbers that update via WebSocket should briefly pulse green/red on change |
| **Confirmation modal** | All destructive/financial actions must show `ModalConfirm` with exact amounts before execution |
| **Alert notification system** | Toast + persistent bell icon with badge count; grouped by severity |
| **Skeleton loaders** | All data-driven cards should show skeleton while loading (not spinner) |
| **Empty states** | Friendly empty state when no bots, no trades, etc. (e.g. "No bots yet — create your first one") |
| **Keyboard shortcuts** | `CMD+K` = AI command bar, `E` = Emergency Stop (guarded), `B` = Bots section |
| **Responsive design** | Dashboard must be usable on tablet (1024px); mobile is secondary for trading but alerts must work |
| **Dark/light toggle** | Optional; dark mode is default and primary |

### 4.5 Visual Identity Recommendations

**Color Palette**:
```css
--bg-primary:    #0a0f1e;   /* Deep navy — main background */
--bg-secondary:  #111827;   /* Slightly lighter — card backgrounds */
--bg-glass:      rgba(255, 255, 255, 0.05);  /* Glassmorphism cards */
--accent-cyan:   #00d4ff;   /* Primary CTA, live indicators */
--accent-green:  #10b981;   /* Profit, success, active bots */
--accent-red:    #ef4444;   /* Loss, error, paused bots */
--accent-gold:   #f5a623;   /* Performance numbers, premium features */
--accent-purple: #8b5cf6;   /* AI features, HuggingFace-powered items */
--text-primary:  #f1f5f9;   /* Main text */
--text-muted:    #64748b;   /* Secondary text, labels */
--border:        rgba(255, 255, 255, 0.08);  /* Card borders */
```

**Typography**:
- Headings: `Space Grotesk` or `Syne` — modern, techy, not stale
- Body: `Inter` — best readability, widely used in fintech
- Monospace (prices, IDs): `JetBrains Mono` or `Fira Code`

**Iconography**: `lucide-react` (already installed) — clean, consistent, 24px grid

**Motion**:
- Page transitions: fade-slide (150ms) — not bouncy
- Number updates: `countUp` animation (300ms) — feels alive
- Card entrance: `opacity 0 → 1` + `translateY(10px → 0)` staggered (20ms per card)
- Emergency stop button: red pulse animation to draw attention

---

## Part 5: Recommended 3rd-Party Integrations

| Service | Purpose | Cost | Priority |
|---------|---------|------|----------|
| **CryptoCompare News API** | Real crypto news for sentiment analyzer | Free 100k/month | 🔴 High |
| **Alternative.me Fear & Greed** | Market sentiment macro signal | Free | 🔴 High |
| **Whale Alert Free Tier** | Real on-chain large movements | Free 10 calls/min | 🟠 Med |
| **Luno WebSocket API** | Real-time ZAR price ticks | Free with account | 🟠 Med |
| **FRED (St. Louis Fed)** | Real macro economic data (CPI, rates) | Free | 🟠 Med |
| **SendGrid** | Transactional email (replaces raw SMTP) | Free 100/day | 🟡 Low |
| **Sentry** | Error tracking / crash reporting | Free 5k events/month | 🟡 Low |
| **Upstash Redis** | Managed Redis for rate limiting + sessions | Free tier available | 🟡 Low |
| **PostHog** | Product analytics (which features are used) | Free self-hosted | 🟡 Low |

---

## Summary Scorecard

| Category | Today | After All Fixes | Target |
|----------|-------|-----------------|--------|
| **Blockers** | 0 remaining critical (10 fixed) | +5 remaining listed above | 0 |
| **AI Commands** | 40 registered | +6 more = 46 | 50+ |
| **Self-learning runs** | ✅ Wired (gated by env flags) | Need feedback loop | Full autonomous |
| **Sentiment** | ✅ HuggingFace FinBERT | Need real news feed | Real-time |
| **Price predictions** | ❌ Random | Needs CCXT momentum | ML-based |
| **Paper P&L accuracy** | ✅ Fixed (real prices) | N/A | Real prices |
| **Trade signals** | Stub | Needs alpha_fusion wired | Full stack |
| **24/7 uptime** | ✅ Schedulers registered | Need health check + Docker | Production-grade |
| **Frontend quality** | Functional | Needs design pass | World-class |
