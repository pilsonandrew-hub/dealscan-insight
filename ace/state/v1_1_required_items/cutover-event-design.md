# ACE V1.1 Cutover Event Design

Status: design only; no implementation and no database writes in this slice.

Related scope anchor: `ace/state/v1_1_required_items/current-operator-instruction.md`

Related disclosure: `ace/state/v1_1_required_items/legacy-chain-defects.md`

## 1. Cutover event specification

### Event type name

Recommended event type: `ace.chain.cutover.v1_1`

Reasoning:

- `ace.chain.cutover` is readable, but too generic if a later V1.2/V2 cutover is needed.
- `ace.chain.cutover.v1_1` makes the governance boundary explicit in the event stream without requiring payload inspection.
- The event still belongs to the ACE infrastructure namespace, not to an item lifecycle namespace, because it governs the ledger itself rather than a work item.

### Payload fields

The cutover event payload should be a stable JSON object with sorted keys under the existing `compute_event_hash(...)` behavior.

Required payload fields:

- `cutover_version`: string, fixed value `v1.1`
- `cutover_timestamp`: UTC timestamp for the actual cutover append time
- `anchor_commit_hash`: full git SHA whose source code and docs define the cutover behavior
- `design_commit_hash`: full git SHA of this design document commit
- `legacy_disclosure_path`: `ace/state/v1_1_required_items/legacy-chain-defects.md`
- `legacy_diagnosis_path`: `ace/state/v1_1_required_items/slice-b1-chain-diagnosis-readonly.md`
- `governing_decision`: short text: `checkpoint-forward; do not rewrite pre-cutover history`
- `governing_decision_reference`: durable reference to the operator acceptance of B-disclose and authorization for B-cutover design
- `legacy_event_count`: count of rows in `events` before the cutover row is inserted
- `legacy_chain_head_event_id`: `event_id` of the last legacy row by append order immediately before cutover
- `legacy_chain_head_row_id`: integer `id` of that last legacy row
- `legacy_chain_head_hash`: stored `event_hash` of that last legacy row
- `legacy_known_defect_counts`: object containing the disclosed defect counts
  - `timestamp_id_inversions`: `163`
  - `backdated_item_created_events`: `4`
  - `concurrent_write_chain_breaks`: `2`
- `post_cutover_chain_policy`: object describing the forward rules
  - `event_sequence_scope`: `post_cutover_only`
  - `previous_event_hash_policy`: `v1_1_genesis_null_with_legacy_head_in_payload`
  - `pre_cutover_verification_policy`: `inventory_only_disclosed_defects`
  - `post_cutover_serialization`: `begin_immediate_required`
- `forbidden_claims_reference`: short reminder that ACE must not claim full-history tamper-evidence

### `event_sequence` assignment

Recommendation: the cutover event receives `event_sequence = 1` for the **post-cutover chain**, while pre-cutover events retain `NULL` in the V1.1 `event_sequence` column.

This creates a clean namespace:

- Pre-cutover rows: `event_sequence IS NULL`
- Cutover row: `event_sequence = 1`
- First normal post-cutover event: `event_sequence = 2`
- Later post-cutover events: strict increment by one inside the serialized append transaction

This does not break the pre-cutover chain because V1.1 no longer attempts to reinterpret or renumber legacy rows. Legacy rows remain unchanged except for schema expansion if needed.

### `previous_event_hash`

Recommendation: the cutover event should set `previous_event_hash = NULL` and include the legacy head information in payload fields.

Rationale:

- Referencing the legacy chain head in `previous_event_hash` would mathematically join the new chain to a known-defective historical chain and make post-cutover verification depend on legacy defects.
- A special sentinel in `previous_event_hash` would require custom hash rules and make the hash chain less transparent.
- `NULL` cleanly identifies the cutover event as the genesis event of the V1.1 post-cutover chain.
- The payload still preserves the legacy link by recording `legacy_chain_head_event_id`, `legacy_chain_head_row_id`, and `legacy_chain_head_hash`.

So the cutover event is both:

- a genesis row for the new deterministic chain, and
- an audited checkpoint that records exactly what legacy head it followed.

### `event_hash`

The cutover event hash should use the existing event hash calculation semantics over these values:

- `event_id`
- `item_id` (`NULL`; this is ledger-level, not item-level)
- `event_type` (`ace.chain.cutover.v1_1`)
- canonical `payload_json` with sorted keys
- `actor`
- `source`
- `session_id`
- `created_at`
- `previous_event_hash` (`NULL`)

B-append may add `event_sequence` to the persisted schema, but recommendation is **not** to include `event_sequence` in `event_hash` unless the whole hash function is explicitly versioned. Keeping the hash input stable avoids making old and new hash rows use incompatible formulas. The deterministic chain ordering comes from `event_sequence`, while hash integrity still covers row content and previous hash.

## 2. Chain boundary semantics

### Pre-cutover vs post-cutover detection

The audit verifier identifies the boundary by locating exactly one `events` row where:

- `event_type = 'ace.chain.cutover.v1_1'`
- `event_sequence = 1`
- `previous_event_hash IS NULL`
- payload `cutover_version = 'v1.1'`

Rows are classified as:

- Pre-cutover: row `id` is less than the cutover row id, regardless of whether legacy/B1-residue `event_sequence` values are present
- Cutover: the single `ace.chain.cutover.v1_1` row
- Post-cutover: row `id` is greater than or equal to the cutover row id and `event_sequence >= 1`, including the cutover row

If multiple cutover rows exist, no cutover row exists after B-cutover-execute, or rows after cutover have `NULL` sequence, audit must fail loudly. Pre-cutover B1-residue `event_sequence` values are inert legacy defects and must not be treated as post-cutover chain membership.

### Does `event_sequence` reset to 1 or continue high?

Recommendation: reset to `1` at cutover.

Why not continue from a high legacy count?

- Continuing from `legacy_event_count + 1` implies legacy rows have a reliable sequence namespace. They do not.
- Resetting to `1` communicates that V1.1 is a new deterministic chain segment.
- Queries can still order globally by `id` or `created_at`; `event_sequence` is specifically for V1.1+ tamper-evidence.

### Does post-cutover audit ignore pre-cutover events entirely?

Recommendation: post-cutover hash-chain audit should not verify pre-cutover hashes as part of pass/fail chain integrity.

Instead, audit should:

1. Verify the disclosure file exists.
2. Verify the cutover payload records the legacy head row and hash that existed at cutover.
3. Report pre-cutover history as `inventory_only_disclosed_defects`.
4. Verify the post-cutover chain strictly from `event_sequence = 1` forward.

This avoids pretending legacy history is clean while still making the boundary visible and accountable.

### Querying event history across the boundary

Event history queries should continue to return both pre-cutover and post-cutover events.

Recommended display behavior:

- Default chronological/item history remains by the existing user-facing order, unless a command explicitly requests ledger-chain order.
- Rows should include a boundary marker when output spans the cutover event.
- For operators, `ace show` / audit views should label:
  - `chain_segment=legacy-pre-v1.1` for pre-cutover rows
  - `chain_segment=v1.1-post-cutover` for cutover and later rows
- The cutover row should be visible as a normal event row, not hidden.

## 3. Migration approach

### Does `event_sequence` already exist?

Source code confirmation after B-revert:

- `ace/storage.py` no longer contains `event_sequence` logic.
- The committed source at `2e590e6` therefore treats `event_sequence` as removed from the implementation after reverting B1.

Live database observation during design:

- The live `ace/state/ace.db` still has an `event_sequence` column because prior B1/bootstrap touched the local state database.
- That live schema residue must be handled as legacy state during B-append. Code must not assume a clean database without the column.

### Do pre-cutover events get `event_sequence` values?

Recommendation: pre-cutover events should ideally have `event_sequence = NULL` under the final V1.1 design, but existing B1-residue values must **not** be cleared.

Migration should support both cases:

- Clean databases with no `event_sequence` column: add nullable `event_sequence INTEGER` and leave existing rows `NULL`.
- Databases already polluted by B1 with populated `event_sequence`: leave those pre-cutover values unchanged as inert legacy residue. Do not rewrite, renumber, or clear pre-cutover rows.

This follows the absolute checkpoint-forward rule: never mutate pre-cutover events for cosmetic cleanup. The verifier must identify post-cutover chain membership by the cutover row boundary, not by assuming every non-null `event_sequence` is post-cutover.

### Should the cutover event be appended before or after B-append serialization fix?

Recommendation: after B-append introduces serialized append behavior, but as the first event written through the new path.

Reasoning:

- The cutover row itself must be trustworthy under the new rules.
- If appended before the serialization fix, it could be subject to the same stale-head concurrency defect disclosed in legacy history.
- B-append should add the schema/serialization support, then append `ace.chain.cutover.v1_1` as `event_sequence = 1` in the same controlled implementation slice or an immediately subsequent cutover execution step.

Safe ordering:

1. B-append slice: implement nullable `event_sequence` support and serialized `BEGIN IMMEDIATE` append path.
2. B-append slice: add audit verifier support for legacy inventory plus strict post-cutover verification.
3. Stop and wait for operator approval.
4. B-cutover-execute slice: append the cutover event with `event_sequence = 1`, `previous_event_hash = NULL`; do not mutate pre-cutover rows, including B1-residue `event_sequence` values.
5. All later events get the next post-cutover `event_sequence` under the same serialized transaction.

## 4. Audit verifier behavior

### Post-cutover verifier

The new verifier should locate the cutover row first, then walk the post-cutover chain by:

```sql
SELECT *
FROM events
WHERE id >= :cutover_row_id
ORDER BY event_sequence ASC
```

Required checks:

- Exactly one cutover event at `event_sequence = 1`.
- Cutover event has `previous_event_hash IS NULL`.
- No gaps in post-cutover `event_sequence` from the cutover row forward.
- No duplicate post-cutover `event_sequence` values from the cutover row forward.
- Pre-cutover rows with non-null B1-residue `event_sequence` values are ignored by the post-cutover verifier and reported only through legacy inventory/disclosure.
- Each post-cutover row's `previous_event_hash` equals the prior post-cutover row's `event_hash`, except the cutover genesis row.
- Each post-cutover `event_hash` recomputes correctly.
- Any row with `id > cutover_row_id` and `event_sequence IS NULL` is an audit failure.

### Pre-cutover options

Option A — skip pre-cutover verification entirely, just inventory:

- Pros: cleanest honesty boundary; avoids normalizing known-defective history into a fake pass.
- Cons: weaker automated signal for legacy rows.

Option B — verify with known-defective allowances per disclosure:

- Pros: gives more detail about known issues.
- Cons: complex, fragile, and risks turning disclosed failures into an implied pass.

Option C — split audit into two named checks:

- `legacy_chain_inventory`: confirms disclosure/cutover references and reports known defects without pass-washing them.
- `post_cutover_event_hash_chain`: strict pass/fail for V1.1+ rows.

Recommendation: Option C.

This keeps the operator-visible audit honest:

- legacy is not silently ignored,
- legacy is not falsely passed,
- post-cutover chain has a crisp deterministic pass/fail gate.

## 5. Backwards compatibility

### Existing tests that expect all-event verification

Tests that create fresh databases with no legacy defects can still verify all rows because their only segment will be post-cutover or, in unit-test fixtures, a local no-cutover test chain.

But tests that assert `verify_event_hash_chain(...) == (True, None)` across all historical rows need to be split:

- Fresh DB tests: prove append/hash works in a clean isolated chain.
- Legacy/cutover tests: prove pre-cutover rows are inventoried and post-cutover rows verify.
- Tamper tests: tamper post-cutover payload and prove strict failure.

### Existing tools and `ace audit verify`

`ace audit verify` should remain the main operator entry point, but its output needs clearer fields.

Recommended fields:

- `audit.verify.legacy_chain_inventory=disclosed`
- `audit.verify.legacy_chain_disclosure=ace/state/v1_1_required_items/legacy-chain-defects.md`
- `audit.verify.cutover_event=ok`
- `audit.verify.cutover_event_id=<event_id>`
- `audit.verify.cutover_event_sequence=1`
- `audit.verify.post_cutover_event_hash_chain=ok|failed`
- Existing checks remain:
  - `audit.verify.evidence_consistency`
  - `audit.verify.governed_run_integrity`
  - `audit.verify.runtime_instance_integrity`

For compatibility, `audit.verify.event_hash_chain` can remain, but after cutover it should mean the post-cutover chain only and print an explanatory note:

`audit.verify.event_hash_chain_scope=post_cutover_only`

### Operator visibility

Audit reporting must make the cutover visible every time, not just when it fails.

Minimum operator-visible line:

`audit.verify.chain_boundary=v1.1_cutover event_id=<id> sequence=1 legacy_events=<count> legacy_policy=inventory_only_disclosed_defects`

## 6. Cutover event content (concrete draft)

Example payload shape with placeholder values:

```json
{
  "anchor_commit_hash": "<full SHA containing approved B-append implementation>",
  "cutover_timestamp": "2026-05-23T04:15:00Z",
  "cutover_version": "v1.1",
  "design_commit_hash": "<full SHA of this design document commit>",
  "forbidden_claims_reference": "Do not claim full-history tamper-evidence; approved claim is cutover-forward only.",
  "governing_decision": "checkpoint-forward; do not rewrite pre-cutover history",
  "governing_decision_reference": "Andrew accepted B-disclose and authorized B-cutover design on 2026-05-22/2026-05-23 Telegram direct session",
  "legacy_chain_head_event_id": "evt_38730c10645c448996f6371cc51a5976",
  "legacy_chain_head_hash": "3e062d573627eccb98724c66f6d72c61c4b6852ebf9e147ba58988c999d01a98",
  "legacy_chain_head_row_id": 176268,
  "legacy_diagnosis_path": "ace/state/v1_1_required_items/slice-b1-chain-diagnosis-readonly.md",
  "legacy_disclosure_path": "ace/state/v1_1_required_items/legacy-chain-defects.md",
  "legacy_event_count": 176268,
  "legacy_known_defect_counts": {
    "backdated_item_created_events": 4,
    "concurrent_write_chain_breaks": 2,
    "timestamp_id_inversions": 163
  },
  "post_cutover_chain_policy": {
    "event_sequence_scope": "post_cutover_only",
    "post_cutover_serialization": "begin_immediate_required",
    "pre_cutover_verification_policy": "inventory_only_disclosed_defects",
    "previous_event_hash_policy": "v1_1_genesis_null_with_legacy_head_in_payload"
  }
}
```

Example event row values:

```text
event_type: ace.chain.cutover.v1_1
item_id: NULL
actor: main
source: ace/storage.py
session_id: v1.1-cutover:<cutover_timestamp>
created_at: same UTC value as payload.cutover_timestamp
previous_event_hash: NULL
event_sequence: 1
event_hash: compute_event_hash(...) over the normal event hash fields
```

The concrete legacy head values above are examples from read-only observation during design, not authorized cutover values. Implementation must re-read the live legacy head inside the serialized cutover transaction immediately before appending the actual cutover event.

## 7. Open questions / decisions needed from operator

1. Approve or revise the recommended event type: `ace.chain.cutover.v1_1`.
2. Approve or reject the genesis policy: `previous_event_hash = NULL`, with legacy head recorded in payload.
3. Approve or reject resetting post-cutover `event_sequence` to `1` and leaving pre-cutover rows `NULL`.
4. Approve or reject clearing any B1-residue `event_sequence` values from pre-cutover rows during implementation.
5. Approve Option C audit behavior: legacy inventory/disclosure plus strict post-cutover verification.
6. Decide whether the actual cutover append may happen in the same implementation commit/slice as B-append, or must be a separate operator-approved execution after B-append tests pass.

Operator decisions recorded after this design draft:

- Decision 1: Approved event type `ace.chain.cutover.v1_1`.
- Decision 2: Approved genesis policy: `previous_event_hash = NULL`, with legacy head recorded in payload.
- Decision 3: Approved resetting post-cutover `event_sequence` to `1` and leaving pre-cutover rows conceptually outside the V1.1 sequence namespace.
- Decision 4: Changed: do **not** clear B1-residue `event_sequence` values from pre-cutover rows. Leave them as inert documented legacy residue. The checkpoint-forward rule is absolute: never mutate pre-cutover events for convenient cleanup.
- Decision 5: Approved Option C audit behavior: `legacy_chain_inventory` plus strict `post_cutover_event_hash_chain`.
- Decision 6: Changed: B-append and B-cutover-execute must be separate slices. B-append lands schema/serialization/audit code and tests only. B-cutover-execute appends the one-time cutover event only after separate operator approval.
