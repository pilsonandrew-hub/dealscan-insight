# ACE V1.1 Honest Claim Language

Status: Slice I6 source of truth for ACE V1.1 public/operator-facing claims. README and other docs must align with this file.

## 1. Full claim language — external attestation fully activated

Use this only when all local audit checks are green and `ace audit verify` reports `audit.verify.external_attestation=ok` against the production Backblaze B2 namespace.

Approved full claim:

> ACE V1.1 has a tamper-evident append-only event chain from the V1.1 cutover forward. Post-cutover event hashes are independently mirrored to a dedicated private Backblaze B2 bucket with Object Lock/versioning controls, and `ace audit verify` compares local post-cutover chain truth against the external B2 attestation set. Pre-cutover history is retained unchanged with disclosed legacy defects.

Short form:

> ACE V1.1 provides post-cutover tamper evidence with external Backblaze B2 hash attestation. Pre-cutover history is retained with disclosed defects.

Operational proof wording:

> The activation-grade proof is `ace audit verify` showing local legacy inventory, event hash chain, post-cutover event hash chain, evidence consistency, governed run integrity, runtime instance integrity, and external attestation all green, including `audit.verify.external_attestation=ok`.

## 2. Downgraded claim language — external attestation unavailable or unverified

Use this if any of the following is true:

- B2 environment is not configured.
- `ace attestation status` is not green.
- `ace audit verify` reports external attestation failed, not configured, or pending.
- B2 Object Lock/versioning/key restrictions are not verified.
- Remote exact-set comparison has not completed.

Approved downgraded claim:

> ACE V1.1 has local post-cutover tamper evidence, but external Backblaze B2 attestation is unavailable or unverified in the current environment. The local post-cutover chain may verify internally, but the external mirror is not activation-grade until `ace audit verify` reports `audit.verify.external_attestation=ok`. Pre-cutover history is retained unchanged with disclosed legacy defects.

Short downgraded form:

> ACE V1.1 is locally tamper-evident from cutover forward, but external attestation is not currently verified.

If B2 is best-effort only because Object Lock/versioning or no-delete credentials are not verified, use:

> ACE has local post-cutover tamper evidence with best-effort external B2 mirroring. Remote mirror records may be compared during audit, but the mirror is not independently protected against overwrite/delete by ACE-held credentials.

That downgraded best-effort claim is not sufficient for an honest ACE 1.0 activation/tag unless the operator explicitly accepts the weaker guarantee in writing.

## 3. Pre-cutover chain claim language

The authoritative pre-cutover claim is:

> Pre-cutover ACE history is retained unchanged with disclosed legacy defects. V1.1 does not claim full tamper evidence for pre-cutover history.

When more detail is needed, reference:

- `ace/state/v1_1_required_items/legacy-chain-defects.md`

Known disclosed defect classes include:

- timestamp/id ordering inversions;
- deliberately backdated proof events;
- concurrent-write chain breaks;
- inert B1-residue `event_sequence` values on legacy rows.

Forbidden pre-cutover claims:

- “ACE history is fully tamper-evident.”
- “All ACE history is append-only verified.”
- “Pre-cutover defects were repaired.”
- “The V1.1 cutover proves historical events before the cutover.”

## 4. Explicit non-claims

ACE V1.1 does **not** guarantee:

1. Full tamper evidence for pre-cutover history.
2. That pre-cutover defects were repaired, rewritten, or hidden.
3. That B2 is ACE’s source of truth.
4. That full event payloads are stored externally.
5. That remote B2 attestation proves anything if `audit.verify.external_attestation` is not green.
6. That a missing or unconfigured external attestation backend is equivalent to success.
7. That Object Lock protects against a human/account owner with sufficient Backblaze administrative authority.
8. That a local actor with both DB write access and broad B2 delete/governance-bypass credentials cannot attack both local and remote records.
9. That backup durability exists before a separately approved backup design/implementation is completed.
10. That ACE is distributed, highly available, multi-tenant, or protected against host compromise.
11. That runtime/supervisor proof equals external attestation proof.
12. That CI success alone proves live B2 attestation is active.
13. That external attestation setup stores or protects full private conversation content.
14. That an object prefix with extra, missing, mismatched, foreign, or conflicting records is safe to ignore.

## 5. Required wording for README/doc alignment

README and operator-facing docs should use this shape:

> ACE V1.1 establishes post-cutover tamper evidence through a serialized event sequence, local hash-chain verification, and optional activation-grade Backblaze B2 external hash attestation. The full external-attestation claim applies only when `ace audit verify` reports `audit.verify.external_attestation=ok`. Pre-cutover history is retained unchanged with disclosed legacy defects documented in `legacy-chain-defects.md`.

If the environment is not configured for B2, docs must say:

> In this environment, external attestation is not configured or not verified. Use the local-only/downgraded claim until B2 setup, sync, and audit verification are complete.

## 6. Operational status labels

Use these labels consistently:

- `full-external-attestation`: local audit green and external B2 attestation green.
- `local-only-tamper-evidence`: local post-cutover audit green, external attestation unavailable/unverified.
- `best-effort-remote-mirror`: remote B2 mirror exists but Object Lock/version/no-delete controls are not fully verified.
- `not-activation-grade`: any local audit failure, external mismatch, missing object, extra object, namespace collision, version conflict, or configured-but-failing B2 path.

## 7. Stop rule for claims

If the current evidence does not show `audit.verify.external_attestation=ok`, do not use the full claim. Use downgraded language and name the blocker plainly.
