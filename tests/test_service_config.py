from backend.ingest.service_config import (
    DEFAULT_APP_PUBLIC_URL,
    resolve_apify_api_token,
    resolve_app_public_url,
    resolve_rover_actions_base_url,
)


def test_resolve_apify_api_token_prefers_primary_and_supports_legacy_alias():
    assert resolve_apify_api_token({"APIFY_TOKEN": " primary ", "APIFY_API_TOKEN": "alias"}) == "primary"
    assert resolve_apify_api_token({"APIFY_TOKEN": "", "APIFY_API_TOKEN": " alias "}) == "alias"
    assert resolve_apify_api_token({}) == ""


def test_resolve_app_public_url_uses_default_when_missing():
    assert resolve_app_public_url({}) == DEFAULT_APP_PUBLIC_URL
    assert resolve_app_public_url({"APP_PUBLIC_URL": " https://example.test "}) == "https://example.test"


def test_resolve_rover_actions_base_url_precedence_and_trailing_slash():
    env = {
        "ROVER_API_BASE_URL": "https://rover.example.test/",
        "VITE_API_URL": "https://vite.example.test/",
        "APP_PUBLIC_URL": "https://app.example.test/",
    }
    assert resolve_rover_actions_base_url(env) == "https://rover.example.test"
    assert resolve_rover_actions_base_url({"VITE_API_URL": "https://vite.example.test/"}) == "https://vite.example.test"
    assert (
        resolve_rover_actions_base_url({}, app_public_url="https://app.example.test/")
        == "https://app.example.test"
    )
    assert resolve_rover_actions_base_url({}) == DEFAULT_APP_PUBLIC_URL
