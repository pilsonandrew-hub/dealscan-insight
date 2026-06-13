#!/usr/bin/env python3
"""Read-only Supabase live evidence probe for DealerScope.

Prints aggregate counts and timestamp/status summaries only. It intentionally
avoids row payloads, customer/user fields, tokens, and listing details.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TABLES = {
    "webhook_log": {
        "timestamp_candidates": ["created_at", "received_at", "updated_at", "completed_at"],
        "status_candidates": ["status", "processing_status", "db_save"],
    },
    "opportunities": {
        "timestamp_candidates": ["created_at", "updated_at", "processed_at", "auction_end", "auction_end_time"],
        "status_candidates": ["status", "db_save", "source_site"],
    },
    "alert_log": {
        "timestamp_candidates": ["created_at", "sent_at", "timestamp", "delivered_at"],
        "status_candidates": ["status", "channel", "delivery_status"],
    },
    "ingest_delivery_log": {
        "timestamp_candidates": ["created_at", "updated_at", "delivered_at"],
        "status_candidates": ["status", "channel", "delivery_status"],
    },
    "scrape_runs": {
        "timestamp_candidates": ["started_at", "completed_at", "created_at", "updated_at"],
        "status_candidates": ["status", "source_name"],
    },
    "parse_events": {
        "timestamp_candidates": ["created_at"],
        "status_candidates": ["status", "event_type", "source_name"],
    },
    "source_health_daily": {
        "timestamp_candidates": ["observed_date", "latest_started_at", "latest_completed_at"],
        "status_candidates": ["source_name"],
    },
    "post_close_outcome_requests": {
        "timestamp_candidates": ["created_at", "updated_at", "last_checked_at", "next_check_at"],
        "status_candidates": ["outcome_status", "referral_source", "source_site"],
    },
}

HIGH_RUST_STATES = {
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA",
    "ND", "SD", "NE", "KS", "WV", "ME", "NH", "VT", "MA", "RI",
    "CT", "NJ", "MD", "DE",
}

DEPLOYMENT_PATH = Path(__file__).resolve().parent.parent / "apify" / "deployment.json"
GENERIC_DELIVERY_SOURCES = {"apify", "webhook", "actor", "unknown"}


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required env: {name}")
    return value.rstrip("/")


def _request(base_url: str, service_key: str, table: str, params: dict[str, str], *, count: bool = False) -> tuple[int, dict[str, str], Any]:
    url = f"{base_url}/rest/v1/{table}?{urlencode(params)}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    if count:
        headers["Prefer"] = "count=exact"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, dict(resp.headers.items()), json.loads(body or "[]")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{table} HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"{table} request failed: {exc}") from exc


def _count(base_url: str, service_key: str, table: str) -> int | None:
    status, headers, _ = _request(
        base_url,
        service_key,
        table,
        {"select": "*", "limit": "1"},
        count=True,
    )
    if status >= 400:
        return None
    crange = headers.get("Content-Range") or headers.get("content-range")
    if crange and "/" in crange:
        total = crange.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    return None


def _opportunity_lifecycle_schema_truth(base_url: str, service_key: str) -> dict[str, Any]:
    columns = [
        "first_seen_at",
        "last_seen_at",
        "relist_count",
        "bid_change_count",
        "source_fingerprint",
    ]
    _, _, rows = _request(
        base_url,
        service_key,
        "opportunities",
        {
            "select": "id," + ",".join(columns),
            "order": "last_seen_at.desc",
            "limit": "25",
        },
    )
    sample_rows = rows if isinstance(rows, list) else []
    non_null_counts = {
        column: sum(1 for row in sample_rows if row.get(column) is not None)
        for column in columns
    }
    return {
        "columns_queryable": True,
        "sample_count": len(sample_rows),
        "non_null_counts": non_null_counts,
    }


def _latest_timestamp(base_url: str, service_key: str, table: str, candidates: list[str]) -> dict[str, Any] | None:
    for column in candidates:
        try:
            _, _, rows = _request(
                base_url,
                service_key,
                table,
                {"select": column, "order": f"{column}.desc", "limit": "1", column: "not.is.null"},
            )
        except RuntimeError:
            continue
        if isinstance(rows, list) and rows and rows[0].get(column):
            return {"column": column, "latest": rows[0][column]}
    return None


def _status_sample(base_url: str, service_key: str, table: str, candidates: list[str]) -> dict[str, Any] | None:
    for column in candidates:
        try:
            _, _, rows = _request(
                base_url,
                service_key,
                table,
                {"select": column, "limit": "200", column: "not.is.null"},
            )
        except RuntimeError:
            continue
        if not isinstance(rows, list):
            continue
        counts: dict[str, int] = {}
        for row in rows:
            value = row.get(column)
            if value is None:
                continue
            key = str(value)[:80]
            counts[key] = counts.get(key, 0) + 1
        if counts:
            return {"column": column, "sample_size": len(rows), "counts": dict(sorted(counts.items())[:20])}
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _has_column(rows: list[dict[str, Any]], column: str) -> bool:
    return any(column in row for row in rows)


def _photo_count(row: dict[str, Any]) -> int | None:
    if "photo_count" not in row:
        return None
    parsed = _coerce_int(row.get("photo_count"))
    if parsed is None:
        return None
    return max(parsed, 0)


def _raw_photo_evidence_count(row: dict[str, Any]) -> int:
    raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
    for key in ("photos", "photo_urls"):
        value = raw.get(key)
        if isinstance(value, list):
            count = len([item for item in value if item])
            if count:
                return count
        if isinstance(value, tuple):
            count = len([item for item in value if item])
            if count:
                return count
        if isinstance(value, str) and value.strip():
            return 1
    for key in ("photo_url", "image_url", "imageUrl"):
        if raw.get(key):
            return 1
    return 0


def _recent_rows(base_url: str, service_key: str, table: str, select: str, order_column: str, limit: int) -> list[dict[str, Any]]:
    _, _, rows = _request(
        base_url,
        service_key,
        table,
        {"select": select, "order": f"{order_column}.desc", "limit": str(limit)},
    )
    return rows if isinstance(rows, list) else []


def _available_columns(base_url: str, service_key: str, table: str) -> set[str]:
    _, _, rows = _request(base_url, service_key, table, {"select": "*", "limit": "1"})
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return set(rows[0].keys())
    return set()


def _summarize_recent_opportunity_truth(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    scored = 0
    hot = 0
    good_plus = 0
    missing_score = 0
    missing_pricing = 0
    missing_url = 0
    ceiling_violations = 0
    margin_violations = 0
    rust_rule_violations = 0
    dos_values: list[float] = []
    sample_count = len(rows)

    current_year = datetime.now(timezone.utc).year
    for row in rows:
        source = str(row.get("source_site") or row.get("source") or "unknown")[:80]
        state = str(row.get("state") or "unknown").upper()[:20]
        source_counts[source] += 1
        state_counts[state] += 1

        score = _coerce_float(row.get("dos_score") if row.get("dos_score") is not None else row.get("score"))
        current_bid = _coerce_float(row.get("current_bid") if row.get("current_bid") is not None else row.get("price"))
        max_bid = _coerce_float(row.get("max_bid"))
        margin = _coerce_float(row.get("gross_margin") if row.get("gross_margin") is not None else row.get("potential_profit"))
        year = _coerce_int(row.get("year"))
        listing_url = row.get("listing_url") or row.get("url")

        if score is None:
            missing_score += 1
        else:
            scored += 1
            dos_values.append(score)
            if score >= 80:
                hot += 1
            if score >= 65:
                good_plus += 1

        if current_bid is None and max_bid is None and margin is None:
            missing_pricing += 1
        if not listing_url:
            missing_url += 1
        if current_bid is not None and max_bid is not None and max_bid > 0 and current_bid > max_bid:
            ceiling_violations += 1
        if score is not None and score >= 50 and margin is not None and margin < 1500:
            margin_violations += 1
        if state in HIGH_RUST_STATES and (year is None or year < current_year - 2):
            rust_rule_violations += 1

    return {
        "sample_count": sample_count,
        "source_counts": dict(source_counts.most_common(20)),
        "state_counts": dict(state_counts.most_common(20)),
        "scored_rows": scored,
        "missing_score_rows": missing_score,
        "hot_score_rows_80_plus": hot,
        "good_plus_rows_65_plus": good_plus,
        "dos_min": min(dos_values) if dos_values else None,
        "dos_max": max(dos_values) if dos_values else None,
        "dos_avg": round(sum(dos_values) / len(dos_values), 2) if dos_values else None,
        "missing_pricing_rows": missing_pricing,
        "missing_listing_url_rows": missing_url,
        "bid_ceiling_violations_in_sample": ceiling_violations,
        "margin_floor_violations_in_sample": margin_violations,
        "rust_rule_violations_in_sample": rust_rule_violations,
    }


def _summarize_run_delivery_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    listing_ids: set[str] = set()
    latest_created_at = None
    latest_updated_at = None
    for row in rows:
        status = str(row.get("status") or "unknown")[:80]
        channel = str(row.get("channel") or "unknown")[:80]
        status_counts[status] += 1
        channel_counts[channel] += 1
        error = str(row.get("error_message") or "")[:160]
        if error:
            reason_counts[error] += 1
        listing_id = row.get("listing_id")
        if listing_id:
            listing_ids.add(str(listing_id))
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
    return {
        "row_count": len(rows),
        "distinct_listing_ids": len(listing_ids),
        "status_counts": dict(status_counts.most_common(20)),
        "channel_counts": dict(channel_counts.most_common(20)),
        "sanitized_error_counts": dict(reason_counts.most_common(20)),
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
    }


def _canonical_delivery_source(value: Any) -> str | None:
    if value is None:
        return None
    source = str(value).strip().lower()
    if not source:
        return None
    if source.startswith("ds-"):
        source = source[3:]
    if source.endswith("-v2"):
        source = source[:-3]
    return source[:80]


def _actor_source_by_id(path: Path = DEPLOYMENT_PATH) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    actors = payload.get("actors") if isinstance(payload, dict) else {}
    if not isinstance(actors, dict):
        return {}
    source_by_id: dict[str, str] = {}
    for actor_name, details in actors.items():
        if not isinstance(details, dict):
            continue
        actor_id = str(details.get("id") or "").strip()
        source = _canonical_delivery_source(actor_name)
        if actor_id and source:
            source_by_id[actor_id] = source
    return source_by_id


def _source_by_run_from_webhooks(rows: list[dict[str, Any]]) -> dict[str, str]:
    source_by_run: dict[str, str] = {}
    source_by_actor_id = _actor_source_by_id()
    for row in rows:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id or run_id in source_by_run:
            continue
        actor_id = str(row.get("actor_id") or "").strip()
        explicit_source = _canonical_delivery_source(row.get("source") or row.get("source_site") or row.get("actor_name"))
        actor_source = source_by_actor_id.get(actor_id)
        source = actor_source if explicit_source in GENERIC_DELIVERY_SOURCES else (explicit_source or actor_source)
        if source:
            source_by_run[run_id] = source
    return source_by_run


def _summarize_recent_delivery_truth(
    rows: list[dict[str, Any]],
    source_by_run: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    source_status_counts: Counter[tuple[str, str]] = Counter()
    reason_counts: Counter[str] = Counter()
    latest_created_at = None
    source_by_run = source_by_run or {}
    for row in rows:
        run_id = str(row.get("run_id") or "").strip()
        source = (
            _canonical_delivery_source(row.get("source_site") or row.get("source"))
            or source_by_run.get(run_id)
            or "unknown"
        )[:80]
        channel = str(row.get("channel") or "unknown")[:80]
        status = str(row.get("status") or "unknown")[:80]
        source_counts[source] += 1
        channel_counts[channel] += 1
        status_counts[status] += 1
        source_status_counts[(source, status)] += 1
        error = str(row.get("error_message") or "")[:160]
        if error:
            reason_counts[error] += 1
        created_at = row.get("created_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at

    return {
        "sample_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "channel_counts": dict(channel_counts.most_common(20)),
        "status_counts": dict(status_counts.most_common(20)),
        "source_status_counts": [
            {"source": source, "status": status, "count": count}
            for (source, status), count in source_status_counts.most_common(30)
        ],
        "sanitized_error_counts": dict(reason_counts.most_common(20)),
        "latest_created_at": latest_created_at,
    }


def _summarize_run_webhook_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    item_counts: Counter[str] = Counter()
    latest_received_at = None
    for row in rows:
        status = str(row.get("processing_status") or row.get("status") or "unknown")[:80]
        status_counts[status] += 1
        error = str(row.get("error_message") or "")[:160]
        if error:
            error_counts[error] += 1
        if row.get("item_count") is not None:
            item_counts[str(row.get("item_count"))] += 1
        received_at = row.get("received_at") or row.get("created_at")
        if received_at and (latest_received_at is None or str(received_at) > str(latest_received_at)):
            latest_received_at = received_at
    return {
        "row_count": len(rows),
        "status_counts": dict(status_counts.most_common(20)),
        "sanitized_error_counts": dict(error_counts.most_common(20)),
        "item_count_values": dict(item_counts.most_common(20)),
        "latest_received_at": latest_received_at,
    }


def _summarize_scrape_run_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    latest_started_at = None
    latest_completed_at = None
    totals = {
        "item_count": 0,
        "evaluated_count": 0,
        "saved_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "parse_event_count": 0,
    }
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        status_counts[str(row.get("status") or "unknown")[:80]] += 1
        for column in totals:
            totals[column] += _coerce_int(row.get(column)) or 0
        started_at = row.get("started_at")
        completed_at = row.get("completed_at")
        if started_at and (latest_started_at is None or str(started_at) > str(latest_started_at)):
            latest_started_at = started_at
        if completed_at and (latest_completed_at is None or str(completed_at) > str(latest_completed_at)):
            latest_completed_at = completed_at
    return {
        "row_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "status_counts": dict(status_counts.most_common(20)),
        "total_item_count": totals["item_count"],
        "total_evaluated_count": totals["evaluated_count"],
        "total_saved_count": totals["saved_count"],
        "total_skipped_count": totals["skipped_count"],
        "total_failed_count": totals["failed_count"],
        "total_parse_event_count": totals["parse_event_count"],
        "latest_started_at": latest_started_at,
        "latest_completed_at": latest_completed_at,
    }


def _summarize_parse_event_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    event_type_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    latest_created_at = None
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        event_type_counts[str(row.get("event_type") or "unknown")[:80]] += 1
        status_counts[str(row.get("status") or "unknown")[:80]] += 1
        reason = row.get("reason")
        if reason:
            reason_counts[str(reason)[:160]] += 1
        created_at = row.get("created_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
    return {
        "row_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "event_type_counts": dict(event_type_counts.most_common(20)),
        "status_counts": dict(status_counts.most_common(20)),
        "reason_counts": dict(reason_counts.most_common(20)),
        "latest_created_at": latest_created_at,
    }


def _summarize_run_opportunity_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    step_counts: Counter[str] = Counter()
    vin_present = 0
    mileage_present = 0
    photo_counts: list[int] = []
    raw_photo_evidence_rows = 0
    suppressed_raw_photo_evidence_rows = 0
    for row in rows:
        source_counts[str(row.get("source_site") or row.get("source") or "unknown")[:80]] += 1
        step_counts[str(row.get("step_status") or row.get("status") or "unknown")[:80]] += 1
        raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        if row.get("vin") or raw.get("vin"):
            vin_present += 1
        if _coerce_float(row.get("mileage") if row.get("mileage") is not None else raw.get("mileage")) is not None:
            mileage_present += 1
        photo_count = _photo_count(row)
        if photo_count is not None:
            photo_counts.append(photo_count)
        raw_photo_count = _raw_photo_evidence_count(row)
        if raw_photo_count > 0:
            raw_photo_evidence_rows += 1
            if (photo_count or 0) <= 0:
                suppressed_raw_photo_evidence_rows += 1
    return {
        "row_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "step_status_counts": dict(step_counts.most_common(20)),
        "vin_present_rows": vin_present,
        "mileage_present_rows": mileage_present,
        "raw_photo_evidence_rows": raw_photo_evidence_rows,
        "suppressed_raw_photo_evidence_rows": suppressed_raw_photo_evidence_rows,
        "photo_count_known_rows": len(photo_counts),
        "zero_photo_count_rows": sum(1 for count in photo_counts if count == 0),
        "positive_photo_count_rows": sum(1 for count in photo_counts if count > 0),
        "max_photo_count": max(photo_counts) if photo_counts else None,
        "average_photo_count": round(sum(photo_counts) / len(photo_counts), 2) if photo_counts else None,
    }


def _summarize_market_scout_run_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    records_found = 0
    records_candidate = 0
    records_rejected = 0
    error_count = 0
    latest_created_at = None
    latest_updated_at = None
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        status_counts[str(row.get("status") or "unknown")[:80]] += 1
        records_found += _coerce_int(row.get("records_found")) or 0
        records_candidate += _coerce_int(row.get("records_candidate")) or 0
        records_rejected += _coerce_int(row.get("records_rejected")) or 0
        error_count += _coerce_int(row.get("error_count")) or 0
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
    return {
        "row_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "status_counts": dict(status_counts.most_common(20)),
        "records_found_total": records_found,
        "records_candidate_total": records_candidate,
        "records_rejected_total": records_rejected,
        "error_count_total": error_count,
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
    }


def _summarize_sold_comp_candidate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    source_listing_ids: set[str] = set()
    source_listing_keys: set[str] = set()
    latest_created_at = None
    latest_updated_at = None
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        channel_counts[str(row.get("channel") or "unknown")[:80]] += 1
        status_counts[str(row.get("candidate_status") or "unknown")[:80]] += 1
        rejection_reason = row.get("rejection_reason")
        if rejection_reason:
            rejection_reason_counts[str(rejection_reason)[:120]] += 1
        source_listing_id = row.get("source_listing_id")
        if source_listing_id:
            source_listing_id_text = str(source_listing_id)
            source_name_text = str(row.get("source_name") or "unknown")
            source_listing_ids.add(source_listing_id_text)
            source_listing_keys.add(f"{source_name_text}:{source_listing_id_text}")
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
    return {
        "row_count": len(rows),
        "distinct_source_listing_ids": len(source_listing_ids),
        "distinct_source_listing_keys": len(source_listing_keys),
        "source_counts": dict(source_counts.most_common(20)),
        "channel_counts": dict(channel_counts.most_common(20)),
        "status_counts": dict(status_counts.most_common(20)),
        "rejection_reason_counts": dict(rejection_reason_counts.most_common(20)),
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
    }


def _summarize_sold_comp_review_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    review_status_counts: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    latest_created_at = None
    latest_updated_at = None
    for row in rows:
        review_status_counts[str(row.get("review_status") or "unknown")[:80]] += 1
        reviewer_counts[str(row.get("reviewer") or "unknown")[:80]] += 1
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
    return {
        "row_count": len(rows),
        "review_status_counts": dict(review_status_counts.most_common(20)),
        "reviewer_counts": dict(reviewer_counts.most_common(20)),
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
    }


def _summarize_verified_sold_comp_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    latest_created_at = None
    latest_updated_at = None
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        channel_counts[str(row.get("channel") or "unknown")[:80]] += 1
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
    return {
        "row_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "channel_counts": dict(channel_counts.most_common(20)),
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
    }


def _summarize_post_close_outcome_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    outcome_status_counts: Counter[str] = Counter()
    referral_source_counts: Counter[str] = Counter()
    referral_reason_counts: Counter[str] = Counter()
    check_attempts_total = 0
    latest_created_at = None
    latest_updated_at = None
    next_check_at = None
    for row in rows:
        source_counts[str(row.get("source_site") or "unknown")[:80]] += 1
        outcome_status_counts[str(row.get("outcome_status") or "unknown")[:80]] += 1
        referral_source_counts[str(row.get("referral_source") or "unknown")[:80]] += 1
        referral_reason = row.get("referral_reason")
        if referral_reason:
            referral_reason_counts[str(referral_reason)[:120]] += 1
        check_attempts_total += _coerce_int(row.get("check_attempts")) or 0
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        row_next_check_at = row.get("next_check_at")
        if created_at and (latest_created_at is None or str(created_at) > str(latest_created_at)):
            latest_created_at = created_at
        if updated_at and (latest_updated_at is None or str(updated_at) > str(latest_updated_at)):
            latest_updated_at = updated_at
        if row_next_check_at and (next_check_at is None or str(row_next_check_at) < str(next_check_at)):
            next_check_at = row_next_check_at
    return {
        "sample_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "outcome_status_counts": dict(outcome_status_counts.most_common(20)),
        "referral_source_counts": dict(referral_source_counts.most_common(20)),
        "referral_reason_counts": dict(referral_reason_counts.most_common(20)),
        "check_attempts_total": check_attempts_total,
        "latest_created_at": latest_created_at,
        "latest_updated_at": latest_updated_at,
        "next_check_at": next_check_at,
    }


def _summarize_source_health_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    latest_observed_date = None
    latest_started_at = None
    totals = {
        "total_runs": 0,
        "processed_runs": 0,
        "failed_runs": 0,
        "item_count": 0,
        "saved_count": 0,
        "skipped_count": 0,
        "parse_event_count": 0,
    }
    for row in rows:
        source_counts[str(row.get("source_name") or "unknown")[:80]] += 1
        for column in totals:
            totals[column] += _coerce_int(row.get(column)) or 0
        observed_date = row.get("observed_date")
        started_at = row.get("latest_started_at")
        if observed_date and (latest_observed_date is None or str(observed_date) > str(latest_observed_date)):
            latest_observed_date = observed_date
        if started_at and (latest_started_at is None or str(started_at) > str(latest_started_at)):
            latest_started_at = started_at
    return {
        "sample_count": len(rows),
        "source_counts": dict(source_counts.most_common(20)),
        "latest_observed_date": latest_observed_date,
        "latest_started_at": latest_started_at,
        **totals,
    }


def _seller_recovery_candidate_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not row.get("vin"):
        reasons.append("missing_vin")
    if row.get("mileage") in (None, "", 0):
        reasons.append("missing_mileage")
    if not (row.get("auction_end_date") or row.get("auction_end") or row.get("auction_end_time")):
        reasons.append("missing_auction_end")
    if str(row.get("condition_grade") or "").strip().lower() in {"", "unknown", "poor"}:
        reasons.append("condition_unverified")
    if str(row.get("pricing_maturity") or "").strip().lower() == "proxy":
        reasons.append("proxy_pricing")
    risk_flags = {str(flag).strip().lower() for flag in (row.get("risk_flags") or [])}
    if "missing_photos" in risk_flags:
        reasons.append("missing_photos_flag")
    photo_count = _photo_count(row)
    if photo_count == 0:
        reasons.append("zero_photo_count")
    elif photo_count is not None and photo_count < 3:
        reasons.append("low_photo_count")
    return reasons


def _first_positive_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _coerce_float(row.get(key))
        if value is not None and value > 0:
            return value
    return None


def _summarize_listing_quality_for_seller_recovery(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_rows = [row for row in rows if row.get("is_active") is not False]
    known_photo_counts = [
        photo_count
        for row in active_rows
        if (photo_count := _photo_count(row)) is not None
    ]
    raw_photo_evidence_rows = [
        row for row in active_rows
        if _raw_photo_evidence_count(row) > 0
    ]
    return {
        "sample_count": len(active_rows),
        "missing_vin_count": sum(1 for row in active_rows if not row.get("vin")),
        "missing_mileage_count": sum(1 for row in active_rows if row.get("mileage") in (None, "", 0)),
        "missing_auction_end_count": sum(1 for row in active_rows if not (row.get("auction_end_date") or row.get("auction_end") or row.get("auction_end_time"))),
        "condition_unverified_count": sum(1 for row in active_rows if str(row.get("condition_grade") or "").strip().lower() in {"", "unknown", "poor"}),
        "proxy_pricing_count": sum(1 for row in active_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy"),
        "missing_photos_flag_count": sum(1 for row in active_rows if "missing_photos" in {str(flag).strip().lower() for flag in (row.get("risk_flags") or [])}),
        "photo_count_known_count": len(known_photo_counts),
        "zero_photo_count": sum(1 for count in known_photo_counts if count == 0),
        "low_photo_count_count": sum(1 for count in known_photo_counts if count < 3),
        "average_photo_count": round(sum(known_photo_counts) / len(known_photo_counts), 2) if known_photo_counts else None,
        "raw_photo_evidence_count": len(raw_photo_evidence_rows),
        "suppressed_raw_photo_evidence_count": sum(
            1 for row in raw_photo_evidence_rows
            if (_photo_count(row) or 0) <= 0
        ),
    }


def _seller_recovery_candidates_from_opportunities(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        gross_margin = _first_positive_number(row, "gross_margin", "potential_profit", "margin")
        bid_headroom = _first_positive_number(row, "bid_headroom")
        if gross_margin is None and bid_headroom is None:
            continue
        reasons = _seller_recovery_candidate_reasons(row)
        if not reasons:
            continue
        score = _coerce_float(row.get("dos_score") if row.get("dos_score") is not None else row.get("score"))
        candidates.append({
            "source_site": str(row.get("source_site") or row.get("source") or "unknown")[:80],
            "year": _coerce_int(row.get("year")),
            "make": str(row.get("make") or "")[:80],
            "model": str(row.get("model") or "")[:80],
            "dos_score": round(score, 2) if score is not None else None,
            "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
            "bid_headroom": round(bid_headroom, 2) if bid_headroom is not None else None,
            "pricing_maturity": str(row.get("pricing_maturity") or "unknown")[:80],
            "recovery_reasons": reasons,
        })
    candidates.sort(
        key=lambda item: (
            float(item["gross_margin"] or 0),
            float(item["bid_headroom"] or 0),
            float(item["dos_score"] or 0),
        ),
        reverse=True,
    )
    return candidates[:limit]


def _summarize_seller_recovery_audit(
    *,
    opportunity_rows: list[dict[str, Any]],
    source_health_rows: list[dict[str, Any]],
    delivery_rows: list[dict[str, Any]],
    parse_event_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = _seller_recovery_candidates_from_opportunities(opportunity_rows)
    source_names = {row.get("source_name") for row in source_health_rows if row.get("source_name")}
    unsupported_dimensions = {
        "bidder_depth": {
            "status": "unavailable",
            "reason": "No governed bidder-count field is currently written across active source rows.",
        },
        "photo_count": {
            "status": "available" if _has_column(opportunity_rows, "photo_count") else "unavailable",
            "reason": (
                "Governed opportunity photo_count field is queryable on sampled rows."
                if _has_column(opportunity_rows, "photo_count")
                else "Current normalized opportunity rows only prove missing_photos as a risk flag, not a reliable photo count."
            ),
        },
    }
    return {
        "status": "ok",
        "summary": {
            "source_count": len(source_names),
            "candidate_count": len(candidates),
            "unavailable_dimensions": [
                name for name, details in unsupported_dimensions.items()
                if details.get("status") == "unavailable"
            ],
        },
        "listing_quality": _summarize_listing_quality_for_seller_recovery(opportunity_rows),
        "delivery_status_counts": _summarize_recent_delivery_truth(delivery_rows).get("status_counts", {}),
        "parse_event_status_counts": _summarize_parse_event_rows(parse_event_rows).get("status_counts", {}),
        "parse_event_type_counts": _summarize_parse_event_rows(parse_event_rows).get("event_type_counts", {}),
        "value_leak_candidates": candidates,
        "unsupported_dimensions": unsupported_dimensions,
        "truth_boundary": "Sanitized aggregate seller recovery proof. Does not print VINs, listing URLs, descriptions, raw payloads, user data, or tokens.",
    }


def _run_id_truth_audit(base_url: str, service_key: str, run_id: str) -> dict[str, Any]:
    delivery_columns = _available_columns(base_url, service_key, "ingest_delivery_log")
    delivery_select = ",".join([
        col for col in ["run_id", "listing_id", "channel", "status", "error_message", "created_at", "updated_at"]
        if col in delivery_columns
    ]) or "run_id,status"
    _, _, delivery_rows = _request(
        base_url,
        service_key,
        "ingest_delivery_log",
        {"select": delivery_select, "run_id": f"eq.{run_id}", "order": "created_at.asc", "limit": "200"},
    )

    webhook_columns = _available_columns(base_url, service_key, "webhook_log")
    webhook_select = ",".join([
        col for col in ["run_id", "received_at", "created_at", "processing_status", "status", "error_message", "item_count", "actor_id"]
        if col in webhook_columns
    ]) or "run_id"
    _, _, webhook_rows = _request(
        base_url,
        service_key,
        "webhook_log",
        {"select": webhook_select, "run_id": f"eq.{run_id}", "order": "received_at.asc", "limit": "50"},
    )

    scrape_run_report: dict[str, Any]
    try:
        scrape_columns = _available_columns(base_url, service_key, "scrape_runs")
        scrape_select = ",".join([
            col for col in [
                "run_id",
                "source_name",
                "status",
                "item_count",
                "evaluated_count",
                "saved_count",
                "skipped_count",
                "failed_count",
                "parse_event_count",
                "started_at",
                "completed_at",
            ]
            if col in scrape_columns
        ]) or "run_id"
        _, _, rows = _request(
            base_url,
            service_key,
            "scrape_runs",
            {"select": scrape_select, "run_id": f"eq.{run_id}", "order": "started_at.asc", "limit": "50"},
        )
        scrape_run_report = _summarize_scrape_run_rows(rows if isinstance(rows, list) else [])
    except Exception as exc:
        scrape_run_report = {"row_count": None, "failure": str(exc)[:500]}

    parse_event_report: dict[str, Any]
    try:
        parse_columns = _available_columns(base_url, service_key, "parse_events")
        parse_select = ",".join([
            col for col in ["run_id", "source_name", "event_type", "status", "reason", "created_at"]
            if col in parse_columns
        ]) or "run_id"
        _, _, rows = _request(
            base_url,
            service_key,
            "parse_events",
            {"select": parse_select, "run_id": f"eq.{run_id}", "order": "created_at.asc", "limit": "500"},
        )
        parse_event_report = _summarize_parse_event_rows(rows if isinstance(rows, list) else [])
    except Exception as exc:
        parse_event_report = {"row_count": None, "failure": str(exc)[:500]}

    opportunity_columns = _available_columns(base_url, service_key, "opportunities")
    opportunity_select = ",".join([
        col for col in [
            "id",
            "listing_id",
            "run_id",
            "source_run_id",
            "source_site",
            "source",
            "step_status",
            "status",
            "vin",
            "mileage",
            "photo_count",
            "created_at",
            "processed_at",
            "raw_data",
        ]
        if col in opportunity_columns
    ]) or "id"
    opportunity_filters = []
    if "run_id" in opportunity_columns:
        opportunity_filters.append({"select": opportunity_select, "run_id": f"eq.{run_id}", "limit": "200"})
    if "source_run_id" in opportunity_columns:
        opportunity_filters.append({"select": opportunity_select, "source_run_id": f"eq.{run_id}", "limit": "200"})
    delivery_listing_ids = sorted({
        str(row.get("listing_id"))
        for row in delivery_rows if isinstance(row, dict) and row.get("listing_id")
    })
    if "listing_id" in opportunity_columns and delivery_listing_ids:
        for start in range(0, len(delivery_listing_ids), 100):
            listing_id_chunk = delivery_listing_ids[start:start + 100]
            opportunity_filters.append({
                "select": opportunity_select,
                "listing_id": f"in.({','.join(listing_id_chunk)})",
                "limit": "200",
            })
    opportunity_by_id: dict[str, dict[str, Any]] = {}
    for params in opportunity_filters:
        _, _, rows = _request(base_url, service_key, "opportunities", params)
        for row in rows if isinstance(rows, list) else []:
            opportunity_by_id[str(row.get("id") or json.dumps(row, sort_keys=True))] = row

    market_scout_report: dict[str, Any]
    try:
        market_scout_columns = _available_columns(base_url, service_key, "market_scout_runs")
        market_scout_select = ",".join([
            col for col in [
                "id",
                "run_id",
                "source_name",
                "status",
                "records_found",
                "records_candidate",
                "records_rejected",
                "error_count",
                "created_at",
                "updated_at",
            ]
            if col in market_scout_columns
        ]) or "run_id"
        _, _, rows = _request(
            base_url,
            service_key,
            "market_scout_runs",
            {"select": market_scout_select, "run_id": f"eq.{run_id}", "limit": "50"},
        )
        market_scout_report = _summarize_market_scout_run_rows(rows if isinstance(rows, list) else [])
    except Exception as exc:
        market_scout_report = {"row_count": None, "failure": str(exc)[:500]}

    sold_comp_candidate_report: dict[str, Any]
    try:
        candidate_columns = _available_columns(base_url, service_key, "sold_comp_candidates")
        candidate_select = ",".join([
            col for col in [
                "id",
                "run_id",
                "source_name",
                "source_listing_id",
                "channel",
                "candidate_status",
                "rejection_reason",
                "created_at",
                "updated_at",
            ]
            if col in candidate_columns
        ]) or "run_id"
        _, _, rows = _request(
            base_url,
            service_key,
            "sold_comp_candidates",
            {"select": candidate_select, "run_id": f"eq.{run_id}", "order": "created_at.asc", "limit": "200"},
        )
        sold_comp_candidate_report = _summarize_sold_comp_candidate_rows(rows if isinstance(rows, list) else [])
        candidate_ids = [
            str(row["id"])
            for row in rows if isinstance(rows, list)
            if row.get("id")
        ]
    except Exception as exc:
        sold_comp_candidate_report = {"row_count": None, "failure": str(exc)[:500]}
        candidate_ids = []

    sold_comp_review_report: dict[str, Any]
    try:
        if candidate_ids:
            review_columns = _available_columns(base_url, service_key, "sold_comp_reviews")
            review_select = ",".join([
                col for col in ["candidate_id", "review_status", "reviewer", "reviewer_version", "created_at", "updated_at"]
                if col in review_columns
            ]) or "candidate_id"
            _, _, rows = _request(
                base_url,
                service_key,
                "sold_comp_reviews",
                {"select": review_select, "candidate_id": f"in.({','.join(candidate_ids)})", "limit": "200"},
            )
            sold_comp_review_report = _summarize_sold_comp_review_rows(rows if isinstance(rows, list) else [])
        else:
            sold_comp_review_report = _summarize_sold_comp_review_rows([])
    except Exception as exc:
        sold_comp_review_report = {"row_count": None, "failure": str(exc)[:500]}

    verified_sold_comp_report: dict[str, Any]
    try:
        if candidate_ids:
            verified_columns = _available_columns(base_url, service_key, "verified_sold_comps")
            verified_select = ",".join([
                col for col in ["candidate_id", "source_name", "channel", "created_at", "updated_at"]
                if col in verified_columns
            ]) or "candidate_id"
            _, _, rows = _request(
                base_url,
                service_key,
                "verified_sold_comps",
                {"select": verified_select, "candidate_id": f"in.({','.join(candidate_ids)})", "limit": "200"},
            )
            verified_sold_comp_report = _summarize_verified_sold_comp_rows(rows if isinstance(rows, list) else [])
        else:
            verified_sold_comp_report = _summarize_verified_sold_comp_rows([])
    except Exception as exc:
        verified_sold_comp_report = {"row_count": None, "failure": str(exc)[:500]}

    return {
        "run_id": run_id,
        "scrape_runs": scrape_run_report,
        "parse_events": parse_event_report,
        "delivery_log": _summarize_run_delivery_rows(delivery_rows if isinstance(delivery_rows, list) else []),
        "webhook_log": _summarize_run_webhook_rows(webhook_rows if isinstance(webhook_rows, list) else []),
        "opportunities": _summarize_run_opportunity_rows(list(opportunity_by_id.values())),
        "market_scout_runs": market_scout_report,
        "sold_comp_candidates": sold_comp_candidate_report,
        "sold_comp_reviews": sold_comp_review_report,
        "verified_sold_comps": verified_sold_comp_report,
        "truth_boundary": "Run-level sanitized aggregate only. Does not print titles, VIN values, listing URLs, raw payloads, user data, or secrets.",
    }


def _safe_truth_audit(base_url: str, service_key: str) -> dict[str, Any]:
    desired_opportunity_columns = [
        "created_at", "updated_at", "source_site", "source", "state", "year", "make", "model",
        "dos_score", "score", "current_bid", "estimated_sale_price", "potential_profit",
        "profit_margin", "gross_margin", "roi_percentage", "auction_end", "auction_end_date",
        "status", "is_active", "max_bid", "bid_headroom", "pricing_maturity", "vin", "mileage",
        "condition_grade", "risk_flags", "listing_url", "url",
        "photo_count", "raw_data",
    ]
    opportunity_columns = _available_columns(base_url, service_key, "opportunities")
    opportunity_select = ",".join([col for col in desired_opportunity_columns if col in opportunity_columns]) or "created_at"
    recent_opportunities = _recent_rows(base_url, service_key, "opportunities", opportunity_select, "created_at", 200)

    alert_columns = _available_columns(base_url, service_key, "alert_log")
    alert_order = "created_at" if "created_at" in alert_columns else "sent_at"
    alert_select = ",".join([col for col in ["created_at", "sent_at", "status", "delivery_status", "channel"] if col in alert_columns]) or alert_order
    alert_rows = _recent_rows(
        base_url,
        service_key,
        "alert_log",
        alert_select,
        alert_order,
        50,
    )
    alert_status_counts: Counter[str] = Counter()
    for row in alert_rows:
        key = row.get("delivery_status") or row.get("status") or row.get("channel") or "unknown"
        alert_status_counts[str(key)[:80]] += 1

    webhook_columns = _available_columns(base_url, service_key, "webhook_log")
    webhook_order = "received_at" if "received_at" in webhook_columns else "created_at"
    webhook_select = ",".join([
        col for col in [
            "run_id",
            "source",
            "source_site",
            "actor_name",
            "actor_id",
            "received_at",
            "created_at",
            "status",
            "processing_status",
            "db_save",
        ]
        if col in webhook_columns
    ]) or webhook_order
    webhook_rows = _recent_rows(
        base_url,
        service_key,
        "webhook_log",
        webhook_select,
        webhook_order,
        100,
    )
    webhook_status_counts: Counter[str] = Counter()
    for row in webhook_rows:
        key = row.get("status") or row.get("processing_status") or row.get("db_save") or "unknown"
        webhook_status_counts[str(key)[:80]] += 1

    delivery_columns = _available_columns(base_url, service_key, "ingest_delivery_log")
    delivery_select = ",".join([
        col for col in [
            "run_id",
            "source_site",
            "source",
            "channel",
            "status",
            "error_message",
            "created_at",
        ]
        if col in delivery_columns
    ]) or "created_at"
    delivery_rows = _recent_rows(
        base_url,
        service_key,
        "ingest_delivery_log",
        delivery_select,
        "created_at",
        200,
    )

    post_close_report: dict[str, Any]
    try:
        post_close_columns = _available_columns(base_url, service_key, "post_close_outcome_requests")
        post_close_select = ",".join([
            col for col in [
                "source_site",
                "outcome_status",
                "referral_source",
                "referral_reason",
                "check_attempts",
                "created_at",
                "updated_at",
                "next_check_at",
            ]
            if col in post_close_columns
        ]) or "created_at"
        post_close_order = "created_at" if "created_at" in post_close_columns else post_close_select.split(",", 1)[0]
        post_close_rows = _recent_rows(
            base_url,
            service_key,
            "post_close_outcome_requests",
            post_close_select,
            post_close_order,
            200,
        )
        post_close_report = _summarize_post_close_outcome_rows(post_close_rows)
    except Exception as exc:
        post_close_report = {"failure": str(exc)[:500]}

    source_health_report: dict[str, Any]
    try:
        source_health_columns = _available_columns(base_url, service_key, "source_health_daily")
        source_health_select = ",".join([
            col for col in [
                "observed_date",
                "source_name",
                "total_runs",
                "processed_runs",
                "failed_runs",
                "item_count",
                "saved_count",
                "skipped_count",
                "parse_event_count",
                "latest_started_at",
            ]
            if col in source_health_columns
        ]) or "observed_date"
        source_health_order = "observed_date" if "observed_date" in source_health_columns else source_health_select.split(",", 1)[0]
        source_health_rows = _recent_rows(
            base_url,
            service_key,
            "source_health_daily",
            source_health_select,
            source_health_order,
            200,
        )
        source_health_report = _summarize_source_health_rows(source_health_rows)
    except Exception as exc:
        source_health_report = {"failure": str(exc)[:500]}
        source_health_rows = []

    parse_event_rows: list[dict[str, Any]] = []
    try:
        parse_columns = _available_columns(base_url, service_key, "parse_events")
        parse_select = ",".join([
            col for col in [
                "source_name",
                "event_type",
                "status",
                "reason",
                "created_at",
            ]
            if col in parse_columns
        ]) or "created_at"
        parse_event_rows = _recent_rows(
            base_url,
            service_key,
            "parse_events",
            parse_select,
            "created_at" if "created_at" in parse_columns else parse_select.split(",", 1)[0],
            500,
        )
    except Exception:
        parse_event_rows = []

    seller_recovery_audit = _summarize_seller_recovery_audit(
        opportunity_rows=recent_opportunities,
        source_health_rows=source_health_rows,
        delivery_rows=delivery_rows,
        parse_event_rows=parse_event_rows,
    )

    return {
        "recent_opportunities": _summarize_recent_opportunity_truth(recent_opportunities),
        "recent_alerts": {
            "sample_count": len(alert_rows),
            "status_counts": dict(alert_status_counts.most_common(20)),
            "latest_sent_at": next((row.get("sent_at") for row in alert_rows if row.get("sent_at")), None),
            "latest_created_at": next((row.get("created_at") for row in alert_rows if row.get("created_at")), None),
        },
        "recent_webhooks": {
            "sample_count": len(webhook_rows),
            "status_counts": dict(webhook_status_counts.most_common(20)),
            "latest_received_at": next((row.get("received_at") for row in webhook_rows if row.get("received_at")), None),
        },
        "recent_deliveries": _summarize_recent_delivery_truth(
            delivery_rows,
            _source_by_run_from_webhooks(webhook_rows),
        ),
        "post_close_outcome_requests": post_close_report,
        "source_health_daily": source_health_report,
        "seller_recovery_audit": seller_recovery_audit,
        "truth_boundary": "Samples only sanitized aggregate fields from recent rows. Does not print VINs, titles, URLs, user data, tokens, or raw listing payloads.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only sanitized Supabase live inspection.")
    parser.add_argument("--run-id", help="Optional Apify run id for sanitized run-level ingest inspection.")
    args = parser.parse_args()

    base_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url.endswith(".supabase.co") and ".supabase.co/" not in base_url:
        print("warning: SUPABASE_URL does not look like a Supabase project URL", file=sys.stderr)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_url_host": base_url.replace("https://", "").split("/", 1)[0],
        "tables": {},
        "proof_boundary": "Read-only REST aggregate probe. Does not print secrets or row payloads; does not prove business quality or Telegram delivery content.",
    }

    failures: dict[str, str] = {}
    for table, config in TABLES.items():
        try:
            report["tables"][table] = {
                "count": _count(base_url, service_key, table),
                "latest_timestamp": _latest_timestamp(base_url, service_key, table, config["timestamp_candidates"]),
                "status_sample": _status_sample(base_url, service_key, table, config["status_candidates"]),
            }
        except Exception as exc:  # intentionally report table-level failure only
            failures[table] = str(exc)[:500]
    if failures:
        report["table_failures"] = failures

    try:
        report["row_level_truth_sample"] = _safe_truth_audit(base_url, service_key)
    except Exception as exc:
        report["row_level_truth_sample_failure"] = str(exc)[:500]

    try:
        report["opportunity_lifecycle_schema_truth"] = _opportunity_lifecycle_schema_truth(base_url, service_key)
    except Exception as exc:
        report["opportunity_lifecycle_schema_truth_failure"] = str(exc)[:500]

    if args.run_id:
        try:
            report["run_id_truth_sample"] = _run_id_truth_audit(base_url, service_key, args.run_id)
        except Exception as exc:
            report["run_id_truth_sample_failure"] = str(exc)[:500]

    print(json.dumps(report, indent=2, sort_keys=True))
    critical = ["webhook_log", "opportunities", "alert_log"]
    missing = [t for t in critical if t not in report["tables"]]
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
