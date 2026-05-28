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


def _run_audit(*, table_row, policy_rows):
    cursor = _mock_cursor(table_row=table_row, policy_rows=policy_rows)
    conn = MagicMock()
    conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
    with patch("psycopg2.connect", return_value=conn), patch(
        "psycopg2.extras.RealDictCursor", return_value=MagicMock()
    ):
        return audit_mod.audit_from_dsn("postgresql://example")


def _protected_table_row(*, rls_enabled: bool = True):
    return {
        "schema_name": "public",
        "table_name": "opportunities",
        "rls_enabled": rls_enabled,
        "force_rls_enabled": False,
    }


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
    report = _run_audit(
        table_row=_protected_table_row(rls_enabled=False),
        policy_rows=[
            {
                "policy_name": "opportunities_authenticated_read",
                "permissive": True,
                "command": "r",
                "using_expression": "true",
                "with_check_expression": None,
                "roles": ["authenticated"],
            }
        ],
    )
    assert report["status"] == "FAIL"
    assert report["table"]["rls_enabled"] is False
    assert any("RLS is disabled" in failure for failure in report["failures"])


def test_audit_fails_on_public_anon_select_policy():
    report = _run_audit(
        table_row=_protected_table_row(),
        policy_rows=[
            {
                "policy_name": "opportunities_anon_read",
                "permissive": True,
                "command": "r",
                "using_expression": "(auth.uid() IS NOT NULL)",
                "with_check_expression": None,
                "roles": ["anon"],
            }
        ],
    )
    assert report["status"] == "FAIL"
    assert any("grants SELECT to ['anon']" in failure for failure in report["failures"])
    assert report["policies"][0]["public_or_anon_read"] is True


def test_audit_fails_on_public_anon_all_policy():
    report = _run_audit(
        table_row=_protected_table_row(),
        policy_rows=[
            {
                "policy_name": "opportunities_public_all",
                "permissive": True,
                "command": "*",
                "using_expression": "(auth.uid() IS NOT NULL)",
                "with_check_expression": None,
                "roles": ["public"],
            }
        ],
    )
    assert report["status"] == "FAIL"
    assert any("grants ALL to ['public']" in failure for failure in report["failures"])


def test_audit_fails_on_permissive_using_true_public_anon_read():
    report = _run_audit(
        table_row=_protected_table_row(),
        policy_rows=[
            {
                "policy_name": "opportunities_public_read",
                "permissive": True,
                "command": "r",
                "using_expression": "true",
                "with_check_expression": None,
                "roles": ["public"],
            }
        ],
    )
    assert report["status"] == "FAIL"
    assert any("permissive USING (true) for public/anon read" in failure for failure in report["failures"])
    assert report["policies"][0]["permissive_true_public_read"] is True


def test_audit_passes_with_authenticated_only_policy():
    report = _run_audit(
        table_row=_protected_table_row(),
        policy_rows=[
            {
                "policy_name": "opportunities_authenticated_read",
                "permissive": True,
                "command": "r",
                "using_expression": "true",
                "with_check_expression": None,
                "roles": ["authenticated"],
            },
            {
                "policy_name": "opportunities_service_role_all",
                "permissive": True,
                "command": "*",
                "using_expression": "true",
                "with_check_expression": "true",
                "roles": ["service_role"],
            },
        ],
    )
    assert report["status"] == "PASS"
    assert report["table"]["rls_enabled"] is True
    assert report["policy_count"] == 2
    assert report["failures"] == []
    assert all(not p["public_or_anon_read"] for p in report["policies"])
