"""Safe webhook-secret posture helpers shared by runtime and operator tooling."""

from __future__ import annotations

import hashlib
from typing import Any

MIN_WEBHOOK_SECRET_LENGTH = 24
FINGERPRINT_PREFIX = "sha256"
FINGERPRINT_LENGTH = 12
PLACEHOLDER_SECRET_VALUES = {
    "changeme",
    "change_me",
    "default",
    "dev-secret-change-in-prod",
    "replace-me",
    "replace_with_real_secret",
    "your_webhook_secret_here",
}


def looks_like_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return False
    if normalized in PLACEHOLDER_SECRET_VALUES:
        return True
    return normalized.startswith("your_") and normalized.endswith("_here")


def secret_fingerprint(value: str, *, length: int = FINGERPRINT_LENGTH) -> str | None:
    secret = value.strip()
    if not secret:
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"{FINGERPRINT_PREFIX}:{digest[:length]}"


def describe_secret_value(value: str, *, minimum_length: int = MIN_WEBHOOK_SECRET_LENGTH) -> dict[str, Any]:
    secret = value.strip()
    fingerprint = secret_fingerprint(secret)
    if not secret:
        state = "missing"
    elif looks_like_placeholder_secret(secret):
        state = "placeholder"
    elif len(secret) < minimum_length:
        state = "short"
    else:
        state = "configured"

    return {
        "configured": bool(secret),
        "fingerprint": fingerprint,
        "length": len(secret),
        "state": state,
    }


def build_webhook_secret_posture(
    active_secret: str,
    previous_secret: str,
    *,
    minimum_length: int = MIN_WEBHOOK_SECRET_LENGTH,
) -> dict[str, Any]:
    active = describe_secret_value(active_secret, minimum_length=minimum_length)
    previous = describe_secret_value(previous_secret, minimum_length=minimum_length)

    if previous["state"] == "missing":
        previous_state = "absent"
    elif previous_secret.strip() == active_secret.strip() and previous_secret.strip():
        previous_state = "duplicate_current"
    else:
        previous_state = str(previous["state"])

    previous_summary = dict(previous)
    previous_summary["state"] = previous_state

    accepts_previous = previous_state not in {"absent", "duplicate_current"}

    posture = {
        "active": active,
        "previous": previous_summary,
        "accepts_previous_secret": accepts_previous,
        "rotation_overlap_active": accepts_previous,
        "posture_ok": active["state"] == "configured" and previous_state not in {"duplicate_current", "placeholder"},
    }
    posture["summary"] = (
        f"active={active['state']}({active['fingerprint'] or 'missing'}) "
        f"previous={previous_state}({previous_summary['fingerprint'] or 'none'})"
    )
    return posture


def render_webhook_secret_posture_lines(posture: dict[str, Any]) -> list[str]:
    active = posture["active"]
    previous = posture["previous"]
    return [
        (
            "active secret posture: "
            f"state={active['state']} "
            f"fingerprint={active['fingerprint'] or 'missing'} "
            f"length={active['length']}"
        ),
        (
            "previous secret posture: "
            f"state={previous['state']} "
            f"fingerprint={previous['fingerprint'] or 'none'} "
            f"length={previous['length']}"
        ),
    ]
