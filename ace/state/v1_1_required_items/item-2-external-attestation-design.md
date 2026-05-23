# ACE V1.1 Item 2 — External Attestation Design

Status: revised design draft for Ja’rvontis/operator re-review. No implementation is authorized by this document.

Scope: V1.1 item 2, external audit attestation to Backblaze B2.

Governing boundary:

> ACE has tamper-evident append-only event chain from V1.1 cutover forward. Pre-cutover history is retained unchanged with disclosed legacy defects.

This design extends that post-cutover claim with independent external attestation. It does not rewrite, repair, or hide pre-cutover defects disclosed in `ace/state/v1_1_required_items/legacy-chain-defects.md`.

## 1. Goal

Add an external, independently retained attestation surface so `ace audit verify` can compare local post-cutover chain truth against Backblaze B2 records that ACE cannot silently rewrite during normal operation.

Acceptance intent from `ace/V1.1-SCOPE.md`:

- Audit chain hashes are mirrored to an external store.
- Backblaze B2 is the required external attestation store.
- `ace audit verify` includes external comparison.
- The bot cannot rewrite the external mirror.
- Without this, `event_hash_chain=ok` remains internally consistent only, not independently verifiable.

## 2. Non-goals

This item does not:

- store full ACE event payloads in B2;
- make any claim about undisclosed or repaired pre-cutover history;
- use B2 as ACE’s source of truth;
- perform credential setup inside the repo;
- put B2 keys in git, `MEMORY.md`, daily memory, logs, or documentation;
- start ACE 1.0 re-tagging;
- change the cutover event or pre-cutover rows.

## 3. What gets mirrored

Mirror event hashes only, not full payloads.

Recommended object content is one canonical JSON document per post-cutover event:

```json
{"schema_version":"ace-b2-attestation-v1","chain_id":"ace-v1.1-post-cutover","instance_id":"<operator-assigned-instance-id>","cutover_event_id":"evt_58b80e6282374bf2b1a8611963817aa2","event_sequence":1,"event_id":"...","event_hash":"...","previous_event_hash":null,"created_at":"...","manifest_generator_version":"..."}
```

Per-row fields:

- `schema_version`
- `chain_id`
- `instance_id`
- `cutover_event_id`
- `event_sequence`
- `event_id`
- `event_hash`
- `previous_event_hash`
- `created_at`
- `manifest_generator_version`

Rationale:

- `event_hash` commits to the canonical event hash payload already stored locally.
- `previous_event_hash` preserves chain linkage for remote-side review without exposing payloads.
- `event_sequence` makes order deterministic from cutover forward.
- `created_at` is metadata only; it is not ordering authority.
- `instance_id` prevents multiple ACE installations or DBs from colliding under the same remote namespace.
- `manifest_generator_version` makes schema/cutover mismatch detectable instead of silently comparing incompatible formats.

Optional checkpoint object content is allowed only as an acceleration aid, not as the primary trust surface. Per-event immutable objects remain authoritative for V1.1.

The manifest/header/checkpoint objects must not include credentials, host secrets, full payloads, or private conversation text.

## 4. Backblaze B2 integration architecture

Recommended module layout:

- `ace/attestation/__init__.py`
- `ace/attestation/backblaze.py`
- `ace/attestation/manifest.py`
- tests under `ace/tests/`

Recommended responsibilities:

### `manifest.py`

- Read local ACE DB through `connect_readonly`.
- Require exactly one V1.1 cutover event.
- Select post-cutover events ordered by `event_sequence ASC, id ASC`.
- Emit deterministic hash-only attestation records.
- Validate no NULL/duplicate/gapped post-cutover `event_sequence` before emitting.
- Validate `schema_version`, `chain_id`, `instance_id`, and cutover event identity before comparing local and remote records.

### `backblaze.py`

- Own B2 API interaction behind a small interface.
- Load credentials only from environment variables or an operator-owned secrets mechanism.
- Upload/read/list attestation objects.
- Convert B2 errors into explicit ACE verification statuses.
- Support paginated prefix listing; audit cannot assume one-page remote listings.
- Surface version metadata needed by the version verification policy in Section 7.

Suggested environment variables:

- `ACE_B2_KEY_ID`
- `ACE_B2_APPLICATION_KEY`
- `ACE_B2_BUCKET_NAME`
- `ACE_B2_BUCKET_ID` optional but preferred after setup
- `ACE_B2_INSTANCE_ID`
- `ACE_B2_OBJECT_PREFIX`, default derived as described in Section 5

No B2 secret is ever committed or remembered in `MEMORY.md`.

## 5. Object naming, namespace isolation, and rewrite prevention

### Mandatory namespace isolation

Each load-bearing ACE instance must have a unique operator-assigned `instance_id`. The `instance_id` is not a secret, but it must be stable for the lifetime of that ACE DB.

Recommended bucket naming rule:

```text
ace-attestation-<operator-or-org-slug>-<environment>
```

Examples:

- `ace-attestation-andrew-prod`
- `ace-attestation-andrew-test`

Recommended prefix derivation:

```text
ace/v1_1/attestation/instance_<instance_id>/cutover_evt_58b80e6282374bf2b1a8611963817aa2/
```

Primary immutable object pattern:

```text
ace/v1_1/attestation/instance_<instance_id>/cutover_evt_58b80e6282374bf2b1a8611963817aa2/seq_000000000001__evt_<event_id>.json
```

Rules:

- One production ACE DB gets one production bucket/prefix.
- Test/dev ACE DBs must use a separate bucket or separate explicit `instance_id` and prefix.
- Two local DBs must never share the same production prefix.
- Every remote object body must contain the same `instance_id`, `chain_id`, and `cutover_event_id` implied by its prefix.
- Audit must fail closed with `external_attestation_namespace_collision` if it lists an object under the active prefix whose body contains an unexpected `instance_id`, `chain_id`, cutover id, schema version, malformed name, or nonconforming record.

### Rewrite prevention

V1.1 re-tag requires Backblaze B2 Object Lock/versioning on the attestation bucket. This is mandatory, not optional, for the full external-attestation claim.

Required operator-side B2 controls:

- Create a dedicated B2 bucket for ACE attestation.
- Enable Object Lock / retention before first production attestation object is written.
- Enable version visibility sufficient for audit to inspect object versions.
- Use a bucket-scoped application key.
- Prefer list/read/write without delete if B2 supports that restriction for the selected key model.
- Do not reuse this key for general automation.

If Object Lock/versioning cannot be enabled and verified, item 2 may still be implemented as a best-effort remote mirror, but the honest claim must be downgraded to:

> ACE has local post-cutover tamper-evidence with best-effort external B2 mirroring. Remote mirror records are compared during audit, but the mirror is not independently protected against overwrite/delete by ACE-held credentials.

That downgraded claim is insufficient for an honest ACE 1.0 re-tag unless the operator explicitly accepts the weaker guarantee in writing.

Why per-event immutable objects:

- B2 is object storage, not an append-only database.
- Re-uploading a monolithic manifest creates rewrite-like behavior unless Object Lock/versioning is configured and verified.
- Per-event object names make each event attestation stable and independently checkable.
- Existing objects are immutable for ACE’s purposes: if the object exists, ACE must read and compare; it must not overwrite.

Optional aggregate checkpoint objects can be added later, but V1.1 must not depend on a mutable aggregate file for integrity.

## 6. When mirror happens and durable crash correctness

Recommendation: hybrid with deterministic full-scan reconciliation.

### Write-time behavior

On successful post-cutover `append_event` commit:

- Do not contact B2 inside the same SQLite transaction.
- Do not block the local append on network I/O.
- It is acceptable to make a best-effort post-commit attestation attempt, but correctness must not depend on that attempt.

Reason: putting network I/O inside the event append transaction risks blocking ACE’s core ledger and creating partial-failure ambiguity.

### Durable correctness rule

No event can be left in an unattested state silently because every explicit sync and every external-attestation audit derives expected remote records by scanning **all** local post-cutover events from the DB.

Therefore:

- A crash after local append but before B2 sync is detected as `external_attestation_missing` on the next audit.
- The next sync scans all post-cutover events and uploads any missing matching immutable objects.
- A durable local queue is not required for correctness.
- A local retry/attempt table may be added later for observability, but it is not authoritative and cannot replace full DB-derived reconciliation.

### Audit-time reconciliation

`ace audit verify` must:

1. run local post-cutover chain verification first;
2. generate expected attestation object names and bodies for all post-cutover events;
3. list the entire B2 remote prefix using pagination until exhaustion;
4. parse and validate every listed object under the prefix;
5. compare exact set equality between local expected object names and remote object names;
6. compare exact canonical content for every matching object;
7. apply the version verification policy in Section 7;
8. fail closed on missing, mismatched, extra, malformed, conflicting-version, namespace-collision, pagination, auth, or API errors.

The chosen approach is exact-set remote comparison, not only local-expected lookup and not a shrinkable remote high-watermark. A remote high-watermark/checkpoint may be added later for performance, but it must not replace exact-set comparison unless the checkpoint is itself Object-Locked and proves it cannot shrink.

Audit must stay read-only by default. If a missing remote object is found, audit reports failure/pending status; it does not mutate B2 unless the operator runs an explicit attestation sync command.

### Explicit sync command

Add a command such as:

```bash
python3 -m ace.ace attestation sync --backend b2 --db ace/state/ace.db
```

This command performs external writes and therefore requires operator authorization and configured B2 credentials.

Recommended operational model:

- local append remains canonical SQLite;
- explicit sync performs B2 writes by full local post-cutover scan;
- read-only audit performs exact local-vs-remote set/content/version comparison;
- audit is not green until remote records exactly match local post-cutover truth under the isolated prefix.

## 7. Remote version verification and TOCTOU mitigation

### Version verification policy

Because V1.1 requires B2 Object Lock/versioning, verification must use version-aware comparison.

Chosen policy:

1. For each expected object name, audit lists all visible versions for that object if B2 exposes version listing.
2. The earliest locked version must exactly match the expected canonical record.
3. No later visible version may conflict with the expected canonical record.
4. If later versions exist and are byte-for-byte identical to the expected canonical record, audit may pass but should report duplicate-identical versions as informational.
5. If B2 cannot expose enough version metadata to enforce this policy, audit must fail with `external_attestation_version_visibility_unverified` for production V1.1.

Rationale: latest-only verification can hide a malicious later version; earliest-locked verification plus no conflicting later versions preserves the first externally attested truth and detects shadowing.

### TOCTOU mitigation

The previous check-then-upload pattern is not sufficient by itself.

Sync must follow this conflict-safe sequence:

1. Build the canonical expected object body locally.
2. List/read existing remote object versions for the exact object name.
3. If a matching locked version already exists and no conflicting version exists, treat as idempotent success.
4. If any conflicting version exists, fail closed and do not upload.
5. If no object exists, upload the canonical body.
6. Immediately read back/list versions for the exact object name.
7. Verify the uploaded object is present, content matches exactly, and version policy is satisfied.
8. If post-upload readback fails, is truncated, differs, shows conflict, or cannot prove the version policy, report `external_attestation_upload_unverified` and leave audit non-green.

If B2 provides conditional upload / if-none-match / file-lock semantics, implementation should use them. If not, strict post-upload readback plus version conflict handling is mandatory.

## 8. Failure-mode handling

### B2 unreachable / timeout

- Append path: event append succeeds; external attestation remains missing until sync succeeds.
- Sync command: exits non-zero with `attestation_remote_unreachable`.
- Audit verify: local checks may pass, but external attestation check fails with a clear unreachable status.

### B2 slow

- Use bounded request timeouts.
- Do not hold SQLite write transaction while waiting for B2.
- Retry only in explicit sync with bounded backoff and jitter.
- Respect 429/rate-limit responses and `Retry-After` if provided.
- No tight retry loops.

### B2 auth error

- Do not prompt for secrets in logs.
- Return `attestation_auth_failed`.
- Operator must fix environment/key configuration.

### B2 object missing

- Audit verify returns failure/pending: `external_attestation_missing event_sequence=N event_id=...`.
- Explicit sync may create it.

### B2 object exists and matches

- Verification passes for that event only if exact content and version policy pass.

### B2 object exists and differs

- Fail closed: `external_attestation_mismatch event_sequence=N event_id=...`.
- Do not overwrite.
- Treat as possible local tamper, remote tamper, naming collision, schema mismatch, or partial upload; operator investigation required.

### Remote extra object

If audit lists an object under the active prefix that is not in the local expected set, audit must fail closed with `external_attestation_remote_extra`.

This is required to detect local deletion/rewrite/shrink attacks where old remote records no longer correspond to local rows.

### B2 eventual consistency / clock behavior

- Audit and sync must not use B2 timestamps as ordering authority.
- `event_sequence` and object name determine order.
- After upload, sync must perform readback with bounded retry to account for B2 visibility delay.
- If read-after-write visibility cannot be confirmed within the bounded window, sync returns `external_attestation_upload_unverified`; audit remains non-green until a later audit sees the object.
- B2 server clock metadata is diagnostic only, never chain truth.

### Remote listing pagination

Audit and sync must paginate remote prefix listing until exhaustion. If pagination fails mid-stream, repeats unexpectedly, returns malformed continuation state, or hits a configured safety cap before exhaustion, audit fails with `external_attestation_listing_incomplete`.

### Remote object truncation / partial upload

Every remote object comparison must verify:

- full byte-for-byte canonical JSON body;
- expected SHA-256 of the body if stored/returned;
- parseable JSON;
- expected schema/version/instance/cutover fields.

A truncated, partial, malformed, or noncanonical object is a mismatch and audit failure.

### Schema migration / manifest generator mismatch

Remote objects include `schema_version` and `manifest_generator_version`. Audit must reject unsupported schema versions and must fail closed if the local generator cannot produce the exact canonical form required by the remote object schema.

Schema upgrades require a separate design/migration path. V1.1 must not silently compare incompatible schema versions.

### Bucket/prefix collision or multiple local DBs

If audit sees objects under the configured prefix with unexpected `instance_id`, unexpected cutover id, duplicate object names for different content, or object names outside the expected naming grammar, audit fails with `external_attestation_namespace_collision` or `external_attestation_remote_extra`.

## 9. Verification logic for `ace audit verify`

Add a seventh audit surface only after implementation:

- `external_attestation=ok|failed|pending|not_configured`

Recommended semantics:

- `ok`: local post-cutover chain passes; remote prefix listing is complete; exact local-vs-remote object set equality passes; every matching object has exact canonical content; every object satisfies the version policy; no extra/malformed/foreign objects exist under the prefix.
- `failed`: remote object exists but differs, remote extras exist, B2 auth fails, B2 API errors prevent trust, version policy cannot be verified, namespace collision is detected, listing is incomplete, or object set/content is inconsistent.
- `pending`: one or more expected objects are missing but credentials/backend are otherwise reachable and no mismatch/conflict is detected. This blocks ACE 1.0 re-tag until sync resolves it.
- `not_configured`: B2 credentials/bucket/instance id are not configured. This blocks V1.1 closure but should be distinguishable from tamper.

Important: `ace audit verify` must not silently skip external comparison once item 2 is active. If credentials are missing after activation, report `not_configured` and return a non-green overall audit.

Suggested CLI output:

```text
audit.verify.external_attestation=ok
audit.verify.external_attestation_detail=backend=b2 checked=123 missing=0 extra=0 mismatched=0 conflicting_versions=0 cutover_event_id=evt_58b80e6282374bf2b1a8611963817aa2 instance_id=<instance_id>
```

## 10. Local state for pending attestation

Design choice for V1.1: no durable queue is required for correctness.

The source of truth for expected remote records is always the local post-cutover `events` table plus the cutover boundary. Sync and audit scan all post-cutover events every time. This means a crash between append and sync cannot silently strand an event; the next audit/sync will find it missing remotely.

A local table may be added for observability only, not correctness:

```sql
CREATE TABLE IF NOT EXISTS event_attestations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  event_sequence INTEGER NOT NULL,
  backend TEXT NOT NULL,
  object_name TEXT NOT NULL,
  expected_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  last_attempted_at TEXT,
  last_verified_at TEXT,
  failure_code TEXT,
  failure_detail TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (event_id) REFERENCES events(event_id)
)
```

This table is metadata about attestation attempts. It is not part of the event hash chain, does not replace remote B2 truth, and cannot suppress full-scan reconciliation.

## 11. Credential management and leakage hardening

Rules:

- B2 keys are operator-owned.
- B2 keys never go in repo files.
- B2 keys never go in `MEMORY.md` or daily memory.
- B2 keys never print in command output, test output, exceptions, logs, audit detail, tracebacks, or failure records.
- Tests use fake clients / dependency injection, not real B2.
- Live sync/verify with B2 requires operator-supplied environment variables or a separate approved secret store.

Operational hardening requirements:

- Shell history: operator setup instructions must use shell-history-safe patterns, such as entering secrets in a non-logged secret manager or temporary environment file outside repo with restrictive permissions. Do not include commands that paste raw secrets into shell history.
- macOS process environment exposure: long-running ACE processes should not keep B2 application keys in broadly inspectable process environments if avoidable. Prefer launchd environment files or keychain/secret-store retrieval scoped to the ACE runner account. If environment variables are used, run under a dedicated restricted OS account and document the residual risk.
- CI masking: live B2 credentials must not be present in default CI. If an optional live integration workflow is added, secrets must use GitHub Actions secrets, masking must be verified, and logs must never echo env vars or command invocations containing secrets.
- Crash/error traceback scrubbing: B2 client exceptions must be wrapped so request headers, authorization tokens, application keys, signed URLs, and raw environment dumps are never included in raised messages or logs.
- Command examples: documentation must use placeholder names only. No command example may include a real key or encourage copying secrets into logs.
- Temporary files: any credentials file, if used, must live outside the repo and daily memory, have restrictive permissions, and be excluded from backups/log collection unless explicitly approved.

Recommended B2 application key capability:

- bucket-scoped;
- list/read/write file capability;
- no delete capability if available;
- Object Lock compatible;
- shortest practical key lifetime compatible with operations;
- separate key for ACE, not shared with other systems.

## 12. Tamper detection across local vs remote

Detected cases:

1. Local event row or hash changed after remote attestation: local canonical object body no longer matches remote object → `external_attestation_mismatch`.
2. Local post-cutover event deleted: local sequence gap/local chain verifier fails, or exact-set remote comparison finds `external_attestation_remote_extra`.
3. Local DB rewritten and rehashed with fewer rows: exact-set comparison finds remote extras under the prefix.
4. Local post-cutover event inserted without remote sync: local chain may pass but external attestation reports missing object.
5. Remote object changed after upload: remote object differs from locally expected record or violates version policy → mismatch/conflicting version.
6. Remote object deleted: missing object → failure/pending depending policy.
7. Remote object truncated/partially uploaded: byte-for-byte comparison and JSON/schema validation fail.
8. Foreign ACE instance writes into the prefix: namespace collision / remote extra failure.
9. Pre-cutover defect: remains governed by disclosure, not item 2.

Not fully solved without stronger operator controls:

- A local actor with DB write access plus B2 credentials that can bypass Object Lock or delete locked versions at the account level can attack both local and remote records.
- This is why credential separation, no-delete keys, Object Lock/versioning, filesystem permissions, dedicated OS account, and OpenClaw exec allowlist/wrappers remain part of activation hardening.

## 13. Operator-owned setup steps

Operator must perform or explicitly authorize:

1. Create or select Backblaze B2 account.
2. Create a dedicated production bucket named according to the bucket naming rule.
3. Enable Object Lock / retention and version visibility before first production attestation object is written.
4. Create a unique production `instance_id` for the live ACE DB.
5. Create bucket-scoped ACE application key.
6. Prefer permissions: list/read/write, no delete if supported.
7. Configure secrets outside repo and memory:
   - `ACE_B2_KEY_ID`
   - `ACE_B2_APPLICATION_KEY`
   - `ACE_B2_BUCKET_NAME`
   - optional `ACE_B2_BUCKET_ID`
   - `ACE_B2_INSTANCE_ID`
   - optional `ACE_B2_OBJECT_PREFIX`
8. Confirm credentials are not pasted into chat, repo, `MEMORY.md`, shell history, process logs, CI logs, or crash reports.
9. Run a dry-run verification command after implementation.
10. Run first explicit sync command after implementation.
11. Run `ace audit verify` and confirm external attestation is green, including exact-set comparison and version policy.
12. Preserve bucket Object Lock/versioning settings as part of ACE activation controls.

## 14. Test design

Required unit tests with fake B2 client:

- manifest generation includes only post-cutover rows;
- manifest generation excludes full payloads;
- manifest order is by `event_sequence`, not `created_at`;
- missing cutover fails loudly;
- duplicate/gapped/null post-cutover sequence fails before manifest;
- sync uploads missing immutable objects;
- sync refuses to overwrite existing different object;
- sync treats existing matching locked object as success/idempotent;
- sync performs post-upload readback verification;
- sync fails on post-upload truncation or mismatch;
- audit external comparison passes when exact local/remote sets and contents match;
- audit external comparison fails on missing object;
- audit external comparison fails on mismatched object;
- audit external comparison fails on remote extra objects, simulating local deletion/rewrite/shrink;
- audit external comparison fails on local truncation plus rehash attempt when old remote records remain;
- audit external comparison reports not configured without leaking secret values;
- B2 unreachable during sync returns explicit failure and does not mutate local chain;
- B2 timeout/auth/API/rate-limit failures map to explicit statuses;
- B2 returning conflicting versions fails under the version policy;
- duplicate identical versions are handled according to policy and surfaced informationally;
- multi-instance collision under the same prefix fails with namespace collision;
- malformed object name/body under the prefix fails closed;
- partial upload recovery: later sync can upload/readback a correct object only if no conflicting locked version exists;
- listing pagination is followed until exhaustion;
- pagination failure/incomplete listing fails closed;
- unsupported schema/manifest generator version fails closed;
- no test uses real B2 credentials or network.

Integration test boundary:

- No live B2 integration test should run in default CI.
- Optional live test may be operator-run only with explicit credentials, a disposable bucket/prefix, Object Lock expectations documented, and log redaction verified.

## 15. Recommended implementation slices after Ja’rvontis/operator approval

Do not implement until Step 4 review is complete.

Proposed slices:

1. Manifest-only local generation, namespace derivation, and tests.
2. Fake-client exact-set external attestation comparison and `audit verify` surface, disabled/not_configured without credentials.
3. Fake-client sync with TOCTOU-safe post-upload readback, version policy, pagination, and conflict tests.
4. Backblaze B2 client wrapper behind the same interface, with no live network in default CI.
5. Optional operator-run live dry-run instructions and activation doc update.

Each slice should be one commit, pushed, CI green, and stopped for operator approval per the current cadence.

## 16. Recommendation

Use a hybrid, exact-set, Object-Locked design:

- canonical local post-cutover event chain remains SQLite;
- deterministic hash-only per-event records are mirrored to B2 as immutable object names under an instance-isolated prefix;
- Object Lock/versioning is mandatory for the full V1.1 re-tag claim;
- normal append does not block on B2 network I/O;
- explicit sync performs external writes by scanning all local post-cutover events;
- read-only audit lists the full remote prefix and compares exact local-vs-remote object set, content, namespace, schema, and version policy;
- credentials stay operator-owned and outside repo/memory/logs;
- audit is not green until remote records exactly match local post-cutover truth and no remote extras/conflicts exist.

This best balances ledger safety, operational reliability, and honest claims. It avoids putting network uncertainty inside SQLite append transactions while making external attestation a required green surface before ACE 1.0 can be honestly re-tagged.

## 17. Honest claim language

If mandatory B2 Object Lock/versioning, exact-set comparison, instance isolation, and version policy are implemented and verified, the allowed claim is:

> ACE has a tamper-evident append-only event chain from the V1.1 cutover forward, with hash-only post-cutover event attestations mirrored to an Object-Locked Backblaze B2 namespace and verified by exact local-vs-remote set comparison. Pre-cutover history is retained unchanged with disclosed legacy defects.

If Object Lock/versioning cannot be verified, the allowed downgraded claim is:

> ACE has local post-cutover tamper-evidence with best-effort external B2 mirroring. Remote mirror records are compared during audit, but the mirror is not independently protected against overwrite/delete by ACE-held credentials.

The downgraded claim is not sufficient for ACE 1.0 re-tag unless the operator explicitly accepts the weaker guarantee in writing.

## 18. Open questions for operator / Ja’rvontis

1. What retention duration should be used for B2 Object Lock?
2. Can Andrew’s Backblaze account create a bucket-scoped application key with list/read/write but no delete?
3. What exact production `instance_id` should be assigned to the live ACE DB?
4. Should optional checkpoint objects be included in V1.1 for performance, or deferred until event volume requires them?
5. What safety cap should audit use for maximum remote objects before requiring paginated/ranged verification optimization?
6. Who owns the first live B2 credential setup: Andrew manually, or a separate explicitly authorized guided setup session?
7. Should live B2 verification ever run in CI, or remain operator-run only?
