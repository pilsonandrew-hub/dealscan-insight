from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "estatesale-lead-watch.yml"


class EstateSaleLeadWatchWorkflowTests(unittest.TestCase):
    def test_estatesale_lead_watch_routes_to_dealerscope_alerts_channel(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("EstateSale Lead Watch", text)
        self.assertIn("15 */12 * * *", text)
        self.assertIn("TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}", text)
        self.assertIn('CHAT_ID: "-1003672399222"', text)
        self.assertIn("python3 scripts/estatesale_lead_alert.py", text)


if __name__ == "__main__":
    unittest.main()
