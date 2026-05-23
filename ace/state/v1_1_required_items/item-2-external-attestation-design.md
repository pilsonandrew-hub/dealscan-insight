# ACE V1.1 Item 2 — External Attestation Design

Status: design draft for Ja’rvontis/operator review. No implementation is authorized by this document.

Scope: V1.1 item 2, external audit attestation to Backblaze B2.

Governing boundary:

> ACE has tamper-evident append-only event chain from V1.1 cutover forward. Pre-cutover history is retained unchanged with disclosed legacy defects.

This design extends that post-cutover claim with independent external attestation. It does not rewrite, repair, or hide pre-cutover defects disclosed in `ace/state/v1_1_required_items/legacy-chain-defects.md`.

## 1. Goal

Add an external, independently retained attestation surface so `ace audit verify` can compare local post-cutover chain truth against a Backblaze B2 object that the bot cannot silently rewrite during normal operation.

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

Recommended object content is a newline-delimited JSON manifest containing one row per post-cutover event:

```json
{"schema_version":"ace-b2-attestation-v1","chain_id":"ace-v1.1-post-cutover","cutover_event_id":"evt_58b80e6282374bf2b1a8611963817aa2","event_sequence":1,"event_id":"...","event_hash":"...","previous_event_hash":null,"created_at":"..."}
```

Per-row fields:

- `schema_version`
- `chain_id`
- `cutover_event_id`
- `event_sequence`
- `event_id`
- `event_hash`
- `previous_event_hash`
- `created_at`

Rationale:

- `event_hash` commits to the canonical event hash payload already stored locally.
- `previous_event_hash` preserves chain linkage for remote-side review without exposing payloads.
- `event_sequence` makes order deterministic from cutover forward.
- `created_at` is metadata only; it is not ordering authority.

Optional manifest header object:

```json
{"schema_version":"ace-b2-attestation-v1","record_type":"manifest_header","chain_id":"ace-v1.1-post-cutover","cutover_event_id":"evt_58b80e6282374bf2b1a8611963817aa2","generated_at":"...","local_db_path_label":"ace/state/ace.db"}
```

The header may identify the local DB label but must not include credentials, host secrets, full payloads, or private conversation text.

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
- Emit deterministic manifest rows containing hashes only.
- Validate no NULL/duplicate/gapped post-cutover `event_sequence` before emitting.

### `backblaze.py`

- Own B2 API interaction behind a small interface.
- Load credentials only from environment variables or an operator-owned secrets mechanism.
- Upload/read attestation objects.
- Convert B2 errors into explicit ACE verification statuses.

Suggested environment variables:

- `ACE_B2_KEY_ID`
- `ACE_B2_APPLICATION_KEY`
- `ACE_B2_BUCKET_NAME`
- `ACE_B2_BUCKET_ID` optional but preferred after setup
- `ACE_B2_OBJECT_PREFIX`, default `ace/v1_1/attestation/`

No B2 secret is ever committed or remembered in `MEMORY.md`.

## 5. Object naming and rewrite prevention

Recommended object naming uses immutable chunk objects plus a mutable pointer only if the operator explicitly allows it.

Primary immutable object pattern:

```text
ace/v1_1/attestation/cutover_evt_58b80e6282374bf2b1a8611963817aa2/seq_000000000001__evt_<event_id>.json
```

Each object contains exactly one event hash record.

Why per-event immutable objects:

- B2 is object storage, not an append-only database.
- Re-uploading a monolithic manifest would create a rewrite-like behavior unless bucket Object Lock/versioning is configured and verified.
- Per-event object names make each event attestation stable and independently checkable.
- Existing objects can be treated as immutable: if the object exists, ACE must read and compare; it must not overwrite.

Optional aggregate checkpoint objects can be added later, but V1.1 should not depend on a mutable aggregate file for integrity.

Recommended local rule:

1. Before uploading an event attestation object, query B2 for object existence by exact name.
2. If absent, upload the object.
3. If present, download and compare exact content/hash.
4. If present but different, fail closed with `remote_attestation_mismatch`.
5. Never overwrite or delete B2 attestation objects from ACE.

Recommended operator-side B2 setting:

- Enable bucket Object Lock / retention if available for the account and bucket type.
- Use an application key that can upload/read/list but cannot delete if B2 supports restricting that capability sufficiently for the chosen bucket/key model.

If B2 application-key permissions cannot prevent overwrite/delete fully, the design still improves detection, but the honest claim must say “externally mirrored and compared,” not “cryptographically impossible for the bot to rewrite.”

## 6. When mirror happens

Recommendation: hybrid.

### Write-time enqueue / lightweight sync

On successful post-cutover `append_event` commit:

- Do not contact B2 inside the same SQLite transaction.
- After commit, queue or attempt attestation for the just-written post-cutover event.
- If B2 is unreachable, record local pending-attestation state without blocking the event append.

Reason: putting network I/O inside the event append transaction risks blocking ACE’s core ledger and creating partial-failure ambiguity.

### Audit-time reconciliation

`ace audit verify` should:

1. run local post-cutover chain verification first;
2. generate expected attestation records for all post-cutover events;
3. compare each expected record to B2;
4. optionally upload missing records only under a separate explicit command, not during read-only audit.

Audit must stay read-only by default. If a missing remote object is found, audit reports failure/pending status; it does not mutate B2 unless the operator runs an explicit attestation sync command.

### Explicit sync command

Add a command such as:

```bash
python3 -m ace.ace attestation sync --backend b2 --db ace/state/ace.db
```

This command performs external writes and therefore requires operator authorization and configured B2 credentials.

Recommended operational model:

- append path records local pending intent;
- scheduled or operator-run sync uploads pending immutable records;
- audit verify compares local vs remote and fails if remote is missing/mismatched.

This hybrid avoids slowing normal ACE writes while still making external verification mandatory for V1.1 closure.

## 7. Failure-mode handling

### B2 unreachable / timeout

- Append path: event append succeeds; attestation status becomes `pending` or remains absent for the event.
- Sync command: exits non-zero with `attestation_remote_unreachable`.
- Audit verify: local checks may pass, but external attestation check fails with a clear missing/unreachable status.

### B2 slow

- Use bounded request timeouts.
- Do not hold SQLite write transaction while waiting for B2.
- Retry only in explicit sync, with bounded backoff; no tight loops.

### B2 auth error

- Do not prompt for secrets in logs.
- Return `attestation_auth_failed`.
- Operator must fix environment/key configuration.

### B2 object missing

- Audit verify returns failure/pending: `external_attestation_missing event_sequence=N event_id=...`.
- Explicit sync may create it.

### B2 object exists and matches

- Verification passes for that event.

### B2 object exists and differs

- Fail closed: `external_attestation_mismatch event_sequence=N event_id=...`.
- Do not overwrite.
- Treat as possible local tamper, remote tamper, or naming collision; operator investigation required.

### Duplicate/conflicting remote object versions

If B2 versioning exposes multiple versions for the same object name:

- Verification should inspect the latest visible object at minimum.
- If Object Lock/versioning is part of operator setup, design can be tightened to require earliest version equals expected and no later conflicting version exists.
- Open question: whether V1.1 requires version-level verification or object-name exact latest verification is enough.

## 8. Verification logic for `ace audit verify`

Add a seventh audit surface only after implementation:

- `external_attestation=ok|failed|pending|not_configured`

Recommended semantics:

- `ok`: local post-cutover chain passes and every expected post-cutover attestation object exists remotely with exact matching content/hash.
- `failed`: remote object exists but differs, B2 auth fails, B2 API errors in a way that prevents trust, or object set is inconsistent.
- `pending`: one or more objects are missing but credentials/backend are otherwise reachable; this blocks ACE 1.0 re-tag until sync resolves it.
- `not_configured`: B2 credentials/bucket are not configured; this blocks V1.1 closure but should be distinguishable from tamper.

Important: `ace audit verify` must not silently skip external comparison once item 2 is active. If credentials are missing after activation, report `not_configured` and return a non-green overall audit.

Suggested CLI output:

```text
audit.verify.external_attestation=ok
audit.verify.external_attestation_detail=backend=b2 checked=123 missing=0 mismatched=0 cutover_event_id=evt_58b80e6282374bf2b1a8611963817aa2
```

## 9. Local state for pending attestation

Recommendation: add a local table only if implementation needs durable retry tracking.

Possible table:

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

This table is metadata about attestation attempts. It is not part of the event hash chain and does not replace remote B2 truth.

Design preference for first implementation: avoid adding this table unless necessary; compute expected records directly from events and let sync/audit be deterministic. Add the table later only for retry observability.

## 10. Credential management

Rules:

- B2 keys are operator-owned.
- B2 keys never go in repo files.
- B2 keys never go in `MEMORY.md` or daily memory.
- B2 keys never print in command output, test output, exceptions, logs, or audit detail.
- Tests use fake clients / dependency injection, not real B2.
- Live sync/verify with B2 requires operator-supplied environment variables or a separate approved secret store.

Recommended B2 application key capability:

- bucket-scoped;
- list/read/write file capability;
- no delete capability if available;
- shortest practical key lifetime compatible with operations;
- separate key for ACE, not shared with other systems.

## 11. Tamper detection across local vs remote

Detected cases:

1. Local event row or hash changed after remote attestation: local manifest record no longer matches remote object → `external_attestation_mismatch`.
2. Local post-cutover event deleted: local sequence gap/local chain verifier fails before external comparison.
3. Local post-cutover event inserted without remote sync: local chain may pass but external attestation reports missing object.
4. Remote object changed after upload: remote object differs from locally expected record → mismatch.
5. Remote object deleted: missing object → failure/pending depending policy.
6. Pre-cutover defect: remains governed by disclosure, not item 2.

Not fully solved without stronger operator controls:

- A local actor with both DB write access and B2 overwrite/delete credentials can rewrite both local and remote records.
- This is why credential separation, no-delete keys, B2 Object Lock/versioning, filesystem permissions, and OpenClaw exec allowlist/wrappers remain part of activation hardening.

## 12. Operator-owned setup steps

Operator must perform or explicitly authorize:

1. Create or select Backblaze B2 account.
2. Create dedicated bucket for ACE attestation.
3. Enable Object Lock / retention if available and acceptable.
4. Create bucket-scoped ACE application key.
5. Prefer permissions: list/read/write, no delete if supported.
6. Configure environment variables outside repo:
   - `ACE_B2_KEY_ID`
   - `ACE_B2_APPLICATION_KEY`
   - `ACE_B2_BUCKET_NAME`
   - optional `ACE_B2_BUCKET_ID`
   - optional `ACE_B2_OBJECT_PREFIX`
7. Confirm credentials are not pasted into chat, repo, `MEMORY.md`, shell history, or logs.
8. Run a dry-run verification command after implementation.
9. Run first explicit sync command after implementation.
10. Run `ace audit verify` and confirm external attestation is green.

## 13. Test design

Required unit tests with fake B2 client:

- manifest generation includes only post-cutover rows;
- manifest generation excludes full payloads;
- manifest order is by `event_sequence`, not `created_at`;
- missing cutover fails loudly;
- duplicate/gapped/null post-cutover sequence fails before manifest;
- sync uploads missing immutable objects;
- sync refuses to overwrite existing different object;
- sync treats existing matching object as success/idempotent;
- audit external comparison passes when all fake remote records match;
- audit external comparison fails on missing object;
- audit external comparison fails on mismatched object;
- audit external comparison reports not configured without leaking secret values;
- B2 timeout/auth/API failures map to explicit statuses;
- no test uses real B2 credentials or network.

Integration test boundary:

- No live B2 integration test should run in default CI.
- Optional live test may be operator-run only with explicit credentials and a disposable bucket/prefix.

## 14. Recommended implementation slices after Ja’rvontis/operator approval

Do not implement until Step 4 review is complete.

Proposed slices:

1. Manifest-only local generation and tests.
2. Fake-client external attestation comparison and `audit verify` surface, disabled/not_configured without credentials.
3. Backblaze B2 client wrapper and explicit `attestation sync` command with fake-client tests.
4. Optional live dry-run instructions and operator activation doc update.

Each slice should be one commit, pushed, CI green, and stopped for operator approval per the current cadence.

## 15. Recommendation

Use a hybrid design:

- canonical local post-cutover event chain remains SQLite;
- deterministic hash-only per-event records are mirrored to B2 as immutable object names;
- normal append does not block on B2 network I/O;
- explicit sync performs external writes;
- read-only audit verify compares expected local post-cutover records against B2 and is not green until remote records match;
- credentials stay operator-owned and outside repo/memory.

This best balances ledger safety, operational reliability, and honest claims. It avoids putting network uncertainty inside SQLite append transactions while making external attestation a required green surface before ACE 1.0 can be honestly re-tagged.

## 16. Open questions for operator / Ja’rvontis

1. Should V1.1 require Backblaze Object Lock/versioning before ACE 1.0 re-tag, or is bucket-scoped no-delete application key plus exact object comparison enough?
2. Should `ace audit verify` return process exit failure when B2 is `not_configured`, or only after item 2 is explicitly activated?
3. Should the first implementation include a local `event_attestations` retry table, or keep V1.1 simpler by deriving expected state from `events` every time?
4. Should attestation object names include only `event_sequence` + `event_id`, or also include `event_hash` to make object-name mismatch visually obvious?
5. Should sync upload one object per event only, or also a signed/checksummed checkpoint manifest for faster audit?
6. What exact B2 key permissions are available in Andrew’s Backblaze account for write-without-delete/overwrite prevention?
7. Who owns the first live B2 credential setup: Andrew manually, or a separate explicitly authorized guided setup session?
8. Should external attestation compare every post-cutover event every audit, or support checkpointed/ranged verification once the event count grows?
