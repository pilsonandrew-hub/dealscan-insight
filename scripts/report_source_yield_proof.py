#!/usr/bin/env python3
"""Report source-by-source live yield without printing row payloads."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from report_pricing_blocked_source_candidates import (
    _fetch_postgrest_rows,
    _normalize_supabase_rest_url,
    resolve_rest_config,
)


GENERIC_SOURCES = {"", "unknown", "db_save", "sonar_mirror", "webhook", "apify"}


def _canon_source(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = text.replace("_", "-")
    if text.startswith("ds-"):
        text = text[3:]
    if text.endswith("-v2"):
        text = text[:-3]
    if text.endswith("-source"):
        text = text[:-7]
    aliases = {
        "gsa": "gsaauctions",
        "gsa-auctions": "gsaauctions",
        "public-surplus": "publicsurplus",
        "gov-deals": "govdeals",
        "gov-planet": "govplanet",
        "jj-kane": "jjkane",
    }
    text = aliases.get(text, text)
    return None if text in GENERIC_SOURCES else text[:80]


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "active"}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_from_row(row: dict[str, Any], *, run_sources: dict[str, str] | None = None) -> str:
    run_id = str(row.get("run_id") or row.get("source_run_id") or "").strip()
    direct = _canon_source(
        row.get("source_site")
        or row.get("source")
        or row.get("source_name")
        or row.get("actor_name")
        or row.get("actor_id")
    )
    if direct:
        return direct
    if run_sources and run_id:
        return run_sources.get(run_id, "unknown")
    return "unknown"


def _reason_bucket(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "none"
    if text.startswith("margin_below_floor"):
        return "margin_below_floor"
    if text.startswith("pricing_maturity_proxy"):
        return "pricing_maturity_proxy"
    if text.startswith("source_quality_proof_record"):
        return "source_quality_proof_record"
    if "age_or_mileage_exceeded" in text:
        return "age_or_mileage_exceeded"
    if "title_brand_rejected" in text:
        return text.split(":", 1)[0][:80]
    if "commercial_hd_tonnage" in text:
        return "commercial_hd_tonnage"
    return text[:80]


def classify_source_summary(summary: dict[str, Any]) -> str:
    if int(summary.get("opportunity_rows") or 0) > 0:
        return "accepted_flow_present"
    if int(summary.get("webhook_processed_rows") or 0) > 0 and int(summary.get("delivery_rows") or 0) == 0:
        return "webhook_without_delivery_gap"

    status_counts = summary.get("status_counts") or {}
    delivery_rows = int(summary.get("delivery_rows") or 0)
    gate_rows = int(status_counts.get("skipped_gate") or 0)
    margin_rows = int(status_counts.get("skipped_margin") or 0)
    ceiling_rows = int(status_counts.get("skipped_ceiling") or 0)
    proof_rows = int(status_counts.get("skipped_proof") or 0)

    if delivery_rows == 0:
        return "no_recent_delivery_rows"
    if gate_rows >= max(2, int(delivery_rows * 0.5)):
        return "source_quality_reject_dominant"
    if margin_rows >= max(2, int(delivery_rows * 0.35)):
        return "economic_reject_dominant"
    if ceiling_rows >= max(2, int(delivery_rows * 0.35)):
        return "pricing_ceiling_reject_dominant"
    if proof_rows == delivery_rows:
        return "proof_control_only"
    return "mixed_rejection_surface"


def _fetch_recent_rows(
    base_url: str,
    service_role_key: str,
    table: str,
    select: str,
    timestamp_column: str,
    since: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    return _fetch_postgrest_rows(
        base_url,
        service_role_key,
        table,
        [
            ("select", select),
            (timestamp_column, f"gte.{since.isoformat()}"),
            ("order", f"{timestamp_column}.desc"),
            ("limit", str(limit)),
        ],
    )


def build_source_yield_report(
    supabase_url: str,
    service_role_key: str,
    *,
    lookback_hours: int,
    limit: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    since = current_time - timedelta(hours=lookback_hours)
    base_url = _normalize_supabase_rest_url(supabase_url)

    webhook_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "webhook_log",
        "run_id,actor_name,actor_id,source,source_site,status,processing_status,received_at",
        "received_at",
        since,
        limit,
    )
    run_sources: dict[str, str] = {}
    webhook_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in webhook_rows:
        source = _source_from_row(row)
        run_id = str(row.get("run_id") or "").strip()
        if run_id and source != "unknown":
            run_sources[run_id] = source
        status = str(row.get("status") or row.get("processing_status") or "unknown")[:80]
        webhook_by_source[source][status] += 1

    delivery_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "ingest_delivery_log",
        "run_id,source_site,source,channel,status,error_message,created_at",
        "created_at",
        since,
        limit,
    )
    delivery_by_source: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: {
        "channel": Counter(),
        "status": Counter(),
        "reason": Counter(),
    })
    for row in delivery_rows:
        source = _source_from_row(row, run_sources=run_sources)
        delivery_by_source[source]["channel"][str(row.get("channel") or "unknown")[:80]] += 1
        delivery_by_source[source]["status"][str(row.get("status") or "unknown")[:80]] += 1
        delivery_by_source[source]["reason"][_reason_bucket(row.get("error_message"))] += 1

    opportunity_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "opportunities",
        "source_site,source,source_name,source_run_id,active,dos_score,created_at",
        "created_at",
        since,
        limit,
    )
    opportunities_by_source: dict[str, dict[str, int]] = defaultdict(lambda: {
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "active_dos80_rows": 0,
    })
    for row in opportunity_rows:
        source = _source_from_row(row, run_sources=run_sources)
        opportunities_by_source[source]["opportunity_rows"] += 1
        if _parse_bool(row.get("active")):
            opportunities_by_source[source]["active_opportunity_rows"] += 1
            score = _safe_float(row.get("dos_score"))
            if score is not None and score >= 80:
                opportunities_by_source[source]["active_dos80_rows"] += 1

    sources = sorted(set(webhook_by_source) | set(delivery_by_source) | set(opportunities_by_source))
    summaries: list[dict[str, Any]] = []
    for source in sources:
        delivery_counters = delivery_by_source[source]
        opportunity_counts = opportunities_by_source[source]
        webhook_status_counts = webhook_by_source[source]
        summary = {
            "source": source,
            "webhook_rows": sum(webhook_status_counts.values()),
            "webhook_processed_rows": int(webhook_status_counts.get("processed") or 0),
            "delivery_rows": sum(delivery_counters["status"].values()),
            "channel_counts": dict(delivery_counters["channel"].most_common(10)),
            "status_counts": dict(delivery_counters["status"].most_common(10)),
            "reason_counts": dict(delivery_counters["reason"].most_common(10)),
            "opportunity_rows": opportunity_counts["opportunity_rows"],
            "active_opportunity_rows": opportunity_counts["active_opportunity_rows"],
            "active_dos80_rows": opportunity_counts["active_dos80_rows"],
        }
        summary["classification"] = classify_source_summary(summary)
        summaries.append(summary)

    classification_counts = Counter(str(item["classification"]) for item in summaries)
    total_recent_opportunities = sum(int(item["opportunity_rows"]) for item in summaries)
    diagnostic_gap = any(item["classification"] == "webhook_without_delivery_gap" for item in summaries)
    if diagnostic_gap:
        overall = "diagnostic_gap"
    elif total_recent_opportunities > 0:
        overall = "accepted_flow_present"
    elif summaries:
        overall = "no_recent_accepted_source_yield"
    else:
        overall = "no_recent_source_activity"

    return {
        "generated_at": current_time.isoformat(),
        "lookback_hours": lookback_hours,
        "db_path": "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY",
        "overall_verdict": overall,
        "classification_counts": dict(classification_counts.most_common()),
        "source_summaries": sorted(
            summaries,
            key=lambda item: (
                0 if item["classification"] == "webhook_without_delivery_gap" else 1,
                -int(item["delivery_rows"]),
                item["source"],
            ),
        ),
        "truth_boundary": "Read-only sanitized source-yield aggregate. It does not print titles, VINs, URLs, row payloads, tokens, or user data.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--via-rest", action="store_true", help="Use Supabase REST secrets from the environment.")
    parser.add_argument("--env-file", help="Optional env file to resolve Supabase REST settings.")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--json", action="store_true", help="Print compact JSON only.")
    args = parser.parse_args()

    if not args.via_rest:
        print("This proof is intentionally REST-only; pass --via-rest.", flush=True)
        return 2
    base_url, service_key, _ = resolve_rest_config(args.env_file)
    if not base_url or not service_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY for REST proof.", flush=True)
        return 2

    report = build_source_yield_report(
        base_url,
        service_key,
        lookback_hours=args.lookback_hours,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
