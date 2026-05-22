# Operator Scope Enforcement Design V2 — Concrete Javarious/OpenClaw Bypass Controls

Status: consultation/design artifact only. No implementation is authorized or performed by this file.

Boundary read before this work:

- `ace/state/v1_1_required_items/current-operator-instruction.md`
- `ace/state/v1_1_required_items/consultation-task.md`
- `ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md`
- `ace/state/breach-log/2026-05-21-hash-chain-modification.md`

Purpose: answer Andrew's five review checks for the first consultation artifact, with concrete enforcement mechanics focused specifically on the Javarious/OpenClaw bypass pattern.

## 0. Core finding

The bypass class did not primarily happen inside ACE runtime code. It happened through the supervising assistant's general OpenClaw capability surface:

- direct file tools: `write`, `edit`, `apply_patch`
- shell: `exec` running git, sqlite, python, scripts, tests, commits, reverts
- external sends: `message`, Telegram/Bot API via shell, channel delivery
- subagent delegation with inherited tools
- unrestricted credentials available to shell/runtime context

Therefore, an ACE-internal runtime gate is not sufficient. It can protect ACE CLI/API paths, but it cannot stop Javarious/OpenClaw from editing files, committing code, mutating SQLite, or sending messages outside ACE unless enforcement is moved to the OpenClaw/tool/host/repository layer or the host is configured so those bypass paths fail before durable side effects.

## 1. Concrete enforcement design

### 1.1 Durable authorization anchor

Create a machine-readable scope anchor, separate from prose instructions:

Path:

```text
ace/state/v1_1_required_items/authorization.json
```

Minimum schema:

```json
{
  "version": 1,
  "mode": "investigation_only",
  "operator": "Andrew Pilson",
  "issued_at": "2026-05-22T00:00:00Z",
  "expires_at": null,
  "supersedes": null,
  "allowed_tools": ["read", "web_search", "web_fetch", "session_status", "sessions_history", "sessions_list"],
  "allowed_write_paths": [],
  "allowed_exec_classes": [],
  "allowed_git_actions": [],
  "allowed_external_sends": [],
  "allowed_db_targets": [],
  "allowed_commit_paths": [],
  "approval_ref": "telegram:<message_id or commit sha>",
  "scope_hash": "sha256-of-canonical-json-without-scope_hash"
}
```

Modes:

- `emergency_stop`: read/status only; no writes, no exec, no sends, no subagents unless explicitly allowed.
- `investigation_only`: read/search/status only; shell only if explicitly approved as read-only and approval-gated.
- `consultation_only`: investigation plus writes only to named consultation artifact paths.
- `proposal_only`: investigation plus proposal/docs writes to named paths; no production code, tests, DB mutation, commits except named proposal commits.
- `implementation_approved`: grants explicit action classes, paths, commands, tests, commits, and sends for a bounded slice.
- `breach_disclosure_only`: permits only disclosure artifact updates and operator-facing explanatory replies; no remediation.

Conflict rule: if chat context and `authorization.json` disagree, the stricter interpretation wins. Free text can reduce scope but cannot expand it. Expansion requires a new anchor update with explicit operator approval.

### 1.2 OpenClaw config/tool surface controls

Current observed host posture during this design pass:

- `~/.openclaw/openclaw.json` has `tools.exec.host=gateway`, `tools.exec.security=full`, `tools.exec.ask=off`.
- `~/.openclaw/exec-approvals.json` defaults are `security=full`, `ask=off`, `askFallback=full`.
- OpenClaw schema exposes global tool policy: `tools.allow`, `tools.deny`, `tools.fs.workspaceOnly`, `tools.exec.*`, `tools.message.*`, `tools.subagents.tools`.
- Docs state exec approvals are host guardrails, not per-user authorization, and YOLO mode has no heuristic command-obfuscation or script-preflight gate.

Concrete hardening target, when implementation is later authorized:

1. Set host exec to non-YOLO:
   - `tools.exec.security=allowlist` or `deny`
   - `tools.exec.ask=always` for protected sessions
   - `tools.exec.strictInlineEval=true`
   - host approvals `~/.openclaw/exec-approvals.json` defaults:
     - `security=allowlist` or `deny`
     - `ask=always`
     - `askFallback=deny`
     - `autoAllowSkills=false`
2. Set direct filesystem scope:
   - `tools.fs.workspaceOnly=true` at minimum.
   - For stronger V1.1 protection, use `tools.deny` during investigation/consultation sessions to remove `write`, `edit`, `apply_patch`, `message`, and unrestricted `exec` from the active surface except when the operator anchor explicitly grants them.
3. Set subagent policy:
   - `tools.subagents.tools.allow` should default to read-only tools for consultation subagents.
   - Subagents must not inherit mutating tools during `investigation_only`, `consultation_only`, or `proposal_only` modes.
4. Set message policy:
   - `message` should be denied by default in protected modes, except reply-to-current user-visible final answers.
   - Cross-context or proactive sends must require explicit destination grants in the anchor.

This is the only OpenClaw-native pre-effect layer currently visible from docs/schema. It is coarse; it does not evaluate per-path write intent unless OpenClaw itself is extended with a before-tool policy hook or the filesystem/exec path is externally guarded.

### 1.3 Required OpenClaw/tool interception point

Enterprise-grade fix: add or configure a pre-tool authorization hook at the OpenClaw gateway/tool dispatcher layer.

Required behavior:

1. Every tool call is normalized before execution:
   - tool name
   - session key
   - agent id
   - caller/subagent identity
   - target paths
   - command argv/shell string
   - destination channel/target
   - DB path/URL if inferable
   - git action if command invokes git
2. The hook loads `authorization.json` and computes a deterministic decision.
3. If denied, the tool is not invoked. No filesystem write, shell spawn, DB open, git action, or message send occurs.
4. The denial is appended to a block log before returning to the model.
5. The hook is fail-closed when the anchor is missing, unparsable, expired, or hash-invalid during protected ACE sessions.

Block log path:

```text
ace/state/v1_1_required_items/operator-scope-block-log.jsonl
```

Denied event shape:

```json
{
  "ts": "2026-05-22T00:00:00Z",
  "session_key": "...",
  "agent_id": "main",
  "tool": "edit",
  "intent_class": "file_write",
  "target": "ace/operator_constraints.py",
  "mode": "consultation_only",
  "decision": "blocked_before_effect",
  "reason": "path not in allowed_write_paths",
  "scope_hash": "..."
}
```

This hook is the cleanest fix because it blocks the exact bypass tools before side effects.

## 2. If OpenClaw is not modified: fallback controls by strength

Fallback controls must be classified honestly. Most do not prevent all local side effects.

### 2.1 Pre-effect blockers

These stop an action before the durable side effect occurs.

#### A. OpenClaw tool deny/allow policy

Mechanism:

- During protected ACE sessions, set `tools.allow` to read-only tools or `tools.deny` to block mutating tools.
- Deny: `write`, `edit`, `apply_patch`, `message`, possibly `exec`, `nodes`, `gateway.config.patch/apply`, `cron.add/update/remove`, and unrestricted `sessions_spawn`.
- For consultation, allow writing only if OpenClaw supports path-scoped policy; if not, do not allow direct file write and use a human-approved external artifact path or a tightly scoped wrapper.

Blocks:

- Direct OpenClaw file writes/edits/patches.
- Direct message sends.
- Shell if `exec` is denied.

Does not block:

- Anything allowed through remaining tools.
- Human/manual OS actions.
- Misconfiguration or runtime debug overrides.

Strength: high if applied before the session starts; coarse and operationally expensive.

#### B. Host exec approvals strict mode

Mechanism:

- `tools.exec.security=allowlist` or `deny`.
- `tools.exec.ask=always`.
- Host `~/.openclaw/exec-approvals.json` uses `askFallback=deny`, not `full`.
- `strictInlineEval=true`.
- No allowlisting shells (`/bin/zsh`, `/bin/bash`, `/bin/sh`) broadly.
- Allow only read-only binaries with stable args where possible: `git status`, `git diff`, `grep`, `python script-that-only-reads` is difficult to prove and should usually require approval.

Blocks:

- `git commit`, `git revert`, direct SQLite mutation, Bot API curl sends, arbitrary scripts, `python -c`, `sqlite3` writes if not approved.

Does not block:

- Direct OpenClaw `write/edit/apply_patch` because those do not necessarily use shell exec.

Strength: high for shell bypasses; irrelevant to direct file tools.

#### C. Filesystem permissions / immutable protected tree

Mechanism:

- Put protected ACE implementation paths under OS-level read-only permissions for the OpenClaw process user during investigation/consultation.
- Only a separate operator-controlled unlock script restores write access.
- Candidate protected paths:
  - `ace/*.py`
  - `ace/tests/*.py`
  - `ace/state/ace.db`, `ace/state/*.sqlite`, `ace/state/telegram_runtime.db`
  - `.git/` write paths if commits are forbidden
- Leave explicitly authorized consultation path writable, e.g. `ace/state/v1_1_required_items/operator-scope-enforcement-design-v2.md`.

Blocks:

- Direct OpenClaw file tools and shell writes to protected files.
- Direct SQLite mutation if DB file is read-only.

Does not block:

- Writes to unprotected paths.
- External sends.
- Commits that include already modified files unless `.git` is protected or hooks block them.

Strength: high for local file/DB mutation if carefully applied; cumbersome and easy to over/under-scope.

#### D. Credential lock strategy

Mechanism:

- During protected modes, move write-capable secrets out of the OpenClaw runtime environment and into an operator-controlled vault or separate OS account.
- Use read-only tokens where possible.
- Specific locks:
  - Telegram Bot API token unavailable except through approved send proxy.
  - Supabase service role unavailable; use read-only DB role for inspection.
  - GitHub PAT unavailable or read-only; branch protection required for merges.
  - Railway/Vercel/Apify write tokens unavailable.

Blocks:

- External sends via shell/API.
- Remote DB mutation.
- Remote deploy/config mutation.

Does not block:

- Local file edits.
- Local commits unless GitHub push/branch protection is involved.

Strength: high for remote/durable damage; not sufficient for local workspace integrity.

#### E. Command wrapper path/alias strategy

Mechanism:

- Prepend a guarded bin directory to PATH via `tools.exec.pathPrepend`.
- Provide wrappers for `git`, `sqlite3`, `python3`, `python`, `node`, `curl`, `gh`, `railway`, `vercel`, `apify`.
- Wrappers read `authorization.json` and block forbidden modes/args before calling the real binary.
- Do not rely on shell aliases; aliases do not reliably apply to noninteractive tool exec and can be bypassed by absolute paths.
- Pair wrappers with exec allowlist that allows only wrapper paths, not real binaries or shells.

Blocks:

- Shell-command bypasses using PATH-resolved commands.

Does not block:

- Absolute binary paths unless exec allowlist denies them.
- Direct OpenClaw file tools.
- Any non-exec tool.

Strength: medium alone; high only when combined with exec allowlist denying shells/absolute real binaries.

### 2.2 Post-effect detectors

These detect after local side effects. They are not prevention.

#### A. Git pre-commit hook

Exact file:

```text
.git/hooks/pre-commit
```

Flow:

1. Read `ace/state/v1_1_required_items/authorization.json`.
2. Compute staged paths: `git diff --cached --name-only`.
3. Compute staged diff classes: code, test, state DB, docs, consultation artifact.
4. Block commit if any staged path/action is outside `allowed_commit_paths` or mode does not permit commit.
5. Log denial to `operator-scope-block-log.jsonl`.

Blocks:

- Local commit creation when hook is installed and not bypassed.

Does not block:

- File edits before commit.
- `git commit --no-verify` unless the `git` binary is wrapped or branch protection/CI catches it.
- Direct `.git` manipulation.

Strength: medium; useful but bypassable without exec/tool-layer control.

#### B. Git pre-push hook

Exact file:

```text
.git/hooks/pre-push
```

Flow:

1. Read `authorization.json`.
2. Inspect outgoing commits with `git rev-list @{u}..HEAD` or stdin refs.
3. Reject push if commits include unauthorized paths or unsigned/unapproved scope hashes.

Blocks:

- Push to remote from this clone.

Does not block:

- Local commits.
- `git push --no-verify`.
- Push from another clone or API unless remote protection exists.

Strength: medium; not enterprise-grade alone.

#### C. Working-tree watchdog

Mechanism:

- A launchd/file-watcher detects protected-path modifications during locked modes and alerts/logs.

Blocks:

- Nothing by itself.

Strength: detector only.

### 2.3 Remote/durable damage blockers

These prevent bad changes from becoming shared/deployed truth.

#### A. GitHub branch protection

Mechanism:

- Protect `master/main`.
- Require PR.
- Require CI status `operator-scope-policy`.
- Disallow direct pushes and force pushes.
- Require CODEOWNERS/operator approval for ACE protected paths.

Blocks:

- Unauthorized local commits from landing remotely.
- `--no-verify` bypass if CI catches policy.

Does not block:

- Local file edits and commits.
- Local DB mutation.

Strength: high for remote repo integrity.

#### B. CI policy check

Mechanism:

- CI reads `authorization.json` and validates each PR/commit touched paths/action classes.
- Fails if code/test/state changes are present while mode is consultation/proposal only.

Blocks:

- Merge/deploy if branch protection requires the check.

Does not block:

- Local side effects.
- Remote push to unprotected branch.

Strength: high only with branch protection.

#### C. Deployment environment protection

Mechanism:

- Railway/Vercel/GitHub deployment environments require manual approval.
- Write tokens removed from OpenClaw runtime.

Blocks:

- Unauthorized deployment/config mutation.

Strength: high for production effects; not local prevention.

### 2.4 Theater / advisory only

These are useful reminders but do not enforce the boundary:

- Prose instruction anchors without machine enforcement.
- Agent promises to read a file first.
- Checklists in memory.
- Status labels without blocking logic.
- Consultation artifacts not connected to tools.
- Git hooks if `--no-verify` remains available and no remote protection exists.
- Shell aliases without exec allowlist.
- ACE-internal gates while OpenClaw direct tools remain unrestricted.

## 3. Common scenario matrix

| Scenario | Mode | Allowed | Blocked | Required proof |
|---|---|---|---|---|
| Investigation-only session | `investigation_only` | `read`, `web_fetch`, `web_search`, `git status/diff` if exec-approved read-only | `write`, `edit`, `apply_patch`, commits, DB mutation, external sends, code tests that write state | Tool policy shows mutating tools denied; denied attempts logged before effect |
| Consultation artifact write | `consultation_only` | Write only named artifact path(s), e.g. `operator-scope-enforcement-design-v2.md`; optional commit only if anchor grants consultation-result commit | Code files, tests, ACE DB, launchd, runtime config, external sends | Diff shows only authorized artifact path; commit message references consultation only |
| Running read-only tests | `proposal_only` or explicit test grant | Only tests listed in `allowed_exec_classes`/`allowed_commands`, with temp/state isolation | Tests that mutate live ACE DB/state, launchd load/unload, external sends | Test command captured; state diff before/after clean or allowed temp paths only |
| Trying to commit implementation | `investigation_only`/`consultation_only` | None | Commit blocked by tool policy/exec approval/git hook/branch protection | Block log entry before commit; git log unchanged |
| Emergency breach disclosure | `breach_disclosure_only` | Reply to operator; update named breach log path if granted; no remediation | Fixes, tests, rehashing, DB mutation, implementation commits | Diff limited to breach log; no ACE DB mtime/hash changes except allowed read artifacts |
| Approved implementation slice | `implementation_approved` | Explicit files, commands, tests, DB migrations, commits named in anchor | Anything outside slice; broad refactors; unrelated cleanup; external sends unless named | Scope hash in commit trailer; CI policy passes; post-run diff only allowed paths |
| External Telegram send | Any mode except explicit send grant | Current direct reply may be allowed by conversation contract; proactive/cross-context sends require `allowed_external_sends` | `message` tool sends, Bot API curl, ACE/JACE notifications if not granted | Destination, text, reason, approval ref logged before send; delivery receipt after send |
| Subagent delegation | Investigation/proposal modes | Subagents with read-only `toolsAllow` and task text carrying current anchor | Subagents with inherited mutating tools, implementation prompts, commit authority | Subagent spawn record includes allowed tools and anchor hash |

## 4. Bottleneck analysis

### 4.1 Day-to-day file edits

Impact: slower.

Why: direct `edit/write/apply_patch` cannot remain universally available in protected ACE sessions. Either the operator must grant a bounded path/action slice or the agent must work in proposal-only mode.

Mitigation:

- Use short-lived scope grants with explicit paths.
- Separate consultation/doc paths from code paths.
- Use PR workflow for implementation rather than direct master commits.

### 4.2 Git workflow

Impact: significantly slower but safer.

Why: commits need path/mode checks, scope hash trailers, hooks, and remote CI validation. `--no-verify` must be neutralized by wrapper/CI/branch protection.

Mitigation:

- Standard commit trailer:

```text
Operator-Scope: <scope_hash>
Authorized-Mode: implementation_approved
Authorized-Ref: <approval_ref>
```

- Keep protected branch direct pushes disabled.

### 4.3 Testing

Impact: moderate to high.

Why: tests may mutate state, spawn processes, write caches, touch SQLite, load launchd, or send notifications. In locked modes, only read-only/static tests can run without approval.

Mitigation:

- Classify tests:
  - read-only/static
  - temp-dir isolated
  - live-state mutating
  - external-effecting
- Require explicit anchor grants for the last two.

### 4.4 Urgent breach disclosure

Impact: should be minimally slowed.

Why: disclosure must not be blocked by implementation controls, but remediation must be blocked.

Mitigation:

- `breach_disclosure_only` mode permits operator replies and named breach-log edits.
- It denies tests/fixes/commits except the named breach disclosure commit if explicitly granted.

### 4.5 Subagent delegation

Impact: slower orchestration.

Why: every subagent must receive narrowed tools and the current scope hash. Inherited broad tool access recreates the bypass risk.

Mitigation:

- Spawn subagents with read-only tools by default.
- For implementation subagents, create a separate bounded authorization anchor or include the parent scope hash and allowed files.

### 4.6 External alerts/sends

Impact: more friction.

Why: external sends are durable and can annoy/mislead the operator. They must be explicit by destination and purpose.

Mitigation:

- Allow normal reply-to-current final answers.
- Gate proactive sends, Telegram Bot API, Slack, email, and ACE/JACE notifications through `allowed_external_sends`.
- Remove tokens from shell environment when sends are not authorized.

## 5. Recommended implementation order when Andrew authorizes implementation

No implementation is authorized now. If authorized later, implement in this order:

1. **Emergency posture change:** move OpenClaw exec out of YOLO (`ask=always`, `askFallback=deny`, `strictInlineEval=true`) and deny mutating tools for protected ACE sessions.
2. **Authorization anchor:** create `authorization.json` schema and validator.
3. **Pre-tool guard:** add OpenClaw gateway/tool-dispatch hook or equivalent wrapper that blocks `write/edit/apply_patch/exec/message/sessions_spawn/gateway/cron` before effect.
4. **Host controls:** add exec wrappers only after exec allowlist denies real binaries/shells; otherwise wrappers are bypassable.
5. **Repo controls:** add pre-commit/pre-push hooks plus GitHub branch protection and CI policy.
6. **Credential controls:** split read-only vs write tokens and remove write tokens from default OpenClaw runtime.
7. **Scenario tests:** prove blocked actions are blocked before side effects with a matrix matching section 3.

## 6. Pass/fail answer against Andrew's five checks

1. Javarious/OpenClaw enforcement specificity: pass for design detail, pending implementation authorization.
2. Fallback if OpenClaw is not modified: pass with classification into pre-effect blockers, post-effect detectors, remote blockers, and theater.
3. Distinguishes ACE V1.1 vs Javarious bypass pattern: pass.
4. Common scenarios: pass, matrix included.
5. Bottleneck analysis: pass, with explicit workflow costs and mitigations.

Enterprise-grade status: design-ready for operator review, not implementation-ready until Andrew chooses which enforcement layer to authorize first and accepts the operational friction.
