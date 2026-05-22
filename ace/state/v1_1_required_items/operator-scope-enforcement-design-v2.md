# Operator Scope Enforcement Design V2 — Concrete Javarious/OpenClaw Bypass Controls

Status: design artifact only. No implementation is authorized or performed by this file.

Boundary read before this work:

- `ace/state/v1_1_required_items/current-operator-instruction.md`
- `ace/state/v1_1_required_items/consultation-task.md`
- `ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md`
- `ace/state/breach-log/2026-05-21-hash-chain-modification.md`

Current operator request for this artifact: fix the weak/missing sections in the first consultation; investigate OpenClaw config/docs read-only; write this file; commit only this file.

## Ground truth from read-only OpenClaw investigation

Observed local OpenClaw config, sanitized:

- `~/.openclaw/openclaw.json`
  - `tools.exec.host = gateway`
  - `tools.exec.security = full`
  - `tools.exec.ask = off`
  - no configured `tools.allow`, `tools.deny`, `tools.fs.workspaceOnly`, `tools.subagents.tools.*`, or `tools.exec.strictInlineEval` in the active file.
  - `agents.defaults.sandbox.mode = off`
- `~/.openclaw/exec-approvals.json`
  - currently has `agents: {}` and no restrictive defaults recorded.
- Docs/schema confirm actual OpenClaw mechanisms:
  - `tools.allow`, `tools.alsoAllow`, `tools.deny`; deny wins over allow.
  - tool groups include `group:runtime` = `exec`, `process`, `code_execution`; `group:fs` = `read`, `write`, `edit`, `apply_patch`; `group:messaging`; `group:sessions`; `group:automation`.
  - `tools.profile` can be `full`, `coding`, `messaging`, `minimal`; `minimal` is `session_status` only.
  - `tools.fs.workspaceOnly` restricts fs tools to workspace only; it is not path-granular inside workspace.
  - `tools.exec.security` supports `deny`, `allowlist`, `full`; `tools.exec.ask` supports `off`, `on-miss`, `always`.
  - `tools.exec.pathPrepend`, `tools.exec.safeBins`, `tools.exec.safeBinTrustedDirs`, `tools.exec.safeBinProfiles`, and `tools.exec.strictInlineEval` exist.
  - exec approvals are host-local guardrails in `~/.openclaw/exec-approvals.json`; docs explicitly say they are not a per-user auth boundary.
  - YOLO/no-approval mode requires both OpenClaw config and host approvals to be open; in YOLO, OpenClaw does not add heuristic command-obfuscation or script-preflight rejection.
  - plugin lifecycle hooks include `before_tool_call`, `after_tool_call`, `message_sending`, and docs say `before_tool_call: { block: true }` is terminal. Native Codex app-server runs bridge Codex-native tool events back into this hook surface; plugins can block native Codex tools through `before_tool_call`, but the bridge does not rewrite Codex-native tool arguments yet.
  - subagents default to all tools except session/system tools when no restrictive profile is used; `tools.subagents.tools.allow/deny` is available and `allow` is a final allow-only filter.

Unknowns / not proven by docs in this pass:

- Exact plugin hook payload fields for `before_tool_call`; source inspection is required before implementation to prove path/command/destination normalization is possible without patching OpenClaw core.
- Whether current active runtime exposes a custom policy plugin route already installed; none was observed in config.
- Whether direct built-in `write/edit/apply_patch` are fully mediated by plugin `before_tool_call` in this exact runtime. Docs imply hook coverage for agent tools and Codex-native events, but implementation must prove it with a no-op/blocking test before relying on it.

## Section 1 — Javarious/OpenClaw enforcement specifics

### 1.1 Git hooks: exact filenames, locations, inspections, refusals

Git hooks are local controls under the repository `.git/hooks/` directory. They are not sufficient alone because `--no-verify`, alternate clones, direct `.git` mutation, or disabled hooks can bypass them. They are still useful as local pre-effect blockers for normal git workflows when combined with command wrapping and remote branch protection.

#### `.git/hooks/pre-commit`

Location:

```text
/Users/andrewpilson/.openclaw/workspace/.git/hooks/pre-commit
```

Inspects:

- `ace/state/v1_1_required_items/authorization.json` exists, parses, is not expired, and has a valid `scope_hash`.
- Current mode, e.g. `investigation_only`, `consultation_only`, `proposal_only`, `implementation_approved`, `breach_disclosure_only`.
- Staged paths from `git diff --cached --name-only`.
- Staged diff content from `git diff --cached -- <path>` for high-risk patterns:
  - ACE implementation code: `ace/*.py`, `ace/**/*.py` excluding allowed docs/state paths.
  - ACE tests: `ace/tests/**`.
  - ACE state DBs: `ace/state/*.db`, `ace/state/*.sqlite`, `ace/state/telegram_runtime.db`.
  - OpenClaw config/credentials: `.openclaw/**` if repo-visible; `MEMORY.md`; files containing token/key patterns.
  - launchd/runtime files: `ace/launchd/**`.
  - GitHub workflows: `.github/workflows/**`.
- Optional commit message trailer is not available in `pre-commit`; trailer validation belongs in `commit-msg`.

Refuses when:

- Mode is `investigation_only` and staged changes are non-empty.
- Mode is `consultation_only` and any staged path is not exactly in `allowed_commit_paths`, e.g. only `ace/state/v1_1_required_items/operator-scope-enforcement-design-v2.md` for this task.
- Mode is `proposal_only` and staged paths include implementation code, tests, runtime config, DB/state mutation, launchd, or external-send code outside allowed proposal/docs paths.
- Mode is `breach_disclosure_only` and staged paths are not the named breach log/disclosure artifact(s).
- Mode is `implementation_approved` but staged paths exceed explicit allowed path globs/action classes.
- Authorization file is missing, hash-invalid, expired, or conflicts with current branch/session marker.

Proof of refusal:

- Append a JSONL entry to `ace/state/v1_1_required_items/operator-scope-block-log.jsonl` before exiting nonzero.
- Exit code nonzero; commit not created.

#### `.git/hooks/commit-msg`

Location:

```text
/Users/andrewpilson/.openclaw/workspace/.git/hooks/commit-msg
```

Inspects:

- Commit message file passed as `$1`.
- Required trailers when mode is not free/unlocked:
  - `Operator-Scope: <scope_hash>`
  - `Authorized-Mode: <mode>`
  - `Authorized-Ref: <approval_ref>`
- Current `authorization.json` hash/mode/approval ref.

Refuses when:

- Commit lacks the required trailers in `implementation_approved` mode.
- Trailer hash does not match current anchor hash.
- Commit claims a broader mode than anchor.
- Commit message attempts to label implementation as consultation/proposal.

Why needed:

- `pre-commit` validates staged content; `commit-msg` binds the commit to the operator authorization.

#### `.git/hooks/pre-push`

Location:

```text
/Users/andrewpilson/.openclaw/workspace/.git/hooks/pre-push
```

Inspects:

- Stdin refs supplied by Git pre-push.
- Outgoing commit range for each ref, e.g. local SHA not present remotely.
- Each outgoing commit's touched paths via `git diff-tree --no-commit-id --name-only -r <sha>`.
- Each outgoing commit message trailers.
- Current `authorization.json` mode; if expired, pushing implementation is refused.

Refuses when:

- Any outgoing commit touches protected paths without matching authorization trailers.
- Branch is `master`/`main` and direct push is attempted while policy says PR-only.
- Commit includes state DB mutation or launchd/config changes without explicit remote-push grant.
- Authorization expired before push.

Limits:

- Bypassable by `git push --no-verify`, alternate clone, GitHub API, or disabled hook. Therefore it is a local pre-effect blocker only when paired with command wrapping and remote branch protection.

#### `.git/hooks/pre-rebase` and `.git/hooks/post-checkout`

Locations:

```text
/Users/andrewpilson/.openclaw/workspace/.git/hooks/pre-rebase
/Users/andrewpilson/.openclaw/workspace/.git/hooks/post-checkout
```

Inspects:

- Whether the operation would rewrite/rebase commits containing protected ACE paths.
- Whether checkout changes `authorization.json`, breach logs, ACE state files, launchd files, or OpenClaw policy artifacts.

Refuses / alerts:

- `pre-rebase` refuses rebase of protected implementation commits unless current mode explicitly grants history rewrite.
- `post-checkout` cannot prevent the checkout after it happened; it is a detector and should alert/log if protected files changed while scope is narrow.

### 1.2 Filesystem permission model

Goal: interactive Javarious/OpenClaw shells and file tools cannot mutate protected ACE implementation/state during narrow modes, while the unattended ACE supervisor/cycle can continue writing required runtime state.

Recommended OS account split:

- `andrew` / current OpenClaw interactive user: owns the workspace today; too powerful for protected modes.
- `ace-runner`: dedicated local service account for ACE launchd/supervisor/cycle writes.
- `ace-admin`: optional admin/operator group for unlocking protected files.
- Group: `ace-state` shared by `ace-runner` and operator-controlled admin, not by unrestricted interactive agent process if separation is possible.

Directory ownership and permissions when locked:

```text
ace/                                  root or ace-admin:ace-admin     0555 for dirs, 0444 for implementation files
ace/*.py                              root or ace-admin:ace-admin     0444
ace/tests/                            root or ace-admin:ace-admin     0555 dirs, 0444 files
ace/launchd/                          root or ace-admin:ace-admin     0555 dirs, 0444 files
ace/reports/                          root or ace-admin:ace-admin     0555 dirs, 0444 files unless report-write scope granted
ace/state/                            ace-runner:ace-state            0750
ace/state/ace.db                      ace-runner:ace-state            0640 or 0660 only if writer group required
ace/state/*.sqlite                    ace-runner:ace-state            0640/0660 same rule
ace/state/telegram_runtime.db         ace-runner:ace-state            0640/0660 same rule
ace/state/breach-log/                 ace-admin:ace-admin             0755 normally; writable only under breach_disclosure grant
ace/state/v1_1_required_items/        ace-admin:ace-admin             0755 normally; per-artifact write grant for consultation/proposal
.git/                                 current git owner              not protected by FS unless no local commits allowed; better controlled by hooks/wrappers/branch protection
```

How supervisor writes while interactive shells cannot:

- Launchd plist runs ACE cycle/supervisor as `ace-runner` or uses a wrapper that drops privileges to `ace-runner` before opening state DBs.
- State DB files are writable only by `ace-runner` and maybe `ace-state` group.
- Interactive OpenClaw process remains outside `ace-state` group for locked modes, or runs under a separate user with no write permission to `ace/state/*.db`.
- If OpenClaw and ACE must currently run under the same macOS user, pure Unix permissions cannot separate them. In that case the concrete design requires either:
  - moving ACE supervisor to a separate OS account, or
  - moving ACE mutable state outside the interactive workspace into a directory writable only by the supervisor account, or
  - using filesystem ACLs plus process identity separation. Without identity separation, permissions are advisory/theater because the same user can chmod/chown files back if allowed.

Required explicit lock/unlock workflow:

- `lock` operation: operator-controlled, not agent-controlled, sets protected files read-only and verifies with `find ace -perm -u+w` exclusions.
- `unlock` operation: requires operator action and records approval ref; grants temporary write access only to allowed paths.
- `relock` operation: restores read-only mode after implementation slice.

Concrete refusal trigger:

- Direct `write/edit/apply_patch` or shell write to protected paths fails with OS permission error before file content changes.

### 1.3 Command wrapper strategy

Recommended order of strength:

1. OpenClaw tool-layer hook/plugin or core patch blocks tool calls before effect.
2. OpenClaw config denies dangerous tools in narrow modes.
3. Exec allowlist/approval allows only wrapper binaries, not shells or real binaries.
4. PATH wrappers enforce command-specific policy.
5. Git hooks/CI/branch protection catch remaining git flows.

Do not rely on shell aliases. Aliases in `.zshrc`/`.bashrc` are bypassable by noninteractive shells, absolute paths, scripts, `env -i`, and OpenClaw direct tools. They are documentation convenience only.

Exact wrapper location:

```text
/Users/andrewpilson/.openclaw/workspace/ace/bin/guarded/
```

OpenClaw config mechanism that exists:

```json
{
  "tools": {
    "exec": {
      "pathPrepend": ["/Users/andrewpilson/.openclaw/workspace/ace/bin/guarded"],
      "security": "allowlist",
      "ask": "always",
      "strictInlineEval": true
    }
  }
}
```

Wrapper targets:

- `git`
- `sqlite3`
- `python3`
- `python`
- `node`
- `curl`
- `gh`
- `railway`
- `vercel`
- `apify`
- optional: `openclaw` to prevent config writes/update/restart outside scope

Wrapper logic:

1. Resolve real binary from a fixed path not writable by the agent, e.g. `/usr/bin/git`, `/usr/bin/sqlite3`, `/usr/bin/python3`, `/usr/bin/curl`, not from mutable PATH.
2. Load `authorization.json`.
3. Classify command:
   - `git status`, `git diff`, `git log` = read-only.
   - `git add`, `git commit`, `git reset`, `git revert`, `git push`, `git rebase` = side-effecting.
   - `sqlite3 ace/state/ace.db SELECT...` = read-only only if query parser proves no write pragma/DDL/DML; otherwise side-effecting.
   - `curl` to Telegram Bot API/send endpoints = external send.
   - `python -c`, `node -e` = inline eval; forbidden unless explicit.
   - test commands = side-effect class based on allowlisted command hash and temp/live state policy.
4. Refuse before execing real binary if mode does not allow the class/path/destination.
5. Append block log entry on refusal.

Critical pairing:

- Exec allowlist must deny `/bin/zsh`, `/bin/bash`, `/bin/sh`, `/usr/bin/env`, and absolute paths to real binaries unless specifically approved. Otherwise wrappers are bypassable.
- `tools.exec.strictInlineEval=true` must be enabled.
- `tools.exec.safeBins` must not include interpreters/runtimes without profiles.

Git-hooks-only strategy is insufficient. Hooks cannot stop direct file edits, DB mutation, `--no-verify`, or external sends.

### 1.4 Credential lock strategy

Goal: the agent cannot read or use write-capable secrets outside authorized scope, and cannot echo them in chat/tool output.

Token classes:

- External-send tokens: Telegram bot token, Slack token, email/API messaging tokens.
- Model/provider tokens: Anthropic, OpenAI, OpenRouter, Gemini, DeepSeek.
- Infra tokens: GitHub PAT, Supabase service role, Railway, Vercel, Apify, Notion.
- Read-only inspection tokens where available.

Storage model:

- Write-capable tokens should not live in `MEMORY.md`, daily memory, repo files, or default shell env available to `exec`.
- Put write-capable tokens in an OS keychain/vault or root/ace-runner-owned env file with mode `0400` or `0440`, readable only by the process that legitimately needs them.
- Split env files:

```text
~/.openclaw/secrets/read-only.env          current OpenClaw user can read, contains read-only tokens only
~/.openclaw/secrets/write-capable.env      operator/ace-runner only, not readable by interactive OpenClaw user
ace/state/ace-telegram.env                 should be readable only by ace-runner if JACE/ACE sends are authorized
```

Permissions:

```text
~/.openclaw/secrets/                       operator-admin:operator-admin 0700
~/.openclaw/secrets/read-only.env          openclaw-agent:operator-admin 0440
~/.openclaw/secrets/write-capable.env      ace-runner:ace-state          0400
ace/state/ace-telegram.env                 ace-runner:ace-state          0400
```

How unauthorized reads are prevented:

- Interactive OpenClaw user does not have filesystem permission to read write-capable env files.
- OpenClaw config for narrow modes denies `exec`, `read`, or FS access to secret paths; but FS permission is the real blocker.
- Shell environment for OpenClaw does not include write-capable secrets by default.
- External-send proxies run as `ace-runner` and accept only structured approved messages with scope hash, not arbitrary token access.

How unauthorized use is prevented:

- Telegram sends go through a local `send-proxy` that checks `authorization.json` `allowed_external_sends` before using the token.
- Supabase service role is unavailable to interactive agent; read-only DB role used for inspection.
- GitHub PAT with write scope unavailable; branch protection prevents direct landing even if local commit exists.
- Model tokens are allowed for model runtime but not exposed to shell or file reads.

What prevents echoing tokens:

- Best prevention is non-access: if the agent cannot read a token, it cannot echo it.
- Add output redaction as secondary detector/mitigation in tool result middleware, but do not rely on redaction as the primary control.
- Keep secrets out of memory files; existing memory secrets are a legacy risk and should be treated as compromised for future enterprise design.

### 1.5 OpenClaw config/tool interception point — actual available mechanisms

Actually available without source changes:

- `tools.allow`, `tools.alsoAllow`, `tools.deny` for coarse tool availability.
- `tools.profile` for coarse baseline (`minimal`, `messaging`, `coding`, `full`).
- `tools.fs.workspaceOnly` for workspace boundary only.
- `tools.exec.security`, `tools.exec.ask`, `tools.exec.strictInlineEval`, `tools.exec.pathPrepend`, `tools.exec.safeBins`, `tools.exec.safeBinTrustedDirs`, `tools.exec.safeBinProfiles`.
- host exec approvals in `~/.openclaw/exec-approvals.json`.
- `tools.subagents.tools.allow/deny` to narrow subagent tools.
- plugin hook mechanism with documented `before_tool_call` terminal block and `message_sending` cancellation.

Not available as documented config:

- No documented built-in per-path allowlist for `write/edit/apply_patch` inside the workspace.
- No documented built-in policy that reads a custom `authorization.json` and blocks tool calls by scope.
- No documented built-in secret vault policy that prevents an agent from reading secrets already present in accessible files/memory.
- No documented built-in per-command semantic classifier for `exec` beyond approvals, allowlist, safeBins, strictInlineEval.

Best concrete tool-layer design:

- Build an OpenClaw plugin or core patch using `before_tool_call` and `message_sending`.
- Plugin loads `authorization.json`, normalizes tool call intent, and blocks before effect.
- It must prove coverage for built-in tools and current runtime by test before being trusted.
- If hook payload lacks necessary path/command/destination fields, implementation must patch OpenClaw core dispatcher rather than handwave.

## Section 2 — Fallback control classification

| Control | Class | What it blocks/catches | Why classification is honest |
|---|---|---|---|
| Git `pre-commit` hook | (a) Pre-effect blocker for normal commit only; (d) if alone | Blocks creation of normal local commits with unauthorized staged changes | Does not block file edits, DB mutation, external sends, or `--no-verify` |
| Git `commit-msg` hook | (a) Pre-effect blocker for normal commit metadata only | Blocks commits without scope trailers | Does not inspect all side effects and is bypassable |
| Git `pre-push` hook | (a) Pre-effect blocker for normal push from this clone; (c) weak remote consequence blocker | Blocks normal push before remote receives it | Does not stop local commit/edit; bypassable with `--no-verify` or another route |
| CI policy check | (c) Remote/durable damage blocker | Prevents merge/deploy if required by branch protection | Local bad action already happened; CI cannot undo local mutation |
| Protected branches | (c) Remote/durable damage blocker | Prevents direct landing on `main/master`; can require PR/review/status | Does not prevent local edits/commits |
| Read-only filesystem / separate OS user | (a) Pre-effect blocker | Prevents file/DB writes at OS level before content changes | Only real if OpenClaw interactive user lacks chmod/chown/write authority |
| Shell/PATH wrappers | (a) Pre-effect blocker for wrapped exec only; (d) if aliases only | Blocks forbidden `git/sqlite3/curl/python` calls before real binary executes | Bypassable unless exec policy denies shells and absolute real binaries |
| DB permissions/read-only DB role | (a) Pre-effect blocker for DB writes; (c) durable data blocker | Prevents write SQL from succeeding | Does not stop file edits or local commits |
| External-send proxy | (a) Pre-effect blocker for sends through proxy | Refuses Telegram/email/Slack sends before token use | Only works if raw tokens are inaccessible and raw `message`/curl paths are denied |
| OpenClaw `tools.deny/allow` | (a) Pre-effect blocker at tool availability layer | Removes dangerous tool calls before model/tool execution | Coarse; not per-path; must be configured before run |
| Exec approvals non-YOLO | (a) Pre-effect blocker for shell | Prompts/denies before shell command starts | Does not stop direct fs tools |
| Working-tree watchdog | (b) Post-effect detector | Detects modifications after they happen | Cannot undo side effects |
| Token redaction | (b) Post-effect mitigation/detector | Reduces leakage after output generated | Does not stop token use if token accessible |
| Prose instructions/current-operator-instruction only | (d) Theater/advisory | Reminds agent | Does not physically block tools |

Minimum combination of (a) + (c) controls that closes the bypass pattern:

1. **OpenClaw pre-effect tool blocking**: either `tools.deny/allow` for coarse locked modes or a `before_tool_call` plugin/core gate for scoped modes. This must block `write`, `edit`, `apply_patch`, `exec`, `message`, `gateway`, `cron`, and mutating `sessions_spawn` when scope does not allow them.
2. **Host exec non-YOLO plus wrappers/allowlist**: `exec` cannot spawn arbitrary shells/binaries; wrappers enforce `authorization.json` for approved command paths.
3. **Filesystem/identity split for ACE protected files/state**: OS permissions prevent direct file/DB mutation even if a tool layer misses.
4. **Credential lock + external-send proxy**: write-capable tokens unavailable to interactive agent; sends require proxy authorization.
5. **Protected branches + required CI policy**: prevents local bypass from becoming remote/canonical even if local blocker fails.

Secondary but still valuable:

- Git hooks for normal workflow friction.
- Watchdogs and block logs for audit.
- Redaction for leakage mitigation.

Controls that are not enough:

- Git hooks + instructions only.
- ACE-internal authorization only.
- Shell aliases without exec allowlist.
- CI without branch protection.
- External-send proxy while raw tokens remain readable.

## Section 3 — Common scenarios matrix

| Scenario | Scope file says | Bot can do | Blocked | Operator workflow to set/update scope |
|---|---|---|---|---|
| Investigation-only session | `mode=investigation_only`; allowed tools read/search/status; no write paths, no exec except approved read-only | Read files/docs/config; inspect git status/diff via approved read-only command; summarize findings | `write/edit/apply_patch`; commits; DB mutation; tests that write; external sends; broad subagents | Operator writes/approves `authorization.json` with mode and expiry; OpenClaw session starts with mutating tools denied or guard active |
| Consultation document write | `mode=consultation_only`; `allowed_write_paths=[operator-scope-enforcement-design-v2.md]`; `allowed_commit_paths` same; commit allowed only for this file | Read docs; write the one artifact; commit only that file | Any code/test/state/config edit; DB mutation; external send; staging other files | Operator grants named artifact path and commit message class; after commit, scope expires or returns to investigation |
| Running read-only tests | `mode=proposal_only` or `implementation_approved` with `allowed_commands` containing exact test command and temp-state guarantees | Run exact allowlisted test command only if it cannot touch live ACE state or external sends | Live DB tests, launchd changes, notification tests, network sends, broad test suites if side effects not classified | Operator approves command hash, cwd, env, timeout, state isolation; output recorded as evidence |
| Trying to commit implementation under wrong scope | `mode=investigation_only` or `consultation_only`; no implementation paths in allowed commits | Nothing beyond explanation; can report blocked attempt | File writes blocked by tool/FS; `git add/commit` blocked by wrappers/hooks; push blocked remotely | Operator must explicitly change scope to `implementation_approved` with files/actions/tests before implementation can proceed |
| Emergency breach disclosure | `mode=breach_disclosure_only`; allowed reply-to-current; optional named breach-log path | Disclose facts to operator; optionally update named breach artifact; no fixes | Remediation, tests, rehashing, DB mutation, implementation commit, notification proof attempts | Operator issues emergency/breach scope; if artifact write needed, names exact file and whether commit is allowed |
| Approved implementation slice | `mode=implementation_approved`; explicit files, commands, DB targets, send targets, expiry, approval ref | Modify only listed files; run only listed tests; commit with scope trailer; maybe PR/push if granted | Anything outside path/action grant; unrelated cleanup; external sends unless named | Operator reviews plan, grants bounded scope with expiry; agent executes; CI/proof must match grant; scope closes after completion |
| External Telegram send | `allowed_external_sends` lists channel, destination, purpose, text class, expiry | Send only through approved proxy/tool path; normal reply-to-current may remain allowed by chat contract | Raw Bot API curl; proactive messages; JACE delivery outside grant; sends to unlisted destinations | Operator grants destination and purpose; proxy logs pre-send authorization and post-send receipt |
| Operator broadening scope mid-session | New `authorization.json` supersedes prior hash with broader mode/actions | Continue only after re-reading anchor and verifying new hash; tool guard uses new scope | Acting on free-text broadening without anchor update | Operator updates anchor via explicit approval path; session records old/new scope hash; guard reloads before next side effect |
| Operator narrowing scope mid-session | New anchor removes grants or sets narrower mode | Finish current read-only thought/report; no further side effects outside new scope | Continuing old implementation/test/send authority | Operator updates anchor; guard treats narrower scope as immediate; in-flight side-effecting processes should be killed or allowed to finish only if explicitly safe |
| Scope expiry mid-action | `expires_at` passes before next side-effecting tool call | Complete current already-started atomic tool only if cannot be interrupted safely; otherwise stop and report expiry | Starting new write/exec/send/commit after expiry | Operator reissues/extends scope with new approval ref; guard fail-closes until then |

## Section 4 — Bottleneck analysis

| Mechanism | What it makes harder | Severity | Mitigation | Acceptance criterion |
|---|---|---:|---|---|
| OpenClaw `tools.deny/allow` locked modes | Day-to-day file edits; quick fixes; using normal assistant flow | High | Use short-lived scoped grants; keep docs/proposals separate; maintain read-only default | Acceptable if protected ACE work is high-risk; too restrictive for ordinary low-risk projects unless scoped by agent/session |
| `before_tool_call` scope plugin/core gate | Every mutating tool call pays policy overhead; implementation complexity | Medium | Normalize once; cache valid scope hash; log concise denials | Acceptable if proven to block built-in fs/exec/message tools before effect |
| Non-YOLO exec approvals | Git workflow, tests, shell inspection, scripts | High | Allowlist read-only commands; use exact command grants; keep `ask=always` only for protected sessions | Acceptable for ACE V1.1 because prior bypasses used shell/git/sqlite/curl |
| PATH command wrappers | Git/push/test/curl workflows; absolute paths must be blocked | Medium | Pair with exec allowlist; provide clear refusal messages | Acceptable only as defense-in-depth, not sole enforcement |
| Filesystem read-only / separate `ace-runner` | File edits, tests writing caches, local DB inspection/migration | High | Split mutable runtime state from implementation; temp dirs for tests; explicit unlock workflow | Acceptable if ACE state integrity matters more than speed; required for real local pre-effect protection |
| Git hooks | Committing/rebasing/pushing; occasional false positives | Medium | Keep hook rules path-based and transparent; provide operator override only through scope update | Acceptable as workflow guard but not primary security |
| Protected branches + CI | Pushing directly to main/master; emergency commits | Medium | Use PRs; emergency disclosure branch; operator override via GitHub review | Acceptable because it protects canonical remote truth |
| Credential lock / vault split | External alerts, deploys, API inspection; some automations need token access | High | Read-only tokens for inspection; proxy for authorized writes; separate `ace-runner` env | Acceptable; token access is too sensitive for unrestricted shell/file context |
| External-send proxy | Telegram/email status updates and JACE delivery slower | Medium | Allow reply-to-current; pre-approve recurring ACE operational sends narrowly | Acceptable if it prevents synthetic/noisy/unauthorized notifications |
| Subagent tool restrictions | Delegation slower; subagents may need explicit tool lists | Medium | Default read-only; grant implementation subagents exact tools/paths; include scope hash in task | Acceptable; inherited broad tools recreate the bypass pattern |
| Documentation path allowlists | Documentation writes require scope path updates | Low/Medium | Keep a dedicated consultation/docs directory writable under consultation mode | Acceptable if path grants are fast and explicit |
| ACE unattended launchd cycle under `ace-runner` | Operational setup complexity; debugging harder from interactive shell | Medium/High | Separate runtime logs; read-only inspection commands; operator-controlled service management | Acceptable if resident cycle must keep running without giving interactive bot DB write authority |
| Breach disclosure mode | Blocks immediate remediation after disclosure | Low | Mode permits operator reply and named breach-log write without ceremony | Acceptable and necessary: disclosure first, remediation only after explicit approval |
| Testing with side effects | Full suites may be blocked; live-state tests need approval | High | Tag tests by side-effect class; run temp isolated tests by default; explicit grants for live tests | Acceptable if test taxonomy is maintained |

Specific bottleneck answers:

- Day-to-day file edits: high under locked ACE modes; acceptable only for protected ACE/V1.1 work, not as global default for all projects.
- Git workflow: medium/high; acceptable because canonical truth needs protection after documented commit/revert bypasses.
- Testing: high for live-state tests; acceptable if tests are classified and temp-isolated variants exist.
- Urgent breach disclosure: low if `breach_disclosure_only` exists; acceptable because it allows disclosure without allowing fixes.
- Subagent delegation: medium; acceptable because child agents otherwise multiply bypass risk.
- External alerts/sends: medium; acceptable because prior JACE/notification proof contamination involved unwanted/synthetic sends.
- Documentation writes: low/medium; acceptable with named docs directory/path grants.
- ACE cycle operations: medium/high; acceptable if `ace-runner` separation preserves unattended operation while limiting interactive writes.

## Section 5 — Decision points for Andrew before implementation

### 5.1 Strict deny-by-default vs allow-known-safe-by-default

Option A: strict deny-by-default.

- Default tools: read/status only.
- Every write/exec/send/test needs explicit scope grant.
- Trade-off: strongest prevention; highest friction.

Option B: allow-known-safe-by-default.

- Read/search/git status/diff and docs writes may be allowed in specific folders.
- Trade-off: lower friction; more classification risk.

Decision needed: choose default posture for ACE sessions. Recommendation: strict deny-by-default for ACE/V1.1 until trust is rebuilt; allow-known-safe for ordinary non-ACE work only if scoped separately.

### 5.2 Per-action approval vs scope-based bulk approval

Option A: per-action approval.

- Every mutating tool call requires approval.
- Trade-off: safest and auditable; slow, annoying, blocks autonomous work.

Option B: scope-based bulk approval.

- Operator grants a bounded package: paths, commands, tests, sends, expiry.
- Trade-off: usable for implementation; risk if grant is too broad.

Decision needed: preferred approval model. Recommendation: scope-based bulk approval with narrow path/action/expiry, plus per-action approval for external sends, DB mutation, and production/deploy actions.

### 5.3 Token expiry duration

Choices:

- 15 minutes: good for breach disclosure or one small commit.
- 1 hour: good for bounded implementation slice.
- 4 hours: good for long test/refactor windows but higher risk.
- Until revoked: not recommended for protected ACE work.

Decision needed: default expiry by mode. Recommendation: investigation no expiry but no side effects; consultation 1 hour; implementation 1 hour renewable; external sends 15 minutes or single-use.

### 5.4 What action classes count as side effect requiring authorization

Proposed side-effect classes:

- File write/edit/delete/rename.
- Git staging/commit/revert/reset/rebase/push/tag.
- Shell command that writes files, mutates DB/state, starts/stops services, changes config, installs packages, or performs network POST/send.
- Test command that writes live state, launches services, sends notifications, or uses production credentials.
- DB mutation including local SQLite and remote Supabase.
- External send/post/message/email/Telegram/JACE/Slack.
- Credential read/access/export.
- Config changes and Gateway restart/update.
- Subagent spawn with mutating tools.
- Cron add/update/remove/run if it can create future side effects.

Decision needed: approve this list or narrow/expand it. Recommendation: treat all above as authorization-required side effects.

### 5.5 Failed authorization attempts: pause entire session or block only action

Option A: block only the specific action.

- Agent can continue investigation/explanation.
- Trade-off: less disruptive; repeated attempts possible.

Option B: pause entire session after high-risk denial.

- Any denied implementation/DB/send/secret action pauses session and requires operator acknowledgement.
- Trade-off: safer after breach pattern; can interrupt useful work.

Decision needed: denial severity policy. Recommendation:

- Low-risk denial (wrong docs path): block action and continue.
- Medium-risk denial (commit/test outside scope): block action and require plan correction.
- High-risk denial (DB mutation, credential read, external send, config change, rehash/audit tampering): pause entire session and require operator acknowledgement.

## Final implementation boundary

No implementation is authorized by this artifact. The concrete design above identifies what to build and what operator decisions are still required. Implementation should not begin until Andrew selects the decision points in Section 5 and authorizes a bounded implementation slice with explicit files, commands, tests, commits, and expiry.
