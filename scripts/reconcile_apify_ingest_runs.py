#!/usr/bin/env python3
"""Reconcile recent Apify runs against webhook_log, opportunities, and ingest_delivery_log."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_PATH = REPO_ROOT / "apify" / "deployment.json"
DEFAULT_ENV_FILES = (".env.live", ".env.local", ".env")
APIFY_TOKEN_KEYS = ("APIFY_TOKEN", "APIFY_API_TOKEN")
APIFY_BASE_URL = "https://api.apify.com/v2"
APIFY_SUCCESS_STATUSES = {"SUCCEEDED"}
WEBHOOK_BAD_STATUSES = {"degraded", "error"}
WEBHOOK_SUCCESS_STATUSES = {"processed", "ignored_replay"}
DB_SAVE_INSERT_STATUSES = {"saved_supabase", "saved_direct_pg"}
DB_SAVE_EXISTING_STATUSES = {"duplicate_existing"}
DB_SAVE_FAILURE_STATUSES = {
    "supabase_error",
    "direct_pg_error",
    "direct_pg_unavailable",
    "duplicate_unresolved",
}
_CURL_SSL_FALLBACK_NOTIFIED = False


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _get_env_value(explicit_value: Optional[str], keys: tuple[str, ...], env_file: Optional[str]) -> Optional[str]:
    if explicit_value:
        return explicit_value

    for key in keys:
        value = os.getenv(key)
        if value:
            return value

    search_paths: list[Path] = []
    if env_file:
        search_paths.append(Path(env_file))
    else:
        search_paths.extend(Path(candidate) for candidate in DEFAULT_ENV_FILES)

    for path in search_paths:
        if not path.exists():
            continue
        values = _parse_env_file(path)
        for key in keys:
            value = values.get(key)
            if value:
                return value
    return None


def parse_datetime(raw_value: Any) -> Optional[datetime]:
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        dt = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "n/a"
    return dt.astimezone().isoformat(timespec="seconds")


def load_actor_registry(actor_filters: list[str]) -> dict[str, str]:
    data = json.loads(DEPLOYMENT_PATH.read_text(encoding="utf-8"))
    actors = data.get("actors") or {}
    registry = {name: details["id"] for name, details in actors.items() if isinstance(details, dict) and details.get("id")}
    if not actor_filters:
        return registry

    selected: dict[str, str] = {}
    unresolved: list[str] = []
    reverse = {actor_id: name for name, actor_id in registry.items()}
    for token in actor_filters:
        token = token.strip()
        if not token:
            continue
        if token in registry:
            selected[token] = registry[token]
        elif token in reverse:
            selected[reverse[token]] = token
        else:
            unresolved.append(token)
    if unresolved:
        raise SystemExit(f"Unknown actor name/id filter(s): {', '.join(unresolved)}")
    return selected


def _build_apify_url(path: str, query: Optional[dict[str, Any]] = None) -> str:
    url = f"{APIFY_BASE_URL}{path}"
    if query:
        encoded = urllib_parse.urlencode({k: v for k, v in query.items() if v is not None})
        if encoded:
            url = f"{url}?{encoded}"
    return url


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    collected: list[BaseException] = []
    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        collected.append(current)
        for next_exc in (getattr(current, "reason", None), current.__cause__, current.__context__):
            if isinstance(next_exc, BaseException):
                pending.append(next_exc)
    return collected


def _is_ssl_verification_error(exc: BaseException) -> bool:
    for current in _iter_exception_chain(exc):
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if isinstance(current, ssl.SSLError):
            message = str(current).lower()
            if "certificate verify failed" in message or "certificate_verify_failed" in message:
                return True
    message = str(exc).lower()
    return "certificate verify failed" in message or "certificate_verify_failed" in message


def _notify_curl_ssl_fallback() -> None:
    global _CURL_SSL_FALLBACK_NOTIFIED
    if _CURL_SSL_FALLBACK_NOTIFIED:
        return
    _CURL_SSL_FALLBACK_NOTIFIED = True
    print(
        "Apify fetch note: Python SSL verification failed; retrying via curl with the system trust store.",
        file=sys.stderr,
    )


def _apify_get_json_via_curl(url: str, token: str, path: str) -> Any:
    curl_path = shutil.which("curl")
    if not curl_path:
        raise RuntimeError(
            f"curl is not available for Apify SSL fallback on {path}; use --runs-json for an offline compare."
        )

    completed = subprocess.run(
        [
            curl_path,
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            "30",
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Accept: application/json",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"curl exit {completed.returncode} while fetching {path}: {stderr[:300] or 'no error output'}"
        )

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Apify curl fallback returned invalid JSON for {path}") from exc


def apify_get_json(path: str, token: str, query: Optional[dict[str, Any]] = None) -> Any:
    url = _build_apify_url(path, query)
    request = urllib_request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API error for {path}: HTTP {exc.code} {body[:300]}") from exc
    except ssl.SSLError as exc:
        if _is_ssl_verification_error(exc):
            _notify_curl_ssl_fallback()
            return _apify_get_json_via_curl(url, token, path)
        raise RuntimeError(f"Apify API unreachable for {path}: {exc}") from exc
    except urllib_error.URLError as exc:
        if _is_ssl_verification_error(exc):
            _notify_curl_ssl_fallback()
            return _apify_get_json_via_curl(url, token, path)
        raise RuntimeError(f"Apify API unreachable for {path}: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Apify API returned invalid JSON for {path}") from exc


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _first_int(*candidates: Any) -> Optional[int]:
    for candidate in candidates:
        if candidate in {None, ""}:
            continue
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def fetch_dataset_item_count(dataset_id: str, token: str, cache: dict[str, Optional[int]]) -> Optional[int]:
    if dataset_id in cache:
        return cache[dataset_id]
    payload = apify_get_json(f"/datasets/{dataset_id}", token)
    data = payload.get("data") if isinstance(payload, dict) else None
    item_count = _first_int(
        data.get("itemCount") if isinstance(data, dict) else None,
        data.get("cleanItemCount") if isinstance(data, dict) else None,
    )
    cache[dataset_id] = item_count
    return item_count


def normalize_run(actor_name: str, actor_id: str, raw_run: dict[str, Any], token: Optional[str], dataset_cache: dict[str, Optional[int]]) -> dict[str, Any]:
    dataset_id = (
        raw_run.get("defaultDatasetId")
        or (raw_run.get("stats") or {}).get("defaultDatasetId")
        or ""
    )
    item_count = _first_int(
        (raw_run.get("stats") or {}).get("itemCount"),
        (raw_run.get("stats") or {}).get("itemsOutputCount"),
        raw_run.get("itemCount"),
    )
    if item_count is None and dataset_id and token:
        try:
            item_count = fetch_dataset_item_count(dataset_id, token, dataset_cache)
        except Exception:
            item_count = None

    started_at = parse_datetime(raw_run.get("startedAt") or raw_run.get("createdAt"))
    finished_at = parse_datetime(raw_run.get("finishedAt") or raw_run.get("modifiedAt"))
    return {
        "run_id": raw_run.get("id") or raw_run.get("runId"),
        "actor_name": actor_name,
        "actor_id": actor_id,
        "status": raw_run.get("status") or "unknown",
        "dataset_id": dataset_id or None,
        "item_count": item_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "raw": raw_run,
    }


def fetch_runs_from_apify(
    actors: dict[str, str],
    token: str,
    start: datetime,
    end: datetime,
    limit_per_actor: int,
) -> list[dict[str, Any]]:
    dataset_cache: dict[str, Optional[int]] = {}
    runs: list[dict[str, Any]] = []
    for actor_name, actor_id in actors.items():
        payload = apify_get_json(
            f"/acts/{actor_id}/runs",
            token,
            query={"limit": limit_per_actor, "desc": 1},
        )
        for raw_run in extract_items(payload):
            run = normalize_run(actor_name, actor_id, raw_run, token, dataset_cache)
            started_at = run.get("started_at")
            finished_at = run.get("finished_at") or started_at
            if started_at and started_at > end:
                continue
            if finished_at and finished_at < start:
                continue
            runs.append(run)
    runs.sort(
        key=lambda run: run.get("started_at") or run.get("finished_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return runs


def load_runs_from_json(path: Path, actors: dict[str, str], start: datetime, end: datetime) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    actor_name_by_id = {actor_id: actor_name for actor_name, actor_id in actors.items()}
    runs: list[dict[str, Any]] = []
    for raw_run in extract_items(payload):
        actor_id = raw_run.get("actId") or raw_run.get("actorId") or raw_run.get("actor_id")
        actor_name = actor_name_by_id.get(actor_id) or raw_run.get("actorName") or raw_run.get("actor_name") or "unknown"
        run = normalize_run(actor_name, actor_id or "unknown", raw_run, token=None, dataset_cache={})
        started_at = run.get("started_at")
        finished_at = run.get("finished_at") or started_at
        if started_at and started_at > end:
            continue
        if finished_at and finished_at < start:
            continue
        runs.append(run)
    runs.sort(
        key=lambda run: run.get("started_at") or run.get("finished_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return runs


def connect(dsn: str):
    return psycopg2.connect(dsn)


def fetch_webhook_rows(
    connection,
    start: datetime,
    end: datetime,
    actor_ids: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        sql = """
            select
              run_id,
              count(*)::int as webhook_entries,
              min(received_at) as first_received_at,
              max(received_at) as last_received_at,
              max(item_count) filter (where item_count is not null)::int as max_item_count,
              (array_agg(processing_status order by received_at desc, id desc))[1] as latest_status,
              (array_agg(error_message order by received_at desc, id desc))[1] as latest_error
            from public.webhook_log
            where run_id is not null
              and received_at >= %s
              and received_at <= %s
        """
        params: list[Any] = [start, end]
        if actor_ids:
            sql += " and actor_id = any(%s)"
            params.append(actor_ids)
        sql += " group by run_id"
        cursor.execute(sql, params)
        return {row["run_id"]: dict(row) for row in cursor.fetchall()}


def fetch_opportunity_rows(
    connection,
    start: datetime,
    end: datetime,
    sources: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        sql = """
            select
              run_id,
              count(*)::int as opportunity_rows,
              min(processed_at) as first_processed_at,
              max(processed_at) as last_processed_at,
              count(*) filter (where step_status = 'complete')::int as complete_rows,
              count(*) filter (where coalesce(is_duplicate, false))::int as duplicate_rows
            from public.opportunities
            where run_id is not null
              and processed_at >= %s
              and processed_at <= %s
        """
        params: list[Any] = [start, end]
        if sources:
            sql += " and source = any(%s)"
            params.append(sources)
        sql += " group by run_id"
        cursor.execute(sql, params)
        return {row["run_id"]: dict(row) for row in cursor.fetchall()}


def derive_source_names(actors: dict[str, str]) -> list[str]:
    names: list[str] = []
    for actor_name in actors:
        if actor_name.startswith("ds-"):
            names.append(actor_name[3:])
        else:
            names.append(actor_name)
    return sorted({name for name in names if name})


def fetch_delivery_rows(connection, start: datetime, end: datetime) -> dict[str, dict[str, Any]]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            select
              run_id,
              channel,
              status,
              count(*)::int as row_count,
              sum(attempt_count)::int as total_attempts,
              max(updated_at) as last_updated_at
            from public.ingest_delivery_log
            where run_id is not null
              and created_at >= %s
              and created_at <= %s
            group by run_id, channel, status
            order by run_id, channel, status
            """
            ,
            (start, end),
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in cursor.fetchall():
            run_id = row["run_id"]
            run_entry = grouped.setdefault(run_id, {"channels": {}, "last_updated_at": None})
            channel_entry = run_entry["channels"].setdefault(row["channel"], {"statuses": {}, "total_rows": 0, "total_attempts": 0})
            channel_entry["statuses"][row["status"]] = int(row["row_count"] or 0)
            channel_entry["total_rows"] += int(row["row_count"] or 0)
            channel_entry["total_attempts"] += int(row["total_attempts"] or 0)
            last_updated_at = parse_datetime(row.get("last_updated_at"))
            prior_last = run_entry.get("last_updated_at")
            if last_updated_at and (prior_last is None or last_updated_at > prior_last):
                run_entry["last_updated_at"] = last_updated_at
        return grouped


def classify_run(
    run_id: str,
    apify_run: Optional[dict[str, Any]],
    webhook: Optional[dict[str, Any]],
    opportunities: Optional[dict[str, Any]],
    delivery: Optional[dict[str, Any]],
    now_utc: datetime,
    pending_grace_minutes: int,
) -> list[str]:
    issues: list[str] = []
    db_save_statuses = ((delivery or {}).get("channels") or {}).get("db_save", {}).get("statuses") or {}
    inserted_rows = sum(int(db_save_statuses.get(status) or 0) for status in DB_SAVE_INSERT_STATUSES)
    existing_rows = sum(int(db_save_statuses.get(status) or 0) for status in DB_SAVE_EXISTING_STATUSES)
    failed_rows = sum(int(db_save_statuses.get(status) or 0) for status in DB_SAVE_FAILURE_STATUSES)
    opportunity_rows = int((opportunities or {}).get("opportunity_rows") or 0)
    latest_webhook_status = str((webhook or {}).get("latest_status") or "unknown").lower()
    has_successful_db_landing = opportunity_rows > 0 or inserted_rows > 0 or existing_rows > 0

    if apify_run is None:
        if webhook or opportunities or delivery:
            has_clean_webhook = not webhook or latest_webhook_status in WEBHOOK_SUCCESS_STATUSES
            if has_clean_webhook and has_successful_db_landing and failed_rows == 0:
                return issues
            issues.append("db_only_run")
        return issues

    apify_status = str(apify_run.get("status") or "unknown").upper()
    item_count = _first_int(apify_run.get("item_count")) or 0
    if apify_status in APIFY_SUCCESS_STATUSES:
        if webhook is None:
            issues.append("missing_webhook")
        else:
            if latest_webhook_status in WEBHOOK_BAD_STATUSES:
                issues.append(f"webhook_{latest_webhook_status}")
            elif latest_webhook_status == "pending":
                last_seen = parse_datetime(webhook.get("last_received_at")) or apify_run.get("finished_at") or apify_run.get("started_at")
                if last_seen and (now_utc - last_seen) > timedelta(minutes=pending_grace_minutes):
                    issues.append("webhook_pending_stale")

            webhook_item_count = _first_int(webhook.get("max_item_count"))
            if item_count > 0 and webhook_item_count is not None and webhook_item_count != item_count:
                issues.append("webhook_item_count_mismatch")

        if item_count > 0 and delivery is None:
            issues.append("missing_delivery_log")
        if failed_rows > 0:
            issues.append("db_save_failures")
        if item_count > 0 and not db_save_statuses:
            issues.append("missing_db_save_ledger")
        if item_count > 0 and opportunity_rows == 0 and inserted_rows == 0 and existing_rows == 0:
            issues.append("no_db_landing")

    return issues


def build_reports(
    apify_runs: list[dict[str, Any]],
    webhook_rows: dict[str, dict[str, Any]],
    opportunity_rows: dict[str, dict[str, Any]],
    delivery_rows: dict[str, dict[str, Any]],
    pending_grace_minutes: int,
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    apify_by_run = {run["run_id"]: run for run in apify_runs if run.get("run_id")}
    run_ids = set(apify_by_run) | set(webhook_rows) | set(opportunity_rows) | set(delivery_rows)
    reports: list[dict[str, Any]] = []
    for run_id in sorted(run_ids):
        apify_run = apify_by_run.get(run_id)
        webhook = webhook_rows.get(run_id)
        opportunities = opportunity_rows.get(run_id)
        delivery = delivery_rows.get(run_id)
        issues = classify_run(
            run_id=run_id,
            apify_run=apify_run,
            webhook=webhook,
            opportunities=opportunities,
            delivery=delivery,
            now_utc=now_utc,
            pending_grace_minutes=pending_grace_minutes,
        )
        reports.append(
            {
                "run_id": run_id,
                "apify": apify_run,
                "webhook": webhook,
                "opportunities": opportunities,
                "delivery": delivery,
                "issues": issues,
            }
        )
    reports.sort(
        key=lambda report: (
            (report["apify"] or {}).get("started_at")
            or parse_datetime((report["webhook"] or {}).get("last_received_at"))
            or parse_datetime((report["opportunities"] or {}).get("last_processed_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return reports


def print_issue_summary(reports: list[dict[str, Any]]) -> None:
    counter: Counter[str] = Counter()
    for report in reports:
        counter.update(report["issues"])
    print("Issue summary")
    if not counter:
        print("- none")
        return
    for issue, count in counter.most_common():
        print(f"- {issue}: {count}")


def _format_status_counts(statuses: dict[str, int]) -> str:
    if not statuses:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(statuses.items()))


def print_reports(reports: list[dict[str, Any]], summary_only: bool) -> None:
    print("\nRuns")
    if not reports:
        print("- none in requested window")
        return

    for report in reports:
        issues = report["issues"]
        if summary_only and not issues:
            continue

        apify = report["apify"] or {}
        webhook = report["webhook"] or {}
        opportunities = report["opportunities"] or {}
        delivery = report["delivery"] or {}
        channels = delivery.get("channels") or {}
        actor_name = apify.get("actor_name") or "unknown"
        apify_status = apify.get("status") or "n/a"
        item_count = apify.get("item_count")
        print(
            "- "
            f"run_id={report['run_id']} | actor={actor_name} | apify_status={apify_status} | "
            f"dataset_id={apify.get('dataset_id') or 'n/a'} | items={item_count if item_count is not None else 'n/a'} | "
            f"started={format_datetime(apify.get('started_at'))} | finished={format_datetime(apify.get('finished_at'))}"
        )
        print(
            "  "
            f"webhook={webhook.get('latest_status') or 'missing'} | entries={webhook.get('webhook_entries') or 0} | "
            f"item_count={webhook.get('max_item_count') if webhook.get('max_item_count') is not None else 'n/a'} | "
            f"last_received={format_datetime(parse_datetime(webhook.get('last_received_at')))}"
        )
        print(
            "  "
            f"opportunities={opportunities.get('opportunity_rows') or 0} | "
            f"complete={opportunities.get('complete_rows') or 0} | "
            f"duplicates={opportunities.get('duplicate_rows') or 0} | "
            f"last_processed={format_datetime(parse_datetime(opportunities.get('last_processed_at')))}"
        )
        if channels:
            for channel_name in sorted(channels):
                channel = channels[channel_name]
                print(
                    "  "
                    f"{channel_name}={_format_status_counts(channel.get('statuses') or {})} | "
                    f"rows={channel.get('total_rows') or 0} | attempts={channel.get('total_attempts') or 0}"
                )
        else:
            print("  delivery=missing")
        if webhook.get("latest_error"):
            print(f"  webhook_error={str(webhook['latest_error'])[:200]}")
        print("  issues=" + (", ".join(issues) if issues else "none"))


def summarize(reports: list[dict[str, Any]]) -> dict[str, Any]:
    issue_counts: Counter[str] = Counter()
    for report in reports:
        issue_counts.update(report["issues"])
    return {
        "run_count": len(reports),
        "issue_counts": dict(issue_counts),
        "runs_with_issues": sum(1 for report in reports if report["issues"]),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare recent Apify runs to webhook_log, opportunities, and ingest_delivery_log."
    )
    parser.add_argument("--dsn", help="Postgres connection string. Defaults to DATABASE_URL/SUPABASE_DB_URL.")
    parser.add_argument(
        "--env-file",
        help="Optional env file to read DATABASE_URL and APIFY_TOKEN from when not exported in the shell.",
    )
    parser.add_argument("--apify-token", help="Apify API token. Defaults to APIFY_TOKEN/APIFY_API_TOKEN.")
    parser.add_argument(
        "--runs-json",
        help="Optional Apify runs export JSON to use instead of fetching Apify over the network.",
    )
    parser.add_argument(
        "--actors",
        nargs="+",
        default=[],
        help="Optional actor names or actor ids to limit the compare set. Defaults to all actors in apify/deployment.json.",
    )
    parser.add_argument(
        "--start",
        help="Window start in ISO-8601. Overrides --lookback-hours.",
    )
    parser.add_argument(
        "--end",
        help="Window end in ISO-8601. Default: now.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=12,
        help="Hours to look back when --start is not provided. Default: 12.",
    )
    parser.add_argument(
        "--limit-per-actor",
        type=int,
        default=100,
        help="Maximum Apify runs to fetch per actor. Default: 100.",
    )
    parser.add_argument(
        "--pending-grace-minutes",
        type=int,
        default=30,
        help="Treat pending webhook rows older than this as stale. Default: 30.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print runs that have issues.",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit 1 when the compare finds any missing/degraded landing evidence.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the text report.",
    )
    args = parser.parse_args(argv)

    start = parse_datetime(args.start) if args.start else None
    end = parse_datetime(args.end) if args.end else datetime.now(timezone.utc)
    if end is None:
        print("--end must be ISO-8601 if provided.", file=sys.stderr)
        return 2
    if start is None:
        start = end - timedelta(hours=args.lookback_hours)
    if start > end:
        print("Window start must be before window end.", file=sys.stderr)
        return 2

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print("DATABASE_URL (or --dsn) is required for reconciliation.", file=sys.stderr)
        return 2

    actors = load_actor_registry(args.actors)
    apify_runs: list[dict[str, Any]]
    if args.runs_json:
        apify_runs = load_runs_from_json(Path(args.runs_json), actors, start=start, end=end)
    else:
        apify_token = _get_env_value(args.apify_token, APIFY_TOKEN_KEYS, args.env_file)
        if not apify_token:
            print("APIFY_TOKEN/APIFY_API_TOKEN (or --apify-token or --runs-json) is required for Apify comparison.", file=sys.stderr)
            return 2
        try:
            apify_runs = fetch_runs_from_apify(
                actors=actors,
                token=apify_token,
                start=start,
                end=end,
                limit_per_actor=args.limit_per_actor,
            )
        except Exception as exc:
            print(f"Unable to fetch Apify runs: {exc}", file=sys.stderr)
            return 2

    try:
        connection = connect(dsn)
    except Exception as exc:
        print(f"Unable to connect to live database: {exc}", file=sys.stderr)
        return 2

    actor_ids = list(actors.values())
    source_names = derive_source_names(actors)

    try:
        webhook_rows = fetch_webhook_rows(connection, start=start, end=end, actor_ids=actor_ids)
        opportunity_rows = fetch_opportunity_rows(connection, start=start, end=end, sources=source_names)
        delivery_rows = fetch_delivery_rows(connection, start=start, end=end)
    except Exception as exc:
        connection.close()
        print(f"Unable to query reconciliation tables: {exc}", file=sys.stderr)
        return 2
    finally:
        if not connection.closed:
            connection.close()

    reports = build_reports(
        apify_runs=apify_runs,
        webhook_rows=webhook_rows,
        opportunity_rows=opportunity_rows,
        delivery_rows=delivery_rows,
        pending_grace_minutes=args.pending_grace_minutes,
    )

    if args.json:
        output = {
            "window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "actors": actors,
            "summary": summarize(reports),
            "reports": reports,
        }
        print(
            json.dumps(
                output,
                default=lambda value: value.isoformat() if isinstance(value, datetime) else value,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            "Window: "
            f"{format_datetime(start)} -> {format_datetime(end)} | "
            f"actors={len(actors)} | apify_runs={len(apify_runs)} | "
            f"db_webhook_runs={len(webhook_rows)} | db_opportunity_runs={len(opportunity_rows)}"
        )
        print_issue_summary(reports)
        print_reports(reports, summary_only=args.summary_only)

    if args.fail_on_issues and any(report["issues"] for report in reports):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
