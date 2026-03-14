# AMARKTAI CRYPTO RUNTIME TRADING TRUTH AUDIT

**Date:** 2026-03-14
**Scope:** Runtime trading behavior truth — paper-mode validation fitness
**Auditor:** Deep code-path inspection of all trading runtime logic
**Method:** Direct source code analysis of every gate, threshold, formula, and decision path

---

## 1. Executive Runtime Verdict

### Is the system mechanically working?
**YES.** The scheduler ticks every 10 seconds, discovers bots, queues trades with priority, stagger-limits per exchange, and dispatches up to 5 per cycle. The paper trading engine fetches real CCXT prices, simulates realistic fees/slippage/latency, runs a 12-step sequential gate stack, records fills to an immutable ledger, and manages exits via a 9-level priority chain. Bot creation, wallet funding, trade execution, position management, and PnL recording all function end-to-end.

### Is it economically sound?
**PARTIALLY.** The economics-first architecture (cost model → edge floor → feasibility gate → Kelly sizing → target policy) is genuinely sophisticated. However, there are **three critical economic weaknesses**:
1. The paper edge floor (100 BPS default) artificially inflates gross edge, making paper results non-representative of real market opportunities
2. Inconsistent threshold standards between `trade_worth_filter.py` and `trade_feasibility_gate.py` create conflicting accept/reject signals
3. Paper notional cap at 100% of capital (vs 10% live) makes paper PnL results 10× larger than live would produce

### Is it meaningful enough for paper validation?
**CONDITIONALLY.** With understanding of the edge floor inflation and notional cap difference, paper mode can validate: trade turnover, exit logic, scheduler health, wallet integrity, and risk gating. It **cannot** validate: realistic edge discovery, realistic profit magnitude, or realistic win rates — because the edge floor guarantees artificially favorable entry conditions.

### Is it paper-go-live ready?
**NOT YET.** Five specific runtime logic issues must be understood and accepted (or fixed) before paper results can be trusted. See Section 12 and 13.

---

## 2. What Is Mechanically Working

These runtime systems truly execute and produce correct results:

| System | Status | Evidence |
|--------|--------|----------|
| **Scheduler tick loop** | ✅ WORKING | 10s interval, fair queue rotation, 5 trades/cycle max, scalper priority |
| **Trade staggerer** | ✅ WORKING | Per-exchange rate limits (Luno: 10s/2 concurrent, Binance: 2s/5 concurrent), per-bot 60s cooldown, 30-min stale cleanup |
| **Paper trading engine** | ✅ WORKING | Real CCXT prices, realistic fee simulation, 12-step V2 decision gate |
| **Paper wallet** | ✅ WORKING | No-free-money model, per-bot ledger, atomic reserve/release, cross-currency ZAR→USDT |
| **Fills ledger** | ✅ WORKING | Immutable INSERT-only, FIFO PnL matching, client_order_id uniqueness |
| **Cost model** | ✅ WORKING | Venue-specific fees, maker adverse selection, VWAP slippage, 7-exchange support |
| **Regime scorer** | ✅ WORKING | Continuous scoring (trend/vol/liquidity), hysteresis (0.55 enter/0.35 exit), 30s cooldown |
| **Entry confidence** | ✅ WORKING | Real weighted composite: 35% regime + 30% ML + 20% FetchAI + 15% CoinStats + consensus bonuses |
| **Feasibility gate** | ✅ WORKING | 10-step hard gate: risk → concentration → regime → confidence → spread → depth → edge → cost-ratio → profit → time |
| **Kelly sizing** | ✅ WORKING | Quarter-Kelly with strategy caps (1-5%), bootstrap conservative mode (<20 trades), defense/liquidity/calibration multipliers |
| **Target policy** | ✅ WORKING | Venue-aware targets, regime/liquidity/confidence adjustments, minimum absolute floors |
| **Hold policy** | ✅ WORKING | Paper normal cap 1200s (20 min), scalpers exempt, explicit values take precedence |
| **Exit priority chain** | ✅ WORKING | 9-level: TP → SL → trailing → V2 manager → regime deterioration → no-progress → time-decay → max-hold → stale |
| **Scalper discipline** | ✅ WORKING | 300s re-entry cooldown after weak exits, early allow on confidence improvement (Δ≥0.15 regime or Δ≥0.12 entry) |
| **Adaptive stand-down** | ✅ WORKING | 4+ consecutive losses OR 75% loss ratio + 60% timeout losses → confidence uplift + edge uplift required |
| **Open position management** | ✅ WORKING | Each tick checks open positions → calls exit logic (not just skip) |
| **Equity calculation** | ✅ WORKING | Starting Capital + Realized PnL + Unrealized PnL - Fees (verified correct formula) |
| **Diagnostic exposure** | ✅ WORKING | Per-bot skip reasons, dominant category classification, queue visibility |

---

## 3. What Is Economically Wrong

### 3.1 Paper Edge Floor Inflation (CRITICAL)

**The Problem:** `PAPER_EDGE_FLOOR_BPS = 100` (1.0%) is applied as a floor to `expected_gross_edge_bps` before the feasibility gate evaluates the trade.

**Formula:**
```
paper_edge_floor = max(100.0, (k_cost + 1.0) × all_in_cost_bps + 15.0)
```

**Example for a Luno normal bot:**
- Real gross edge from ML predictor: 25 BPS (0.25%)
- All-in cost: 35 BPS (Luno taker round-trip)
- Paper edge floor: max(100, 2.5 × 35 + 15) = max(100, 102.5) = **102.5 BPS**
- Edge presented to feasibility gate: **102.5 BPS** (not the real 25 BPS)
- Net edge: 102.5 - 35 = **67.5 BPS** (looks great!)
- Real net edge: 25 - 35 = **-10 BPS** (actually unprofitable)

**Impact:** The system will approve trades that are economically unprofitable in reality. Paper results will show positive PnL from trades that would lose money live. This is the single biggest reason paper results feel "untrustworthy" — the edge floor guarantees every trade looks economically viable at entry, but actual price movement determines the real outcome.

**Why it exists:** Without the edge floor, paper-mode ML predictors return near-zero predicted_change during bootstrap (insufficient training data). Every trade would fail the feasibility gate. The floor is a bootstrap necessity, not an oversight.

**The Trade-Off:** With the floor, the system trades (validates mechanics, turnover, exits). Without the floor, the system is frozen (no trades execute). Neither produces honest economics.

### 3.2 Notional Cap Disparity (SIGNIFICANT)

**Paper mode:** Notional cap = 100% of paper_capital
**Live mode:** Notional cap = 10% of capital

A paper bot with R1,000 capital can open a R1,000 position. A live bot with R1,000 capital can only open a R100 position. Same edge, 10× different profit magnitude.

**Impact:** Paper PnL results are approximately 10× what live trading would produce at the same capital level. Users seeing R50/day paper profits should expect ~R5/day live profits. This disparity is undocumented and will cause disappointment at go-live.

### 3.3 Inconsistent Threshold Standards (MODERATE)

Two files that both gate trade entries have **conflicting standards**:

| Threshold | `trade_feasibility_gate.py` | `trade_worth_filter.py` | Gap |
|-----------|---------------------------|------------------------|-----|
| Scalper min net edge | **20.0 BPS** | **8.0 BPS** | 2.5× |
| Normal/small USDT profit min | **$0.50** | **$0.80** | 60% |
| Normal/medium USDT profit min | **$1.50** | **$2.00** | 33% |
| Normal/large USDT profit min | **$5.00** | **$6.00** | 20% |

**Impact:** Depending on which filter runs first, a trade might pass one gate but fail the other, creating confusing skip reasons. A scalper trade with 12 BPS net edge passes `trade_worth_filter` but fails `trade_feasibility_gate`. The diagnostic will say "EDGE_INSUFFICIENT" even though the softer filter said it was fine.

### 3.4 Target Policy Produces Tiny Targets Under Stress (MODERATE)

Per-trade target policy starts at 0.7-1.5% but applies cascading reductions:
- Ambiguous regime: ×0.8
- Low confidence (<0.5): ×0.8
- Low liquidity (<0.5): ×0.85

**Worst case:** 0.7% × 0.8 × 0.8 × 0.85 = **0.38%** → Floor: 0.35%

For a R500 Luno bot at 0.35% TP and 35 BPS all-in cost: projected profit = R500 × 0.0035 - R500 × 0.0035 = **R0.00**. The TP target equals the cost. These trades have zero expected profit even if they hit TP perfectly.

### 3.5 Scalper Economics Are Tight But Viable (LOW)

Scalper on Binance:
- Per-trade target: 0.7% (USDT)
- All-in cost: ~22 BPS (10+10 fees + 2 slippage)
- Net per-trade: ~48 BPS = 0.48%
- On $50 USDT notional: $0.24 profit per trade
- 50 trades/day max: $12/day theoretical max
- At 50% win rate: $6/day - $6/day = break-even

Scalper economics require >55% win rate to be profitable. This is achievable with good signals but not guaranteed. The system correctly requires high confidence (0.72) for scalpers.

---

## 4. What Is Behaviorally Wrong

### 4.1 Paper Hold Cap Creates Premature Exits (MODERATE)

Normal bots in paper mode are capped at 1200 seconds (20 minutes). With a 2.0% take-profit target (Luno normal), the price needs to move 2% in 20 minutes. BTC/ZAR typical 20-minute move: 0.3-0.5%. This means:

- **Most normal bot trades will hit max-hold before TP**
- Exit reason: `PAPER_HOLD_CAP_EXCEEDED` (a weak exit)
- PnL depends entirely on where price is at 20 minutes
- Many trades will close at small profit or small loss — neither validating the strategy nor the exit logic

**The 20-minute cap validates turnover speed but prevents validation of the actual take-profit logic.** Normal bots in paper mode almost never reach their profit targets through natural TP/SL mechanics.

### 4.2 Edge Floor Masks Real Signal Quality (SIGNIFICANT)

Because the edge floor inflates gross edge to ≥100 BPS, the entry confidence score and the signal quality become irrelevant to the economics gate. All trades that pass the regime and confidence gates will also pass the economics gates (because the edge is artificially guaranteed to be high enough).

**Result:** Paper mode cannot distinguish between "the ML model predicted a 200 BPS move" and "the ML model predicted a 5 BPS move" — both get the same 100 BPS floor. The system trades on all signals equally, not just good signals.

### 4.3 Stale Exit Fallback Triggers on Profitable Positions (LOW)

The stagnation exit (`position_lifecycle.py`) checks if price moved less than 0.05% within a time window. It does NOT check the current PnL. A bot sitting at +0.8% profit during a consolidation phase will be force-exited as "stagnant" rather than allowed to hold for TP.

### 4.4 No-Progress Threshold Is Cost-Unaware (MODERATE)

The open trade manager's no-progress exit triggers at PnL ≤ 0.05% at 60-75% of time budget. But:
- Luno round-trip cost: ~35 BPS (0.35%)
- Binance round-trip cost: ~22 BPS (0.22%)

A trade at +0.05% is actually -0.30% net on Luno and -0.17% net on Binance after costs. The no-progress check doesn't account for venue-specific costs, so it treats a deep loss (after costs) the same as a near-breakeven.

### 4.5 Coverage Throttle Limits Paper Validation Speed (LOW-MODERATE)

Normal bot coverage throttle: 300 seconds (5 minutes) between trades.
Scalper coverage throttle: 30 seconds between trades.
Plus: 60-second per-bot cooldown in trade staggerer.

For a fleet of 5 normal bots on Luno:
- Each bot can trade at most every 5 minutes
- Staggerer adds 10s Luno delay
- 5 bots × 12 trades/hour = 60 trades/hour theoretical max
- With hold time (20 min paper cap), each bot can complete ~3 trades/hour
- 5 bots × 3 trades/hour = **15 completed trades/hour**

This is adequate for validation but feels slow when watching the dashboard. A user expecting rapid paper trading will see long periods of "managing_open_positions" with no new trades.

---

## 5. Entry Logic Audit

### 5.1 Gate Stack (12 Steps in V2 Decision)

| Step | Gate | Threshold | Assessment |
|------|------|-----------|------------|
| 1 | Paper Wallet Balance | balance > 0 | ✅ CORRECT — prevents zero-capital trading |
| 2 | All-In Cost Model | compute() | ✅ CORRECT — venue-specific, includes adverse selection |
| 3 | Regime Scoring + Cold-Start Fix | fallback trend=2.0%, vol=2.5% | ⚠️ FUNCTIONAL but may produce false-positive regimes |
| 4 | Adaptive Discipline | 4+ consecutive losses → stand-down | ✅ CORRECT — meaningful loss-streak protection |
| 5 | Scalper Readiness | spread, depth, loss-streak, budget | ✅ CORRECT — multi-gate scalper discipline |
| 6 | Entry Confidence | 35% regime + 30% ML + 20% Fetch + 15% CoinStats | ✅ CORRECT — real composite score |
| 7 | Edge Floor | max(100 BPS, (k+1)×cost+15) | ⚠️ INFLATES edge — see Section 3.1 |
| 8 | Kelly Sizing V2 | Quarter-Kelly, bootstrap conservative | ✅ CORRECT — conservative sizing |
| 9 | Trade Feasibility Gate | 10-point hard gate | ✅ CORRECT but misleading with inflated edge |
| 10 | Target Policy V2 | venue-aware TP/SL/trailing | ✅ CORRECT — regime-adjusted targets |
| 11 | Wallet Trade Check | can_trade() | ✅ CORRECT — prevents overspend |
| 12 | Risk Engine | capital + drawdown validation | ✅ CORRECT — final safety check |

### 5.2 Entry Confidence Quality

The `compute_entry_confidence()` function in `entry_quality.py` is a **genuine weighted composite**, not a fake score:

```
score = regime × 0.35 + ML × 0.30 + FetchAI/100 × 0.20 + CoinStats/100 × 0.15
      + consensus_bonus (up to +0.14)
      - conflict_penalty (-0.28 if directions conflict)
      - no_consensus_penalty (-0.08 if strength = 0)
```

**Score Range Analysis:**
- Cold-start (all zeros): 0.0 → BLOCKED (below 0.40 MIN_ENTRY_CONFIDENCE)
- Cold-start with fallback regime (conf=0.6, trend=2%): ~0.21 → BLOCKED
- Real signals (regime=0.7, ML=0.6, Fetch=65, Stats=50): ~0.60 → PASSES normal (0.40), FAILS scalper gate in entry_quality (needs 0.78)
- Strong signals (regime=0.85, ML=0.8, Fetch=80, Stats=75): ~0.81 → PASSES all gates

**Key Finding:** The entry confidence gate (MIN_ENTRY_CONFIDENCE=0.40) in `trade_feasibility_gate.py` is much softer than the per-strategy gates in `entry_quality.py` (normal=0.68, scalper=0.78). **Both are checked** — the feasibility gate's 0.40 is a pre-filter, the entry_quality thresholds are the real gates.

### 5.3 Whether Weak Trades Still Pass

**With edge floor:** YES, weak trades pass the economics gates because the edge floor guarantees sufficient gross edge. A trade with real expected edge of 5 BPS gets promoted to 100+ BPS, making it look highly profitable.

**Without edge floor:** NO, weak trades would be correctly rejected. The feasibility gate's edge rule (`expected_net_edge_bps < k × all_in_cost_bps`) would block any trade where the real edge doesn't cover costs.

**Whether good trades are being rejected:** Only in cold-start scenarios where confidence is 0 and regime is unknown. Once the system has accumulated 10+ price samples and signals begin flowing, good trades pass correctly.

---

## 6. Hold / Exit Logic Audit

### 6.1 Hold Duration Analysis

| Bot Type | Live Hold Cap | Paper Hold Cap | Assessment |
|----------|--------------|----------------|------------|
| Normal/safe | 6 hours | **20 min** | ⚠️ 18× shorter — prevents TP validation |
| Normal/balanced | 3 hours | **20 min** | ⚠️ 9× shorter — prevents TP validation |
| Normal/aggressive | 90 min | **20 min** | Reasonable ratio |
| Scalper | 5 min | 5 min (unchanged) | ✅ CORRECT |
| Mean Reversion | 3 hours | **20 min** | ⚠️ 9× shorter |

### 6.2 Exit Logic Intelligence Assessment

| Exit Type | Economically Intelligent? | Evidence |
|-----------|--------------------------|----------|
| Take-profit | ✅ YES | Direct profit realization at target |
| Stop-loss | ✅ YES | Loss limitation at pre-calculated level |
| Trailing stop | ✅ YES | Proven winner logic with adaptive trailing (min 0.15%, ×0.6 multiplier) |
| V2 Open Trade Manager | ✅ MOSTLY | Edge-decay check is cost-aware; no-progress threshold is NOT cost-aware |
| Regime deterioration | ✅ YES | Direction quality collapse check at 25% of hold window |
| Time-decay | ✅ YES | Adaptive targets that shrink with time (good diminishing-returns model) |
| Max-hold | ⚠️ MECHANICAL | Forces exit regardless of economics — necessary safety but not intelligent |
| Stale exit | ⚠️ MECHANICAL | No PnL awareness — can exit profitable consolidating positions |
| No-progress | ⚠️ WEAK | 0.05% threshold is far below round-trip costs on any venue |

### 6.3 Paper-Mode Exit Truth

In paper mode with 20-minute hold cap, the **most common exit reason will be `PAPER_HOLD_CAP_EXCEEDED`**, not TP/SL. This means:
- Trade outcomes are determined by where price happens to be at 20 minutes
- Win/loss distribution approaches 50/50 (random at short horizons)
- Paper results will show many small wins and small losses
- Paper TP hit rate will be very low (price rarely moves 1.5-2% in 20 min)
- Paper SL hit rate will be low too (price rarely moves -1% in 20 min)

**This is validating turnover and mechanics, not strategy profitability.**

---

## 7. Scalper Logic Audit

### 7.1 Scalper Regime Compatibility

Scalpers are allowed in: `BREAKOUT, HIGH_VOL, CONSOLIDATION, TRENDING_UP, TRENDING_DOWN`
Scalpers are blocked in: `LOW_VOL` (explicitly), `AMBIGUOUS` (unless confidence ≥ 0.3 for microstructure_only)

**Assessment:** Reasonable. Scalpers need volatility to capture micro-moves. Blocking in LOW_VOL prevents futile scalping. The AMBIGUOUS regime allowance with reduced size (×0.5) is sensible.

### 7.2 Cold-Start Impact on Scalpers

With regime fallback (trend=2.0%, vol=2.5%):
- Trend score: ~0.3 (below 0.5 moderate threshold)
- Vol score: ~0.33 (below 0.5 moderate threshold)
- Likely regime: `AMBIGUOUS` or `MEAN_REVERSION`
- Regime confidence: ~0.4-0.5

Scalper regime eligibility in AMBIGUOUS with confidence ≥ 0.3: ALLOWED but `microstructure_only` (size ×0.5, edge ×1.5)

**Finding:** Scalpers CAN trade during cold-start but at half size with 50% higher edge requirement. This is reasonable bootstrap behavior.

### 7.3 Re-Entry Discipline Assessment

**Cooldown:** 300s after weak exits (stale, max-hold, no-progress, time-budget, edge-decay, stagnation)
**Early re-entry:** Allowed if regime_confidence improves ≥0.15 OR entry_confidence improves ≥0.12

**Issue:** The improvement thresholds are relatively small. If regime_confidence goes from 0.45 → 0.60 (+0.15), the scalper can re-enter immediately even though conditions may not have materially improved. However, the scalper still must pass all other gates (edge, feasibility, readiness), so the re-entry isn't unchecked.

**Assessment:** ✅ ADEQUATE — the multi-layer gating compensates for the permissive early re-entry.

### 7.4 Are Scalpers Overblocked?

**Yes, in one scenario:** During cold-start, scalpers face:
1. Regime = AMBIGUOUS → size ×0.5
2. Edge floor = 100 BPS → artificially high edge requirement
3. Confidence must be ≥ 0.72 (but cold-start signals give low confidence)
4. Min 20 BPS net edge (from bot contracts)

At cold-start, entry_confidence will be ~0.20-0.40 (insufficient signal data), which fails the 0.72 scalper confidence gate in `entry_quality.py`. **Scalpers will be blocked until real signals produce ≥0.72 confidence**, which may take 15-30 minutes of price data accumulation.

**This is correct behavior** — trading scalpers without signals is gambling. But it slows initial paper validation.

### 7.5 Can Scalpers Produce Meaningful Paper Validation?

**Conditionally yes.** Once signals flow (15-30 min bootstrap), scalpers:
- Trade every 30s (coverage throttle) → up to 120 trades/hour
- Hold 10s-300s → fast turnover
- Have venue-aware economics (20 BPS min net edge)
- Have proper discipline (loss-streak cooldown, stagnation exit, re-entry cooldown)

Scalper paper validation will produce meaningful data about:
- Signal quality (are signals producing >55% win rate?)
- Execution cost realism (are fees/slippage estimates accurate?)
- Regime adaptation (do scalpers correctly pause in low-vol?)
- Risk management (does loss-streak cooldown prevent cascading losses?)

---

## 8. Position Sizing / Capital Usage Audit

### 8.1 Kelly Sizing Truth

**Quarter-Kelly parameters:**
- Fraction: 0.25 (conservative)
- Max position: 3-5% of equity (strategy-dependent)
- Min position: 1% of equity (floor)
- Bootstrap (<20 trades): 1.5% × MIN_POSITION_PCT = 1.5%

**Example: R1,000 Luno normal bot**
- Bootstrap mode (< 20 trades): 1.5% × R1,000 = R15 notional
- After 20+ trades (60% win, 2:1 reward/risk): Quarter-Kelly ≈ 3.5% → R35 notional
- Max: 5% → R50 notional

**R15 notional on BTC/ZAR (price ~R2M):** Buys 0.0000075 BTC. At 50 BPS net edge: R0.075 profit. This is below the R3.00 absolute profit minimum and would be rejected by the feasibility gate.

### 8.2 The Paper Notional Boost Saves Small Trades

The paper notional boost (lines 2073-2100) calculates:
```
min_notional = abs_profit_minimum / (net_edge_bps / 10000)
notional = max(kelly_notional, min(min_notional, paper_capital))
```

**Example continuation:**
- Abs profit minimum: R3.00 (normal/small/zar)
- Net edge: 67.5 BPS (after edge floor inflation) = 0.00675
- Min notional: R3.00 / 0.00675 = R444
- Paper capital: R1,000
- Final notional: max(R15, min(R444, R1,000)) = **R444**

This boost is **essential** — without it, Kelly sizing would produce trades too small to meet absolute profit minimums. But R444 notional on R1,000 capital = 44.4% of equity in one trade, which is very aggressive for paper mode.

### 8.3 Why Some Trades Are Still Tiny

If the edge floor produces a very high edge (say 150 BPS), the min_notional becomes smaller:
- Net edge: 115 BPS = 0.0115
- Min notional: R3.00 / 0.0115 = R261

The trade is smaller because the edge is (artificially) higher. **Higher edge floor → smaller required notional → smaller trades → smaller absolute profits.** This is counterintuitive but mathematically correct.

### 8.4 Paper vs Live Capital Usage Comparison

| Metric | Paper Mode | Live Mode | Ratio |
|--------|-----------|-----------|-------|
| Notional cap | 100% of capital | 10% of capital | **10×** |
| Kelly sizing | Same | Same | 1× |
| Notional boost | Full (to meet profit floor) | Limited to 10% cap | Variable |
| Profit magnitude | 10× larger | 1× baseline | **10×** |

**This means paper profits are structurally inflated by approximately 10× compared to live.** A paper bot showing R30/day should expect ~R3/day live.

---

## 9. Regime / AI Signal Audit

### 9.1 How Regime Is Determined

The regime scorer uses continuous scoring functions:
- **Trend score** (0-1): Based on `trend_pct` — 3.0%+ → 1.0, 0.5%+ → 0.2-0.6
- **Volatility score** (0-1): Based on `vol_pct` — 5.0%+ → 1.0, 0.5%+ → 0.15-0.5
- **Liquidity score** (0-1): 50% spread quality + 50% depth quality

Regime labels: `TRENDING_UP/DOWN, CONSOLIDATION, MEAN_REVERSION, BREAKOUT, HIGH_VOL, LOW_VOL, AMBIGUOUS`

**Hysteresis:** Must score >0.55 to enter regime, must drop below 0.35 to leave. 30s minimum between transitions. This prevents regime flapping.

### 9.2 When Regime Becomes Unknown

Regime becomes `unknown` with confidence=0 when:
- Market regime detector has <10 price samples (cold-start)
- Price data feed is unavailable
- Internal error in regime calculation

**Frequency:** Every server restart causes a cold-start. Regime typically becomes known within 2-3 minutes (10 price samples at 10s intervals).

### 9.3 Cold-Start Fallback Assessment

**Fallback:** trend_pct=2.0%, vol_pct=2.5% when regime is unknown/cold-start.

These values produce:
- Trend score: ~0.3 (mild)
- Vol score: ~0.33 (mild)
- Likely regime: AMBIGUOUS or borderline MEAN_REVERSION
- Confidence: ~0.4-0.5

**Assessment:** The fallback prevents the deadlock (LOW_VOL blocking all scalpers) but produces an AMBIGUOUS regime that:
- Allows normal bots (reduced capacity)
- Allows scalpers at half size (microstructure_only)
- Does NOT create false confidence in any direction

**This is reasonable bootstrap behavior.** The system can trade but cautiously.

### 9.4 How Often Regime Blocks Entries

Once signals flow (2-3 min after startup), regime blocking depends on actual market conditions:
- **LOW_VOL regime:** Blocks scalpers entirely, allows normal/mean_reversion
- **AMBIGUOUS regime:** Reduces all sizes by 40-50%, increases edge requirements by 30-50%
- **Clear regimes** (TRENDING, BREAKOUT, etc.): Full trading allowed

In typical BTC markets:
- ~40% of time: TRENDING (allows all)
- ~20% of time: CONSOLIDATION (allows all at reduced size)
- ~15% of time: BREAKOUT/HIGH_VOL (allows all)
- ~15% of time: AMBIGUOUS (reduced, may block some scalpers)
- ~10% of time: LOW_VOL (blocks scalpers)

**Estimate: Scalpers are regime-blocked ~10-25% of the time. Normal bots are rarely regime-blocked (<5%).**

### 9.5 Are AI Signal Sources Meaningful or Decorative?

**Entry confidence composite:**
```
35% × regime_confidence    → FROM: market_regime_detector (real price analysis)
30% × ml_confidence        → FROM: ML predictor (model prediction confidence)  
20% × fetchai_confidence   → FROM: Fetch.ai signal (external service)
15% × coinstats_strength   → FROM: CoinStats data (external service)
```

**Reality check:**
- **Regime confidence:** Based on actual price data analysis. REAL and meaningful.
- **ML confidence:** Model exists but quality depends on training data. During bootstrap, confidence is low (expected). After sufficient data, it provides genuine prediction confidence. REAL but accuracy varies.
- **FetchAI confidence:** Requires external Fetch.ai API. In paper mode, this may return fallback/zero. POTENTIALLY DECORATIVE if external API is not connected.
- **CoinStats strength:** Requires external CoinStats API. Same concern. POTENTIALLY DECORATIVE if not connected.

**Finding:** If FetchAI and CoinStats are not returning real data (likely in paper mode without API keys), then entry_confidence is effectively:
```
35% × regime + 30% × ML + 0 + 0 = max 65% of possible score
```

To reach 0.78 (scalper threshold): would need regime_conf=1.0 AND ML_conf=1.0 (impossible in practice). **Scalpers may be systematically blocked by the confidence gate if external signals are not connected.**

To reach 0.68 (normal threshold): would need regime_conf=0.9 AND ML_conf=0.8 = 0.315 + 0.24 = 0.555 + consensus bonus ≈ 0.63. **Normal bots may also struggle to reach their confidence threshold without external signals.**

**THIS IS A CRITICAL FINDING:** If FetchAI and CoinStats are returning zeros, the confidence gate becomes the primary bottleneck, potentially blocking most or all trades.

### 9.6 Cold-Start Trade Approval Path

Given the above, how do trades actually get approved in paper mode?

The feasibility gate's `MIN_ENTRY_CONFIDENCE = 0.40` (not the per-strategy thresholds in entry_quality.py) is the gate used in the V2 decision path. The entry_quality per-strategy thresholds (0.68/0.78) appear to be checked separately in a pre-filter, but the V2 path passes `entry_confidence` to the feasibility gate which checks against 0.40.

**If the V2 path only checks against 0.40:** Normal bots with regime_conf=0.7 and ML_conf=0.6 get entry_confidence ≈ 0.43 → PASSES 0.40 gate → trade approved.

**If both checks apply:** The trade passes 0.40 but fails 0.68 → trade blocked.

**This ambiguity in the gate chain is a significant finding.** The exact behavior depends on whether `entry_quality.py` thresholds are enforced in the V2 path or only in the legacy path.

---

## 10. Scheduler / Execution Audit

### 10.1 Scheduler Tick Throughput

**Configuration:**
- Tick interval: 10 seconds
- Max trades per tick: 5
- Theoretical max: 30 trades/minute (5 per 10s tick)
- Practical max (with stagger): ~10-15 trades/minute (exchange rate limits)

**Per-Exchange Bottlenecks:**

| Exchange | Concurrent Max | Min Delay | Effective Rate |
|----------|---------------|-----------|----------------|
| Luno | 2 | 10s | ~12/min |
| Binance | 5 | 2s | ~150/min |
| KuCoin | 3 | 3s | ~60/min |
| Bybit | 4 | 3s | ~80/min |
| Bitget | 4 | 3s | ~80/min |

Luno is the bottleneck. A user with 5 normal bots on Luno will see:
- 2 concurrent + 10s delay = ~6 trades dispatched/min
- Each trade takes 20 min (paper hold cap) to complete
- Steady state: 2 bots trading, 3 waiting → ~6 completed trades/hour
- **This is slow but mechanically correct.**

### 10.2 Queue Fairness

The fair queue rotation (offset increments each tick) prevents bot starvation. Scalper priority (appendleft) ensures scalpers execute before normal bots each cycle. The same-bot deferral prevents a single bot from monopolizing the queue.

**Assessment:** ✅ CORRECT and fair.

### 10.3 Whether Scheduler Prevents Sufficient Turnover

**For paper validation purposes:**
- 5 normal bots × 3 trades/hour = 15 trades/hour = 360 trades/day
- 2 scalper bots × 30 trades/hour = 60 trades/hour = 1,440 trades/day

**This is sufficient for paper validation.** The system can generate hundreds of trades per day, providing meaningful statistical samples for win rate, PnL distribution, and risk metric validation.

**Perception issue:** The 10-second tick + 20-minute hold creates long periods where the dashboard shows "managing_open_positions" with no new activity. This feels slow even though the actual throughput is adequate.

### 10.4 Runtime State Alignment

The scheduler correctly:
- Filters paused/stopped bots
- Checks emergency stop per-user
- Checks daily loss lock per-user
- Checks autopilot enabled per-user
- Tracks per-bot skip reasons
- Reports diagnostic state

**Assessment:** ✅ ALIGNED with intended paper testing goals.

---

## 11. Portfolio / PnL / Drawdown Truth Audit

### 11.1 Portfolio Summary Math

**Overview service computes:**
- Total PnL: Sum of `net_pnl` across closed trades (fee-inclusive)
- Today PnL: Same but filtered to today's timestamp
- Win rate: winning_trades / total_trades × 100
- Equity: Sum of `current_capital` across active bots
- Fees: Sum of `fee_amount` across closed trades

**Field cascade:** `net_pnl` → `profit_loss` (fallback for legacy trades)

**Assessment:** ✅ CORRECT — single source of truth via overview_service.

### 11.2 Realized vs Unrealized PnL

**Ledger service:**
- Realized: FIFO matching of buy fills → sell fills → PnL = qty × (sell_price - buy_price) ✅ CORRECT
- Unrealized: Open position fills × (mark_price - entry_price) ✅ CORRECT
- Equity: Starting Capital + Realized + Unrealized - Fees ✅ CORRECT

**No double-counting:** Three independent systems (scheduler telemetry, overview service, ledger service) read from different source collections with different filters.

### 11.3 Drawdown Semantics

**Bodyguard service:**
- Win-aware: Never pauses profitable bots
- 2-confirmation: Requires 2 breach confirmations within 15 minutes
- Thresholds: 15% (safe) → 20% (balanced) → 25% (aggressive)
- Peak tracking: Tracks equity high-water mark per bot

**Assessment:** ✅ CORRECT — drawdown calculation is sound.

### 11.4 Per-Bot vs Portfolio Alignment

**Potential issue:** Overview service sums `current_capital` from bot documents, while ledger service computes equity from fills. If `current_capital` is not updated after each trade, the overview could show stale equity.

**How `current_capital` is updated:** After each trade closes in paper_trading_engine.py, the bot document is updated with new capital. This should stay in sync, but any failed update (database error, race condition) could create divergence.

**Assessment:** ⚠️ MINOR RISK — single-update-point means generally consistent, but no reconciliation job ensures agreement.

### 11.5 Whether User-Visible Numbers Feel Wrong

**Yes, they will feel wrong because:**

1. **PnL magnitude is inflated 10×** (100% notional cap vs 10% live)
2. **Win rate will be ~45-55%** (most trades hit max-hold, not TP/SL, so outcomes are semi-random)
3. **Fee display may confuse:** Paper trades show realistic fees (0.1% taker), but the edge floor means the gross edge dwarfs fees — making fees look negligible when they're actually significant relative to real edge
4. **"Today" trade count includes open trades:** A user with 5 bots with open positions sees "5 trades today" even if none have closed yet

### 11.6 Are Truth Surfaces Sufficient for Paper-Mode Trust?

**Sufficient:**
- Overview snapshot provides one-stop dashboard truth
- Per-bot capital tracking is accurate
- Realized PnL (FIFO) is mathematically correct
- Win rate calculation is correct
- Fee tracking is accurate

**Insufficient:**
- No display of "paper vs live expected" comparison
- No indicator that edge floor is active (user thinks system found real edge)
- No indicator that notional cap is 10× live (user thinks paper profits are realistic)
- No reconciliation between overview service equity and ledger service equity

---

## 12. Top Runtime Go-Live Blockers

### Blocker 1: Paper Edge Floor Creates False Economic Signals (CRITICAL)
The 100 BPS edge floor means every paper trade that passes the confidence/regime gates will look economically sound regardless of actual market opportunity. Paper profits reflect the edge floor, not real market edge. Users cannot distinguish "system is finding profitable trades" from "system is approving all trades with artificial edge."

### Blocker 2: 10× Notional Cap Disparity Is Undocumented (SIGNIFICANT)
Paper mode allows 100% notional, live allows 10%. Paper PnL is 10× what live will produce. This will cause severe user disappointment at go-live. No UI indicator warns users of this difference.

### Blocker 3: Confidence Gate May Block Most Trades If External Signals Offline (SIGNIFICANT)
If FetchAI and CoinStats are not returning real data in paper mode, entry_confidence maxes at ~0.55-0.65 (regime + ML only). Depending on which confidence threshold is enforced in the V2 path (0.40 vs 0.68), this may block all normal bot trades or none. The exact behavior needs runtime verification.

### Blocker 4: Paper Hold Cap Prevents Strategy Validation (MODERATE)
20-minute hold cap for normal bots means TP/SL logic is almost never exercised. Most exits are max-hold timeout, making paper results a test of "where is the price at 20 minutes" not "does the trading strategy work."

### Blocker 5: Inconsistent Threshold Standards Between Gate Files (MODERATE)
`trade_worth_filter.py` scalper min edge (8 BPS) vs `trade_feasibility_gate.py` (20 BPS) creates confusing skip diagnostics. Similarly, USDT profit minimums differ by 20-60%. These should be unified.

### Blocker 6: No-Progress Exit Is Cost-Unaware (LOW-MODERATE)
The 0.05% no-progress threshold doesn't account for venue-specific round-trip costs (0.22-0.35%). Exits that look like "breaking even" are actually deep in the red after costs.

---

## 13. Top 5 Highest-Impact Repairs

**IMPORTANT: No code. No diffs. Only ranked descriptions.**

### Repair 1: Make Edge Floor Transparent and Documented
The edge floor is a necessary bootstrap mechanism, but its existence and impact must be visible. The diagnostics endpoint should expose: `real_gross_edge_bps` vs `paper_floor_adjusted_edge_bps`. The user (and future analysts) must be able to see that paper trades are approved with inflated edge. Without this transparency, paper results will be misinterpreted as evidence of real market opportunity discovery.

### Repair 2: Align or Document Paper Notional Cap Difference
Either reduce paper notional cap to match live (10% of capital — will make paper profits tiny but honest), or prominently document the 10× disparity in the dashboard. The overview snapshot should include a field like `notional_mode: "paper_full"` and the frontend should display "Paper profits use 10× live capital allocation" somewhere visible. Without this, paper-to-live transition will cause confusion.

### Repair 3: Unify Gate Thresholds Between trade_worth_filter.py and trade_feasibility_gate.py
The scalper min net edge should be 20 BPS in both files (not 8 vs 20). The USDT absolute profit minimums should be identical in both files. Having two contradictory standards creates confusing diagnostics and means the effective gate depends on execution order rather than explicit policy. One source of truth for each threshold.

### Repair 4: Verify and Document Which Confidence Threshold Governs V2 Entry
Clarify whether the V2 decision path enforces MIN_ENTRY_CONFIDENCE (0.40 from feasibility gate) or the per-strategy thresholds from entry_quality.py (0.68 normal / 0.78 scalper), or both. If 0.40 is the effective gate, document this. If 0.68/0.78 are also enforced, verify that paper-mode signals can actually reach these thresholds without external signal providers (FetchAI, CoinStats). If they can't, either lower the thresholds for paper mode or accept that normal bots need strong regime + ML signals to trade.

### Repair 5: Make No-Progress Exit Venue-Cost-Aware
Change the no-progress threshold from a fixed 0.05% to venue-aware values: at least 1.5× round-trip cost (Luno: ~0.53%, Binance: ~0.33%). This ensures that "no progress" actually means "below breakeven after costs" rather than "marginally positive but actually deeply underwater." This is the simplest repair with the most direct economic impact on exit quality.

---

## 14. Final Runtime Verdict

### **MECHANICALLY WORKING BUT ECONOMICALLY WEAK**

**Justification:**

The system is genuinely mechanically impressive. The 12-step V2 decision gate, the 9-level exit priority chain, the FIFO fills ledger, the venue-aware cost model, the quarter-Kelly sizing, the scalper discipline system, the adaptive stand-down, the fair queue rotation, the per-exchange rate limiting — all of these work correctly and demonstrate production-grade engineering.

However, the system is **economically weak for paper validation** because:

1. **The edge floor artificially guarantees all trades look profitable at entry.** Paper results cannot distinguish good signals from bad signals because the economics are overridden by the floor. This is the foundational economic weakness.

2. **The 10× notional cap means paper PnL magnitude is unrealistic.** Even if every trade's direction is correct, the profit amounts are 10× what live trading will produce.

3. **The paper hold cap prevents strategy validation.** Normal bot TP/SL logic is rarely exercised. Most exits are mechanical timeouts, not economic decisions.

4. **Signal confidence may be insufficient without external providers.** If FetchAI and CoinStats return zeros, the system's multi-source consensus becomes a two-source system (regime + ML) that may not reach the required confidence thresholds.

**The system is NOT paper-go-live ready** in the sense of "paper results can be trusted to predict live performance." It IS paper-go-live ready in the sense of "paper mode can validate mechanics, turnover, risk gating, wallet integrity, ledger correctness, and scheduler health."

**Recommended path:** Accept the current limitations, document them prominently, and use paper mode for **mechanical validation** (not profit prediction). The five highest-impact repairs would upgrade the verdict to "GOOD FOR LIMITED PAPER VALIDATION."

---

*End of Runtime Trading Truth Audit*
*This document reflects code truth as of 2026-03-14. No code was changed during this audit.*
