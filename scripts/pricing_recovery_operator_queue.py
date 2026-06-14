#!/usr/bin/env python3
"""Materialize sanitized pricing recovery groups into an operator queue."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import report_pricing_coverage_gaps


RECOVERY_STATUSES = {
    "covered_by_market_prices",
    "covered_by_dealer_sales",
    "covered_by_competitor_sales",
    "seedable_from_internal_history",
    "insufficient_dealer_sales",
    "insufficient_internal_history",
    "insufficient_competitor_sales",
    "blocked_no_internal_comp_evidence",
    "dirty_source_row",
    "expired_pricing_gap",
}
RECOMMENDED_ACTIONS = {
    "none",
    "refresh_market_prices_from_dealer_sales",
    "refresh_market_prices_from_competitor_sales",
    "review_internal_history_for_completed_sales_evidence",
    "request_completed_sales_evidence",
    "wait_for_more_internal_history",
    "ignore_dirty_source_row",
    "ignore_expired_listing",
}
QUEUE_STATUSES = {
    "open",
    "evidence_requested",
    "evidence_received",
    "preview_ready",
    "applied",
    "blocked",
    "dismissed",
}
APPLY_CONFIRMATION = "SYNC_PRICING_RECOVERY_OPERATOR_QUEUE"
VIN_LIKE_RE = re.compile(r"\b(?:vin\s*#?\s*)?[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


class QueueRepository(Protocol):
    def get_by_group_key(self, group_key: str) -> dict[str, Any] | None: ...

    def save_request_with_event(self, record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]: ...


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _iso(value: datetime) -> str:
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def _validate_choice(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {label}: {value}")
    return value


def _safe_text(value: Any) -> str:
    return VIN_LIKE_RE.sub("[redacted]", _norm_text(value))


def _postgrest_eq_literal(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'eq."{escaped}"'


def build_queue_record(group: dict[str, Any], *, proof_run_id: str, head_sha: str, now: datetime) -> dict[str, Any]:
    key = group.get("key") or {}
    sources = sorted(_norm_text(source) for source in (group.get("source_counts") or {}) if _norm_text(source))
    year = _clean_int(key.get("year")) or None
    make = _safe_text(key.get("make"))
    model = _safe_text(key.get("model"))
    state = _norm_text(key.get("state")) or None
    if not year or not make or not model:
        raise ValueError("queue record requires year, make, and model")

    status = _validate_choice(str(group.get("status") or ""), RECOVERY_STATUSES, "recovery status")
    action = _validate_choice(str(group.get("recommended_action") or ""), RECOMMENDED_ACTIONS, "recommended action")
    evidence = group.get("evidence_counts") or {}
    return {
        "group_key": "|".join([str(year), make, model, state or "", ",".join(sources)]),
        "year": year,
        "make": make,
        "model": model,
        "state": state,
        "source_families": sources,
        "candidate_count": _clean_int(group.get("candidate_count")),
        "status": status,
        "recommended_action": action,
        "queue_status": "open",
        "market_prices_usable": _clean_int(evidence.get("usable_market_prices")),
        "market_prices_total": _clean_int(evidence.get("market_prices")),
        "dealer_sales_usable": _clean_int(evidence.get("usable_dealer_sales")),
        "dealer_sales_total": _clean_int(evidence.get("dealer_sales")),
        "competitor_sales_usable": _clean_int(evidence.get("usable_competitor_sales")),
        "competitor_sales_total": _clean_int(evidence.get("competitor_sales")),
        "internal_history_usable": _clean_int(evidence.get("usable_internal_history")),
        "internal_history_total": _clean_int(evidence.get("internal_history")),
        "latest_proof_run_id": str(proof_run_id),
        "latest_proof_head_sha": str(head_sha),
        "last_seen_at": _iso(now),
    }


def sync_queue_records(
    records: list[dict[str, Any]],
    *,
    repo: QueueRepository,
    apply: bool,
    confirmation: str,
    actor: str = "local",
) -> dict[str, int]:
    if apply and confirmation != APPLY_CONFIRMATION:
        raise ValueError(f"queue sync requires confirmation={APPLY_CONFIRMATION}")

    summary = {"would_insert": 0, "would_update": 0, "inserted": 0, "updated": 0}
    for record in records:
        existing = repo.get_by_group_key(record["group_key"])
        payload = dict(record)
        if existing:
            for field in ("queue_status", "owner", "priority", "blocked_reason", "resolution_notes", "resolved_at"):
                if field in existing:
                    payload[field] = existing[field]
        if not apply:
            summary["would_update" if existing else "would_insert"] += 1
            continue

        event_type = "updated" if existing else "inserted"
        event = {
            "event_type": event_type,
            "previous_queue_status": (existing or {}).get("queue_status"),
            "next_queue_status": payload["queue_status"],
            "actor": actor,
            "reason": payload["recommended_action"],
            "proof_run_id": payload.get("latest_proof_run_id"),
            "head_sha": payload.get("latest_proof_head_sha"),
            "metadata": {"group_key": payload["group_key"], "status": payload["status"]},
        }
        saved = repo.save_request_with_event(payload, event)
        summary[event_type] += 1
    return summary


class DryRunQueueRepository:
    def get_by_group_key(self, group_key: str) -> dict[str, Any] | None:
        return None

    def save_request_with_event(self, record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        return {"id": "dry-run", **record}


class SupabaseRestQueueRepository:
    def __init__(self, *, supabase_url: str, service_role_key: str):
        self.base_url = supabase_url.rstrip("/").removesuffix("/rest/v1")
        self.service_role_key = service_role_key

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"
        request = urllib_request.Request(
            f"{self.base_url}/rest/v1/{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=30) as response:
                raw_payload = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase REST API error: HTTP {exc.code} {body[:300]}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Supabase REST API unreachable: {exc}") from exc
        return json.loads(raw_payload or "[]")

    def get_by_group_key(self, group_key: str) -> dict[str, Any] | None:
        query = urllib_parse.urlencode(
            {
                "select": (
                    "id,group_key,queue_status,owner,priority,"
                    "blocked_reason,resolution_notes,resolved_at"
                ),
                "group_key": _postgrest_eq_literal(group_key),
                "limit": "1",
            }
        )
        rows = self._request("GET", f"pricing_recovery_requests?{query}")
        if not isinstance(rows, list) or not rows:
            return None
        return dict(rows[0])

    def save_request_with_event(self, record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        row = self._request(
            "POST",
            "rpc/sync_pricing_recovery_request",
            {"request_payload": record, "event_payload": event},
        )
        if not isinstance(row, dict) or not row:
            raise RuntimeError("Supabase queue sync RPC returned no row")
        return dict(row)


def repository_for_sync(
    *,
    apply: bool,
    rest_base_url: str | None,
    service_role_key: str | None,
) -> QueueRepository:
    if rest_base_url and service_role_key:
        return SupabaseRestQueueRepository(
            supabase_url=rest_base_url,
            service_role_key=service_role_key,
        )
    if apply:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for queue apply")
    return DryRunQueueRepository()


def records_from_live_pricing_proof(
    *,
    proof_run_id: str,
    head_sha: str,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    limit: int,
    now: datetime,
) -> list[dict[str, Any]]:
    rest_base_url, service_role_key, _ = report_pricing_coverage_gaps.resolve_rest_config(None)
    if not rest_base_url or not service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for live queue proof")
    rows = report_pricing_coverage_gaps.fetch_gap_rows_via_rest(
        rest_base_url,
        service_role_key,
        lookback_days=lookback_days,
        max_mileage=max_mileage,
        max_age_years=max_age_years,
        limit=limit,
    )
    groups = report_pricing_coverage_gaps.group_recovery_rows(rows)
    return [
        build_queue_record(group, proof_run_id=proof_run_id, head_sha=head_sha, now=now)
        for group in groups
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="JSON file of grouped pricing recovery rows.")
    parser.add_argument("--from-live-pricing-proof", action="store_true")
    parser.add_argument("--proof-run-id", default=os.getenv("GITHUB_RUN_ID", "local"))
    parser.add_argument("--head-sha", default=os.getenv("GITHUB_SHA", "local"))
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--max-mileage", type=int, default=100000)
    parser.add_argument("--max-age-years", type=int, default=10)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--queue-dry-run", action="store_true")
    parser.add_argument("--queue-apply", action="store_true")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.from_live_pricing_proof:
        records = records_from_live_pricing_proof(
            proof_run_id=args.proof_run_id,
            head_sha=args.head_sha,
            lookback_days=args.lookback_days,
            max_mileage=args.max_mileage,
            max_age_years=args.max_age_years,
            limit=args.limit,
            now=now,
        )
    elif args.input_json:
        with open(args.input_json, encoding="utf-8") as handle:
            groups = json.load(handle)
        records = [
            build_queue_record(group, proof_run_id=args.proof_run_id, head_sha=args.head_sha, now=now)
            for group in groups
        ]
    else:
        records = []

    apply = bool(args.queue_apply)
    rest_base_url, service_role_key, _ = report_pricing_coverage_gaps.resolve_rest_config(None)
    try:
        repo = repository_for_sync(
            apply=apply,
            rest_base_url=rest_base_url,
            service_role_key=service_role_key,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    summary = sync_queue_records(
        records,
        repo=repo,
        apply=apply,
        confirmation=args.confirmation,
        actor="github-actions" if os.getenv("GITHUB_ACTIONS") else "local",
    )
    print(f"pricing_recovery_queue_records={len(records)}")
    print(f"pricing_recovery_queue_summary={json.dumps(summary, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
