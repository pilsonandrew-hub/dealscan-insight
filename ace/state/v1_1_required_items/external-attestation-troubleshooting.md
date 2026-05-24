# ACE V1.1 External Attestation Troubleshooting

Status: Slice I6 runbook. This document covers external attestation failure modes from the V1.1 design. Do not paste real credentials into commands, logs, chat, memory, or issue comments.

## Standard diagnostic commands

Run from the workspace with the approved environment already loaded:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
python3 -m ace.ace --db ace/state/ace.db audit verify
```

For convergence repairs only:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation sync --progress-every 500
```

Use the failure-specific sections below before retrying. Do not run tight retry loops against B2.

## 1. `not_configured`

Symptom:

```text
attestation.status=failed
attestation.status_detail=external_attestation_not_configured: ...
audit.verify.external_attestation=failed
```

Likely cause:

- One or more required environment variables is missing.
- launchd/runtime wrapper did not source the env file.
- The command was run in a shell that does not have the B2 env loaded.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Confirm the operator-owned env file exists outside the repo.
2. Confirm it contains placeholder-shaped required names only in documentation, and real values only in the private env file.
3. Source the env file without echoing values.
4. Re-run `attestation status`.
5. If launchd is the runtime path, verify the wrapper sources the env file without logging it.

If resolution fails:

- Stop. Do not claim external attestation activation.
- Use downgraded claim language from `honest-claim-language.md`.

## 2. `auth_failure`

Symptom:

```text
external_attestation_auth_failed: ...
```

Likely cause:

- Wrong key ID/application key pair.
- Key does not apply to the bucket.
- Key was revoked or expired.
- Key capabilities are too narrow for required list/read/write operations.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Create or select a separate restricted bucket-scoped key.
2. Ensure capabilities include `listFiles`, `readFiles`, and `writeFiles` only.
3. Ensure no delete/governance-bypass capability is used.
4. Update the private env file outside the repo.
5. Re-run `attestation status`.

If resolution fails:

- Stop and escalate to the operator.
- Do not paste key values into chat or logs.

## 3. `remote_unreachable`

Symptom:

```text
external_attestation_remote_unreachable: ...
```

or sync exits non-zero after B2/network errors.

Likely cause:

- Backblaze API outage or regional endpoint issue.
- Local network/TLS/connectivity failure.
- Endpoint value points to the wrong region.
- Rate limiting or transient 5xx response.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Confirm general network access is available.
2. Confirm `ACE_B2_ENDPOINT` matches the bucket region.
3. Wait for transient provider/network failure to clear.
4. Retry with bounded spacing; do not tight-loop.
5. If sync was interrupted, run `attestation sync` once connectivity returns.

If resolution fails:

- Keep local audit results separate from external attestation.
- Use downgraded claim language until B2 is reachable and audit is green.

## 4. Missing objects

Symptom:

```text
external_attestation_missing event_sequence=<n> event_id=<event-id>
```

Likely cause:

- Local post-cutover event was appended after the last sync.
- Sync was interrupted after local append and before upload.
- Live runtime continued appending events while the exact-set sync target moved.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. If events are actively appending, quiesce writes using the approved runtime path.
2. Run:

   ```bash
   python3 -m ace.ace --db ace/state/ace.db attestation sync --progress-every 500
   ```

3. Re-run `attestation status`.
4. Re-run `audit verify`.

If resolution fails:

- Do not manually upload or edit objects.
- Preserve the first missing sequence/event ID and escalate.

## 5. Extra objects

Symptom:

```text
external_attestation_remote_extra file_name=<name>
```

or:

```text
remote attestation prefix contains unexpected objects
```

Likely cause:

- Wrong `ACE_B2_INSTANCE_ID` or object prefix points to another ACE DB.
- A stale/test object exists in the production prefix.
- Local DB was truncated or rewritten relative to remote history.
- Foreign process wrote into the prefix.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Verify the configured instance ID and bucket/prefix are the intended production values.
2. Confirm no test/dev DB shares the production namespace.
3. Do not delete remote objects as a first response; extras are evidence.
4. Investigate whether local state was truncated or rewritten.

If resolution fails:

- Stop. Treat as a possible integrity incident.
- Do not claim V1.1 full external attestation.

## 6. Mismatched content

Symptom:

```text
external_attestation_mismatch event_sequence=<n> event_id=<event-id>
```

or remote body/schema/record mismatch.

Likely cause:

- Local event row or hash changed after remote attestation.
- Remote object content differs from expected canonical JSON.
- Wrong namespace or cutover boundary.
- Partial/truncated remote object.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db audit verify
```

Resolution path:

1. Preserve the mismatch output exactly, excluding secrets.
2. Run local audit verify and check local post-cutover chain status.
3. Confirm instance ID and cutover ID are correct.
4. Do not overwrite the remote object.

If resolution fails:

- Stop. Treat as an integrity incident requiring operator review.

## 7. Version conflicts

Symptom:

```text
conflicting_versions=...
```

or:

```text
remote object has conflicting later version
```

Likely cause:

- Existing object was uploaded more than once with conflicting metadata/content.
- Object Lock/versioning exposed a later conflicting version.
- A non-ACE writer used the same object name.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Preserve the object name and event sequence.
2. Confirm the application key has no delete/governance-bypass capability.
3. Confirm no other automation writes to the bucket/prefix.
4. Do not delete versions or overwrite the object.

If resolution fails:

- Stop. Treat as an external attestation integrity incident.

## 8. Namespace collision

Symptom:

```text
external_attestation_namespace_collision file_name=<name>
```

Likely cause:

- Two ACE DBs share a bucket/prefix/instance ID.
- A remote object body contains the wrong instance ID, cutover event ID, chain ID, schema version, or naming grammar.
- Test/dev records were written into the production namespace.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Stop writes to the affected namespace.
2. Verify the production `ACE_B2_INSTANCE_ID` is stable and unique.
3. Verify test/dev uses a separate bucket or explicit non-production prefix.
4. Preserve foreign object details for review.

If resolution fails:

- Do not delete evidence.
- Escalate to the operator before any namespace migration.

## 9. Pagination failure

Symptom:

```text
external_attestation_listing_incomplete: ...
```

Likely cause:

- B2 list operation failed mid-pagination.
- Malformed continuation token or repeated/incomplete listing.
- API response did not include expected list fields.
- Provider/network failure during a multi-page list.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Wait and retry once with bounded spacing.
2. Confirm bucket endpoint and credentials.
3. If sync was running, do not assume convergence until status/audit passes.
4. Keep logs redacted; do not dump raw credentials or headers.

If resolution fails:

- Treat the remote set as unverified.
- Use downgraded claim language.

## 10. `upload_unverified`

Symptom:

```text
external_attestation_upload_unverified
```

or sync reports post-upload readback/visibility failure.

Likely cause:

- Read-after-write visibility delay exceeded the bounded retry window.
- B2 upload accepted but object could not be read/listed for verification.
- Uploaded object body did not match canonical expected content.
- Version policy could not be proven after upload.

Diagnostic command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Resolution path:

1. Wait for bounded eventual consistency delay.
2. Re-run `attestation status`.
3. If missing only, re-run `attestation sync` once.
4. If mismatch/conflict appears, stop and treat as integrity issue.

If resolution fails:

- Do not manually overwrite remote objects.
- Keep audit non-green and escalate.

## Final rule

Only this state is activation-grade:

```text
audit.verify.external_attestation=ok
```

with local audit checks also green. Any other external attestation status requires downgraded claim language.
