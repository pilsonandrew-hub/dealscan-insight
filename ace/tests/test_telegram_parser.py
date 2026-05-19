from __future__ import annotations

import unittest

from ace.telegram_parser import parse_telegram_message


class TelegramParserTests(unittest.TestCase):
    def test_actionable_direct_request(self) -> None:
        result = parse_telegram_message(
            "Can you check the ACE autonomy lane today?",
            chat_id="7529788084",
            message_id="msg-100",
            received_at="2026-05-08T16:50:00Z",
        )

        self.assertTrue(result.actionable)
        self.assertEqual(result.classification, "direct_work")
        self.assertEqual(result.parser_rule, "bounded_direct_work_rule")
        self.assertIn("can you", result.parser_reason)
        self.assertEqual(result.source_chat_id, "7529788084")
        self.assertEqual(result.source_message_id, "msg-100")
        self.assertFalse(result.autonomy_eligible)
        self.assertIn("requires governed execution evidence", result.autonomy_policy_reason or "")

    def test_actionable_audit_command_without_polite_marker(self) -> None:
        result = parse_telegram_message(
            "Audit the ACE scheduler collision path.",
            chat_id="7529788084",
            message_id="msg-104",
            received_at="2026-05-08T16:54:00Z",
        )

        self.assertTrue(result.actionable)
        self.assertEqual(result.classification, "direct_work")
        self.assertEqual(result.parser_rule, "bounded_direct_work_rule")
        self.assertIn("audit", result.parser_reason)

    def test_actionable_imperative_without_prefix_marker(self) -> None:
        result = parse_telegram_message(
            "Keep working until the loop control proof is green.",
            chat_id="7529788084",
            message_id="msg-105",
            received_at="2026-05-08T16:55:00Z",
        )

        self.assertTrue(result.actionable)
        self.assertEqual(result.classification, "direct_work")
        self.assertIn("keep working", result.parser_reason)
        self.assertTrue(result.autonomy_eligible)
        self.assertIn("operator-continuation", result.autonomy_policy_reason or "")

    def test_actionable_continue_and_proceed_command(self) -> None:
        result = parse_telegram_message(
            "Continue and proceed",
            chat_id="7529788084",
            message_id="msg-106",
            received_at="2026-05-14T08:30:00Z",
        )

        self.assertTrue(result.actionable)
        self.assertEqual(result.classification, "direct_work")
        self.assertIn("continue", result.parser_reason)
        self.assertTrue(result.autonomy_eligible)

    def test_non_actionable_chatter(self) -> None:
        result = parse_telegram_message(
            "That sunset was incredible tonight.",
            chat_id="7529788084",
            message_id="msg-101",
            received_at="2026-05-08T16:51:00Z",
        )

        self.assertFalse(result.actionable)
        self.assertEqual(result.classification, "ignore")
        self.assertEqual(result.parser_rule, "no_direct_work_rule_matched")

    def test_empty_message(self) -> None:
        result = parse_telegram_message(
            "   \n\t  ",
            chat_id="7529788084",
            message_id="msg-102",
            received_at="2026-05-08T16:52:00Z",
        )

        self.assertFalse(result.actionable)
        self.assertEqual(result.classification, "ignore")
        self.assertEqual(result.parser_rule, "empty_text")

    def test_deterministic_repeatability(self) -> None:
        first = parse_telegram_message(
            "Please follow up on the parser-created intake proof.",
            chat_id="7529788084",
            message_id="msg-103",
            received_at="2026-05-08T16:53:00Z",
        )
        second = parse_telegram_message(
            "Please follow up on the parser-created intake proof.",
            chat_id="7529788084",
            message_id="msg-103",
            received_at="2026-05-08T16:53:00Z",
        )

        self.assertEqual(first, second)

    def test_item4_parser_breadth_corpus(self) -> None:
        cases = [
            ("Could you verify the ACE audit chain after the proof?", True, "could you"),
            ("when you can, inspect parser breadth", True, "when you can"),
            ("Rerun the full ACE suite", True, "rerun"),
            ("Test the sleep wake proof runner", True, "test"),
            ("Commit the parser breadth evidence", True, "commit"),
            ("Record the Item 4 proof artifact", True, "record"),
            ("Document the parser decision table", True, "document"),
            ("Send back the clean proof summary", True, "send back"),
            ("Move to Item 4 parser breadth", True, "move to"),
            ("Fix the closeout metadata gap", True, "fix"),
            ("Please harden direct work intake", True, "please"),
            ("Make sure the cycle is green", True, "make sure"),
            ("Beautiful work on Item 3", False, "no_direct_work_rule_matched"),
            ("Thanks, that looks right", False, "no_direct_work_rule_matched"),
            ("lol that was brutal", False, "no_direct_work_rule_matched"),
            ("Good morning", False, "no_direct_work_rule_matched"),
            ("Nice", False, "no_direct_work_rule_matched"),
            ("The proof passed", False, "no_direct_work_rule_matched"),
            ("Parser breadth matters", False, "no_direct_work_rule_matched"),
            ("Item 4 is next", False, "no_direct_work_rule_matched"),
        ]

        for index, (text, expected_actionable, expected_reason_fragment) in enumerate(cases, start=1):
            with self.subTest(index=index, text=text):
                result = parse_telegram_message(
                    text,
                    chat_id="7529788084",
                    message_id=f"item4-{index}",
                    received_at="2026-05-15T06:00:00Z",
                )

                self.assertEqual(result.actionable, expected_actionable)
                if expected_actionable:
                    self.assertEqual(result.classification, "direct_work")
                    self.assertEqual(result.parser_rule, "bounded_direct_work_rule")
                    self.assertIn(expected_reason_fragment, result.parser_reason)
                else:
                    self.assertEqual(result.classification, "ignore")
                    self.assertEqual(result.parser_rule, expected_reason_fragment)


if __name__ == "__main__":
    unittest.main()
