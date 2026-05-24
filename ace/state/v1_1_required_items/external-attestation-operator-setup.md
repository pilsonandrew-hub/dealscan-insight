# ACE V1.1 External Attestation Operator Setup

Status: Slice I6 operator documentation. This guide activates the Backblaze B2 external attestation surface for ACE V1.1. Use placeholder names only. Do not paste real keys into this document, chat, shell history, logs, Git, memory, or CI output.

## 1. Activation goal

ACE V1.1 external attestation is active only when:

1. the local V1.1 post-cutover chain verifies;
2. a dedicated Backblaze B2 bucket stores one hash-only immutable attestation object per post-cutover event;
3. `ace attestation sync` converges the remote set;
4. `ace audit verify` reports `audit.verify.external_attestation=ok`.

Until all four are true, use the downgraded claim language in `honest-claim-language.md`.

## 2. B2 bucket creation requirements

Create a dedicated production bucket for ACE attestation.

Required settings:

- Private bucket.
- Object Lock enabled before the first production attestation object is written.
- Encryption enabled.
- File/version visibility available to the ACE audit path.
- Lifecycle/retention policy must not automatically delete attestation objects or versions needed for audit.
- Bucket is used only for ACE external attestation, not general backups or unrelated automation.

Recommended placeholder naming pattern:

```text
ace-attestation-<operator-or-org-slug>-<environment>
```

Examples using placeholders only:

```text
ace-attestation-example-prod
ace-attestation-example-test
```

Do not reuse a test bucket or prefix for the production ACE DB.

## 3. Application key creation requirements

Create a separate restricted application key for ACE attestation.

Required key policy:

- Bucket-scoped to the dedicated ACE attestation bucket.
- Separate from any Backblaze master key.
- Separate from any backup key.
- No delete capability.
- No governance-bypass capability.
- Capabilities limited to:
  - `listFiles`
  - `readFiles`
  - `writeFiles`
- Not shared with other systems.

If Backblaze cannot express a separate restricted no-delete key for this bucket, stop and escalate. Do not silently use a master key or broad key.

## 4. Environment variables

Configure these values outside the repo:

```text
ACE_B2_KEY_ID=<key-id-placeholder>
ACE_B2_APPLICATION_KEY=<application-key-placeholder>
ACE_B2_BUCKET=<bucket-name-placeholder>
ACE_B2_INSTANCE_ID=<stable-instance-id-placeholder>
ACE_B2_ENDPOINT=<endpoint-placeholder>
```

Notes:

- `ACE_B2_KEY_ID` is not the application secret, but it still should not be casually logged.
- `ACE_B2_APPLICATION_KEY` is secret and must never be stored in Git, memory, chat, shell history, or CI logs.
- `ACE_B2_BUCKET` names the dedicated private Object-Locked bucket.
- `ACE_B2_INSTANCE_ID` is stable for the lifetime of the production ACE DB and prevents namespace collisions.
- `ACE_B2_ENDPOINT` should point to the correct Backblaze region endpoint for the bucket.

If the runtime also supports optional object-prefix configuration, keep production and test prefixes separate and stable. Do not place two ACE DBs under the same production prefix.

## 5. Shell-history-safe setup patterns

Do not paste the application key directly into an `export` command or any command line.

That can persist in shell history, terminal scrollback, process capture, or logs.

Preferred patterns:

### Pattern A — operator-owned env file outside repo

Create the env file outside the repository and outside memory directories:

```bash
install -m 600 /dev/null /path/outside/repo/ace-b2-attestation.env
```

Open it in a trusted editor and enter placeholder-shaped lines like:

```text
ACE_B2_KEY_ID=<key-id-placeholder>
ACE_B2_APPLICATION_KEY=<application-key-placeholder>
ACE_B2_BUCKET=<bucket-name-placeholder>
ACE_B2_INSTANCE_ID=<stable-instance-id-placeholder>
ACE_B2_ENDPOINT=<endpoint-placeholder>
```

After editing:

```bash
chmod 600 /path/outside/repo/ace-b2-attestation.env
```

Load it without echoing values:

```bash
set -a
. /path/outside/repo/ace-b2-attestation.env
set +a
```

Do not commit this file. Do not place it under `/Users/andrewpilson/.openclaw/workspace`.

### Pattern B — secret manager or Keychain

Store the application key in a secret manager or macOS Keychain and have the launch/runtime wrapper retrieve it without printing it.

Requirements:

- no command output prints the secret;
- no debug mode echoes the secret;
- failures redact request headers, authorization tokens, signed URLs, and environment values.

### Pattern C — one-shot subshell without history expansion

If a one-shot test is unavoidable, disable history for the session and avoid pasting secrets into chat/logged prompts. Prefer an env file over this pattern.

## 6. launchd environment file integration

ACE launchd jobs must receive the B2 values without embedding secrets in the plist or repository.

Recommended approach:

1. Keep the restricted env file outside the repo with mode `0600`.
2. Have the launch wrapper source the env file before invoking ACE.
3. Ensure logs do not echo the env file contents.
4. Ensure any process/status collection does not dump environment values.
5. Restart or reload only through the approved operator path for the current slice.

Example wrapper shape using placeholders only:

```bash
#!/bin/zsh
set -euo pipefail
set -a
. /path/outside/repo/ace-b2-attestation.env
set +a
cd /path/to/workspace
exec python3 -m ace.ace --db ace/state/ace.db audit verify
```

The real path and restart action are operator-owned. Do not edit launchd configuration unless explicitly authorized.

## 7. Initial sync invocation

After B2 configuration is present in the runtime environment, run the explicit sync command from the workspace:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation sync --progress-every 500
```

Expected successful output includes:

```text
attestation.sync.progress=sync_start expected=<count> prefix=<prefix>
attestation.sync.progress=remote_initial count=<count>
attestation.sync=ok
attestation.sync.expected_count=<count>
attestation.sync.uploaded_count=<count>
attestation.sync.existing_count=<count>
attestation.sync.prefix=<prefix>
attestation.sync.cutover_event_id=<cutover-event-id>
```

If the command reports failure, do not retry in a tight loop. Use `external-attestation-troubleshooting.md`.

## 8. Verify status before audit

Run the read-only status command:

```bash
python3 -m ace.ace --db ace/state/ace.db attestation status
```

Expected green output:

```text
attestation.status=ok
attestation.status_detail=external_attestation=ok backend=b2 checked=<count> missing=0 extra=0 mismatched=0 conflicting_versions=0 cutover_event_id=<cutover-event-id> instance_id=<instance-id>
attestation.db_path=ace/state/ace.db
```

If status is `failed`, do not claim external attestation activation.

## 9. Verify `external_attestation=ok` in audit verify

Run:

```bash
python3 -m ace.ace --db ace/state/ace.db audit verify
```

External attestation is active only when audit output includes:

```text
audit.verify.external_attestation=ok
audit.verify.external_attestation_detail=external_attestation=ok backend=b2 checked=<count> missing=0 extra=0 mismatched=0 conflicting_versions=0 cutover_event_id=<cutover-event-id> instance_id=<instance-id>
```

The full audit must also keep local checks green:

```text
audit.verify.legacy_chain_inventory=ok
audit.verify.event_hash_chain=ok
audit.verify.post_cutover_event_hash_chain=ok
audit.verify.evidence_consistency=ok
audit.verify.governed_run_integrity=ok
audit.verify.runtime_instance_integrity=ok
```

## 10. Activation checklist

Before using the full V1.1 claim language:

- [ ] Dedicated private B2 bucket exists.
- [ ] Object Lock was enabled before first production attestation object.
- [ ] Encryption is enabled.
- [ ] Lifecycle/retention will not delete required objects/versions.
- [ ] Restricted bucket-scoped no-delete application key exists.
- [ ] No master key is used.
- [ ] Env values are configured outside repo/memory/chat/logs.
- [ ] launchd or runtime wrapper receives env values without echoing secrets.
- [ ] `ace attestation sync` has completed successfully.
- [ ] `ace attestation status` reports `attestation.status=ok`.
- [ ] `ace audit verify` reports `audit.verify.external_attestation=ok`.
- [ ] README and external descriptions align with `honest-claim-language.md`.

If any checkbox is false, use downgraded claim language.
