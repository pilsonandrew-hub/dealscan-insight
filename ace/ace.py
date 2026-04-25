from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace.repository import ItemRepository, ValidationError
from ace.storage import DB_PATH, bootstrap_db
from ace.workflow import AceError, normalize_state


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ace", description="Super A.C.E. V1 operator entrypoint")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to the ACE SQLite database")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize the local ACE database")
    subparsers.add_parser("bootstrap", help="Alias for init")

    intake = subparsers.add_parser("intake", help="Create a new TRIAGE item")
    intake.add_argument("item_type")
    intake.add_argument("title")
    intake.add_argument("--description")
    intake.add_argument("--priority-hint")
    intake.add_argument("--source")
    intake.add_argument("--session")
    intake.add_argument("--deadline")
    intake.add_argument("--owner")
    intake.add_argument("--actor")

    list_cmd = subparsers.add_parser("list", help="List items")
    list_cmd.add_argument("--state")

    show = subparsers.add_parser("show", help="Show a single item")
    show.add_argument("item_id")
    show.add_argument("--event-type")
    show.add_argument("--event-limit", type=int)

    evidence = subparsers.add_parser("add-evidence", help="Add evidence for an item")
    evidence.add_argument("item_id")
    evidence.add_argument("evidence_text")
    evidence.add_argument("--evidence-uri")
    evidence.add_argument("--created-by")
    evidence.add_argument("--actor")

    obligation = subparsers.add_parser("add-obligation", help="Add an obligation for an item")
    obligation.add_argument("item_id")
    obligation.add_argument("obligation_type")
    obligation.add_argument("--status", default="open")
    obligation.add_argument("--target-surface")
    obligation.add_argument("--notes")
    obligation.add_argument("--actor")

    contradiction = subparsers.add_parser("add-contradiction", help="Add a contradiction for an item")
    contradiction.add_argument("item_id", help="The item being contradicted")
    contradiction.add_argument("source_item_id", help="The item that contradicts it")
    contradiction.add_argument("--status", default="open")
    contradiction.add_argument("--reason")
    contradiction.add_argument("--actor")

    resolve_contradiction = subparsers.add_parser(
        "resolve-contradiction",
        help="Resolve an existing contradiction",
    )
    resolve_contradiction.add_argument("contradiction_id")
    resolve_contradiction.add_argument("--reason")
    resolve_contradiction.add_argument("--actor")

    resolve_obligation = subparsers.add_parser(
        "resolve-obligation",
        help="Resolve an existing obligation",
    )
    resolve_obligation.add_argument("obligation_id")
    resolve_obligation.add_argument("--reason")
    resolve_obligation.add_argument("--actor")

    for name in ("approve", "block", "done", "resolve", "drop"):
        command = subparsers.add_parser(name, help=f"Apply the {name} transition")
        command.add_argument("item_id")
        command.add_argument("--reason")
        command.add_argument("--actor")
        command.add_argument("--source")
        command.add_argument("--session")

    return parser


def _print_item(item) -> None:
    print(
        "item_id={id} item_type={item_type} state={state} title={title}".format(
            id=item.id,
            item_type=item.item_type,
            state=item.state,
            title=item.title,
        )
    )
    if item.description:
        print(f"description={item.description}")
    if item.priority_hint:
        print(f"priority_hint={item.priority_hint}")
    if item.source:
        print(f"source={item.source}")
    if item.source_session:
        print(f"session={item.source_session}")
    if item.deadline_at:
        print(f"deadline={item.deadline_at}")
    if item.owner:
        print(f"owner={item.owner}")
    if item.closed_at:
        print(f"closed_at={item.closed_at}")
    if item.closed_by:
        print(f"closed_by={item.closed_by}")
    if item.closed_reason:
        print(f"closed_reason={item.closed_reason}")
    if item.last_event_id:
        print(f"last_event_id={item.last_event_id}")


def _print_item_events(events: Iterable) -> None:
    events = list(events)
    print(f"event_count={len(events)}")
    for index, event in enumerate(events):
        print(f"event[{index}].id={event.event_id}")
        print(f"event[{index}].type={event.event_type}")
        print(f"event[{index}].created_at={event.created_at}")
        if event.actor:
            print(f"event[{index}].actor={event.actor}")
        if event.source:
            print(f"event[{index}].source={event.source}")
        if event.session_id:
            print(f"event[{index}].session={event.session_id}")
        print(f"event[{index}].payload_status={event.payload_status}")
        if event.payload_json is not None:
            print(f"event[{index}].payload={event.payload_json}")
        if event.payload_raw is not None:
            print(f"event[{index}].payload_raw={event.payload_raw}")


def _print_items(items: Iterable) -> None:
    items = list(items)
    print(f"count={len(items)}")
    for item in items:
        print(
            "item_id={id} state={state} title={title}".format(
                id=item.id,
                state=item.state,
                title=item.title,
            )
        )


def _print_evidence_added(*, item_id: str, evidence_id: str) -> None:
    print(f"item_id={item_id} evidence_id={evidence_id}")


def _print_obligation_added(*, item_id: str, obligation_id: str) -> None:
    print(f"item_id={item_id} obligation_id={obligation_id}")


def _print_contradiction_added(*, item_id: str, contradiction_id: str) -> None:
    print(f"item_id={item_id} contradiction_id={contradiction_id}")


def _print_contradiction_resolved(*, contradiction_id: str, item_id: str, status: str) -> None:
    print(f"contradiction_id={contradiction_id} item_id={item_id} status={status}")


def _print_obligation_resolved(*, obligation_id: str, item_id: str, status: str) -> None:
    print(f"obligation_id={obligation_id} item_id={item_id} status={status}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db)

    command = args.command or "init"
    if command in {"init", "bootstrap"}:
        bootstrap_db(db_path)
        print(f"Initialized ACE state at {db_path}")
        return 0

    repo = ItemRepository(db_path)

    try:
        if command == "intake":
            item = repo.create_item(
                item_type=_normalize_required_text(args.item_type, field_name="item_type"),
                title=_normalize_required_text(args.title, field_name="title"),
                description=_normalize_optional_text(args.description, field_name="description"),
                priority_hint=_normalize_optional_text(args.priority_hint, field_name="priority_hint"),
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                deadline_at=args.deadline,
                owner=_normalize_optional_text(args.owner, field_name="owner"),
                actor=args.actor,
            )
            _print_item(item)
            return 0

        if command == "list":
            normalized_state = normalize_state(args.state) if args.state is not None else None
            items = repo.list_items(state=normalized_state)
            _print_items(items)
            return 0

        if command == "show":
            if args.event_limit is not None and args.event_limit <= 0:
                print(f"error=invalid_event_limit event_limit={args.event_limit}")
                return 1
            normalized_event_type = args.event_type
            if normalized_event_type is not None:
                normalized_event_type = normalized_event_type.strip()
                if not normalized_event_type:
                    print(f"error=invalid_event_type event_type={args.event_type}")
                    return 1
            item = repo.get_item(args.item_id)
            if item is None:
                print(f"error=unknown_item_id item_id={args.item_id}")
                return 1
            _print_item(item)
            _print_item_events(
                repo.list_item_events(
                    args.item_id,
                    event_type=normalized_event_type,
                    limit=args.event_limit,
                )
            )
            return 0

        if command == "add-evidence":
            evidence_id = repo.add_evidence(
                args.item_id,
                evidence_text=_normalize_required_text(args.evidence_text, field_name="evidence_text"),
                evidence_uri=_normalize_optional_text(args.evidence_uri, field_name="evidence_uri"),
                created_by=_normalize_optional_text(args.created_by, field_name="created_by"),
                actor=args.actor,
            )
            _print_evidence_added(item_id=args.item_id, evidence_id=evidence_id)
            return 0

        if command == "add-obligation":
            obligation_id = repo.add_obligation(
                args.item_id,
                obligation_type=_normalize_required_text(args.obligation_type, field_name="obligation_type"),
                status=_normalize_required_text(args.status, field_name="status").lower(),
                target_surface=_normalize_optional_text(args.target_surface, field_name="target_surface"),
                notes=_normalize_optional_text(args.notes, field_name="notes"),
                actor=args.actor,
            )
            _print_obligation_added(item_id=args.item_id, obligation_id=obligation_id)
            return 0

        if command == "add-contradiction":
            contradiction_id = repo.add_contradiction(
                args.item_id,
                source_item_id=args.source_item_id,
                status=args.status,
                reason=_normalize_optional_text(args.reason, field_name="reason"),
                actor=args.actor,
            )
            _print_contradiction_added(item_id=args.item_id, contradiction_id=contradiction_id)
            return 0

        if command == "resolve-contradiction":
            result = repo.resolve_contradiction(
                args.contradiction_id,
                reason=_normalize_required_text(args.reason, field_name="reason") if args.reason is not None else None,
                actor=args.actor,
            )
            _print_contradiction_resolved(
                contradiction_id=result["contradiction_id"],
                item_id=result["item_id"],
                status=result["status"],
            )
            return 0

        if command == "resolve-obligation":
            result = repo.resolve_obligation(
                args.obligation_id,
                reason=_normalize_required_text(args.reason, field_name="reason") if args.reason is not None else None,
                actor=args.actor,
            )
            _print_obligation_resolved(
                obligation_id=result["obligation_id"],
                item_id=result["item_id"],
                status=result["status"],
            )
            return 0

        if command in {"approve", "block", "done", "resolve", "drop"}:
            item = repo.apply_action(
                args.item_id,
                command,
                actor=args.actor,
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                reason=_normalize_optional_text(args.reason, field_name="reason"),
            )
            _print_item(item)
            return 0
    except AceError as exc:
        print(f"error={exc}")
        return 1
    except KeyError as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error={message}")
        return 1
    except ValidationError as exc:
        print(f"error={exc}")
        return 1

    parser.error(f"unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
