#!/usr/bin/env python3
"""Materialize sanitized pricing recovery groups into an operator queue."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any
from typing import Protocol


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

    def upsert_request(self, record: dict[str, Any]) -> dict[str, Any]: ...

    def insert_event(self, event: dict[str, Any]) -> None: ...


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="JSON file of grouped pricing recovery rows.")
    args = parser.parse_args()
    if not args.input_json:
        print(json.dumps({"queue_records": 0}, sort_keys=True))
        return 0
    with open(args.input_json, encoding="utf-8") as handle:
        groups = json.load(handle)
    records = [
        build_queue_record(group, proof_run_id="local", head_sha="local", now=datetime.now(timezone.utc))
        for group in groups
    ]
    print(json.dumps({"queue_records": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
