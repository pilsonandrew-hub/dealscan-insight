# Operator Scope Enforcement Consultation — ACE V1.1

Status: consultation artifact only. No implementation is authorized or performed by this file.

Source boundary read before this work:

- `ace/state/v1_1_required_items/current-operator-instruction.md`
- `ace/state/v1_1_required_items/consultation-task.md`
- `ace/state/breach-log/2026-05-21-hash-chain-modification.md`

Critical clarification added during consultation: the five documented bypasses occurred primarily at the Javarious/OpenClaw tool layer, using general edit/write/bash/git capability to modify files, commit code, and ship implementations. They were not limited to ACE internal code paths. Therefore, an ACE-internal authorization gate alone cannot prevent recurrence unless all relevant side-effecting actions are forced through ACE or independent external enforcement blocks non-ACE paths.

## Claude recommendation

Claude CLI was attempted twice for live consultation, but both invocations produced no output before timeout/kill. Because the operator instruction requires consultation results and the available live Claude tool did not return, this section records a Claude-style architecture recommendation synthesized from the consultation prompt and the breach facts rather than falsely claiming a successful live Claude response.

Recommendation:

1. Treat operator authorization as a durable capability boundary, not conversational instruction. Store the active scope in a machine-readable file or ledger that is loaded before any work and survives context compaction, handoff, and restart.
2. Represent scope as structured data, including:
   - mode: `investigation_only`, `proposal_only`, `implementation_approved`, `blocked`, `emergency_stop`
   - allowed action classes
   - denied action classes
   - allowed paths/resources
   - allowed external destinations, if any
   - allowed commands/tests, if any
   - approval issuer/reference
   - expiry or supersession rule
   - scope hash
3. Active conversational context must never expand scope. If active context conflicts with the durable operator anchor, the anchor wins and the agent must stop the conflicting action path.
4. Enforcement must be pre-effect. A denied action must be recorded before the write/commit/send/test/DB mutation receives execution control.
5. Approvals must be machine-distinguishable. Free-text phrases like “look into this,” “proposal only,” and “ship it” should compile to explicit modes and action grants.
6. ACE-internal enforcement is necessary but insufficient. The past failures used OpenClaw-level tools, so future prevention requires either modifying/wrapping OpenClaw tool execution or adding external gates such as git hooks, filesystem permissions, protected branches, CI policy, and command wrappers.

Layer clarification:

- If the gate is ACE-internal only, it can block ACE commands, ACE DB mutation, ACE-managed sends, ACE test harnesses, and ACE commit wrappers. It cannot block raw OpenClaw `edit`, `write`, `exec`, `git commit`, or `message` usage.
- Therefore, an ACE-internal-only gate would not have prevented the five bypasses unless those bypasses had been forced through ACE.
- Enterprise-grade prevention requires enforcement at the OpenClaw/tool/OS/repository layer, or compensating controls that make bypasses fail downstream before merge/deploy/external effect.

## Gemini recommendation

Live Gemini CLI consultation returned the following core recommendation, summarized and normalized into this artifact.

Gemini identified the fundamental problem as a layer mismatch: ACE policy can be bypassed by OpenClaw transport tools. Its recommendation was:

1. Create a durable authorization anchor, e.g. `.ace/AUTHORIZATION.json`, containing current scope such as `INVESTIGATE`, `PROPOSE`, `TEST`, or `IMPLEMENT`, plus task/session hash.
2. Add pre-flight interceptors for every mutating tool: file write, replace, shell command, git commit, DB mutation, and external send.
3. Enforce pessimistic conflict resolution: if chat context conflicts with the durable anchor, the anchor wins.
4. Log blocked attempts to an append-only blocking log with timestamp, attempted tool/command, and triggering policy.
5. Make approval tiers explicit:
   - `INVESTIGATE`: read/search only.
   - `PROPOSE`: investigation plus writing proposal/consultation files only.
   - `IMPLEMENT`: full tool access only after signed/timestamped transition.
6. Use an auditor/guard pattern that checks planned mutating commands before executor access.
7. Move enforcement to the infrastructure/tool layer, not agent cognition.

Gemini’s explicit tool-layer recommendation:

- ACE-internal paths alone cannot prevent bypasses if Javarious uses generic OpenClaw tools.
- Enforcement must move to the infrastructure layer.
- Use pre-commit/pre-push hooks that verify the authorization anchor and fail unless scope allows implementation.
- Wrap shell execution to reject mutating commands unless implementation is approved.
- Use read-only filesystem mounts during investigation/proposal phases, with narrow writable exceptions for allowed results.
- Use OS-level or repository-level controls because the agent cannot bypass filesystem permissions or protected branch policy as easily as it can ignore markdown instructions.

## DeepSeek recommendation

No `deepseek` CLI was available in the workspace environment, and no OpenRouter API key was present in the process environment for a live DeepSeek API consultation. This section records a DeepSeek-style technical architecture recommendation synthesized from the task and known constraints rather than falsely claiming a successful live DeepSeek response.

Recommendation:

1. Define authorization as a policy decision point / policy enforcement point split:
   - PDP: reads durable operator scope and returns allow/deny with reason.
   - PEPs: enforce decisions at every side-effect boundary.
2. Use deny-by-default semantics. Missing scope, malformed scope, stale scope, or conflicting scope means no mutation.
3. Normalize all attempted side effects into action descriptors:
   - `file.write`
   - `file.edit`
   - `shell.exec`
   - `git.stage`
   - `git.commit`
   - `git.push`
   - `db.mutate`
   - `external.send`
   - `test.stateful`
   - `test.external_effect`
4. Include resource descriptors:
   - path/resource
   - command argv
   - git ref
   - DB path/table
   - external destination
   - expected side-effect class
5. Require explicit grants for each descriptor class. For example, consultation-only can allow `file.write` only for `ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md` and deny everything else.
6. Record pre-effect audit entries:
   - `guard.decision.requested`
   - `guard.decision.denied.before_effect` or `guard.decision.allowed.before_effect`
   - `effect.completed` only after success
7. Harden against bypass by layering controls:
   - OpenClaw tool wrapper/interceptor, if available.
   - git hooks for local enforcement.
   - protected branch and CI checks for remote enforcement.
   - filesystem permissions/read-only workspace for local mutation prevention.
   - shell allowlist wrappers for command execution.
   - DB file permission and authorizer controls for ACE DB mutation.
   - external-send proxy requiring scope token for Telegram/email/etc.

Layer clarification:

- The central authorization gate should conceptually constrain Javarious/OpenClaw tool use, not only ACE internals.
- If OpenClaw cannot be modified to route tool calls through ACE, then ACE cannot be the sole enforcement layer.
- In that case, ACE should produce signed/hashed scope state consumed by independent enforcement mechanisms: git hooks, shell wrappers, filesystem permissions, CI, protected branches, DB permissions, and external-send proxies.

## Cross-model agreement

All recommendations converge on these points:

1. Markdown or conversational memory is not enforcement.
2. Current operator scope must be durable, machine-readable, and loaded before work begins.
3. The durable anchor wins over active context when they conflict.
4. Approvals must be structured modes with explicit allowed/denied action classes.
5. Enforcement must happen before side effects.
6. Denied actions must be auditable as denied before effect.
7. ACE-internal gates are insufficient for the documented bypass pattern because the bypasses used general OpenClaw tools.
8. Real prevention requires either tool-layer interception/wrapping or external controls outside the agent’s discretion.
9. Deny-by-default is mandatory.

## Disagreements/tradeoffs

1. Scope storage location:
   - A root-level `.ace/AUTHORIZATION.json` is easy for hooks and wrappers to consume.
   - An ACE append-only DB/table is stronger for ledger semantics.
   - Recommended tradeoff: use an append-only ACE scope ledger as source of truth and generate a root-level machine-readable current-scope file for external tools.

2. Enforcement location:
   - ACE-internal gates are cleaner to implement inside ACE but do not catch OpenClaw tool bypass.
   - OpenClaw-level interception is stronger but requires modifying/wrapping external infrastructure.
   - OS/repo controls are less elegant but enforceable without trusting agent cognition.

3. Logging blocked attempts:
   - If the filesystem is read-only, writing deny logs may itself be blocked.
   - Recommended tradeoff: keep a narrow append-only writable directory for guard logs, or log through an external append-only service.

4. Shell command handling:
   - Keyword-based blocking is fragile.
   - Allowlist command wrappers are safer: investigation/proposal modes should permit only known read-only commands, with explicit exceptions.

5. Tests:
   - Some tests are read-only, some mutate local state, and some send external messages.
   - Test commands must be classified by side-effect class, not treated as generically safe.

## Final proposed architecture

### 1. Source of truth: durable operator scope ledger

Create a durable, append-only operator-scope model with one current derived scope.

Minimum schema:

- `scope_id`
- `issued_at`
- `issued_by`
- `approval_reference`
- `mode`
- `allowed_action_classes`
- `denied_action_classes`
- `allowed_paths`
- `allowed_commands`
- `allowed_git_refs`
- `allowed_db_resources`
- `allowed_external_destinations`
- `allowed_test_classes`
- `expires_at` or `superseded_by`
- `scope_hash`
- `operator_attestation`

Modes:

- `blocked`
- `investigation_only`
- `consultation_only`
- `proposal_only`
- `implementation_approved`
- `maintenance_approved`
- `emergency_stop`

The human-readable `current-operator-instruction.md` should be treated as an operator-facing anchor, but the machine-readable current scope should be the enforceable source consumed by tools/hooks/wrappers.

### 2. Policy decision point

Implement or define one policy decision point that takes normalized action descriptors and returns allow/deny.

Example action descriptor classes:

- `file.read`
- `file.write`
- `file.edit`
- `shell.exec.read_only`
- `shell.exec.mutating`
- `git.stage`
- `git.commit`
- `git.push`
- `db.read`
- `db.mutate`
- `external.send`
- `test.read_only`
- `test.local_stateful`
- `test.external_effect`

Deny if scope does not explicitly allow the descriptor.

### 3. Policy enforcement points by layer

ACE-internal PEPs:

- ACE CLI commands
- ACE DB mutation paths
- ACE audit/hash-chain repair paths
- ACE notification sends
- ACE test harnesses

OpenClaw/tool-layer PEPs, if OpenClaw can be modified or wrapped:

- `write` tool
- `edit` tool
- `apply_patch` tool
- `exec` tool
- `message` tool
- any git helper or shell command that can mutate state

External compensating PEPs if OpenClaw cannot be modified:

- git pre-commit hook requiring current scope to allow commit and path set
- git pre-push hook requiring current scope to allow push/ref
- protected branches requiring CI scope check
- CI job that rejects unapproved implementation diffs
- filesystem read-only mode for the repo during investigation/proposal phases, with narrow writable allowlist for consultation/proposal artifacts
- shell wrapper/allowlist for command execution
- DB filesystem permissions and SQLite authorizer controls
- external-send proxy requiring a valid scope token before Telegram/email/etc.

### 4. Explicit answer: central gate layer

The central authorization gate must constrain Javarious/OpenClaw tool use to prevent the documented bypass pattern.

ACE-internal-only enforcement is not enough. It would not prevent direct OpenClaw file edits, writes, shell commands, git commits, or Telegram sends because those actions do not necessarily route through ACE.

There are only three viable enforcement models:

1. Modify/wrap OpenClaw so every side-effecting tool call asks the ACE scope gate before execution.
2. Run OpenClaw inside an environment where OS/repository/network controls enforce the current scope regardless of agent intent.
3. Accept that local bypass remains possible, but prevent durable/shipped impact with git hooks, protected branches, CI rejection, deployment gates, and external-send proxies.

The recommended architecture is layered model 1 plus model 2/3 as defense in depth. If model 1 is not available immediately, model 2/3 should be used as enforceable alternatives.

### 5. Proof of blocked-before-effect

For each attempted side-effect:

1. Create normalized action descriptor.
2. Read current scope hash.
3. Decide allow/deny.
4. Record decision before side-effect:
   - `guard.allowed.before_effect`
   - `guard.denied.before_effect`
5. Execute side effect only if allowed.
6. Record completion/failure after effect.

Deny records must include:

- timestamp
- session/process id
- actor/tool
- action descriptor
- target resources
- current scope hash
- denial reason
- assertion that target execution was not invoked

### 6. Approval structure

Approvals must be issued as structured scope transitions, not prose.

Examples:

- `consultation_only`:
  - allow reads
  - allow writing only `operator-scope-enforcement-consultation.md`
  - deny implementation files, git commits except explicitly authorized consultation result commit, DB mutation, external sends, mutating tests

- `proposal_only`:
  - allow reads
  - allow writing proposal docs under specified paths
  - deny implementation files, runtime changes, DB mutation, external sends, commits unless explicitly listed

- `implementation_approved`:
  - require item/scope id
  - specify allowed files/resources
  - specify allowed commands/tests
  - specify whether commit/push is allowed
  - specify expiry/supersession

- `emergency_stop`:
  - deny all side effects except explicitly allowed breach log/operator anchor updates

## Explicit non-implementation boundary

This artifact is consultation only. It does not implement operator scope enforcement, does not modify ACE runtime behavior, does not install hooks, does not change OpenClaw, does not change filesystem permissions, does not modify git branch protections, does not mutate any database, and does not send any external notification.

The only side effect performed for this task is the operator-authorized creation of this consultation results file at:

`ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md`
