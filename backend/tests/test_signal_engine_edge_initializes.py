import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_compute_edge_initializes_edge():
    from services.signal_engine import SignalEngine

    se = SignalEngine(db=None, config={"MIN_EDGE_BPS": 0.0})
    edge = se._compute_edge(
        regime={"regime": "stable_uptrend", "confidence": 0.9},
        ml={"predicted_change": 1.0, "confidence": 0.8, "direction": "up", "is_simulated": False},
        alpha={"score": 0.2, "confidence": 0.7},
        history={"avg_profit_bps": 5.0, "win_rate": 0.6},
        side="buy",
    )
    assert isinstance(edge, float)
