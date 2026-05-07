"""
Verify that paper-reset/validate accepts all documented payload field aliases.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_reset_validate_accepts_all_payload_aliases(monkeypatch):
    """All accepted_fields aliases must pass validation when correct password provided."""
    import database as db
    from routes.system_mode import PaperResetRequest, validate_paper_reset

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "unit-test-reset")
    user_id = "alias_test_user"

    mock_sys_modes = MagicMock()
    mock_sys_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    with patch.object(db, "system_modes_collection", mock_sys_modes):
        for alias_value, payload in [
            ("password", PaperResetRequest(password="unit-test-reset")),
            ("resetPassword", PaperResetRequest(resetPassword="unit-test-reset")),
            ("reset_password", PaperResetRequest(reset_password="unit-test-reset")),
            ("confirmation", PaperResetRequest(confirmation="unit-test-reset")),
            ("confirmation_phrase", PaperResetRequest(confirmation_phrase="unit-test-reset")),
            ("confirm", PaperResetRequest(confirm="unit-test-reset")),
        ]:
            result = await validate_paper_reset(request=payload, user_id=user_id)
            assert result["valid"] is True, f"alias '{alias_value}' did not return valid=True"


@pytest.mark.asyncio
async def test_paper_reset_validate_missing_password_returns_error(monkeypatch):
    """Empty payload with no password must return valid=False."""
    import database as db
    from routes.system_mode import PaperResetRequest, validate_paper_reset

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "unit-test-reset")
    user_id = "alias_missing_user"

    mock_sys_modes = MagicMock()
    mock_sys_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    with patch.object(db, "system_modes_collection", mock_sys_modes):
        result = await validate_paper_reset(
            request=PaperResetRequest(),
            user_id=user_id,
        )
    # Empty request yields no candidate password → must not be valid
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_paper_reset_validate_wrong_password_returns_403(monkeypatch):
    """Wrong password must return valid=False with reason=wrong_password."""
    import database as db
    from routes.system_mode import PaperResetRequest, validate_paper_reset

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "unit-test-reset")
    user_id = "alias_wrong_pass_user"

    mock_sys_modes = MagicMock()
    mock_sys_modes.find_one = AsyncMock(
        return_value={"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    with patch.object(db, "system_modes_collection", mock_sys_modes):
        result = await validate_paper_reset(
            request=PaperResetRequest(password="WRONG_PASSWORD"),
            user_id=user_id,
        )
    assert result["valid"] is False
    assert result.get("reason") == "wrong_password"


def test_accepted_fields_match_all_aliases():
    """PAPER_RESET_ACCEPTED_FIELDS must include all six documented aliases."""
    from routes.system_mode import PAPER_RESET_ACCEPTED_FIELDS

    expected = {
        "password",
        "resetPassword",
        "reset_password",
        "confirmation",
        "confirmation_phrase",
        "confirm",
    }
    actual = set(PAPER_RESET_ACCEPTED_FIELDS)
    missing = expected - actual
    assert not missing, f"Missing accepted_fields aliases: {missing}"
