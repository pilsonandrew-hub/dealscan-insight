#!/usr/bin/env python3
"""Reconcile active high-DOS rows with explicit negative condition evidence.

This script exists for the narrow PR #78 production reconciliation:
rows that are already proven explicit condition blockers must not remain
Platinum / DOS>=80 in the active pool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.trace_condition_source_evidence import (
    _apify_get,
    build_source_evidence_trace,
    dataset_id_from_run_payload,
)
from webapp.routers.internal import _condition_blocker_basis, _opportunity_condition_proof_row

DEFAULT_LIMIT = 1000


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required env: {name}")
    return value.rstrip("/")


def _coerce_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_explicit_condition_blocked_hot_row(row: dict[str, Any]) -> bool:
    if row.get("is_active") is not True:
        return False
    if max(_coerce_float(row.get("dos_score")), _coerce_float(row.get("score"))) < 80:
        return False
    return _condition_blocker_basis(row) == "explicit_negative_condition_signal"


def is_hot_active_condition_blocked_row(row: dict[str, Any]) -> bool:
    if row.get("is_active") is not True:
        return False
    if max(_coerce_float(row.get("dos_score")), _coerce_float(row.get("score"))) < 80:
        return False
    condition_grade = str(row.get("condition_grade") or "").strip().lower()
    return condition_grade in {"poor", "unknown"}


def is_recovered_source_condition_blocked_hot_row(
    row: dict[str, Any],
    dataset_items: list[dict[str, Any]],
    *,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    if not is_hot_active_condition_blocked_row(row):
        return {"target": False, "reason": "not_active_hot_condition_blocked", "trace": None}

    condition_proof = {
        "selector": {"id": row.get("id")},
        "opportunity": _opportunity_condition_proof_row(row),
    }
    trace = build_source_evidence_trace(
        condition_proof,
        dataset_items,
        dataset_id=dataset_id,
    )
    recommendation = trace.get("backfill_recommendation") or {}
    if (
        trace.get("source_trace", {}).get("matched") is True
        and recommendation.get("status") == "blocked_recovered_source_still_condition_negative"
    ):
        return {
            "target": True,
            "reason": "recovered_source_condition_negative",
            "trace": trace,
        }
    return {"target": False, "reason": "source_trace_not_negative", "trace": trace}


def rejection_payload() -> dict[str, Any]:
    return {
        "dos_score": 0.0,
        "score": 0.0,
        "legacy_dos_score": 0.0,
        "investment_grade": "Rejected",
        "max_bid": 0.0,
        "bid_headroom": 0.0,
        "ceiling_reason": "condition_unverified",
    }


def _request_json(
    *,
    supabase_url: str,
    service_key: str,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    query = f"?{urlencode(params or {})}" if params else ""
    url = f"{supabase_url}/rest/v1/{path}{query}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body or "[]")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} HTTP {exc.code}: {body[:500]}") from exc


def fetch_candidate_rows(supabase_url: str, service_key: str, *, limit: int) -> list[dict[str, Any]]:
    rows = _request_json(
        supabase_url=supabase_url,
        service_key=service_key,
        method="GET",
        path="opportunities",
        params={
            "select": (
                "id,is_active,dos_score,score,title,year,mileage,condition_grade,"
                "source_site,created_at,investment_grade,raw_data"
            ),
            "is_active": "eq.true",
            "or": "(dos_score.gte.80,score.gte.80)",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    return rows if isinstance(rows, list) else []


def fetch_opportunity_row(supabase_url: str, service_key: str, *, opportunity_id: str) -> dict[str, Any]:
    rows = _request_json(
        supabase_url=supabase_url,
        service_key=service_key,
        method="GET",
        path="opportunities",
        params={
            "select": (
                "id,is_active,dos_score,score,title,year,mileage,condition_grade,"
                "source_site,created_at,updated_at,listing_id,investment_grade,raw_data"
            ),
            "id": f"eq.{opportunity_id}",
            "limit": "1",
        },
    )
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"opportunity not found: {opportunity_id}")
    return rows[0]


def fetch_source_dataset_for_row(row: dict[str, Any], *, apify_token: str) -> tuple[str, list[dict[str, Any]]]:
    proof = _opportunity_condition_proof_row(row)
    identity = proof.get("source_identity") or {}
    run_id = str(identity.get("actor_run_id") or identity.get("apify_run_id") or "").strip()
    if not run_id:
        raise RuntimeError("source trace requires actor_run_id/apify_run_id")

    run_payload = _apify_get(f"/actor-runs/{run_id}", apify_token)
    dataset_id = dataset_id_from_run_payload(run_payload)
    if not dataset_id:
        raise RuntimeError(f"unable to resolve dataset id for Apify run {run_id}")
    items = _apify_get(f"/datasets/{dataset_id}/items?clean=true&limit=1000", apify_token)
    if not isinstance(items, list):
        raise RuntimeError(f"dataset {dataset_id} payload is not a list")
    return dataset_id, items


def update_row(supabase_url: str, service_key: str, row_id: str) -> None:
    _request_json(
        supabase_url=supabase_url,
        service_key=service_key,
        method="PATCH",
        path="opportunities",
        params={"id": f"eq.{row_id}"},
        payload=rejection_payload(),
    )


def reconcile(
    *,
    apply: bool,
    limit: int,
    opportunity_id: str = "",
    apify_token: str = "",
) -> dict[str, Any]:
    supabase_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    source_trace_results: list[dict[str, Any]] = []
    if opportunity_id:
        row = fetch_opportunity_row(supabase_url, service_key, opportunity_id=opportunity_id)
        if not apify_token.strip():
            raise SystemExit("APIFY_TOKEN/APIFY_API_TOKEN is required for opportunity source tracing")
        dataset_id, dataset_items = fetch_source_dataset_for_row(row, apify_token=apify_token.strip())
        source_trace_result = is_recovered_source_condition_blocked_hot_row(
            row,
            dataset_items,
            dataset_id=dataset_id,
        )
        source_trace_results.append({
            "id": row.get("id"),
            "target": source_trace_result["target"],
            "reason": source_trace_result["reason"],
            "dataset_id": dataset_id,
            "source_trace_matched": (source_trace_result.get("trace") or {}).get("source_trace", {}).get("matched"),
            "recovered_condition_grade": (
                (source_trace_result.get("trace") or {})
                .get("recovered_source_condition")
                or {}
            ).get("condition_grade"),
            "recovered_condition_signals": (
                (source_trace_result.get("trace") or {})
                .get("recovered_source_condition")
                or {}
            ).get("condition_signals") or [],
            "recommendation_status": (
                (source_trace_result.get("trace") or {})
                .get("backfill_recommendation")
                or {}
            ).get("status"),
        })
        candidates = [row]
        targets = [row] if source_trace_result["target"] else []
    else:
        candidates = fetch_candidate_rows(supabase_url, service_key, limit=limit)
        targets = [row for row in candidates if is_explicit_condition_blocked_hot_row(row)]

    updated: list[str] = []
    errors: list[dict[str, str]] = []
    if apply:
        for row in targets:
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                errors.append({"id": "", "error": "missing id"})
                continue
            try:
                update_row(supabase_url, service_key, row_id)
                updated.append(row_id)
            except Exception as exc:
                errors.append({"id": row_id, "error": str(exc)})

    return {
        "status": "error" if errors else "ok",
        "mode": "apply" if apply else "dry_run",
        "candidate_rows": len(candidates),
        "target_rows": len(targets),
        "updated_rows": len(updated),
        "error_count": len(errors),
        "target_samples": [
            {
                "id": row.get("id"),
                "source_site": row.get("source_site"),
                "dos_score": row.get("dos_score") or row.get("score"),
                "investment_grade": row.get("investment_grade"),
                "condition_grade": row.get("condition_grade"),
                "condition_blocker_basis": _condition_blocker_basis(row),
            }
            for row in targets[:20]
        ],
        "source_trace_results": source_trace_results,
        "updated_ids": updated,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write reconciliation updates")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--opportunity-id", default="", help="single opportunity id to reconcile by recovered source trace")
    parser.add_argument("--apify-token", default=os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN") or "")
    args = parser.parse_args()
    result = reconcile(
        apply=args.apply,
        limit=args.limit,
        opportunity_id=args.opportunity_id,
        apify_token=args.apify_token,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
