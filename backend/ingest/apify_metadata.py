"""Apify webhook metadata extraction helpers."""

from __future__ import annotations

from typing import Any

from backend.ingest.time_utils import parse_datetime_utc


def _first_present(*candidates: Any) -> Any:
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def extract_apify_webhook_metadata(payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    resource = payload.get("resource", {}) if isinstance(payload.get("resource", {}), dict) else {}
    event_data = payload.get("eventData", {}) if isinstance(payload.get("eventData", {}), dict) else {}
    nested_resource = event_data.get("resource", {}) if isinstance(event_data.get("resource", {}), dict) else {}

    item_count = _first_present(
        payload.get("item_count"),
        payload.get("itemCount"),
        event_data.get("itemCount"),
        resource.get("item_count"),
        resource.get("itemCount"),
        nested_resource.get("itemCount"),
    )

    if item_count is None and isinstance(payload.get("items"), list):
        item_count = len(payload["items"])

    try:
        item_count = int(item_count) if item_count is not None else None
    except (TypeError, ValueError):
        item_count = None

    actor_id = _first_present(
        resource.get("actId"),
        resource.get("actorId"),
        nested_resource.get("actId"),
        nested_resource.get("actorId"),
        event_data.get("actorId"),
        payload.get("actId"),
        payload.get("actorId"),
        payload.get("actor_id"),
    )
    run_id = _first_present(
        resource.get("id"),
        nested_resource.get("id"),
        event_data.get("actorRunId"),
        event_data.get("runId"),
        payload.get("actorRunId"),
        payload.get("runId"),
        payload.get("id"),
        payload.get("run_id"),
    )
    dataset_id = _first_present(
        resource.get("defaultDatasetId"),
        nested_resource.get("defaultDatasetId"),
        event_data.get("defaultDatasetId"),
        payload.get("defaultDatasetId"),
        payload.get("defaultDatasetID"),
        payload.get("datasetId"),
        payload.get("defaultDataset"),
    )
    created_at = _first_present(
        payload.get("createdAt"),
        payload.get("timestamp"),
        event_data.get("createdAt"),
        resource.get("createdAt"),
        resource.get("startedAt"),
        nested_resource.get("createdAt"),
        nested_resource.get("startedAt"),
    )

    return {
        "source": payload.get("source") or "apify",
        "actor_id": actor_id,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "item_count": item_count,
        "created_at": parse_datetime_utc(created_at),
    }
