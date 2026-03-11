# PHASE 0 — FULL BACKEND SYSTEM AUDIT
## Amarktai Crypto — Technical Blocker Map

**Audit Date:** 2026-03-11  
**Branch:** `copilot/repair-backend-truth-engine`  
**Status:** Diagnostic only — no code changes in this document

---

## SECTION 1 — SYSTEM ARCHITECTURE MAP

### Core Execution Path (Paper Mode)

```
User creates bot (POST /api/bots)
    └─ bot stored in MongoDB bots_collection

TradingScheduler (trading_scheduler.py)
    ├─ Tick every 10 seconds (line 52: self.check_interval = 10)
    ├─ Loads all active bots from DB (line 118-121)
    ├─ _fair_queue_order() rotates bot processing order (line 77-86)
    ├─ trade_staggerer.can_execute_now() gate (line 524)
    └─ Dispatches to PaperTradingEngine.execute_smart_trade()

PaperTradingEngine.execute_smart_trade() (paper_trading_engine.py:937)
    ├─ Trading gate (line 941)
    ├─ Rate limiter (line 982)
    ├─ Market data fetch (line 1040)
    ├─ Spread/liquidity gates (line 1054-1082)
    ├─ [FLAG: NEW_TRADING_BRAIN_V2]
    │   ├─ IF TRUE  → _execute_v2_decision() (line 1734) [DISABLED by default]
    │   └─ IF FALSE → V1 pipeline (line 1144+) [ACTIVE]
    ├─ Regime gate (line 1156)
    ├─ Adaptive discipline (line 1190)
    ├─ Edge gate (line 1221)
    ├─ Confidence gate (line 1282)
    ├─ Scalper-specific gates (line 1313, if bot_type==scalper)
    ├─ Expectancy gate (line 1405)
    ├─ Paper wallet balance (line 1440)
    ├─ Risk engine (line 1565)
    └─ Trade record written to trades_collection (line 1658+)

Radar Snapshot (/api/radar/snapshot) — routes/radar.py
    ├─ Loads all active bots for user
    ├─ For each bot: queries trades_collection for open trade (line 342)
    └─ _compute_radar_entry(bot, open_trade) builds radar row

Bot Status (/api/bots/status) — routes/bot_lifecycle.py
    ├─ get_canonical_bot_activity() (line 246)
    ├─ get_canonical_metrics_snapshot() (line 268)
    └─ normalize_bot_state() (line 284) — does NOT read open trades

Recent Trades (/api/trades/recent) — routes/trades.py
    └─ build_trade_record() (line 115) passes through trade fields

Self-Healing (/api/self-healing/status) — routes/self_healing_endpoints.py
    └─ Imports from self_healing.py (root module) NOT engines/self_healing.py
```

### Two Self-Healing Modules (KEY CONFLICT)

```
self_healing.py (ROOT — 225 lines)
    └─ Has get_status() with running/idle/stopped/disabled states
    └─ Imported by: routes/self_healing_endpoints.py

engines/self_healing.py (ENGINE — 251 lines)
    └─ NO get_status() method
    └─ Started by: services/lifecycle.py (line 92: module_path="engines.self_healing")
    └─ Imported by: server.py:1998, autonomous_scheduler.py
```

**These are DIFFERENT instances. Lifecycle starts engines/self_healing, but status endpoint reads self_healing (root). Root is never started → always reports idle.**

---

## SECTION 2 — TRADING ENGINE PIPELINE

### V1 Pipeline (Currently Active — NEW_TRADING_BRAIN_V2=false)

```
execute_smart_trade() @ line 937
│
├─ 1. Trading gate      @ 941    enforce_trading_gates("paper")
├─ 2. Rate limiter      @ 982    rate_limiter.can_trade()
├─ 3. Market data       @ 1040   price, spread, depth
├─ 4. Spread cap        @ 1054   PAPER_MAX_SPREAD_PCT=0.35%
├─ 5. Depth floor       @ 1069   PAPER_MIN_ORDERBOOK_NOTIONAL=50000
│
├─ 6. Regime gate       @ 1156   classify_regime() → strategy_regime_allowed()
│      ├─ ALSO calls legacy market_regime_detector.detect_regime() @ 1085
│      └─ TWO regime sources combined here (ARCHITECTURE RISK)
│
├─ 7. Adaptive standdown @ 1190  derive_adaptive_discipline()
│
├─ 8. Edge gate         @ 1221
│      estimated_cost_pct = fee_roundtrip + slippage_roundtrip + spread_pct
│      edge_required_pct  = estimated_cost_pct + EDGE_BUFFER_PCT (0.15%)
│      For scalper: edge_required = max(edge_req+0.35%, cost*2.25, SCALPER_MIN_EDGE_PCT+uplift)
│      SCALPER_MIN_EDGE_PCT = 1.0% (env default)
│
├─ 9. Confidence gate   @ 1282   compute_entry_confidence() score ≥ threshold
│      Scalper threshold: 0.78 (services/entry_quality.py:4)
│      Normal threshold:  0.68
│
├─10. Scalper-specific  @ 1313   (ONLY if bot_type==scalper)
│      Requires ≥3 confidence sources
│      avg_confidence ≥ SCALPER_MIN_AVG_CONFIDENCE (0.75)
│      Regime confidence check
│      Consensus strength ≥2
│      Direction conflict check
│
├─11. Expectancy gate   @ 1405   evaluate_expectancy_gate() net_edge ≥ required
│      timeout_risk_pct = 0.12 (scalper) vs 0.08 (normal)
│
├─12. Wallet balance    @ 1440   paper_wallet_ledger.get_balance()
├─13. Order validation  @ 1488   min_notional, precision checks
├─14. Risk engine       @ 1565   fixed-fractional sizing, daily loss, drawdown
│
└─15. Trade record      @ 1582   Written with canonical fields:
       symbol, canonical_market_regime, canonical_regime_confidence,
       entry_confidence_score, entry_reason_code="ENTRY_APPROVED"
       NOTE: trade writes "symbol" NOT "pair"
       Ledger writes "pair" = trade_result["symbol"] @ line 2491
```

### V2 Pipeline (DISABLED — NEW_TRADING_BRAIN_V2=false)

```
_execute_v2_decision() @ line 1734
  ├─ AllInCostModel.compute()
  ├─ RegimeScorerV2.score()
  ├─ ScalperContract.check_scalper_readiness()
  ├─ compute_entry_confidence()
  ├─ KellySizingV2.compute()     ← FRACTIONAL KELLY (quarter-Kelly)
  ├─ TradeFeasibilityGate.evaluate()  ← HARD ECONOMIC GATE
  ├─ TargetPolicyV2.compute()    ← ECONOMICS-AWARE TARGETS
  └─ Trade record with all V2 fields
```

---

## SECTION 3 — ROOT CAUSES OF CURRENT PROBLEMS

### Problem 1: Bots chasing tiny profits (~R5 target on R200 position)

**Root cause:** V1 target logic.

In the V1 pipeline, position sizing uses `paper_wallet_ledger.get_balance()` (line 1440-1451). The resulting `paper_capital` feeds into `risk_engine._calculate_max_notional_for_risk()` (line 1544). With a 1-2% risk fraction and a typical stop distance of 0.5%, this produces:

- `risk_amount = paper_capital × 1.5% = R200 × 0.015 = R3`
- `max_notional = risk_amount / stop_distance = R3 / 0.005 = R600`

But `entry_value` is capped by `paper_capital`, so a bot with only R200 in its wallet will have `trade_amount = min(R200, R600) = R200`.

Then `trade_profit_target` from `services/target_policy.py` gives:
- Balanced normal bot: `trade_pct = 0.5%`, `trade_profit_target = R200 × 0.005 = R1.00`

This is within the `MIN_TRADE_PROFIT_THRESHOLD_ZAR = R2.0` floor (line 2367), so it barely survives. But even at R2-R5, the target feels trivially small.

The V2 `TargetPolicyV2` in `services/trading_brain_v2/target_policy.py` would give `min_absolute_target = R5.00` for normal/small/ZAR (line 183) — **but V2 is disabled**.

**Code location:** `config.py:84` — `NEW_TRADING_BRAIN_V2 = os.getenv(..., 'false')`

### Problem 2: Scalpers queued but not producing frequent executions

**Root causes (3):**

A. **Same scheduler queue, priority=0**: Scalpers get `priority=0` identical to normal bots (trading_scheduler.py:528). No preferential queue position.

B. **5-bot-per-tick queue cap**: Only 5 bots per tick get dispatched (implied by staggerer), and with 10-second ticks, if 8+ bots are active, scalpers wait multiple ticks.

C. **Scalper gates are STRICTER than normal gates**: While scalpers need fast turnover, the V1 pipeline applies ADDITIONAL blocks for scalpers:
   - SCALPER_MIN_EDGE_PCT = 1.0% (line 133)
   - Requires ≥3 confidence sources vs ≥2 for normal (line 1313-1327)
   - avg_confidence ≥ 0.75 vs 0.68 (line 1327)
   - Explicit regime confidence check (line 1314)
   - Consensus strength ≥2 (line 1345)
   - Direction conflict check (line 1358)

This means scalpers are MORE likely to be blocked, not less.

### Problem 3: Radar shows symbol: "unknown"

**Root cause (partially fixed in Phase 1, but upstream write issue remains):**

The `_compute_radar_entry()` in `routes/radar.py` was fixed to pull symbol from the open trade's `pair`/`symbol`/`trading_pair` fields. However the root cause was:

- Trades are written with field `"symbol"` (trade_result at line 1586)
- Ledger writes `"pair": trade_result.get('symbol')` (line 2491)
- Radar's initial bot entry uses `bot.get("pair", bot.get("symbol", "unknown"))`

If the bot document doesn't have a `pair` field (which is common for bots created without explicitly setting it), the initial entry starts as `"unknown"`. The Phase 1 fix in radar.py now overrides this from the trade if available — so this is mitigated at the radar layer.

**Remaining risk:** If the open trade in MongoDB has `"pair"` field set but it's empty string or None, the fallback chain resolves to `"unknown"` again.

### Problem 4: Endpoints disagree on regime/confidence/expectancy

**Root cause:** Three different serialization paths exist, none sharing a common truth normalizer:

1. `routes/radar.py` — reads from `open_trade.canonical_market_regime` with fallback chain (Phase 1 improved)
2. `routes/bot_lifecycle.py` — calls `normalize_bot_state()` which reads from bot document only, never from open trade
3. `routes/trades.py` — returns raw trade fields via `build_trade_record()`

The `services/truth_normalizer.py` created in Phase 1 exists but is **not imported by any route yet**. It is a dead module.

### Problem 5: Self-healing logs show activity but status says disabled/idle

**Root cause:** TWO different self_healing modules exist:

- `engines/self_healing.py` (251 lines) — STARTED by lifecycle, logs activity
- `self_healing.py` (225 lines, root) — READ by status endpoint

Lifecycle starts `engines.self_healing.self_healing` (lifecycle.py:92). Status endpoint reads `from self_healing import self_healing` (routes/self_healing_endpoints.py:18). These are separate singleton instances. The lifecycle instance runs, but the status endpoint's instance is never started, so it permanently reports `state: "idle"`.

---

## SECTION 4 — TARGET ECONOMICS ISSUES

### Two Competing Target Calculators

| Calculator | File | Lines | Used by | Default target for R5000 balanced normal bot |
|---|---|---|---|---|
| **V1 Static** | `services/target_policy.py` | 82 | radar.py via `derive_targets()` | Daily=R50, Trade=R25 |
| **V2 Dynamic** | `services/trading_brain_v2/target_policy.py` | 199 | `_execute_v2_decision()` only | Daily=R40, Trade=R20 min |

Both calculators are valid but serve different purposes:
- V1 is used for display (radar, dashboard rendering)
- V2 is used for execution (but ONLY when NEW_TRADING_BRAIN_V2=true, which is disabled)

**Result:** Display targets (V1) and execution targets (V2) are computed separately and may differ.

### Weak Economics in V1 Path

For a Luno BTC/ZAR trade with R200 paper wallet balance:

```
Fee rate (Luno taker):           0.4%
Fee roundtrip:                   0.8%
Slippage roundtrip:              0.16%  (PAPER_SLIPPAGE_BPS=8)
Spread estimate:                 0.06%  (PAPER_SPREAD_BPS=6)
estimated_cost_pct:              1.02%
EDGE_BUFFER_PCT:                 0.15%
edge_required_pct:               1.17%

Paper capital (wallet balance):  R200
Trade amount:                    R200 (full wallet)
Trade profit target (0.5%):      R1.00  ← BELOW MIN_TRADE_PROFIT_THRESHOLD_ZAR (R2)
Trade profit target (1.0%):      R2.00  ← Barely meets threshold
```

So R5 profit on R200 means the ML predicted change is 2.5% and the target was set at 2.5%×R200=R5. The edge gate doesn't prevent this — 2.5% > 1.17% edge requirement. The real problem is that R200 capital is too small to produce meaningful returns.

**The minimum capital for meaningful normal-bot returns is roughly R500-R1000.**

### MIN_TRADE_PROFIT_THRESHOLD_ZAR Usage

`MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0` (config.py:14) is checked at **exit** time (line 2367), not at entry time:

```python
if net_profit > 0 and net_profit < MIN_TRADE_PROFIT_THRESHOLD_ZAR:
    close_reason = "take_profit" if close_reason == "take_profit" else close_reason
```

This check **does not block the trade**. It merely re-labels the close reason. The trade still closes with tiny profit. This is effectively a no-op filter.

---

## SECTION 5 — SCALPER ENGINE ISSUES

### Architecture Assessment: Option D — Using Normal-Bot Logic

Scalpers are routed through the **identical** `trading_scheduler.py` queue and `execute_smart_trade()` entry point. The scalper-specific differences only kick in mid-pipeline via `if bot_type == "scalper":` checks. They are not a separate execution path.

### Scalper Configuration Constants

| Constant | Location | Value | Problem |
|---|---|---|---|
| `SCALPER_MIN_EDGE_PCT` | `paper_trading_engine.py:133` | 1.0% | Higher than normal bot's `EDGE_BUFFER_PCT=0.15%` |
| `SCALPER_MIN_AVG_CONFIDENCE` | `paper_trading_engine.py:134` | 0.75 | Higher than normal's 0.68 |
| `SCALPER_MAX_HOLD_SECONDS` | `exchange_limits.py:59` | 300s | Correct (5 min), but only enforced in V2 |
| `ScalperContract.max_hold_seconds` | `services/trading_brain_v2/bot_contracts.py` | 300s | V2 only (disabled) |

### Scalper Time-Cap Enforcement Status

`services/hold_policy.py:40` correctly handles scalpers:
```python
elif bot_type == "scalper":
    max_hold_seconds = int(SCALPER_MAX_HOLD_SECONDS)  # 300 seconds
```

This is shared by both radar.py and paper_trading_engine.py. **Scalper 5-minute hold is correctly enforced in V1.** ✓

### Scalper Entry Gate Paradox

Scalpers need MORE trades (higher frequency) to compensate for smaller per-trade profit. But the V1 gate actually makes scalpers HARDER to enter than normal bots:

| Gate | Normal | Scalper |
|---|---|---|
| Confidence sources required | ≥2 | **≥3** |
| Avg confidence | ≥0.68 | **≥0.75** |
| Edge uplift | 0% | **+0.35% AND 2.25× cost** |
| Direction conflict | Allowed | **Explicit block** |
| Consensus strength | ≥0 | **≥2** |

The result is scalpers get blocked MORE often than normal bots, producing fewer trades rather than more.

### Scheduler Queue Priority

From `trading_scheduler.py:528`:
```python
await trade_staggerer.add_to_queue(bot_id, exchange, priority=0)
```

All bots have the same priority. Scalpers should have priority > 0 to execute more frequently within each tick.

---

## SECTION 6 — DATA TRUTH INCONSISTENCIES

### Symbol Field Mapping Chain

```
Trade entry (paper_trading_engine.py:1586)
    "symbol": symbol_variable        ← writes "symbol"

Ledger write (paper_trading_engine.py:2491)
    "pair": trade_result.get('symbol')    ← maps "symbol" → "pair"

Bot document (bots_collection)
    "pair": "BTC/ZAR" (if configured)    ← OR missing entirely

Radar snapshot (routes/radar.py:120)
    Initial: bot.get("pair", bot.get("symbol", "unknown"))   ← reads "pair"
    After Phase 1 fix (lines 249-254): 
        trade.get("pair") → trade.get("symbol") → trade.get("trading_pair") → bot fallback
```

**Residual risk:** Radar queries `open_trade` from `trades_collection`. MongoDB trades have `"pair"` field (written at line 2491). So `open_trade.get("pair")` in radar correctly resolves. But if the initial write failed (e.g. None symbol), the ledger "pair" will be None and radar falls back to bot "pair" which might also be missing.

### Regime Field Flow

```
paper_trading_engine.py (trade record, line 1640-1641):
    "canonical_market_regime": canonical_regime.get("regime", "unknown")
    "canonical_regime_confidence": round(float(canonical_regime.get("confidence", 0) or 0), 4)

Radar (routes/radar.py, after Phase 1 fix):
    resolved_regime = (
        open_trade.get("canonical_market_regime")   ← ✓ CORRECT
        or open_trade.get("market_regime")
        or open_trade.get("regime")
        or entry["market_regime"]  ← bot fallback
    )

Bot Status (routes/bot_lifecycle.py):
    Uses normalize_bot_state() which reads from BOT DOCUMENT only
    Does NOT read from open trades
    Regime comes from bot.get("market_regime") ← stale/missing

Recent Trades (routes/trades.py):
    Passes through build_trade_record() which includes canonical_market_regime
    ← CORRECT (raw fields preserved)
```

**Inconsistency:** Bot status endpoint reports bot-level `market_regime` (stale, set when bot last ran analysis). Radar reports trade-level `canonical_market_regime` (set at trade open). Trades report raw trade canonical fields. Three different values for same trade's regime.

### Truth Normalizer Dead Module

`services/truth_normalizer.py` (created in Phase 1) defines `normalize_bot_trade_truth()` and `sanitize_decision_payload()` but is **imported by zero production routes**. It has no effect on the running system.

### NaN Source in Entry Quality

`services/entry_quality.py:30-31`:
```python
+ ((fetchai_confidence / 100.0) * 0.20)
+ ((coinstats_strength / 100.0) * 0.15)
```

If `fetchai_confidence` or `coinstats_strength` are `None` (likely when external API is unreachable), this raises `TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'`. This would propagate as an exception, causing the entire confidence calculation to fail and return an error response. The V1 pipeline at line 1282+ would then have no confidence score, potentially defaulting to 0 and blocking all trades.

---

## SECTION 7 — SELF-HEALING STATUS PROBLEM

### Root Cause: Two Separate Module Instances

The system has two `self_healing` modules that are never the same object:

**Module 1 — `backend/self_healing.py` (root, 225 lines)**
- Class: `SelfHealingSystem` with `get_status()` method (lines 59-86)
- Singleton: `self_healing = SelfHealingSystem()` at end of file
- **Never started** (no caller invokes `.start()` on this instance)
- Status endpoint reads THIS instance (line 18 of self_healing_endpoints.py)
- Always reports: `state: "idle"`, `enabled: false`

**Module 2 — `backend/engines/self_healing.py` (engine, 251 lines)**
- Class: `SelfHealingSystem` — DIFFERENT class, no `get_status()` method
- Singleton: `self_healing = SelfHealingSystem()` at end of file
- **IS started** by `services/lifecycle.py` when `ENABLE_SCHEDULERS=true`
- Logs activity (detect_excessive_loss, detect_stuck_bot, etc.)
- This is the instance that appears "running" in logs

**Result:** The lifecycle starts Module 2, which logs activity. The status endpoint reads Module 1, which never starts. They are completely separate Python objects.

### State Machine Definition

`self_healing.py:68-75`:
```python
if self.is_running:
    state = "running"
elif self.last_result == "stopped":
    state = "stopped"
elif self.last_result == "idle":
    state = "idle"
else:
    state = "disabled"
```

Initial state: `last_result = "idle"` (line 33), `is_running = False`.
→ `get_status()` returns `state: "idle"`, `enabled: false` for a fresh instance.

### ENABLE_SELF_HEALING Flag: Dead Config Variable

`config.py:75`:
```python
ENABLE_SELF_HEALING = os.getenv('ENABLE_SELF_HEALING', 'true').lower() == 'true'
```

This flag is defined but **used nowhere** — not in lifecycle.py, not in server.py, not in either self_healing module. Self-healing startup is gated solely on `ENABLE_SCHEDULERS` (lifecycle.py:94: `enabled_flag="enable_schedulers"`).

---

## SECTION 8 — DEAD / DUPLICATE CODE

### Duplicate Target Calculators

| File | Purpose | State |
|---|---|---|
| `services/target_policy.py` | V1 static percentage-based targets | **Active** — called by radar.py via `derive_targets()` |
| `services/trading_brain_v2/target_policy.py` | V2 economics-aware targets | **Active but gated** — only called if `NEW_TRADING_BRAIN_V2=true` |

Both compute different things for the same concept (bot profit targets). The V1 results are shown on the dashboard. The V2 results control actual trade TP prices when V2 is on. When V2 is off, trade TP prices come from `services/position_lifecycle.py` `compute_position_limits()` which uses a THIRD set of hardcoded percentages (lines 37-43: safe=1%, balanced=1.5%, aggressive=2.5%).

**THREE TP/target systems coexist** for V1 path.

### Duplicate Regime Classifiers

| File | Purpose | State |
|---|---|---|
| `market_regime.py` (root) | Legacy regime detection (old-style) | **Active** — imported at paper_trading_engine.py:1085 |
| `services/regime_classifier.py` | Canonical regime classification | **Active** — imported at paper_trading_engine.py:50 |
| `engines/regime_detector.py` | Another regime system | Unclear if active |

`paper_trading_engine.py` feeds legacy output into canonical classifier:
```python
regime = await market_regime_detector.detect_regime(symbol, exchange)  # legacy
canonical_regime = classify_regime(raw_regime=regime.get("regime"), ...)  # canonical
```

This creates a double-layer regime derivation where the canonical classifier is post-processing legacy output.

### Dead `ENABLE_SELF_HEALING` Flag

`config.py:75` defines `ENABLE_SELF_HEALING = True` by default, but nothing reads this variable. Dead flag that misleads operators.

### Dead `MIN_TRADE_PROFIT_THRESHOLD_ZAR` Filter

`paper_trading_engine.py:2367`:
```python
if net_profit > 0 and net_profit < MIN_TRADE_PROFIT_THRESHOLD_ZAR:
    close_reason = "take_profit" if close_reason == "take_profit" else close_reason
```

This **does not block or reject** the tiny-profit trade — it merely re-assigns the same close_reason back to itself (the conditional is a no-op for `close_reason == "take_profit"`). The filter is effectively dead code.

### Dead `services/truth_normalizer.py`

Created in Phase 1 but imported nowhere. All endpoints still use their own independent field resolution logic.

### Legacy `services/trade_worth_filter.py`

Created in Phase 1. Defines `evaluate_minimum_worthwhile_trade()` but is not called anywhere in `paper_trading_engine.py` or any entry gate. Another dead module.

### Duplicate Entry Quality Guards

Both `services/entry_quality.py:compute_entry_confidence()` and `paper_trading_engine.py:1282-1344` perform confidence gating, creating potential double-checking but also a risk of discrepancy if one is updated and the other isn't.

---

## SECTION 9 — PRIORITY BLOCKERS (Top 10)

### BLOCKER 1 — Self-Healing Truth Disconnect (Severity: HIGH)
**The status endpoint reads a different singleton than the lifecycle starts.**  
`routes/self_healing_endpoints.py:18` imports `from self_healing import self_healing` (root module).  
`services/lifecycle.py:92` starts `engines.self_healing.self_healing`.  
These are separate Python objects — one runs, the other is always idle.  
**Impact:** Self-healing status is permanently misleading.

### BLOCKER 2 — V2 Trading Brain Disabled (Severity: HIGH)
**All V2 improvements (Kelly sizing, TradeFeasibilityGate, TargetPolicyV2) are inactive.**  
`config.py:84`: `NEW_TRADING_BRAIN_V2 = os.getenv(..., 'false')` — disabled by default.  
Phase 1 added the minimum worthwhile trade filter (`services/trade_worth_filter.py`) and truth normalizer (`services/truth_normalizer.py`), but neither is called by any live code path.  
**Impact:** Economics improvements have zero effect on running system.

### BLOCKER 3 — Scalper Hold Time IS Handled in hold_policy (CORRECTION)
**`services/hold_policy.py:40` DOES check `if bot_type == "scalper"` and returns `SCALPER_MAX_HOLD_SECONDS=300`.**  
This was correctly implemented. The hold policy is not a blocker.  
**Replaced by:** Blocker 3 is replaced by the scalper confidence gate paradox below.

### BLOCKER 3 — Scalper Entry Gates Are More Restrictive Than Normal Bot Gates (Severity: HIGH)
**Scalpers require ≥3 confidence sources (normal=2), avg_confidence≥0.75 (normal=0.68), consensus≥2, no direction conflict.**  
`paper_trading_engine.py:1313-1370`: all these checks are ADDITIONAL blocks for scalpers only.  
Scalpers compensate for smaller per-trade profits through higher trade frequency, but these gates reduce their frequency.  
**Impact:** Scalpers fire less frequently than normal bots, defeating their core purpose.

### BLOCKER 4 — Scalper Gates More Restrictive Than Normal (Severity: HIGH)
**Scalpers require stricter entry criteria than normal bots, reducing their trade frequency.**  
`paper_trading_engine.py:1212-1370`: Scalpers need 3 confidence sources (vs 2), 0.75 avg confidence (vs 0.68), no direction conflict, consensus ≥2.  
**Impact:** Scalpers fire less often than normal bots, defeating their purpose.

### BLOCKER 5 — Truth Normalizer Dead Module (Severity: MEDIUM)
**`services/truth_normalizer.py` and `services/trade_worth_filter.py` are not imported anywhere.**  
All Phase 1 logic improvements are inaccessible at runtime.  
**Impact:** Phase 1 economics and truth fixes have no effect.

### BLOCKER 6 — Bot Status Endpoint Has No Trade Data (Severity: MEDIUM)
**`/api/bots/status` builds payload from bot document only, never reading open trades.**  
`routes/bot_lifecycle.py:284`: Calls `normalize_bot_state()` which reads `bot` dict.  
Regime, confidence, symbol all come from bot document (stale, set at analysis time).  
**Impact:** Bot status disagrees with radar which reads from trade canonical fields.

### BLOCKER 7 — Three Competing TP/Target Systems (Severity: MEDIUM)
**In V1 path, take-profit prices come from `services/position_lifecycle.py` (hardcoded %).**  
Display targets come from `services/target_policy.py` (V1 static %).  
V2 targets from `services/trading_brain_v2/target_policy.py` are inactive.  
**Impact:** The TP displayed in radar may not match the actual TP price in the trade record.

### BLOCKER 8 — MIN_TRADE_PROFIT_THRESHOLD_ZAR Is a No-Op (Severity: MEDIUM)
**The profit threshold filter at paper_trading_engine.py:2367 does not block tiny trades.**  
It only re-assigns `close_reason` to the same value it already had.  
`services/trade_worth_filter.py` would fix this but is not called.  
**Impact:** Tiny-profit trades are logged but not prevented.

### BLOCKER 9 — NaN Risk in Entry Quality (Severity: MEDIUM)
**`services/entry_quality.py:30-31` can raise TypeError if fetchai/coinstats return None.**  
`fetchai_confidence / 100.0` with `fetchai_confidence=None` → TypeError, not NaN.  
This causes exception propagation that may result in entry confidence returning 0.  
**Impact:** When external AI services are down, confidence silently collapses, blocking all trades.

### BLOCKER 10 — Dual Regime Classifier (Severity: LOW)
**`paper_trading_engine.py` calls both `market_regime_detector.detect_regime()` and `classify_regime()`.**  
The canonical classifier post-processes legacy output. Any inconsistency in legacy classification flows through to canonical regime.  
**Impact:** Regime classification is opaque — hard to reason about or tune.

---

## SECTION 10 — RECOMMENDED FIX ORDER

The following fixes are listed in priority order for maximum system improvement with minimum risk.

### Fix 1: Wire self_healing_endpoints.py to the correct instance
**File:** `backend/routes/self_healing_endpoints.py`  
**Change:** Import `from engines.self_healing import self_healing` instead of `from self_healing import self_healing`  
**Risk:** Low — the `engines/self_healing.py` doesn't have `get_status()`, so also add it  
**Expected outcome:** Status endpoint reports actual runtime state

### Fix 2: Reduce scalper entry gates to be appropriate for high-frequency trading
**File:** `backend/paper_trading_engine.py`  
**Change:** Scalpers need ≥2 confidence sources (not 3), avg_confidence ≥ 0.70 (not 0.75). Maintain edge gate and direction filters.  
**Rationale:** Scalpers compensate for lower per-trade accuracy through volume. Hold policy already enforces 5-minute cap.  
**Risk:** Medium — more scalper trades; edge gate must still be robust  
**Expected outcome:** Scalpers fire at appropriate frequency while edge quality is maintained

### Fix 3: Reduce scalper entry gates to match scalper economics
**File:** `backend/paper_trading_engine.py`  
**Change:** Scalpers should require ≥2 confidence sources (not 3), avg_confidence ≥ 0.70 (not 0.75)  
**Rationale:** Scalpers compensate for lower per-trade accuracy through volume  
**Risk:** Medium — more scalper trades, need to verify edge gate still blocks bad trades  
**Expected outcome:** Scalpers fire at appropriate frequency

### Fix 4: Give scalpers higher queue priority
**File:** `backend/trading_scheduler.py`  
**Change:** `await trade_staggerer.add_to_queue(bot_id, exchange, priority=1 if is_scalper else 0)`  
**Risk:** Low — affects queue ordering only  
**Expected outcome:** Scalpers execute within each tick instead of waiting multiple ticks

### Fix 5: Wire trade_worth_filter into V1 entry gate
**File:** `backend/paper_trading_engine.py`  
**Change:** Before the trade record is written at line 1582, call `evaluate_minimum_worthwhile_trade()` from `services/trade_worth_filter.py`. Reject if not approved.  
**Risk:** Low — service already exists and is tested  
**Expected outcome:** Tiny-profit trades blocked at entry time, not just logged at exit

### Fix 6: Wire truth_normalizer into bot_lifecycle status endpoint
**File:** `backend/routes/bot_lifecycle.py`  
**Change:** When building bot status payload, use `normalize_bot_trade_truth(bot, open_trade)` to pull live regime/confidence from open trade into status payload  
**Risk:** Low — module exists, function is tested  
**Expected outcome:** Bot status endpoint agrees with radar on regime and symbol

### Fix 7: Fix NaN guard in entry_quality.py
**File:** `backend/services/entry_quality.py:30-31`  
**Change:** `float(fetchai_confidence or 0) / 100.0` and `float(coinstats_strength or 0) / 100.0`  
**Risk:** Very low — defensive None coercion  
**Expected outcome:** No TypeError when external AI services return None

### Fix 8: Enable NEW_TRADING_BRAIN_V2 or migrate V2 gates into V1
**Options:**  
A. Set `NEW_TRADING_BRAIN_V2=true` in `.env` → activates all V2 improvements  
B. Backport `TradeFeasibilityGate` and `TargetPolicyV2` into V1 pipeline  
**Risk:** Medium — V2 changes economics significantly; requires careful testing  
**Expected outcome:** Capital-aware targets, proper absolute profit floors, Kelly sizing

### Fix 9: Retire ENABLE_SELF_HEALING dead flag
**File:** `backend/config.py:75`  
**Change:** Remove or connect `ENABLE_SELF_HEALING` to control the lifecycle entry for self_healing  
**Risk:** Very low — config change only  
**Expected outcome:** Operator can control self-healing via the named env var

### Fix 10: Remove or consolidate duplicate target/regime systems
**Files:** `services/target_policy.py`, `services/trading_brain_v2/target_policy.py`, `services/position_lifecycle.py`  
**Action:** Document which is canonical and retire others or explicitly label them  
**Risk:** Low in documentation-only phase; medium if code is removed  
**Expected outcome:** Single source of truth for target computation

---

## APPENDIX: QUICK REFERENCE — KEY FILE LOCATIONS

| Component | File | Key Lines |
|---|---|---|
| Feature flags | `config.py` | 75-84 |
| V1/V2 branch | `paper_trading_engine.py` | 1123-1143 |
| Scalper gates | `paper_trading_engine.py` | 1212-1370 |
| Edge gate | `paper_trading_engine.py` | 1221-1252 |
| Trade record write | `paper_trading_engine.py` | 1582-1670 |
| Profit threshold | `paper_trading_engine.py` | 2367 |
| Target policy V1 | `services/target_policy.py` | all |
| Target policy V2 | `services/trading_brain_v2/target_policy.py` | all |
| Hold policy | `services/hold_policy.py` | all |
| Trade worth filter | `services/trade_worth_filter.py` | all (unused) |
| Truth normalizer | `services/truth_normalizer.py` | all (unused) |
| Lifecycle startup | `services/lifecycle.py` | 88-120 |
| Self-healing (root) | `self_healing.py` | 59-86 (get_status) |
| Self-healing (engine) | `engines/self_healing.py` | all |
| Self-healing status route | `routes/self_healing_endpoints.py` | 18 |
| Radar symbol fix | `routes/radar.py` | 249-254, 271-298 |
| Bot status | `routes/bot_lifecycle.py` | 217-460 |
| Scheduler | `trading_scheduler.py` | 52, 77-86, 514-529 |
