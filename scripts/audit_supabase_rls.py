#!/usr/bin/env python3
"""Inspect live Supabase/Postgres RLS policies for opportunities (read-only safe audit)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


def _rest_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }


def fetch_policies_via_rest(supabase_url: str, service_key: str) -> list[dict[str, Any]]:
    """Best-effort policy listing via PostgREST-exposed catalog if available."""
    url = f"{supabase_url.rstrip('/')}/rest/v1/rpc/list_opportunity_policies"
    if httpx is None:
        return []
    try:
        resp = httpx.post(url, headers=_rest_headers(service_key), json={}, timeout=20.0)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def audit_from_dsn(dsn: str) -> dict[str, Any]:
    import psycopg2

    query = """
    SELECT
      c.relname AS table_name,
      c.relrowsecurity AS rls_enabled,
      p.polname AS policy_name,
      p.polcmd AS command,
      pg_get_expr(p.polqual, p.polrelid) AS using_expression,
      pg_get_expr(p.polwithcheck, p.polrelid) AS with_check_expression,
      ARRAY(SELECT rolname FROM pg_roles WHERE oid = ANY(p.polroles)) AS roles
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'opportunities'
    ORDER BY p.polname;
    """
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    public_read = []
    for row in rows:
        using = (row.get("using_expression") or "").lower()
        roles = row.get("roles") or []
        if "true" in using and (not roles or "public" in roles or "anon" in roles):
            public_read.append(row)
    return {
        "table": "opportunities",
        "policy_count": len(rows),
        "policies": rows,
        "public_or_anon_read_policies": public_read,
        "status": "FAIL" if public_read else "PASS",
    }


def main() -> int:
    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or ""
    if not dsn:
        print(
            json.dumps(
                {
                    "status": "SKIP",
                    "message": "Set SUPABASE_DB_URL or DATABASE_URL to audit live RLS.",
                },
                indent=2,
            )
        )
        return 0

    report = audit_from_dsn(dsn)
    print(json.dumps(report, indent=2, default=str))
    return 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
