# PHASE 3 INSTITUTION-LEVEL TRADING BRAIN UPGRADE
# EXACT FILES, FUNCTIONS & INSERTION POINTS

## 1. REGIME DETECTION & CLASSIFIER

### Primary Implementation:
- **File**: backend/engines/regime_detector.py (Lines 26-491)
  - Class: RegimeDetector
  - Method: async detect_regime(symbol: str) → RegimeState
  - Enum: MarketRegime (TRENDING, RANGING, VOLATILE, LOW_VOLATILITY, PANIC, ACCUMULATION)
  - Key: _map_regime_to_state() (line 231) maps HMM/GMM outputs to semantic regimes
  - Key: get_trading_parameters(regime_state) (line 373) returns adaptive params per regime

### Legacy Detector:
- File: backend/market_regime.py (14-176)
  - Class: MarketRegimeDetector (simpler version)
  - Used as fallback

### Where Paper Engine Uses Regime:
- File: backend/paper_trading_engine.py
  - Line 972-973: regime = await market_regime_detector.detect_regime(symbol, exchange)
  - Line 990-991: Override trend if confidence > 0.7
  - Line 1050-1051: Include regime confidence in quality filter
  - Line 1064: Signal consensus computation
  - Line 1074-1075: Scalper regime gate (blocks unknown/choppy regimes)

### PHASE 3 INSERTION POINTS:
1. Position sizing multiplier (lines 1098-1125)
   → Insert: regime_detector.get_trading_parameters()["position_size_multiplier"]
   
2. Exit target adaptation (lines 1192-1200)
   → Add regime context: TRENDING→wider, PANIC→tighter targets
   
3. Multi-regime entry gate (lines 1073-1096)
   → Insert: regime_state.confidence >= 0.65 (normal), >= 0.80 (scalpers)

---

## 2. ENTRY GATING / SIGNAL CONSENSUS / EXPECTANCY

### Existing Signal Consensus:
- File: backend/paper_trading_engine.py
  - Lines 309-333: _compute_signal_consensus(regime, prediction, fetchai_data)
  - Returns: {bullish, bearish, neutral, sources, consensus_strength}
  - Combines: regime trend, ML prediction, Fetch.ai signal

### Existing Quality Filters (Entry Gates):
- Lines 1046-1062: Aggregate confidence from 4 sources (regime, ML, fetchai, coinstats)
- Lines 1073-1096: Bot-type-specific gates:
  
  SCALPER GATES:
  - regime.confidence >= 0.75
  - confidence_sources >= 3
  - avg_confidence >= 0.75 (SCALPER_MIN_AVG_CONFIDENCE from env)
  - consensus_strength >= 2
  
  NORMAL GATES:
  - confidence_sources >= 2
  - avg_confidence >= 0.68 (NORMAL_MIN_AVG_CONFIDENCE from env)
  - OR consensus_strength == 0 & avg_confidence >= 0.75

- Lines 1008-1044: Edge gate
  - expected_move > (fees + slippage + edge_buffer)
  - Scalpers get 2.25x multiplier

### Shared Services Used:
- backend/services/paper_wallet_ledger.py: get_balance(), can_trade()
- backend/services/order_validation.py: validate_order()
- backend/utils/trading_gates.py: enforce_trading_gates("paper")
- backend/risk_engine.py: Fixed-fractional sizing (1-2%), daily loss, drawdown

### PHASE 3 INSERTION POINTS - EXPECTANCY:

**Create NEW FILE: backend/services/entry_expectancy.py**
```python
async def calculate_entry_expectancy(
    regime_state: RegimeState,
    prediction: Dict,
    symbol: str,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Dict[str, float]:
    # Returns: {expectancy, win_rate, profit_factor, kelly_fraction}
```

**Insert in paper_trading_engine.py AFTER line 1064:**
```
expectancy = await entry_expectancy_service.calculate_entry_expectancy(...)
if expectancy.get("expectancy", 0) <= 0:
    return {"success": False, "skip_reason": "negative_expectancy", ...}
if bot_type == "scalper" and expectancy["expectancy"] < 0.005:
    return {"success": False, "skip_reason": "scalper_low_expectancy", ...}
```

**Enhance _compute_signal_consensus():**
- Add conviction weighting: regime(0.4) > prediction(0.3) > fetchai(0.2) > coinstats(0.1)
- Return: conviction_score in addition to raw counts

---

## 3. EXIT MANAGEMENT PATHS & REASON CODES

### Existing Exit Reason Codes (IMMUTABLE):
- File: backend/services/position_lifecycle.py (lines 26-32)
  - TIME_EXIT: max hold time exceeded
  - STAGNATION_EXIT: price hasn't moved enough in stagnation window
  - RISK_EXIT: unrealized loss exceeds threshold
  - TARGET_EXIT: take-profit reached
  - STOP_EXIT: stop-loss hit
  - TRAIL_EXIT: trailing stop triggered
  
- Function: check_position_exit() (line 111)
  - Returns: (should_exit: bool, reason_code: str, reason_text: str)

### Time Decay Exit Engine:
- File: backend/engines/time_decay_exit.py (lines 51-175)
  - Class: TimeDecayExitEngine
  - Method: evaluate(bot_id, bot_class, hold_seconds, profit_pct)
  - Returns: TimeDecayResult with exit_reason field
  - Logic: decay_factor = hold_time / expected_hold; adjusted_target = target * (1 - 0.5 * decay)

### Chandelier (ATR) Exits:
- File: backend/engines/chandelier_exits.py
  - Class: ChandelierExits
  - Method: calculate_atr_stop_loss(), calculate_atr()
  - Volatility-adjusted dynamic stops

### PHASE 3 INSERTION POINTS - EXIT TRACES:

**Create NEW FILE: backend/services/exit_decision_trace.py**
```python
@dataclass
class ExitDecisionTrace:
    reason_code: str
    reason_text: str
    radar_exposure: Dict[str, float]  # leverage, position_age_hours, drawdown_pct
    decision_context: Dict  # regime, volatility, trend, margin_level
    timestamp: datetime
    bot_id: str
```

**Wrap position_lifecycle.check_position_exit() (NEW FUNCTION):**
```python
async def check_position_exit_with_trace(...) -> Tuple[bool, str, str, ExitDecisionTrace]:
    should_exit, code, text = await check_position_exit(...)  # Original
    trace = await build_exit_trace(code, ...)  # NEW
    return should_exit, code, text, trace
```

**Create NEW FILE: backend/services/radar_exposure.py**
```python
def calculate_radar_exposure(position, regime, market_conditions) -> Dict:
    # Returns: {leverage_ratio, time_decay_pct, volatility_exposure, margin_proximity, drawdown_depth}
```

**Wire into paper_trading_engine.py AFTER trade execution (line 1213+):**
- Store exit_decision_trace in trades_collection
- Include radar_exposure in trace metadata

---

## 4. STAND-DOWN / ADAPTIVE DISCIPLINE HOOKS

### Existing Scheduler Infrastructure:
- File: backend/autonomous_scheduler.py (line 22)
  - Class: AutonomousScheduler
  - Orchestrates bot execution cycles
  - INSERT POINT: Line ~80 before execute_smart_trade() loop

- File: backend/trading_scheduler.py (line 46)
  - Class: TradingScheduler
  - INSERT POINT: Line ~100 where next_trade_timestamp evaluated

- File: backend/ai_scheduler.py (line 17)
  - Class: AIScheduler
  - INSERT POINT: Before signal fetch

### Risk Engine Existing Checks:
- File: backend/risk_engine.py (line 29)
  - check_trade_risk(): Daily loss limit, drawdown, fractional risk, asset exposure
  - INSERT POINT: Line 124 after existing checks

### Bodyguard Service (Risk Enforcement):
- File: backend/services/bodyguard_service.py (line ~450)
  - pause_reason_code field where stand-down can be triggered

### PHASE 3 INSERTION POINTS - ADAPTIVE DISCIPLINE:

**Create NEW FILE: backend/services/adaptive_discipline.py**
```python
class AdaptiveDisciplineEngine:
    async def evaluate_stand_down_triggers(
        bot_id: str,
        recent_outcomes: List[TradeOutcome],
        current_pnl: float,
        regime_state: RegimeState,
        scheduler_tick: int
    ) -> Dict[str, Any]:
        # Returns: {should_stand_down: bool, reason: str, duration_seconds: int}
```

**Create NEW FILE: backend/services/recent_bot_outcomes.py**
```python
@dataclass
class BotOutcomeSummary:
    bot_id: str
    last_trade_timestamp: datetime
    last_10_trades: List[TradeOutcome]
    win_rate_10: float
    win_rate_30: float
    profit_factor: float
    avg_hold_seconds: float
    pnl_today: float
```

**Hook into autonomous_scheduler.py (line ~80):**
```python
for bot in eligible_bots:
    discipline_eval = await adaptive_discipline.evaluate_stand_down_triggers(...)
    if discipline_eval["should_stand_down"]:
        await db.bots_collection.update_one(
            {"id": bot['id']},
            {"$set": {
                "paused": True,
                "pause_reason": "adaptive_discipline",
                "stand_down_reason_code": discipline_eval["reason"],
                "resume_at": datetime.now(tz.utc) + timedelta(seconds=...)
            }}
        )
        continue
    result = await self.paper_engine.execute_smart_trade(bot)
```

**Create NEW FILE: backend/utils/discipline_codes.py**
- CONSECUTIVE_LOSSES_3: 3+ consecutive losses
- PROFIT_FACTOR_LOW: Profit factor < 1.0
- WIN_RATE_BELOW_40: Win rate < 40%
- REGIME_MISMATCH: Bot strategy doesn't fit regime
- MARGIN_ACCELERATION: Loss velocity increasing
- TIME_BASED_COOLDOWN: Cool-off after large loss

**Wire into risk_engine.py (line ~124):**
```python
async def check_recent_outcomes_discipline(user_id: str, bot_id: str) -> Tuple[bool, str]:
    recent = await recent_outcomes_svc.get_summary(bot_id)
    if recent.win_rate_10 < 0.3:
        return False, "DISCIPLINE_LOW_WIN_RATE"
    if recent.profit_factor < 0.8:
        return False, "DISCIPLINE_NEGATIVE_PF"
    return True, "OK"
```

---

## 5. TESTS ALREADY COVERING THESE AREAS

### Existing Test Files:
1. tests/test_paper_trading.py - Fee calculations, ledger records
2. tests/test_paper_trade_scenario.py - Scenario-based entry/exit
3. tests/test_risk_engine_fractional.py - Fixed-fractional sizing
4. tests/test_paper_trade_deterministic.py - Deterministic outcomes
5. tests/test_phase1_deliverables.py - Phase 1 contract validation

### PHASE 3 TEST FILES TO CREATE:

**tests/test_expectancy_calculator.py (NEW)**
- test_positive_expectancy_entry_gate(): Positive expectancy passes
- test_negative_expectancy_blocked(): Negative expectancy blocked
- test_expectancy_varies_by_regime(): Regime context affects expectancy
- test_scalper_expectancy_threshold(): Scalpers have tighter gate

**tests/test_exit_decision_trace.py (NEW)**
- test_exit_trace_includes_radar_exposure(): Verify radar fields
- test_time_exit_trace_includes_decay_factor(): Time decay captured
- test_all_reason_codes_generate_traces(): Each code has valid trace

**tests/test_adaptive_discipline.py (NEW)**
- test_stand_down_after_3_losses(): 3 consecutive losses → paused
- test_discipline_resume_after_cooldown(): Bot resumes after duration
- test_regime_mismatch_triggers_stand_down(): Strategy-regime mismatch
- test_discipline_codes_are_unique(): No code collisions
- test_recent_outcomes_tracking(): Outcomes captured correctly

**tests/test_signal_consensus_weighted.py (NEW)**
- test_consensus_conviction_weighting(): Weighted sources
- test_regime_higher_weight_than_fetchai(): Correct priorities

---

## 6. PHASE 1/2 TRUTH CONTRACTS - PRESERVATION

### IMMUTABLE - DO NOT CHANGE:

1. Paper Trading Engine Math (paper_trading_engine.py):
   - Lines 78-83: PAPER_SLIPPAGE_BPS, PAPER_LATENCY_BPS, PAPER_SPREAD_BPS
   - Lines 1008-1044: Edge gate formula (fee*2 + slippage*2 + spread + buffer)
   - Lines 1145-1190: Entry price = ask * (1 + slippage + latency)
   - Lines 1189-1190: entry_fee = entry_value * taker_fee

2. Risk Engine Fixed-Fractional (risk_engine.py):
   - Line 66-80: Position size = capital * risk_fraction, capped by stop loss
   - Line 50-63: Daily loss limit check (3% default)
   - Line 141-168: Max notional calculation

3. Position Lifecycle Codes (position_lifecycle.py):
   - Line 26-32: All 6 reason codes (NEVER REMOVE/RENAME)
   - Line 111-150: Exit logic (wrap, don't replace)

4. Regime Enum (engines/regime_detector.py):
   - Line 26-39: Enum values (can add, don't remove)
   - Line 231-286: _map_regime_to_state logic (extend, don't refactor)

5. Trading Gates (utils/trading_gates.py):
   - Line 22-39: check_trading_mode_enabled() signature
   - Line 143-179: enforce_trading_gates() behavior

6. Paper Wallet Ledger (services/paper_wallet_ledger.py):
   - Balance tracking methods (core functionality)
   - Debit/credit logic (immutable)

### SAFE EXTENSION PATTERN:

✓ DO:
  async def check_position_exit_with_trace(...):
      should_exit, code, text = await check_position_exit(...)  # CALL ORIGINAL
      trace = await build_exit_trace(code, ...)  # NEW LAYER
      return should_exit, code, text, trace

✓ DO:
  if existing_gate_passes:
      return result
  # NEW PHASE 3 GATES
  expectancy = await calc_expectancy(...)
  if expectancy <= 0:
      return {"success": False, ...}

✗ DON'T:
  def check_position_exit(...):  # REWRITE (removes original)
      # Completely different logic

✗ DON'T:
  class MarketRegime(Enum):
      TRENDING_UP = "trending_up"  # CHANGED (breaks enum)

---

## 7. INSERTION POINT SUMMARY TABLE

| Phase 3 Feature | File | Lines | Function | Action |
|-----------------|------|-------|----------|--------|
| Regime position sizing | paper_trading_engine.py | 1098-1125 | execute_smart_trade | Insert multiplier after capital calc |
| Regime exit targets | paper_trading_engine.py | 1192-1200 | _apply_dynamic_exit_targets | Add regime context param |
| Entry expectancy gate | paper_trading_engine.py | 1064-1073 | execute_smart_trade | Insert check before position size |
| Signal consensus weighting | paper_trading_engine.py | 309-333 | _compute_signal_consensus | Enhance with conviction weights |
| Exit decision trace | position_lifecycle.py | 111-150 | check_position_exit | Wrap in async trace wrapper |
| Radar exposure | services/radar_exposure.py | NEW | NEW MODULE | Calculate exposure metrics |
| Adaptive discipline eval | autonomous_scheduler.py | ~80 | execute_bots_cycle | Insert before trade loop |
| Recent outcomes tracking | services/recent_bot_outcomes.py | NEW | NEW MODULE | Aggregate trade outcomes |
| Discipline reason codes | utils/discipline_codes.py | NEW | NEW MODULE | Define stand-down triggers |
| Discipline gate in risk | risk_engine.py | ~124 | check_trade_risk | Add recent_outcomes check |

---

## 8. MINIMUM VIABLE PHASE 3 (8-Week Delivery)

WEEK 1-2: Foundation
- services/entry_expectancy.py (3-day)
- services/exit_decision_trace.py (2-day)
- services/radar_exposure.py (1-day)
- Test stubs (1-day)

WEEK 3-4: Integrations
- Insert expectancy gate in paper_trading_engine.py (1-day)
- Wrap exit traces in position_lifecycle.py (1-day)
- Extend regime detection parameters (2-day)
- Tests - expectancy & traces (2-day)

WEEK 5-6: Discipline
- services/adaptive_discipline.py (2-day)
- services/recent_bot_outcomes.py (2-day)
- utils/discipline_codes.py (1-day)
- Hook into autonomous_scheduler.py (1-day)
- Tests - discipline triggers (1-day)

WEEK 7-8: Hardening
- Full integration tests (3-day)
- Performance/load tests (2-day)
- Documentation (1-day)
- Phase 1/2 regression suite (2-day)

___BEGIN___COMMAND_DONE_MARKER___0
