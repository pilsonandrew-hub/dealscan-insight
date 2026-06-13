import pytest

from scripts import run_competitor_sales_scraper as runner


def test_runner_returns_failure_when_selected_source_errors(monkeypatch):
    async def failing_scraper(max_pages=10):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(runner, "SCRAPERS", {"govdeals": failing_scraper})
    monkeypatch.setenv("COMPETITOR_SCRAPER_SOURCES", "govdeals")
    monkeypatch.setenv("COMPETITOR_SCRAPER_DRY_RUN", "true")

    assert runner.main() == 1


def test_runner_returns_failure_when_non_dry_run_has_no_db_writes(monkeypatch):
    async def successful_scraper(max_pages=10):
        return [{"source": "govdeals", "sale_price": 20000, "listing_url": "https://example.com/1"}]

    monkeypatch.setattr(runner, "SCRAPERS", {"govdeals": successful_scraper})
    monkeypatch.setattr(runner, "_make_client", lambda: None)
    monkeypatch.setenv("COMPETITOR_SCRAPER_SOURCES", "govdeals")
    monkeypatch.setenv("COMPETITOR_SCRAPER_DRY_RUN", "false")

    assert runner.main() == 1


def test_runner_returns_failure_when_non_dry_run_scrapes_zero_rows(monkeypatch):
    async def empty_scraper(max_pages=10):
        return []

    monkeypatch.setattr(runner, "SCRAPERS", {"govdeals": empty_scraper})
    monkeypatch.setattr(runner, "_make_client", lambda: object())
    monkeypatch.setenv("COMPETITOR_SCRAPER_SOURCES", "govdeals")
    monkeypatch.setenv("COMPETITOR_SCRAPER_DRY_RUN", "false")

    assert runner.main() == 1


def test_runner_returns_success_for_dry_run_scrape_without_db(monkeypatch):
    async def successful_scraper(max_pages=10):
        return [{"source": "govdeals", "sale_price": 20000, "listing_url": "https://example.com/1"}]

    monkeypatch.setattr(runner, "SCRAPERS", {"govdeals": successful_scraper})
    monkeypatch.setenv("COMPETITOR_SCRAPER_SOURCES", "govdeals")
    monkeypatch.setenv("COMPETITOR_SCRAPER_DRY_RUN", "true")

    assert runner.main() == 0
