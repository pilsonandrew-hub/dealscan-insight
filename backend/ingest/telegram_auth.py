"""Telegram webhook authentication and operator identity resolution."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def telegram_webhook_secret() -> str:
    return (
        os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        or os.getenv("TELEGRAM_BOT_WEBHOOK_SECRET", "").strip()
    )


def verify_telegram_secret_header(provided: Optional[str]) -> bool:
    expected = telegram_webhook_secret()
    if not expected:
        logger.warning("[TELEGRAM_AUTH] TELEGRAM_WEBHOOK_SECRET not configured")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided.strip(), expected)


def _parse_operator_map(raw: str) -> dict[int, str]:
    mapping: dict[int, str] = {}
    text = (raw or "").strip()
    if not text:
        return mapping
    try:
        if text.startswith("{"):
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    mapping[int(key)] = str(value).strip()
                return mapping
    except json.JSONDecodeError:
        pass
    for part in text.split(","):
        piece = part.strip()
        if ":" not in piece:
            continue
        tg_id, user_id = piece.split(":", 1)
        try:
            mapping[int(tg_id.strip())] = user_id.strip()
        except ValueError:
            continue
    return mapping


def resolve_operator_user_id(telegram_user_id: Optional[int]) -> Optional[str]:
    """Map Telegram user id to DealerScope auth user UUID."""
    if telegram_user_id is None:
        return None
    operator_map = _parse_operator_map(os.getenv("TELEGRAM_OPERATOR_MAP", ""))
    if telegram_user_id in operator_map:
        return operator_map[telegram_user_id]
    default_operator = os.getenv("DEALERSCOPE_OPERATOR_USER_ID", "").strip()
    if default_operator and len(operator_map) == 0:
        return default_operator
    return None
