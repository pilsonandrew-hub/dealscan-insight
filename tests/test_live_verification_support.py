import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import live_verification_support as support


class LiveVerificationSupportTests(unittest.TestCase):
    def test_resolve_database_url_prefers_supabase_direct_env_over_database_url(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://stale-user:stale-pass@old.example/postgres",
                "SUPABASE_DB_URL": "postgresql://fresh-user:fresh-pass@db.example/postgres?sslmode=require",
            },
            clear=True,
        ):
            dsn, source = support.resolve_database_url(None)

        self.assertEqual(
            dsn,
            "postgresql://fresh-user:fresh-pass@db.example/postgres?sslmode=require",
        )
        self.assertEqual(source, "env.SUPABASE_DB_URL")

    def test_resolve_database_url_derives_direct_supabase_dsn_from_password_and_project_id(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_DB_PASSWORD": "p@ss:w/or d",
                "SUPABASE_PROJECT_ID": "projectref123",
            },
            clear=True,
        ):
            dsn, source = support.resolve_database_url(None)

        self.assertEqual(
            dsn,
            "postgresql://postgres:p%40ss%3Aw%2For%20d@db.projectref123.supabase.co:5432/postgres?sslmode=require",
        )
        self.assertEqual(source, "env.derived_supabase_direct")

    def test_resolve_database_url_uses_env_file_direct_supabase_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.live"
            env_file.write_text(
                "\n".join(
                    [
                        "DATABASE_URL=postgresql://stale-user:stale-pass@old.example/postgres",
                        "SUPABASE_DB_PASSWORD=file-pass",
                        "SUPABASE_URL=https://projectref999.supabase.co",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                dsn, source = support.resolve_database_url(None, env_file=str(env_file))

        self.assertEqual(
            dsn,
            "postgresql://postgres:file-pass@db.projectref999.supabase.co:5432/postgres?sslmode=require",
        )
        self.assertEqual(source, "env_file.derived_supabase_direct")


if __name__ == "__main__":
    unittest.main()
