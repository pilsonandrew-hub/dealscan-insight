# DealerScope Red Team Audit

Date: 2026-03-11
Auditor: Codex GPT-5
Scope: requested backend, frontend, infra, and sampled Apify actors (`ds-allsurplus`, `ds-govdeals`, `ds-publicsurplus`), plus adjacent files needed to verify contracts.

## Secrets And Credential Exposure

- [CRITICAL] `webapp/routers/ingest.py:29` — Hardcoded Telegram bot token in application source. Anyone with repo or image access can hijack alerts or impersonate the bot. — Remove the default token, rotate it immediately, and fail startup if `TELEGRAM_BOT_TOKEN` is missing in non-dev environments.
- [CRITICAL] `apify/actors/ds-allsurplus/src/main.js:5` — Hardcoded `WEBHOOK_SECRET` in actor code. The same secret pattern also appears in other actor files, so the ingest trust boundary is already burned. — Rotate the secret now, move it to Apify actor input or secrets, and refuse to run actors without it.
- [LOW] `src/pages/Auth.tsx:101` — Dead-code helper still contains a hardcoded test account email/password (`test@dealerscope.com` / `testpass123`). Even if it is not wired into the UI, committing credentials is sloppy and invites accidental exposure later. — Delete the helper, scrub the credential from source control, and keep test accounts in fixtures or environment-scoped seeding.

## Authentication, Authorization, And Abuse Controls

- [CRITICAL] `backend/main.py:181` — `/api/pipeline/run` is completely unauthenticated. Any external caller who can hit the backend can trigger scrapes and downstream costs on demand. — Require admin auth or a dedicated signed service token, queue the work server-side, and audit every trigger.
- [HIGH] `backend/main.py:18` — Security-critical middleware imports fail open. If `SecurityMiddleware`, `RateLimitMiddleware`, or `ErrorHandlerMiddleware` cannot import, the app still boots and merely logs a warning. — Treat security middleware load failures as startup-fatal in production.
- [HIGH] `webapp/middleware/rate_limit.py:14` — IP extraction trusts spoofable headers from any client and then takes the wrong end of `X-Forwarded-For`. An attacker can pick their own identity and sidestep per-IP limits. — Only trust proxy headers from known reverse proxies and use the first untrusted hop, not the last.
- [HIGH] `webapp/middleware/rate_limit.py:57` — Redis outage disables rate limiting entirely because the middleware falls through to `call_next`. That turns “cache issue” into “no abuse protection.” — Use an in-process fallback limiter for sensitive routes or fail closed on auth-heavy endpoints.
- [HIGH] `webapp/middleware/rate_limit.py:38` — Route-specific limits do not match the real mounted paths. The middleware limits `/auth/login` and `/upload`, but the app mounts these under `/api/auth` and `/api/upload`, so the stricter caps never fire. — Normalize routes before lookup or configure limits against the real mounted paths.
- [MEDIUM] `webapp/middleware/rate_limit.py:89` — The middleware mixes per-IP, per-user, and global route counters under the same limit value. One loud client can exhaust the route-wide bucket and rate-limit everyone else. — Split global route ceilings from per-user/IP ceilings and tune them independently.
- [LOW] `backend/main.py:205` — The health endpoint leaks loaded router names and route count. This is not catastrophic, but it gives recon data away for free. — Return only readiness/liveness status on unauthenticated health checks.

## Ingest Pipeline And Data Integrity

- [HIGH] `webapp/routers/ingest.py:215` — The ingest endpoint only understands Apify platform webhook payloads with `resource.defaultDatasetId`, but `ds-allsurplus` posts raw `{ source, listings }` JSON directly. Those deliveries are silently discarded with “No dataset to process.” — Pick one ingestion contract and enforce it consistently: either accept direct listing payloads or require dataset-based webhooks everywhere.
- [HIGH] `webapp/routers/ingest.py:225` — Dataset ingestion loads the full Apify dataset into memory in one `resp.json()` call with no paging or max item cap. A large dataset turns into an easy memory/latency DoS. — Page through the dataset, bound item counts, and reject oversized runs.
- [MEDIUM] `webapp/routers/ingest.py:33` — The backend silently falls back from `SUPABASE_SERVICE_ROLE_KEY` to `VITE_SUPABASE_ANON_KEY`. That collapses the boundary between backend and browser credentials and can leave writes half-working or fully broken without a hard failure. — Require the service role key explicitly for backend writes and crash on startup if it is absent.
- [MEDIUM] `webapp/routers/ingest.py:171` — Duplicate detection is a read-then-write sequence outside a transaction. Concurrent ingests can both decide a record is canonical and race into inconsistent state. — Move dedupe into a single transactional DB routine or Supabase RPC guarded by the unique index.
- [MEDIUM] `webapp/routers/ingest.py:727` — The upsert conflict key is `listing_url`, which is source-controlled input. URL collisions or normalization differences can overwrite unrelated rows. — Use a stable source-specific listing ID or a composite natural key, with canonical dedupe handled separately.
- [LOW] `webapp/routers/ingest.py:204` — Webhook verification is a simple string compare with no replay protection. If the secret leaks once, old or forged requests are reusable forever. — Use `hmac.compare_digest`, add a signed timestamp/nonce, and reject stale requests.

## Frontend And API Contract Failures

- [HIGH] `src/services/api.ts:204` — The rover recommendations client calls `/api/rover/recommendations` without the required `user_id` parameter and expects `recommendations`/`data`, while the backend returns `items` and enforces `user_id` equality. The feature as written cannot work. — Define a shared typed contract and update either the backend shape or the client call, then add an integration test.
- [HIGH] `src/services/api.ts:226` — Rover event tracking posts `{ deal_id, event_type }`, but the backend expects `event` and optionally `item`. The server will reject or mis-handle the payload, so feedback loops never train correctly. — Version the event schema, share request types across client/server, and test the round trip.
- [MEDIUM] `src/services/api.ts:72` — The frontend queries `opportunities` with `select('*')` and ships whole rows into the browser. If the table contains VINs, raw payloads, or internal scoring artifacts, you are overexposing data by default. — Project only the columns the UI actually renders and keep sensitive fields server-side.
- [MEDIUM] `src/components/SniperScopeDashboard.tsx:112` — Locked bid targets are stored in plaintext `localStorage`. Any XSS, browser extension, shared workstation, or dumped profile leaks your bidding strategy. — Store targets server-side per user or encrypt them client-side with a user-held secret and retention policy.
- [MEDIUM] `src/components/SniperScopeDashboard.tsx:121` — The calculator trusts raw numeric input with no bounds. Negative fees, negative tax, or absurd values produce nonsense max bids that users can save as if they were valid. — Validate and clamp every numeric field before calculation and persistence.
- [LOW] `src/pages/Auth.tsx:50` — The auth page logs emails and auth outcomes to the browser console. That is needless PII leakage in production builds. — Strip auth debug logging from production or gate it behind a dev-only logger.
- [LOW] `src/services/api.ts:269` — `uploadCSV` always returns success without performing any upload. That masks real failures and trains operators to trust fake green lights. — Remove the stub or implement the upload and failure handling honestly.

## Infrastructure And Deployment

- [HIGH] `Dockerfile:25` — `COPY . .` with no `.dockerignore` means the whole repo enters the build context, including local `.env`, docs, test artifacts, and `.git` if present. That is how secrets end up baked into layers. — Add a strict `.dockerignore` and copy only the runtime files needed for the image.
- [MEDIUM] `Dockerfile:8` — `apt-get upgrade -y` during the image build makes the container non-reproducible and causes package drift outside your dependency review process. — Use a pinned base image, install only required packages, and avoid blanket distro upgrades during the build.
- [LOW] `vercel.json:6` — Only `/proxy/health` is proxied same-origin; other authenticated API calls go straight to Railway. You have two network paths and inconsistent trust assumptions. — Proxy the app API consistently or enforce CORS/CSRF and environment separation deliberately.
- [LOW] `railway.toml:8` — Railway health checks hit `/health`, which returns verbose router metadata, instead of a minimal readiness path. — Point health checks at a narrow liveness/readiness endpoint that reveals nothing else.

## Database And Migration Risks

- [MEDIUM] `supabase/migrations/20260312_deduplication.sql:11` — The partial unique index is only a backstop. It does nothing to fix the non-transactional duplicate check in application code, so concurrent ingests still race and lose data. — Keep the index, but move canonical selection into a single DB transaction/RPC.
- [LOW] `supabase/migrations/20260312_deduplication.sql:4` — `canonical_record_id` can point anywhere in the same table, including invalid chains or self-reference, because there is no invariant beyond foreign-key existence. — Add a check/trigger that only canonical rows may be referenced and prevent self-reference.

## Apify Actors

- [HIGH] `apify/actors/ds-govdeals/package.json:1` — The actor uses ESM `import` syntax in `src/main.js` but the package lacks `"type": "module"`. Under plain `node src/main.js`, this fails before the actor even crawls. — Declare ESM explicitly or convert the actor to CommonJS.
- [HIGH] `apify/actors/ds-publicsurplus/package.json:1` — Same runtime mismatch as GovDeals: ESM source, no `"type": "module"`, plain Node start command. — Fix the package type or transpile before runtime.
- [MEDIUM] `apify/actors/ds-publicsurplus/src/main.js:99` — Selector fallbacks like `h1`, `[class*="title"]`, and `[class*="location"]` are so broad they will scrape site chrome as vehicle data when the page layout shifts. — Tighten selectors to stable detail containers and validate extracted fields before `pushData`.
- [MEDIUM] `apify/actors/ds-govdeals/src/main.js:265` — A new `page.on('response')` listener is added inside every pagination loop iteration without cleanup. That causes duplicate captures, noisy counts, and growing listener overhead. — Register once per page lifecycle or remove listeners between page turns.
- [MEDIUM] `apify/actors/ds-allsurplus/src/main.js:383` — The actor both pushes dataset items and separately POSTs listings directly to the ingest endpoint, but the ingest endpoint does not consume that payload shape. The integration model is inconsistent and partly dead. — Standardize actor delivery on either Apify dataset webhooks or direct signed POSTs, not both.

## Top 5 Fixes

1. Lock down `POST /api/pipeline/run` immediately. Right now anyone can spend your money for you.
2. Rotate every compromised secret already committed to source: Telegram bot token and the shared Apify webhook secret first.
3. Make security middleware and rate limiting fail closed in production instead of silently disappearing.
4. Fix the rover client/server contract and the ingest actor/webhook contract; both are broken in ways that quietly drop critical data.
5. Add a `.dockerignore`, stop copying the whole repo into the image, and remove backend fallbacks to browser-scoped credentials.

## Overall Risk

Overall risk score: **9/10**

Reason: there are multiple externally reachable control-plane weaknesses (unauthenticated pipeline trigger, compromised shared webhook secret, fail-open abuse controls), plus several broken data contracts that make the platform look healthy while silently dropping or corrupting data.
