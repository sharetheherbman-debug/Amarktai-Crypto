import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.regime_classifier import classify_regime, strategy_regime_allowed
from services.entry_quality import (
    compute_entry_confidence,
    evaluate_expectancy_gate,
    derive_adaptive_discipline,
    evaluate_pre_timeout_exit,
)


def test_regime_classifier_unknown_low_confidence_biases_no_trade():
    regime = classify_regime(
        raw_regime="choppy",
        trend="neutral",
        trend_pct=0.1,
        volatility_pct=0.5,
        spread_pct=1.8,
        depth_notional=2000,
    )
    gate = strategy_regime_allowed("scalper", regime["regime"], regime["confidence"])
    assert regime["regime"] == "unknown"
    assert gate["allowed"] is False
    assert gate["reason_code"] == "REGIME_UNKNOWN_BLOCK"


def test_strategy_regime_mapping_blocks_scalper_in_trending_down():
    gate = strategy_regime_allowed("scalper", "trending_down", 0.9)
    assert gate["allowed"] is False
    assert gate["reason_code"] == "REGIME_BLOCK"


def test_signal_consensus_conflict_rejected_and_strong_alignment_passes():
    conflict = compute_entry_confidence(
        bot_type="scalper",
        regime_confidence=0.55,
        ml_confidence=0.52,
        fetchai_confidence=51,
        coinstats_strength=40,
        consensus_strength=0,
        consensus_sources=1,
        direction_conflict=True,
    )
    strong = compute_entry_confidence(
        bot_type="normal",
        regime_confidence=0.85,
        ml_confidence=0.82,
        fetchai_confidence=88,
        coinstats_strength=77,
        consensus_strength=3,
        consensus_sources=3,
        direction_conflict=False,
    )
    assert conflict["accepted"] is False
    assert conflict["reason_code"] == "LOW_ENTRY_CONFIDENCE"
    assert strong["accepted"] is True
    assert strong["entry_confidence_score"] > conflict["entry_confidence_score"]


def test_expectancy_gate_requires_stronger_edge_for_scalpers():
    scalper = evaluate_expectancy_gate(
        bot_type="scalper",
        expected_move_pct=0.8,
        estimated_cost_pct=0.45,
        market_quality=0.7,
        entry_confidence_score=0.75,
        timeout_risk_pct=0.12,
    )
    normal = evaluate_expectancy_gate(
        bot_type="normal",
        expected_move_pct=0.8,
        estimated_cost_pct=0.45,
        market_quality=0.7,
        entry_confidence_score=0.75,
        timeout_risk_pct=0.08,
    )
    assert scalper["required_net_edge_pct"] > normal["required_net_edge_pct"]
    assert scalper["accepted"] is False
    assert normal["reason_code"] in {"EXPECTANCY_OK", "INSUFFICIENT_NET_EXPECTANCY"}


def test_early_invalidation_can_trigger_before_timeout_fallback():
    reason = evaluate_pre_timeout_exit(
        bot_class="scalper",
        hold_ratio=0.62,
        pnl_pct=0.01,
        min_progress_pct=0.12,
        regime_trend="neutral",
        regime_confidence=0.0,
    )
    assert reason == "scalper_no_progress_exit"


def test_adaptive_discipline_tightens_after_repeated_timeout_losses():
    trades = [
        {"net_pnl": -10, "trade_close_reason": "max_hold_exceeded"},
        {"net_pnl": -8, "trade_close_reason": "max_hold_exceeded"},
        {"net_pnl": -12, "trade_close_reason": "max_hold_exceeded"},
        {"net_pnl": -6, "trade_close_reason": "time_decay_exit"},
        {"net_pnl": 2, "trade_close_reason": "take_profit"},
        {"net_pnl": -4, "trade_close_reason": "max_hold_exceeded"},
    ]
    adaptive = derive_adaptive_discipline(trades)
    assert adaptive["reason_code"] in {"ADAPTIVE_STAND_DOWN", "ADAPTIVE_TIGHTENED"}
    assert adaptive["edge_uplift_pct"] > 0


def test_phase3_reason_codes_and_radar_truth_fields_are_wired():
    backend_root = os.path.join(os.path.dirname(__file__), "..", "backend")
    engine_src = open(os.path.join(backend_root, "paper_trading_engine.py"), encoding="utf-8").read()
    radar_src = open(os.path.join(backend_root, "routes", "radar.py"), encoding="utf-8").read()

    assert "INSUFFICIENT_NET_EXPECTANCY" in engine_src
    assert "SIGNAL_CONFLICT" in engine_src
    assert "REGIME_BLOCK" in engine_src or "REGIME_UNKNOWN_BLOCK" in engine_src
    assert "trade_close_reason_code" in engine_src
    assert "entry_reason_code" in radar_src
    assert "regime_confidence" in radar_src
