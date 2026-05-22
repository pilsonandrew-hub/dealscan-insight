# Current Operator Instruction — ACE V1.1

Status: implementation-approved bounded scope.

Operator approval source: Andrew Pilson Telegram direct instruction on 2026-05-22: "Approved+ Proceed + Continue in the most professional and elegant manner possible. hygiene is a must! Fix all errors + failures + errors along the way. Remember Industrious and enterprise quality is our goal in everything we do!"

Allowed objective: implement the ACE operator-scope enforcement hygiene slice needed to prevent the Javarious/OpenClaw bypass pattern described in `ace/state/v1_1_required_items/operator-scope-enforcement-design-v2.md`.

Allowed files/directories:

- `ace/` source, tests, docs, launchd-supporting files, and V1.1 required-item artifacts when directly related to operator-scope enforcement.
- `.github/workflows/` only if CI is failing because of the ACE enforcement slice.
- `memory/YYYY-MM-DD.md` for real-time logging only.

Allowed commands:

- Read-only repo/config/docs inspection.
- Python unit tests under `ace/tests`.
- `python3 -m ace.ace audit verify` and read-only ACE health/status commands.
- Git status/diff/log/add/commit/push for this bounded slice only.

Denied unless Andrew explicitly re-approves:

- Direct SQLite mutation of ACE state.
- Rehash/hash-chain repair.
- External Telegram/JACE/send tests.
- Secret/token reads or credential relocation.
- OpenClaw config changes, gateway restart, self-update, or broad tool-policy changes.
- Destructive cleanup outside this scope.

Commit/push rule: commits and pushes are allowed only for this bounded implementation slice, after local validation. Keep unrelated dirty state unstaged.

Expiry/completion condition: this authorization expires when the working tree is clean for the scoped files, validation evidence is recorded, and the scoped commit(s) are pushed, or when Andrew narrows/stops the scope.
