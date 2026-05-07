import os
import sys
from collections import defaultdict

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_no_route_collisions_strict():
    import server

    seen = defaultdict(int)
    for route in server.app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            seen[(method, path)] += 1

    duplicates = [k for k, v in seen.items() if v > 1]
    assert duplicates == []
