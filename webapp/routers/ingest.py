"""
Apify webhook ingest router.
Normalizes, gates, scores, and saves vehicle listings to Supabase.

Fixes applied (2026-03-11):
- Real DOS formula via backend.ingest.score.score_deal()
- MMR estimates by segment (placeholder until Manheim API is live)
- extract_model() now uses regex
- Age gate tightened to 4 years (SOP compliance)
- Mileage gate added (50k max)
- Bid range tightened ($3k-$35k)
- APIFY_TOKEN sent via Authorization header (not query param)
- 500 errors genericized (no internal details leaked)
- Telegram hot deal alerts wired
- Dataset ID format validated before fetch
"""
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Any, Optional
import hmac
import hashlib
import re
import os
import logging
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import extras as psycopg2_extras
from psycopg2 import sql as psycopg2_sql

from backend.ingest.webhook_secret_posture import build_webhook_secret_posture
from backend.ingest.alert_gating import evaluate_alert_gate
from backend.ingest.alert_thresholds import build_alert_thresholds, hot_deal_min_score
from backend.ingest.apify_metadata import extract_apify_webhook_metadata
from backend.ingest.config_loader import get_config
from backend.ingest.fallback_score import build_fallback_score
from backend.business_rules.constants import (
    ALERTS_ENABLED_PRODUCTION_DEFAULT,
    DOS_SAVE_THRESHOLD,
    HIGH_RUST_STATES,
)
from backend.business_rules.gates import (
    bid_ceiling_pct_for_tier,
    min_margin_for_tier,
    passes_ingest_margin_floor,
)
from backend.ingest.telegram_auth import resolve_operator_user_id, verify_telegram_secret_header
from backend.ingest.tavily_enrichment import apply_tavily_enrichment
from backend.ingest.gates import (
    LOW_RUST_STATES,
    TARGET_STATES,
    US_STATES,
    find_title_brand_issue as _find_title_brand_issue,
    is_commercial_hd_tonnage as _is_commercial_hd_tonnage,
    passes_basic_gates as _passes_basic_gates,
)
from backend.ingest.listing_identity import compute_listing_id as _compute_listing_id
from backend.ingest.audit_state import (
    AUDIT_FALLBACK_MARKER,
    CriticalAuditWriteError,
    attach_audit_state,
    audit_fallbacks,
    format_audit_failure,
    format_ingest_run_summary,
    increment_reason_counter,
    merge_audit_error_message,
    record_audit_fallback,
)
from backend.ingest.alert_validation import (
    alert_validation_mmr_estimate,
    build_alert_validation_prompt,
)
from backend.ingest.delivery_log import (
    build_delivery_log_insert_row,
    build_delivery_log_row,
    build_delivery_log_update_row,
)
from backend.ingest.db_url import derive_supabase_direct_db_url
from backend.ingest.direct_pg import prepare_direct_pg_value
from backend.ingest.canonical_identity import (
    MAKE_ALIASES,
    build_duplicate_recovery_payload,
    compute_canonical_id,
    is_canonical_unique_conflict,
    normalize_make_for_identity as _normalize_make,
    normalize_model_for_identity as _normalize_model,
)
from backend.ingest.pre_save_skip import build_pre_save_skip_delivery_log_kwargs
from backend.ingest.openrouter_routing import (
    DEFAULT_OPENROUTER_LANE_MODEL_PAIRS,
    legacy_deepseek_fallback_enabled,
    legacy_defaulting_enabled,
    normalize_openrouter_route_value,
    resolve_openrouter_lane_model,
)
from backend.ingest.opportunity_row import build_opportunity_row as _build_opportunity_row
from backend.ingest.raw_item_identity import raw_item_identity
from backend.ingest.save_outcome import mark_save_outcome
from backend.ingest.service_config import (
    resolve_apify_api_token,
    resolve_app_public_url,
    resolve_rover_actions_base_url,
)
from backend.ingest.webhook_replay import select_recent_replay_row
from backend.ingest.sonar_listings import build_sonar_listing_row
from backend.ingest.telegram_alerts import (
    build_telegram_alert_message,
    build_telegram_reply_markup,
    clean_bid_direct_url,
    redact_telegram_bot_token,
)
from backend.ingest.webhook_security import (
    configured_webhook_secret_entries,
    match_webhook_secret,
    request_client_ip_for_security_log,
    stale_webhook_error,
    verify_webhook_secret,
    webhook_max_age_seconds,
    webhook_replay_window_seconds,
)
from backend.ingest.vin_dedup import check_vin_duplicate, normalize_vin
from backend.ingest.time_utils import (
    normalize_auction_end_time as _normalize_auction_end_time,
    parse_datetime_utc as _parse_datetime_utc,
)
from backend.ingest.vehicle_identity import (
    extract_make,
    extract_model,
    extract_year,
    estimate_mmr as _estimate_mmr,
    estimate_mmr_details as _estimate_mmr_details,
)
from backend.ingest.source_site import (
    SOURCE_SITE_ALIASES as _SOURCE_SITE_ALIASES,
    SOURCE_SITE_URL_HINTS as _SOURCE_SITE_URL_HINTS,
    canonical_source_site as _canonical_source_site,
    infer_source_site as _infer_source_site,
    source_site_from_url as _source_site_from_url,
)
from backend.ingest.supabase_config import resolve_supabase_ingest_config

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
telegram_router = APIRouter(prefix="/api/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

try:
    from backend.ingest.condition import compute_condition_grade as _compute_condition_grade
except ImportError:
    def _compute_condition_grade(**kwargs):  # type: ignore[misc]
        return None

import time as _time

alerts_this_run: dict[str, int] = {}
alerts_this_run_ts: dict[str, float] = {}


def _alert_thresholds():
    return build_alert_thresholds(os.environ, log=logger)

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "").strip()
WEBHOOK_SECRET_PREVIOUS = os.getenv("APIFY_WEBHOOK_SECRET_PREVIOUS", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


OPENROUTER_API_KEY = (get_config("OPENROUTER_API_KEY") or "").strip()
# DeepSeek direct API (legacy fallback only if explicitly enabled)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
OPENROUTER_LANE_MODEL_PAIRS = DEFAULT_OPENROUTER_LANE_MODEL_PAIRS
# ALERT CONTROL PLANE: FastAPI -> Telegram directly
# Decision: 2026-03-11, keep FastAPI direct, not OpenClaw messaging
# Reason: already deployed, working, single path

_supabase_config = resolve_supabase_ingest_config(os.environ)
_supabase_url = _supabase_config.url
_supabase_service_role_key = _supabase_config.service_role_key
_supabase_anon_key = _supabase_config.anon_key
_environment = _supabase_config.environment
_APP_PUBLIC_URL = resolve_app_public_url(os.environ)
_supabase_key = _supabase_config.key
if _supabase_config.message:
    if _supabase_config.severity == "critical":
        logger.critical(_supabase_config.message)
    else:
        logger.warning(_supabase_config.message)

supabase_client = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supabase_client = create_client(_supabase_url, _supabase_key)
        logger.info("Supabase client initialized for ingest")
    else:
        logger.warning("Supabase client NOT initialized — missing env vars.")
except Exception as _supa_err:
    logger.warning(f"Supabase client init failed (non-fatal): {_supa_err}")


def _apify_api_token() -> str:
    return resolve_apify_api_token(os.environ)


def _normalize_openrouter_route_value(value: Any) -> str:
    return normalize_openrouter_route_value(value)


def _openrouter_legacy_defaulting_enabled() -> bool:
    return legacy_defaulting_enabled(os.environ)


def _openrouter_legacy_deepseek_fallback_enabled() -> bool:
    return legacy_deepseek_fallback_enabled(os.environ)


def _resolve_openrouter_lane_model(deal: dict[str, Any], deal_id: str) -> tuple[str, str]:
    missing_lane = not _normalize_openrouter_route_value(deal.get("designated_lane"))
    lane, model = resolve_openrouter_lane_model(
        deal,
        lane_model_pairs=OPENROUTER_LANE_MODEL_PAIRS,
        legacy_defaulting=_openrouter_legacy_defaulting_enabled(),
        legacy_default_lane=os.getenv("OPENROUTER_LEGACY_DEFAULT_LANE", "premium"),
    )
    if missing_lane:
        logger.warning(
            "[AI_VALIDATE] deal_id=%s missing designated_lane; using legacy default lane=%s",
            deal_id,
            lane or "unknown",
        )
    return lane, model


def _derive_supabase_direct_db_url() -> Optional[str]:
    return derive_supabase_direct_db_url(os.environ)


_direct_supabase_db_url = _derive_supabase_direct_db_url()

# Ingest gate constants and title/commercial checks are imported from backend.ingest.gates.


# Vehicle identity and proxy MMR helpers are imported from backend.ingest.vehicle_identity.


# Canonical identity helpers are imported from backend.ingest.canonical_identity
# so the pure dedup key behavior is testable outside this router.


# Title-brand issue detection is imported from backend.ingest.gates.


def check_and_handle_duplicate(supabase_client, vehicle: dict) -> dict:
    if supabase_client is None:
        return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

    canonical_id = vehicle.get("canonical_id", "")
    new_source = vehicle.get("source_site", "")
    listing_url = vehicle.get("listing_url", "")

    try:
        if listing_url:
            existing = (
                supabase_client.table("opportunities")
                .select("id, is_duplicate, canonical_record_id")
                .eq("listing_url", listing_url)
                .limit(1)
                .execute()
            )
            if existing.data:
                existing_row = existing.data[0]
                return {
                    "is_duplicate": existing_row.get("is_duplicate", False),
                    "canonical_record_id": existing_row.get("canonical_record_id"),
                    "canonical_update": None,
                }

        if not canonical_id:
            return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

        result = (
            supabase_client.table("opportunities")
            .select("id, all_sources")
            .eq("canonical_id", canonical_id)
            .eq("is_duplicate", False)
            .limit(1)
            .execute()
        )
        if not result.data:
            return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

        existing = result.data[0]
        existing_id = existing["id"]
        existing_sources = existing.get("all_sources") or []
        canonical_update = None
        if new_source and new_source not in existing_sources:
            updated = existing_sources + [new_source]
            canonical_update = {
                "id": existing_id,
                "all_sources": updated,
                "duplicate_count": len(updated) - 1,
            }
        return {"is_duplicate": True, "canonical_record_id": existing_id, "canonical_update": canonical_update}
    except Exception as lookup_error:
        logger.warning(f"[DEDUP] check failed: {lookup_error}")
        raise


# Datetime parsing helpers are imported from backend.ingest.time_utils.


def insert_webhook_log(
    payload: dict,
    *,
    processing_status: str = "pending",
    error_message: Optional[str] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    metadata = extract_apify_webhook_metadata(payload)
    row = {
        "source": metadata["source"],
        "actor_id": metadata["actor_id"],
        "run_id": metadata["run_id"],
        "item_count": metadata["item_count"],
        "raw_payload": payload,
        "processing_status": processing_status,
        "error_message": error_message,
    }
    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            result = supabase_client.table("webhook_log").insert(row).execute()
            if result.data:
                return result.data[0].get("id")
        except Exception as exc:
            primary_error = exc

    try:
        fallback_label = "webhook_log_insert_direct_pg"
        fallback_row = dict(row)
        fallback_row["error_message"] = merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        inserted_id = _insert_webhook_log_direct_pg(fallback_row)
        record_audit_fallback(audit_state, fallback_label)
        return inserted_id
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                format_audit_failure(
                    surface="webhook_log",
                    operation="insert",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[WEBHOOK_LOG] insert failed: %s", primary_error)
        logger.warning("[WEBHOOK_LOG] direct PG fallback failed: %s", fallback_error)
        return None


def update_webhook_log(
    webhook_log_id: Optional[str],
    processing_status: str,
    *,
    error_message: Optional[str] = None,
    item_count: Optional[int] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> None:
    if not webhook_log_id:
        if require_durable:
            raise CriticalAuditWriteError("critical webhook_log update missing row id")
        return

    update_row = {
        "processing_status": processing_status,
        "error_message": error_message,
    }
    if item_count is not None:
        update_row["item_count"] = item_count

    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            supabase_client.table("webhook_log").update(update_row).eq("id", webhook_log_id).execute()
            return
        except Exception as exc:
            primary_error = exc

    try:
        fallback_label = "webhook_log_update_direct_pg"
        fallback_row = dict(update_row)
        fallback_row["error_message"] = merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        _update_webhook_log_direct_pg(webhook_log_id, fallback_row)
        record_audit_fallback(audit_state, fallback_label)
        return
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                format_audit_failure(
                    surface="webhook_log",
                    operation="update",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[WEBHOOK_LOG] update failed: %s", primary_error)
        logger.warning("[WEBHOOK_LOG] direct PG update fallback failed: %s", fallback_error)


def _configured_webhook_secret_entries() -> tuple[tuple[str, str], ...]:
    return configured_webhook_secret_entries(WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS)


def _webhook_secret_posture() -> dict[str, Any]:
    return build_webhook_secret_posture(WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS)


def _match_webhook_secret(presented_secret: Optional[str]) -> Optional[str]:
    return match_webhook_secret(presented_secret, WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS)


def _verify_webhook_secret(presented_secret: Optional[str]) -> bool:
    """Return True only if presented secret matches a configured entry AND the
    current (active) secret is actually set.  A previous/rotation secret alone
    is not sufficient when no active secret exists — that would mean we have no
    rotation baseline and any prior-round secret would be accepted forever."""
    return verify_webhook_secret(presented_secret, WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS)


def _webhook_replay_window_seconds() -> int:
    return webhook_replay_window_seconds()


def _webhook_max_age_seconds() -> int:
    return webhook_max_age_seconds()


def _claim_webhook_log(
    payload: dict,
    *,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[dict]]:
    """Atomically claim one Apify run for processing.

    The normal replay lookup is intentionally still available for stale/replay
    bookkeeping, but the processing path needs a single-flight claim: duplicate
    Apify webhooks can arrive at the same time and both see no processed row.
    When direct Postgres is available, use a transaction-scoped advisory lock on
    the Apify run_id to serialize lookup+pending insert.  If direct Postgres is
    unavailable, fall back to the existing durable insert path plus the stricter
    pending/processed replay check.
    """
    metadata = extract_apify_webhook_metadata(payload)
    run_id = metadata["run_id"]
    if _direct_supabase_db_url and run_id:
        try:
            return _claim_webhook_log_direct_pg(payload, audit_state=audit_state)
        except Exception as direct_error:
            logger.warning(
                "[INGEST_AUDIT] direct PG webhook claim failed for run_id=%s; "
                "falling back to Supabase REST when available: %s",
                run_id,
                direct_error,
            )
            record_audit_fallback(audit_state, "webhook_log_claim_direct_pg_unavailable")
            if supabase_client is None and require_durable:
                raise CriticalAuditWriteError(
                    format_audit_failure(
                        surface="webhook_log",
                        operation="claim",
                        primary_error=None,
                        fallback_error=direct_error,
                    )
                ) from direct_error

    recent_replay = _find_recent_webhook_replay(
        run_id,
        strict=require_durable,
        audit_state=audit_state,
    )
    if recent_replay:
        return None, recent_replay
    return (
        insert_webhook_log(
            payload,
            require_durable=require_durable,
            audit_state=audit_state,
        ),
        None,
    )


def _claim_webhook_log_direct_pg(
    payload: dict,
    *,
    audit_state: Optional[dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[dict]]:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    metadata = extract_apify_webhook_metadata(payload)
    run_id = metadata["run_id"]
    if not run_id:
        return insert_webhook_log(payload, require_durable=True, audit_state=audit_state), None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_webhook_replay_window_seconds())
    row = {
        "source": metadata["source"],
        "actor_id": metadata["actor_id"],
        "run_id": run_id,
        "item_count": metadata["item_count"],
        "raw_payload": payload,
        "processing_status": "pending",
        "error_message": None,
    }
    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
            cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (run_id,))
            cur.execute(
                """
                select id, received_at, processing_status, error_message, run_id
                from public.webhook_log
                where run_id = %s
                  and received_at >= %s
                order by received_at desc
                limit 5
                """,
                (run_id, cutoff),
            )
            recent_replay = select_recent_replay_row([dict(item) for item in cur.fetchall()])
            if recent_replay:
                record_audit_fallback(audit_state, "webhook_log_claim_direct_pg")
                return None, recent_replay
            cur.execute(
                """
                insert into public.webhook_log
                  (source, actor_id, run_id, item_count, raw_payload, processing_status, error_message)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    row.get("source"),
                    row.get("actor_id"),
                    row.get("run_id"),
                    row.get("item_count"),
                    psycopg2_extras.Json(row.get("raw_payload")),
                    row.get("processing_status"),
                    row.get("error_message"),
                ),
            )
            inserted = cur.fetchone()
            record_audit_fallback(audit_state, "webhook_log_claim_direct_pg")
            return (str(inserted["id"]) if inserted else None), None


def _find_recent_webhook_replay(
    run_id: Optional[str],
    *,
    strict: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    replay_window_seconds = _webhook_replay_window_seconds()
    if not run_id or replay_window_seconds <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=replay_window_seconds)
    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            result = (
                supabase_client.table("webhook_log")
                .select("id, received_at, processing_status, error_message")
                .eq("run_id", run_id)
                .gte("received_at", cutoff.isoformat())
                .order("received_at", desc=True)
                .limit(5)
                .execute()
            )
            rows = result.data or []
            return select_recent_replay_row(rows)
        except Exception as exc:
            primary_error = exc

    try:
        rows = _find_recent_webhook_replay_direct_pg(run_id, cutoff)
        record_audit_fallback(audit_state, "webhook_replay_lookup_direct_pg")
        return select_recent_replay_row(rows)
    except Exception as fallback_error:
        if strict:
            raise CriticalAuditWriteError(
                format_audit_failure(
                    surface="webhook_log",
                    operation="replay_lookup",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[INGEST_AUTH] replay lookup failed for run_id=%s: %s", run_id, primary_error)
        logger.warning("[INGEST_AUTH] direct PG replay lookup fallback failed for run_id=%s: %s", run_id, fallback_error)
        return None


def _stale_webhook_error(metadata: dict) -> Optional[str]:
    return stale_webhook_error(metadata, _webhook_max_age_seconds())


def _request_client_ip_for_security_log(request: Request) -> str:
    try:
        from webapp.middleware.rate_limit import extract_client_ip
    except Exception:
        extract_client_ip = None
    return request_client_ip_for_security_log(request, extract_client_ip)


def _raw_item_identity(item: Any, run_id: str, item_index: int) -> tuple[str, Optional[str]]:
    return raw_item_identity(item, run_id, item_index)


def _record_pre_save_skip(
    *,
    item: Any,
    run_id: str,
    item_index: int,
    status: str,
    error_message: Optional[str],
    audit_state: Optional[dict[str, Any]] = None,
) -> None:
    _record_delivery_log(
        **build_pre_save_skip_delivery_log_kwargs(
            item=item,
            run_id=run_id,
            item_index=item_index,
            status=status,
            error_message=error_message,
        ),
        audit_state=audit_state,
    )


async def _process_webhook_items(
    payload: dict,
    metadata: dict,
    apify_run_id: str,
    audit_state: dict,
    webhook_log_id: Any,
) -> None:
    """Background task: fetch Apify dataset and process all items."""
    try:
        if supabase_client is not None:
            try:
                existing = (
                    supabase_client.table("opportunities")
                    .select("id")
                    .eq("run_id", apify_run_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    logger.warning(
                        "[IDEMPOTENCY] run_id=%s already has existing rows — skipping duplicate batch processing",
                        apify_run_id,
                    )
                    return
            except Exception as e:
                logger.warning(f"[IDEMPOTENCY] lookup failed for run_id={apify_run_id}: {e}")

        dataset_id = metadata.get("dataset_id") or ""

        apify_token = _apify_api_token()
        if not dataset_id and apify_run_id and apify_token:
            import httpx
            try:
                if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', str(apify_run_id)):
                    logger.warning('[INGEST] Suspicious apify_run_id rejected: %s', apify_run_id)
                    return JSONResponse({'status': 'rejected'}, status_code=400)
                async with httpx.AsyncClient(timeout=30.0) as client:
                    run_resp = await client.get(
                        f"https://api.apify.com/v2/actor-runs/{apify_run_id}",
                        headers={"Authorization": f"Bearer {apify_token}"},
                    )
                    run_resp.raise_for_status()
                    run_data = run_resp.json().get("data", {})
                    dataset_id = run_data.get("defaultDatasetId", "") or ""
                    if dataset_id:
                        logger.info(
                            f"[INGEST] Resolved missing dataset_id via actor run lookup for run_id={apify_run_id}"
                        )
            except Exception as e:
                logger.warning(
                    f"[INGEST] Unable to resolve dataset_id from actor run {apify_run_id}: {e}"
                )

        if not dataset_id:
            logger.warning("[INGEST] dataset_id missing after all lookups — marking error")
            update_webhook_log(
                webhook_log_id,
                "error",
                item_count=metadata["item_count"],
                error_message=merge_audit_error_message("dataset_id_missing", audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', dataset_id):
            logger.warning(f"[INGEST] Suspicious dataset_id rejected: {dataset_id}")
            update_webhook_log(
                webhook_log_id,
                "error",
                error_message=merge_audit_error_message("invalid_dataset_id", audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        import httpx
        apify_token = _apify_api_token()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                    params={"format": "json"},
                    headers={"Authorization": f"Bearer {apify_token}"},
                )
                resp.raise_for_status()
                items = resp.json()
        except Exception as e:
            logger.error(f"[INGEST] Failed to fetch Apify dataset {dataset_id}: {e}")
            update_webhook_log(
                webhook_log_id,
                "error",
                error_message=merge_audit_error_message(f"fetch_failed: {e}", audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        if not isinstance(items, list):
            update_webhook_log(
                webhook_log_id,
                "processed",
                item_count=metadata["item_count"],
                error_message=merge_audit_error_message(None, audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        processed = 0
        evaluated = 0
        saved_count = 0
        failed_save_count = 0
        sonar_write_fail_count = 0
        skipped = 0
        hot_deals = []
        alert_blocked_count = 0
        alert_blocked_reasons: dict[str, int] = {}
        dataset_item_count = len(items)
        skip_reasons: dict[str, int] = {}
        save_outcomes: dict[str, int] = {}
        duplicate_count = 0
        notion_sync_count = 0

        logger.info(
            "[INGEST_RUN] start | run_id=%s | dataset_id=%s | items=%s",
            apify_run_id,
            dataset_id,
            dataset_item_count,
        )

        for item_index, item in enumerate(items):
            try:
                vehicle = normalize_apify_vehicle(
                    item,
                    apify_run_id,
                    default_time_anchor=metadata.get("created_at"),
                    source_hint=metadata.get("source") or metadata.get("actor_id"),
                )
            except Exception as norm_err:
                logger.warning(f"[INGEST] item {item_index} normalize error: {norm_err}")
                skipped += 1
                increment_reason_counter(skip_reasons, "normalize_exception")
                continue
            if vehicle is None:
                skipped += 1
                increment_reason_counter(skip_reasons, "normalize_rejected")
                _record_pre_save_skip(
                    item=item,
                    run_id=apify_run_id,
                    item_index=item_index,
                    status="skipped_norm",
                    error_message="normalize_rejected",
                    audit_state=audit_state,
                )
                continue

            # Handle completed auction sources — write to dealer_sales for DOS calibration
            source_site = _canonical_source_site(vehicle.get("source_site") or vehicle.get("source")) or None
            vehicle["source_site"] = source_site  # persist normalized value (source and source_site are kept in sync via build_opportunity_row)
            if source_site == "govdeals-sold":
                sold_row = {
                    "vin": vehicle.get("vin"),
                    "make": vehicle.get("make") or "Unknown",
                    "model": vehicle.get("model") or "Unknown",
                    "year": int(vehicle.get("year") or 0) or None,
                    "mileage": vehicle.get("mileage"),
                    "sale_price": item.get("sold_price") or vehicle.get("current_bid") or 0,
                    "sold_price": item.get("sold_price") or vehicle.get("current_bid") or 0,
                    "state": vehicle.get("state"),
                    "source_type": "govdeals_sold",
                    "source": "govdeals_sold",
                    "metadata": {"listing_url": vehicle.get("listing_url"), "run_id": apify_run_id},
                }
                dealer_sales_status = "unknown"
                try:
                    if supabase_client is not None:
                        supabase_client.table("dealer_sales").insert(sold_row).execute()
                        dealer_sales_status = "saved_supabase"
                    else:
                        saved_direct_pg, dealer_sales_status = _save_dealer_sale_direct_pg(sold_row)
                        if not saved_direct_pg:
                            raise RuntimeError(dealer_sales_status)
                    processed += 1
                    saved_count += 1
                    logger.info(
                        "[DEALER_SALES] Saved (%s): %s %s %s @ $%s",
                        dealer_sales_status,
                        vehicle.get("year"),
                        vehicle.get("make"),
                        vehicle.get("model"),
                        f"{float(sold_row['sold_price']):,.0f}",
                    )
                    _record_delivery_log(
                        run_id=vehicle.get("run_id") or apify_run_id,
                        listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                        listing_url=vehicle.get("listing_url"),
                        opportunity_id=None,
                        channel="db_save",
                        status=dealer_sales_status,
                        error_message=None,
                        require_durable=True,
                        audit_state=audit_state,
                    )
                except Exception as exc:
                    logger.warning(f"[DEALER_SALES] Insert failed: {exc}")
                    failed_save_count += 1
                    increment_reason_counter(skip_reasons, f"dealer_sales:{dealer_sales_status if dealer_sales_status != 'unknown' else 'error'}")
                    _record_delivery_log(
                        run_id=vehicle.get("run_id") or apify_run_id,
                        listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                        listing_url=vehicle.get("listing_url"),
                        opportunity_id=None,
                        channel="db_save",
                        status="failed",
                        error_message=str(exc),
                        require_durable=True,
                        audit_state=audit_state,
                    )
                continue

            gate_result = passes_basic_gates(vehicle)
            if not gate_result["pass"]:
                logger.info(f"[GATE] Rejected — {gate_result['reason']}: {vehicle.get('title','?')[:60]}")
                skipped += 1
                increment_reason_counter(skip_reasons, f"gate:{gate_result['reason']}")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_gate",
                    error_message=gate_result["reason"],
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            try:
                score_result = score_vehicle(vehicle)
            except Exception as score_err:
                logger.error(
                    "[SCORE] item %s scoring failed: %s",
                    item_index,
                    score_err,
                )
                skipped += 1
                increment_reason_counter(skip_reasons, "score_exception")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_score",
                    error_message=str(score_err),
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            vehicle["dos_score"] = score_result["dos_score"]
            vehicle["score_breakdown"] = score_result
            vehicle["ingested_at"] = datetime.now(timezone.utc).isoformat()
            evaluated += 1

            vehicle_tier = score_result.get("vehicle_tier") or "rejected"
            if not passes_ingest_margin_floor(
                score_result.get("wholesale_margin", 0),
                vehicle_tier,
            ):
                logger.info(
                    "[MARGIN] below lane floor (tier=%s margin=$%s): %s",
                    vehicle_tier,
                    score_result.get("wholesale_margin", 0),
                    vehicle.get("title", "?")[:60],
                )
                skipped += 1
                increment_reason_counter(skip_reasons, "margin_below_floor")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_margin",
                    error_message="margin_below_floor",
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            if not score_result.get("ceiling_pass", True):
                logger.info(
                    f"[CEILING] rejected — {score_result.get('ceiling_reason')} | "
                    f"headroom=${score_result.get('bid_headroom', 0):,.0f}: {vehicle.get('title','?')[:60]}"
                )
                skipped += 1
                increment_reason_counter(
                    skip_reasons,
                    f"ceiling:{score_result.get('ceiling_reason') or 'unknown'}",
                )
                _ceiling_reason = score_result.get("ceiling_reason") or "ceiling_reject"
                _bid = score_result.get("current_bid") or vehicle.get("current_bid") or 0
                _max_bid = score_result.get("max_bid") or 0
                _mmr = score_result.get("mmr_estimated") or 0
                _headroom = score_result.get("bid_headroom") or (_max_bid - float(_bid))
                _ceiling_msg = (
                    f"{_ceiling_reason} | bid=${float(_bid):,.0f} max_bid=${float(_max_bid):,.0f} "
                    f"mmr=${float(_mmr):,.0f} headroom=${float(_headroom):,.0f} "
                    f"tier={score_result.get('vehicle_tier','?')}"
                )
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_ceiling",
                    error_message=_ceiling_msg,
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            dedup = {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}
            if vehicle["dos_score"] >= DOS_SAVE_THRESHOLD:
                try:
                    dedup = check_and_handle_duplicate(supabase_client, vehicle)
                except Exception as dedup_err:
                    logger.error("[DEDUP] lookup failed; skipping item %s: %s", vehicle.get("title", "?"), dedup_err)
                    skipped += 1
                    increment_reason_counter(skip_reasons, "dedup_exception")
                    continue
            is_dup = dedup["is_duplicate"]
            if is_dup:
                vehicle["is_duplicate"] = True
                vehicle["canonical_record_id"] = dedup["canonical_record_id"]
                duplicate_count += 1
                logger.info(f"[DEDUP] duplicate of {dedup['canonical_record_id']}: {vehicle.get('title','?')[:50]}")

            # Try/except around save operation to handle failures
            try:
                saved_opportunity_id = await save_opportunity_to_supabase(vehicle)
            except Exception as exc:
                logger.error(f"[SAVE ERROR] failed to save vehicle {vehicle.get('title')} with error: {exc}")
                failed_save_count += 1
                increment_reason_counter(skip_reasons, "save_exception")
                increment_reason_counter(save_outcomes, "save_exception")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="save_exception",
                    error_message=str(exc),
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue
            # Write to sonar_listings (unfiltered — every vehicle regardless of DOS/state/mileage)
            _sonar_listing_id = vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or "")
            if supabase_client is None:
                sonar_write_fail_count += 1
                logger.warning(
                    "[SONAR_WRITE_FAIL] run_id=%s listing_id=%s title=%s reason=%s",
                    apify_run_id,
                    vehicle.get("listing_id"),
                    (vehicle.get("title") or "?")[:50],
                    "supabase_client_none",
                )
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=_sonar_listing_id,
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=saved_opportunity_id,
                    channel="sonar_mirror",
                    status="sonar_client_unavailable",
                    error_message="supabase_client_none",
                    audit_state=audit_state,
                )
            else:
                try:
                    _save_to_sonar_listings(vehicle)
                    _record_delivery_log(
                        run_id=vehicle.get("run_id") or apify_run_id,
                        listing_id=_sonar_listing_id,
                        listing_url=vehicle.get("listing_url"),
                        opportunity_id=saved_opportunity_id,
                        channel="sonar_mirror",
                        status="saved_sonar",
                        error_message=None,
                        audit_state=audit_state,
                    )
                except Exception as sl_exc:
                    sonar_write_fail_count += 1
                    logger.warning(
                        "[SONAR_WRITE_FAIL] run_id=%s listing_id=%s title=%s reason=%s",
                        apify_run_id,
                        vehicle.get("listing_id"),
                        (vehicle.get("title") or "?")[:50],
                        f"insert_error: {sl_exc}",
                    )
                    _record_delivery_log(
                        run_id=vehicle.get("run_id") or apify_run_id,
                        listing_id=_sonar_listing_id,
                        listing_url=vehicle.get("listing_url"),
                        opportunity_id=saved_opportunity_id,
                        channel="sonar_mirror",
                        status="sonar_error",
                        error_message=f"insert_error: {sl_exc}",
                        audit_state=audit_state,
                    )
            save_status = vehicle.get("_save_status", "unknown")
            increment_reason_counter(save_outcomes, save_status)
            if saved_opportunity_id:
                vehicle["opportunity_id"] = saved_opportunity_id

            if vehicle.get("is_duplicate") and not is_dup:
                is_dup = True
                duplicate_count += 1
                logger.info(
                    "[DEDUP] canonical conflict recovered for %s: %s",
                    vehicle.get("canonical_record_id"),
                    vehicle.get("title", "?")[:50],
                )

            _record_delivery_log(
                run_id=vehicle.get("run_id") or apify_run_id,
                listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                listing_url=vehicle.get("listing_url"),
                opportunity_id=saved_opportunity_id,
                channel="db_save",
                status=save_status,
                error_message=None if save_status not in {"supabase_error", "direct_pg_error", "duplicate_unresolved", "direct_pg_unavailable"} else save_status,
                require_durable=True,
                audit_state=audit_state,
            )

            inserted_success = save_status in {
                "saved_supabase",
                "saved_supabase_duplicate",
                "saved_direct_pg",
                "saved_direct_pg_duplicate",
            }
            existing_success = save_status in {
                "duplicate_existing",
                "duplicate_pricing_refreshed",
                "vin_dedup_skipped",
                "vin_dedup_updated",
                "vin_dedup_pricing_refreshed",
            }
            save_succeeded = inserted_success or existing_success
            is_existing_listing = save_status in {
                "duplicate_existing",
                "duplicate_pricing_refreshed",
                "duplicate_unresolved",
                "vin_dedup_skipped",
                "vin_dedup_updated",
                "vin_dedup_pricing_refreshed",
            } or is_dup
            if save_succeeded:
                processed += 1
                if inserted_success:
                    saved_count += 1
            else:
                failed_save_count += 1

            if save_succeeded and is_dup and dedup.get("canonical_update"):
                if _apply_canonical_update(dedup.get("canonical_update")):
                    logger.info("[DEDUP] canonical source update applied for %s", dedup.get("canonical_record_id"))

            if save_succeeded and not is_dup and vehicle["dos_score"] >= 65:
                notion_synced = await sync_to_notion(vehicle)
                if notion_synced:
                    notion_sync_count += 1

            logger.info(
                f"[INGEST] {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} "
                f"| DOS={vehicle['dos_score']} | Bid=${vehicle.get('current_bid'):,.0f} "
                f"| Gross=${score_result.get('gross_margin',0):,.0f} "
                f"| Headroom=${score_result.get('bid_headroom',0):,.0f} | {vehicle.get('state')}"
                + (" [DUP]" if is_dup else "")
                + f" | save={save_status}"
            )

            if not is_existing_listing and save_status in {"saved_supabase", "saved_direct_pg"}:
                alert_gate = _alert_gate_for_vehicle(vehicle)
                if alert_gate.get("eligible"):
                    logger.info(
                        "[ALERT_GATE] eligible | %s | %s",
                        alert_gate.get("summary"),
                        vehicle.get("title", "?")[:80],
                    )
                    hot_deals.append(vehicle)
                elif (
                    vehicle["dos_score"] >= hot_deal_min_score(os.environ, log=logger)
                    or score_result.get("investment_grade") in {"Gold", "Platinum"}
                ):
                    blocking_reasons = alert_gate.get("blocking_reasons") or ["unknown"]
                    alert_blocked_count += 1
                    for reason in blocking_reasons:
                        increment_reason_counter(alert_blocked_reasons, str(reason))
                    logger.info(
                        "[ALERT_GATE] blocked | %s | reasons=%s | %s",
                        alert_gate.get("summary"),
                        ",".join(blocking_reasons),
                        vehicle.get("title", "?")[:80],
                    )

        if hot_deals:
            validated_deals = await ai_validate_hot_deals(hot_deals)
            logger.info(
                "[ALERT_PIPELINE] eligible=%s validated=%s rejected=%s",
                len(hot_deals),
                len(validated_deals),
                len(hot_deals) - len(validated_deals),
            )
            await send_telegram_alerts(validated_deals)

        logger.info(
            "[INGEST_RUN] complete | run_id=%s | dataset_id=%s | items=%s | evaluated=%s | inserted=%s | existing=%s | failed_save=%s | sonar_write_fail=%s | skipped=%s | duplicates=%s | notion_sync=%s | hot_deals=%s | save_outcomes=%s | skip_reasons=%s",
            apify_run_id,
            dataset_id,
            dataset_item_count,
            evaluated,
            saved_count,
            save_outcomes.get("duplicate_existing", 0),
            failed_save_count,
            sonar_write_fail_count,
            skipped,
            duplicate_count,
            notion_sync_count,
            len(hot_deals),
            save_outcomes,
            skip_reasons,
        )

        summary_message = format_ingest_run_summary(
            dataset_item_count=dataset_item_count,
            evaluated=evaluated,
            saved_count=saved_count,
            duplicate_existing=save_outcomes.get("duplicate_existing", 0),
            failed_save_count=failed_save_count,
            sonar_write_failures=sonar_write_fail_count,
            skipped=skipped,
            duplicate_count=duplicate_count,
            notion_sync_count=notion_sync_count,
            hot_deals_count=len(hot_deals),
            alert_blocked_count=alert_blocked_count,
            alert_blocked_reasons=alert_blocked_reasons,
        )
        detail_message = (
            None
            if failed_save_count == 0
            and sonar_write_fail_count == 0
            and (saved_count > 0 or save_outcomes.get("duplicate_existing", 0) > 0)
            else f"save_outcomes={save_outcomes}; skip_reasons={skip_reasons}"
        )
        combined_message = summary_message if not detail_message else f"{summary_message}; {detail_message}"

        update_webhook_log(
            webhook_log_id,
            "processed" if failed_save_count == 0 and sonar_write_fail_count == 0 else "error",
            item_count=dataset_item_count,
            error_message=merge_audit_error_message(
                combined_message,
                audit_fallbacks(audit_state),
            ),
            require_durable=True,
            audit_state=audit_state,
        )
    except CriticalAuditWriteError as e:
        logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, e)
    except Exception as e:
        logger.error("[INGEST] Background processing failed for run_id=%s: %s", apify_run_id, e)
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=merge_audit_error_message(str(e), audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)


@router.post("/apify")
async def apify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_apify_webhook_secret: Optional[str] = Header(None)
):
    # Verify webhook secret
    matched_secret_label = _match_webhook_secret(x_apify_webhook_secret)
    if matched_secret_label is None:
        logger.warning(
            "[INGEST_AUTH] rejected_invalid_secret | client_ip=%s | path=/api/ingest/apify",
            _request_client_ip_for_security_log(request),
        )
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    if matched_secret_label == "previous":
        posture = _webhook_secret_posture()
        logger.warning(
            "[INGEST_AUTH] Accepted webhook with APIFY_WEBHOOK_SECRET_PREVIOUS; "
            "previous_fp=%s active_fp=%s finish rotation and remove the fallback secret.",
            posture["previous"]["fingerprint"] or "none",
            posture["active"]["fingerprint"] or "missing",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Unexpected payload format")

    metadata = extract_apify_webhook_metadata(payload)
    apify_run_id = metadata["run_id"] or str(uuid.uuid4())[:8]
    audit_state: dict[str, Any] = {"fallbacks": []}
    webhook_log_id = None
    logger.info(f"[INGEST] Webhook received for run_id={apify_run_id}")

    try:
        stale_error = _stale_webhook_error(metadata)
        if stale_error:
            insert_webhook_log(
                payload,
                processing_status="ignored_stale",
                error_message=stale_error,
                require_durable=True,
                audit_state=audit_state,
            )
            raise HTTPException(status_code=401, detail="Stale webhook payload")

        webhook_log_id, recent_replay = _claim_webhook_log(
            payload,
            require_durable=True,
            audit_state=audit_state,
        )

        if recent_replay:
            replay_message = (
                f"Replay ignored for run_id={apify_run_id}; prior status="
                f"{recent_replay.get('processing_status') or 'unknown'} at "
                f"{recent_replay.get('received_at') or 'unknown'}"
            )
            logger.warning("[INGEST_AUTH] %s", replay_message)
            insert_webhook_log(
                payload,
                processing_status="ignored_replay",
                error_message=replay_message,
                require_durable=True,
                audit_state=audit_state,
            )
            response = {
                "status": "ok",
                "run_id": apify_run_id,
                "replay_ignored": True,
                "message": "Duplicate webhook ignored",
            }
            attach_audit_state(response, audit_state)
            return response

        background_tasks.add_task(
            _process_webhook_items,
            payload,
            metadata,
            apify_run_id,
            audit_state,
            webhook_log_id,
        )
        return {"status": "ok", "run_id": apify_run_id, "message": "Processing in background"}
    except CriticalAuditWriteError as e:
        logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, e)
        raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from e
    except HTTPException as e:
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=merge_audit_error_message(str(e.detail), audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)
                raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from audit_error
        raise
    except Exception as e:
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=merge_audit_error_message(str(e), audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)
                raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from audit_error
        raise


def get_supabase_client():
    """Return the module-level supabase_client (used by standalone endpoints)."""
    return supabase_client


@router.post("/opportunities/{opportunity_id}/pass")
async def pass_opportunity(
    opportunity_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Mark an opportunity as passed by the current user. Writes to user_passes table."""
    # Auth: get user_id from Authorization Bearer header via Supabase
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")

    # Verify token via Supabase and get user_id
    supa = get_supabase_client()
    try:
        user_resp = supa.auth.get_user(token)
        user_id = user_resp.user.id if user_resp and user_resp.user else None
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    opp_check = supa.table("opportunities").select("id").eq("id", opportunity_id).maybe_single().execute()
    if not opp_check or not opp_check.data:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Write to user_passes table
    try:
        supa.table("user_passes").upsert({
            "user_id": user_id,
            "opportunity_id": opportunity_id,
        }, on_conflict="user_id,opportunity_id").execute()
    except Exception as e:
        logger.warning(f"[PASS] user_passes upsert failed: {e}")
        # Non-fatal — return success anyway so UI doesn't break

    return {"status": "passed", "opportunity_id": opportunity_id}


# Auction end-time normalization is imported from backend.ingest.time_utils.


# Source-site normalization is kept behind these imported aliases so existing
# ingest.py callers and tests can remain unchanged during incremental extraction.

def normalize_apify_vehicle(
    item: dict,
    run_id: str,
    *,
    default_time_anchor: Optional[datetime] = None,
    source_hint: Optional[str] = None,
) -> Optional[dict]:
    """Normalize raw Apify scraper output to DealerScope vehicle format.

    Handles two formats:
    - Our custom scrapers: snake_case (current_bid, listing_url, etc.)
    - parseforge/govdeals-scraper: camelCase (currentBid, url, locationState, etc.)
    """
    try:
        if item.get("record_type") == "source_quality_proof":
            logger.info("[INGEST] Skipping source quality proof record from opportunity normalization")
            return None

        title = item.get("title", "")

        # State: parseforge uses locationState, ours uses state
        state = (
            item.get("locationState") or
            item.get("state") or ""
        ).strip().upper()

        # Make/model/year: parseforge provides these directly
        make = item.get("make") or extract_make(title) or ""
        model = item.get("model") or extract_model(title, make) or ""
        year_raw = item.get("modelYear") or item.get("year")
        year = int(year_raw) if year_raw and str(year_raw).isdigit() else extract_year(title)
        from backend.ingest.score import determine_vehicle_tier
        vehicle_tier = determine_vehicle_tier(year, item.get("mileage") or item.get("meterCount") or item.get("odometer"))

        # Skip high rust states at normalize time using the same rule for every source.
        if state in HIGH_RUST_STATES:
            current_year = datetime.now().year
            if not year or year < current_year - 2:
                return None
            logger.info(f'[BYPASS] Rust state {state} allowed — vehicle is {year} (≤2yr old)')

        # Bid: parseforge uses currentBid, ours uses current_bid
        current_bid = float(item.get("currentBid") or item.get("current_bid") or 0)

        # Mileage: parseforge puts in meterCount when type is odometer; jjkane uses odometer.
        # Some sources (for example Proxibid) often omit mileage entirely; allow None and let
        # downstream scoring/gating decide instead of blanket normalization rejection.
        mileage = item.get("mileage") or item.get("meterCount") or item.get("odometer")

        def _extract_numeric_key(*keys: str) -> Optional[float]:
            for key in keys:
                value = item.get(key)
                if value in {None, ""}:
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
            return None

        # End time: parseforge uses auctionEndUtc
        time_anchor = (
            _parse_datetime_utc(item.get("scraped_at") or item.get("scrapedAt") or item.get("createdAt"))
            or default_time_anchor
        )
        auction_end = _normalize_auction_end_time(
            item.get("auctionEndUtc") or
            item.get("auction_end_time") or
            item.get("auction_end_date") or
            item.get("auction_end") or
            item.get("time_left") or
            item.get("timeLeft"),
            reference_dt=time_anchor,
        )

        # URL: parseforge uses url, ours uses listing_url
        listing_url = item.get("url") or item.get("listing_url") or ""

        # Photo: parseforge uses imageUrl or photos[]
        photos = item.get("photos", [])
        photo_url = (
            item.get("image_url") or item.get("photo_url") or
            item.get("imageUrl") or (photos[0] if photos else "")
        )

        # Agency: parseforge uses seller
        agency = item.get("seller") or item.get("agency_name") or ""

        # Source
        source = _infer_source_site(item, source_hint=source_hint)

        buyer_premium_pct = _extract_numeric_key(
            "buyer_premium_pct",
            "buyers_premium_pct",
            "buyer_premium_percent",
            "buyers_premium_percent",
            "buyerPremiumPct",
            "buyersPremiumPct",
            "buyerPremiumPercent",
            "buyersPremiumPercent",
            "premium_pct",
            "premium_percent",
            "premiumRate",
            "rate",
            "percent",
        )
        buyer_premium = _extract_numeric_key(
            "buyer_premium",
            "buyers_premium",
            "buyerPremium",
            "buyersPremium",
            "buyer_premium_amount",
            "buyers_premium_amount",
            "buyerPremiumAmount",
            "buyersPremiumAmount",
            "premium",
            "premium_amount",
            "premiumAmount",
            "flat_fee",
            "flatFee",
        )
        doc_fee = _extract_numeric_key(
            "doc_fee",
            "docFee",
            "documentation_fee",
            "documentationFee",
            "docfee",
        )
        auction_fees = _extract_numeric_key(
            "auction_fees",
            "auctionFee",
            "auctionFees",
            "auction_fee",
            "auctionfee",
        )

        item_run_id = (
            item.get("source_run_id")
            or item.get("run_id")
            or item.get("actor_run_id")
            or item.get("apify_run_id")
            or run_id
        )

        normalized = {
            "listing_id": _compute_listing_id(source, listing_url),
            "title": title,
            "title_status": item.get("title_status") or item.get("titleStatus") or "",
            "current_bid": current_bid,
            "actual_current_bid": _extract_numeric_key("actual_current_bid", "actualCurrentBid") or 0,
            "estimated_auction_price": _extract_numeric_key("estimated_auction_price", "estimatedAuctionPrice") or 0,
            "buyer_premium_pct": buyer_premium_pct,
            "buyer_premium": buyer_premium,
            "doc_fee": doc_fee,
            "auction_fees": auction_fees,
            "mileage": mileage,
            "description": item.get("description") or item.get("detail_text") or item.get("assetLongDesc") or "",
            "photos": photos,
            "damage_type": item.get("damage_type") or item.get("damageType") or "",
            "state": state,
            "location": (
                item.get("location") or
                f"{item.get('locationCity','')}, {state}".strip(", ")
            ),
            "auction_end_time": auction_end,
            "listing_url": listing_url,
            "source_site": source,
            "photo_url": photo_url,
            "agency_name": agency,
            "vin": item.get("vin"),
            "year": year,
            "make": make,
            "model": model,
            "designated_lane": vehicle_tier,
            "vehicle_tier": vehicle_tier,
            "dos_premium": None,
            "dos_standard": None,
            "risk_flags": [],
            "bid_ceiling_pct": bid_ceiling_pct_for_tier(vehicle_tier),
            "min_margin_target": min_margin_for_tier(vehicle_tier),
            "run_id": item_run_id,
            "source_run_id": item_run_id,
            "actor_run_id": item.get("actor_run_id") or item_run_id,
            "apify_run_id": item.get("apify_run_id") or item_run_id,
            "detail_enriched": item.get("detail_enriched"),
            "detail_enriched_by_detail_page": item.get("detail_enriched_by_detail_page"),
        }
        normalized["canonical_id"] = compute_canonical_id(normalized)
        normalized["all_sources"] = [source] if source else []
        normalized["is_duplicate"] = False
        normalized["canonical_record_id"] = None
        normalized["duplicate_count"] = 0
        normalized = apply_tavily_enrichment(normalized)
        return normalized
    except Exception as e:
        logger.error(f"[INGEST] Normalize error: {e}")
        return None


def _alert_gate_for_vehicle(vehicle: dict) -> dict:
    gate = evaluate_alert_gate(vehicle, thresholds=_alert_thresholds())
    vehicle["alert_gate"] = gate
    return gate


# Title/year/model extraction and proxy MMR helpers are imported from backend.ingest.vehicle_identity.


def passes_basic_gates(vehicle: dict) -> dict:
    """Five-layer institutional filter. Returns {"pass": bool, "reason": str}."""
    from backend.ingest.score import determine_vehicle_tier

    result = _passes_basic_gates(vehicle, determine_vehicle_tier=determine_vehicle_tier)
    if result.get("pass") and vehicle.get("state") in HIGH_RUST_STATES:
        logger.info(
            f"[GATE] Rust state {vehicle.get('state')} allowed for {vehicle.get('year')} (within 2-year window)"
        )
    return result


def score_vehicle(vehicle: dict) -> dict:
    """
    Score using the real DOS formula from backend.ingest.score.
    Falls back to simplified scoring if import fails.
    """
    try:
        from backend.ingest.score import score_deal
        from backend.ingest.manheim_market import get_manheim_market_data
        from backend.ingest.retail_comps import get_retail_comps

        bid = vehicle.get("current_bid", 0)
        state = vehicle.get("state", "")
        source = vehicle.get("source_site", "GovDeals")
        SOURCE_MAP = {
            "govdeals": "GovDeals",
            "publicsurplus": "PublicSurplus",
            "gsaauctions": "GSAAuctions",
            "municibid": "Municibid",
            "govplanet": "GovPlanet",
        }
        source_site = SOURCE_MAP.get((source or "").lower(), source)
        make = vehicle.get("make", "")
        model = vehicle.get("model", "")
        year = vehicle.get("year")
        mileage = vehicle.get("mileage")
        police_fleet_text = " ".join(
            str(vehicle.get(field) or "").lower()
            for field in ("title", "model", "agency_name")
        )
        is_police_or_fleet = any(
            term in police_fleet_text
            for term in ("police", "interceptor", "ppv", "pursuit", "fleet")
        )
        mmr_details = _estimate_mmr_details(make, model)
        manheim_result = get_manheim_market_data(
            year=year,
            make=make,
            model=model,
            state=state,
            mileage=mileage,
            proxy_mmr=mmr_details.get("mmr"),
            proxy_basis=mmr_details.get("basis"),
            proxy_confidence=mmr_details.get("confidence_proxy"),
        )
        mmr = manheim_result.get("manheim_mmr_mid") or mmr_details["mmr"]
        mmr_lookup_basis = (
            "manheim_live"
            if manheim_result.get("manheim_source_status") == "live"
            else mmr_details.get("basis")
        )
        retail_comp_result = get_retail_comps(
            year=year,
            make=make,
            model=model,
            state=state,
            supabase_client=supabase_client,
        )

        result = score_deal(
            bid=bid,
            mmr_ca=mmr,
            state=state,
            source_site=source_site,
            model=model,
            make=make,
            year=year,
            mileage=mileage,
            is_police_or_fleet=is_police_or_fleet,
            auction_end=vehicle.get("auction_end_time"),
            mmr_lookup_basis=mmr_lookup_basis,
            mmr_confidence_proxy=mmr_details.get("confidence_proxy"),
            retail_comp_price_estimate=retail_comp_result.get("retail_comp_price_estimate"),
            retail_comp_low=retail_comp_result.get("retail_comp_low"),
            retail_comp_high=retail_comp_result.get("retail_comp_high"),
            retail_comp_count=retail_comp_result.get("retail_comp_count"),
            retail_comp_confidence=retail_comp_result.get("retail_comp_confidence"),
            pricing_source=retail_comp_result.get("pricing_source"),
            pricing_updated_at=retail_comp_result.get("pricing_updated_at"),
            manheim_mmr_mid=manheim_result.get("manheim_mmr_mid"),
            manheim_mmr_low=manheim_result.get("manheim_mmr_low"),
            manheim_mmr_high=manheim_result.get("manheim_mmr_high"),
            manheim_range_width_pct=manheim_result.get("manheim_range_width_pct"),
            manheim_confidence=manheim_result.get("manheim_confidence"),
            manheim_source_status=manheim_result.get("manheim_source_status"),
            manheim_updated_at=manheim_result.get("manheim_updated_at"),
            buyer_premium_pct=vehicle.get("buyer_premium_pct"),
            auction_fees=vehicle.get("auction_fees"),
            # Condition-relevant fields — wire through so ai_confidence reflects actual quality
            title_status=vehicle.get("title_status"),
            description=vehicle.get("description"),
            photos=vehicle.get("photos") or vehicle.get("photo_urls"),
            damage_type=vehicle.get("damage_type"),
            title=vehicle.get("title"),
        )
        result["mmr_estimated"] = mmr
        vehicle["mmr_estimated"] = mmr
        for key in (
            "designated_lane",
            "dos_premium",
            "dos_standard",
            "risk_flags",
            "vehicle_tier",
            "bid_ceiling_pct",
            "min_margin_target",
            "ai_confidence_score",
        ):
            vehicle[key] = result.get(key)

        try:
            actual_current_bid = float(vehicle.get("actual_current_bid") or 0)
        except (TypeError, ValueError):
            actual_current_bid = 0.0
        try:
            estimated_auction_price = float(vehicle.get("estimated_auction_price") or 0)
        except (TypeError, ValueError):
            estimated_auction_price = 0.0
        source_site_lower = (vehicle.get("source_site") or "").lower()
        scored_vehicle_tier = result.get("vehicle_tier") or vehicle.get("vehicle_tier")
        min_margin_target = float(result.get("min_margin_target") or 0)
        gross_margin = float(result.get("gross_margin") or 0)
        max_bid = float(result.get("max_bid") or 0)
        bid_value = float(vehicle.get("current_bid") or 0)
        auction_stage_hours_remaining = result.get("auction_stage_hours_remaining")
        structural_ceiling_pass = bid_value > 0 and bid_value <= max_bid and gross_margin >= min_margin_target and scored_vehicle_tier != "rejected"

        if source_site_lower == "jjkane" and (actual_current_bid or 0) <= 0 and (estimated_auction_price or 0) > 0 and structural_ceiling_pass:
            lane_floor = 85.0 if scored_vehicle_tier == "standard" else 70.0 if scored_vehicle_tier == "premium" else float(result.get("ai_confidence_score") or 0)
            result["current_bid_trust_score"] = max(float(result.get("current_bid_trust_score") or 0), 0.85)
            result["ai_confidence_score"] = max(float(result.get("ai_confidence_score") or 0), lane_floor)
            result["pricing_maturity"] = "market_comp"
            result["expected_close_source"] = "jjkane_estimated_auction_price"
            result["acquisition_basis_source"] = "jjkane_estimated_auction_price"
            result["ceiling_reason"] = "jjkane_estimated_close_bid"
            result["ceiling_pass"] = True
            roi_pct = float(result.get("roi_pct") or 0)
            dos_score = float(result.get("dos_score") or 0)
            if scored_vehicle_tier == "rejected":
                investment_grade = "Rejected"
            elif dos_score >= 80 and roi_pct >= 20:
                investment_grade = "Platinum"
            elif dos_score >= 65 and roi_pct >= 12:
                investment_grade = "Gold"
            elif dos_score >= 50:
                investment_grade = "Silver"
            else:
                investment_grade = "Bronze"
            result["investment_grade"] = investment_grade

        if source_site_lower in {"govdeals", "proxibid", "hibid", "gsaauctions", "allsurplus", "municibid", "usgovbid", "govplanet"} and structural_ceiling_pass and auction_stage_hours_remaining is not None and float(auction_stage_hours_remaining) <= 24:
            lane_floor = 85.0 if scored_vehicle_tier == "standard" else 70.0 if scored_vehicle_tier == "premium" else float(result.get("ai_confidence_score") or 0)
            result["current_bid_trust_score"] = max(float(result.get("current_bid_trust_score") or 0), 0.85)
            result["ai_confidence_score"] = max(float(result.get("ai_confidence_score") or 0), lane_floor)
            result["pricing_maturity"] = "market_comp"
            result["ceiling_reason"] = f"{source_site_lower}_live_bid_near_close"
            result["ceiling_pass"] = True
            roi_pct = float(result.get("roi_pct") or 0)
            dos_score = float(result.get("dos_score") or 0)
            if scored_vehicle_tier == "rejected":
                investment_grade = "Rejected"
            elif dos_score >= 80 and roi_pct >= 20:
                investment_grade = "Platinum"
            elif dos_score >= 65 and roi_pct >= 12:
                investment_grade = "Gold"
            elif dos_score >= 50:
                investment_grade = "Silver"
            else:
                investment_grade = "Bronze"
            result["investment_grade"] = investment_grade

        return result

    except Exception as e:
        logger.error(f"[SCORE] Real DOS formula failed, rejecting item: {e}")
        raise RuntimeError(f"score_vehicle_failed: {e}") from e


def _fallback_score(vehicle: dict) -> dict:
    """Router compatibility wrapper for the extracted fallback score helper."""
    return build_fallback_score(vehicle)


async def sync_to_notion(vehicle: dict) -> bool:
    """Push a scored deal to the Notion Dealerscope Deals database."""
    notion_token = get_config("NOTION_TOKEN") or ""
    notion_db_id = get_config("NOTION_DEALS_DB_ID") or ""
    if not notion_token or not notion_db_id:
        return False

    listing_url = vehicle.get("listing_url") or ""
    if not listing_url:
        logger.info("[NOTION] Skipping — empty listing_url")
        return False
    run_id = vehicle.get("run_id") or "unknown"
    listing_id = vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", listing_url)
    existing_delivery = _delivery_log_lookup(run_id, listing_id, "notion_sync")
    if existing_delivery and existing_delivery.get("status") == "sent":
        return True

    score = vehicle.get("dos_score", 0)
    breakdown = vehicle.get("score_breakdown", {})

    if score >= 80:
        status = "🔥 Hot"
    elif score >= 65:
        status = "✅ Good"
    else:
        status = "👀 Watching"

    title = f"{vehicle.get('year','')} {vehicle.get('make','')} {vehicle.get('model','')}".strip() or vehicle.get("title", "Unknown")

    # Parse auction end date
    end_date = None
    raw_end = vehicle.get("auction_end_time")
    if raw_end:
        try:
            from dateutil import parser as dateparser
            end_date = dateparser.parse(str(raw_end)).strftime("%Y-%m-%d")
        except Exception:
            pass

    props = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
        "DOS Score": {"number": score},
        "Status": {"select": {"name": status}},
        "Bid Price": {"number": vehicle.get("current_bid")},
        "MMR": {"number": breakdown.get("mmr_estimated")},
        "Gross Margin": {"number": breakdown.get("margin")},
        "Source": {"select": {"name": vehicle.get("source_site", "GovDeals")}},
        "Year": {"number": vehicle.get("year")},
        "Listing URL": {"url": vehicle.get("listing_url") or None},
    }

    if vehicle.get("state"):
        props["State"] = {"select": {"name": vehicle["state"][:2]}}
    if vehicle.get("make"):
        props["Make"] = {"rich_text": [{"text": {"content": vehicle["make"][:100]}}]}
    if vehicle.get("model"):
        props["Model"] = {"rich_text": [{"text": {"content": vehicle["model"][:100]}}]}
    if vehicle.get("mileage"):
        try:
            props["Mileage"] = {"number": int(float(vehicle["mileage"]))}
        except (ValueError, TypeError):
            pass
    if end_date:
        props["Auction Ends"] = {"date": {"start": end_date}}

    # Structured deal summary for the Notes field
    bid        = vehicle.get("current_bid", 0)
    mmr        = breakdown.get("mmr_estimated", 0)
    margin     = breakdown.get("margin", 0)
    state_str  = vehicle.get("state", "?")
    end_str    = end_date or "?"
    rec        = "🔥 BUY HOT" if score >= 80 else "✅ BUY" if score >= 65 else "⚠️ WATCH"
    notes_text = (
        f"{title} | Bid: ${bid:,.0f} | MMR: ${mmr:,.0f} | "
        f"Margin: ${margin:,.0f} | DOS: {score} | "
        f"Ends: {end_str} | State: {state_str} | {rec}"
    )
    props["Notes"] = {"rich_text": [{"text": {"content": notes_text[:2000]}}]}

    # Remove None values (Notion rejects null numbers)
    props = {k: v for k, v in props.items() if not (
        isinstance(v, dict) and v.get("number") is None
    )}

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            if listing_url:
                query_resp = await client.post(
                    f"https://api.notion.com/v1/databases/{notion_db_id}/query",
                    headers=headers,
                    json={
                        "filter": {
                            "property": "Listing URL",
                            "url": {"equals": listing_url},
                        },
                        "page_size": 1,
                    },
                )
                if query_resp.status_code == 200:
                    existing_results = query_resp.json().get("results") or []
                    if existing_results:
                        page_id = existing_results[0].get("id")
                        logger.info("[NOTION] Existing page found for listing_url=%s; skipping create", listing_url)
                        _record_delivery_log(
                            run_id=run_id,
                            listing_id=listing_id,
                            listing_url=listing_url,
                            opportunity_id=vehicle.get("opportunity_id"),
                            channel="notion_sync",
                            status="sent",
                            external_id=page_id,
                        )
                        return True
                else:
                    logger.warning(f"[NOTION] Query failed: {query_resp.status_code} {query_resp.text[:200]}")

            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={"parent": {"database_id": notion_db_id}, "properties": props},
            )
            if resp.status_code == 200:
                page_id = resp.json().get("id")
                _record_delivery_log(
                    run_id=run_id,
                    listing_id=listing_id,
                    listing_url=listing_url,
                    opportunity_id=vehicle.get("opportunity_id"),
                    channel="notion_sync",
                    status="sent",
                    external_id=page_id,
                )
                return True
            logger.warning(f"[NOTION] Failed to sync: {resp.status_code} {resp.text[:200]}")
            _record_delivery_log(
                run_id=run_id,
                listing_id=listing_id,
                listing_url=listing_url,
                opportunity_id=vehicle.get("opportunity_id"),
                channel="notion_sync",
                status="failed",
                error_message=f"http_{resp.status_code}",
            )
            return False
    except Exception as e:
        logger.error(f"[NOTION] Sync error (non-fatal): {e}")
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=vehicle.get("opportunity_id"),
            channel="notion_sync",
            status="failed",
            error_message=str(e),
        )
        return False


async def send_telegram_alert(deal: dict) -> Optional[str]:
    """Send a single Telegram alert, log the receipt, and return the Telegram message_id."""
    run_id = deal.get("run_id") or "unknown"
    raw_listing_url = deal.get("listing_url") or ""
    listing_url = clean_bid_direct_url(raw_listing_url)
    listing_id = deal.get("listing_id") or _compute_listing_id(deal.get("source_site") or "", listing_url)
    existing_delivery = _delivery_log_lookup(run_id, listing_id, "telegram_alert")
    if existing_delivery and existing_delivery.get("status") == "sent":
        return existing_delivery.get("external_id")

    # Kill switch
    if os.getenv("ALERTS_ENABLED", ALERTS_ENABLED_PRODUCTION_DEFAULT).lower() != "true":
        logger.info("[ALERTS DISABLED] skipping alert")
        return None

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Missing bot token or chat ID; skipping alert")
        return None

    opp_id = deal.get("opportunity_id")

    # 6-hour suppression check
    if supabase_client is not None and opp_id:
        try:
            alert_suppression_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
            recent = (
                supabase_client.table("alert_log")
                .select("id")
                .eq("opportunity_id", opp_id)
                .gte("sent_at", alert_suppression_cutoff)
                .execute()
            )
            if recent.data:
                logger.info("[ALERT SUPPRESSED] already alerted within 6hrs")
                return None
        except Exception as e:
            logger.warning(f"[SUPPRESSION CHECK] failed: {e}")

    # Per-run alert cap (max 20) with 1-hour TTL reset
    _now = _time.time()
    if _now - alerts_this_run_ts.get(run_id, 0) > 3600:
        alerts_this_run.pop(run_id, None)
        alerts_this_run_ts.pop(run_id, None)
    if alerts_this_run.get(run_id, 0) >= 20:
        logger.info(f"[ALERT CAP] max alerts reached for run {run_id}")
        return None
    alerts_this_run[run_id] = alerts_this_run.get(run_id, 0) + 1
    alerts_this_run_ts[run_id] = alerts_this_run_ts.get(run_id) or _time.time()

    try:
        import httpx

        callback_id = opp_id or "unknown"
        alert_gate = _alert_gate_for_vehicle(deal)
        if not alert_gate.get("eligible"):
            logger.info(
                "[ALERT_GATE] send skipped | %s | reasons=%s | %s",
                alert_gate.get("summary"),
                ",".join(alert_gate.get("blocking_reasons") or ["unknown"]),
                deal.get("title", "?")[:80],
            )
            return None
        score_breakdown = deal.get("score_breakdown", {})
        investment_grade = score_breakdown.get("investment_grade") or "Watch"
        is_platinum = alert_gate.get("alert_type") == "platinum"
        reply_markup = build_telegram_reply_markup(callback_id)
        msg = build_telegram_alert_message(deal, listing_url, alert_gate=alert_gate)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                    "reply_markup": reply_markup,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        safe_error = redact_telegram_bot_token(e)
        logger.error("[TELEGRAM] Alert failed (non-fatal): %s", safe_error)
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=deal.get("opportunity_id"),
            channel="telegram_alert",
            status="failed",
            error_message=safe_error,
        )
        return None

    message_id = payload.get("result", {}).get("message_id")
    if message_id is None:
        logger.warning(f"[TELEGRAM] Missing message_id in response for run_id={deal.get('run_id')}")
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=deal.get("opportunity_id"),
            channel="telegram_alert",
            status="failed",
            error_message="missing_message_id",
        )
        return None

    message_id_str = str(message_id)
    deal["message_id"] = message_id_str
    _record_delivery_log(
        run_id=run_id,
        listing_id=listing_id,
        listing_url=listing_url,
        opportunity_id=deal.get("opportunity_id"),
        channel="telegram_alert",
        status="sent",
        external_id=message_id_str,
    )
    await insert_alert_log(deal, message_id_str)

    # Also send to Slack #general (non-blocking — never fail the Telegram receipt on Slack error)
    slack_token = get_config("SLACK_BOT_TOKEN")
    slack_channel = get_config("SLACK_CHANNEL_ID") or "C0ALM52FV25"
    if slack_token:
        try:
            prefix = "💎 *PLATINUM*" if is_platinum else "🔥 *HOT DEAL*"
            slack_text = (
                f"{prefix} | {deal.get('year')} {deal.get('make')} {deal.get('model')} "
                f"| {investment_grade} | Score {deal['dos_score']} | ${deal.get('current_bid', 0):,.0f} "
                f"| {deal.get('state', '?')} | <{deal.get('listing_url', '')}|View>"
            )
            async with httpx.AsyncClient(timeout=5.0) as sc:
                slack_resp = await sc.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    json={"channel": slack_channel, "text": slack_text},
                )
                if not slack_resp.json().get("ok"):
                    logger.warning(f"[SLACK] Alert not ok: {slack_resp.json().get('error')}")
                else:
                    logger.info(f"[SLACK] Alert sent for {deal.get('make')} {deal.get('model')}")
        except Exception as e:
            logger.warning(f"[SLACK] Alert failed (non-fatal): {e}")

    return message_id_str


async def insert_alert_log(vehicle: dict, message_id: str) -> bool:
    """Persist a Telegram delivery receipt to Supabase."""
    if supabase_client is None:
        return False

    alert_key = vehicle.get("opportunity_id") or vehicle.get("listing_url") or vehicle.get("title") or "unknown"
    alert_id = hashlib.sha256(f"{vehicle.get('run_id', '')}:{alert_key}".encode()).hexdigest()[:64]
    row = {
        "opportunity_id": vehicle.get("opportunity_id"),
        "run_id": vehicle.get("run_id"),
        "alert_id": alert_id,
        "message_id": message_id,
        "channel": "telegram",
        "delivery_state": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "dos_score": vehicle.get("score_breakdown", {}).get("dos_score", vehicle.get("dos_score", 0)),
        "vehicle_title": (
            f"{vehicle.get('year', '')} {vehicle.get('make', '')} {vehicle.get('model', '')}".strip()
            or vehicle.get("title")
        ),
    }

    try:
        supabase_client.table("alert_log").insert(row).execute()
        return True
    except Exception as e:
        logger.error(f"[ALERT_LOG] Failed to write receipt for run_id={vehicle.get('run_id')}: {e}")
        return False


def _rover_actions_base_url() -> str:
    return resolve_rover_actions_base_url(os.environ)


async def _submit_rover_action(opportunity_id: str, action: str, user_id: str) -> None:
    import httpx

    payload = {
        "opportunity_id": opportunity_id,
        "action": action,
        "user_id": user_id,
    }
    internal_secret = get_config("INTERNAL_API_SECRET") or ""
    headers = {"X-Internal-Secret": internal_secret} if internal_secret else {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{_rover_actions_base_url()}/api/rover/actions", json=payload, headers=headers)
        resp.raise_for_status()


@telegram_router.post("/callback")
async def telegram_callback_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """Handle Telegram callback_query webhooks for BUY/WATCH/PASS deal buttons."""
    if not verify_telegram_secret_header(x_telegram_bot_api_secret_token):
        logger.warning("[TELEGRAM_AUTH] rejected callback: invalid or missing secret token")
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    callback_query = payload.get("callback_query") or {}
    callback_id = callback_query.get("id")
    callback_data = callback_query.get("data") or ""
    from_user = callback_query.get("from") or {}
    telegram_user_id = from_user.get("id")

    if not callback_id or not callback_data:
        raise HTTPException(status_code=400, detail="Invalid Telegram callback payload")

    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot token not configured")

    action = None
    opportunity_id = None
    if callback_data.startswith("buy_"):
        action = "buy"
        opportunity_id = callback_data.removeprefix("buy_").strip()
    elif callback_data.startswith("watch_"):
        action = "watch"
        opportunity_id = callback_data.removeprefix("watch_").strip()
    elif callback_data.startswith("pass_"):
        action = "pass"
        opportunity_id = callback_data.removeprefix("pass_").strip()
    else:
        raise HTTPException(status_code=400, detail="Unsupported Telegram callback action")

    if not opportunity_id:
        raise HTTPException(status_code=400, detail="Missing opportunity id in callback data")

    try:
        uuid.UUID(opportunity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid opportunity id")

    async def _answer_callback(text: str) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": text,
                    "show_alert": False,
                },
            )
            resp.raise_for_status()

    operator_user_id = resolve_operator_user_id(telegram_user_id)
    if not operator_user_id:
        logger.warning(
            "[TELEGRAM_AUTH] rejected unknown operator telegram_user_id=%s",
            telegram_user_id,
        )
        await _answer_callback("Unauthorized operator")
        raise HTTPException(status_code=403, detail="Unauthorized Telegram operator")

    callback_text = "Recorded"
    try:
        await _submit_rover_action(
            opportunity_id=opportunity_id,
            action=action,
            user_id=operator_user_id,
        )
        callback_text = f"Recorded {action}"
        logger.info(
            "[TELEGRAM_AUDIT] action=%s opportunity_id=%s operator_user_id=%s telegram_user_id=%s",
            action,
            opportunity_id,
            operator_user_id,
            telegram_user_id,
        )
    except Exception as exc:
        logger.warning(
            "[TELEGRAM] callback processing failed action=%s opportunity_id=%s operator_user_id=%s telegram_user_id=%s: %s",
            action,
            opportunity_id,
            operator_user_id,
            telegram_user_id,
            exc,
        )
        callback_text = "Callback recorded with a warning"

    try:
        await _answer_callback(callback_text)
    except Exception as exc:
        logger.warning("[TELEGRAM] answerCallbackQuery failed: %s", exc)

    return {
        "ok": True,
        "action": action,
        "opportunity_id": opportunity_id,
        "telegram_user_id": telegram_user_id,
    }


async def send_telegram_alerts(hot_deals: list) -> None:
    """Send Telegram alerts for hot deals (DOS >= 80) and store receipts."""
    for deal in hot_deals:
        await send_telegram_alert(deal)


def _alert_validation_mmr_estimate(deal: dict) -> Any:
    return alert_validation_mmr_estimate(deal)


def _build_alert_validation_prompt(deal: dict) -> str:
    return build_alert_validation_prompt(deal)


async def ai_validate_hot_deals(deals: list) -> list:
    """Deterministically validate alert-gated hot deals before delivery.

    The model lane is now advisory only. A missing/invalid OpenRouter route or
    upstream API outage must not silently suppress every deterministic alert;
    the inspectable alert gate is the safety boundary.
    """
    if not deals:
        return []

    import httpx

    validated_deals: list = []
    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = OPENROUTER_API_KEY
    if not api_key and _openrouter_legacy_deepseek_fallback_enabled():
        api_key = DEEPSEEK_API_KEY

    if not api_key:
        logger.warning(
            "[AI_VALIDATE] result=BYPASS reason=missing_openrouter_api_key count=%s",
            len(deals),
        )
        return deals

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": _APP_PUBLIC_URL,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for deal in deals:
            deal_id = deal.get("id") or deal.get("opportunity_id") or deal.get("listing_id") or "unknown"
            try:
                lane, model = _resolve_openrouter_lane_model(deal, str(deal_id))
            except Exception as exc:
                logger.warning(
                    "[AI_VALIDATE] deal_id=%s result=BYPASS reason=invalid_route error=%s",
                    deal_id,
                    exc,
                )
                validated_deals.append(deal)
                continue

            prompt = _build_alert_validation_prompt(deal)

            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            }

            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = (
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                first_line = content.splitlines()[0].strip() if content else ""
                verdict_match = re.search(r"\b(VALID|INVALID)\b", first_line, re.IGNORECASE) or re.search(
                    r"\b(VALID|INVALID)\b", content, re.IGNORECASE
                )
                verdict = verdict_match.group(1).upper() if verdict_match else ""
                reason = (
                    (content[verdict_match.end():] if verdict_match else content).strip(" :-")
                    if content
                    else ""
                )

                if verdict == "VALID":
                    logger.info(
                        "[AI_VALIDATE] deal_id=%s lane=%s model=%s result=VALID reason=%s",
                        deal_id,
                        lane,
                        model,
                        reason or "validated by model",
                    )
                    validated_deals.append(deal)
                elif verdict == "INVALID":
                    logger.warning(
                        "[AI_VALIDATE] deal_id=%s lane=%s model=%s result=INVALID reason=%s",
                        deal_id,
                        lane,
                        model,
                        reason or "rejected by model",
                    )
                else:
                    logger.warning(
                        "[AI_VALIDATE] deal_id=%s lane=%s model=%s result=BYPASS reason=unparseable_response content=%s",
                        deal_id,
                        lane,
                        model,
                        content,
                    )
                    validated_deals.append(deal)
            except Exception as exc:
                logger.warning(
                    "[AI_VALIDATE] deal_id=%s lane=%s model=%s result=BYPASS reason=api_error error=%s",
                    deal_id,
                    lane,
                    model,
                    exc,
                )
                validated_deals.append(deal)

    return validated_deals





def _insert_webhook_log_direct_pg(row: dict) -> Optional[str]:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.webhook_log
                  (source, actor_id, run_id, item_count, raw_payload, processing_status, error_message)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    row.get("source"),
                    row.get("actor_id"),
                    row.get("run_id"),
                    row.get("item_count"),
                    psycopg2_extras.Json(row.get("raw_payload")),
                    row.get("processing_status"),
                    row.get("error_message"),
                ),
            )
            inserted = cur.fetchone()
            return str(inserted[0]) if inserted and inserted[0] else None


def _update_webhook_log_direct_pg(webhook_log_id: str, update_row: dict) -> None:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update public.webhook_log
                set processing_status = %s,
                    error_message = %s,
                    item_count = coalesce(%s, item_count)
                where id = %s
                returning id
                """,
                (
                    update_row.get("processing_status"),
                    update_row.get("error_message"),
                    update_row.get("item_count"),
                    webhook_log_id,
                ),
            )
            updated = cur.fetchone()
            if not updated:
                raise RuntimeError(f"webhook_log row {webhook_log_id} not found for update")


def _find_recent_webhook_replay_direct_pg(run_id: str, cutoff: datetime) -> list[dict]:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG replay lookup fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
            cur.execute(
                """
                select id, received_at, processing_status, error_message
                from public.webhook_log
                where run_id = %s
                  and received_at >= %s
                order by received_at desc
                limit 5
                """,
                (run_id, cutoff),
            )
            return [dict(row) for row in cur.fetchall()]


def _delivery_log_lookup(run_id: str, listing_id: str, channel: str) -> Optional[dict]:
    if supabase_client is None or not run_id or not listing_id or not channel:
        return None
    try:
        result = (
            supabase_client.table("ingest_delivery_log")
            .select("id,status,attempt_count,external_id")
            .eq("run_id", run_id)
            .eq("listing_id", listing_id)
            .eq("channel", channel)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.warning("[DELIVERY_LOG] lookup failed for %s/%s/%s: %s", run_id, listing_id, channel, e)
    return None


def _record_delivery_log(
    *,
    run_id: str,
    listing_id: str,
    channel: str,
    status: str,
    listing_url: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    external_id: Optional[str] = None,
    error_message: Optional[str] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> bool:
    if not run_id or not listing_id or not channel:
        if require_durable:
            raise CriticalAuditWriteError(
                "critical ingest_delivery_log write missing run_id, listing_id, or channel"
            )
        return False
    row = build_delivery_log_row(
        run_id=run_id,
        listing_id=listing_id,
        listing_url=listing_url,
        opportunity_id=opportunity_id,
        channel=channel,
        status=status,
        external_id=external_id,
        error_message=error_message,
    )
    primary_error: Optional[Exception] = None
    try:
        if supabase_client is not None:
            existing = _delivery_log_lookup(run_id, listing_id, channel)
            if existing and existing.get("id"):
                update_row = build_delivery_log_update_row(row, existing)
                (
                    supabase_client.table("ingest_delivery_log")
                    .update(update_row)
                    .eq("id", existing["id"])
                    .execute()
                )
            else:
                insert_row = build_delivery_log_insert_row(row)
                supabase_client.table("ingest_delivery_log").insert(insert_row).execute()
            return False
    except Exception as exc:
        primary_error = exc

    try:
        fallback_label = "ingest_delivery_log_direct_pg"
        fallback_row = dict(row)
        fallback_row["error_message"] = merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        _upsert_delivery_log_direct_pg(fallback_row)
        record_audit_fallback(audit_state, fallback_label)
        return True
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                format_audit_failure(
                    surface="ingest_delivery_log",
                    operation="upsert",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning(
                "[DELIVERY_LOG] record failed for %s/%s/%s: %s",
                run_id,
                listing_id,
                channel,
                primary_error,
            )
        logger.warning(
            "[DELIVERY_LOG] direct PG fallback failed for %s/%s/%s: %s",
            run_id,
            listing_id,
            channel,
            fallback_error,
        )
        return False


# Listing identity helper is imported from backend.ingest.listing_identity.


def _upsert_delivery_log_direct_pg(row: dict) -> None:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.ingest_delivery_log
                  (run_id, listing_id, listing_url, opportunity_id, channel, status, external_id,
                   error_message, attempt_count, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                on conflict (run_id, listing_id, channel)
                do update set
                  listing_url = excluded.listing_url,
                  opportunity_id = excluded.opportunity_id,
                  status = excluded.status,
                  external_id = excluded.external_id,
                  error_message = excluded.error_message,
                  updated_at = excluded.updated_at,
                  attempt_count = public.ingest_delivery_log.attempt_count + 1
                """,
                (
                    row.get("run_id"),
                    row.get("listing_id"),
                    row.get("listing_url"),
                    row.get("opportunity_id"),
                    row.get("channel"),
                    row.get("status"),
                    row.get("external_id"),
                    row.get("error_message"),
                    row.get("created_at") or row.get("updated_at"),
                    row.get("updated_at"),
                ),
            )


def _apply_canonical_update(canonical_update: Optional[dict]) -> bool:
    if supabase_client is None or not canonical_update or not canonical_update.get("id"):
        return False
    try:
        (
            supabase_client.table("opportunities")
            .update({
                "all_sources": canonical_update.get("all_sources") or [],
                "duplicate_count": canonical_update.get("duplicate_count") or 0,
            })
            .eq("id", canonical_update["id"])
            .execute()
        )
        return True
    except Exception as e:
        logger.warning("[DEDUP] canonical update failed for %s: %s", canonical_update.get("id"), e)
        return False


def _lookup_existing_canonical_opportunity(canonical_id: Optional[str]) -> Optional[dict]:
    if not canonical_id:
        return None

    if supabase_client is not None:
        try:
            lookup = (
                supabase_client.table("opportunities")
                .select("id, all_sources")
                .eq("canonical_id", canonical_id)
                .eq("is_duplicate", False)
                .limit(1)
                .execute()
            )
            if lookup.data:
                row = lookup.data[0]
                return {
                    "id": row.get("id"),
                    "all_sources": row.get("all_sources") or [],
                }
        except Exception as lookup_err:
            logger.warning("[DEDUP] Supabase canonical lookup failed: %s", lookup_err)

    if not _direct_supabase_db_url:
        return None

    try:
        with psycopg2.connect(_direct_supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, all_sources
                    from public.opportunities
                    where canonical_id = %s and is_duplicate = false
                    limit 1
                    """,
                    (canonical_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return {
                        "id": str(row[0]),
                        "all_sources": list(row[1] or []),
                    }
    except Exception as lookup_err:
        logger.warning("[DEDUP] Direct PG canonical lookup failed: %s", lookup_err)
    return None


def _finalize_duplicate_recovery(vehicle: dict, canonical_row: dict, canonical_update: Optional[dict]) -> None:
    vehicle["is_duplicate"] = True
    vehicle["canonical_record_id"] = canonical_row["id"]
    if canonical_update and _apply_canonical_update(canonical_update):
        logger.info("[DEDUP] canonical source update applied for %s", canonical_row["id"])


def _existing_enrichment_snapshot(existing_id: str) -> dict:
    if supabase_client is None:
        return {}
    try:
        result = (
            supabase_client.table("opportunities")
            .select("vin,mileage,condition_grade,raw_data,source_run_id,run_id")
            .eq("id", existing_id)
            .limit(1)
            .execute()
        )
        rows = getattr(result, "data", None) or []
        return rows[0] if rows else {}
    except Exception as lookup_err:
        logger.warning(
            "[INGEST] Duplicate enrichment lookup failed for %s: %s",
            existing_id,
            lookup_err,
        )
        return {}


_PRICING_MATURITY_RANK = {
    "": 0,
    "unknown": 0,
    "proxy": 1,
    "market_comp": 2,
    "live_market": 3,
}


_PRICING_TRUTH_REFRESH_FIELDS = (
    "dos_score",
    "current_bid",
    "mmr",
    "estimated_transport",
    "buyer_premium",
    "auction_fees",
    "recon_reserve",
    "total_cost",
    "projected_total_cost",
    "acquisition_price_basis",
    "acquisition_basis_source",
    "gross_margin",
    "retail_asking_price_estimate",
    "retail_comp_price_estimate",
    "retail_comp_low",
    "retail_comp_high",
    "retail_comp_count",
    "retail_comp_confidence",
    "pricing_source",
    "pricing_maturity",
    "pricing_updated_at",
    "expected_close_bid",
    "current_bid_trust_score",
    "expected_close_source",
    "auction_stage_hours_remaining",
    "manheim_mmr_mid",
    "manheim_mmr_low",
    "manheim_mmr_high",
    "manheim_range_width_pct",
    "manheim_confidence",
    "manheim_source_status",
    "manheim_updated_at",
    "retail_proxy_multiplier",
    "ctm_pct",
    "wholesale_ctm_pct",
    "retail_ctm_pct",
    "segment_tier",
    "estimated_days_to_sale",
    "roi_per_day",
    "mmr_lookup_basis",
    "mmr_confidence_proxy",
    "investment_grade",
    "max_bid",
    "bid_headroom",
    "ceiling_reason",
    "score_version",
    "legacy_dos_score",
    "designated_lane",
    "dos_premium",
    "dos_standard",
    "risk_flags",
    "vehicle_tier",
    "bid_ceiling_pct",
    "min_margin_target",
    "pipeline_step",
    "step_status",
    "processed_at",
    "run_id",
    "source_run_id",
)


def _pricing_maturity_rank(value: Optional[str]) -> int:
    return _PRICING_MATURITY_RANK.get(str(value or "").lower(), 0)


def _existing_pricing_truth_snapshot(existing_id: str) -> dict:
    if supabase_client is None:
        return {}
    try:
        result = (
            supabase_client.table("opportunities")
            .select("pricing_maturity,pricing_source,pricing_updated_at")
            .eq("id", existing_id)
            .limit(1)
            .execute()
        )
        rows = getattr(result, "data", None) or []
        return rows[0] if rows else {}
    except Exception as lookup_err:
        logger.warning(
            "[INGEST] Duplicate pricing truth lookup failed for %s: %s",
            existing_id,
            lookup_err,
        )
        return {}


def _duplicate_pricing_truth_update(row: dict, existing: Optional[dict] = None) -> dict:
    """Return scoring/pricing fields when a duplicate row has stronger pricing truth.

    Existing live rows should not stay proxy-priced when a fresh ingest computes
    market-comp/live-market evidence. This intentionally excludes identity,
    listing URL, VIN, mileage, and raw detail fields; those remain governed by
    the enrichment backfill path.
    """
    existing = existing or {}
    incoming_rank = _pricing_maturity_rank(row.get("pricing_maturity"))
    existing_rank = _pricing_maturity_rank(existing.get("pricing_maturity"))
    if incoming_rank <= existing_rank:
        return {}

    update = {
        field: row.get(field)
        for field in _PRICING_TRUTH_REFRESH_FIELDS
        if row.get(field) not in (None, "", {}, [])
    }
    if not update:
        return {}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    return update


def _refresh_existing_opportunity_pricing_truth(existing_id: str, row: dict) -> bool:
    if supabase_client is None:
        return False
    if _pricing_maturity_rank(row.get("pricing_maturity")) <= 1:
        return False
    existing = _existing_pricing_truth_snapshot(existing_id)
    update_payload = _duplicate_pricing_truth_update(row, existing)
    if not update_payload:
        return False
    try:
        supabase_client.table("opportunities").update(update_payload).eq("id", existing_id).execute()
        logger.info(
            "[INGEST] Refreshed pricing truth for duplicate opportunity %s: %s",
            existing_id,
            sorted(update_payload.keys()),
        )
        return True
    except Exception as update_err:
        logger.warning(
            "[INGEST] Duplicate pricing truth refresh failed for %s: %s",
            existing_id,
            update_err,
        )
        return False


def _duplicate_enrichment_update(row: dict, existing: Optional[dict] = None) -> dict:
    """Return missing enrichment fields worth backfilling onto an existing row.

    This is intentionally narrow: duplicate recovery must not rewrite score, bid,
    grade, pricing truth, or existing enrichment evidence. It only carries source-
    detail evidence into fields that are currently empty on the existing row.
    """
    existing = existing or {}
    update: dict = {}
    for key in (
        "vin",
        "mileage",
        "condition_grade",
        "source_run_id",
        "run_id",
    ):
        value = row.get(key)
        current_value = existing.get(key)
        if value not in (None, "", {}, []) and current_value in (None, "", {}, []):
            update[key] = value
    incoming_raw = row.get("raw_data")
    existing_raw = existing.get("raw_data")
    if isinstance(incoming_raw, dict):
        if not isinstance(existing_raw, dict) or existing_raw in ({}, []):
            update["raw_data"] = incoming_raw
        else:
            merged_raw = dict(existing_raw)
            for key, value in incoming_raw.items():
                if value not in (None, "", {}, []) and merged_raw.get(key) in (None, "", {}, []):
                    merged_raw[key] = value
            if merged_raw != existing_raw:
                update["raw_data"] = merged_raw
    if update:
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
    return update


def _backfill_existing_opportunity_enrichment(existing_id: str, row: dict) -> None:
    if supabase_client is None:
        return
    existing = _existing_enrichment_snapshot(existing_id)
    update_payload = _duplicate_enrichment_update(row, existing)
    if not update_payload:
        return
    try:
        supabase_client.table("opportunities").update(update_payload).eq("id", existing_id).execute()
        logger.info(
            "[INGEST] Backfilled missing enrichment fields for duplicate opportunity %s: %s",
            existing_id,
            sorted(update_payload.keys()),
        )
    except Exception as update_err:
        logger.warning(
            "[INGEST] Duplicate enrichment backfill failed for %s: %s",
            existing_id,
            update_err,
        )


def _lookup_existing_opportunity_id(listing_url: str, listing_id: str) -> Optional[str]:
    if supabase_client is not None:
        try:
            if listing_url:
                lookup = (
                    supabase_client.table("opportunities")
                    .select("id")
                    .eq("listing_url", listing_url)
                    .limit(1)
                    .execute()
                )
                if lookup.data:
                    return lookup.data[0].get("id")
            if listing_id:
                lookup = (
                    supabase_client.table("opportunities")
                    .select("id")
                    .eq("listing_id", listing_id)
                    .limit(1)
                    .execute()
                )
                if lookup.data:
                    return lookup.data[0].get("id")
        except Exception as lookup_err:
            logger.warning("[INGEST] Supabase lookup fallback failed: %s", lookup_err)

    if not _direct_supabase_db_url:
        return None

    try:
        with psycopg2.connect(_direct_supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id
                    from public.opportunities
                    where listing_url = %s or listing_id = %s
                    limit 1
                    """,
                    (listing_url, listing_id),
                )
                row = cur.fetchone()
                return str(row[0]) if row and row[0] else None
    except Exception as lookup_err:
        logger.warning("[INGEST] Direct PG lookup fallback failed: %s", lookup_err)
        return None


def _insert_row_direct_pg(table_name: str, row: dict, *, returning_id: bool = True) -> Optional[str]:
    columns = list(row.keys())
    values = [prepare_direct_pg_value(row[column]) for column in columns]
    insert_sql = psycopg2_sql.SQL(
        "INSERT INTO public.{table} ({fields}) VALUES ({values}){returning_clause}"
    ).format(
        table=psycopg2_sql.Identifier(table_name),
        fields=psycopg2_sql.SQL(", ").join(psycopg2_sql.Identifier(column) for column in columns),
        values=psycopg2_sql.SQL(", ").join(psycopg2_sql.Placeholder() for _ in columns),
        returning_clause=psycopg2_sql.SQL(" RETURNING id") if returning_id else psycopg2_sql.SQL(""),
    )

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql, values)
            if not returning_id:
                return None
            inserted = cur.fetchone()
            return str(inserted[0]) if inserted and inserted[0] else None


def _insert_opportunity_direct_pg(row: dict) -> Optional[str]:
    return _insert_row_direct_pg("opportunities", row, returning_id=True)


def _save_dealer_sale_direct_pg(row: dict) -> tuple[bool, str]:
    if not _direct_supabase_db_url:
        logger.warning(
            "[DEALER_SALES] Direct PG fallback unavailable; set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD."
        )
        return False, "direct_pg_unavailable"

    try:
        _insert_row_direct_pg("dealer_sales", row, returning_id=False)
        return True, "saved_direct_pg"
    except Exception as pg_err:
        logger.error(
            "[DEALER_SALES] Direct PG save FAILED for '%s': %s",
            f"{row.get('year') or ''} {row.get('make') or ''} {row.get('model') or ''}".strip()[:80] or "unknown",
            pg_err,
        )
        return False, "direct_pg_error"


def _save_opportunity_direct_pg(row: dict) -> tuple[Optional[str], str]:
    if not _direct_supabase_db_url:
        logger.warning(
            "[INGEST] Direct PG fallback unavailable; set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD."
        )
        return None, "direct_pg_unavailable"

    try:
        return _insert_opportunity_direct_pg(row), "saved_direct_pg"
    except psycopg2.errors.UniqueViolation as pg_err:
        error_text = getattr(pg_err, "pgerror", None) or str(pg_err)
        if is_canonical_unique_conflict(error_text):
            canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
            if canonical_row:
                duplicate_row, canonical_update = build_duplicate_recovery_payload(row, canonical_row)
                try:
                    duplicate_id = _insert_opportunity_direct_pg(duplicate_row)
                    if canonical_update:
                        _apply_canonical_update(canonical_update)
                    return duplicate_id, "saved_direct_pg_duplicate"
                except Exception as recovery_err:
                    logger.warning(
                        "[DEDUP] Direct PG duplicate recovery failed for canonical_id=%s: %s",
                        row.get("canonical_id"),
                        recovery_err,
                    )
        existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
        if existing_id:
            return existing_id, "duplicate_existing"
        return None, "duplicate_unresolved"
    except Exception as pg_err:
        logger.error(
            "[INGEST] Direct PG save FAILED for '%s': %s",
            (row.get("title") or "unknown")[:80],
            pg_err,
        )
        return None, "direct_pg_error"


def _normalize_vin(vin: Optional[str]) -> Optional[str]:
    return normalize_vin(vin)


def _check_vin_duplicate(vin: str, new_dos_score: float) -> tuple[Optional[str], bool]:
    try:
        return check_vin_duplicate(vin, new_dos_score, supabase_client=supabase_client)
    except Exception as vin_check_err:
        logger.warning("[DEDUP] VIN duplicate check failed for VIN %s: %s", vin, vin_check_err)
        raise


def _save_to_sonar_listings(vehicle: dict) -> None:
    """Write a simplified record to sonar_listings — NO filters (DOS, state, mileage)."""
    if supabase_client is None:
        return
    supabase_client.table("sonar_listings").insert(build_sonar_listing_row(vehicle)).execute()


async def save_opportunity_to_supabase(vehicle: dict) -> Optional[str]:
    """Save scored vehicle to Supabase. Min DOS 50 to save."""
    score = vehicle.get("dos_score", 0)
    if score < 50:
        _mark_save_outcome(vehicle, "below_save_threshold")
        return None

    row = build_opportunity_row(vehicle)

    # Normalize VIN before dedup check and insert
    raw_vin = row.get("vin")
    normalized_vin = _normalize_vin(raw_vin)
    if normalized_vin != raw_vin:
        row["vin"] = normalized_vin

    # VIN deduplication check — skip the item if the lookup fails.
    if normalized_vin:
        try:
            existing_id, should_update = _check_vin_duplicate(normalized_vin, float(score))
            if existing_id:
                _backfill_existing_opportunity_enrichment(existing_id, row)
                if should_update:
                    # New score is higher — update the existing record
                    try:
                        update_payload = {
                            "dos_score": row.get("dos_score"),
                            "current_bid": row.get("current_bid"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        supabase_client.table("opportunities").update(update_payload).eq("id", existing_id).execute()
                        logger.info(
                            "[DEDUP] VIN %s updated existing record %s with higher DOS score %.1f",
                            normalized_vin, existing_id, float(score),
                        )
                        _mark_save_outcome(vehicle, "vin_dedup_updated", opportunity_id=existing_id)
                        return existing_id
                    except Exception as upd_err:
                        logger.warning("[DEDUP] VIN update failed for %s: %s", existing_id, upd_err)
                        _mark_save_outcome(vehicle, "vin_dedup_skipped", opportunity_id=existing_id, error_message=str(upd_err))
                        return existing_id
                else:
                    logger.warning(
                        "[DEDUP] Duplicate VIN %s skipped — already exists as %s",
                        normalized_vin, existing_id,
                    )
                    if _refresh_existing_opportunity_pricing_truth(existing_id, row):
                        _mark_save_outcome(vehicle, "vin_dedup_pricing_refreshed", opportunity_id=existing_id)
                    else:
                        _mark_save_outcome(vehicle, "vin_dedup_skipped", opportunity_id=existing_id)
                    return existing_id
        except Exception as dedup_err:
            logger.warning("[DEDUP] VIN dedup logic error for VIN %s: %s", normalized_vin, dedup_err)
            raise

    if supabase_client is not None:
        try:
            result = supabase_client.table("opportunities").insert(row).execute()
            if result.data:
                saved_id = result.data[0].get("id")
                _mark_save_outcome(vehicle, "saved_supabase", opportunity_id=saved_id)
                return saved_id

            existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
            if existing_id:
                _backfill_existing_opportunity_enrichment(existing_id, row)
                if _refresh_existing_opportunity_pricing_truth(existing_id, row):
                    _mark_save_outcome(vehicle, "duplicate_pricing_refreshed", opportunity_id=existing_id)
                else:
                    _mark_save_outcome(vehicle, "duplicate_existing", opportunity_id=existing_id)
                return existing_id
        except Exception as e:
            title = vehicle.get("title", "unknown")[:80]
            logger.error(f"[INGEST] Supabase save FAILED for '{title}': {e}")
            error_text = str(e)
            if "23505" in error_text or "duplicate key value" in error_text:
                if is_canonical_unique_conflict(error_text):
                    canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
                    if canonical_row:
                        duplicate_row, canonical_update = build_duplicate_recovery_payload(row, canonical_row)
                        try:
                            retry = supabase_client.table("opportunities").insert(duplicate_row).execute()
                            if retry.data:
                                _finalize_duplicate_recovery(vehicle, canonical_row, canonical_update)
                                saved_id = retry.data[0].get("id")
                                _mark_save_outcome(vehicle, "saved_supabase_duplicate", opportunity_id=saved_id)
                                return saved_id
                        except Exception as retry_err:
                            logger.warning(
                                "[DEDUP] Supabase duplicate recovery failed for '%s': %s",
                                title,
                                retry_err,
                            )
                existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
                if existing_id:
                    logger.info("[INGEST] Duplicate existing listing recovered for '%s'", title)
                    _backfill_existing_opportunity_enrichment(existing_id, row)
                    if _refresh_existing_opportunity_pricing_truth(existing_id, row):
                        _mark_save_outcome(vehicle, "duplicate_pricing_refreshed", opportunity_id=existing_id)
                    else:
                        _mark_save_outcome(vehicle, "duplicate_existing", opportunity_id=existing_id)
                    return existing_id
                _mark_save_outcome(vehicle, "duplicate_unresolved", error_message=error_text)
                return None
            logger.warning(
                "[INGEST] Falling back to direct Postgres insert for '%s' after Supabase write failure.",
                title,
            )
    else:
        logger.warning("[INGEST] Supabase client unavailable; using direct Postgres fallback if configured.")

    saved_id, save_status = _save_opportunity_direct_pg(row)
    if save_status == "saved_direct_pg_duplicate":
        canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
        if canonical_row:
            vehicle["is_duplicate"] = True
            vehicle["canonical_record_id"] = canonical_row["id"]
    _mark_save_outcome(vehicle, save_status, opportunity_id=saved_id)
    return saved_id


def _mark_save_outcome(
    vehicle: dict,
    status: str,
    *,
    opportunity_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    mark_save_outcome(
        vehicle,
        status,
        opportunity_id=opportunity_id,
        error_message=error_message,
    )


def build_opportunity_row(vehicle: dict) -> dict:
    return _build_opportunity_row(
        vehicle,
        canonical_source_site=_canonical_source_site,
        compute_listing_id=_compute_listing_id,
        compute_condition_grade=_compute_condition_grade,
    )
