#!/usr/bin/env python3
"""Read-only live RLS audit for the DealerScope opportunities table.

This audit proves table-level RLS state directly from pg_class/pg_namespace and
then inspects every policy attached to public.opportunities. It fails closed for
public/anon reads and permissive public USING (true) policies.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

PUBLIC_ROLES = {"public", "anon"}
READ_COMMANDS = {"r", "*"}  # SELECT, ALL in pg_policy.polcmd
COMMAND_LABELS = {"r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE", "*": "ALL"}


def _normalize_expr(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _policy_roles(roles: list[str] | tuple[str, ...] | None) -> set[str]:
    # PostgreSQL stores empty polroles as PUBLIC.
    if not roles:
        return {"public"}
    return {str(role) for role in roles}


def audit_from_dsn(dsn: str) -> dict[str, Any]:
    import psycopg2
    import psycopg2.extras

    table_query = """
    SELECT
      n.nspname AS schema_name,
      c.relname AS table_name,
      c.relrowsecurity AS rls_enabled,
      c.relforcerowsecurity AS force_rls_enabled
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'opportunities'
      AND c.relkind IN ('r', 'p')
    LIMIT 1;
    """
    policy_query = """
    SELECT
      p.polname AS policy_name,
      p.polpermissive AS permissive,
      p.polcmd AS command,
      pg_get_expr(p.polqual, p.polrelid) AS using_expression,
      pg_get_expr(p.polwithcheck, p.polrelid) AS with_check_expression,
      ARRAY(SELECT rolname FROM pg_roles WHERE oid = ANY(p.polroles)) AS roles
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'opportunities'
    ORDER BY p.polname;
    """

    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(table_query)
            table = cur.fetchone()
            cur.execute(policy_query)
            policies = [dict(row) for row in cur.fetchall()]

    failures: list[str] = []
    if not table:
        failures.append("public.opportunities table not found")
        table_report = None
    else:
        table_report = dict(table)
        if not table_report.get("rls_enabled"):
            failures.append("public.opportunities RLS is disabled")

    normalized_policies: list[dict[str, Any]] = []
    for policy in policies:
        roles = _policy_roles(policy.get("roles"))
        command = str(policy.get("command") or "")
        using = _normalize_expr(policy.get("using_expression"))
        public_scope = bool(roles & PUBLIC_ROLES)
        read_scope = command in READ_COMMANDS
        permissive_true_read = bool(policy.get("permissive")) and using == "true" and public_scope and read_scope
        public_read = public_scope and read_scope

        if public_read:
            failures.append(
                f"policy {policy.get('policy_name')} grants {COMMAND_LABELS.get(command, command)} to {sorted(roles & PUBLIC_ROLES)}"
            )
        if permissive_true_read:
            failures.append(
                f"policy {policy.get('policy_name')} is permissive USING (true) for public/anon read"
            )

        normalized_policies.append(
            {
                "policy_name": policy.get("policy_name"),
                "permissive": bool(policy.get("permissive")),
                "command": COMMAND_LABELS.get(command, command),
                "roles": sorted(roles),
                "using_expression": policy.get("using_expression"),
                "with_check_expression": policy.get("with_check_expression"),
                "public_or_anon_read": public_read,
                "permissive_true_public_read": permissive_true_read,
            }
        )

    return {
        "status": "FAIL" if failures else "PASS",
        "table": table_report,
        "policy_count": len(normalized_policies),
        "policies": normalized_policies,
        "failures": failures,
    }


def main() -> int:
    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or ""
    if not dsn:
        print(json.dumps({"status": "FAIL", "failures": ["Set SUPABASE_DB_URL or DATABASE_URL to audit live RLS."]}, indent=2))
        return 1

    report = audit_from_dsn(dsn)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
