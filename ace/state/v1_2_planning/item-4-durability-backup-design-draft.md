> Draft design from unauthorized V1.1 write. Reviewed by Ja’rvontis with FAIL verdict and five blockers. To be revised and re-approved in V1.2 planning. Not authorized for V1.1 implementation.

# ACE V1.1 Item 4 — Durability Backup Design

Status: design draft for operator / Ja'rvontis review. No implementation is authorized by this document.

Scope: durable backup for ACE state after V1.1 external attestation activation.

## 1. Goal

Add a governed, reproducible backup path for ACE local state so the post-cutover ledger, operator-scope artifacts, breach logs, and activation evidence can survive local disk loss without overstating the trust claim.

The backup layer must preserve the current V1.1 truth boundary:

> ACE has tamper-evident append-only event chain from V1.1 cutover forward, externally attested in Backblaze B2. Pre-cutover history is retained unchanged with disclosed legacy defects.

Backups are for durability and recovery. They are not a replacement for the B2 hash attestation proof and must not become a second mutable source of truth.

## 2. Non-goals

This item does not:

- rewrite or repair pre-cutover history;
- alter the V1.1 cutover event;
- change the external attestation object schema or prefix;
- store B2 application keys or secrets in git, MEMORY.md, daily memory, logs, or backup manifests;
- implement multi-node / distributed ACE;
- claim high availability;
- start ACE 1.0 re-tagging;
- modify DealerScope product code.

## 3. Backup inputs

Minimum backup set:

- `ace/state/ace.db`
- `ace/state/v1_1_required_items/`
- `ace/state/breach-log/`
- any committed activation checklist artifact created for V1.1 closure

Explicit exclusions:

- credential env files, including `/tmp/ace_b2_restricted_env`;
- OpenClaw config or session secrets;
- untracked scratch DBs such as `unused.db` unless separately classified and approved;
- pycache, temporary logs, and process samples.

## 4. Backup artifact format

Recommended artifact family:

```text
ace-backups/v1_1/andrew-prod/snapshot_<utc_timestamp>__seq_<max_event_sequence>__<short_head_sha>.tar.zst
ace-backups/v1_1/andrew-prod/snapshot_<utc_timestamp>__seq_<max_event_sequence>__<short_head_sha>.manifest.json
ace-backups/v1_1/andrew-prod/snapshot_<utc_timestamp>__seq_<max_event_sequence>__<short_head_sha>.sha256
```

Manifest fields:

- `schema_version`: `ace-backup-manifest-v1`
- `instance_id`
- `created_at_utc`
- `git_head`
- `cutover_event_id`
- `max_event_sequence`
- `event_hash_at_max_sequence`
- `backup_inputs`
- `excluded_paths`
- `archive_sha256`
- `manifest_generator_version`
- `external_attestation_status_at_backup`: last observed audit/status summary, not a substitute for re-verification

The manifest must be deterministic except for creation timestamp and artifact names.

## 5. Local consistency rule

Before creating any backup artifact, the script must run local read-only validation:

1. `legacy_chain_inventory=ok`
2. `event_hash_chain=ok`
3. `post_cutover_event_hash_chain=ok`
4. `evidence_consistency=ok`
5. `governed_run_integrity=ok`
6. `runtime_instance_integrity=ok`

External attestation should be checked when B2 credentials are configured. If not configured, backup may still be created only with manifest field `external_attestation_status_at_backup=not_configured`; it must not claim activation-grade external durability.

## 6. Write destination

Preferred destination: same dedicated Backblaze bucket family, under a separate backup prefix from attestation:

```text
ace/v1_1/backups/andrew-prod/
```

The backup prefix must be distinct from:

```text
ace/v1_1/attestation/...
```

Rationale: attestation objects are small immutable hash proofs; backup archives are larger recovery artifacts. Mixing the two weakens audit clarity.

## 7. Credential policy

The backup writer must use a separate restricted key from the attestation writer if Backblaze permissions allow it.

Required properties:

- bucket-scoped;
- prefix-scoped when possible;
- read/list/write allowed for backup prefix;
- delete not allowed where Backblaze supports that restriction;
- no master/admin key use;
- no credential creation by the bot without explicit operator authorization.

If the operator chooses to reuse an existing restricted key, that choice must be recorded in an operator-approved artifact without recording the secret.

## 8. Restore verification

A backup is not considered valid until a restore verification path exists.

Minimum restore proof:

1. unpack archive into a temporary directory;
2. open restored `ace.db` read-only;
3. verify local six-check audit on restored DB;
4. confirm restored max `event_sequence`, cutover id, and max event hash match manifest;
5. if B2 credentials are configured, confirm restored DB's external attestation status is OK against the existing attestation prefix;
6. produce a restore-proof JSON artifact outside the archive.

The restore proof must not write to production ACE state.

## 9. CLI shape

Proposed commands:

```bash
python3 -m ace.ace backup create --db ace/state/ace.db --out /tmp/ace-backup-proof
python3 -m ace.ace backup verify --manifest <manifest.json> --archive <archive.tar.zst>
python3 -m ace.ace backup restore-proof --manifest <manifest.json> --archive <archive.tar.zst> --workdir /tmp/ace-restore-proof
```

External upload should be explicit, not hidden inside `backup create`, unless operator approves the destination and credential path:

```bash
python3 -m ace.ace backup upload --manifest <manifest.json> --archive <archive.tar.zst> --backend b2
```

## 10. Failure behavior

Fail closed on:

- local audit failure;
- backup input missing;
- manifest/archive hash mismatch;
- missing or malformed manifest fields;
- restored DB audit failure;
- external upload auth failure;
- external destination prefix collision;
- using a master/admin credential when restricted key is required.

Partial local artifacts may remain in the operator-selected output directory for inspection, but production state must not be mutated by failed backup creation.

## 11. Tests required before implementation commit

Required fake-client/unit coverage:

- manifest includes cutover id, max event sequence, and max event hash;
- backup refuses local audit failure;
- backup excludes credential files and scratch DBs;
- archive hash mismatch fails verification;
- restore-proof runs against temporary restored DB only;
- upload uses backup prefix, never attestation prefix;
- upload rejects remote extras/collisions under backup manifest name;
- missing B2 config returns not-configured exit code without local mutation.

## 12. Activation boundary

This backup design is not activation by itself.

Activation requires, in order:

1. operator / Ja'rvontis approval of this design;
2. implementation slice with tests;
3. local full ACE suite green;
4. commit and push;
5. CI green;
6. live backup create/upload/restore-proof with explicit operator approval for external upload;
7. activation checklist artifact updated;
8. only then consider ACE 1.0 re-tag approval.
