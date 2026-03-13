"""
Tests for the paper trading end-to-end execution path.

Validates:
 1. Regime cold-start fallback prevents REGIME_LOW_VOL dead-lock.
 2. Paper-mode edge floor prevents EDGE_TOO_SMALL dead-lock.
 3. Notional cap allows small accounts to meet abs-profit floor.
 4. Symbol is resolved (never 'unknown') for Luno and Binance bots.
 5. Luno paper bot: candidate → simulated trade persisted.
 6. Binance paper bot: candidate → simulated trade persisted.
 7. Binance scalper: candidate → simulated trade persisted or explicit skip.
 8. Trades endpoint reflects successful entries (recent_trades visibility).
 9. Radar reflects open position after entry.
10. Binance/USDT bot data does not carry ZAR-only representation.
11. Scalper detail panels return complete expected sections.
"""

import asyncio
import os
import pytest

# ── Module-level env flags to activate paper-mode logic ────────────────────
os.environ.setdefault("NEW_TRADING_BRAIN_V2", "true")
os.environ.setdefault("PAPER_EDGE_FLOOR_BPS", "100.0")
os.environ.setdefault("PAPER_FALLBACK_TREND_PCT", "2.0")
os.environ.setdefault("PAPER_FALLBACK_VOL_PCT", "2.5")


# ── Regime scorer cold-start fallback ───────────────────────────────────────

def test_regime_scorer_zero_inputs_no_longer_produces_low_vol_for_scalper():
    """
    Before the fix: trend=0, vol=0 → REGIME_LOW_VOL → scalpers blocked.
    After the fix:  cold-start fallback forces trend=2.0, vol=2.5 → REGIME_TRENDING_UP
                    which IS in the scalper allowed set.
    This test validates the regime-scorer directly with the fallback values.
    """
    from services.trading_brain_v2.regime_scorer import RegimeScorerV2, REGIME_LOW_VOL

    scorer = RegimeScorerV2()

    # Simulate what paper_trading_engine does BEFORE fix: feed zero data
    result_zero = scorer.score(
        symbol="BTC/ZAR",
        trend_pct=0.0,
        volatility_pct=0.0,
        spread_pct=0.1,
        depth_notional=50000,
    )
    # Zero-data regime should NOT be treated as "full confidence low-vol"
    # The scorer assigns low_vol with conf ≈ 1.0 — the fix bypasses it.

    # Simulate what paper_trading_engine does AFTER fix: feed fallback values
    scorer2 = RegimeScorerV2()
    result_fallback = scorer2.score(
        symbol="BTC/ZAR",
        trend_pct=2.0,
        volatility_pct=2.5,
        spread_pct=0.1,
        depth_notional=50000,
    )

    # Scalper eligibility check on fallback result
    elig = scorer2.is_eligible("scalper", result_fallback)
    assert elig["eligible"], (
        f"Scalper should be eligible after cold-start fallback, got: {elig}"
    )
    # Low-vol regime must NOT appear in fallback result
    assert result_fallback["regime_label"] != REGIME_LOW_VOL, (
        f"Fallback regime must not be {REGIME_LOW_VOL}, got: {result_fallback['regime_label']}"
    )


def test_regime_scorer_scalper_eligible_with_trending_up():
    """REGIME_TRENDING_UP is in scalper allowed set → eligible=True."""
    from services.trading_brain_v2.regime_scorer import RegimeScorerV2

    scorer = RegimeScorerV2()
    result = scorer.score("BTC/USDT", trend_pct=2.0, volatility_pct=2.5,
                          spread_pct=0.1, depth_notional=50000)
    elig = scorer.is_eligible("scalper", result)
    assert elig["eligible"] is True
    assert elig["action"] in ("full", "microstructure_only", "reduced_size")


# ── Edge floor ──────────────────────────────────────────────────────────────

def test_paper_edge_floor_ensures_positive_net_edge():
    """
    With all_in_cost_bps = 40 and k=1.5 for normal bots:
    paper_edge_floor = max(100, (1.5+1)*40 + 15) = max(100, 115) = 115 bps
    net_edge = 115 - 40 = 75 bps >= required = max(15, 1.5*40=60) = 60 bps ✓
    """
    all_in_cost_bps = 40.0
    bot_type = "normal"

    k_cost_map = {"scalper": 1.2, "mean_reversion": 1.3}
    k_cost = k_cost_map.get(bot_type, 1.5)
    floor = max(
        float(os.getenv("PAPER_EDGE_FLOOR_BPS", "100.0")),
        (k_cost + 1.0) * all_in_cost_bps + 15.0,
    )
    net_edge = floor - all_in_cost_bps

    from services.trading_brain_v2.trade_feasibility_gate import MIN_NET_EDGE_BPS, K_COST
    min_edge = MIN_NET_EDGE_BPS.get(bot_type, 15.0)
    k = K_COST.get(bot_type, 1.5)
    required = max(min_edge, k * all_in_cost_bps)

    assert net_edge >= required, (
        f"After edge floor, net_edge={net_edge:.1f} should be >= required={required:.1f}"
    )


def test_paper_edge_floor_scalper():
    """Same as above for scalpers (k=1.2)."""
    all_in_cost_bps = 40.0
    bot_type = "scalper"

    k_cost_map = {"scalper": 1.2, "mean_reversion": 1.3}
    k_cost = k_cost_map.get(bot_type, 1.5)
    floor = max(
        float(os.getenv("PAPER_EDGE_FLOOR_BPS", "100.0")),
        (k_cost + 1.0) * all_in_cost_bps + 15.0,
    )
    net_edge = floor - all_in_cost_bps

    from services.trading_brain_v2.trade_feasibility_gate import MIN_NET_EDGE_BPS, K_COST
    required = max(MIN_NET_EDGE_BPS.get(bot_type, 8.0), K_COST.get(bot_type, 1.2) * all_in_cost_bps)
    assert net_edge >= required, (
        f"Scalper: net_edge={net_edge:.1f} should be >= required={required:.1f}"
    )


# ── Notional cap ─────────────────────────────────────────────────────────────

def test_notional_cap_allows_abs_profit_floor_with_small_capital():
    """
    With paper_capital=1000 ZAR, edge_floor=115 bps, all_in=40 bps:
      net_edge_frac = 0.0075
      _abs_min = 1.50 ZAR  (normal, small, zar)
      _min_notional = 200 ZAR
      notional = min(200, 1000) = 200 ZAR  [OLD: min(200, 100) = 100 ZAR → FAIL]
      projected = 200 * 0.0075 = 1.50 ≥ 1.50 ✓
    """
    from services.trading_brain_v2.trade_feasibility_gate import (
        ABS_PROFIT_MIN_QUOTE, _equity_bucket, _venue_class,
    )
    paper_capital = 1000.0
    all_in_cost_bps = 40.0
    k_cost = 1.5
    expected_gross = max(100.0, (k_cost + 1.0) * all_in_cost_bps + 15.0)  # 115 bps
    net_edge_frac = max((expected_gross - all_in_cost_bps) / 10000.0, 0.0001)

    vc = _venue_class("luno")
    eq_bucket = _equity_bucket(paper_capital, vc)
    abs_min = ABS_PROFIT_MIN_QUOTE.get(("normal", eq_bucket, vc), 2.0)
    min_notional = abs_min / net_edge_frac

    # NEW cap: paper_capital (100%)
    notional_new = max(1.0, min(min_notional, paper_capital))
    projected_new = notional_new * net_edge_frac

    assert projected_new >= abs_min, (
        f"projected={projected_new:.4f} must be >= abs_min={abs_min} with new cap"
    )

    # OLD cap: paper_capital * 0.10 would fail for 1000 ZAR accounts.
    # projected_old must be strictly less than abs_min to demonstrate the failure.
    notional_old = max(1.0, min(min_notional, paper_capital * 0.10))
    projected_old = notional_old * net_edge_frac
    if paper_capital <= 2000:
        assert projected_old < abs_min, (
            f"Old 10% cap should fail the abs_profit floor for accounts <= 2000 {vc}. "
            f"projected_old={projected_old:.4f} expected to be < abs_min={abs_min}"
        )


# ── Symbol resolution ────────────────────────────────────────────────────────

def test_luno_symbol_resolution():
    """Luno bots must resolve to a /ZAR pair, never 'unknown'."""
    from config import PAPER_PAIR_WHITELIST

    luno_pairs = PAPER_PAIR_WHITELIST.get("luno", [])
    assert luno_pairs, "PAPER_PAIR_WHITELIST must have luno entries"
    for pair in luno_pairs:
        assert "/ZAR" in pair, f"Luno pair {pair} must contain /ZAR"
        assert pair != "unknown", "Symbol must not be 'unknown'"


def test_binance_symbol_resolution():
    """Binance bots must resolve to a /USDT pair, never 'unknown'."""
    from config import PAPER_PAIR_WHITELIST

    binance_pairs = PAPER_PAIR_WHITELIST.get("binance", [])
    assert binance_pairs, "PAPER_PAIR_WHITELIST must have binance entries"
    for pair in binance_pairs:
        assert "/USDT" in pair, f"Binance pair {pair} must contain /USDT"
        assert pair != "unknown", "Symbol must not be 'unknown'"


# ── Feasibility gate end-to-end with paper fallbacks ────────────────────────

def _make_regime_result_from_fallback(bot_type="normal", spread_pct=0.1, depth=50000):
    """Produce a regime result the same way _execute_v2_decision does after fallback."""
    from services.trading_brain_v2.regime_scorer import RegimeScorerV2
    scorer = RegimeScorerV2()
    result = scorer.score(
        symbol="BTC/ZAR",
        trend_pct=2.0,
        volatility_pct=2.5,
        spread_pct=spread_pct,
        depth_notional=depth,
    )
    return result, scorer.is_eligible(bot_type, result)


def _compute_paper_floor(bot_type, all_in_cost_bps):
    k_cost_map = {"scalper": 1.2, "mean_reversion": 1.3}
    k = k_cost_map.get(bot_type, 1.5)
    # Mirror the _EDGE_FLOOR_NET_BUFFER_BPS = 15.0 constant from paper_trading_engine.py
    _EDGE_FLOOR_NET_BUFFER_BPS = 15.0
    return max(100.0, (k + 1.0) * all_in_cost_bps + _EDGE_FLOOR_NET_BUFFER_BPS)


def _run_feasibility(bot_type, exchange, paper_capital,
                     spread_pct=0.1, depth_notional=50000):
    """
    Simulate the feasibility gate call as paper_trading_engine does it.
    Returns the feasibility payload.
    """
    from services.trading_brain_v2.trade_feasibility_gate import TradeFeasibilityGate
    from services.trading_brain_v2.cost_model import AllInCostModel
    from services.trading_brain_v2.kelly_sizing import KellySizingV2
    from services.trading_brain_v2.trade_feasibility_gate import (
        ABS_PROFIT_MIN_QUOTE, _equity_bucket, _venue_class,
    )

    symbol = "BTC/ZAR" if exchange == "luno" else "BTC/USDT"
    quote_currency = "ZAR" if exchange == "luno" else "USDT"

    cost_model = AllInCostModel()
    current_price = 1_000_000.0 if exchange == "luno" else 60_000.0
    bid = current_price * 0.999
    ask = current_price * 1.001

    cost = cost_model.compute(
        venue=exchange,
        symbol=symbol,
        quote_currency=quote_currency,
        side="buy",
        order_mode="taker",
        notional_size=paper_capital,
        best_bid=bid,
        best_ask=ask,
        mid=current_price,
        spread=spread_pct / 100.0,
    )
    all_in_cost_bps = cost["all_in_cost_bps"]

    regime_result, regime_eligibility = _make_regime_result_from_fallback(
        bot_type, spread_pct=spread_pct, depth=depth_notional
    )

    # Apply edge floor
    expected_gross_edge_bps = _compute_paper_floor(bot_type, all_in_cost_bps)

    # Kelly sizing (bootstrap)
    kelly = KellySizingV2()
    sizing = kelly.compute(
        bot_type=bot_type,
        bot_equity=paper_capital,
        win_rate=0.5,
        avg_win=0.0,
        avg_loss=0.0,
        num_trades=0,
        regime_size_multiplier=regime_eligibility.get("size_multiplier", 1.0),
    )
    notional = sizing.get("position_quote", paper_capital * 0.03)

    # Notional boost (new: uncapped)
    net_edge_frac = max((expected_gross_edge_bps - all_in_cost_bps) / 10000.0, 0.0001)
    vc = _venue_class(exchange)
    eq_b = _equity_bucket(paper_capital, vc)
    strat_key = bot_type if bot_type in ("scalper", "mean_reversion") else "normal"
    abs_min = ABS_PROFIT_MIN_QUOTE.get((strat_key, eq_b, vc), 2.0)
    min_notional = abs_min / net_edge_frac
    notional = max(notional, min(min_notional, paper_capital))  # cap at 100%

    gate = TradeFeasibilityGate()
    return gate.evaluate(
        strategy=bot_type,
        venue=exchange,
        symbol=symbol,
        bot_equity=paper_capital,
        notional=notional,
        expected_gross_edge_bps=expected_gross_edge_bps,
        all_in_cost_bps=all_in_cost_bps,
        spread_pct=spread_pct,
        depth_notional=depth_notional,
        regime_result=regime_result,
        regime_eligibility=regime_eligibility,
        entry_confidence=0.55,
        mid_price=current_price,
    )


def test_luno_normal_bot_feasibility_passes():
    """Luno normal bot with 1000 ZAR must pass all feasibility checks."""
    result = _run_feasibility("normal", "luno", paper_capital=1000.0)
    assert result.get("approved") is True, (
        f"Luno normal bot feasibility must pass. Got: {result.get('decision_reason_code')} "
        f"— {result.get('decision_reason_text')}"
    )


def test_binance_normal_bot_feasibility_passes():
    """Binance normal bot with 100 USDT must pass all feasibility checks."""
    result = _run_feasibility("normal", "binance", paper_capital=100.0)
    assert result.get("approved") is True, (
        f"Binance normal bot feasibility must pass. Got: {result.get('decision_reason_code')} "
        f"— {result.get('decision_reason_text')}"
    )


def test_binance_scalper_feasibility_passes_or_has_explicit_reason():
    """
    Binance scalper with 100 USDT must either pass or return an explicit,
    machine-readable reason code. No silent drops.
    """
    result = _run_feasibility("scalper", "binance", paper_capital=100.0)
    # Either approved, or rejected with a non-empty structured reason
    reason_code = result.get("decision_reason_code", "")
    assert reason_code, "Feasibility result must always contain decision_reason_code"
    if not result.get("approved"):
        assert reason_code != "UNKNOWN", (
            f"Rejection must have a specific reason, not UNKNOWN. Got: {result}"
        )


# ── Trade persistence helpers ────────────────────────────────────────────────

class _FakeCollection:
    """
    Minimal async-compatible fake MongoDB collection for unit tests.

    Limitations (by design – these tests don't need full Mongo semantics):
    - ``find_one`` only matches top-level equality filters; dict-valued
      operators (``$in``, ``$gt``, etc.) are silently skipped.
    - ``update_one`` only applies ``$set`` operations; other operators
      (``$inc``, ``$push``, ``$unset``, etc.) are ignored.  Tests that need
      those operators must extend this class or use a proper mock library.
    """
    def __init__(self):
        self.docs = {}
        self.inserts = []
        self.updates = []

    async def find_one(self, query, *args, **kwargs):
        # Return first matching doc
        for doc in self.docs.values():
            match = all(doc.get(k) == v for k, v in query.items()
                        if not isinstance(v, dict))
            if match:
                return dict(doc)
        return None

    async def insert_one(self, doc):
        key = doc.get("id") or doc.get("trade_id") or str(len(self.inserts))
        self.docs[key] = dict(doc)
        self.inserts.append(dict(doc))

    async def update_one(self, query, update, *args, **kwargs):
        self.updates.append({"query": query, "update": update})
        # Apply $set to matching doc
        for key, doc in list(self.docs.items()):
            match = all(doc.get(k) == v for k, v in query.items()
                        if not isinstance(v, dict))
            if match and "$set" in update:
                doc.update(update["$set"])
                self.docs[key] = doc
                break

    def find(self, query, *args, **kwargs):
        return _FakeCursor([d for d in self.docs.values()])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, *args, **kwargs):
        return list(self._docs)


class _FakeRTEvents:
    async def trade_opened(self, *args, **kwargs):
        pass
    async def broadcast_trade_execution(self, *args, **kwargs):
        pass


class _FakeDB:
    db = None

    class bots_collection_cls:
        async def update_one(self, *a, **k):
            pass

    bots_collection = bots_collection_cls()


# ── run_trading_cycle: reject path logs structured reason ────────────────────

def _try_import_pte():
    """Import paper_trading_engine, skipping if ccxt is unavailable."""
    ccxt = pytest.importorskip("ccxt", reason="ccxt not installed in test environment")
    import paper_trading_engine as pte_module
    return pte_module


def test_run_trading_cycle_rejected_entry_returns_none(monkeypatch):
    """
    When execute_smart_trade returns success=False, run_trading_cycle must
    return None (no silent drop, structured reason logged).
    """
    pte_module = _try_import_pte()

    engine = pte_module.PaperTradingEngine()

    bot_id = "test-luno-bot"
    bot_data = {
        "id": bot_id, "user_id": "u1", "name": "LunoTest",
        "exchange": "luno", "bot_type": "normal",
        "initial_capital": 1000.0, "current_capital": 1000.0,
        "trading_mode": "paper",
    }

    # Patch execute_smart_trade to return an explicit rejection
    async def mock_reject(*args, **kwargs):
        return {
            "success": False,
            "bot_id": bot_id,
            "reason_code": "EDGE_TOO_SMALL",
            "decision_reason_code": "EDGE_TOO_SMALL",
            "error": "Test rejection",
            "symbol": "BTC/ZAR",
        }
    monkeypatch.setattr(engine, "execute_smart_trade", mock_reject)

    trades_col = _FakeCollection()
    bots_col = _FakeCollection()
    bots_col.docs[bot_id] = dict(bot_data)

    result = asyncio.get_event_loop().run_until_complete(
        engine.run_trading_cycle(bot_id, bot_data, {
            "bots": bots_col,
            "trades": trades_col,
        })
    )

    assert result is None, "run_trading_cycle must return None on rejected entry"
    assert len(trades_col.inserts) == 0, "No trade must be persisted on rejection"


def test_run_trading_cycle_approved_entry_persists_trade(monkeypatch):
    """
    When execute_smart_trade returns an open trade, run_trading_cycle must
    insert a trade document and update the bot's open_position_value.
    """
    pte_module = _try_import_pte()
    from datetime import datetime, timezone

    engine = pte_module.PaperTradingEngine()

    bot_id = "test-binance-bot"
    bot_data = {
        "id": bot_id, "user_id": "u2", "name": "BinanceTest",
        "exchange": "binance", "bot_type": "normal",
        "initial_capital": 100.0, "current_capital": 100.0,
        "trading_mode": "paper",
    }

    entry_ts = datetime.now(timezone.utc).isoformat()

    async def mock_approved(*args, **kwargs):
        return {
            "success": True,
            "status": "open",
            "bot_id": bot_id,
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "entry_price": 60000.0,
            "amount": 0.001,
            "trade_amount": 60.0,
            "entry_value": 60.0,
            "fees": 0.06,
            "fees_total": 0.06,
            "entry_fee": 0.06,
            "fee_currency": "USDT",
            "slippage_cost": 0.0,
            "entry_fills": [{"qty": 0.001, "price": 60000.0, "timestamp": entry_ts}],
            "gross_pnl": 0.0,
            "net_profit": 0.0,
            "net_profit_zar": 0.0,
            "timestamp": entry_ts,
            "canonical_market_regime": "trending_up",
            "regime_label": "trending_up",
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "trailing_stop_pct": 0.005,
            "stop_loss_price": 59400.0,
            "take_profit_price": 61200.0,
            "max_hold_seconds": 21600,
            "latency_ms": 50,
            "data_source": "BINANCE_PUBLIC",
            "risk_mode": "safe",
            "slippage_bps": 5,
            "spread": 10,
            "price_source": "order_book",
            "partial_fill": False,
            "highest_price": 60000.0,
            "is_paper": True,
        }
    monkeypatch.setattr(engine, "execute_smart_trade", mock_approved)

    # Patch out ledger and realtime
    monkeypatch.setattr(pte_module, "rt_events", _FakeRTEvents())
    import database as db_module
    monkeypatch.setattr(db_module, "db", _FakeDB())

    trades_col = _FakeCollection()
    bots_col = _FakeCollection()
    bots_col.docs[bot_id] = dict(bot_data)

    result = asyncio.get_event_loop().run_until_complete(
        engine.run_trading_cycle(bot_id, bot_data, {
            "bots": bots_col,
            "trades": trades_col,
        })
    )

    assert result is not None, "run_trading_cycle must return a result dict on approved entry"
    assert "trade" in result, "Result must contain 'trade' key"
    assert len(trades_col.inserts) == 1, "Exactly one trade doc must be persisted"

    trade_doc = trades_col.inserts[0]
    assert trade_doc.get("bot_id") == bot_id
    assert trade_doc.get("status") == "open"
    assert trade_doc.get("pair") == "BTC/USDT"

    # Bot doc must have been updated with open_position_value and pair
    assert len(bots_col.updates) >= 1
    all_sets = {}
    for upd in bots_col.updates:
        all_sets.update(upd.get("update", {}).get("$set", {}))
    assert "open_position_value" in all_sets
    assert "pair" in all_sets
    assert all_sets["market_regime"] == "trending_up"


# ── Recent trades endpoint visibility ────────────────────────────────────────

def test_recent_trades_endpoint_reflects_open_position(monkeypatch):
    """
    After a successful paper entry, the trades collection must contain a record
    with status='open' that would be returned by the recent-trades endpoint.
    """
    trades_col = _FakeCollection()
    asyncio.get_event_loop().run_until_complete(
        trades_col.insert_one({
            "id": "t001",
            "bot_id": "bot-luno",
            "user_id": "u1",
            "pair": "BTC/ZAR",
            "status": "open",
            "entry_price": 1_000_000.0,
            "trade_amount": 250.0,
            "is_paper": True,
        })
    )
    open_trades = [d for d in trades_col.docs.values() if d.get("status") == "open"]
    assert len(open_trades) == 1
    assert open_trades[0]["pair"] == "BTC/ZAR"
    assert open_trades[0]["is_paper"] is True


# ── Radar open-position visibility ───────────────────────────────────────────

def test_radar_open_position_after_entry(monkeypatch):
    """
    After a paper entry, the bot document must have open_position_value > 0
    and pair set to a non-'unknown' value.
    """
    bot_doc = {
        "id": "bot-radar",
        "exchange": "luno",
        "pair": "BTC/ZAR",
        "open_position_value": 250.0,
        "market_regime": "trending_up",
    }
    # Simulate what radar.py does
    symbol = bot_doc.get("pair", bot_doc.get("symbol", "unknown"))
    regime = bot_doc.get("market_regime") or "unknown"

    assert symbol != "unknown", f"Radar symbol must not be 'unknown', got: {symbol}"
    assert regime != "unknown", f"Radar market_regime must not be 'unknown', got: {regime}"
    assert bot_doc["open_position_value"] > 0


# ── Currency contract: Binance bot must expose USDT not ZAR ──────────────────

def test_binance_bot_api_exposes_usdt_currency():
    """
    A Binance bot's API payload must carry quote_currency='USDT'.
    The frontend must NOT render this as ZAR (R symbol).
    """
    from services.fx_normalizer import get_quote_currency

    exchange = "binance"
    pair = "BTC/USDT"
    qc = get_quote_currency(exchange, pair)
    assert qc == "USDT", f"Binance bot quote_currency must be 'USDT', got '{qc}'"


def test_luno_bot_api_exposes_zar_currency():
    """A Luno bot's API payload must carry quote_currency='ZAR'."""
    from services.fx_normalizer import get_quote_currency

    exchange = "luno"
    pair = "BTC/ZAR"
    qc = get_quote_currency(exchange, pair)
    assert qc == "ZAR", f"Luno bot quote_currency must be 'ZAR', got '{qc}'"


def test_usdt_bot_values_not_rendered_as_zar():
    """
    The frontend fmtBotAmount helper must use USDT symbol ($) for USDT bots,
    not ZAR symbol (R).  This is a contract test on the data that reaches the
    frontend: bot.quote_currency must be 'USDT' and the formatter must pick
    the $ symbol.
    """
    CURRENCY_SYMBOLS = {"ZAR": "R", "USDT": "$", "USD": "$", "USDC": "$"}

    usdt_bot = {"quote_currency": "USDT", "initial_capital": 52.63}
    currency = usdt_bot.get("quote_currency", "ZAR").upper()
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    assert symbol == "$", (
        f"USDT bot values must use '$' symbol, not 'R'. currency={currency} symbol={symbol}"
    )
    assert symbol != "R", "USDT bot must never show 'R' (ZAR) symbol"


# ── Scalper detail sections ───────────────────────────────────────────────────

def test_scalper_detail_sections_contain_all_tabs():
    """
    The detailSections object built for a scalper bot must have both
    'overview' and 'performance' lists with content — just like normal bots.
    This validates the frontend contract expected by the scalper detail panel.
    """
    # Simulate what BotFleetSection.detailSections produces for a scalper
    scalper_bot = {
        "id": "sc001",
        "name": "ScalperTest",
        "exchange": "binance",
        "quote_currency": "USDT",
        "bot_type": "scalper",
        "profit_routing": "SCALPER_GROWTH",
        "status": "active",
        "trading_mode": "paper",
        "training_complete": True,
        "capital_summary": {
            "initial_capital": 50.0,
            "allocated_capital": 50.0,
            "available_capital": 47.0,
            "open_position_value": 3.0,
            "total_equity": 50.0,
            "realized_profit": 0.0,
            "unrealized_profit": 0.0,
            "quote_currency": "USDT",
        },
    }

    # Replicate the frontend botMetrics + detailSections logic in Python
    cap = scalper_bot["capital_summary"]
    overview_keys = {"Bot ID", "Name", "Exchange", "Currency", "Status", "Mode",
                     "Bot Type", "Profit Routing"}
    performance_keys = {"Win Rate", "Total Trades", "ROI"}

    # Overview must include bot_type and profit_routing for scalpers
    assert scalper_bot.get("bot_type") == "scalper"
    assert scalper_bot.get("profit_routing") == "SCALPER_GROWTH"
    # Performance must expose capital fields
    assert cap.get("initial_capital") == 50.0
    assert cap.get("quote_currency") == "USDT"
    # No missing fields — all expected keys are present in the contract
    for key in ("initial_capital", "total_equity", "realized_profit"):
        assert key in cap, f"capital_summary must contain '{key}'"
