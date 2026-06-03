#!/usr/bin/env python3
"""Read-only trace from an exact opportunity condition proof to Apify source text."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ingest.condition import score_condition


APIFY_BASE_URL = "https://api.apify.com/v2"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _norm_url(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    parsed = urllib_parse.urlsplit(text)
    path = parsed.path.rstrip("/")
    return urllib_parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", _clean_text(value))


def _item_text(item: dict[str, Any], keys: Iterable[str]) -> str:
    return " ".join(_clean_text(item.get(key)) for key in keys if _clean_text(item.get(key)))


def _item_urls(item: dict[str, Any]) -> set[str]:
    keys = ("listing_url", "url", "source_url", "detail_url", "asset_url")
    return {_norm_url(item.get(key)) for key in keys if _norm_url(item.get(key))}


def _item_listing_ids(item: dict[str, Any]) -> set[str]:
    keys = ("listing_id", "asset_id", "assetId", "id", "lot_id", "lotId")
    return {_clean_text(item.get(key)) for key in keys if _clean_text(item.get(key))}


def select_dataset_item(items: list[dict[str, Any]], source_identity: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return the dataset item most likely to represent the stored opportunity."""
    expected_url = _norm_url(source_identity.get("listing_url"))
    expected_listing_id = _clean_text(source_identity.get("listing_id"))
    expected_vin_suffix = _clean_text(source_identity.get("vin_suffix")).upper()

    best_item: Optional[dict[str, Any]] = None
    best_score = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        score = 0
        if expected_url and expected_url in _item_urls(item):
            score += 100
        if expected_listing_id and expected_listing_id in _item_listing_ids(item):
            score += 60
        if expected_vin_suffix:
            vin_text = _item_text(item, ("vin", "VIN", "detail_text", "description", "details")).upper()
            if expected_vin_suffix in vin_text:
                score += 40
        if score > best_score:
            best_score = score
            best_item = item

    return best_item if best_score > 0 else None


def _evidence_field_summary(item: Optional[dict[str, Any]], title: str) -> dict[str, dict[str, Any]]:
    fields = ("description", "details", "detail_text", "condition_notes", "assetLongDesc", "damage_type", "damage")
    summary: dict[str, dict[str, Any]] = {}
    title_norm = _clean_text(title).lower()
    for key in fields:
        value = _clean_text((item or {}).get(key))
        summary[key] = {
            "present": bool(value),
            "length": len(value),
            "matches_title": bool(value and title_norm and value.lower() == title_norm),
        }
    return summary


def _score_recovered_item(item: dict[str, Any], opportunity: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(item.get("title") or opportunity.get("title"))
    description = _item_text(
        item,
        (
            "description",
            "details",
            "detail_text",
            "condition_notes",
            "assetLongDesc",
            "raw_description",
        ),
    )
    mileage = item.get("mileage") or item.get("odometer") or opportunity.get("mileage") or 0
    year = item.get("year") or opportunity.get("year") or 0
    damage_type = _item_text(item, ("damage_type", "damage", "title_status"))
    vin = _clean_text(item.get("vin") or item.get("VIN"))

    result = score_condition(
        title=title,
        description=description,
        mileage=mileage,
        year=year,
        damage_type=damage_type,
        vin=vin,
    )
    return {
        "condition_grade": result.get("condition_grade"),
        "condition_score": result.get("condition_score"),
        "condition_signals": result.get("condition_signals") or [],
        "source_text_excerpt": (f"{title} {description}").strip()[:240],
    }


def _backfill_recommendation(
    *,
    matched_item: Optional[dict[str, Any]],
    recovered_condition: Optional[dict[str, Any]],
) -> dict[str, Any]:
    if not matched_item:
        return {"status": "blocked_no_matching_source_item", "mutate_row": False}

    grade = _clean_text((recovered_condition or {}).get("condition_grade")).upper()
    signals = {str(signal).lower() for signal in (recovered_condition or {}).get("condition_signals") or []}
    negative_signals = {
        "as-is",
        "as is",
        "salvage",
        "flood",
        "fire damage",
        "frame damage",
        "no start",
        "needs work",
        "parts only",
        "wrecked",
        "open manufacturer recall",
        "remedy not yet available",
        "engine performance concerns",
        "major components missing",
        "repairs required",
        "check engine",
    }
    if grade in {"D", "F"} or signals & negative_signals:
        return {"status": "blocked_recovered_source_still_condition_negative", "mutate_row": False}

    return {"status": "review_required_recovered_source_not_negative", "mutate_row": False}


def build_source_evidence_trace(
    condition_proof: dict[str, Any],
    dataset_items: list[dict[str, Any]],
    *,
    dataset_id: Optional[str] = None,
) -> dict[str, Any]:
    opportunity = condition_proof.get("opportunity") or {}
    source_identity = opportunity.get("source_identity") or {}
    matched_item = select_dataset_item(dataset_items, source_identity)
    recovered_condition = _score_recovered_item(matched_item, opportunity) if matched_item else None

    return {
        "selector": condition_proof.get("selector"),
        "stored_opportunity": {
            "id": opportunity.get("id"),
            "source_site": opportunity.get("source_site"),
            "title": opportunity.get("title"),
            "year": opportunity.get("year"),
            "mileage": opportunity.get("mileage"),
            "condition_grade": opportunity.get("condition_grade"),
            "condition_blocker_basis": opportunity.get("condition_blocker_basis"),
            "condition_signals": opportunity.get("condition_signals") or [],
            "condition_backfill_assessment": opportunity.get("condition_backfill_assessment"),
            "source_identity": source_identity,
        },
        "source_trace": {
            "dataset_id": dataset_id,
            "dataset_items_sampled": len(dataset_items),
            "matched": bool(matched_item),
            "match_keys": {
                "listing_url": source_identity.get("listing_url"),
                "listing_id": source_identity.get("listing_id"),
                "vin_suffix": source_identity.get("vin_suffix"),
            },
            "source_evidence_fields": _evidence_field_summary(matched_item, opportunity.get("title") or ""),
        },
        "recovered_source_condition": recovered_condition,
        "backfill_recommendation": _backfill_recommendation(
            matched_item=matched_item,
            recovered_condition=recovered_condition,
        ),
    }


def _apify_get(path: str, token: str) -> Any:
    separator = "&" if "?" in path else "?"
    url = f"{APIFY_BASE_URL}{path}{separator}token={urllib_parse.quote(token)}"
    req = urllib_request.Request(url)
    try:
        with urllib_request.urlopen(req, timeout=45) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib_error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Apify HTTP {exc.code} for {path}: {body}") from exc


def _load_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition-proof-json", required=True, help="Path to exact condition proof JSON.")
    parser.add_argument("--dataset-items-json", help="Optional offline Apify dataset items JSON.")
    parser.add_argument("--dataset-id", help="Optional Apify dataset id. Resolved from --run-id when omitted.")
    parser.add_argument("--run-id", help="Optional Apify run id used to resolve dataset id.")
    parser.add_argument("--apify-token", default=os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN") or "")
    args = parser.parse_args(argv)

    condition_proof = _load_json_file(args.condition_proof_json)
    dataset_id = args.dataset_id

    if args.dataset_items_json:
        dataset_items = _load_json_file(args.dataset_items_json)
    else:
        token = args.apify_token.strip()
        if not token:
            print("APIFY_TOKEN/APIFY_API_TOKEN is required unless --dataset-items-json is provided.", file=sys.stderr)
            return 2
        if not dataset_id:
            run_id = args.run_id or (
                (condition_proof.get("opportunity") or {})
                .get("source_identity", {})
                .get("actor_run_id")
            )
            if not run_id:
                print("No dataset id or run id available for Apify source trace.", file=sys.stderr)
                return 2
            run_payload = _apify_get(f"/actor-runs/{run_id}", token)
            dataset_id = run_payload.get("defaultDatasetId")
        if not dataset_id:
            print("Unable to resolve Apify dataset id.", file=sys.stderr)
            return 2
        dataset_items = _apify_get(f"/datasets/{dataset_id}/items?clean=true&limit=1000", token)

    if not isinstance(dataset_items, list):
        print("Dataset items payload must be a JSON list.", file=sys.stderr)
        return 2

    trace = build_source_evidence_trace(condition_proof, dataset_items, dataset_id=dataset_id)
    print(json.dumps(trace, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
