import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_paper_execution_proof_route_mounted():
    from server import app
    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/paper-execution-proof" in paths

