# AI Learning & Rules - Quick Reference

## 🧠 AI Learning Components

### 1. AI Super Brain
**File:** `backend/ai_super_brain.py`  
**Function:** Aggregates learning from all bots, generates insights  
**Frequency:** On-demand + daily  
**Status:** ✅ Operational

### 2. Self-Learning System
**File:** `backend/self_learning.py`  
**Function:** Daily trade analysis, learning reports  
**Frequency:** Daily at midnight UTC  
**Status:** ✅ Operational

### 3. Data Storage
**Collections:**
- `learning_data_collection` - Insights and patterns
- `learning_logs_collection` - Learning events log
- `trades_collection` - Source data
- `alerts_collection` - Learning notifications

---

## 📏 Critical Hard-Coded Limits

### Bot Limits
```
GLOBAL MAX: 65 bots
├─ Luno: 5 bots
├─ Binance: 10 bots
├─ KuCoin: 10 bots
├─ Bybit: 10 bots
├─ Kraken: 10 bots
├─ Bitget: 10 bots
└─ Gate.io: 10 bots
```

### Trading Limits (Per Bot)
```
Daily: 50 trades max per bot
Per 10s: 10 orders max (burst protection)
Per minute: 60 orders max
Per day per exchange: 500 orders max
```

### Risk Limits
```
Daily Loss: 5% max of total equity
Position Size (Safe): 25% of bot capital
Position Size (Balanced): 35% of bot capital
Position Size (Risky): 45% of bot capital
Position Size (Aggressive): 60% of bot capital
Asset Exposure: 35% max per asset
Exchange Exposure: 60% max per exchange
Min Trade: R10
```

### Paper → Live Promotion
```
Training Days: 7 minimum
Win Rate: 52% minimum
Profit: 3% minimum
Trades: 25 minimum
Live Training: 24 hours quarantine
```

---

## 🔄 Learning Flow

```
TRADE EXECUTION
    ↓
DATA STORAGE (trades_collection)
    ↓
NIGHTLY ANALYSIS (self_learning.py)
    ├─ Calculate metrics
    ├─ Detect patterns
    └─ Generate AI insights
    ↓
KNOWLEDGE STORAGE
    ├─ learning_data_collection
    ├─ learning_logs_collection
    └─ alerts_collection
    ↓
STRATEGY ADJUSTMENT
    ├─ Update strategies
    ├─ Adjust risk parameters
    └─ Modify position sizing
    ↓
NEXT TRADE (improved)
```

---

## ✅ Verify Learning is Working

### Method 1: Check Database
```javascript
// Last learning log
db.learning_logs_collection.find().sort({timestamp: -1}).limit(1)

// Daily learning data
db.learning_data_collection.find().sort({date: -1}).limit(5)

// Learning alerts
db.alerts_collection.find({type: "learning"}).sort({timestamp: -1})
```

### Method 2: AI Chat
```
"Show me learning insights"
"What patterns have you learned?"
"Show daily report"
```

### Method 3: Admin Panel
- View system-wide learning stats
- Check per-user learning activity
- Monitor strategy adjustments

---

## 🛡️ Safety Gates

### Cannot Trade Without:
1. ✅ Trading mode enabled (`PAPER_TRADING=1` OR `LIVE_TRADING=1`)
2. ✅ Rate limits not exceeded
3. ✅ Risk checks passed
4. ✅ Daily loss limit not hit
5. ✅ For live: Valid API keys

### Automatic Protections:
1. ✅ Burst protection (10 orders per 10s)
2. ✅ Rogue bot detection (15% loss in 1 hour)
3. ✅ Daily loss circuit breaker (5%)
4. ✅ Position size limits
5. ✅ Exposure limits

---

## 🎯 What AI Learns

### Trade Performance
- Win/loss patterns
- Profit per trade
- Best strategies
- Recovery patterns

### Market Conditions
- Bull/bear/sideways
- Volatility patterns
- Best trading times
- Volume correlations

### Asset Performance
- Best pairs
- Correlations
- Liquidity patterns
- Price action

### Risk Management
- Drawdown patterns
- Stop-loss effectiveness
- Position sizing optimization
- Exposure management

---

## 📊 Key Files

```
AI & Learning:
├─ backend/ai_super_brain.py
├─ backend/self_learning.py
├─ backend/ai_memory_manager.py
└─ backend/ai_service.py

Rules & Limits:
├─ backend/config.py
├─ backend/exchange_limits.py
├─ backend/rate_limiter.py
├─ backend/risk_engine.py
└─ backend/utils/trading_gates.py

Trading Logic:
├─ backend/paper_trading_engine.py
├─ backend/autopilot_engine.py
└─ backend/bot_lifecycle.py
```

---

## 🚀 Quick Status Check

### AI Learning: ✅ OPERATIONAL
- Super brain analyzing patterns
- Self-learning running nightly
- Data stored in database
- Insights generated from real trades

### Rules Enforcement: ✅ ACTIVE
- All limits enforced
- Safety gates cannot be bypassed
- Real-time validation
- Automatic protection

### Ready: ✅ YES
- Learning from every trade
- Rules documented
- Systems verified
- Production-ready

---

*For complete documentation, see: `SYSTEM_RULES_AND_AI_LEARNING.md`*
