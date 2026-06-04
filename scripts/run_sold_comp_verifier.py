#!/usr/bin/env python3
"""Run deterministic Comp Evidence Ledger candidate verification.

Default posture is dry-run. Write mode is intentionally narrow: reviews,
verified comps, candidate review status, and run aggregate counters only.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
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


def _fetch_candidates(supabase: Any, *, limit: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sold_comp_candidates")
        .select(CANDIDATE_SELECT)
        .in_("candidate_status", ["candidate", "rejected", "needs_review"])
        .limit(limit)
        .execute()
    )
    return response.data or []


def _fetch_existing_verified_source_listing_ids(supabase: Any) -> set[str]:
    response = (
        supabase.table("verified_sold_comps")
        .select("source_name,source_listing_id")
        .execute()
    )
    rows = response.data or []
    return {
        f"{row.get('source_name')}:{row.get('source_listing_id')}"
        for row in rows
        if row.get("source_name") and row.get("source_listing_id")
    }


def _candidate_status_for_review(review_status: str) -> str:
    if review_status == "accepted":
        return "verified"
    return review_status


def _write_rows(
    supabase: Any,
    *,
    review_rows: list[dict[str, Any]],
    verified_rows: list[dict[str, Any]],
    candidate_updates: list[dict[str, Any]],
    run_updates: dict[str, Counter[str]],
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
    for run_id, counts in run_updates.items():
        supabase.table("market_scout_runs").update(
            {
                "records_verified": counts.get("accepted", 0),
                "records_rejected": counts.get("rejected", 0),
                "records_needs_review": counts.get("needs_review", 0),
                "records_promoted": counts.get("accepted", 0),
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
    today: date | None = None,
    reviewer: str = REVIEWER,
    reviewer_version: str = REVIEWER_VERSION,
) -> dict[str, Any]:
    candidates = _fetch_candidates(supabase, limit=limit)
    existing_verified = _fetch_existing_verified_source_listing_ids(supabase)
    decision_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    run_updates: dict[str, Counter[str]] = defaultdict(Counter)
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
            rejection_reason_counts[decision.rejection_reason] += 1
        run_updates[str(candidate["run_id"])][decision.review_status] += 1
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
    rejection_reason_text = ", ".join(
        f"{key}={value}" for key, value in sorted(rejection_reasons.items())
    ) or "none"
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
    )
    print(build_message(summary))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
