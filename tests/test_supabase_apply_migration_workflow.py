from pathlib import Path


WORKFLOW = Path(".github/workflows/supabase-apply-migration.yml")


def test_supabase_apply_migration_workflow_is_manual_and_allowlisted():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "migration_file:" in text
    assert "supabase/migrations/" in text
    assert "../" in text
    assert "exit 2" in text


def test_supabase_apply_migration_workflow_uses_direct_db_secret_without_printing_dsn():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "SUPABASE_DB_PASSWORD" in text
    assert "SUPABASE_PROJECT_ID" in text
    assert "SUPABASE_URL" in text
    assert "re.search" in text
    assert "SUPABASE_DB_POOLER_HOST" in text
    assert "aws-0-us-west-1.pooler.supabase.com" in text
    assert "postgresql://postgres.{project_id}:" in text
    assert "psql" in text
    assert "echo ${DATABASE_URL}" not in text
    assert "echo \"$DATABASE_URL\"" not in text
