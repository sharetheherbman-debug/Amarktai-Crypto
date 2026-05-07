import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_safe_mode_expectancy_profile_positive():
    from config import RISK_MODE_CONFIG

    safe = RISK_MODE_CONFIG["safe"]
    tp_pct = float(safe["take_profit_pct"]) * 100
    sl_pct = float(safe["stop_loss_pct"]) * 100
    assumed_round_trip_cost_pct = 0.36
    win_prob = 0.5

    avg_win_after_costs = max(tp_pct - assumed_round_trip_cost_pct, 0.0)
    avg_loss_after_costs = sl_pct + assumed_round_trip_cost_pct
    expected_value_pct = (win_prob * avg_win_after_costs) - ((1 - win_prob) * avg_loss_after_costs)

    assert tp_pct >= 2.2
    assert expected_value_pct > 0
