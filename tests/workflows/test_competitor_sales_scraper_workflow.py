from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "competitor-sales-scraper.yml"


def test_scheduled_competitor_sales_scraper_uses_govdeals_canary():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "SCHEDULED_COMPETITOR_SCRAPER_SOURCES: govdeals" in text
    assert "SCHEDULED_COMPETITOR_SCRAPER_MAX_PAGES: \"1\"" in text
    assert (
        "SCHEDULED_COMPETITOR_GOVDEALS_SEO_ASSET_URLS: "
        "https://prod-seo.govdeals.com/en/asset/17167/7167"
    ) in text
    assert 'if [ "${GITHUB_EVENT_NAME}" = "schedule" ]; then' in text
    assert 'COMPETITOR_SCRAPER_SOURCES="${SCHEDULED_COMPETITOR_SCRAPER_SOURCES}"' in text
    assert (
        'COMPETITOR_GOVDEALS_SEO_ASSET_URLS="${SCHEDULED_COMPETITOR_GOVDEALS_SEO_ASSET_URLS}"'
        in text
    )


def test_manual_competitor_sales_scraper_preserves_source_inputs():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "COMPETITOR_SCRAPER_SOURCES: ${{ inputs.sources }}" in text
    assert "COMPETITOR_SCRAPER_MAX_PAGES: ${{ inputs.max_pages || '10' }}" in text
    assert "COMPETITOR_GOVDEALS_SEO_ASSET_URLS: ${{ inputs.govdeals_seo_asset_urls || '' }}" in text
