from pathlib import Path


WORKFLOW = Path(".github/workflows/supabase-apply-migration.yml")


def test_supabase_apply_migration_workflow_is_manual_and_allowlisted():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "migration_file:" in text
    assert "supabase/migrations/" in text
    assert "Path(MIGRATION_FILE)" in text
    assert "relative_to(allowed_root)" in text
    assert "exit 2" in text


def test_supabase_apply_migration_workflow_uses_direct_db_secret_without_printing_dsn():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "SUPABASE_DB_PASSWORD" in text
    assert "SUPABASE_PROJECT_ID" in text
    assert "SUPABASE_URL" in text
    assert "re.search" in text
    assert "SUPABASE_DB_POOLER_HOST" in text
    assert "aws-0-us-west-2.pooler.supabase.com" in text
    assert 'or "5432"' in text
    assert "PROJECT_REF_RE" in text
    assert "POOLER_HOST_RE" in text
    assert "PORT_RE" in text
    assert 'PORT_RE = re.compile(r"^[0-9]{1,5}$")' in text
    assert "PGPASSWORD" in text
    assert "postgresql://postgres" not in text
    assert "sslmode=require" in text
    assert "echo ${DATABASE_URL}" not in text
    assert "echo \"$DATABASE_URL\"" not in text
    assert "psql \"${PSQL_CONN}\"" in text


def test_supabase_apply_migration_workflow_can_fall_back_to_metadata_pooler():
    text = WORKFLOW.read_text(encoding="utf-8")

    missing_secret_gate = next(
        line for line in text.splitlines() if "Missing Supabase DB secret inputs." in line
    )
    preceding_if = text.split(missing_secret_gate, 1)[0].splitlines()[-1]
    assert "SUPABASE_DB_POOLER_HOST" not in preceding_if
    assert "aws-0-us-west-2.pooler.supabase.com" in text
    assert "conn_source = \"pooler\"" in text
    assert "CONN_SOURCE" in text


def test_supabase_apply_migration_workflow_ignores_stale_database_url_secret():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "DATABASE_URL:" not in text
    assert "database_url = os.environ.get(\"DATABASE_URL\", \"\").strip()" not in text
    assert "user=postgres.{project_id}" in text


def test_supabase_apply_migration_workflow_direct_host_uses_ipv4_hostaddr():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "import socket" in text
    assert "socket.AF_INET" in text
    assert "hostaddr={direct_hostaddr}" in text
    assert "Unable to resolve Supabase direct database IPv4 address." in text
