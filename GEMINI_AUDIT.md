# Gemini 3.1 Pro — Independent Red Team Audit
_Run independently, not shown Codex findings_

SEVERITY: CRITICAL
FILE: webapp/routers/ingest.py
LINE: 881
ISSUE: SSRF (Server-Side Request Forgery) and Path Traversal via unvalidated `apify_run_id`. The `apify_run_id` is extracted directly from the unauthenticated webhook payload (`metadata["run_id"]`) and interpolated into an outgoing HTTP request URL (`f"https://api.apify.com/v2/actor-runs/{apify_run_id}"`). An attacker can pass `../` sequences to access arbitrary Apify API endpoints using the application's `APIFY_TOKEN`.
FIX: Validate `apify_run_id` against a strict regex before using it in the URL.
```python
if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', apify_run_id):
    logger.warning("Invalid apify_run_id format")
    return
```

SEVERITY: CRITICAL
FILE: webapp/routers/ingest.py
LINE: 1181
ISSUE: Authentication Bypass / Insecure Direct Object Reference (IDOR) in `pass_opportunity`. The endpoint extracts `user_id` from the JWT but uses the privileged Service Role client (`get_supabase_client()`) to perform the upsert. It blindly trusts the `opportunity_id` path parameter without verifying if the opportunity exists or if the user has access to it