from pathlib import Path


WORKFLOW = Path(".github/workflows/configure-bidspotter-apify-schedule.yml")


def test_configure_bidspotter_apify_schedule_uses_github_secrets_for_apify_env():
    text = WORKFLOW.read_text()

    assert "APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}" in text
    assert "FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}" in text
    assert "APIFY_WEBHOOK_SECRET: ${{ secrets.APIFY_WEBHOOK_SECRET }}" in text
    assert "FIRECRAWL_API_KEY" in text
    assert "WEBHOOK_SECRET" in text
    assert '"isSecret": True' in text
    assert 'request("PUT", f"{env_path}/FIRECRAWL_API_KEY", env_payload)' in text
    assert 'request("POST", env_path, env_payload)' in text
    assert 'request("PUT", f"{env_path}/WEBHOOK_SECRET", webhook_env_payload)' in text
    assert 'request("POST", env_path, webhook_env_payload)' in text


def test_configure_bidspotter_apify_schedule_rebuilds_after_secret_env_write():
    text = WORKFLOW.read_text()

    assert "def version_sort_key(version_number):" in text
    assert 'active_version = max(versions, key=lambda version: version_sort_key(version["versionNumber"]))' in text
    assert 'build = request("POST", f"/actors/{ACTOR_ID}/builds?version={ACTIVE_VERSION}&tag=latest&useCache=false&betaPackages=false")' in text
    assert 'wait_for_terminal_build(build["id"])' in text
    assert '"configured_build_id": build.get("id")' in text
    assert '"configured_build_number": build.get("buildNumber")' in text


def test_configure_bidspotter_apify_schedule_creates_native_schedule_without_secret_input():
    text = WORKFLOW.read_text()

    assert 'SCHEDULE_NAME: "ds-bidspotter-12hr-apify-native"' in text
    assert 'DEFAULT_SCHEDULE_CRON: "5 11,23 * * *"' in text
    assert '"actorId": ACTOR_ID' in text
    assert '"firecrawlApiKey"' not in text
    assert '"maxCatalogues": 2' in text
    assert '"maxPages": 1' in text
    assert '"minYear": CURRENT_YEAR - 10' in text
    assert '"maxMileage": 100000' in text
    assert '"minYear": CURRENT_YEAR - 4' not in text
    assert '"maxMileage": 50000' not in text
