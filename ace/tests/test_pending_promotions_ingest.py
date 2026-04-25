from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ace.pending_promotions_ingest import (
    PendingPromotionParseError,
    PendingPromotionSchemaError,
    ingest_continuity_pending_promotions,
)
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pending_promotions"
SOURCE_LABEL = "continuity/pending-promotions.json"
INGEST_ACTOR = "ace.pending_promotions_ingest"


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _required_source_item(raw_item: dict[str, object]) -> dict[str, str]:
    return {
        "id": str(raw_item["id"]),
        "title": str(raw_item["title"]),
        "source": str(raw_item["source"]),
        "reason": str(raw_item["reason"]),
        "created_at": str(raw_item["created_at"]),
        "status": str(raw_item["status"]),
    }


def _canonical_item_json(*, item_id: str, title: str, source: str, reason: str, created_at: str, status: str) -> str:
    return json.dumps(
        {
            "id": item_id,
            "title": title,
            "source": source,
            "reason": reason,
            "created_at": created_at,
            "status": status,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_digest(*, item: dict[str, str]) -> str:
    return hashlib.sha256(
        _canonical_item_json(
            item_id=item["id"],
            title=item["title"],
            source=item["source"],
            reason=item["reason"],
            created_at=item["created_at"],
            status=item["status"],
        ).encode("utf-8")
    ).hexdigest()


class ContinuityPendingPromotionsIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_valid_ingest_imports_only_pending_rows_and_ignores_non_pending_rows(self) -> None:
        fixture = _load_fixture(FIXTURES / "valid.json")
        source_items = [_required_source_item(item) for item in fixture["items"] if item["status"] == "pending"]

        results = ingest_continuity_pending_promotions(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )

        self.assertEqual(len(results), 2)
        repo = ItemRepository(self.db_path)
        items = repo.list_items()
        self.assertEqual([item.item_type for item in items], ["continuity_pending_promotion", "continuity_pending_promotion"])
        self.assertEqual([item.state for item in items], ["TRIAGE", "TRIAGE"])
        self.assertEqual([item.title for item in items], ["Pending promotion alpha", "Pending promotion beta"])
        self.assertEqual([item.description for item in items], ["alpha reason", "beta reason"])
        self.assertEqual([item.source for item in items], [SOURCE_LABEL, SOURCE_LABEL])
        self.assertEqual(
            [item.source_session for item in items],
            [f"{SOURCE_LABEL}|{item['id']}|{_canonical_digest(item=item)}" for item in source_items],
        )

        with connect(self.db_path) as connection:
            evidence_rows = connection.execute(
                "SELECT item_id, evidence_text, evidence_uri, created_by FROM evidence ORDER BY created_at ASC, id ASC"
            ).fetchall()

        self.assertEqual(len(evidence_rows), 2)
        self.assertEqual(
            dict(evidence_rows[0]),
            {
                "item_id": items[0].id,
                "evidence_text": _canonical_item_json(
                    item_id=source_items[0]["id"],
                    title=source_items[0]["title"],
                    source=source_items[0]["source"],
                    reason=source_items[0]["reason"],
                    created_at=source_items[0]["created_at"],
                    status=source_items[0]["status"],
                ),
                "evidence_uri": SOURCE_LABEL,
                "created_by": INGEST_ACTOR,
            },
        )
        self.assertEqual(
            dict(evidence_rows[1]),
            {
                "item_id": items[1].id,
                "evidence_text": _canonical_item_json(
                    item_id=source_items[1]["id"],
                    title=source_items[1]["title"],
                    source=source_items[1]["source"],
                    reason=source_items[1]["reason"],
                    created_at=source_items[1]["created_at"],
                    status=source_items[1]["status"],
                ),
                "evidence_uri": SOURCE_LABEL,
                "created_by": INGEST_ACTOR,
            },
        )

    def test_malformed_json_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(PendingPromotionParseError):
            ingest_continuity_pending_promotions(
                self.db_path,
                source_path=FIXTURES / "malformed.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_missing_required_field_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(PendingPromotionSchemaError):
            ingest_continuity_pending_promotions(
                self.db_path,
                source_path=FIXTURES / "invalid_missing_required.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_replay_reuses_existing_rows_and_does_not_duplicate_evidence(self) -> None:
        first = ingest_continuity_pending_promotions(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )
        second = ingest_continuity_pending_promotions(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )

        self.assertEqual([item.id for item in first], [item.id for item in second])

        with connect(self.db_path) as connection:
            item_count = connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()["count"]
            evidence_count = connection.execute("SELECT COUNT(*) AS count FROM evidence").fetchone()["count"]

        self.assertEqual(item_count, 2)
        self.assertEqual(evidence_count, 2)


if __name__ == "__main__":
    unittest.main()
