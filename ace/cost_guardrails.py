from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import DB_PATH, bootstrap_db, connect, utc_now

DEFAULT_COST_LIMIT_CENTS = 0
DEFAULT_TOKEN_LIMIT = 0
DEFAULT_SESSION_COUNT_LIMIT = 0


@dataclass(frozen=True)
class CostGuardrailPolicy:
    cost_limit_cents: int = DEFAULT_COST_LIMIT_CENTS
    token_limit: int = DEFAULT_TOKEN_LIMIT
    session_count_limit: int = DEFAULT_SESSION_COUNT_LIMIT


@dataclass(frozen=True)
class CostGuardrailStatus:
    cost_limit_cents: int
    token_limit: int
    session_count_limit: int
    used_cost_cents: int
    used_tokens: int
    used_session_count: int
    blocked: bool
    reason: str | None


def load_cost_guardrail_policy_from_env() -> CostGuardrailPolicy:
    return CostGuardrailPolicy(
        cost_limit_cents=_env_non_negative_int("ACE_COST_LIMIT_CENTS", DEFAULT_COST_LIMIT_CENTS),
        token_limit=_env_non_negative_int("ACE_TOKEN_LIMIT", DEFAULT_TOKEN_LIMIT),
        session_count_limit=_env_non_negative_int("ACE_SESSION_COUNT_LIMIT", DEFAULT_SESSION_COUNT_LIMIT),
    )


def record_cost_usage(
    db_path: Path | str = DB_PATH,
    *,
    cost_cents: int = 0,
    tokens: int = 0,
    session_count: int = 0,
    source: str = "manual",
    source_session: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    normalized_cost = _normalize_non_negative_int(cost_cents, field_name="cost_cents")
    normalized_tokens = _normalize_non_negative_int(tokens, field_name="tokens")
    normalized_session_count = _normalize_non_negative_int(session_count, field_name="session_count")
    normalized_source = _normalize_required_text(source, field_name="source")
    normalized_recorded_at = recorded_at or utc_now()
    bootstrap_db(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO cost_usage (
                recorded_at, cost_cents, tokens, session_count, source, source_session
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_recorded_at,
                normalized_cost,
                normalized_tokens,
                normalized_session_count,
                normalized_source,
                source_session,
            ),
        )
        connection.commit()
    return {
        "recorded_at": normalized_recorded_at,
        "cost_cents": normalized_cost,
        "tokens": normalized_tokens,
        "session_count": normalized_session_count,
        "source": normalized_source,
        "source_session": source_session,
    }


def get_cost_guardrail_status(
    db_path: Path | str = DB_PATH,
    *,
    policy: CostGuardrailPolicy | None = None,
) -> CostGuardrailStatus:
    active_policy = policy or load_cost_guardrail_policy_from_env()
    bootstrap_db(db_path)
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(cost_cents), 0) AS used_cost_cents,
                COALESCE(SUM(tokens), 0) AS used_tokens,
                COALESCE(SUM(session_count), 0) AS used_session_count
            FROM cost_usage
            """
        ).fetchone()
    used_cost_cents = int(row["used_cost_cents"])
    used_tokens = int(row["used_tokens"])
    used_session_count = int(row["used_session_count"])
    reason = _first_block_reason(
        policy=active_policy,
        used_cost_cents=used_cost_cents,
        used_tokens=used_tokens,
        used_session_count=used_session_count,
    )
    return CostGuardrailStatus(
        cost_limit_cents=active_policy.cost_limit_cents,
        token_limit=active_policy.token_limit,
        session_count_limit=active_policy.session_count_limit,
        used_cost_cents=used_cost_cents,
        used_tokens=used_tokens,
        used_session_count=used_session_count,
        blocked=reason is not None,
        reason=reason,
    )


def enforce_cost_guardrails(
    db_path: Path | str = DB_PATH,
    *,
    policy: CostGuardrailPolicy | None = None,
) -> CostGuardrailStatus:
    return get_cost_guardrail_status(db_path, policy=policy)


def _first_block_reason(
    *,
    policy: CostGuardrailPolicy,
    used_cost_cents: int,
    used_tokens: int,
    used_session_count: int,
) -> str | None:
    if policy.cost_limit_cents > 0 and used_cost_cents >= policy.cost_limit_cents:
        return "cost_limit_exceeded"
    if policy.token_limit > 0 and used_tokens >= policy.token_limit:
        return "token_limit_exceeded"
    if policy.session_count_limit > 0 and used_session_count >= policy.session_count_limit:
        return "session_count_limit_exceeded"
    return None


def _env_non_negative_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return _normalize_non_negative_int(raw, field_name=name)


def _normalize_non_negative_int(value: int | str, *, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return normalized


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized
