from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import ItemRepository
from .storage import DB_PATH, bootstrap_db, utc_now
from .sweep import SweepFinding, SweepThresholds, collect_sweep_findings


@dataclass(frozen=True)
class BriefingSection:
    key: str
    title: str
    items: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "count": len(self.items),
            "items": self.items,
        }


def generate_briefing(
    db_path: Path | str = DB_PATH,
    *,
    thresholds: SweepThresholds | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    repo = ItemRepository(db_path)
    generated_at = now or utc_now()
    thresholds = thresholds or SweepThresholds()

    findings = collect_sweep_findings(db_path, thresholds=thresholds, now=generated_at)
    open_items = repo.list_items()
    sections = _build_sections(repo, open_items=open_items, findings=findings)

    return {
        "generated_at": generated_at,
        "thresholds": thresholds.as_dict(),
        "item_count": len(open_items),
        "section_count": len(sections),
        "sections": [section.as_dict() for section in sections],
    }


def render_briefing_text(briefing: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"generated_at={briefing['generated_at']}")
    lines.append(f"item_count={briefing['item_count']}")
    lines.append(f"section_count={briefing['section_count']}")

    for index, section in enumerate(briefing.get("sections", [])):
        lines.append(f"section[{index}].key={section['key']}")
        lines.append(f"section[{index}].title={section['title']}")
        lines.append(f"section[{index}].count={section['count']}")
        for item_index, item in enumerate(section.get("items", [])):
            prefix = f"section[{index}].item[{item_index}]"
            lines.append(f"{prefix}.item_id={item['item_id']}")
            lines.append(f"{prefix}.state={item['state']}")
            lines.append(f"{prefix}.title={item['title']}")
            if item.get("classification") is not None:
                lines.append(f"{prefix}.classification={item['classification']}")
            if item.get("activity_at") is not None:
                lines.append(f"{prefix}.activity_at={item['activity_at']}")
            if item.get("age_seconds") is not None:
                lines.append(f"{prefix}.age_seconds={item['age_seconds']}")
            if item.get("stale_after_seconds") is not None:
                lines.append(f"{prefix}.stale_after_seconds={item['stale_after_seconds']}")
            if item.get("evidence_count") is not None:
                lines.append(f"{prefix}.evidence_count={item['evidence_count']}")
            if item.get("open_obligation_count") is not None:
                lines.append(f"{prefix}.open_obligation_count={item['open_obligation_count']}")
            if item.get("open_contradiction_count") is not None:
                lines.append(f"{prefix}.open_contradiction_count={item['open_contradiction_count']}")
            if item.get("last_event_id") is not None:
                lines.append(f"{prefix}.last_event_id={item['last_event_id']}")
            if item.get("source") is not None:
                lines.append(f"{prefix}.source={item['source']}")
            if item.get("source_session") is not None:
                lines.append(f"{prefix}.source_session={item['source_session']}")
    return "\n".join(lines)


def _build_sections(
    repo: ItemRepository,
    *,
    open_items: list[Any],
    findings: list[SweepFinding],
) -> list[BriefingSection]:
    finding_by_item_id = {finding.item_id: finding for finding in findings}
    stale_item_ids = {finding.item_id for finding in findings}

    stale_items = [_serialize_finding(finding) for finding in findings]
    blocked_items = [
        _serialize_blocked_item(repo, item, finding_by_item_id.get(item.id))
        for item in open_items
        if item.state == "BLOCKED" and item.id not in stale_item_ids
    ]
    needs_decision_items = [
        _serialize_decision_item(repo, item)
        for item in open_items
        if item.state == "TRIAGE" and item.id not in stale_item_ids
    ]
    claimed_done_items = [
        _serialize_claimed_done_item(repo, item, finding_by_item_id.get(item.id))
        for item in open_items
        if item.state == "CLAIMED_DONE" and item.id not in stale_item_ids
    ]

    sections: list[BriefingSection] = []
    if stale_items:
        sections.append(BriefingSection(key="stale", title="Stale work", items=stale_items))
    if blocked_items:
        sections.append(BriefingSection(key="blocked", title="Blocked work", items=blocked_items))
    if needs_decision_items:
        sections.append(BriefingSection(key="needs_decision", title="Needs decision", items=needs_decision_items))
    if claimed_done_items:
        sections.append(BriefingSection(key="claimed_done", title="Claimed done awaiting closeout", items=claimed_done_items))
    return sections


def _serialize_finding(finding: SweepFinding) -> dict[str, Any]:
    return finding.as_dict()


def _serialize_blocked_item(repo: ItemRepository, item: Any, finding: SweepFinding | None) -> dict[str, Any]:
    return {
        "item_id": item.id,
        "state": item.state,
        "title": item.title,
        "classification": finding.classification if finding else None,
        "activity_at": finding.activity_at if finding else item.updated_at or item.created_at,
        "age_seconds": finding.age_seconds if finding else None,
        "stale_after_seconds": finding.stale_after_seconds if finding else None,
        "evidence_count": repo.item_evidence_count(item.id),
        "open_obligation_count": repo.item_open_obligation_count(item.id),
        "open_contradiction_count": repo.item_open_contradiction_count(item.id),
        "last_event_id": item.last_event_id,
        "source": item.source,
        "source_session": item.source_session,
    }


def _serialize_decision_item(repo: ItemRepository, item: Any) -> dict[str, Any]:
    return {
        "item_id": item.id,
        "state": item.state,
        "title": item.title,
        "classification": None,
        "activity_at": item.updated_at or item.created_at,
        "age_seconds": None,
        "stale_after_seconds": None,
        "evidence_count": repo.item_evidence_count(item.id),
        "open_obligation_count": repo.item_open_obligation_count(item.id),
        "open_contradiction_count": repo.item_open_contradiction_count(item.id),
        "last_event_id": item.last_event_id,
        "source": item.source,
        "source_session": item.source_session,
    }


def _serialize_claimed_done_item(repo: ItemRepository, item: Any, finding: SweepFinding | None) -> dict[str, Any]:
    return {
        "item_id": item.id,
        "state": item.state,
        "title": item.title,
        "classification": finding.classification if finding else None,
        "activity_at": finding.activity_at if finding else item.updated_at or item.created_at,
        "age_seconds": finding.age_seconds if finding else None,
        "stale_after_seconds": finding.stale_after_seconds if finding else None,
        "evidence_count": repo.item_evidence_count(item.id),
        "open_obligation_count": repo.item_open_obligation_count(item.id),
        "open_contradiction_count": repo.item_open_contradiction_count(item.id),
        "last_event_id": item.last_event_id,
        "source": item.source,
        "source_session": item.source_session,
    }
