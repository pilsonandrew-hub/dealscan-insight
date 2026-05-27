from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from ace.propose_commitments import DECISION_LOG_PATH, PROPOSAL_SOURCE
from ace.storage import DB_PATH, STATE_DIR, connect_readonly

TELEGRAM_DIRECT_SOURCE = "telegram/direct"
LOOSE_ENDS_PREFIX = "loose_ends"
PROPOSE_PREFIX = "propose"
TELEGRAM_PREFIX = "telegram"

DRIFT_RATIO_THRESHOLD = 0.25
MIN_TUNING_SAMPLES = 2
HEALTHY_RATIO_THRESHOLD = 0.5

TABLE_HEADER = (
    f"{'filter':<36} {'month':<8} {'signal':>6} {'noise':>6} {'pending':>7} "
    f"{'ratio':>6} {'status':<24}"
)


@dataclass(frozen=True)
class FilterHealthRow:
    filter_id: str
    month: str
    signal: int
    noise: int
    pending: int
    ratio: float | None
    status: str


def _parse_month_label(raw: str | None) -> str:
    if raw is None or not str(raw).strip():
        now = datetime.now(timezone.utc)
        return f"{now.year:04d}-{now.month:02d}"
    label = str(raw).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", label):
        raise ValueError(f"invalid month label: {label} (expected YYYY-MM)")
    year_str, month_str = label.split("-", 1)
    month = int(month_str)
    if month < 1 or month > 12:
        raise ValueError(f"invalid month label: {label}")
    return label


def _month_from_timestamp(value: str) -> str | None:
    normalized = str(value).strip()
    if len(normalized) < 7:
        return None
    return normalized[:7]


def _ratio(signal: int, noise: int) -> float | None:
    total = signal + noise
    if total == 0:
        return None
    return round(signal / total, 2)


def _status_for_tuning(*, signal: int, noise: int, ratio: float | None) -> str:
    samples = signal + noise
    if samples < MIN_TUNING_SAMPLES:
        return "insufficient_data"
    if ratio is None:
        return "insufficient_data"
    if ratio < DRIFT_RATIO_THRESHOLD:
        return "warn:drifting"
    if ratio >= HEALTHY_RATIO_THRESHOLD:
        return "ok"
    return "watch:weak_signal"


def load_propose_decision_records(path: Path = DECISION_LOG_PATH) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def propose_filter_rows(
    records: Iterable[dict[str, object]],
    *,
    month: str,
    db_path: Path | str = DB_PATH,
) -> list[FilterHealthRow]:
    buckets: dict[str, dict[str, int]] = {}
    for record in records:
        decided_at = str(record.get("decided_at") or "")
        record_month = _month_from_timestamp(decided_at)
        if record_month != month:
            continue
        parser_rule = str(record.get("parser_rule") or "unknown")
        filter_id = f"{PROPOSE_PREFIX}:{parser_rule}"
        bucket = buckets.setdefault(filter_id, {"signal": 0, "noise": 0, "pending": 0})
        decision = str(record.get("decision") or "").strip().lower()
        if decision == "accept":
            bucket["signal"] += 1
        elif decision == "reject":
            bucket["noise"] += 1

    pending_counts = _pending_proposal_counts(db_path=db_path, month=month)
    rows: list[FilterHealthRow] = []
    all_filters = set(buckets) | set(pending_counts)
    for filter_id in sorted(all_filters):
        counts = buckets.get(filter_id, {"signal": 0, "noise": 0, "pending": 0})
        pending = pending_counts.get(filter_id, 0)
        signal = counts["signal"]
        noise = counts["noise"]
        ratio = _ratio(signal, noise)
        rows.append(
            FilterHealthRow(
                filter_id=filter_id,
                month=month,
                signal=signal,
                noise=noise,
                pending=pending,
                ratio=ratio,
                status=_status_for_tuning(signal=signal, noise=noise, ratio=ratio),
            )
        )
    return rows


def _pending_proposal_counts(*, db_path: Path | str, month: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with connect_readonly(db_path) as connection:
        rows = connection.execute(
            """
            SELECT items.created_at, events.payload_json
            FROM items
            JOIN events ON events.item_id = items.id AND events.event_type = 'item.created'
            WHERE items.source = ?
              AND items.state = 'TRIAGE'
            """,
            (PROPOSAL_SOURCE,),
        ).fetchall()
    for row in rows:
        created_month = _month_from_timestamp(str(row["created_at"]))
        if created_month != month:
            continue
        parser_rule = _parser_rule_from_payload(str(row["payload_json"] or ""))
        filter_id = f"{PROPOSE_PREFIX}:{parser_rule}"
        counts[filter_id] = counts.get(filter_id, 0) + 1
    return counts


def _parser_rule_from_payload(payload_json: str) -> str:
    if not payload_json:
        return "unknown"
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return "unknown"
    if isinstance(payload, dict):
        return str(payload.get("parser_rule") or "unknown")
    return "unknown"


def telegram_direct_work_rows(*, db_path: Path | str, month: str) -> list[FilterHealthRow]:
    buckets: dict[str, dict[str, int]] = {}
    with connect_readonly(db_path) as connection:
        rows = connection.execute(
            """
            SELECT items.state, items.created_at, events.payload_json
            FROM items
            JOIN events ON events.item_id = items.id AND events.event_type = 'item.created'
            WHERE items.source = ?
            """,
            (TELEGRAM_DIRECT_SOURCE,),
        ).fetchall()
    for row in rows:
        created_month = _month_from_timestamp(str(row["created_at"]))
        if created_month != month:
            continue
        parser_rule = _parser_rule_from_payload(str(row["payload_json"] or ""))
        filter_id = f"{TELEGRAM_PREFIX}:{parser_rule}"
        bucket = buckets.setdefault(filter_id, {"signal": 0, "noise": 0, "pending": 0})
        state = str(row["state"] or "").upper()
        if state == "DROPPED":
            bucket["noise"] += 1
        elif state == "TRIAGE":
            bucket["pending"] += 1
        else:
            bucket["signal"] += 1

    rows_out: list[FilterHealthRow] = []
    for filter_id in sorted(buckets):
        counts = buckets[filter_id]
        signal = counts["signal"]
        noise = counts["noise"]
        pending = counts["pending"]
        ratio = _ratio(signal, noise)
        rows_out.append(
            FilterHealthRow(
                filter_id=filter_id,
                month=month,
                signal=signal,
                noise=noise,
                pending=pending,
                ratio=ratio,
                status=_status_for_tuning(signal=signal, noise=noise, ratio=ratio),
            )
        )
    return rows_out


def loose_ends_snapshot_rows(*, db_path: Path | str, month: str) -> list[FilterHealthRow]:
    from ace.ace import _loose_end_rows

    findings = _loose_end_rows(db_path)
    buckets: dict[str, int] = {}
    for finding in findings:
        pattern = str(finding.get("pattern_name") or "unknown")
        buckets[pattern] = buckets.get(pattern, 0) + 1

    rows: list[FilterHealthRow] = []
    for pattern_name in sorted(buckets):
        count = buckets[pattern_name]
        rows.append(
            FilterHealthRow(
                filter_id=f"{LOOSE_ENDS_PREFIX}:{pattern_name}",
                month=month,
                signal=count,
                noise=0,
                pending=0,
                ratio=None,
                status="snapshot_only",
            )
        )
    return rows


def build_filter_health_rows(
    *,
    db_path: Path | str = DB_PATH,
    month: str,
    decisions_log: Path = DECISION_LOG_PATH,
) -> list[FilterHealthRow]:
    records = load_propose_decision_records(decisions_log)
    rows = propose_filter_rows(records, month=month, db_path=db_path)
    rows.extend(telegram_direct_work_rows(db_path=db_path, month=month))
    rows.extend(loose_ends_snapshot_rows(db_path=db_path, month=month))
    rows.sort(key=lambda row: (row.status, row.filter_id))
    return rows


def render_filter_health_table(rows: Sequence[FilterHealthRow]) -> str:
    lines = [TABLE_HEADER]
    for row in rows:
        ratio_label = "" if row.ratio is None else f"{row.ratio:.2f}"
        lines.append(
            f"{row.filter_id:<36} {row.month:<8} {row.signal:>6} {row.noise:>6} {row.pending:>7} "
            f"{ratio_label:>6} {row.status:<24}"
        )
    return "\n".join(lines)


def drift_warnings(rows: Sequence[FilterHealthRow]) -> list[str]:
    warnings: list[str] = []
    for row in rows:
        if row.status == "warn:drifting":
            ratio_label = "n/a" if row.ratio is None else f"{row.ratio:.2f}"
            warnings.append(
                f"{row.filter_id} ({row.month}) signal-to-noise={ratio_label} "
                f"signal={row.signal} noise={row.noise} — filter may be drifting toward useless"
            )
    return warnings


def run_filter_health_command(
    *,
    db_path: Path | str = DB_PATH,
    month: str | None = None,
    decisions_log: Path | None = None,
) -> int:
    try:
        month_label = _parse_month_label(month)
    except ValueError as exc:
        print(f"error={exc}")
        return 1

    log_path = decisions_log or DECISION_LOG_PATH
    rows = build_filter_health_rows(db_path=db_path, month=month_label, decisions_log=log_path)

    print(f"filter_health.month={month_label}")
    print(f"filter_health.decisions_log={log_path}")
    print(f"filter_health.row_count={len(rows)}")
    if not rows:
        print("filter_health.note=no filter metrics for this month")
        return 0

    print(render_filter_health_table(rows))
    warnings = drift_warnings(rows)
    if warnings:
        print("")
        print("Drift warnings:")
        for warning in warnings:
            print(f"- {warning}")
    return 0
