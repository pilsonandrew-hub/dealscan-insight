# Current Operator Instruction
Authority: this file is the durable operator scope anchor. The bot does not edit this file. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.
Last updated: 2026-05-22 by operator authorization
## Mode
implementation_approved — V1.1 item 3 (operator scope enforcement) implementation in slices
## Scope
Per design d90fbbf (operator-scope-enforcement-design-v2.md). Five operator decisions adopted:
1. Strict deny-by-default
2. Scope-based bulk approval with narrow bounds
3. Default expiries: investigation no-expiry/no-side-effects, consultation 1hr, implementation 1hr renewable, external sends 15min single-use
4. Side-effect class list per design v2 Section 5.4 approved as-is
5. Tiered denial: low-risk blocks action, medium-risk requires plan revision, high-risk pauses session
## Allowed write paths
- ace/scope_guard.py and related new modules for the scope guard implementation
- ace/tests/test_scope_guard.py and related new test files*
- ace/state/v1_1_required_items/authorization.json (new file, schema per design v2 Section 1.1)
- ace/state/v1_1_required_items/operator-scope-block-log.jsonl (new file)
- ace/state/v1_1_required_items/operator-scope-design-decisions.md (record the five decisions)
- ace/bin/guarded/ (new directory, command wrappers per design v2 Section 1.3)*
- ace/hooks/ — tracked Git hook source, hook library, installer, and documentation for Slice 3
- .git/hooks/pre-commit, commit-msg, pre-push, pre-rebase, post-checkout (per design v2 Section 1.1)
- Integration edits to existing ACE write paths: ace/repository.py, ace/action_runtime.py, ace/governed_run_runtime.py, ace/supervisor_runtime.py, ace/sweep.py — minimal edits only to route through scope guard
## Allowed actions
- File writes/edits to the above paths only
- Git commits with Operator-Scope trailer referencing this anchor
- Git push to origin/master after commits
- Running ACE test suite under PYTHONWARNINGS=error
- Read access to all of ACE, OpenClaw config, DealerScope for investigation
## Forbidden
- Editing this anchor file (current-operator-instruction.md) — operator-owned
- ACE state DB writes (ace/state/.db) outside authorization.json and block-log files*
- OpenClaw config modification (~/.openclaw/openclaw.json, exec-approvals.json)
- Filesystem permission changes (chmod/chown)
- Credential reads or writes
- External sends (Telegram, JACE, HTTP POST)
- Launchd plist modification
- DealerScope changes
- Hermes/Ja’rvontis interaction
- Subagent spawns
- Force-push or history rewrite
## Implementation slices
Sequential. Report each commit before next. Wait for operator approval before each next slice.
Slice 1: authorization.json schema + ace/scope_guard.py with gate.authorize() interface. Tests prove ALLOW/BLOCK/REQUIRE_APPROVAL behave correctly. No integration yet.
Slice 2: Wire scope guard into ace/repository.py, ace/action_runtime.py, ace/governed_run_runtime.py, ace/supervisor_runtime.py, ace/sweep.py. Tests prove unauthorized actions blocked at code level.
Slice 3: Git hooks per design v2 Section 1.1. Tests prove unauthorized commits/pushes refused.
Slice 4: Command wrappers in ace/bin/guarded/ per design v2 Section 1.3. Tests prove unauthorized commands refused before real binary runs.
Slice 5: Record five decisions in ace/state/v1_1_required_items/operator-scope-design-decisions.md.
## Expiry
This implementation_approved scope was refreshed at 2026-05-22 by operator authorization. Expires 4 hours from this refresh OR when Slice 5 lands with all tests passing under PYTHONWARNINGS=error, whichever first.
Slices completed before refresh: 1, 2, 3.
Slices remaining under this refresh: 4 (command wrappers in ace/bin/guarded/), 5 (record five decisions in operator-scope-design-decisions.md).
After expiry, scope reverts to investigation/consultation only.
## Tiered denial behavior
If you encounter a need to do something outside this scope:
- Do NOT extend scope yourself
- Do NOT edit this anchor
- Do NOT proceed
- Stop, report what you need, wait for operator to update anchor
## Operator-owned items NOT in this scope
- OS account creation (ace-runner) — operator handles
- Filesystem permission changes — operator handles
- OpenClaw config changes — operator handles
- Credential vault setup — operator handles
- GitHub branch protection — operator handles
