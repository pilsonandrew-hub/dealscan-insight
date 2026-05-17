from backend.ingest.db_url import derive_supabase_direct_db_url


def test_derive_supabase_direct_db_url_prefers_explicit_url():
    assert (
        derive_supabase_direct_db_url(
            {
                "SUPABASE_DB_URL": "postgresql://fresh-user:fresh-pass@db.example/postgres?sslmode=require",
                "SUPABASE_DB_PASSWORD": "ignored",
                "SUPABASE_PROJECT_ID": "ignored",
            }
        )
        == "postgresql://fresh-user:fresh-pass@db.example/postgres?sslmode=require"
    )


def test_derive_supabase_direct_db_url_urlencodes_password():
    derived = derive_supabase_direct_db_url(
        {
            "SUPABASE_DB_PASSWORD": "p@ss:w/or d",
            "SUPABASE_PROJECT_ID": "projectref123",
        }
    )

    assert derived == (
        "postgresql://postgres:p%40ss%3Aw%2For%20d"
        "@db.projectref123.supabase.co:5432/postgres?sslmode=require"
    )


def test_derive_supabase_direct_db_url_can_infer_project_ref_from_url():
    derived = derive_supabase_direct_db_url(
        {
            "SUPABASE_DB_PASSWORD": "secret",
            "SUPABASE_URL": "https://abc123xyz.supabase.co",
        }
    )

    assert derived == "postgresql://postgres:secret@db.abc123xyz.supabase.co:5432/postgres?sslmode=require"


def test_derive_supabase_direct_db_url_requires_password_for_derived_url():
    assert derive_supabase_direct_db_url({"SUPABASE_PROJECT_ID": "projectref123"}) is None


def test_derive_supabase_direct_db_url_requires_project_ref_for_derived_url():
    assert derive_supabase_direct_db_url({"SUPABASE_DB_PASSWORD": "secret"}) is None
