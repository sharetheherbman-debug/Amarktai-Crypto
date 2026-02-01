# Rule Conflicts & Inconsistencies Analysis

**Analysis Date:** 2026-01-28  
**Status:** 🔴 **CONFLICTS FOUND** - Resolution needed

---

## 🚨 CRITICAL CONFLICTS

### CONFLICT #1: Max Bot Limits (CRITICAL)

**Issue:** Multiple conflicting definitions for maximum bots

**Conflicting Values:**
```python
# config.py (line 128)
MAX_TOTAL_BOTS = 30  # Autopilot setting

# exchange_limits.py (line 20)
MAX_BOTS_GLOBAL = 45  # Total bots across all exchanges

# autopilot_engine.py (2 occurrences)
max_bots = int(os.getenv('MAX_BOTS', 45))  # Uses env or defaults to 45
```

**Impact:** 🔴 HIGH
- Autopilot might try to create 30 bots but system allows 45
- Documentation says 45 but config says 30
- Different parts of system use different limits

**Resolution Needed:**
- ✅ **RECOMMENDED:** Use 45 as the authoritative limit (exchange_limits.py)
- Update config.py MAX_TOTAL_BOTS = 45 OR remove it
- Ensure autopilot_engine.py uses consistent value
- Update all documentation to reflect single source of truth

---

### CONFLICT #2: Per-Bot Trade Limits (CRITICAL)

**Issue:** Different limits in different files

**config.py EXCHANGE_TRADE_LIMITS:**
```python
'luno': {'max_trades_per_bot_per_day': 75}
'binance': {'max_trades_per_bot_per_day': 150}
'kucoin': {'max_trades_per_bot_per_day': 150}
'ovex': {'max_trades_per_bot_per_day': 100}
'valr': {'max_trades_per_bot_per_day': 100}
```

**exchange_limits.py EXCHANGE_LIMITS:**
```python
'luno': {'max_orders_per_bot_per_day': 50}
'binance': {'max_orders_per_bot_per_day': 50}
'kucoin': {'max_orders_per_bot_per_day': 50}
'ovex': {'max_orders_per_bot_per_day': 50}
'valr': {'max_orders_per_bot_per_day': 50}
```

**Impact:** 🔴 HIGH
- Rate limiter uses exchange_limits.py (50 per day)
- Config suggests higher limits (75-150 per day)
- System behavior depends on which file is imported where
- Could allow trades to exceed actual safe limits

**Where Used:**
- `rate_limiter.py` imports from `exchange_limits` → Uses 50
- `config.py` has its own limits → 75-150
- Documentation states both values in different places

**Resolution Needed:**
- ✅ **RECOMMENDED:** Use exchange_limits.py (50) as conservative safe limit
- Remove EXCHANGE_TRADE_LIMITS from config.py OR clearly mark as deprecated
- Update documentation to show 50 per bot per day consistently
- Or: Consolidate into single source file

---

### CONFLICT #3: Duplicate PAPER_TRAINING_DAYS (MEDIUM)

**Issue:** Same variable defined twice in same file

**config.py:**
```python
# Line 56 (in Feature Flags section)
PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))  # Must complete 7 days of paper trading

# Line 117 (in Paper → Live promotion criteria section)
PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))  # Must be 7 days minimum
```

**Impact:** 🟡 MEDIUM
- Redundant definition
- Second definition overwrites first
- Could cause confusion when updating
- Not a functional issue but poor code hygiene

**Resolution Needed:**
- ✅ **RECOMMENDED:** Remove line 56 duplicate
- Keep only line 117 (in the logical section with other promotion criteria)
- Add comment explaining it's used in feature flags too

---

## ⚠️ INCONSISTENCIES

### INCONSISTENCY #4: Documentation vs Code (Trading Limits)

**Issue:** Documentation shows different values than code

**Documentation (SYSTEM_RULES_AND_AI_LEARNING.md):**
```
LUNO: Max orders per bot per day: 50
BINANCE: Max orders per bot per day: 50
KUCOIN: Max orders per bot per day: 50
OVEX: Max orders per bot per day: 50
VALR: Max orders per bot per day: 50
```

**Code (config.py EXCHANGE_TRADE_LIMITS):**
```
Luno: 75
Binance: 150
KuCoin: 150
OVEX: 100
VALR: 100
```

**Impact:** 🟡 MEDIUM
- Developers reading docs get wrong information
- May expect different behavior than actual

**Resolution Needed:**
- ✅ Update documentation to match actual enforced limits (50 from exchange_limits.py)
- OR update code if documentation represents desired state

---

### INCONSISTENCY #5: Naming Convention (trades vs orders)

**Issue:** Inconsistent terminology between files

**config.py uses:**
- `max_trades_per_bot_per_day`

**exchange_limits.py uses:**
- `max_orders_per_bot_per_day`

**Impact:** 🟢 LOW
- Semantically similar but technically different
- "Trade" could mean a complete buy+sell cycle
- "Order" is more atomic (single exchange order)
- Could cause confusion when referencing limits

**Resolution Needed:**
- ✅ Standardize on one term (prefer "orders" as more precise)
- Update all references to use consistent naming

---

### INCONSISTENCY #6: Multiple Profit Thresholds

**Issue:** Different profit-related constants with unclear relationship

**Constants Found:**
```python
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0  # Minimum net profit per trade (ignore below)
MIN_PROFIT_PERCENT = 0.03              # 3% for bot promotion criteria
REINVEST_THRESHOLD_ZAR = 500          # Reinvest profit threshold
```

**Impact:** 🟢 LOW
- These serve different purposes
- Not conflicting, but could be documented better

**Resolution Needed:**
- ✅ Add clarifying comments in code
- Document relationship in README

---

## 🔍 POTENTIAL CONFLICTS (Needs Verification)

### POTENTIAL #7: Risk Percentages Context

**Issue:** Multiple "5%" values used in different contexts

**Occurrences:**
```python
# risk_engine.py - Daily loss limit
max_daily_loss = total_equity * 0.05  # 5% max

# config.py - Stop loss
STOP_LOSS_SAFE = 0.05  # 5%
```

**Status:** ✅ NOT A CONFLICT
- Different purposes (daily loss vs stop loss per trade)
- Intentionally both 5%
- Well separated in code

---

### POTENTIAL #8: Rate Limit Hierarchies

**Issue:** Multiple overlapping rate limits

**Limits Found:**
```
1. Burst: 10 orders per 10 seconds
2. Per minute: 60 orders
3. Per bot per day: 50 orders
4. Per exchange per day: 500 orders (10 bots × 50)
5. Global user per day: 3,000 orders
```

**Status:** ✅ NOT A CONFLICT
- These are hierarchical and all must pass
- Each serves a different purpose
- Intentionally layered for safety

---

## 📊 CONFLICT SUMMARY

| # | Issue | Severity | Files Affected | Needs Fix |
|---|-------|----------|----------------|-----------|
| 1 | Max Bot Limits (30 vs 45) | 🔴 CRITICAL | config.py, exchange_limits.py, autopilot_engine.py | YES |
| 2 | Per-Bot Trade Limits (50 vs 75-150) | 🔴 CRITICAL | config.py, exchange_limits.py, rate_limiter.py | YES |
| 3 | Duplicate PAPER_TRAINING_DAYS | 🟡 MEDIUM | config.py | YES |
| 4 | Documentation vs Code | 🟡 MEDIUM | Documentation files, code | YES |
| 5 | Naming (trades vs orders) | 🟢 LOW | config.py, exchange_limits.py | OPTIONAL |
| 6 | Multiple Profit Thresholds | 🟢 LOW | config.py | OPTIONAL |

---

## 🛠️ RECOMMENDED RESOLUTIONS

### Priority 1: Fix Critical Conflicts

**1. Unify Max Bot Limits**
```python
# RECOMMENDED ACTION:
# In config.py, line 128:
MAX_TOTAL_BOTS = 45  # Must match exchange_limits.py MAX_BOTS_GLOBAL

# OR remove from config.py and import:
from exchange_limits import MAX_BOTS_GLOBAL as MAX_TOTAL_BOTS
```

**2. Unify Trade Limits**
```python
# OPTION A: Use exchange_limits.py as single source
# Remove EXCHANGE_TRADE_LIMITS from config.py
# Import when needed: from exchange_limits import get_exchange_limits

# OPTION B: Consolidate everything into config.py
# Move exchange_limits.py content into config.py
# Update all imports

# RECOMMENDED: OPTION A (exchange_limits.py already actively used)
```

**3. Remove Duplicate PAPER_TRAINING_DAYS**
```python
# In config.py:
# DELETE line 56 (first occurrence)
# KEEP line 117 (in logical section)
```

### Priority 2: Update Documentation

**Update all documentation files to reflect actual enforced limits:**
- Max bots: 45 (not 30)
- Per-bot trades: 50 per day (not 75-150)
- Clarify which file is authoritative

### Priority 3: Add Clarifying Comments

**In code, add comments explaining:**
- Why certain values are set
- Which file is authoritative for each limit
- Relationship between similar-sounding constants

---

## 📋 IMPLEMENTATION CHECKLIST

### Immediate Actions Required:

- [ ] **Fix config.py line 128:** Change MAX_TOTAL_BOTS = 30 to 45
- [ ] **Fix config.py line 56:** Remove duplicate PAPER_TRAINING_DAYS definition
- [ ] **Decide on trade limits:** Either remove EXCHANGE_TRADE_LIMITS from config.py or update exchange_limits.py
- [ ] **Update documentation:** Correct all references to bot limits and trade limits
- [ ] **Verify rate_limiter.py:** Ensure it uses consistent source (currently uses exchange_limits.py)
- [ ] **Update autopilot_engine.py:** Ensure it references correct max bot limit
- [ ] **Add code comments:** Clarify which constants are authoritative

### Testing After Fixes:

- [ ] Test rate limiter with corrected limits
- [ ] Test autopilot bot spawning with unified limit
- [ ] Verify documentation matches code
- [ ] Run integration tests for bot creation

---

## 🎯 SINGLE SOURCE OF TRUTH RECOMMENDATION

**Proposed Structure:**

```python
# exchange_limits.py - AUTHORITATIVE for all exchange-related limits
MAX_BOTS_GLOBAL = 45
BOT_ALLOCATION = {...}
EXCHANGE_LIMITS = {...}  # Per-bot limits: 50 per day

# config.py - AUTHORITATIVE for business logic
PAPER_TRAINING_DAYS = 7  # Promotion criteria
MIN_WIN_RATE = 0.52
MIN_PROFIT_PERCENT = 0.03
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0  # Per-trade minimum
REINVEST_THRESHOLD_ZAR = 500  # Autopilot threshold

# Import exchange limits where needed:
from exchange_limits import MAX_BOTS_GLOBAL, get_exchange_limits
```

**Benefits:**
- Clear ownership of each constant
- No duplication
- Easy to find and update
- Self-documenting through file names

---

## ⚠️ RISKS IF NOT FIXED

### If Max Bot Conflict (30 vs 45) Not Fixed:
- Autopilot might stop at 30 bots while system allows 45
- Users confused about actual limit
- Wasted exchange capacity
- Inconsistent behavior across system components

### If Trade Limit Conflict (50 vs 75-150) Not Fixed:
- Rate limiter might block legitimate trades
- OR rate limiter might allow too many trades
- Risk of exchange API bans
- Unpredictable trade execution

### If Documentation Not Updated:
- Developers make wrong assumptions
- Support tickets from confused users
- Incorrect capacity planning
- Loss of trust in documentation

---

## ✅ VERIFICATION AFTER FIX

**How to verify conflicts are resolved:**

```bash
# 1. Check no duplicate definitions
grep -n "MAX_TOTAL_BOTS\|MAX_BOTS_GLOBAL" backend/*.py

# 2. Check trade limits consistency
grep -n "max_trades_per_bot_per_day\|max_orders_per_bot_per_day" backend/*.py

# 3. Check PAPER_TRAINING_DAYS only defined once
grep -n "^PAPER_TRAINING_DAYS" backend/config.py

# 4. Verify documentation matches code
# Compare documented values with actual code constants
```

---

**Status:** 🔴 **ACTION REQUIRED**  
**Priority:** 🔴 **HIGH** - Fix before production deployment  
**Estimated Effort:** 1-2 hours to fix + test  

---

*Generated: 2026-01-28*  
*Requires immediate attention*
