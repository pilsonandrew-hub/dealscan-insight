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


if __name__ == "__main__":
    unittest.main()
