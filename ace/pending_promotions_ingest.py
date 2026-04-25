from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .repository import Item, ItemRepository, ValidationError
from .storage import DB_PATH


DEFAULT_SOURCE_LABEL = "continuity/pending-promotions.json"
DEFAULT_SOURCE_PATH = Path(__file__).resolve().parent.parent / DEFAULT_SOURCE_LABEL
ITEM_TYPE = "continuity_pending_promotion"
INGEST_ACTOR = "ace.pending_promotions_ingest"
REQUIRED_FIELDS = ("id", "title", "source", "reason", "created_at", "status")


class PendingPromotionIngestError(ValueError):
    """Raised when continuity pending-promotions ingest cannot proceed."""


class PendingPromotionParseError(PendingPromotionIngestError):
    """Raised when the source file cannot be parsed as JSON."""


class PendingPromotionSchemaError(PendingPromotionIngestError):
    """Raised when the source shape does not match the narrow contract."""


def ingest_continuity_pending_promotions(
    db_path: Path | str = DB_PATH,
    source_path: Path | str = DEFAULT_SOURCE_PATH,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
) -> list[Item]:
    """Read continuity/pending-promotions.json and mirror pending items into ACE TRIAGE.

    The proof is intentionally narrow: only `status == "pending"` items are eligible,
    provenance is preserved via `source` + deterministic `source_session`, and replay
    reuses the existing ACE item plus its evidence row instead of duplicating either.
    """
    repo = ItemRepository(db_path)
    source_path = Path(source_path)
    payload = _load_payload(source_path)

    ingested: list[Item] = []
    for raw_item in payload["items"]:
        if not isinstance(raw_item, Mapping):
            raise PendingPromotionSchemaError("each pending-promotion item must be a JSON object")

        status = _normalize_required_text(raw_item.get("status"), field_name="status").lower()
        if status != "pending":
            continue

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

        canonical_json = _canonical_json(normalized_item)
        item = repo.create_item(
            item_type=ITEM_TYPE,
            title=normalized_item["title"],
            description=normalized_item["reason"],
            state="TRIAGE",
            source=source_label,
            source_session=source_session,
            actor=INGEST_ACTOR,
        )
        repo.add_evidence(
            item.id,
            evidence_text=canonical_json,
            evidence_uri=source_label,
            created_by=INGEST_ACTOR,
            actor=INGEST_ACTOR,
        )
        ingested.append(item)

    return ingested


def _load_payload(source_path: Path) -> dict[str, Any]:
    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PendingPromotionParseError(f"unable to read pending-promotion source: {source_path}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PendingPromotionParseError(f"malformed pending-promotion JSON: {source_path}") from exc

    if not isinstance(payload, dict):
        raise PendingPromotionSchemaError("pending-promotion payload must be a JSON object")

    items = payload.get("items")
    if not isinstance(items, list):
        raise PendingPromotionSchemaError("pending-promotion payload must contain an items array")

    return payload


def _normalize_source_item(raw_item: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field_name in REQUIRED_FIELDS:
        normalized[field_name] = _normalize_required_text(raw_item.get(field_name), field_name=field_name)

    if normalized["status"].lower() != "pending":
        raise PendingPromotionSchemaError("only pending pending-promotion items are eligible")

    normalized["status"] = "pending"
    return normalized


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise PendingPromotionSchemaError(f"{field_name} is required")
    if isinstance(value, str):
        normalized = value.strip()
    else:
        normalized = str(value).strip()
    if not normalized:
        raise PendingPromotionSchemaError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _canonical_json(source_item: Mapping[str, str]) -> str:
    return json.dumps(
        {
            "id": source_item["id"],
            "title": source_item["title"],
            "source": source_item["source"],
            "reason": source_item["reason"],
            "created_at": source_item["created_at"],
            "status": source_item["status"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_digest(source_item: Mapping[str, str]) -> str:
    return hashlib.sha256(_canonical_json(source_item).encode("utf-8")).hexdigest()


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
