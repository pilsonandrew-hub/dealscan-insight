from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import estatesale_lead_alert


class EstateSaleLeadAlertTests(unittest.TestCase):
    def test_formats_review_payload_for_telegram(self) -> None:
        report = {
            "status": "ok",
            "review_payload": {
                "summary": "EstateSale lead: role=structured_vehicle_lot_signpost",
                "estatesale_role": "structured_vehicle_lot_signpost",
                "recommended_handoff": "downstream_hibid_or_catalog_review",
                "vehicle_lot_count": 1,
                "candidate_count": 1,
                "truth_note": "Review lead only; not scored and not saved as a DealerScope opportunity yet.",
                "downstream_catalog_links": [
                    {
                        "source": "hibid",
                        "title": "VIEW ONLINE CATALOG",
                        "url": "https://garystowingarizona.hibid.com/catalog/646639",
                    }
                ],
                "sample_vehicle_lots": [
                    {
                        "title": "2021 Ford Escape Automatic",
                        "vin": "1FMCU9G62MUA91928",
                        "miles": 76165,
                        "lot_url": "https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic",
                    }
                ],
                "sample_candidates": [],
            },
        }

        message = estatesale_lead_alert.format_telegram_message(report)

        self.assertIn("EstateSale Lead Radar", message)
        self.assertIn("downstream_hibid_or_catalog_review", message)
        self.assertIn("2021 Ford Escape Automatic", message)
        self.assertIn("1FMCU9G62MUA91928", message)
        self.assertIn("Review lead only", message)

    def test_dry_run_does_not_send_telegram(self) -> None:
        report = {
            "status": "ok",
            "vehicle_lot_count": 0,
            "candidate_count": 0,
            "downstream_catalog_links": [],
            "review_payload": {
                "summary": "EstateSale lead: role=no_vehicle_signal",
                "estatesale_role": "no_vehicle_signal",
                "recommended_handoff": "ignore",
                "vehicle_lot_count": 0,
                "candidate_count": 0,
                "truth_note": "Review lead only; not scored.",
                "downstream_catalog_links": [],
                "sample_vehicle_lots": [],
                "sample_candidates": [],
            },
        }

        with (
            patch("scripts.estatesale_lead_alert.watcher.build_report", return_value=report),
            patch("scripts.estatesale_lead_alert.send_telegram") as send_telegram,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = estatesale_lead_alert.main(["--url", "https://www.estatesale.com/", "--dry-run"])

        self.assertEqual(exit_code, 0)
        send_telegram.assert_not_called()
        self.assertIn("EstateSale Lead Radar", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
