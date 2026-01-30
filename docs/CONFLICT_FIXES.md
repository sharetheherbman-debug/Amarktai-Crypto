# Rule Conflict Resolution - Quick Fix Guide

## 🎯 FIXES TO IMPLEMENT

### Fix #1: Unify Max Bot Limits ✅

**Problem:** config.py has MAX_TOTAL_BOTS = 30, but exchange_limits.py has MAX_BOTS_GLOBAL = 45

**Solution:**
```python
# config.py line 128
# BEFORE:
MAX_TOTAL_BOTS = 30

# AFTER:
MAX_TOTAL_BOTS = 45  # Must match MAX_BOTS_GLOBAL in exchange_limits.py
```

---

### Fix #2: Remove Duplicate PAPER_TRAINING_DAYS ✅

**Problem:** PAPER_TRAINING_DAYS defined twice in config.py (lines 56 and 117)

**Solution:**
```python
# config.py line 56
# DELETE THIS LINE (keep the one at line 117)
```

---

### Fix #3: Clarify Trade Limits ✅

**Problem:** config.py has EXCHANGE_TRADE_LIMITS with different values than exchange_limits.py

**Solution:**
```python
# Add clarifying comment in config.py above EXCHANGE_TRADE_LIMITS:
# NOTE: These are ASPIRATIONAL limits for future optimization
# ACTUAL enforced limits are in exchange_limits.py (50 per bot per day)
# Rate limiter uses exchange_limits.py as authoritative source
```

---

### Fix #4: Update Documentation ✅

**Problem:** Documentation shows conflicting values

**Solution:**
- Update SYSTEM_RULES_AND_AI_LEARNING.md
- Update AI_LEARNING_QUICK_REF.md
- Ensure all docs show: 45 max bots, 50 trades/bot/day

---

## 📝 IMPLEMENTATION ORDER

1. Fix config.py duplicate PAPER_TRAINING_DAYS (line 56)
2. Fix config.py MAX_TOTAL_BOTS (line 128) 
3. Add clarifying comments about trade limits
4. Update all documentation files
5. Verify no conflicts remain

---

## ✅ VERIFICATION COMMANDS

After fixes:
```bash
# Should show only line 117
grep -n "^PAPER_TRAINING_DAYS" backend/config.py

# Should show 45 in both files
grep -n "MAX.*BOTS.*=" backend/config.py backend/exchange_limits.py

# Should be clear which is authoritative
grep -B2 -A2 "EXCHANGE_TRADE_LIMITS" backend/config.py
```
