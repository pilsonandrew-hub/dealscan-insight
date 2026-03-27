# DealerScope Full-System Audit — Gemini 3.1 Pro
Date: 2026-03-27
Auditor: Gemini 3.1 Pro (1M context, full 124-file codebase ingested)
Prompt: dealerscope-audit-prompt-FINAL.md (hardened by Codex)

**DEALERSCOPE FULL-SYSTEM AUDIT — FINAL REPORT****

As requested, I have conducted a hostile, zero-tolerance audit of the DealerScope codebase. I evaluated the system against the specified threat models, business rules, and operational requirements. 

Here are the findings.

---

### 🔴 CRITICAL

`CRITICAL | backend/ingest/score.py:350` | **Financial Miscalculation:** `_compute_max_bid_v2` calculates the max bid incorrectly. It subtracts the buyer premium of the *current* bid instead of the *max* bid. If a user bids the calculated `max_bid`, the actual buyer premium applied at the auction house will cause the total all-in cost to exceed the strict MMR ceiling. | 
```python
# Replace lines 349-350 with:
return round(((mmr * ceiling) - auction_fees_amount) / (1 + premium_pct), 2)
```

`CRITICAL | webapp/routers/rover.py:360` | **Unauthenticated Data Injection:** The `/api/rover/actions` endpoint has zero authentication. An external attacker can POST crafted payloads to inject fake "buy" intents into the `dealer_sales` table for ANY user and ANY opportunity, corrupting the analytics and ML training data. | 
```python
@router.post("/actions")
async def record_action(
    payload: dict[str, Any],
    authorization: Optional[Here are the complete remaining audit findings across all categories for the DealerScope codebase, continuing from the previous analysis.

## CRITICAL

**1. Hardcoded Supabase Service Role Key (JWT)**
*   `backend/ingest/config_loader.py:20`
*   **Detail**: The `SUPABASE_SERVICE_ROLE_KEY` environment variable fallback contains a hardcoded, valid-looking JWT (`[SUPABASE_JWT_REDACTED]`). This key grants full administrative bypass of Row Level Security (RLS) to the Supabase database. If this code is committed to version control, the database is fully compromised.

**2. Hardcoded Firecrawl API Key**
*   `backend/ingest/firecrawl_fallback.py:23`
*   **Detail**: The `FIRECRAWL_API_KEY` fallback contains a hardcoded production API key (`[FIRECRAWL_KEY_REDACTED]`). This exposes the Firecrawl account to unauthorized usage and quota exhaustion.

**3. Hardcoded Supabase Anon Keys in Frontend Source**
*   `src/config/environmentConfig.ts:36`
*   `src/config/environmentManager.ts:101`
*   `src/config/environmentManager.ts:134`
*   `src/config/environmentManager.ts:167`
*   `src/config/productionConfig.ts:66`
*   **Detail**: The Supabase Anon Key is hardcoded across multiple frontend configuration files. While Anon keys are designed to be public, hardcoding them in source code prevents seamless key rotation and violates secure configuration management principles.

**4. Global RLS Bypass via Service Role Key in API Routers**
*   `webapp/database.py:20`
*   `webapp/routers/recon.py:31`
*   **Detail**: The global `supabase_client` is initialized using `SUPABASE_SERVICE_ROLE_KEY` if it exists in the environment. This client is then imported and used across user-facing endpoints (e.g., `webapp/routers/outcomes.py`, `webapp/routers/opportunities.py`). This means the backend API operates with administrative privileges, completely bypassing Supabase Row Level Security (RLS). A vulnerability in any endpoint (e.g., IDOR) would allow users to read/modify data belonging to other tenants.

## HIGH

**1. Unsalted Hashing of Predictable Backup Codes**
*   `webapp/routers/auth.py:260`
*   `webapp/routers/auth.py:341`
*   **Detail**: TOTP backup codes are hashed using raw SHA-256 (`hashlib.sha256(code.encode()).hexdigest()`) without a salt. Because backup codes are short, predictable strings (e.g., 8 hex characters), an attacker with read access to the database can easily crack these hashes using precomputed rainbow tables or brute force.

**2. In-Memory Token Blacklist Prevents Horizontal Scaling**
*   `webapp/security/jwt.py:60`
*   `webapp/routers/auth.py:211`
*   **Detail**: The `TokenBlacklist` class uses an in-memory Python `set()` to store revoked JWTs. If the FastAPI application is deployed with multiple workers (e.g., Gunicorn) or scaled horizontally across multiple containers, a token revoked on Worker A will still be accepted by Worker B. This defeats the logout mechanism.

**3. SSRF Vulnerability via DNS Rebinding (TOCTOU)**
*   `webapp/middleware/security.py:100`
*   **Detail**: The `_is_safe_url` function resolves the hostname to an IP address using `socket.gethostbyname(hostname)` and checks if it belongs to a private network. However, the actual HTTP request is made later. An attacker can use a DNS rebinding attack where the DNS server returns a safe IP during the check, but a private IP (e.g., `127.0.0.1`) during the actual fetch, bypassing the SSRF protection.

**4. Arbitrary Code Execution Risk via Pandas Excel Parsing**
*   `webapp/routers/upload.py:58`
*   `webapp/routers/upload.py:63`
*   **Detail**: The `/csv` upload endpoint passes raw uploaded bytes directly to `pd.read_excel()`. Depending on the underlying engine installed (e.g., `openpyxl`, `xlrd`), parsing untrusted Excel files can lead to XML External Entity (XXE) attacks or arbitrary code execution.

**5. Dynamic SQL Construction Risk**
*   `webapp/routers/ingest.py:1011`
*   **Detail**: `_insert_opportunity_direct_pg` dynamically constructs a SQL `INSERT` statement by iterating over `row.keys()` and wrapping them in `psycopg2_sql.Identifier(column)`. While `row` is currently built from a controlled dictionary in `build_opportunity_row`, any future modification that allows user-controlled keys to enter this dictionary will result in SQL injection.

## MEDIUM

**1. Non-Fatal Fallback for Missing Production Secret Key**
*   `backend/main.py:139`
*   **Detail**: If `SECRET_KEY` is not set in the production environment, the application logs a critical error but *does not exit*. It continues running using the hardcoded fallback `"dev-secret-change-in-prod"`, compromising all cryptographic signing and session management.

**2. Flawed Account Lockout Reset Logic**
*   `webapp/routers/auth.py:111`
*   **Detail**: The account lockout logic checks `if user.locked_until > datetime.now()`. If the lockout period has expired, it allows the login attempt. However, if the user guesses the password incorrectly again, `user.failed_login_attempts` is incremented (from 5 to 6), and the account is immediately locked for another 30 minutes. The failed attempts counter is only reset upon a *successful* login, creating a frustrating UX and potential denial-of-service vector.

**3. Inadequate IP Parsing in Frontend SSRF Guard**
*   `src/security/ssrfGuard.ts:130`
*   **Detail**: The `isPrivateIP` function uses regular expressions (e.g., `/^10\./`) to detect private IP addresses. This can be bypassed using alternative IP representations supported by browsers and `fetch` (e.g., octal `012.0.0.1`, hexadecimal `0x0A000001`, or integer formats), allowing SSRF attacks against internal networks.

**4. Magic Byte Validation Bypass**
*   `src/security/uploadHardening.ts:240`
*   **Detail**: The `detectMimeType` function checks magic bytes, but if no signature matches, it falls back to trusting the client-provided `file.type` if it exists in `allowedMimeTypes`. An attacker can upload a malicious executable, spoof the `Content-Type` header to `image/jpeg`, and bypass the magic byte check.

**5. Unhandled External API Changes (Notion)**
*   `webapp/routers/ingest.py:1180`
*   **Detail**: `sync_to_notion` uses `httpx.AsyncClient` to push data to Notion. If the Notion API schema changes or the database ID is invalid, the function logs a warning and returns `False`, but there is no dead-letter queue or retry mechanism for failed syncs.

## LOW

**1. Synchronous Network Call in Async Event Loop**
*   `backend/ingest/condition.py:88`
*   **Detail**: `urllib.request.urlopen` is used synchronously inside the FastAPI application to fetch NHTSA VIN data. This blocks the ASGI event loop, degrading performance and concurrency for all other API requests during the network call.

**2. Unsafe File Replacement in Cache**
*   `backend/ingest/retail_comps.py:31`
*   **Detail**: `_write_file_cache_locked` uses `os.replace(temp_path, _CACHE_PATH)`. While atomic, it assumes the `.cache` directory exists and has the correct permissions. If the application is run in a read-only container filesystem without a mounted volume, this will crash.

**3. Redis Connection Initialized Per-Request**
*   `webapp/middleware/rate_limit.py:130`
*   **Detail**: The `RateLimitMiddleware` initializes the `redis.asyncio` client inside the `dispatch` method on the first request. This should be initialized during the FastAPI `lifespan` startup event to ensure connection pooling is established before traffic arrives.

**4. Stubbed Security Scan Endpoint**
*   `webapp/routers/admin.py:34`
*   **Detail**: The `POST /api/admin/security/scan` endpoint is a stub that returns `{"message": "Security scan initiated"}` without actually performing any action.

**5. Inconsistent Logging Levels**
*   `src/core/SimpleLogger.ts:30`
*   **Detail**: `console.debug` is correctly gated behind `isDevelopment`, but `console.info`, `console.warn`, and `console.error` are executed unconditionally, potentially leaking sensitive application state or stack traces to the browser console in production.

## CONFIRMED CORRECT

*   **Webhook Secret Posture**: `backend/ingest/webhook_secret_posture.py` implements excellent validation, checking for placeholder values, minimum entropy (length), and safe rotation overlap states.
*   **TOTP Implementation**: `webapp/security/totp.py` correctly utilizes `pyotp` for standard time-based one-time passwords and securely generates provisioning URIs and QR codes.
*   **Password Strength**: `src/auth/passwordSecurity.ts` implements robust, NIST-compliant password strength checks, including entropy validation, sequential character blocking, and integration with the HaveIBeenPwned API using k-anonymity.
*   **Error Sanitization**: `webapp/middleware/error_handler.py` correctly intercepts exceptions and uses regex to redact sensitive tokens, passwords, and bearer strings before writing to the application logs.

## CANNOT DETERMINE

*   **Frontend Environment Variable Exposure**: It cannot be determined from the provided files if `VITE_SUPABASE_SERVICE_ROLE_KEY` is accidentally injected into the frontend build process. If the build pipeline exposes this to the client bundle, it is a critical vulnerability.
*   **Supabase RLS Policy Strictness**: Because the backend uses the Service Role Key, it cannot be determined if the actual Row Level Security policies defined in the Supabase database are correctly scoped to `auth.uid()`. If the backend is ever refactored to use Anon keys, weak RLS policies would immediately expose tenant data.

## MISSING SOPs

*   **Secret Rotation SOP**: There is no Standard Operating Procedure documented for rotating the hardcoded fallback keys (Supabase JWT, Firecrawl API key) found in the codebase.
*   **Token Revocation SOP**: There is no SOP for managing the in-memory token blacklist (`TokenBlacklist`). If a user's account is compromised, restarting the server clears the blacklist, re-validating the compromised tokens.

## RISK ACCEPTANCE STATEMENT

*   **Headless Browser Detection**: The use of `headless=True` in Playwright (`backend/scrapers/govdeals_active.py`) without stealth plugins (e.g., `playwright-stealth`) is accepted for now, assuming the target sites (GovDeals, PublicSurplus) do not aggressively block the current IP ranges.
*   **In-Memory Rate Limiting/Blacklisting**: The use of in-memory structures for token blacklisting is accepted for single-instance deployments, but must be migrated to Redis prior to horizontal scaling.

## ARCHITECTURE VERDICT

The architecture demonstrates a strong conceptual separation between the React frontend and the FastAPI backend, with sophisticated ML scoring and ingestion pipelines. However, the backend's reliance on the **Supabase Service Role Key** for database operations is a critical architectural flaw. By bypassing Row Level Security (RLS) at the API layer, the backend acts as a monolithic, highly-privileged entity. A single vulnerability in the API (e.g., an IDOR in the opportunities router) would grant an attacker access to all cross-tenant data. 

Furthermore, the presence of hardcoded production JWTs and API keys in the source code indicates a severe breakdown in secrets management and CI/CD practices. While the frontend implements excellent defense-in-depth mechanisms (SSRF guards, upload hardening, intrusion detection), these client-side protections are ultimately "security by obscurity" if the backend API and database credentials are fundamentally compromised. Immediate remediation of hardcoded secrets and a transition to JWT-forwarded RLS queries are required before production deployment.