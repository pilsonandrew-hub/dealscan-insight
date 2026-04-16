"""
Analytics summary endpoint.
GET /api/analytics/summary — aggregates KPIs from Supabase.

Uses the opportunities table which now carries outcome_* columns,
and the alert_log table for alert delivery stats.
"""
try:
    from fastapi import APIRouter, HTTPException, Header
except ModuleNotFoundError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @staticmethod
        def _decorator(*_args, **_kwargs):
            def wrapper(func):
                return func
            return wrapper

        get = post = patch = delete = put = _decorator

    def Header(default=None):
        return default
from typing import Optional

from webapp.routers.outcomes import _verify_auth
from webapp.database import supabase_client
import os
import logging
import json
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib import request, error

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

SOURCE_ACTOR_MAP = {
    "ds-govdeals": {"actor_id": "CuKaIAcWyFS0EPrAz", "source_site": "govdeals"},
    "ds-publicsurplus": {"actor_id": "9xxQLlRsROnSgA42i", "source_site": "publicsurplus"},
    "ds-municibid": {"actor_id": "svmsItf3CRBZuIntp", "source_site": "municibid"},
    "ds-gsaauctions": {"actor_id": "fvDnYmGuFBCrwpEi9", "source_site": "gsaauctions"},
    "ds-allsurplus": {"actor_id": "gYGIfHeYeN3EzmLnB", "source_site": "allsurplus"},
    "ds-govplanet": {"actor_id": "pO2t5UDoSVmO1gvKJ", "source_site": "govplanet"},
    "ds-proxibid": {"actor_id": "bxhncvtHEP712WX2e", "source_site": "proxibid"},
    "ds-equipmentfacts": {"actor_id": "0XjoegYZVcPldLstl", "source_site": "equipmentfacts"},
    "ds-usgovbid": {"actor_id": "6XO9La81aEmtsCT3g", "source_site": "usgovbid"},
    "ds-jjkane": {"actor_id": "lvb7T6VMFfNUQpqlq", "source_site": "jjkane"},
    "ds-hibid-v2": {"actor_id": "7s9e0eATTt1kuGGfE", "source_site": "hibid"},
    "ds-bidspotter": {"actor_id": "5Eu3hfCcBBdzp6I1u", "source_site": "bidspotter"},
}
ACTOR_TO_SOURCE = {details["actor_id"]: details["source_site"] for details in SOURCE_ACTOR_MAP.values()}

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY", "")
)

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supa = create_client(_supabase_url, _supabase_key)
        logger.info("[ANALYTICS] Supabase client initialised")
    else:
        logger.warning("[ANALYTICS] Supabase env vars not set — analytics will return zeros")
except Exception as _e:
    logger.warning(f"[ANALYTICS] Supabase client init failed (non-fatal): {_e}")


def _safe_avg(values: list, field: str) -> Optional[float]:
    """Return average of a numeric field from a list of dicts, ignoring None."""
    nums = [float(r[field]) for r in values if r.get(field) is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def _build_execution_notes(*, pending_outcomes, ceiling_compliance) -> list[str]:
    notes = [
        "Execution counts use dealer_sales outcome states",
        "Bid pricing metrics come from explicit bid outcome records",
    ]
    if pending_outcomes is None:
        notes.append("Pending outcomes remain undefined where no canonical lifecycle state is available")
    if ceiling_compliance is None:
        notes.append("Ceiling compliance is partial and only computed where purchase price and max bid both exist")
    return notes


FRESHNESS_STALE_THRESHOLD_SECONDS = 86400
# Keep the 24h cutoff aligned with the frontend trust summary for this sweep.
# Changing the threshold would alter alerting semantics, so leave it untouched.


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _build_freshness_entry(*, updated_at: Optional[datetime], has_records: bool, query_failed: bool = False) -> dict:
    # Empty means there are no underlying records to judge.
    # Unknown means we expected data, but the timestamp is missing or the query failed.
    if not has_records:
        return {
            "updated_at": None,
            "age_seconds": None,
            "status": "empty",
        }
    if query_failed:
        return {
            "updated_at": None,
            "age_seconds": None,
            "status": "unknown",
        }
    if updated_at is None:
        return {
            "updated_at": None,
            "age_seconds": None,
            "status": "unknown",
        }

    updated_at_utc = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    updated_at_utc = updated_at_utc.astimezone(timezone.utc)
    age_seconds = max(0, int((datetime.now(timezone.utc) - updated_at_utc).total_seconds()))
    return {
        "updated_at": updated_at_utc.isoformat(),
        "age_seconds": age_seconds,
        "status": "fresh" if age_seconds <= FRESHNESS_STALE_THRESHOLD_SECONDS else "stale",
    }


TRUST_RULE_REGISTRY = [
    {
        "id": "wins_without_recorded_outcomes",
        "severity": "high",
        "message": "Workflow counts show wins but no recorded outcomes exist",
        "condition": lambda ctx: ctx["total_wins"] > 0 and ctx["total_outcomes"] == 0,
    },
    {
        "id": "bid_activity_missing_bid_metrics",
        "severity": "high",
        "message": "Bid metrics are incomplete despite recorded bid activity",
        "condition": lambda ctx: ctx["total_bids"] > 0 and ctx["win_rate"] is None,
    },
    {
        "id": "wins_missing_purchase_price_support",
        "severity": "medium",
        "message": "Winning bid records exist without purchase-price support",
        "condition": lambda ctx: ctx["total_wins"] > 0 and ctx["avg_purchase_price"] is None,
    },
    {
        "id": "outcomes_missing_source_distribution",
        "severity": "high",
        "message": "Recorded outcomes exist without outcome-source distribution",
        "condition": lambda ctx: ctx["total_outcomes"] > 0 and not ctx["wins_by_source"],
    },
    {
        "id": "fresh_source_health_with_stale_execution_or_outcomes",
        "severity": "medium",
        "message": "System and source signals are current while execution/outcomes freshness is stale or empty",
        "condition": lambda ctx: ctx["pipeline_freshness_status"] == "fresh"
        and ctx["source_health_freshness_status"] == "fresh"
        and (
            ctx["execution_freshness_status"] in {"stale", "empty"}
            or ctx["outcomes_freshness_status"] in {"stale", "empty"}
        ),
    },
]


def _evaluate_trust_rules(
    *,
    total_wins,
    total_outcomes,
    total_bids,
    win_rate,
    avg_purchase_price,
    wins_by_source,
    source_health_status,
    freshness_age,
    freshness,
) -> list[dict]:
    rules: list[dict] = []
    ctx = {
        "total_wins": total_wins,
        "total_outcomes": total_outcomes,
        "total_bids": total_bids,
        "win_rate": win_rate,
        "avg_purchase_price": avg_purchase_price,
        "wins_by_source": wins_by_source,
        "source_health_status": source_health_status,
        "freshness_age": freshness_age,
        "pipeline_freshness_status": freshness["pipeline"]["status"],
        "source_health_freshness_status": freshness["source_health"]["status"],
        "execution_freshness_status": freshness["execution"]["status"],
        "outcomes_freshness_status": freshness["outcomes"]["status"],
    }
    for rule in TRUST_RULE_REGISTRY:
        try:
            if rule["condition"](ctx):
                rules.append({
                    "id": rule["id"],
                    "severity": rule["severity"],
                    "message": rule["message"],
                })
        except Exception as exc:
            logger.warning(f"[ANALYTICS] trust rule evaluation failed for {rule['id']}: {exc}")
    return rules


def _emit_trust_events(
    *,
    user_id: Optional[str],
    trust_status: str,
    trust_severity: str,
    trust_rule_ids: list[str],
    trust_notes: list[str],
    degraded_sections: list[str],
    completeness_score,
    summary_refreshed_at,
    freshness_age,
    freshness,
) -> dict:
    if trust_status != "degraded":
        return {
            "event": None,
            "paperclip": None,
        }

    event_name = "analytics_summary_degraded"
    if trust_rule_ids:
        event_name = "analytics_summary_rule_violation"
    elif completeness_score is not None and completeness_score < 0.5:
        event_name = "analytics_summary_low_completeness"

    event_payload = {
        "type": "analytics_trust_event",
        "event": event_name,
        "trustStatus": trust_status,
        "trustSeverity": trust_severity,
        "trustRuleIds": trust_rule_ids,
        "trustNotes": trust_notes,
        "degradedSections": degraded_sections,
        "completenessScore": completeness_score,
        "summaryRefreshedAt": summary_refreshed_at,
        "freshnessAge": freshness_age,
        "freshness": freshness,
    }

    logger.log(
        logging.ERROR if trust_severity == "high" else logging.WARNING if trust_severity == "medium" else logging.INFO,
        json.dumps(event_payload),
    )

    paperclip_result = _maybe_escalate_to_paperclip(
        user_id=user_id,
        trust_status=trust_status,
        trust_severity=trust_severity,
        trust_rule_ids=trust_rule_ids,
        trust_notes=trust_notes,
        degraded_sections=degraded_sections,
        completeness_score=completeness_score,
        summary_refreshed_at=summary_refreshed_at,
        freshness_age=freshness_age,
    )

    if paperclip_result:
        event_payload["paperclip"] = paperclip_result

    if supabase_client is not None:
        try:
            supabase_client.table("system_logs").insert({
                "level": "error" if trust_severity == "high" else "warn" if trust_severity == "medium" else "info",
                "message": f"Analytics trust event: {event_name}",
                "context": {
                    **event_payload,
                    "user_id": user_id,
                    "source": "analytics_summary",
                },
            }).execute()
        except Exception as exc:
            logger.warning(f"[ANALYTICS] failed to persist trust event: {exc}")

    return {
        "event": event_name,
        "paperclip": paperclip_result,
    }


def _paperclip_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _find_existing_paperclip_issue(*, paperclip_api_url: str, paperclip_api_key: str, company_id: str, correlation_key: str) -> Optional[dict]:
    req = request.Request(
        f"{paperclip_api_url}/api/companies/{company_id}/issues",
        headers=_paperclip_headers(paperclip_api_key),
        method="GET",
    )
    with request.urlopen(req, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    data = json.loads(raw)
    issues = data if isinstance(data, list) else data.get("items") or data.get("issues") or []
    needle = f"Correlation key: {correlation_key}"
    for issue in issues:
        if needle in (issue.get("description") or ""):
            return issue
    return None


def _maybe_escalate_to_paperclip(*, user_id: Optional[str], trust_status: str, trust_severity: str, trust_rule_ids: list[str], trust_notes: list[str], degraded_sections: list[str], completeness_score, summary_refreshed_at, freshness_age) -> Optional[dict]:
    if trust_status != "degraded" or trust_severity != "high" or not trust_rule_ids:
        return None

    if os.getenv("ANALYTICS_TRUST_ESCALATION_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
        logger.info("[ANALYTICS] Paperclip escalation disabled by ANALYTICS_TRUST_ESCALATION_ENABLED")
        return {
            "status": "disabled",
        }

    paperclip_api_url = os.getenv("PAPERCLIP_API_URL", "http://localhost:3100").rstrip("/")
    paperclip_api_key = os.getenv("PAPERCLIP_API_KEY")
    company_id = os.getenv("PAPERCLIP_COMPANY_ID")
    agent_id = os.getenv("PAPERCLIP_JAARIOUS_AGENT_ID")

    if not paperclip_api_key or not company_id or not agent_id:
        logger.warning("[ANALYTICS] skipping Paperclip escalation because Paperclip env is incomplete")
        return {
            "status": "skipped_missing_env",
        }

    correlation_key = f"analytics-trust:{'|'.join(sorted(set(trust_rule_ids)))}"
    title = f"Analytics trust high severity: {', '.join(trust_rule_ids)}"
    description = "\n".join([
        f"Correlation key: {correlation_key}",
        f"Trust status: {trust_status}",
        f"Trust severity: {trust_severity}",
        f"User ID: {user_id or 'unknown'}",
        f"Rule IDs: {', '.join(trust_rule_ids)}",
        f"Degraded sections: {', '.join(degraded_sections) if degraded_sections else 'none'}",
        f"Completeness score: {completeness_score}",
        f"Summary refreshed at: {summary_refreshed_at or 'unknown'}",
        f"Freshness age: {freshness_age if freshness_age is not None else 'unknown'}",
        "",
        "Trust notes:",
        *[f"- {note}" for note in trust_notes],
    ])

    try:
        existing_issue = _find_existing_paperclip_issue(
            paperclip_api_url=paperclip_api_url,
            paperclip_api_key=paperclip_api_key,
            company_id=company_id,
            correlation_key=correlation_key,
        )
        if existing_issue:
            issue_id = existing_issue.get("id")
            patch_payload = {
                "description": description,
                "comment": "Analytics trust event repeated with the same correlation key. Refreshed evidence attached.",
                "priority": "high",
            }
            patch_req = request.Request(
                f"{paperclip_api_url}/api/issues/{issue_id}",
                data=json.dumps(patch_payload).encode("utf-8"),
                headers=_paperclip_headers(paperclip_api_key),
                method="PATCH",
            )
            with request.urlopen(patch_req, timeout=15) as response:
                response_body = response.read().decode("utf-8", errors="ignore")
            logger.info(json.dumps({
                "type": "analytics_trust_event_escalation",
                "status": "issue_updated",
                "issueId": issue_id,
                "correlationKey": correlation_key,
                "trustRuleIds": trust_rule_ids,
                "trustSeverity": trust_severity,
                "paperclipApiUrl": paperclip_api_url,
                "responsePreview": response_body[:400],
            }))
            issue_status = existing_issue.get("status")
            return {
                "status": "issue_updated",
                "issue_id": issue_id,
                "identifier": existing_issue.get("identifier"),
                "title": existing_issue.get("title"),
                "issue_status": issue_status,
                "correlation_key": correlation_key,
                "is_open": bool(issue_status and issue_status.lower() not in {"done", "closed", "resolved", "cancelled"}),
            }

        payload = {
            "title": title,
            "description": description,
            "status": "backlog",
            "priority": "high",
            "assigneeAgentId": agent_id,
        }
        create_req = request.Request(
            f"{paperclip_api_url}/api/companies/{company_id}/issues",
            data=json.dumps(payload).encode("utf-8"),
            headers=_paperclip_headers(paperclip_api_key),
            method="POST",
        )
        with request.urlopen(create_req, timeout=15) as response:
            response_body = response.read().decode("utf-8", errors="ignore")
        created_issue = json.loads(response_body) if response_body else {}
        logger.info(json.dumps({
            "type": "analytics_trust_event_escalation",
            "status": "issue_created",
            "correlationKey": correlation_key,
            "trustRuleIds": trust_rule_ids,
            "trustSeverity": trust_severity,
            "paperclipApiUrl": paperclip_api_url,
            "responsePreview": response_body[:400],
        }))
        issue_status = created_issue.get("status")
        return {
            "status": "issue_created",
            "issue_id": created_issue.get("id"),
            "identifier": created_issue.get("identifier"),
            "title": created_issue.get("title") or title,
            "issue_status": issue_status,
            "correlation_key": correlation_key,
            "is_open": bool(issue_status and issue_status.lower() not in {"done", "closed", "resolved", "cancelled"}),
        }
    except error.HTTPError as exc:
        logger.warning(f"[ANALYTICS] Paperclip issue escalation failed with HTTP {exc.code}: {exc.reason}")
        return {
            "status": "failed_http",
            "correlation_key": correlation_key,
        }
    except Exception as exc:
        logger.warning(f"[ANALYTICS] Paperclip issue escalation failed: {exc}")
        return {
            "status": "failed_exception",
            "correlation_key": correlation_key,
        }


@router.get("/summary")
async def analytics_summary(authorization: Optional[str] = Header(None)):
    """
    Return high-level KPIs:
      - total_opportunities      (from opportunities table)
      - total_outcomes           (rows where outcome_recorded_at is not null)
      - avg_gross_margin         (avg gross_margin on outcome rows)
      - avg_roi_pct              (avg roi on outcome rows)
      - wins_by_source           (count of sold outcomes grouped by source)
      - top_makes                (top 5 makes by avg dos_score)
      - alerts_sent_last_30d     (count from alert_log where sent_at > now()-30d)
    """
    user_id = _verify_auth(authorization)
    now_iso = datetime.now(timezone.utc).isoformat()

    if supa is None:
        # Return zeroed structure so the UI still renders.
        # Execution/outcomes are intentionally marked empty here because the
        # summary has no records to judge, even though freshness timestamps are
        # unavailable in this no-DB path.
        freshness = {
            "pipeline": _build_freshness_entry(updated_at=None, has_records=False, query_failed=True),
            "source_health": _build_freshness_entry(updated_at=None, has_records=False, query_failed=True),
            "execution": {
                "updated_at": None,
                "age_seconds": None,
                "status": "empty",
            },
            "outcomes": {
                "updated_at": None,
                "age_seconds": None,
                "status": "empty",
            },
        }
        return {
            "total_opportunities": 0,
            "total_outcomes": 0,
            "avg_gross_margin": None,
            "avg_roi_pct": None,
            "wins_by_source": [],
            "top_makes": [],
            "alerts_sent_last_30d": 0,
            "total_bids": 0,
            "total_wins": 0,
            "win_rate": None,
            "avg_purchase_price": None,
            "avg_max_bid": None,
            "pipeline": {
                "status": "empty",
                "scope": "system",
                "updated_at": now_iso,
                "active_opportunities": 0,
                "fresh_opportunities_24h": 0,
                "fresh_opportunities_7d": 0,
                "hot_deals_count": 0,
                "good_plus_deals_count": 0,
                "avg_dos_score": None,
                "unique_sources": 0,
                "unique_states": 0,
            },
            "source_health": {
                "status": "degraded",
                "scope": "system",
                "updated_at": now_iso,
                "sources": [],
                "notes": ["Supabase client unavailable"],
            },
            "execution": {
                "status": "empty",
                "scope": "user_execution",
                "updated_at": now_iso,
                "workflow_counts": {
                    "wins": 0,
                    "losses": None,
                    "passes": None,
                    "pending": None,
                },
                "bid_metrics": {
                    "bids_placed": 0,
                    "win_rate": None,
                    "avg_max_bid": None,
                    "avg_purchase_price": None,
                    "ceiling_compliance": None,
                },
                "notes": _build_execution_notes(pending_outcomes=None, ceiling_compliance=None),
            },
            "outcomes": {
                "status": "empty",
                "scope": "user_outcomes",
                "updated_at": now_iso,
                "recorded_outcomes": 0,
                "total_gross_margin": None,
                "avg_gross_margin": None,
                "avg_roi": None,
                "wins_by_source": [],
                "top_makes_by_realized_performance": [],
            },
            "freshness": freshness,
            "trust": {
                "status": "degraded",
                "scope": "trust",
                "updated_at": now_iso,
                "summary_refreshed_at": now_iso,
                "completeness_score": 0.0,
                "degraded_sections": ["pipeline", "source_health", "execution", "outcomes", "trust"],
                "freshness_age": 0,
                "severity": "high",
                "rule_ids": ["supabase_unavailable"],
                "notes": ["Supabase client unavailable"],
            },
        }

    total_opportunities = 0
    total_outcomes = 0
    avg_gross_margin = None
    avg_roi_pct = None
    wins_by_source = []
    top_makes = []
    alerts_sent_last_30d = 0
    total_bids = 0
    total_wins = 0
    win_rate = None
    avg_purchase_price = None
    avg_max_bid = None
    fresh_opportunities_24h = 0
    fresh_opportunities_7d = 0
    hot_deals_count = 0
    good_plus_deals_count = 0
    avg_dos_score = None
    unique_sources = 0
    unique_states = 0
    losses = None
    passes = None
    pending_outcomes = None
    ceiling_compliance = None
    total_gross_margin = None
    source_health_sources = []
    source_health_status = "empty"
    source_health_notes: list[str] = []
    degraded_sections: list[str] = []
    notes: list[str] = []
    pipeline_updated_at = None
    source_health_updated_at = None
    execution_updated_at = None
    outcomes_updated_at = None
    pipeline_query_failed = False
    source_health_query_failed = False
    execution_query_failed = False
    outcomes_query_failed = False

    try:
        opp_resp = (
            supa.table("opportunities")
            .select("id,created_at,dos_score,source_site,state")
            .limit(5000)
            .execute()
        )
        opp_rows = opp_resp.data or []
        total_opportunities = len(opp_rows)
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        scores = []
        source_set = set()
        state_set = set()
        for row in opp_rows:
            created_at_raw = row.get("created_at")
            if created_at_raw:
                try:
                    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                    if pipeline_updated_at is None or created_at > pipeline_updated_at:
                        pipeline_updated_at = created_at
                    if created_at >= cutoff_24h:
                        fresh_opportunities_24h += 1
                    if created_at >= cutoff_7d:
                        fresh_opportunities_7d += 1
                except Exception:
                    pass
            score = row.get("dos_score")
            if score is not None:
                try:
                    score_f = float(score)
                    scores.append(score_f)
                    if score_f >= 80:
                        hot_deals_count += 1
                    if score_f >= 65:
                        good_plus_deals_count += 1
                except Exception:
                    pass
            src = row.get("source_site")
            st = row.get("state")
            if src:
                source_set.add(src)
            if st:
                state_set.add(st)
        avg_dos_score = round(sum(scores) / len(scores), 1) if scores else None
        unique_sources = len(source_set)
        unique_states = len(state_set)
    except Exception as exc:
        logger.warning(f"[ANALYTICS] summary opportunities query degraded: {exc}")
        pipeline_query_failed = True
        degraded_sections.append("pipeline")
        notes.append("Pipeline metrics degraded")

    try:
        outcomes_resp = (
            supa.table("dealer_sales")
            .select("outcome,gross_margin,roi_pct,source,make,created_at,updated_at,sold_at", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        outcome_rows = outcomes_resp.data or []
        total_outcomes = outcomes_resp.count or len(outcome_rows)
        avg_gross_margin = _safe_avg(outcome_rows, "gross_margin")
        avg_roi_pct = _safe_avg(outcome_rows, "roi_pct")
        gross_margin_values = [float(row["gross_margin"]) for row in outcome_rows if row.get("gross_margin") is not None]
        total_gross_margin = round(sum(gross_margin_values), 2) if gross_margin_values else None

        source_map: dict[str, int] = {}
        make_margin_map: dict[str, list[float]] = {}

        for row in outcome_rows:
            for ts_key in ("sold_at", "updated_at", "created_at"):
                ts_raw = row.get(ts_key)
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if outcomes_updated_at is None or ts > outcomes_updated_at:
                        outcomes_updated_at = ts
                    break
                except Exception:
                    continue

            normalized_outcome = str(row.get("outcome") or "").strip().lower()
            if normalized_outcome not in {"won", "sold"}:
                continue

            source = row.get("source") or "unknown"
            source_map[source] = source_map.get(source, 0) + 1

            margin = row.get("gross_margin")
            make = (row.get("make") or "Unknown").strip()
            if margin is not None:
                try:
                    make_margin_map.setdefault(make, []).append(float(margin))
                except (TypeError, ValueError):
                    pass

        wins_by_source = [
            {"source": k, "count": v}
            for k, v in sorted(source_map.items(), key=lambda x: -x[1])
        ]
        top_makes = [
            {"make": m, "avg_gross_margin": round(sum(v) / len(v), 1), "count": len(v)}
            for m, v in make_margin_map.items()
        ]
        top_makes.sort(key=lambda x: -x["avg_gross_margin"])
        top_makes = top_makes[:5]
    except Exception as exc:
        logger.warning(f"[ANALYTICS] summary outcomes query degraded: {exc}")
        outcomes_query_failed = True
        if "outcomes" not in degraded_sections:
            degraded_sections.append("outcomes")
        notes.append("Outcome metrics degraded")

    try:
        bid_resp = (
            supa.table("opportunities")
            .select("id,outcome_notes,outcome_sale_price,max_bid,outcome_recorded_at")
            .eq("user_id", user_id)
            .not_.is_("outcome_recorded_at", "null")
            .execute()
        )
        purchase_prices: list[float] = []
        max_bids_on_bid_rows: list[float] = []

        for row in (bid_resp.data or []):
            recorded_at_raw = row.get("outcome_recorded_at")
            if recorded_at_raw:
                try:
                    recorded_at = datetime.fromisoformat(str(recorded_at_raw).replace("Z", "+00:00"))
                    if execution_updated_at is None or recorded_at > execution_updated_at:
                        execution_updated_at = recorded_at
                except Exception:
                    pass

            notes_raw = row.get("outcome_notes") or ""
            bid_data: dict = {}
            try:
                parsed = json.loads(notes_raw)
                if isinstance(parsed, dict) and parsed.get("type") == "bid_outcome":
                    bid_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

            if not bid_data:
                continue

            if bid_data.get("bid"):
                total_bids += 1
                mb = row.get("max_bid")
                if mb is not None:
                    try:
                        max_bids_on_bid_rows.append(float(mb))
                    except (TypeError, ValueError):
                        pass
            if bid_data.get("won"):
                total_wins += 1
                pp = bid_data.get("purchase_price") or row.get("outcome_sale_price")
                if pp is not None:
                    try:
                        purchase_prices.append(float(pp))
                    except (TypeError, ValueError):
                        pass

        execution_outcomes_resp = (
            supa.table("dealer_sales")
            .select("outcome,recorded_at,created_at,updated_at")
            .eq("user_id", user_id)
            .execute()
        )
        execution_outcome_rows = execution_outcomes_resp.data or []
        outcome_counts = {"pending": 0, "won": 0, "lost": 0, "passed": 0}
        for row in execution_outcome_rows:
            outcome = str(row.get("outcome") or "pending").strip().lower()
            if outcome in outcome_counts:
                outcome_counts[outcome] += 1
            for ts_key in ("updated_at", "recorded_at", "created_at"):
                ts_raw = row.get(ts_key)
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if execution_updated_at is None or ts > execution_updated_at:
                        execution_updated_at = ts
                    break
                except Exception:
                    continue

        passes = outcome_counts["passed"]
        losses = outcome_counts["lost"]
        pending_outcomes = outcome_counts["pending"]

        compliant_bids = 0
        wins_with_purchase_and_cap = 0
        for row in (bid_resp.data or []):
            notes_raw = row.get("outcome_notes") or ""
            bid_data: dict = {}
            try:
                parsed = json.loads(notes_raw)
                if isinstance(parsed, dict) and parsed.get("type") == "bid_outcome":
                    bid_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass
            if not bid_data or not bid_data.get("won"):
                continue
            purchase_price = bid_data.get("purchase_price") or row.get("outcome_sale_price")
            max_bid = row.get("max_bid")
            if purchase_price is None or max_bid is None:
                continue
            try:
                wins_with_purchase_and_cap += 1
                if float(purchase_price) <= float(max_bid):
                    compliant_bids += 1
            except (TypeError, ValueError):
                continue
        ceiling_compliance = round((compliant_bids / wins_with_purchase_and_cap) * 100, 1) if wins_with_purchase_and_cap > 0 else None

        win_rate = round(total_wins / total_bids * 100, 1) if total_bids > 0 else None
        avg_purchase_price = round(sum(purchase_prices) / len(purchase_prices), 2) if purchase_prices else None
        avg_max_bid = round(sum(max_bids_on_bid_rows) / len(max_bids_on_bid_rows), 2) if max_bids_on_bid_rows else None
    except Exception as exc:
        logger.warning(f"[ANALYTICS] summary execution query degraded: {exc}")
        execution_query_failed = True
        if "execution" not in degraded_sections:
            degraded_sections.append("execution")
        notes.append("Execution metrics degraded")
        notes.append("Top makes metrics degraded")

    try:
        source_health_payload = await source_health(authorization)
        source_health_sources = source_health_payload.get("sources", [])
        source_health_status = "empty" if not source_health_sources else "healthy"
        source_health_notes = []
        source_health_timestamps = []
        source_health_generated_at = source_health_payload.get("generated_at")
        if source_health_generated_at:
            # `generated_at` is the snapshot build time for source health, not a
            # per-source event timestamp. Use it as a fallback when rows are sparse.
            try:
                source_health_timestamps.append(datetime.fromisoformat(str(source_health_generated_at).replace("Z", "+00:00")))
            except Exception:
                pass
        for source in source_health_sources:
            for ts_key in ("last_webhook_at", "last_seen_at"):
                ts_raw = source.get(ts_key)
                if not ts_raw:
                    continue
                try:
                    source_health_timestamps.append(datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")))
                except Exception:
                    continue
        source_health_updated_at = max(source_health_timestamps) if source_health_timestamps else None
    except HTTPException as exc:
        logger.warning(f"[ANALYTICS] summary source-health query degraded: {exc.detail}")
        source_health_query_failed = True
        source_health_sources = []
        source_health_status = "degraded"
        source_health_notes = [str(exc.detail)]
        if "source_health" not in degraded_sections:
            degraded_sections.append("source_health")
        notes.append("Source health degraded")
    except Exception as exc:
        logger.warning(f"[ANALYTICS] summary source-health query degraded: {exc}")
        source_health_query_failed = True
        source_health_sources = []
        source_health_status = "degraded"
        source_health_notes = ["Source health metrics degraded"]
        if "source_health" not in degraded_sections:
            degraded_sections.append("source_health")
        notes.append("Source health degraded")

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        alerts_resp = (
            supa.table("alert_log")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .gte("sent_at", cutoff)
            .execute()
        )
        alerts_sent_last_30d = alerts_resp.count or 0
    except Exception as exc:
        logger.warning(f"[ANALYTICS] summary alerts query degraded: {exc}")
        if "trust" not in degraded_sections:
            degraded_sections.append("trust")
        notes.append("Alert metrics degraded")

    completeness_score = round(max(0.0, 1 - (len(set(degraded_sections)) / 5)), 2)
    section_timestamps = [ts for ts in [pipeline_updated_at, source_health_updated_at, execution_updated_at, outcomes_updated_at] if ts is not None]
    summary_refreshed_at_value = max(section_timestamps).isoformat() if section_timestamps else None
    freshness_age = None
    if section_timestamps:
        freshness_age = round((datetime.now(timezone.utc) - max(section_timestamps)).total_seconds(), 1)
        if freshness_age > 86400 and "trust" not in degraded_sections:
            degraded_sections.append("trust")
            notes.append("Summary freshness is older than 24 hours")
    trust_status = "healthy" if not degraded_sections else "degraded"
    execution_notes = _build_execution_notes(
        pending_outcomes=pending_outcomes,
        ceiling_compliance=ceiling_compliance,
    )
    execution_has_data = (
        total_bids > 0
        or total_wins > 0
        or any(v not in (None, 0) for v in [passes, losses, pending_outcomes])
        or avg_purchase_price is not None
        or avg_max_bid is not None
        or ceiling_compliance is not None
    )
    execution_status = "degraded" if execution_has_data else "empty"
    outcomes_status = "empty" if total_outcomes == 0 else ("degraded" if "outcomes" in degraded_sections else "healthy")
    pipeline_status = "empty" if total_opportunities == 0 else ("degraded" if "pipeline" in degraded_sections else "healthy")
    freshness = {
        "pipeline": _build_freshness_entry(
            updated_at=pipeline_updated_at,
            has_records=total_opportunities > 0,
            query_failed=pipeline_query_failed,
        ),
        "source_health": _build_freshness_entry(
            updated_at=source_health_updated_at,
            has_records=bool(source_health_sources),
            query_failed=source_health_query_failed,
        ),
        "execution": _build_freshness_entry(
            updated_at=execution_updated_at,
            has_records=execution_has_data,
            query_failed=execution_query_failed,
        ),
        "outcomes": _build_freshness_entry(
            updated_at=outcomes_updated_at,
            has_records=total_outcomes > 0,
            query_failed=outcomes_query_failed,
        ),
    }
    trust_rule_results = _evaluate_trust_rules(
        total_wins=total_wins,
        total_outcomes=total_outcomes,
        total_bids=total_bids,
        win_rate=win_rate,
        avg_purchase_price=avg_purchase_price,
        wins_by_source=wins_by_source,
        source_health_status=source_health_status,
        freshness_age=freshness_age,
        freshness=freshness,
    )
    trust_rule_notes = [rule["message"] for rule in trust_rule_results]
    trust_rule_ids = [rule["id"] for rule in trust_rule_results]
    trust_severity = "high" if any(rule["severity"] == "high" for rule in trust_rule_results) else ("medium" if trust_rule_results else "low")
    if trust_rule_notes:
        notes.extend(trust_rule_notes)
        if "trust" not in degraded_sections:
            degraded_sections.append("trust")
    if execution_has_data and "execution" not in degraded_sections:
        degraded_sections.append("execution")
    trust_status = "healthy" if not degraded_sections else "degraded"

    response = {
        "total_opportunities": total_opportunities,
        "total_outcomes": total_outcomes,
        "avg_gross_margin": avg_gross_margin,
        "avg_roi_pct": avg_roi_pct,
        "wins_by_source": wins_by_source,
        "top_makes": top_makes,
        "alerts_sent_last_30d": alerts_sent_last_30d,
        "total_bids": total_bids,
        "total_wins": total_wins,
        "win_rate": win_rate,
        "avg_purchase_price": avg_purchase_price,
        "avg_max_bid": avg_max_bid,
        "pipeline": {
            "status": pipeline_status,
            "scope": "system",
            "updated_at": pipeline_updated_at.isoformat() if pipeline_updated_at else now_iso,
            "active_opportunities": total_opportunities,
            "fresh_opportunities_24h": fresh_opportunities_24h,
            "fresh_opportunities_7d": fresh_opportunities_7d,
            "hot_deals_count": hot_deals_count,
            "good_plus_deals_count": good_plus_deals_count,
            "avg_dos_score": avg_dos_score,
            "unique_sources": unique_sources,
            "unique_states": unique_states,
        },
        "source_health": {
            "status": source_health_status,
            "scope": "system",
            "updated_at": source_health_updated_at.isoformat() if source_health_updated_at else now_iso,
            "sources": source_health_sources,
            "notes": source_health_notes,
        },
        "execution": {
            "status": execution_status,
            "scope": "user_execution",
            "updated_at": execution_updated_at.isoformat() if execution_updated_at else now_iso,
            "workflow_counts": {
                "wins": total_wins,
                "losses": losses,
                "passes": passes,
                "pending": pending_outcomes,
            },
            "bid_metrics": {
                "bids_placed": total_bids,
                "win_rate": win_rate,
                "avg_max_bid": avg_max_bid,
                "avg_purchase_price": avg_purchase_price,
                "ceiling_compliance": ceiling_compliance,
            },
            "notes": execution_notes,
        },
        "outcomes": {
            "status": outcomes_status,
            "scope": "user_outcomes",
            "updated_at": outcomes_updated_at.isoformat() if outcomes_updated_at else now_iso,
            "recorded_outcomes": total_outcomes,
            "total_gross_margin": total_gross_margin,
            "avg_gross_margin": avg_gross_margin,
            "avg_roi": avg_roi_pct,
            "wins_by_source": wins_by_source,
            "top_makes_by_realized_performance": top_makes,
        },
        "freshness": freshness,
        "trust": {
            "status": trust_status,
            "scope": "trust",
            "updated_at": summary_refreshed_at_value or now_iso,
            "summary_refreshed_at": summary_refreshed_at_value,
            "completeness_score": completeness_score,
            "degraded_sections": sorted(set(degraded_sections)),
            "freshness_age": freshness_age,
            "severity": trust_severity,
            "rule_ids": trust_rule_ids,
            "notes": notes,
        },
    }

    _emit_trust_events(
        user_id=user_id,
        trust_status=trust_status,
        trust_severity=trust_severity,
        trust_rule_ids=trust_rule_ids,
        trust_notes=notes,
        degraded_sections=sorted(set(degraded_sections)),
        completeness_score=completeness_score,
        summary_refreshed_at=summary_refreshed_at_value,
        freshness_age=freshness_age,
        freshness=freshness,
    )

    return response


@router.get("/dos-calibration")
async def dos_calibration(authorization: Optional[str] = Header(None)):
    """
    Return DOS scoring calibration status:
      - Current weight breakdown
      - Data availability (recon count, dealer_sales count)
      - Which components are estimated vs data-driven
      - Recommendations for calibration when real data arrives
    """
    user_id = _verify_auth(authorization)
    # Base DOS formula weights
    base_weights = {
        "margin": 0.35,
        "velocity": 0.25,
        "segment": 0.20,
        "model": 0.12,
        "source": 0.08,  # baseline, now dynamic
    }

    # Dynamic source weights by tier
    source_weight_tiers = {
        "proven_gov": {"weight": 0.10, "sources": ["govplanet", "govdeals", "municibid", "publicsurplus", "gsaauctions", "usgovbid", "jjkane"]},
        "mid_tier": {"weight": 0.08, "sources": ["ritchiebros", "ironplanet"]},
        "less_reliable": {"weight": 0.06, "sources": ["proxibid", "bidspotter"]},
        "lowest_confidence": {"weight": 0.04, "sources": ["hibid", "allsurplus"]},
        "salvage": {"weight": 0.03, "sources": ["iaa", "copart"]},
    }

    # Component estimation status
    component_status = {
        "margin": {
            "data_driven": False,
            "source": "Marketcheck retail comps or proxy multiplier",
            "confidence": "medium",
            "notes": "Uses retail comp prices when available, otherwise proxy estimate from MMR",
        },
        "velocity": {
            "data_driven": False,
            "source": "Hardcoded heuristics based on price/age/mileage",
            "confidence": "low",
            "notes": "No actual days-to-sale data — uses segment tier estimates (25-70 days)",
        },
        "segment": {
            "data_driven": True,
            "source": "Static model→segment mapping",
            "confidence": "high",
            "notes": "Segment demand patterns are stable; scoring is appropriate",
        },
        "model": {
            "data_driven": True,
            "source": "TIER_1/TIER_2 model lists",
            "confidence": "high",
            "notes": "Model desirability is well-understood",
        },
        "source": {
            "data_driven": True,
            "source": "Dynamic weight by source tier (0.03-0.10)",
            "confidence": "high",
            "notes": "Source reliability is known from government fleet patterns",
        },
    }

    # Query data availability
    recon_count = 0
    dealer_sales_count = 0
    outcomes_with_bids = 0

    if supa is not None:
        try:
            # Count recon evaluations (opportunities with dos_score)
            recon_resp = supa.table("opportunities").select("id", count="exact").eq("user_id", user_id).not_.is_("dos_score", "null").execute()
            recon_count = recon_resp.count or 0

            # Count dealer_sales comps
            ds_resp = supa.table("dealer_sales").select("id", count="exact").eq("user_id", user_id).execute()
            dealer_sales_count = ds_resp.count or 0

            # Count bid outcomes only, exclude manual outcome mirrors
            outcomes_resp = supa.table("opportunities").select("outcome_notes", count="exact").eq("user_id", user_id).not_.is_("outcome_recorded_at", "null").execute()
            for row in (outcomes_resp.data or []):
                notes = row.get("outcome_notes") or ""
                if '"type": "bid_outcome"' in notes:
                    outcomes_with_bids += 1
        except Exception as e:
            logger.warning(f"[DOS-CALIBRATION] Data query failed: {e}")

    # Calibration recommendations
    recommendations = []
    if dealer_sales_count < 50:
        recommendations.append({
            "priority": 1,
            "component": "margin",
            "action": "Collect more dealer_sales comps to improve margin accuracy",
            "threshold": "50+ comps enables data-driven margin scoring",
        })
    if outcomes_with_bids < 10:
        recommendations.append({
            "priority": 2,
            "component": "velocity",
            "action": "Log bid outcomes with actual days-to-sale to calibrate velocity",
            "threshold": "10+ bid outcomes enables real velocity measurement",
        })
    if outcomes_with_bids >= 10:
        recommendations.append({
            "priority": 1,
            "component": "velocity",
            "action": "Replace heuristic velocity with actual days-to-sale from outcomes",
            "threshold": "Ready for calibration — sufficient bid data exists",
        })
    if not recommendations:
        recommendations.append({
            "priority": 0,
            "component": "all",
            "action": "DOS scoring is appropriately calibrated for current data volume",
            "threshold": "n/a",
        })

    return {
        "formula": "DOS = Margin×W1 + Velocity×W2 + Segment×W3 + Model×W4 + Source×W_src",
        "base_weights": base_weights,
        "source_weight_tiers": source_weight_tiers,
        "component_status": component_status,
        "data_availability": {
            "recon_evaluations": recon_count,
            "dealer_sales_comps": dealer_sales_count,
            "bid_outcomes": outcomes_with_bids,
        },
        "recommendations": recommendations,
        "next_calibration_target": "velocity" if outcomes_with_bids < 10 else "margin",
    }


@router.get("/recent-trust-events")
async def recent_trust_events(limit: int = 25, authorization: Optional[str] = Header(None)):
    user_id = _verify_auth(authorization)
    safe_limit = max(1, min(limit, 100))

    if supabase_client is None:
        return {
            "events": [],
            "count": 0,
            "limit": safe_limit,
            "notes": ["Supabase client unavailable"],
        }

    try:
        response = (
            supabase_client.table("system_logs")
            .select("id, level, message, context, timestamp, created_at")
            .ilike("message", "Analytics trust event:%")
            .order("timestamp", desc=True)
            .limit(max(safe_limit * 3, safe_limit))
            .execute()
        )
        rows = response.data or []

        filtered_rows = []
        for row in rows:
            context = row.get("context") or {}
            context_user_id = context.get("user_id")
            if context_user_id and context_user_id != user_id:
                continue
            filtered_rows.append(row)

        events = []
        for row in filtered_rows[:safe_limit]:
            context = row.get("context") or {}
            paperclip = context.get("paperclip") or {}
            issue_status = paperclip.get("issue_status")
            is_open_issue = bool(issue_status and issue_status.lower() not in {"done", "closed", "resolved", "cancelled"})
            events.append({
                "id": row.get("id"),
                "level": row.get("level"),
                "message": row.get("message"),
                "event": context.get("event"),
                "severity": context.get("trustSeverity"),
                "rule_ids": context.get("trustRuleIds") or [],
                "notes": context.get("trustNotes") or [],
                "degraded_sections": context.get("degradedSections") or [],
                "completeness_score": context.get("completenessScore"),
                "summary_refreshed_at": context.get("summaryRefreshedAt"),
                "freshness_age": context.get("freshnessAge"),
                "freshness": context.get("freshness") or {},
                "paperclip": {
                    "status": paperclip.get("status"),
                    "issue_id": paperclip.get("issue_id"),
                    "identifier": paperclip.get("identifier"),
                    "title": paperclip.get("title"),
                    "issue_status": issue_status,
                    "correlation_key": paperclip.get("correlation_key"),
                    "is_open": bool(paperclip.get("is_open", is_open_issue)),
                },
                "timestamp": row.get("timestamp") or row.get("created_at"),
            })

        return {
            "events": events,
            "count": len(events),
            "limit": safe_limit,
            "notes": [],
        }
    except Exception as exc:
        logger.warning(f"[ANALYTICS] failed to fetch recent trust events: {exc}")
        return {
            "events": [],
            "count": 0,
            "limit": safe_limit,
            "notes": ["Failed to fetch recent trust events"],
        }


@router.get("/source-health")
async def source_health(authorization: Optional[str] = Header(None)):
    """
    Return operational source-health metrics separated from portfolio summary.

    This endpoint is intentionally ops-focused rather than outcome-history-focused.
    It answers:
      - Which sources ran recently?
      - Which sources processed recently?
      - Which sources are actually creating fresh opportunities?
      - What is the fetched / saved / skipped picture for the latest observed run?
    """
    user_id = _verify_auth(authorization)
    if supa is None:
        # `generated_at` is the snapshot assembly time for the current source-health view.
        return {"sources": [], "generated_at": datetime.now(timezone.utc).isoformat()}

    now = datetime.now(timezone.utc)
    window_7d = (now - timedelta(days=7)).isoformat()

    try:
        opp_resp = (
            supa.table("opportunities")
            .select("source_site,created_at,auction_end_date")
            .limit(5000)
            .execute()
        )
        opp_rows = opp_resp.data or []
    except Exception as exc:
        logger.error(f"[ANALYTICS] source-health opportunities query error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Source health query failed")

    webhook_rows = []
    try:
        webhook_resp = (
            supa.table("webhook_log")
            .select("received_at,actor_id,run_id,item_count,processing_status,error_message")
            .order("received_at", desc=True)
            .limit(250)
            .execute()
        )
        webhook_rows = webhook_resp.data or []
    except Exception as exc:
        logger.warning(f"[ANALYTICS] source-health webhook_log query degraded: {exc}")

    counts_total: Counter[str] = Counter()
    counts_7d: Counter[str] = Counter()
    counts_active: Counter[str] = Counter()
    latest_opp_by_source: dict[str, datetime] = {}

    for row in opp_rows:
        source = (row.get("source_site") or "unknown").lower()
        counts_total[source] += 1

        created_at = row.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if source not in latest_opp_by_source or created_dt > latest_opp_by_source[source]:
                    latest_opp_by_source[source] = created_dt
                if created_dt >= datetime.fromisoformat(window_7d.replace("Z", "+00:00")):
                    counts_7d[source] += 1
            except Exception:
                pass

        auction_end = row.get("auction_end_date")
        if auction_end in {None, ""}:
            counts_active[source] += 1
        else:
            try:
                auction_end_dt = datetime.fromisoformat(str(auction_end).replace("Z", "+00:00"))
                if auction_end_dt > now:
                    counts_active[source] += 1
            except Exception:
                pass

    latest_webhook_by_source: dict[str, dict] = {}
    for row in webhook_rows:
        actor_id = row.get("actor_id")
        source = ACTOR_TO_SOURCE.get(actor_id)
        if not source:
            continue
        if source not in latest_webhook_by_source:
            latest_webhook_by_source[source] = row

    def _extract_counts(error_message: Optional[str]) -> dict[str, int]:
        if not error_message:
            return {}
        counts: dict[str, int] = {}
        marker = "save_outcomes={"
        if marker in error_message:
            try:
                fragment = error_message.split(marker, 1)[1].split("}", 1)[0]
                if fragment.strip():
                    for part in fragment.split(","):
                        if ":" not in part:
                            continue
                        key, value = part.split(":", 1)
                        counts[key.strip().strip("'\"")] = int(value.strip())
            except Exception:
                return {}
        return counts

    def _extract_funnel(error_message: Optional[str]) -> dict[str, int]:
        if not error_message or "funnel=" not in error_message:
            return {}
        try:
            fragment = error_message.split("funnel=", 1)[1].split(";", 1)[0]
            values: dict[str, int] = {}
            for part in fragment.split(","):
                if ":" not in part:
                    continue
                key, value = part.split(":", 1)
                values[key.strip()] = int(value.strip())
            return values
        except Exception:
            return {}

    def _extract_skip_reasons(error_message: Optional[str]) -> dict[str, int]:
        if not error_message:
            return {}
        counts: dict[str, int] = {}
        marker = "skip_reasons={"
        if marker in error_message:
            try:
                fragment = error_message.split(marker, 1)[1].split("}", 1)[0]
                if fragment.strip():
                    for part in fragment.split(","):
                        if ":" not in part:
                            continue
                        key, value = part.split(":", 1)
                        counts[key.strip().strip("'\"")] = int(value.strip())
            except Exception:
                return {}
        return counts

    sources = []
    for actor_name, details in SOURCE_ACTOR_MAP.items():
        source = details["source_site"]
        webhook = latest_webhook_by_source.get(source, {})
        latest_opp = latest_opp_by_source.get(source)
        latest_opp_age_hours = None
        if latest_opp is not None:
            latest_opp_age_hours = round((now - latest_opp).total_seconds() / 3600, 1)

        save_outcomes = _extract_counts(webhook.get("error_message"))
        skip_reasons = _extract_skip_reasons(webhook.get("error_message"))
        funnel = _extract_funnel(webhook.get("error_message"))
        saved_count = funnel.get("saved")
        if saved_count is None:
            saved_count = sum(value for key, value in save_outcomes.items() if key.startswith("saved_"))
        duplicate_count = funnel.get("existing")
        if duplicate_count is None:
            duplicate_count = save_outcomes.get("duplicate_existing", 0)
        latest_item_count = funnel.get("items", webhook.get("item_count") or 0)
        skipped_count = funnel.get("skipped")
        if skipped_count is None:
            skipped_count = max(0, int(latest_item_count) - int(saved_count) - int(duplicate_count)) if latest_item_count else None

        health = "red"
        if counts_7d.get(source, 0) > 0:
            health = "green" if latest_opp_age_hours is not None and latest_opp_age_hours <= 24 else "yellow"
        elif webhook.get("received_at"):
            health = "yellow"

        sources.append({
            "actor_name": actor_name,
            "source_site": source,
            "health": health,
            "latest_webhook_at": webhook.get("received_at"),
            "latest_webhook_status": webhook.get("processing_status"),
            "latest_run_id": webhook.get("run_id"),
            "latest_fetched_items": latest_item_count,
            "latest_saved_items": saved_count,
            "latest_duplicate_items": duplicate_count,
            "latest_skipped_items_estimate": skipped_count,
            "latest_error_summary": webhook.get("error_message"),
            "latest_skip_reasons": skip_reasons,
            "latest_top_skip_reason": max(skip_reasons.items(), key=lambda item: item[1])[0] if skip_reasons else None,
            "fresh_opportunities_7d": counts_7d.get(source, 0),
            "total_opportunities": counts_total.get(source, 0),
            "active_opportunities": counts_active.get(source, 0),
            "latest_opportunity_at": latest_opp.isoformat() if latest_opp else None,
            "latest_opportunity_age_hours": latest_opp_age_hours,
        })

    sources.sort(key=lambda row: (row["health"], row.get("latest_opportunity_age_hours") or 10**9, row["source_site"]))
    return {
        "generated_at": now.isoformat(),
        "sources": sources,
        "notes": {
            "purpose": "operational source health, separate from portfolio summary",
            "health_logic": {
                "green": "fresh opportunities landed within 24h",
                "yellow": "webhooks/runs exist but fresh opportunity contribution is stale or weak",
                "red": "no fresh opportunity contribution and no meaningful recent signal",
            },
        },
    }
