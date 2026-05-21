#!/usr/bin/env python3
"""Read-only Supabase live evidence probe for DealerScope.

Prints aggregate counts and timestamp/status summaries only. It intentionally
avoids row payloads, customer/user fields, tokens, and listing details.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
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
}

HIGH_RUST_STATES = {
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA",
    "ND", "SD", "NE", "KS", "WV", "ME", "NH", "VT", "MA", "RI",
    "CT", "NJ", "MD", "DE",
}


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
        {"select": "id", "limit": "1"},
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


def _recent_rows(base_url: str, service_key: str, table: str, select: str, order_column: str, limit: int) -> list[dict[str, Any]]:
    _, _, rows = _request(
        base_url,
        service_key,
        table,
        {"select": select, "order": f"{order_column}.desc", "limit": str(limit)},
    )
    return rows if isinstance(rows, list) else []


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


def _safe_truth_audit(base_url: str, service_key: str) -> dict[str, Any]:
    opportunity_select = ",".join([
        "created_at", "updated_at", "source_site", "state", "year", "score",
        "current_bid", "estimated_sale_price", "potential_profit", "profit_margin",
        "roi_percentage", "auction_end", "status", "is_active",
    ])
    recent_opportunities = _recent_rows(base_url, service_key, "opportunities", opportunity_select, "created_at", 200)

    alert_rows = _recent_rows(
        base_url,
        service_key,
        "alert_log",
        "created_at,sent_at,status,delivery_status,channel",
        "created_at",
        50,
    )
    alert_status_counts: Counter[str] = Counter()
    for row in alert_rows:
        key = row.get("delivery_status") or row.get("status") or row.get("channel") or "unknown"
        alert_status_counts[str(key)[:80]] += 1

    webhook_rows = _recent_rows(
        base_url,
        service_key,
        "webhook_log",
        "received_at,created_at,status,processing_status,db_save",
        "received_at",
        100,
    )
    webhook_status_counts: Counter[str] = Counter()
    for row in webhook_rows:
        key = row.get("status") or row.get("processing_status") or row.get("db_save") or "unknown"
        webhook_status_counts[str(key)[:80]] += 1

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
        "truth_boundary": "Samples only sanitized aggregate fields from recent rows. Does not print VINs, titles, URLs, user data, tokens, or raw listing payloads.",
    }


def main() -> int:
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

    print(json.dumps(report, indent=2, sort_keys=True))
    critical = ["webhook_log", "opportunities", "alert_log"]
    missing = [t for t in critical if t not in report["tables"]]
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
