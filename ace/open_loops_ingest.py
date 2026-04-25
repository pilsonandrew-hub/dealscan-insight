from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .repository import Item, ItemRepository, ValidationError
from .storage import DB_PATH


DEFAULT_SOURCE_LABEL = "continuity/open-loops.json"
DEFAULT_SOURCE_PATH = Path(__file__).resolve().parent.parent / DEFAULT_SOURCE_LABEL
ITEM_TYPE = "continuity_open_loop"
INGEST_ACTOR = "ace.open_loops_ingest"
ACTIVE_LIKE_STATUSES = {"open", "blocked", "waiting"}
SUPPORTED_STATUSES = ACTIVE_LIKE_STATUSES | {"closed"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
REQUIRED_FIELDS = ("id", "title", "status", "severity", "next_start", "closure_condition", "owner")


class OpenLoopIngestError(ValueError):
    """Raised when continuity open-loop ingest cannot proceed."""


class OpenLoopParseError(OpenLoopIngestError):
    """Raised when the source file cannot be parsed as JSON."""


class OpenLoopSchemaError(OpenLoopIngestError):
    """Raised when the source shape does not match the narrow contract."""


class UnsupportedOpenLoopStateError(OpenLoopIngestError):
    """Raised when the source item is not eligible for TRIAGE ingest."""


def ingest_continuity_open_loops(
    db_path: Path | str = DB_PATH,
    source_path: Path | str = DEFAULT_SOURCE_PATH,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
) -> list[Item]:
    """Read continuity/open-loops.json and mirror eligible items into ACE TRIAGE.

    The proof is intentionally narrow: it only accepts active-like open-loop items,
    preserves provenance via `source` + deterministic `source_session`, and reuses
    an existing ACE row on replay instead of creating duplicates.
    """
    repo = ItemRepository(db_path)
    source_path = Path(source_path)
    payload = _load_payload(source_path)

    ingested: list[Item] = []
    for raw_item in payload["items"]:
        normalized_item = _normalize_source_item(raw_item)
        source_session = _build_source_session(
            source_label=source_label,
            source_item_id=normalized_item["id"],
            canonical_digest=_canonical_digest(normalized_item),
        )

        existing = repo.get_item_by_source_and_session(source_label, source_session)
        if existing is not None:
            ingested.append(existing)
            continue

        item = repo.create_item(
            item_type=ITEM_TYPE,
            title=normalized_item["title"],
            description=normalized_item["closure_condition"],
            state="TRIAGE",
            priority_hint=normalized_item["severity"],
            source=source_label,
            source_session=source_session,
            owner=normalized_item["owner"],
            actor=INGEST_ACTOR,
        )
        ingested.append(item)

    return ingested


def _load_payload(source_path: Path) -> dict[str, Any]:
    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpenLoopParseError(f"unable to read open-loop source: {source_path}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise OpenLoopParseError(f"malformed open-loop JSON: {source_path}") from exc

    if not isinstance(payload, dict):
        raise OpenLoopSchemaError("open-loop payload must be a JSON object")

    items = payload.get("items")
    if not isinstance(items, list):
        raise OpenLoopSchemaError("open-loop payload must contain an items array")

    return payload


def _normalize_source_item(raw_item: Any) -> dict[str, Any]:
    if not isinstance(raw_item, Mapping):
        raise OpenLoopSchemaError("each open-loop item must be a JSON object")

    normalized: dict[str, Any] = {}
    for field_name in REQUIRED_FIELDS:
        normalized[field_name] = _normalize_required_text(raw_item.get(field_name), field_name=field_name)

    status = normalized["status"].lower()
    if status not in SUPPORTED_STATUSES:
        legal = ", ".join(sorted(SUPPORTED_STATUSES))
        raise UnsupportedOpenLoopStateError(
            f"unsupported open-loop status: {normalized['status']} (legal statuses: {legal})"
        )
    if status == "closed":
        raise UnsupportedOpenLoopStateError("closed open-loop items are not eligible for TRIAGE ingest")
    if status not in ACTIVE_LIKE_STATUSES:
        legal = ", ".join(sorted(ACTIVE_LIKE_STATUSES))
        raise UnsupportedOpenLoopStateError(
            f"unsupported open-loop status: {normalized['status']} (eligible statuses: {legal})"
        )
    normalized["status"] = status

    severity = normalized["severity"].lower()
    if severity not in ALLOWED_SEVERITIES:
        legal = ", ".join(sorted(ALLOWED_SEVERITIES))
        raise OpenLoopSchemaError(f"invalid open-loop severity: {normalized['severity']} (legal severities: {legal})")
    normalized["severity"] = severity

    for key, value in raw_item.items():
        if key not in normalized:
            normalized[key] = _canonicalize_value(value)

    return normalized


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise OpenLoopSchemaError(f"{field_name} is required")
    if isinstance(value, str):
        normalized = value.strip()
    else:
        normalized = str(value).strip()
    if not normalized:
        raise OpenLoopSchemaError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return {str(key): _canonicalize_value(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, list):
        return [_canonicalize_value(item) for item in value]
    return value


def _canonical_digest(source_item: Mapping[str, Any]) -> str:
    canonical_json = json.dumps(
        _canonicalize_value(dict(source_item)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _build_source_session(*, source_label: str, source_item_id: str, canonical_digest: str) -> str:
    normalized_source_label = source_label.strip()
    if not normalized_source_label:
        raise ValidationError("source_label must not be empty or whitespace-only")
    normalized_source_item_id = source_item_id.strip()
    if not normalized_source_item_id:
        raise ValidationError("source_item_id must not be empty or whitespace-only")
    normalized_canonical_digest = canonical_digest.strip().lower()
    if not normalized_canonical_digest:
        raise ValidationError("canonical_digest must not be empty or whitespace-only")
    return f"{normalized_source_label}|{normalized_source_item_id}|{normalized_canonical_digest}"
