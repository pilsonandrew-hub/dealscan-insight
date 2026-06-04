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

from webapp.routers.internal import _condition_blocker_basis

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


def update_row(supabase_url: str, service_key: str, row_id: str) -> None:
    _request_json(
        supabase_url=supabase_url,
        service_key=service_key,
        method="PATCH",
        path="opportunities",
        params={"id": f"eq.{row_id}"},
        payload=rejection_payload(),
    )


def reconcile(*, apply: bool, limit: int) -> dict[str, Any]:
    supabase_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
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
        "updated_ids": updated,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write reconciliation updates")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    result = reconcile(apply=args.apply, limit=args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
