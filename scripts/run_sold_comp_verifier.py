#!/usr/bin/env python3
"""Run deterministic Comp Evidence Ledger candidate verification.

Default posture is dry-run. Write mode is intentionally narrow: reviews,
verified comps, candidate review status, and run aggregate counters only.
"""

from __future__ import annotations

import os
import sys
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from supabase import create_client

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_sold_comp_candidates import (
    build_review_row,
    build_verified_comp_row,
    evaluate_candidate,
)


REVIEWER = "market_scout_verifier"
REVIEWER_VERSION = "deterministic-v1"
VERIFIED_ID_PAGE_SIZE = 1000
RUN_STATUS_PAGE_SIZE = 1000
CANONICAL_REJECTION_REASONS = {
    "duplicate_source_listing",
    "invalid_sale_date",
    "invalid_vin",
    "implausible_price",
    "missing_evidence_ref",
    "missing_listing_url",
    "missing_sold_price",
    "missing_year_make_model",
    "outside_approved_vehicle_scope",
}
NONCANONICAL_REJECTION_REASON = "noncanonical_rejection_reason"

CANDIDATE_SELECT = ",".join(
    [
        "id",
        "run_id",
        "source_name",
        "source_listing_id",
        "listing_url",
        "evidence_ref",
        "sale_date",
        "sold_price_hammer",
        "buyer_premium",
        "fees",
        "sold_price_all_in",
        "price_basis",
        "currency",
        "year",
        "make",
        "model",
        "trim",
        "vin",
        "mileage",
        "title_brand_status",
        "condition_text",
        "defect_signals",
        "location_city",
        "location_state",
        "region",
        "channel",
        "dedup_key",
        "extractor_version",
        "source_policy_version",
        "candidate_status",
        "rejection_reason",
    ]
)


def _truthy_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _fetch_candidates(supabase: Any, *, limit: int, run_id: str | None = None) -> list[dict[str, Any]]:
    query = (
        supabase.table("sold_comp_candidates")
        .select(CANDIDATE_SELECT)
        .eq("candidate_status", "candidate")
    )
    if run_id:
        query = query.eq("run_id", run_id).order("created_at", desc=True)
    response = query.limit(limit).execute()
    return response.data or []


def _fetch_existing_verified_source_listing_ids(
    supabase: Any,
    *,
    page_size: int = VERIFIED_ID_PAGE_SIZE,
) -> set[str]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            supabase.table("verified_sold_comps")
            .select("source_name,source_listing_id")
            .order("candidate_id", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return {
        f"{row.get('source_name')}:{row.get('source_listing_id')}"
        for row in rows
        if row.get("source_name") and row.get("source_listing_id")
    }


def _fetch_run_candidate_status_counts(
    supabase: Any,
    *,
    run_id: str,
    page_size: int = RUN_STATUS_PAGE_SIZE,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    offset = 0
    while True:
        response = (
            supabase.table("sold_comp_candidates")
            .select("candidate_status")
            .eq("run_id", run_id)
            .order("id", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        counts.update(
            str(row.get("candidate_status"))
            for row in page
            if row.get("candidate_status")
        )
        if len(page) < page_size:
            break
        offset += page_size
    return counts


def _candidate_status_for_review(review_status: str) -> str:
    if review_status == "accepted":
        return "verified"
    return review_status


def _safe_rejection_reason(reason: str | None) -> str:
    if reason in CANONICAL_REJECTION_REASONS:
        return str(reason)
    return NONCANONICAL_REJECTION_REASON


def _write_rows(
    supabase: Any,
    *,
    review_rows: list[dict[str, Any]],
    verified_rows: list[dict[str, Any]],
    candidate_updates: list[dict[str, Any]],
    run_updates: set[str],
) -> dict[str, int]:
    if review_rows:
        supabase.table("sold_comp_reviews").upsert(
            review_rows,
            on_conflict="candidate_id,reviewer,reviewer_version",
        ).execute()
    if verified_rows:
        supabase.table("verified_sold_comps").upsert(
            verified_rows,
            on_conflict="candidate_id",
        ).execute()
    for update in candidate_updates:
        supabase.table("sold_comp_candidates").update(
            {
                "candidate_status": update["candidate_status"],
                "rejection_reason": update["rejection_reason"],
            }
        ).eq("id", update["candidate_id"]).execute()
    for run_id in run_updates:
        counts = _fetch_run_candidate_status_counts(supabase, run_id=run_id)
        supabase.table("market_scout_runs").update(
            {
                "records_verified": counts.get("verified", 0),
                "records_rejected": counts.get("rejected", 0),
                "records_needs_review": counts.get("needs_review", 0),
                "records_promoted": counts.get("verified", 0),
            }
        ).eq("run_id", run_id).execute()

    return {
        "review_rows_written": len(review_rows),
        "verified_rows_written": len(verified_rows),
        "candidate_rows_updated": len(candidate_updates),
        "run_rows_updated": len(run_updates),
    }


def run_verifier(
    supabase: Any,
    *,
    dry_run: bool = True,
    limit: int = 100,
    run_id: str | None = None,
    today: date | None = None,
    reviewer: str = REVIEWER,
    reviewer_version: str = REVIEWER_VERSION,
) -> dict[str, Any]:
    candidates = _fetch_candidates(supabase, limit=limit, run_id=run_id)
    existing_verified = _fetch_existing_verified_source_listing_ids(supabase)
    decision_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    run_updates: set[str] = set()
    review_rows: list[dict[str, Any]] = []
    verified_rows: list[dict[str, Any]] = []
    candidate_updates: list[dict[str, Any]] = []

    for candidate in candidates:
        decision = evaluate_candidate(
            candidate,
            today=today,
            existing_verified_source_listing_ids=existing_verified,
        )
        decision_counts[decision.review_status] += 1
        if decision.rejection_reason:
            rejection_reason_counts[_safe_rejection_reason(decision.rejection_reason)] += 1
        run_updates.add(str(candidate["run_id"]))
        review_rows.append(
            build_review_row(
                candidate,
                decision,
                reviewer=reviewer,
                reviewer_version=reviewer_version,
            )
        )
        if verified_row := build_verified_comp_row(
            candidate,
            decision,
            verifier_version=reviewer_version,
        ):
            verified_rows.append(verified_row)
        candidate_updates.append(
            {
                "candidate_id": candidate["id"],
                "candidate_status": _candidate_status_for_review(decision.review_status),
                "rejection_reason": decision.rejection_reason,
            }
        )

    write_counts = {
        "review_rows_written": 0,
        "verified_rows_written": 0,
        "candidate_rows_updated": 0,
        "run_rows_updated": 0,
    }
    if not dry_run:
        write_counts = _write_rows(
            supabase,
            review_rows=review_rows,
            verified_rows=verified_rows,
            candidate_updates=candidate_updates,
            run_updates=run_updates,
        )

    return {
        "dry_run": dry_run,
        "reviewer": reviewer,
        "reviewer_version": reviewer_version,
        "run_id": run_id,
        "candidates_reviewed": len(candidates),
        "decision_counts": dict(decision_counts),
        "rejection_reason_counts": dict(rejection_reason_counts),
        **write_counts,
    }


def build_message(summary: dict[str, Any]) -> str:
    label = " DRY RUN" if summary.get("dry_run") else ""
    decisions = summary.get("decision_counts") or {}
    decision_text = ", ".join(
        f"{key}={value}" for key, value in sorted(decisions.items())
    ) or "none"
    rejection_reasons = summary.get("rejection_reason_counts") or {}
    safe_rejection_reasons = Counter()
    for reason, count in rejection_reasons.items():
        safe_rejection_reasons[_safe_rejection_reason(str(reason))] += count
    rejection_reason_text = (
        ", ".join(
            f"{key}={value}" for key, value in sorted(safe_rejection_reasons.items())
        )
        or "none"
    )
    return (
        f"DealerScope Sold Comp Verifier{label}\n"
        f"Candidates reviewed: {summary.get('candidates_reviewed', 0)}\n"
        f"Decisions: {decision_text}\n"
        f"Rejection reasons: {rejection_reason_text}\n"
        f"Review rows written: {summary.get('review_rows_written', 0)}\n"
        f"Verified rows written: {summary.get('verified_rows_written', 0)}\n"
        f"Candidate rows updated: {summary.get('candidate_rows_updated', 0)}\n"
        f"Run rows updated: {summary.get('run_rows_updated', 0)}"
    )


def main() -> int:
    if _truthy_env(os.environ.get("SOLD_COMP_VERIFIER_IMPORT_CHECK")):
        print("SOLD_COMP_VERIFIER_IMPORT_OK")
        return 0

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    summary = run_verifier(
        supabase,
        dry_run=_truthy_env(os.environ.get("SOLD_COMP_VERIFIER_DRY_RUN"), default=True),
        limit=int(os.environ.get("SOLD_COMP_VERIFIER_LIMIT", "100")),
        run_id=(os.environ.get("SOLD_COMP_VERIFIER_RUN_ID") or "").strip() or None,
    )
    print(build_message(summary))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
