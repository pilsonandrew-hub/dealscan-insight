"""DealerScope deal expiry sweeper.

Keeps lifecycle rules testable instead of hiding them inside workflow YAML.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.ingest.alert_gating import (
    UNKNOWN_OR_WEAK_CONDITION_GRADES,
    has_source_condition_evidence,
)
from supabase import create_client


def _fetch_ids(supabase: Any, filters: Iterable[Callable[[Any], Any]]) -> list[str]:
    rows = _fetch_rows(supabase, "id", filters)
    return [row["id"] for row in rows if row.get("id")]


def _fetch_rows(supabase: Any, select: str, filters: Iterable[Callable[[Any], Any]]) -> list[dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    filter_fns = tuple(filters)
    offset = 0
    page_size = 500
    while True:
        query = supabase.table("opportunities").select(select).order("id")
        for filter_fn in filter_fns:
            query = filter_fn(query)
        response = query.range(offset, offset + page_size - 1).execute()
        rows = response.data or []
        if not rows:
            break
        rows_all.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return rows_all


def _chunked(values: list[str], size: int = 200):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _condition_grade_requires_source_evidence(row: dict[str, Any]) -> bool:
    grade = str(row.get("condition_grade") or row.get("condition") or "").strip().lower()
    return grade not in UNKNOWN_OR_WEAK_CONDITION_GRADES


def _missing_source_condition_evidence_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    return _dedupe_preserving_order(
        str(row["id"])
        for row in rows
        if row.get("id")
        and _condition_grade_requires_source_evidence(row)
        and not has_source_condition_evidence(row)
    )


def _update_batches(supabase: Any, ids: list[str], payload: dict[str, Any]) -> int:
    count = 0
    for batch in _chunked(ids):
        supabase.table("opportunities").update(payload).in_("id", batch).execute()
        count += len(batch)
    return count


def _source_listing_id(row: dict[str, Any]) -> str | None:
    for key in ("source_listing_id", "listing_id", "external_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _build_post_close_outcome_request(row: dict[str, Any]) -> dict[str, Any] | None:
    source_site = row.get("source_site") or row.get("source")
    source_listing_id = _source_listing_id(row)
    listing_url = row.get("listing_url") or row.get("url")
    if not (source_site and source_listing_id and listing_url):
        return None
    return {
        "opportunity_id": row.get("id"),
        "source_site": str(source_site),
        "source_listing_id": source_listing_id,
        "listing_url": str(listing_url),
        "auction_end_date": row.get("auction_end_date"),
        "referral_source": "deal_expiry_sweeper",
        "referral_reason": "auction_expired",
        "outcome_status": "pending_outcome_check",
        "year": row.get("year"),
        "make": row.get("make"),
        "model": row.get("model"),
        "vin": row.get("vin"),
        "mileage": row.get("mileage"),
    }


def _upsert_post_close_outcome_requests(supabase: Any, rows: list[dict[str, Any]]) -> int:
    requests = [
        request
        for row in rows
        if (request := _build_post_close_outcome_request(row)) is not None
    ]
    if not requests:
        return 0
    supabase.table("post_close_outcome_requests").upsert(
        requests,
        on_conflict="source_site,source_listing_id",
        ignore_duplicates=True,
    ).execute()
    return len(requests)


def _truthy_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def build_message(summary: dict[str, Any]) -> str:
    dry_run_label = " <b>DRY RUN</b>" if summary.get("dry_run") else ""
    return (
        f"🧹 <b>DealerScope Deal Expiry Sweeper</b>{dry_run_label}\n\n"
        f"Expired deals: <b>{summary['expired']}</b>\n"
        "Post-close outcome referrals: "
        f"<b>{summary.get('post_close_outcome_requests', 0)}</b>\n"
        f"Archived passed deals: <b>{summary['archived_passed']}</b>\n"
        "Archived stale saved/inactive deals: "
        f"<b>{summary['archived_stale_saved_inactive']}</b>\n"
        "Archived active high-DOS missing-mileage deals: "
        f"<b>{summary['archived_untrusted_active_high_dos_missing_mileage']}</b>\n"
        "Archived active high-DOS missing-VIN deals: "
        f"<b>{summary['archived_untrusted_active_high_dos_missing_vin']}</b>\n"
        "Archived active high-DOS missing-condition-evidence deals: "
        f"<b>{summary['archived_untrusted_active_high_dos_missing_condition_evidence']}</b>\n"
        "Archived active rejected/low-DOS deals: "
        f"<b>{summary['archived_untrusted_active_rejected_or_low_dos']}</b>\n"
        f"Run time: {summary['run_time']}"
    )


def run_sweep(
    supabase: Any,
    *,
    now: _datetime.datetime | None = None,
    notify: Callable[[str], bool] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = now or _datetime.datetime.now(_datetime.timezone.utc)
    expired_cutoff = (now - _datetime.timedelta(hours=24)).isoformat()
    archive_cutoff = (now - _datetime.timedelta(days=7)).isoformat()

    expired_filters = [
        lambda q: q.lt("auction_end_date", expired_cutoff),
        lambda q: q.neq("pipeline_step", "expired"),
        lambda q: q.eq("is_active", True),
    ]
    expired_rows = _fetch_rows(
        supabase,
        "id,source_site,listing_id,listing_url,auction_end_date,year,make,model,vin,mileage",
        expired_filters,
    )
    expired_ids = [row["id"] for row in expired_rows if row.get("id")]
    archived_passed_ids = _fetch_ids(
        supabase,
        [
            lambda q: q.eq("pipeline_step", "passed"),
            lambda q: q.lt("updated_at", archive_cutoff),
        ],
    )
    stale_saved_inactive_ids = _fetch_ids(
        supabase,
        [
            lambda q: q.eq("pipeline_step", "saved"),
            lambda q: q.eq("is_active", False),
            lambda q: q.lt("updated_at", archive_cutoff),
        ],
    )
    active_high_dos_missing_mileage_ids = _dedupe_preserving_order([
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.gte("dos_score", 80),
                lambda q: q.is_("mileage", "null"),
            ],
        ),
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.gte("dos_score", 80),
                lambda q: q.lte("mileage", 0),
            ],
        ),
    ])
    active_high_dos_missing_vin_ids = _dedupe_preserving_order([
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.gte("dos_score", 80),
                lambda q: q.is_("vin", "null"),
            ],
        ),
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.gte("dos_score", 80),
                lambda q: q.eq("vin", ""),
            ],
        ),
    ])
    active_high_dos_rows = _fetch_rows(
        supabase,
        "id,title,condition_grade,raw_data",
        [
            lambda q: q.eq("is_active", True),
            lambda q: q.gte("dos_score", 80),
        ],
    )
    active_high_dos_missing_condition_evidence_ids = _missing_source_condition_evidence_ids(
        active_high_dos_rows
    )
    active_rejected_or_low_dos_ids = _dedupe_preserving_order([
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.lt("dos_score", 50),
            ],
        ),
        *_fetch_ids(
            supabase,
            [
                lambda q: q.eq("is_active", True),
                lambda q: q.eq("investment_grade", "Rejected"),
            ],
        ),
    ])

    post_close_request_count = (
        len([
            request
            for row in expired_rows
            if (request := _build_post_close_outcome_request(row)) is not None
        ])
        if dry_run
        else _upsert_post_close_outcome_requests(supabase, expired_rows)
    )

    summary = {
        "dry_run": dry_run,
        "post_close_outcome_requests": post_close_request_count,
        "expired": len(expired_ids) if dry_run else _update_batches(
            supabase,
            expired_ids,
            {"is_active": False, "pipeline_step": "expired"},
        ),
        "archived_passed": len(archived_passed_ids) if dry_run else _update_batches(
            supabase,
            archived_passed_ids,
            {"pipeline_step": "archived"},
        ),
        "archived_stale_saved_inactive": len(stale_saved_inactive_ids) if dry_run else _update_batches(
            supabase,
            stale_saved_inactive_ids,
            {"pipeline_step": "archived"},
        ),
        "archived_untrusted_active_high_dos_missing_mileage": len(active_high_dos_missing_mileage_ids)
        if dry_run
        else _update_batches(
            supabase,
            active_high_dos_missing_mileage_ids,
            {
                "is_active": False,
                "pipeline_step": "archived",
                "step_status": "q_no_mileage",
            },
        ),
        "archived_untrusted_active_high_dos_missing_vin": len(active_high_dos_missing_vin_ids)
        if dry_run
        else _update_batches(
            supabase,
            active_high_dos_missing_vin_ids,
            {
                "is_active": False,
                "pipeline_step": "archived",
                "step_status": "q_no_vin",
            },
        ),
        "archived_untrusted_active_high_dos_missing_condition_evidence": len(
            active_high_dos_missing_condition_evidence_ids
        )
        if dry_run
        else _update_batches(
            supabase,
            active_high_dos_missing_condition_evidence_ids,
            {
                "is_active": False,
                "pipeline_step": "archived",
                "step_status": "q_no_cond_ev",
            },
        ),
        "archived_untrusted_active_rejected_or_low_dos": len(active_rejected_or_low_dos_ids)
        if dry_run
        else _update_batches(
            supabase,
            active_rejected_or_low_dos_ids,
            {
                "is_active": False,
                "pipeline_step": "archived",
                "step_status": "q_rejected",
            },
        ),
        "run_time": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

    if notify:
        summary["notification_ok"] = notify(build_message(summary))
    return summary


def _send_telegram(text: str) -> bool:
    bot_token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context()) as resp:
        json.loads(resp.read())
    print("Telegram notification sent")
    return True


def _safe_send_telegram(text: str) -> bool:
    try:
        return _send_telegram(text)
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")
        return False


def main() -> int:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    summary = run_sweep(
        supabase,
        notify=_safe_send_telegram,
        dry_run=_truthy_env(os.environ.get("DEAL_EXPIRY_SWEEPER_DRY_RUN")),
    )
    print(build_message(summary).replace("<b>", "").replace("</b>", ""))
    if not summary.get("notification_ok", True):
        print(
            "Sweep completed, but Telegram delivery failed; "
            "investigate TELEGRAM_BOT_TOKEN / chat permissions."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
