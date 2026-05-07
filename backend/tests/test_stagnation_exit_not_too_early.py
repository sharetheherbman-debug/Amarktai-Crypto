import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_stagnation_exit_window_not_too_early():
    from config import STAGNATION_EXIT_MINUTES

    assert STAGNATION_EXIT_MINUTES >= 30
