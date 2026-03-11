"""
Production Stability Repair – targeted tests for the 6-task fix pack.

Verifies:
1. data-integrity endpoint uses db.db (not db.database) attribute
2. server.py countdown uses canonical capital_source literals
3. self_healing.SelfHealingSystem.get_status() returns correct state transitions
4. exchange status SUPPORTED_EXCHANGES is from exchange_adapter (single source)
5. /api/market/snapshot is NOT registered as a public route
6. no active runtime modules import from _archive or removed_duplicates paths
"""

import os
import sys
import ast

ROOT = os.path.join(os.path.dirname(__file__), "..")
BACKEND_DIR = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── TASK 2: data-integrity endpoint uses canonical db.db accessor ─────────

def test_data_integrity_uses_db_db_not_db_database():
    """diagnostics.py must use db.db[...] not db.database[...] for ad-hoc collections."""
    src = _read("backend/routes/diagnostics.py")
    assert 'db.database["paper_wallets"]' not in src, (
        "data-integrity: stale db.database access still present for paper_wallets"
    )
    assert 'db.database["fills_ledger"]' not in src, (
        "data-integrity: stale db.database access still present for fills_ledger"
    )
    # Canonical pattern must be present
    assert 'db.db["paper_wallets"]' in src
    assert 'db.db["fills_ledger"]' in src


# ── TASK 1/COUNTDOWN: server.py uses canonical capital_source literals ────

def test_server_countdown_has_wallet_snapshot_source():
    """server.py countdown must declare capital_source = 'wallet_snapshot'."""
    src = _read("backend/server.py")
    assert 'capital_source = "wallet_snapshot"' in src, (
        "server.py countdown missing capital_source = 'wallet_snapshot' literal"
    )


def test_server_countdown_has_all_three_capital_sources():
    """server.py countdown must have all three canonical capital_source values."""
    src = _read("backend/server.py")
    assert 'capital_source = "wallet_snapshot"' in src
    assert 'capital_source = "ledger_equity_zar"' in src
    assert 'capital_source = "bots_current_capital_sum"' in src


# ── TASK 3: exchange status converges on exchange_adapter.SUPPORTED_EXCHANGES ──

def test_diagnostics_exchange_uses_exchange_adapter_list():
    """diagnostics.py exchange_keys section must import SUPPORTED_EXCHANGES from exchange_adapter."""
    src = _read("backend/routes/diagnostics.py")
    assert "from services.exchange_adapter import SUPPORTED_EXCHANGES" in src, (
        "diagnostics must import SUPPORTED_EXCHANGES from exchange_adapter, not bot_rules"
    )


def test_exchange_adapter_is_canonical_exchange_list():
    """exchange_adapter.SUPPORTED_EXCHANGES must contain all required canonical exchanges."""
    from services.exchange_adapter import SUPPORTED_EXCHANGES
    # Required exchanges (minimum canonical set)
    required = {"luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"}
    assert required.issubset(set(SUPPORTED_EXCHANGES)), (
        f"exchange_adapter.SUPPORTED_EXCHANGES missing required exchanges: "
        f"{required - set(SUPPORTED_EXCHANGES)}"
    )
    assert len(SUPPORTED_EXCHANGES) >= len(required)


# ── TASK 4: /api/market/snapshot is NOT a public route ───────────────────

def test_market_snapshot_is_not_a_public_route():
    """/api/market/snapshot must not be registered as a public route.
    The market snapshot is internal engine logic only."""
    src = _read("backend/routes/market_api.py")
    assert "/snapshot" not in src, (
        "market_api.py must not define a /snapshot public route"
    )


def test_no_frontend_references_to_market_snapshot():
    """No frontend JS should reference /api/market/snapshot."""
    import os
    frontend_src = os.path.join(ROOT, "frontend", "src")
    if not os.path.isdir(frontend_src):
        return  # Skip if frontend not present
    for root_dir, _dirs, files in os.walk(frontend_src):
        for fn in files:
            if not fn.endswith((".js", ".ts", ".jsx", ".tsx")):
                continue
            fp = os.path.join(root_dir, fn)
            with open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
            assert "api/market/snapshot" not in content, (
                f"{fp}: references /api/market/snapshot (should be internal-only)"
            )


# ── SELF-HEALING: get_status() state transitions ─────────────────────────

def test_self_healing_stopped_state():
    """SelfHealingSystem.get_status() must return state='stopped' when last_result='stopped'."""
    from engines.self_healing import SelfHealingSystem
    shs = SelfHealingSystem()
    shs.is_running = False
    shs.last_result = "stopped"
    status = shs.get_status()
    assert status["state"] == "stopped", f"Expected 'stopped', got '{status['state']}'"
    assert status["enabled"] is False


def test_self_healing_idle_state():
    """SelfHealingSystem.get_status() must return state='idle' for fresh instance."""
    from engines.self_healing import SelfHealingSystem
    shs = SelfHealingSystem()
    assert shs.is_running is False
    status = shs.get_status()
    assert status["state"] == "idle"


def test_self_healing_running_state():
    """SelfHealingSystem.get_status() must return state='running' when is_running=True."""
    from engines.self_healing import SelfHealingSystem
    shs = SelfHealingSystem()
    shs.is_running = True
    status = shs.get_status()
    assert status["state"] == "running"
    assert status["enabled"] is True


def test_self_healing_get_status_in_engine_file():
    """Canonical get_status() must be defined in engines/self_healing.py."""
    src = _read("backend/engines/self_healing.py")
    assert "def get_status(" in src
    assert '"enabled"' in src
    assert '"state"' in src
    assert '"last_result"' in src


# ── TASK 6: no active imports from archive/backup paths ──────────────────

def test_no_active_imports_from_archive():
    """Active Python modules must not import from _archive or removed_duplicates."""
    import os
    active_dirs = [
        os.path.join(BACKEND_DIR, "routes"),
        os.path.join(BACKEND_DIR, "services"),
        os.path.join(BACKEND_DIR, "engines"),
    ]
    # Also check top-level backend py files
    top_files = [
        f for f in os.listdir(BACKEND_DIR)
        if f.endswith(".py") and not f.startswith(".")
    ]

    violations = []
    bad_patterns = ["_archive", "removed_duplicates", ".bak"]

    for d in active_dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(d, fn)
            with open(fp, encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for pat in bad_patterns:
                        if pat in line and ("import" in line or "from" in line):
                            violations.append(f"{fp}:{lineno}: {stripped}")

    for fn in top_files:
        fp = os.path.join(BACKEND_DIR, fn)
        with open(fp, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat in bad_patterns:
                    if pat in line and ("import" in line or "from" in line):
                        violations.append(f"{fp}:{lineno}: {stripped}")

    assert not violations, (
        "Active runtime code imports from archive/backup paths:\n"
        + "\n".join(violations)
    )
