import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_seed_fresh_paper_bots_route_declared():
    path = os.path.join(ROOT, "routes", "bot_lifecycle.py")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    assert '@router.post("/seed-paper")' in src

