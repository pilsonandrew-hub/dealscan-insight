import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ingest import scrape_all


class LegacyScrapeAllGuardTests(unittest.TestCase):
    def test_legacy_local_scraper_fails_closed_without_explicit_opt_in(self):
        with patch.dict(os.environ, {scrape_all.ALLOW_LEGACY_LOCAL_SCRAPER_ENV: ""}, clear=False):
            with self.assertRaises(RuntimeError) as context:
                scrape_all.require_legacy_local_scraper_enabled()

        self.assertIn("legacy local CSV/offline scraper path", str(context.exception))
        self.assertIn("/api/ingest/apify", str(context.exception))

    def test_legacy_local_scraper_allows_explicit_local_diagnostics(self):
        with patch.dict(os.environ, {scrape_all.ALLOW_LEGACY_LOCAL_SCRAPER_ENV: "1"}, clear=False):
            scrape_all.require_legacy_local_scraper_enabled()


if __name__ == "__main__":
    unittest.main()
