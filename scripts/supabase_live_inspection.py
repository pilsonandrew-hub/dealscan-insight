#!/usr/bin/env python3
"""Read-only Supabase live evidence probe for DealerScope.

Prints aggregate counts and timestamp/status summaries only. It intentionally
avoids row payloads, customer/user fields, tokens, and listing details.
"""
from __future__ import annotations

import json
import os
import sys
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

    print(json.dumps(report, indent=2, sort_keys=True))
    critical = ["webhook_log", "opportunities", "alert_log"]
    missing = [t for t in critical if t not in report["tables"]]
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
