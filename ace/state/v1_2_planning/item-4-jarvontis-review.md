# Ja’rvontis Review — Item 4 Durability Backup Design

Source design under review: `ace/state/v1_2_planning/item-4-durability-backup-design-draft.md`

Verdict: **FAIL**

This review preserves the Ja’rvontis finding that the unauthorized item-4 durability backup design is not approved for V1.1 implementation. The design may live in V1.2 planning, but it requires revision and re-approval before any implementation work.

## Summary

The item-4 design is directionally useful, but it is not implementation-ready. The core problem is that it describes a durability backup path while leaving several operator-safety, credential-boundary, and restore-proof hazards under-specified. Because the document was created without operator approval after item 2 completion, the review also confirms why operator gating was required before design work continued.

## Blocking Findings

### Blocker 1 — Separate restricted key hedge

The design says the backup writer “must use a separate restricted key from the attestation writer if Backblaze permissions allow it.” The hedge weakens the security boundary.

For a durability backup path, the attestation key and backup key must be separate operational authorities. The attestation key protects post-cutover hash proof objects. The backup key writes larger recovery artifacts. Reusing a key collapses two different trust domains and makes it harder to reason about blast radius if either path is compromised.

Required correction:

- Remove “if Backblaze permissions allow it.”
- Require a separate restricted key for backup operations.
- If Backblaze cannot express the desired separation, implementation must stop and escalate to the operator rather than silently degrading.

### Blocker 2 — Key reuse escape hatch

The design allows: “If the operator chooses to reuse an existing restricted key, that choice must be recorded…” This is an escape hatch that undermines the previous credential boundary.

Operator approval can authorize scope, but the design should not normalize credential reuse for a backup system that is explicitly meant to improve durability without weakening attestation integrity. Recording key reuse does not make the security boundary safe.

Required correction:

- Delete the key reuse allowance.
- Replace it with a fail-closed requirement: no backup external upload is allowed unless a distinct backup-scoped restricted key is configured.
- Allow local-only backup creation without B2 upload if the backup key is not configured, provided output truthfully reports `backup_upload=not_configured`.

### Blocker 3 — B2 configured-but-failing case

The design says external attestation should be checked when B2 credentials are configured, and if not configured the backup may still be created with a not-configured marker. It does not clearly distinguish not-configured from configured-but-failing.

That distinction matters. A missing optional credential can be an operator choice. A configured B2 path that fails is a live integrity/durability warning. Backup creation must not proceed as activation-grade when the configured external proof path is failing.

Required correction:

- If B2 attestation credentials are not configured, local backup may be created only with explicit `external_attestation_status_at_backup=not_configured`.
- If B2 attestation credentials are configured but status/audit fails, backup creation must fail closed unless the operator explicitly authorizes a degraded local-only diagnostic artifact.
- The CLI output and manifest must distinguish `not_configured`, `failed`, and `ok`.

### Blocker 4 — Restore-proof production overwrite guard

The design says restore proof must not write to production ACE state, but it does not specify a concrete guard that prevents production overwrite.

Restore logic is dangerous because it touches an archive containing production state. A single mistaken default path could overwrite the live ACE DB or governed artifacts. The design needs explicit path refusal rules before implementation.

Required correction:

- `backup restore-proof` must require a caller-supplied temporary workdir.
- It must refuse workdirs under `ace/state/` or any path equal to, parent of, or child of the production DB path.
- It must refuse to run if the target workdir already contains `ace.db`, `v1_1_required_items`, `breach-log`, or an existing restore marker unless a separate explicit cleanup flag is added in a future approved design.
- Tests must prove production state is not modified.

### Blocker 5 — Missing backup-create no-write test

The test list includes failure cases, but it does not require a direct proof that `backup create` performs no production-state writes.

The backup feature must be read-only with respect to production ACE state. Without an explicit no-write test, a future implementation could accidentally append audit events, mutate metadata, or touch the live database while creating a backup.

Required correction:

- Add a required test that records production DB file hash / event count / max event sequence before `backup create`, runs backup creation, and proves those values are unchanged afterward.
- Add a failure-path variant proving failed backup creation also leaves production state unchanged.

## Non-blocking Improvements

1. Add a short threat model section distinguishing disk-loss recovery, local tamper detection, remote attestation integrity, and credential compromise. The current design mixes these concerns but does not label them explicitly.
2. Define retention expectations for backup artifacts. “Keep all versions” is appropriate for attestation, but backup archives may need retention policy, storage cost review, and manual deletion governance.
3. Add compression/tooling fallback guidance. `tar.zst` is good, but implementation should fail clearly if `zstd` is unavailable rather than silently switching formats.
4. Define maximum backup size reporting. The manifest should include archive size and uncompressed input size so operator review can detect unexpected scope expansion.
5. Add a deterministic path allowlist for backup inputs instead of relying only on exclusions. Explicit include beats broad copy plus exclude for safety.
6. Add a human-readable restore summary artifact in addition to machine JSON so an operator can quickly inspect what was proven.
7. Add a future-work note for scheduled backups, but keep scheduling out of the first implementation slice to avoid mixing backup mechanics with automation policy.

## Confirmations — What The Design Got Right

1. Correctly treats backups as durability/recovery artifacts, not as a replacement for B2 hash attestation.
2. Correctly preserves the V1.1 truth boundary: post-cutover tamper evidence only, with pre-cutover defects disclosed rather than repaired.
3. Correctly excludes credentials and secret-bearing files from backup artifacts.
4. Correctly separates backup prefix from attestation prefix, preserving audit clarity.
5. Correctly requires local six-check audit before backup creation.
6. Correctly requires restore verification before considering a backup valid.
7. Correctly refuses to use master/admin credentials in the intended design direction.
8. Correctly delays ACE 1.0 re-tagging until backup implementation, proof, CI, activation checklist, and operator approval are complete.

## Recommended Patches

### Patch 1 — Remove separate-key hedge

```diff
--- a/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
+++ b/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
@@
-The backup writer must use a separate restricted key from the attestation writer if Backblaze permissions allow it.
+The backup writer must use a separate restricted key from the attestation writer.
+
+If Backblaze cannot provide a distinct restricted backup key with the required boundary, external backup upload is not authorized. The implementation must stop and escalate to the operator rather than silently degrading or reusing the attestation key.
```

### Patch 2 — Delete key reuse escape hatch

```diff
--- a/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
+++ b/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
@@
-If the operator chooses to reuse an existing restricted key, that choice must be recorded in an operator-approved artifact without recording the secret.
+Key reuse between attestation and backup upload is not allowed. Local-only backup creation may proceed without a configured backup upload key only when output and manifest truthfully report `backup_upload=not_configured`.
```

### Patch 3 — Distinguish not-configured from configured-but-failing

```diff
--- a/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
+++ b/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
@@
-External attestation should be checked when B2 credentials are configured. If not configured, backup may still be created only with manifest field `external_attestation_status_at_backup=not_configured`; it must not claim activation-grade external durability.
+External attestation should be checked when B2 credentials are configured.
+
+If B2 attestation credentials are not configured, backup may still be created only with manifest field `external_attestation_status_at_backup=not_configured`; it must not claim activation-grade external durability.
+
+If B2 attestation credentials are configured but verification fails, backup creation must fail closed unless the operator explicitly authorizes a degraded local-only diagnostic artifact. CLI output and manifest state must distinguish `ok`, `not_configured`, and `failed`.
```

### Patch 4 — Add restore-proof production overwrite guard

```diff
--- a/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
+++ b/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
@@
-The restore proof must not write to production ACE state.
+The restore proof must not write to production ACE state.
+
+`backup restore-proof` must require an explicit temporary workdir and refuse any workdir under `ace/state/`, equal to the production DB path, parent of the production DB path, or child of the production DB path. It must also refuse a workdir that already contains `ace.db`, `v1_1_required_items`, `breach-log`, or a previous restore marker unless a future approved design adds an explicit cleanup flag.
```

### Patch 5 — Add backup-create no-write tests

```diff
--- a/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
+++ b/ace/state/v1_2_planning/item-4-durability-backup-design-draft.md
@@
 - missing B2 config returns not-configured exit code without local mutation.
+- backup create leaves production ACE state unchanged: DB file hash, event count, and max event sequence must match before and after successful backup creation.
+- failed backup create leaves production ACE state unchanged: DB file hash, event count, and max event sequence must match before and after a forced failure.
```

## Approval Boundary

This review does not authorize implementation. The item-4 design must be revised in V1.2 planning, re-reviewed, and explicitly approved before any backup implementation slice begins.
