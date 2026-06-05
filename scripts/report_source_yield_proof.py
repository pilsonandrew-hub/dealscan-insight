#!/usr/bin/env python3
"""Report source-by-source live yield without printing row payloads."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from report_pricing_blocked_source_candidates import (
    _fetch_postgrest_rows,
    _normalize_supabase_rest_url,
    resolve_rest_config,
)


GENERIC_SOURCES = {"", "unknown", "db_save", "sonar_mirror", "webhook", "apify"}
DEPLOYMENT_PATH = Path(__file__).resolve().parent.parent / "apify" / "deployment.json"


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _actor_source_by_id(path: Path = DEPLOYMENT_PATH) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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
        source = _canon_source(actor_name)
        if actor_id and source:
            source_by_id[actor_id] = source
    return source_by_id


def _source_from_row(
    row: dict[str, Any],
    *,
    run_sources: dict[str, str] | None = None,
    actor_sources: dict[str, str] | None = None,
) -> str:
    run_id = str(row.get("run_id") or row.get("source_run_id") or "").strip()
    direct = _canon_source(
        row.get("source_site")
        or row.get("source")
        or row.get("source_name")
        or row.get("actor_name")
    )
    actor_id = str(row.get("actor_id") or "").strip()
    actor_source = (actor_sources or {}).get(actor_id)
    if direct and direct not in GENERIC_SOURCES:
        return direct
    if actor_source:
        return actor_source
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
        if int(summary.get("webhook_item_count_total") or 0) == 0:
            return "source_empty_result"
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


def classify_run_summary(summary: dict[str, Any]) -> str:
    if int(summary.get("opportunity_rows") or 0) > 0:
        return "accepted_flow_present"
    if int(summary.get("webhook_processed_rows") or 0) > 0 and int(summary.get("delivery_rows") or 0) == 0:
        if int(summary.get("webhook_item_count_total") or 0) == 0:
            return "source_empty_result"
        return "webhook_without_delivery_gap"

    status_counts = summary.get("status_counts") or {}
    delivery_rows = int(summary.get("delivery_rows") or 0)
    if delivery_rows == 0:
        return "no_recent_delivery_rows"
    if int(status_counts.get("skipped_gate") or 0) == delivery_rows:
        return "source_quality_reject_dominant"
    if int(status_counts.get("skipped_margin") or 0) == delivery_rows:
        return "economic_reject_dominant"
    if int(status_counts.get("skipped_ceiling") or 0) == delivery_rows:
        return "pricing_ceiling_reject_dominant"
    if int(status_counts.get("skipped_proof") or 0) == delivery_rows:
        return "proof_control_only"
    return classify_source_summary(summary)


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


def _available_columns(base_url: str, service_role_key: str, table: str) -> set[str]:
    rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        table,
        [("select", "*"), ("limit", "1")],
    )
    if rows and isinstance(rows[0], dict):
        return set(rows[0].keys())
    return set()


def _select_available(columns: set[str], desired: list[str], fallback: str) -> str:
    selected = [column for column in desired if column in columns]
    return ",".join(selected) if selected else fallback


def _delivery_select_for_columns(columns: set[str]) -> tuple[str, str]:
    order = "created_at" if "created_at" in columns else "updated_at"
    return (
        _select_available(
            columns,
            ["run_id", "source_site", "source", "channel", "status", "error_message", "created_at", "updated_at"],
            order,
        ),
        order,
    )


def _fetch_optional_delivery_rows(
    base_url: str,
    service_role_key: str,
    table: str,
    since: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        columns = _available_columns(base_url, service_role_key, table)
    except Exception:
        return []
    if not columns:
        return []
    select, order = _delivery_select_for_columns(columns)
    try:
        return _fetch_recent_rows(
            base_url,
            service_role_key,
            table,
            select,
            order,
            since,
            limit,
        )
    except Exception:
        return []


def _fetch_optional_delivery_rows_for_run(
    base_url: str,
    service_role_key: str,
    table: str,
    run_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        columns = _available_columns(base_url, service_role_key, table)
    except Exception:
        return []
    if not columns or "run_id" not in columns:
        return []
    select, order = _delivery_select_for_columns(columns)
    try:
        return _fetch_postgrest_rows(
            base_url,
            service_role_key,
            table,
            [
                ("select", select),
                ("run_id", f"eq.{run_id}"),
                ("order", f"{order}.asc"),
                ("limit", str(limit)),
            ],
        )
    except Exception:
        return []


def build_source_yield_report(
    supabase_url: str,
    service_role_key: str,
    *,
    lookback_hours: int,
    limit: int,
    run_detail_source: str | None = None,
    now: datetime | None = None,
    deployment_path: Path = DEPLOYMENT_PATH,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    since = current_time - timedelta(hours=lookback_hours)
    base_url = _normalize_supabase_rest_url(supabase_url)
    actor_sources = _actor_source_by_id(deployment_path)
    detail_source = _canon_source(run_detail_source) if run_detail_source else None

    webhook_columns = _available_columns(base_url, service_role_key, "webhook_log")
    webhook_order = "received_at" if "received_at" in webhook_columns else "created_at"
    webhook_select = _select_available(
        webhook_columns,
        [
            "run_id",
            "actor_name",
            "actor_id",
            "source",
            "source_site",
            "status",
            "processing_status",
            "db_save",
            "item_count",
            "received_at",
            "created_at",
        ],
        webhook_order,
    )
    webhook_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "webhook_log",
        webhook_select,
        webhook_order,
        since,
        limit,
    )
    run_sources: dict[str, str] = {}
    webhook_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    webhook_item_count_by_source: Counter[str] = Counter()
    webhook_by_run: dict[str, Counter[str]] = defaultdict(Counter)
    webhook_item_count_by_run: Counter[str] = Counter()
    processed_positive_run_ids: set[str] = set()
    for row in webhook_rows:
        source = _source_from_row(row, actor_sources=actor_sources)
        run_id = str(row.get("run_id") or "").strip()
        if run_id and source != "unknown":
            run_sources[run_id] = source
        status = str(row.get("status") or row.get("processing_status") or row.get("db_save") or "unknown")[:80]
        webhook_by_source[source][status] += 1
        if run_id:
            webhook_by_run[run_id][status] += 1
        if status == "processed":
            item_count = _safe_int(row.get("item_count"))
            webhook_item_count_by_source[source] += item_count
            if run_id:
                webhook_item_count_by_run[run_id] += item_count
                if item_count > 0:
                    processed_positive_run_ids.add(run_id)

    delivery_columns = _available_columns(base_url, service_role_key, "ingest_delivery_log")
    delivery_order = "created_at"
    delivery_select = _select_available(
        delivery_columns,
        ["run_id", "source_site", "source", "channel", "status", "error_message", "created_at"],
        delivery_order,
    )
    delivery_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "ingest_delivery_log",
        delivery_select,
        delivery_order,
        since,
        limit,
    )
    primary_delivery_run_ids = {
        str(row.get("run_id") or "").strip()
        for row in delivery_rows
        if str(row.get("run_id") or "").strip()
    }
    legacy_delivery_rows = [
        row
        for row in _fetch_optional_delivery_rows(base_url, service_role_key, "delivery_log", since, limit)
        if str(row.get("run_id") or "").strip()
        and str(row.get("run_id") or "").strip() not in primary_delivery_run_ids
    ]
    fallback_seen = {
        (
            str(row.get("run_id") or ""),
            str(row.get("channel") or ""),
            str(row.get("status") or ""),
            str(row.get("error_message") or ""),
            str(row.get("created_at") or row.get("updated_at") or ""),
        )
        for row in legacy_delivery_rows
    }
    missing_primary_run_ids = sorted(processed_positive_run_ids - primary_delivery_run_ids)
    for run_id in missing_primary_run_ids:
        for row in _fetch_optional_delivery_rows_for_run(
            base_url,
            service_role_key,
            "delivery_log",
            run_id,
            limit,
        ):
            key = (
                str(row.get("run_id") or ""),
                str(row.get("channel") or ""),
                str(row.get("status") or ""),
                str(row.get("error_message") or ""),
                str(row.get("created_at") or row.get("updated_at") or ""),
            )
            if key not in fallback_seen:
                fallback_seen.add(key)
                legacy_delivery_rows.append(row)
    all_delivery_rows = delivery_rows + legacy_delivery_rows
    delivery_by_source: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: {
        "channel": Counter(),
        "status": Counter(),
        "reason": Counter(),
    })
    delivery_by_run: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: {
        "status": Counter(),
        "reason": Counter(),
    })
    for row in all_delivery_rows:
        source = _source_from_row(row, run_sources=run_sources)
        run_id = str(row.get("run_id") or "").strip()
        if run_id and source != "unknown":
            run_sources[run_id] = source
        delivery_by_source[source]["channel"][str(row.get("channel") or "unknown")[:80]] += 1
        delivery_by_source[source]["status"][str(row.get("status") or "unknown")[:80]] += 1
        delivery_by_source[source]["reason"][_reason_bucket(row.get("error_message"))] += 1
        if run_id:
            delivery_by_run[run_id]["status"][str(row.get("status") or "unknown")[:80]] += 1
            delivery_by_run[run_id]["reason"][_reason_bucket(row.get("error_message"))] += 1

    opportunity_columns = _available_columns(base_url, service_role_key, "opportunities")
    opportunity_order = "created_at"
    opportunity_select = _select_available(
        opportunity_columns,
        [
            "source_site",
            "source",
            "source_name",
            "run_id",
            "source_run_id",
            "active",
            "is_active",
            "dos_score",
            "score",
            "created_at",
        ],
        opportunity_order,
    )
    opportunity_rows = _fetch_recent_rows(
        base_url,
        service_role_key,
        "opportunities",
        opportunity_select,
        opportunity_order,
        since,
        limit,
    )
    opportunities_by_source: dict[str, dict[str, int]] = defaultdict(lambda: {
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "active_dos80_rows": 0,
    })
    opportunities_by_run: dict[str, dict[str, int]] = defaultdict(lambda: {
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "active_dos80_rows": 0,
    })
    for row in opportunity_rows:
        source = _source_from_row(row, run_sources=run_sources)
        run_id = str(row.get("source_run_id") or row.get("run_id") or "").strip()
        if run_id and source != "unknown":
            run_sources[run_id] = source
        opportunities_by_source[source]["opportunity_rows"] += 1
        if run_id:
            opportunities_by_run[run_id]["opportunity_rows"] += 1
        if _parse_bool(row.get("active") if "active" in row else row.get("is_active")):
            opportunities_by_source[source]["active_opportunity_rows"] += 1
            if run_id:
                opportunities_by_run[run_id]["active_opportunity_rows"] += 1
            score = _safe_float(row.get("dos_score") if row.get("dos_score") is not None else row.get("score"))
            if score is not None and score >= 80:
                opportunities_by_source[source]["active_dos80_rows"] += 1
                if run_id:
                    opportunities_by_run[run_id]["active_dos80_rows"] += 1

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
            "webhook_item_count_total": int(webhook_item_count_by_source[source]),
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

    report = {
        "generated_at": current_time.isoformat(),
        "lookback_hours": lookback_hours,
        "db_path": "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY",
        "delivery_log_fallback_rows": len(legacy_delivery_rows),
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
    if detail_source:
        run_ids = sorted(set(webhook_by_run) | set(delivery_by_run) | set(opportunities_by_run))
        run_summaries: list[dict[str, Any]] = []
        for run_id in run_ids:
            source = run_sources.get(run_id, "unknown")
            if source != detail_source:
                continue
            webhook_status_counts = webhook_by_run[run_id]
            delivery_counters = delivery_by_run[run_id]
            opportunity_counts = opportunities_by_run[run_id]
            run_summary = {
                "run_id": run_id[:120],
                "source": source,
                "webhook_rows": sum(webhook_status_counts.values()),
                "webhook_processed_rows": int(webhook_status_counts.get("processed") or 0),
                "webhook_item_count_total": int(webhook_item_count_by_run[run_id]),
                "delivery_rows": sum(delivery_counters["status"].values()),
                "status_counts": dict(delivery_counters["status"].most_common(10)),
                "reason_counts": dict(delivery_counters["reason"].most_common(10)),
                "opportunity_rows": opportunity_counts["opportunity_rows"],
                "active_opportunity_rows": opportunity_counts["active_opportunity_rows"],
                "active_dos80_rows": opportunity_counts["active_dos80_rows"],
            }
            run_summary["classification"] = classify_run_summary(run_summary)
            run_summaries.append(run_summary)
        report["run_detail_source"] = detail_source
        report["run_summaries"] = sorted(
            run_summaries,
            key=lambda item: (
                -int(item["webhook_item_count_total"]),
                -int(item["delivery_rows"]),
                item["run_id"],
            ),
        )[:25]
        run_classification_counts = Counter(str(item["classification"]) for item in run_summaries)
        report["run_classification_counts"] = dict(run_classification_counts.most_common())
        if run_classification_counts.get("webhook_without_delivery_gap"):
            report["overall_verdict"] = "diagnostic_gap"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--via-rest", action="store_true", help="Use Supabase REST secrets from the environment.")
    parser.add_argument("--env-file", help="Optional env file to resolve Supabase REST settings.")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--source", help="Optional source slug for sanitized run-level summaries.")
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
        run_detail_source=args.source,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
