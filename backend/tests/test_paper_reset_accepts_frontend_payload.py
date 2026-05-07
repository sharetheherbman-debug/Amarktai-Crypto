import os
import sys
import pytest
from fastapi import HTTPException

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_paper_reset_validate_accepts_password_aliases(monkeypatch):
    import database as db
    from routes.system_mode import PaperResetRequest, validate_paper_reset

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "unit-test-reset")
    user_id = "paper_reset_alias_user"
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    for payload in (
        PaperResetRequest(password="unit-test-reset"),
        PaperResetRequest(resetPassword="unit-test-reset"),
        PaperResetRequest(reset_password="unit-test-reset"),
        PaperResetRequest(confirmation="unit-test-reset"),
        PaperResetRequest(confirmation_phrase="unit-test-reset"),
        PaperResetRequest(confirm="unit-test-reset"),
    ):
        result = await validate_paper_reset(request=payload, user_id=user_id)
        assert result["valid"] is True


@pytest.mark.asyncio
async def test_paper_reset_wrong_password_returns_403(monkeypatch):
    import database as db
    from routes import system_mode

    monkeypatch.setenv("PAPER_RESET_PASSWORD", "unit-test-reset")
    user_id = "paper_reset_wrong_password_user"
    await db.system_modes_collection.insert_one(
        {"user_id": user_id, "paperTrading": True, "liveTrading": False}
    )

    with pytest.raises(HTTPException) as exc:
        await system_mode.paper_reset(
            request=system_mode.PaperResetRequest(confirmation_phrase="WRONG"),
            user_id=user_id,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["reason"] == "wrong_password"
