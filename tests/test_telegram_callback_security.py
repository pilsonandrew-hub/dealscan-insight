import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.ingest.telegram_auth import resolve_operator_user_id, verify_telegram_secret_header
from webapp.routers.ingest import telegram_callback_webhook


def test_telegram_callback_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            telegram_callback_webhook(
                {"callback_query": {"id": "1", "data": "pass_x"}},
                x_telegram_bot_api_secret_token=None,
            )
        )
    assert exc.value.status_code == 401


def test_telegram_callback_rejects_unknown_operator(monkeypatch):
    from webapp.routers import ingest as ingest_mod

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(ingest_mod, "TELEGRAM_BOT_TOKEN", "bot-token")
    opp_id = str(uuid.uuid4())
    payload = {
        "callback_query": {
            "id": "cb-1",
            "data": f"pass_{opp_id}",
            "from": {"id": 999999},
        }
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                telegram_callback_webhook(
                    payload,
                    x_telegram_bot_api_secret_token="test-secret",
                )
            )
    assert exc.value.status_code == 403


def test_verify_telegram_secret_header():
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "abc"
    assert verify_telegram_secret_header("abc") is True
    assert verify_telegram_secret_header("wrong") is False


def test_resolve_operator_from_map(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OPERATOR_MAP", '{"12345":"user-uuid-1"}')
    assert resolve_operator_user_id(12345) == "user-uuid-1"
    assert resolve_operator_user_id(1) is None


def test_telegram_callback_authorized_operator_submits_rover_action(monkeypatch):
    from webapp.routers import ingest as ingest_mod

    operator_uuid = str(uuid.uuid4())
    opp_id = str(uuid.uuid4())
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_OPERATOR_MAP", f'{{"12345":"{operator_uuid}"}}')
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(ingest_mod, "TELEGRAM_BOT_TOKEN", "bot-token")

    payload = {
        "callback_query": {
            "id": "cb-ok",
            "data": f"buy_{opp_id}",
            "from": {"id": 12345},
        }
    }
    mock_submit = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch.object(ingest_mod, "_submit_rover_action", mock_submit), patch("httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = asyncio.run(
            telegram_callback_webhook(
                payload,
                x_telegram_bot_api_secret_token="test-secret",
            )
        )

    mock_submit.assert_awaited_once_with(
        opportunity_id=opp_id,
        action="buy",
        user_id=operator_uuid,
    )
    assert result["ok"] is True
