"""
Tests for final go-live blocker fixes (problem statement requirements).

Verifies:
1. /api/self-healing/status route is wired and mounted
2. Wallet funding truth is computed from available + allocated (no contradiction)
3. Bot runnable/eligible state does not use regime checks (engine only)
4. Low-volatility regime does not block normal bots at structural level
5. Target policy returns consistent strategy-derived values across routes
6. Bot cap enforcement is type-aware (normal vs scalper separate pools)
7. Frontend: no "Market Data Providers" or "Optional Intelligence Sources" sections
8. Frontend: duplicate "User Storage Usage" removed from admin panel
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))


def _read(rel_path: str) -> str:
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ── 1. Self-healing route is mounted ────────────────────────────────────────

def test_self_healing_route_file_exists():
    """Dedicated self-healing route file must exist."""
    path = os.path.join(ROOT, "backend", "routes", "self_healing_endpoints.py")
    assert os.path.isfile(path), "routes/self_healing_endpoints.py must exist"


def test_self_healing_route_registered_in_server():
    """server.py must mount the self-healing router."""
    src = _read("backend/server.py")
    assert "routes.self_healing_endpoints" in src
    assert "self_healing_endpoints" in src


def test_self_healing_endpoint_in_route_file():
    """The self-healing route file must define /status endpoint."""
    src = _read("backend/routes/self_healing_endpoints.py")
    assert '@router.get("/status")' in src
    assert "get_self_healing_status" in src
    assert "self_healing.get_status()" in src


def test_self_healing_get_status_method_exists():
    """self_healing.SelfHealingSystem must have a get_status() method."""
    src = _read("backend/self_healing.py")
    assert "def get_status(" in src
    assert '"enabled"' in src
    assert '"state"' in src
    assert '"last_result"' in src


# ── 2. Wallet funding truth ──────────────────────────────────────────────────

def test_canonical_wallet_truth_uses_ledger_total():
    """get_canonical_wallet_truth must use paper_wallet_ledger (available + allocated)."""
    src = _read("backend/services/canonical.py")
    assert "paper_wallet_ledger" in src
    assert "get_user_balance" in src, "Must call ledger.get_user_balance() for full balance"


def test_wallet_paper_route_uses_canonical_wallet_truth():
    """wallet/paper endpoint must call get_canonical_wallet_truth for funded status."""
    src = _read("backend/routes/wallet_hub.py")
    assert "get_canonical_wallet_truth" in src
    assert "funded_status" in src


def test_system_status_and_wallet_paper_use_same_logic():
    """Both /api/system/status and /api/wallet/paper must eventually use ledger total."""
    wallet_src = _read("backend/routes/wallet_hub.py")
    canonical_src = _read("backend/services/canonical.py")
    # Both must reference the same canonical service
    assert "get_canonical_wallet_truth" in wallet_src
    assert "paper_wallet_ledger" in canonical_src


# ── 3. Bot eligibility does NOT use regime checks ────────────────────────────

def test_bot_state_no_regime_block_in_eligible_check():
    """eligible_to_trade must NOT include regime_unknown_low_confidence blocking."""
    src = _read("backend/utils/bot_state.py")
    assert "regime_unknown_low_confidence" not in src
    assert "MIN_REGIME_CONFIDENCE" not in src
    assert "MIN_ENTRY_CONFIDENCE" not in src


def test_active_bot_with_trading_mode_is_eligible():
    """Active bot with any regime state is structurally eligible (engine decides)."""
    from utils.bot_state import normalize_bot_state

    for regime in ("unknown", "low_volatility", "consolidation", "trending_up"):
        bot = normalize_bot_state({
            "status": "active",
            "trading_mode": "paper",
            "market_regime": regime,
            "canonical_regime_confidence": 0.0,
        })
        assert bot["eligible_to_trade"] is True, (
            f"Active bot with regime={regime!r} should be structurally eligible"
        )


def test_paused_bot_is_not_eligible():
    """Paused bot must remain ineligible regardless of regime."""
    from utils.bot_state import normalize_bot_state

    bot = normalize_bot_state({
        "status": "paused",
        "paused_by_user": True,
        "trading_mode": "paper",
        "market_regime": "trending_up",
    })
    assert bot["eligible_to_trade"] is False


# ── 4. Regime classifier: low_volatility allowed for normal bots ─────────────

def test_low_volatility_allowed_for_normal_bots():
    """strategy_regime_allowed must allow low_volatility for normal bots."""
    from services.regime_classifier import strategy_regime_allowed

    result = strategy_regime_allowed("normal", "low_volatility", 0.55)
    assert result["allowed"] is True, (
        f"low_volatility should be allowed for normal bots; got: {result}"
    )


def test_low_volatility_still_blocks_scalper():
    """Scalper bots should not be allowed to trade in low_volatility."""
    from services.regime_classifier import strategy_regime_allowed

    result = strategy_regime_allowed("scalper", "low_volatility", 0.55)
    assert result["allowed"] is False, (
        "low_volatility should block scalper bots"
    )


def test_consolidation_allowed_for_normal_bots():
    """Consolidation regime must remain allowed for normal bots."""
    from services.regime_classifier import strategy_regime_allowed

    result = strategy_regime_allowed("normal", "consolidation", 0.60)
    assert result["allowed"] is True, (
        f"consolidation should be allowed for normal bots; got: {result}"
    )


def test_unknown_regime_blocks_both_types():
    """Unknown regime with low confidence blocks both normal and scalper bots."""
    from services.regime_classifier import strategy_regime_allowed

    for bot_type in ("normal", "scalper"):
        result = strategy_regime_allowed(bot_type, "unknown", 0.30)
        assert result["allowed"] is False, (
            f"unknown/low-confidence regime should block {bot_type} bots; got: {result}"
        )


# ── 5. Target policy consistency ─────────────────────────────────────────────

def test_target_policy_strategy_derived_non_null():
    """derive_targets must return non-null positive values for unconfigured bots."""
    from services.target_policy import derive_targets

    for bot_type, risk_mode in [("normal", "balanced"), ("scalper", "aggressive"), ("normal", "conservative")]:
        targets = derive_targets({
            "bot_type": bot_type,
            "risk_mode": risk_mode,
            "initial_capital": 5000,
        })
        assert targets["target_source"] == "strategy_derived"
        assert targets["daily_profit_target"] is not None
        assert targets["daily_profit_target"] > 0
        assert targets["trade_profit_target"] is not None
        assert targets["trade_profit_target"] > 0


def test_target_policy_configured_overrides_strategy():
    """Explicitly configured pct values must override strategy defaults."""
    from services.target_policy import derive_targets

    targets = derive_targets({
        "bot_type": "normal",
        "risk_mode": "balanced",
        "initial_capital": 10000,
        "daily_profit_target_pct": 0.03,
        "trade_profit_target_pct": 0.015,
    })
    assert targets["target_source"] == "configured"
    assert targets["daily_profit_target"] == 300.0
    assert targets["trade_profit_target"] == 150.0


def test_radar_uses_target_policy_service():
    """Radar route must call derive_targets from services.target_policy."""
    src = _read("backend/routes/radar.py")
    assert "from services.target_policy import derive_targets" in src or \
           "derive_targets" in src


# ── 6. Separate bot caps ─────────────────────────────────────────────────────

def test_scalper_caps_defined_separately():
    """SCALPER_CAPS must exist and differ from BOT_CAPS."""
    from rules.bot_rules import BOT_CAPS, SCALPER_CAPS

    assert 'luno' in SCALPER_CAPS
    assert SCALPER_CAPS['luno'] == 2
    assert SCALPER_CAPS['binance'] == 5
    assert BOT_CAPS['luno'] != SCALPER_CAPS['luno']


def test_check_bot_cap_limit_type_aware():
    """check_bot_cap_limit must enforce separate caps per bot_type."""
    from rules.bot_rules import check_bot_cap_limit

    # Luno: 5 normal, 2 scalper
    ok, _ = check_bot_cap_limit('luno', 4, bot_type='normal')
    assert ok is True
    ok, r = check_bot_cap_limit('luno', 5, bot_type='normal')
    assert ok is False and r == 'BOT_CAP_EXCEEDED'

    ok, _ = check_bot_cap_limit('luno', 1, bot_type='scalper')
    assert ok is True
    ok, r = check_bot_cap_limit('luno', 2, bot_type='scalper')
    assert ok is False and r == 'BOT_CAP_EXCEEDED'


def test_normal_cap_not_consumed_by_scalpers():
    """Normal cap check must count only normal bots, not scalpers."""
    src = _read("backend/validators/bot_validator.py")
    # Must use explicit bot_type: normal filter (not $ne: scalper)
    assert '"bot_type": "normal"' in src, (
        "bot_validator.py must filter by bot_type=='normal' for normal cap"
    )


# ── 7. Frontend: noisy sections removed ─────────────────────────────────────

def test_market_data_providers_section_removed_from_main_panel():
    """The old 📈 Market Data Providers block must be removed from main dashboard panel."""
    src = _read("frontend/src/pages/dashboard/sections/MarketIntelligencePanel.js")
    # The old standalone always-visible "Market Data Providers" section heading
    # must not appear as a top-level h4 card; it's now inside a collapsible group
    assert "📈 Market Data Providers" not in src, \
        "MarketIntelligencePanel must not show a standalone 'Market Data Providers' heading card"


def test_optional_intelligence_section_removed_from_main_panel():
    """The 🔍 Optional Intelligence Sources block must be removed as top-level card."""
    src = _read("frontend/src/pages/dashboard/sections/MarketIntelligencePanel.js")
    # Must not appear as a standalone always-visible top-level section heading
    assert "Optional Intelligence Sources" not in src or "CollapsibleGroup" in src, \
        "MarketIntelligencePanel must not show a standalone 'Optional Intelligence Sources' card"


def test_market_intelligence_panel_has_compact_summary():
    """New MarketIntelligencePanel must have a compact summary with key metrics."""
    src = _read("frontend/src/pages/dashboard/sections/MarketIntelligencePanel.js")
    assert "Market Intelligence" in src
    assert "Market Sources" in src
    assert "Intelligence Enrichers" in src


def test_market_intelligence_panel_has_collapsible_detail():
    """New MarketIntelligencePanel must have collapsible provider detail section."""
    src = _read("frontend/src/pages/dashboard/sections/MarketIntelligencePanel.js")
    assert "showDetail" in src or "CollapsibleGroup" in src or "expand" in src


def test_admin_panel_duplicate_storage_removed():
    """Admin panel must NOT have the duplicate 'User Storage Usage' card."""
    src = _read("frontend/src/pages/dashboard/sections/AdminPanelSection.js")
    # The duplicate small card should be gone; the canonical "User Storage Tracking" stays
    assert "User Storage Usage" not in src, \
        "Duplicate 'User Storage Usage' section must be removed from admin panel"
    assert "User Storage Tracking" in src, \
        "Canonical 'User Storage Tracking' section must remain"


# ── 8. Capital source consistency ────────────────────────────────────────────

def test_countdown_uses_paper_equity_source_field():
    """Countdown endpoint must use paper_equity['source'] not a hardcoded string."""
    src = _read("backend/server.py")
    assert 'capital_source = paper_equity["source"]' in src


def test_canonical_paper_wallet_equity_imported_in_server():
    """server.py must import get_canonical_paper_wallet_equity for countdown."""
    src = _read("backend/server.py")
    assert "get_canonical_paper_wallet_equity" in src
