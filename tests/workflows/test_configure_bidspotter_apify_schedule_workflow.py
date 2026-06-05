from pathlib import Path


WORKFLOW = Path(".github/workflows/configure-bidspotter-apify-schedule.yml")


def test_configure_bidspotter_apify_schedule_uses_github_secrets_for_apify_env():
    text = WORKFLOW.read_text()

    assert "APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}" in text
    assert "FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}" in text
    assert "FIRECRAWL_API_KEY" in text
    assert '"isSecret": True' in text
    assert 'request("PUT", f"{env_path}/FIRECRAWL_API_KEY", env_payload)' in text
    assert 'request("POST", env_path, env_payload)' in text


def test_configure_bidspotter_apify_schedule_creates_native_schedule_without_secret_input():
    text = WORKFLOW.read_text()

    assert 'SCHEDULE_NAME: "ds-bidspotter-12hr-apify-native"' in text
    assert 'DEFAULT_SCHEDULE_CRON: "45 10,22 * * *"' in text
    assert '"actorId": ACTOR_ID' in text
    assert '"firecrawlApiKey"' not in text
    assert '"maxCatalogues": 2' in text
    assert '"maxPages": 1' in text
    assert '"minYear": CURRENT_YEAR - 4' in text
    assert '"maxMileage": 50000' in text
