from backend.ingest.supabase_config import resolve_supabase_ingest_config


def test_resolve_supabase_ingest_config_prefers_backend_url_and_service_role():
    config = resolve_supabase_ingest_config(
        {
            "SUPABASE_URL": "https://backend.supabase.co",
            "VITE_SUPABASE_URL": "https://vite.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
            "SUPABASE_ANON_KEY": "anon-key",
            "ENVIRONMENT": "production",
        }
    )

    assert config.url == "https://backend.supabase.co"
    assert config.key == "service-key"
    assert config.key_source == "service_role"
    assert config.message is None
    assert config.severity is None


def test_resolve_supabase_ingest_config_allows_anon_key_only_in_development():
    config = resolve_supabase_ingest_config(
        {
            "VITE_SUPABASE_URL": "https://vite.supabase.co",
            "VITE_SUPABASE_ANON_KEY": "vite-anon",
            "ENVIRONMENT": "development",
        }
    )

    assert config.url == "https://vite.supabase.co"
    assert config.key == "vite-anon"
    assert config.key_source == "anon_development_fallback"
    assert config.severity == "warning"
    assert "falling back to anon key" in config.message


def test_resolve_supabase_ingest_config_blocks_anon_key_in_production():
    config = resolve_supabase_ingest_config(
        {
            "SUPABASE_URL": "https://backend.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
            "ENVIRONMENT": "production",
        }
    )

    assert config.key is None
    assert config.key_source is None
    assert config.severity == "critical"
    assert "required" in config.message


def test_resolve_supabase_ingest_config_reports_missing_keys_by_environment():
    dev = resolve_supabase_ingest_config({"ENVIRONMENT": "development"})
    prod = resolve_supabase_ingest_config({"ENVIRONMENT": "production"})

    assert dev.key is None
    assert dev.severity == "warning"
    assert "no anon key" in dev.message
    assert prod.key is None
    assert prod.severity == "critical"
    assert prod.message == "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations."
