# Amarktai Network — Forensic & Go-Live Consolidated Report

**Date:** 2026-03-09  
**Version:** 1.0  
**Status:** Active

---

## 1. Executive Summary

This document consolidates the forensic audit findings and go-live readiness assessment for the Amarktai Network AI trading platform.  It covers repository clean-up, Market Intelligence Engine integration, risk management enhancements, bot genetics, and the production deployment checklist.

---

## 2. Architecture Overview

### Backend (Python / FastAPI)
- **Entry point:** `backend/server.py`
- **Configuration:** `backend/config.py` (canonical trading gates), `backend/config/settings.py` (feature flags)
- **Engines:** `backend/engines/` — trading, risk, AI learning, regime detection, capital allocation, market intelligence, bot genetics
- **Services:** `backend/services/` — API key management, provider registry, exchange adapter, order pipeline, autonomy heartbeat
- **Routes:** `backend/routes/` — 50+ FastAPI endpoint modules

### Frontend (React 19 / Tailwind)
- **Entry point:** `frontend/src/App.js`
- **Dashboard:** 12 sections (Welcome, API Setup, Bot Management, Bot Fleet, Bot Radar, System Mode, Analytics, Profits, Live Trades, Countdown, Wallet Hub, Profile)
- **State management:** `useDashboardState.js` + SSE via `useRealtime.js`

### Data Stores
- **MongoDB** (Motor async driver) — bots, trades, wallets, API keys, system modes
- **Redis** (optional) — caching, hive-mind shared memory

---

## 3. Market Intelligence Engine

### 3.1 Multi-Provider Price Aggregation

| Provider       | Tier  | Rate Limit              | Use Case          |
|---------------|-------|-------------------------|--------------------|
| CryptoCompare | Primary | 100 k calls/month      | Price, OHLCV, social |
| CoinGecko     | Secondary | 30 req/min, no daily cap | Market overview, prices |
| Coinranking   | Fallback | 10 k calls/month       | Price history       |
| Luzia         | Optional | 100 req/min, 5 k/day   | Real-time streaming |
| CoinMarketCap | Optional | 333 req/day            | Taxonomy only       |

**Note:** Alpha Vantage is explicitly **not recommended** — its 25-request/day free tier is far too restrictive for real-time trading.

### 3.2 Provider Scheduler

The `ProviderScheduler` rotates requests across providers to stay within free-tier limits:
- Tracks monthly and per-minute call counts.
- Switches to the secondary provider when the primary exceeds 70 % of its monthly quota.
- Local LRU cache (60 s TTL) prevents duplicate requests.

### 3.3 Whale Flow Tracking

Sources: Etherscan (ETH transfers ≥ threshold), Glassnode (exchange inflows/outflows), Whale Alert (cross-chain).

### 3.4 Order Book Analysis

`OrderBookAnalyzer` computes bid/ask imbalance, liquidity walls, and spread metrics from CCXT order-book snapshots.

### 3.5 Strategy Selector

Maps market regimes to strategy types:
- Bullish/Calm → Trend Following
- Bearish/Volatile → Mean Reversion
- Squeeze → Breakout
- Volatile → Momentum Scalping
- Panic → Liquidity Sweep

---

## 4. Risk Management Enhancements

### 4.1 Rule Precedence

Risk locks are evaluated in strict order:

1. **Emergency Stop** — global kill-switch
2. **Circuit Breaker** — rapid successive losses
3. **Daily Loss Lock** — cumulative daily loss exceeds `DAILY_LOSS_LIMIT`
4. **Bodyguard Lock** — per-bot protective pause
5. **Training Gate** — 7-day paper training requirement

### 4.2 Dynamic Thresholds

- `DAILY_LOSS_LIMIT` (default 5 % of equity)
- `MAX_DRAW_DOWN` (default 10 % drawdown triggers emergency stop)

### 4.3 Quarantine

Bots that trigger a hard stop-loss are automatically quarantined.  Admin can release via the Admin panel.

---

## 5. Bot Genetics

- **Fitness criteria:** win rate ≥ 55 %, ≥ 10 trades, positive total profit, active status
- **Mutation:** numeric parameters randomised within ±20 %
- **Population cap:** 50 genetic children (configurable)
- Child bots start in `paused` state; operator must activate.

---

## 6. Environment Variables

New keys added to `.env.example`:

```
# Market Data
CRYPTOCOMPARE_API_KEY, COINGECKO_API_KEY, COINRANKING_API_KEY
COINMARKETCAP_API_KEY, LUZIA_API_KEY

# On-Chain & Whale
GLASSNODE_API_KEY, ETHERSCAN_API_KEY, WHALE_ALERT_API_KEY

# Social & News
LUNARCRUSH_API_KEY, CRYPTOPANIC_API_KEY, SANTIMENT_API_KEY, KAIKO_API_KEY

# Risk
DAILY_LOSS_LIMIT=0.05, MAX_DRAW_DOWN=0.10

# Bot Intelligence
BOT_GENETICS_ENABLED=true, HIVE_MIND_ENABLED=true
```

---

## 7. Go-Live Checklist

- [ ] Paper trading runs for ≥ 7 consecutive days with positive PnL
- [ ] `/api/diagnostics/go-live` passes all checks
- [ ] API keys validated for chosen providers
- [ ] Risk thresholds configured (`DAILY_LOSS_LIMIT`, `MAX_DRAW_DOWN`)
- [ ] Provider rotation thresholds set (no provider > 70 % monthly quota)
- [ ] UI shows consistent truth across all panels
- [ ] Advanced execution modules (SOR, arbitrage) disabled by default in live mode
- [ ] Switch to live mode via ChatOps (`set_system_mode live`) with manual monitoring

---

## 8. Testing

- Unit tests for `PriceProvider`, `ProviderScheduler`, `PriceAggregator`, `WhaleFlowTracker`, `OrderBookAnalyzer`, `StrategySelector`, `BotGenetics`, `RiskLockState`, `QuarantineManager`, `DailyLossTracker`
- Integration tests verify signal flow from providers → engine → bots → dashboard
- Existing 59 test files cover auth, trading gates, bot lifecycle, production readiness

---

*This document supersedes all previous forensic and go-live audit reports.*
