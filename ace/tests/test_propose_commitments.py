from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ace.commitment_parser import parse_commitment_message
from ace.propose_commitments import (
    PROPOSAL_SOURCE,
    accept_commitment_proposal,
    append_proposal_decision,
    reject_commitment_proposal,
    scan_commitment_proposals,
)
from ace.repository import ItemRepository
from ace.storage import bootstrap_db


class FakeSessionMessages:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self._messages = messages

    def __call__(self) -> list[dict[str, object]]:
        return list(self._messages)


class ProposeCommitmentsTests(unittest.TestCase):
    def test_commitment_parser_matches_bounded_phrases(self) -> None:
        matched = parse_commitment_message("I will send the weekly digest tonight.")
        self.assertTrue(matched.actionable)
        self.assertEqual(matched.parser_rule, "commitment_i_will")
        self.assertEqual(matched.matched_phrase, "i will")

        ignored = parse_commitment_message("Please check the deployment status.")
        self.assertFalse(ignored.actionable)

    def test_scan_creates_triage_proposal_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            messages = [
                {
                    "chat_id": "12345",
                    "message_id": "99",
                    "received_at": "2026-05-26T12:00:00Z",
                    "text": "I need to review the loose-ends output before Monday.",
                }
            ]
            rows = scan_commitment_proposals(
                db_path,
                message_loader=FakeSessionMessages(messages),
            )
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].created)
            repo = ItemRepository(db_path)
            item = repo.get_item(rows[0].item_id)
            self.assertEqual(item.state, "TRIAGE")
            self.assertEqual(item.source, PROPOSAL_SOURCE)

            rows_again = scan_commitment_proposals(
                db_path,
                message_loader=FakeSessionMessages(messages),
            )
            self.assertEqual(len(rows_again), 1)
            self.assertFalse(rows_again[0].created)

    def test_accept_and_reject_log_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            log_path = Path(tmpdir) / "decisions.jsonl"
            bootstrap_db(db_path)
            rows = scan_commitment_proposals(
                db_path,
                message_loader=FakeSessionMessages(
                    [
                        {
                            "chat_id": "1",
                            "message_id": "2",
                            "received_at": "2026-05-26T12:00:00Z",
                            "text": "Remember to tighten the stale filter thresholds.",
                        }
                    ]
                ),
            )
            item_id = rows[0].item_id

            accept_result = accept_commitment_proposal(
                db_path,
                item_id,
                actor="operator-test",
            )
            self.assertEqual(accept_result["decision"], "accept")
            self.assertEqual(accept_result["state"], "APPROVED")

            rows_reject = scan_commitment_proposals(
                db_path,
                message_loader=FakeSessionMessages(
                    [
                        {
                            "chat_id": "1",
                            "message_id": "3",
                            "received_at": "2026-05-26T13:00:00Z",
                            "text": "Let me harden the propose parser next.",
                        }
                    ]
                ),
            )
            reject_id = rows_reject[0].item_id
            reject_result = reject_commitment_proposal(
                db_path,
                reject_id,
                actor="operator-test",
            )
            self.assertEqual(reject_result["decision"], "reject")
            self.assertEqual(reject_result["state"], "DROPPED")

            append_proposal_decision(
                decision="accept",
                item_id="item_test",
                parser_rule="commitment_i_will",
                matched_phrase="i will",
                source_session="telegram:1:9",
                actor="operator-test",
                log_path=log_path,
            )
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["decision"], "accept")

    def test_accept_rejects_non_proposal_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            item = repo.create_item(
                item_type="work",
                title="ordinary work",
                source="telegram/direct",
                source_session="telegram:9:9",
                actor="test",
            )
            with self.assertRaises(Exception):
                accept_commitment_proposal(db_path, item.id, actor="operator")


if __name__ == "__main__":
    unittest.main()
