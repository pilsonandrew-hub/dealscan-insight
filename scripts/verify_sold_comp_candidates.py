#!/usr/bin/env python3
"""Deterministic verifier helpers for Comp Evidence Ledger candidates.

This module intentionally separates judgment from persistence. The verifier
can build review rows and verified-comp rows, but callers decide when to write
them to Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


APPROVED_VEHICLE_MODELS = {
    ("ford", "f-150"),
    ("ford", "f150"),
    ("ford", "f-250"),
    ("ford", "f250"),
    ("chevrolet", "silverado 1500"),
    ("chevy", "silverado 1500"),
    ("chevrolet", "silverado 2500"),
    ("chevy", "silverado 2500"),
    ("ram", "1500"),
    ("ram", "2500"),
}


@dataclass(frozen=True)
class VerificationDecision:
    review_status: str
    rejection_reason: str | None
    human_required: bool
    deterministic_checks: dict[str, Any]
    completion_confidence: float
    price_confidence: float
    identity_confidence: float
    overall_verification_confidence: float


def _present(value: Any) -> bool:
    return value not in (None, "")


def _numeric(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _valid_vin(vin: Any) -> bool:
    if not vin:
        return True
    text = str(vin).strip().upper()
    return len(text) == 17 and text.isalnum() and not any(char in text for char in "IOQ")


def _source_listing_key(candidate: dict[str, Any]) -> str:
    return f"{candidate.get('source_name')}:{candidate.get('source_listing_id')}"


def _approved_vehicle_scope(candidate: dict[str, Any]) -> bool:
    make = str(candidate.get("make") or "").strip().lower()
    model = str(candidate.get("model") or "").strip().lower()
    if (make, model) in APPROVED_VEHICLE_MODELS:
        return True
    if make == "ford" and model.replace("-", "") in {"f150", "f250"}:
        return True
    if make in {"chevrolet", "chevy"} and model.startswith("silverado"):
        return model in {"silverado 1500", "silverado 2500"}
    return False


def evaluate_candidate(
    candidate: dict[str, Any],
    *,
    today: date | None = None,
    existing_verified_source_listing_ids: set[str] | None = None,
) -> VerificationDecision:
    today = today or date.today()
    existing_verified_source_listing_ids = existing_verified_source_listing_ids or set()
    sale_date = _parse_date(candidate.get("sale_date"))
    price = _numeric(candidate.get("sold_price_all_in") or candidate.get("sold_price_hammer"))
    required_identity_present = all(_present(candidate.get(key)) for key in ("year", "make", "model"))
    duplicate_source_listing = _source_listing_key(candidate) in existing_verified_source_listing_ids
    checks = {
        "candidate_not_pre_rejected": candidate.get("candidate_status") != "rejected",
        "listing_url_present": _present(candidate.get("listing_url")),
        "evidence_ref_present": _present(candidate.get("evidence_ref")),
        "sale_date_parseable": sale_date is not None,
        "sale_date_not_future": sale_date is not None and sale_date <= today,
        "price_present": price is not None,
        "price_plausible": price is not None and 500 < price < 200000,
        "required_identity_present": required_identity_present,
        "valid_vin": _valid_vin(candidate.get("vin")),
        "duplicate_source_listing": duplicate_source_listing,
        "approved_vehicle_scope": _approved_vehicle_scope(candidate),
    }

    if candidate.get("candidate_status") == "rejected":
        deterministic_rejection = candidate.get("rejection_reason") or "pre_rejected_missing_reason"
        return _decision("rejected", str(deterministic_rejection), False, checks)
    if duplicate_source_listing:
        return _decision("rejected", "duplicate_source_listing", False, checks)
    if not checks["listing_url_present"]:
        return _decision("rejected", "missing_listing_url", False, checks)
    if not checks["evidence_ref_present"]:
        return _decision("rejected", "missing_evidence_ref", False, checks)
    if not checks["sale_date_parseable"] or not checks["sale_date_not_future"]:
        return _decision("rejected", "invalid_sale_date", False, checks)
    if not checks["price_present"] or not checks["price_plausible"]:
        return _decision("rejected", "implausible_price", False, checks)
    if not checks["required_identity_present"]:
        return _decision("rejected", "missing_year_make_model", False, checks)
    if not checks["valid_vin"]:
        return _decision("rejected", "invalid_vin", False, checks)
    if not checks["approved_vehicle_scope"]:
        return _decision("needs_review", "outside_approved_vehicle_scope", True, checks)
    return _decision("accepted", None, False, checks)


def _decision(
    review_status: str,
    rejection_reason: str | None,
    human_required: bool,
    checks: dict[str, Any],
) -> VerificationDecision:
    accepted = review_status == "accepted"
    return VerificationDecision(
        review_status=review_status,
        rejection_reason=rejection_reason,
        human_required=human_required,
        deterministic_checks=checks,
        completion_confidence=1.0 if accepted else 0.0,
        price_confidence=1.0 if checks.get("price_plausible") else 0.0,
        identity_confidence=1.0 if checks.get("required_identity_present") and checks.get("valid_vin") else 0.0,
        overall_verification_confidence=1.0 if accepted else 0.0,
    )


def build_review_row(
    candidate: dict[str, Any],
    decision: VerificationDecision,
    *,
    reviewer: str,
    reviewer_version: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate["id"],
        "run_id": candidate["run_id"],
        "reviewer": reviewer,
        "reviewer_version": reviewer_version,
        "review_status": decision.review_status,
        "rejection_reason": decision.rejection_reason,
        "review_notes": None,
        "completion_confidence": decision.completion_confidence,
        "price_confidence": decision.price_confidence,
        "identity_confidence": decision.identity_confidence,
        "condition_confidence": None,
        "mileage_confidence": 1.0 if _present(candidate.get("mileage")) else 0.0,
        "overall_verification_confidence": decision.overall_verification_confidence,
        "deterministic_checks": decision.deterministic_checks,
        "llm_enrichment": {},
        "human_required": decision.human_required,
    }


def build_verified_comp_row(
    candidate: dict[str, Any],
    decision: VerificationDecision,
    *,
    verifier_version: str,
) -> dict[str, Any] | None:
    if decision.review_status != "accepted":
        return None
    sold_price_all_in = candidate.get("sold_price_all_in") or candidate.get("sold_price_hammer")
    return {
        "candidate_id": candidate["id"],
        "source_name": candidate["source_name"],
        "source_listing_id": candidate["source_listing_id"],
        "listing_url": candidate["listing_url"],
        "evidence_ref": candidate["evidence_ref"],
        "sale_date": candidate["sale_date"],
        "sold_price_hammer": candidate.get("sold_price_hammer"),
        "buyer_premium": candidate.get("buyer_premium"),
        "fees": candidate.get("fees"),
        "sold_price_all_in": sold_price_all_in,
        "price_basis": candidate.get("price_basis") or "source_reported",
        "currency": candidate.get("currency") or "USD",
        "year": candidate["year"],
        "make": candidate["make"],
        "model": candidate["model"],
        "trim": candidate.get("trim"),
        "vin": candidate.get("vin"),
        "mileage": candidate.get("mileage"),
        "title_brand_status": candidate.get("title_brand_status"),
        "condition_text": candidate.get("condition_text"),
        "defect_signals": candidate.get("defect_signals"),
        "location_city": candidate.get("location_city"),
        "location_state": candidate.get("location_state"),
        "region": candidate.get("region"),
        "channel": candidate["channel"],
        "normalized_make": str(candidate["make"]).strip(),
        "normalized_model": str(candidate["model"]).strip(),
        "normalized_trim": candidate.get("trim"),
        "dedup_key": candidate["dedup_key"],
        "extractor_version": candidate["extractor_version"],
        "verifier_version": verifier_version,
        "source_policy_version": candidate["source_policy_version"],
        "verification_metadata": {"deterministic_checks": decision.deterministic_checks},
    }
