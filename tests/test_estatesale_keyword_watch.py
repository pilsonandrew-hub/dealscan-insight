from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import estatesale_keyword_watch as watcher


class EstateSaleKeywordWatchTests(unittest.TestCase):
    def test_extracts_vehicle_candidate_from_sale_card_context(self) -> None:
        html = """
        <html><body>
          <div class="sale">
            <a href="/sales/view/123/Fine-Orange-Estate-Sale.html">Fine Orange Estate Sale</a>
            <p>Includes a 2017 Honda CR-V with VIN available, tools, and shop equipment.</p>
          </div>
          <div class="sale">
            <a href="/sales/view/456/Furniture-and-China.html">Furniture and China</a>
            <p>Dining table, lamps, rugs, and collectibles only.</p>
          </div>
        </body></html>
        """

        report = watcher.analyze_html(
            html,
            source_url="https://www.estatesale.com/cities/view/384/Estate-Sales-Orange-CA.html",
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["candidate_count"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["url"], "https://www.estatesale.com/sales/view/123/Fine-Orange-Estate-Sale.html")
        self.assertEqual(candidate["matched_keywords"], ["Honda", "VIN", "equipment", "tools"])
        self.assertEqual(candidate["priority"], "review")
        self.assertIn("2017 Honda CR-V", candidate["snippet"])

    def test_household_only_sales_are_not_candidates(self) -> None:
        html = """
        <html><body>
          <a href="/sales/view/456/Furniture-and-China.html">Furniture and China</a>
          <p>Dining table, lamps, rugs, jewelry, and collectibles only.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["candidates"], [])

    def test_incapsula_challenge_reports_blocked_not_empty(self) -> None:
        html = """
        <html>
          <head>
            <META NAME="robots" CONTENT="noindex,nofollow">
            <script src="/_Incapsula_Resource?SWJIYLWA=challenge"></script>
          </head>
          <body></body>
        </html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/")

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blocked_reason"], "imperva_incapsula_challenge")
        self.assertEqual(report["candidate_count"], 0)

    def test_incapsula_script_on_real_sale_page_is_not_blocked(self) -> None:
        html = """
        <html>
          <head><script src="/_Incapsula_Resource?SWJIYLWA=script"></script></head>
          <body>
            <h1>Gary's Public Auction 97</h1>
            <p>Listing ID#: 871215</p>
            <p>Sale Location 5131 E Drexel RD Tucson, AZ 85706</p>
            <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
            <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
              2021 Ford Escape Automatic
            </a>
            <p>VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape Miles: 76165</p>
          </body>
        </html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/871215.html")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["vehicle_lot_count"], 1)

    def test_cli_reads_html_file_and_prints_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            fixture = Path(tmpdir) / "estate.html"
            fixture.write_text(
                """
                <a href="https://www.estatesale.com/sales/view/789/Shop-Sale.html">Shop Sale</a>
                <p>Pickup truck parts, motorcycle gear, and Toyota manuals.</p>
                """,
                encoding="utf-8",
            )

            exit_code, output_text = watcher.run_cli(
                ["--html-file", str(fixture), "--source-url", "https://www.estatesale.com/"]
            )

        self.assertEqual(exit_code, 0)
        output = json.loads(output_text)
        self.assertEqual(output["candidate_count"], 1)
        self.assertEqual(output["candidates"][0]["priority"], "review")
        self.assertEqual(output["candidates"][0]["matched_keywords"], ["Toyota", "motorcycle", "pickup", "truck"])

    def test_extracts_vehicle_lots_from_estatesale_catalog_page(self) -> None:
        html = """
        <html><body>
          <h1>Gary's Public Auction 97</h1>
          <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
          <p>1</p>
          <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
            2021 Ford Escape Automatic
          </a>
          <p>White VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape
          Engine: 6 Cylinder Miles: 76165 Keys: YES Runs: Yes with battery boost
          Title Status: Regular Odometer Status: Unknown</p>
          <p>2</p>
          <a href="https://garystowingarizona.hibid.com/lot/248849231/2011-hyundai-santa-fe-automatic">
            2011 Hyundai Santa fe Automatic
          </a>
          <p>White VIN: 5XYZG3AB8BG067463 Year: 2011 Make: Hyundai Model: Santa fe
          Engine: 6 Cylinder Miles: 118654 Keys: YES Runs: Yes with battery boost
          Title Status: Regular Odometer Status: Unknown notes: Title shows 1 not actual mileage</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/871215.html")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["vehicle_lot_count"], 2)
        first_lot = report["vehicle_lots"][0]
        self.assertEqual(first_lot["lot_url"], "https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic")
        self.assertEqual(first_lot["title"], "2021 Ford Escape Automatic")
        self.assertEqual(first_lot["vin"], "1FMCU9G62MUA91928")
        self.assertEqual(first_lot["year"], 2021)
        self.assertEqual(first_lot["make"], "Ford")
        self.assertEqual(first_lot["model"], "Escape")
        self.assertEqual(first_lot["miles"], 76165)
        self.assertEqual(first_lot["title_status"], "Regular")
        self.assertEqual(first_lot["runs"], "Yes with battery boost")

    def test_extracts_apple_towing_hibid_vehicle_lot_shape(self) -> None:
        html = """
        <html><body>
          <h1>Apple Towing (CA Locations) online auction 6/9/2026</h1>
          <a href="https://appletowing.hibid.com/catalog/647193">VIEW ONLINE CATALOG</a>
          <p>501</p>
          <a href="https://appletowing.hibid.com/lot/249384315/ca-2007-nissan-armada">
            (CA) 2007 Nissan Armada
          </a>
          <p>Location: Apple Towing Co. (Otay Mesa) - 7210 Otay Mesa Rd,
          San Diego, CA 92154. VIN #: 5N1BA08A07N724413 Odometer reads: 222,598
          Keys?: Yes. Started?: Yes, with battery boost. Notice: As-Is.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/872546.html")

        self.assertEqual(report["vehicle_lot_count"], 1)
        lot = report["vehicle_lots"][0]
        self.assertEqual(lot["lot_url"], "https://appletowing.hibid.com/lot/249384315/ca-2007-nissan-armada")
        self.assertEqual(lot["title"], "(CA) 2007 Nissan Armada")
        self.assertEqual(lot["vin"], "5N1BA08A07N724413")
        self.assertEqual(lot["year"], 2007)
        self.assertEqual(lot["make"], "Nissan")
        self.assertEqual(lot["miles"], 222598)
        self.assertEqual(lot["keys"], "Yes.")
        self.assertEqual(lot["runs"], "Yes, with battery boost.")

    def test_classifies_downstream_catalog_handoff(self) -> None:
        govdeals_html = """
        <html><body>
          <h1>2017 Toyota RAV4 Hybrid</h1>
          <a href="https://www.govdeals.com/en/asset/2113/28146">VIEW ONLINE CATALOG</a>
          <p>Online Auction for Government Surplus. 2017 Toyota RAV4 Hybrid. Runs and Drives. Keys: Yes.</p>
        </body></html>
        """
        hibid_html = """
        <html><body>
          <h1>Gary's Public Auction 97</h1>
          <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
          <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
            2021 Ford Escape Automatic
          </a>
          <p>VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape Miles: 76165</p>
        </body></html>
        """

        govdeals_report = watcher.analyze_html(govdeals_html, source_url="https://www.estatesale.com/sales/view/873593")
        hibid_report = watcher.analyze_html(hibid_html, source_url="https://www.estatesale.com/sales/view/871215")

        self.assertEqual(govdeals_report["estatesale_role"], "downstream_catalog_signpost")
        self.assertEqual(govdeals_report["recommended_handoff"], "dealer_scope_govdeals_pipeline")
        self.assertEqual(govdeals_report["downstream_catalog_links"][0]["source"], "govdeals")

        self.assertEqual(hibid_report["estatesale_role"], "structured_vehicle_lot_signpost")
        self.assertEqual(hibid_report["recommended_handoff"], "downstream_hibid_or_catalog_review")
        self.assertEqual(hibid_report["downstream_catalog_links"][0]["source"], "hibid")

    def test_builds_dealerscope_review_payload(self) -> None:
        html = """
        <html><body>
          <h1>Gary's Public Auction 97</h1>
          <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
          <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
            2021 Ford Escape Automatic
          </a>
          <p>VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape Miles: 76165</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/871215.html")

        self.assertEqual(report["review_payload"]["destination"], "dealerscope_alerts")
        self.assertEqual(report["review_payload"]["lead_source"], "estatesale")
        self.assertEqual(report["review_payload"]["recommended_handoff"], "downstream_hibid_or_catalog_review")
        self.assertEqual(report["review_payload"]["vehicle_lot_count"], 1)
        self.assertIn("EstateSale lead", report["review_payload"]["summary"])
        self.assertIn("not scored", report["review_payload"]["truth_note"])

    def test_aggregate_mixed_sources_route_to_mixed_review(self) -> None:
        govdeals_report = watcher.analyze_html(
            """
            <a href="https://www.govdeals.com/en/asset/2113/28146">VIEW ONLINE CATALOG</a>
            <p>2017 Toyota RAV4 Hybrid vehicle auction.</p>
            """,
            source_url="https://www.estatesale.com/sales/view/873593",
        )
        hibid_report = watcher.analyze_html(
            """
            <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
            <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
              2021 Ford Escape Automatic
            </a>
            <p>VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape Miles: 76165</p>
            """,
            source_url="https://www.estatesale.com/sales/view/871215",
        )

        catalog_links = govdeals_report["downstream_catalog_links"] + hibid_report["downstream_catalog_links"]
        lots = govdeals_report["vehicle_lots"] + hibid_report["vehicle_lots"]
        candidates = govdeals_report["candidates"] + hibid_report["candidates"]

        self.assertEqual(watcher._recommended_handoff(catalog_links, lots, candidates), "mixed_downstream_review")

    def test_strips_downstream_catalog_urls_before_alert_handoff(self) -> None:
        html = """
        <html><body>
          <a href="http://www.govdeals.com ">www.govdeals.com</a>
          <p>2017 Toyota RAV4 Hybrid vehicle auction.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/873593")

        self.assertEqual(report["downstream_catalog_links"][0]["url"], "http://www.govdeals.com")

    def test_ignores_navigation_links_as_candidates(self) -> None:
        html = """
        <html><body>
          <a href="/account/signup">email notifications</a>
          <p>Estate sale updates with trucks and tools delivered to your inbox.</p>
          <a href="/company/add">Add Your Company</a>
          <p>Advertise vehicle auctions and tools.</p>
          <a href="/sales/view/123/Vehicle-Sale.html">Vehicle Sale</a>
          <p>Includes a Honda motorcycle and shop tools.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/")

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["title"], "Vehicle Sale")

    def test_ignores_non_navigable_links_as_candidates(self) -> None:
        html = """
        <html><body>
          <a href="javascript:void(0);">javascript:void(0);</a>
          <p>2015 Toyota Tacoma, tools, and four wheelers shown in photos.</p>
          <a href="/sales/view/858964.html">Estate Auction</a>
          <p>2015 Toyota Tacoma, Kioti tractor, Yamaha Grizzly, Honda dirt bike, and tools.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/858964.html")

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["title"], "Estate Auction")

    def test_page_level_vehicle_text_creates_review_lead(self) -> None:
        html = """
        <html><body>
          <h1>Estate Sale with Shop Equipment</h1>
          <p>Photos show a 2015 Toyota Tacoma, Kioti tractor, Yamaha Grizzly,
          Honda dirt bike, four wheelers, and tools.</p>
        </body></html>
        """

        report = watcher.analyze_html(html, source_url="https://www.estatesale.com/sales/view/858964.html")

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["url"], "https://www.estatesale.com/sales/view/858964.html")
        self.assertEqual(report["candidates"][0]["title"], "EstateSale page lead")
        self.assertEqual(report["recommended_handoff"], "lead_review_alert")

    def test_cli_browser_mode_uses_browser_fetcher(self) -> None:
        html = """
        <html><body>
          <a href="https://garystowingarizona.hibid.com/catalog/646639">VIEW ONLINE CATALOG</a>
          <a href="https://garystowingarizona.hibid.com/lot/248849230/2021-ford-escape-automatic">
            2021 Ford Escape Automatic
          </a>
          <p>VIN: 1FMCU9G62MUA91928 Year: 2021 Make: Ford Model: Escape Miles: 76165</p>
        </body></html>
        """

        with patch.object(watcher, "fetch_html_browser", return_value=html) as fetcher:
            exit_code, output_text = watcher.run_cli(
                ["--url", "https://www.estatesale.com/sales/view/871215.html", "--browser"]
            )

        self.assertEqual(exit_code, 0)
        fetcher.assert_called_once()
        output = json.loads(output_text)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["vehicle_lot_count"], 1)
        self.assertEqual(output["recommended_handoff"], "downstream_hibid_or_catalog_review")


if __name__ == "__main__":
    unittest.main()
