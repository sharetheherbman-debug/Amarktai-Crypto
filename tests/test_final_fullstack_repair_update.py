from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_normalize_bot_state_forces_eligibility_coherence_with_activity_state():
    src = _read("backend/utils/bot_state.py")
    assert "if not activity_runnable and eligible:" in src
    assert '"runnable": activity_runnable and eligible' in src


def test_decision_trace_supports_per_bot_recent_view():
    backend = _read("backend/routes/compatibility_endpoints.py")
    frontend = _read("frontend/src/components/DecisionTrace.js")
    assert "bot_id: Optional[str] = Query(None" in backend
    assert 'query["bot_id"] = bot_id' in backend
    assert "setSelectedBotId" in frontend
    assert "/advanced/decisions/recent?limit=20" in frontend


def test_removed_premium_providers_not_in_visible_default_lists():
    src = _read("frontend/src/constants/platforms.js")
    assert "export const INTELLIGENCE_ENRICHERS = ['etherscan', 'whale_alert', 'cryptopanic'];" in src
