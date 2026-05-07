from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.briefing import generate_briefing, render_briefing_text
from ace.repository import ItemRepository
from ace.storage import bootstrap_db


def _hours_after(timestamp: str, hours: int) -> str:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed + timedelta(hours=hours)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class BriefingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generate_briefing_includes_stale_section_from_live_db_truth(self) -> None:
        item = self.repo.create_item(item_type="task", title="Stale triage", actor="test")
        stale_now = _hours_after(item.created_at, 25)

        briefing = generate_briefing(self.db_path, now=stale_now)

        self.assertEqual(briefing["section_count"], 1)
        stale_section = briefing["sections"][0]
        self.assertEqual(stale_section["key"], "stale")
        self.assertEqual(stale_section["items"][0]["item_id"], item.id)
        self.assertEqual(stale_section["items"][0]["classification"], "stale_triage")

    def test_generate_briefing_does_not_duplicate_stale_triage_into_needs_decision(self) -> None:
        item = self.repo.create_item(item_type="task", title="Stale triage", actor="test")
        stale_now = _hours_after(item.created_at, 25)

        briefing = generate_briefing(self.db_path, now=stale_now)
        keys = [section["key"] for section in briefing["sections"]]

        self.assertEqual(keys, ["stale"])

    def test_generate_briefing_includes_blocked_and_claimed_done_sections(self) -> None:
        blocked = self.repo.create_item(item_type="task", title="Blocked item", actor="test")
        claimed = self.repo.create_item(item_type="task", title="Claimed item", actor="test")
        blocked = self.repo.apply_action(blocked.id, "block", actor="test")
        approved = self.repo.apply_action(claimed.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")

        briefing = generate_briefing(self.db_path, now="2026-05-06T00:00:00Z")
        keys = [section["key"] for section in briefing["sections"]]

        self.assertIn("blocked", keys)
        self.assertIn("claimed_done", keys)
        blocked_section = next(section for section in briefing["sections"] if section["key"] == "blocked")
        claimed_section = next(section for section in briefing["sections"] if section["key"] == "claimed_done")
        self.assertEqual(blocked_section["items"][0]["item_id"], blocked.id)
        self.assertEqual(claimed_section["items"][0]["item_id"], claimed.id)

    def test_generate_briefing_includes_needs_decision_for_live_triage_items(self) -> None:
        triage = self.repo.create_item(item_type="task", title="Decision item", actor="test")

        briefing = generate_briefing(self.db_path, now="2026-05-05T00:00:00Z")

        needs_decision = next(section for section in briefing["sections"] if section["key"] == "needs_decision")
        self.assertEqual(needs_decision["items"][0]["item_id"], triage.id)
        self.assertIsNone(needs_decision["items"][0]["classification"])

    def test_render_briefing_text_is_deterministic_and_contains_ids(self) -> None:
        item = self.repo.create_item(item_type="task", title="Render me", actor="test")
        stale_now = _hours_after(item.created_at, 25)

        briefing = generate_briefing(self.db_path, now=stale_now)
        rendered = render_briefing_text(briefing)

        self.assertIn(f"generated_at={stale_now}", rendered)
        self.assertIn(f"item_id={item.id}", rendered)
        self.assertIn("section[0].key=stale", rendered)


if __name__ == "__main__":
    unittest.main()
