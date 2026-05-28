import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import audit_supabase_rls as audit_mod

ROOT = Path(__file__).resolve().parents[1]


def _mock_cursor(*, table_row, policy_rows):
    cursor = MagicMock()

    def execute(query, *_args, **_kwargs):
        if "relrowsecurity" in query:
            cursor.fetchone.return_value = table_row
        else:
            cursor.fetchall.return_value = policy_rows

    cursor.execute.side_effect = execute
    return cursor


def test_missing_db_url_fails_with_json():
    env = {"PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        [sys.executable, "scripts/audit_supabase_rls.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["status"] == "FAIL"
    assert report["failures"]


def test_audit_fails_when_rls_disabled():
    table_row = {
        "schema_name": "public",
        "table_name": "opportunities",
        "rls_enabled": False,
        "force_rls_enabled": False,
    }
    policy_rows = [
        {
            "policy_name": "opportunities_read_policy",
            "permissive": True,
            "command": "r",
            "using_expression": "true",
            "with_check_expression": None,
            "roles": ["public"],
        }
    ]
    cursor = _mock_cursor(table_row=table_row, policy_rows=policy_rows)
    conn = MagicMock()
    conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor

    with patch("psycopg2.connect", return_value=conn), patch(
        "psycopg2.extras.RealDictCursor", return_value=MagicMock()
    ):
        report = audit_mod.audit_from_dsn("postgresql://example")

    assert report["status"] == "FAIL"
    assert report["table"]["rls_enabled"] is False
    assert any("RLS is disabled" in failure for failure in report["failures"])


def test_audit_passes_with_authenticated_only_policy():
    table_row = {
        "schema_name": "public",
        "table_name": "opportunities",
        "rls_enabled": True,
        "force_rls_enabled": False,
    }
    policy_rows = [
        {
            "policy_name": "opportunities_authenticated_read",
            "permissive": True,
            "command": "r",
            "using_expression": "true",
            "with_check_expression": None,
            "roles": ["authenticated"],
        }
    ]
    cursor = _mock_cursor(table_row=table_row, policy_rows=policy_rows)
    conn = MagicMock()
    conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor

    with patch("psycopg2.connect", return_value=conn), patch(
        "psycopg2.extras.RealDictCursor", return_value=MagicMock()
    ):
        report = audit_mod.audit_from_dsn("postgresql://example")

    assert report["status"] == "PASS"
    assert report["table"]["rls_enabled"] is True
    assert report["policy_count"] == 1
