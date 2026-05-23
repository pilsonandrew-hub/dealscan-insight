# ACE Guarded Command Wrappers

Status: Slice 4 implementation artifact for ACE V1.1 operator-scope enforcement.

These wrappers are pre-exec command guards for the Javarious/OpenClaw bypass class. They load the durable authorization file at:

```text
ace/state/v1_1_required_items/authorization.json
```

and append refusal evidence to:

```text
ace/state/v1_1_required_items/operator-scope-block-log.jsonl
```

## Security boundary requirement

These wrappers are a security boundary **only when paired with OpenClaw exec policy** that prevents bypassing them. Operator-owned setup must configure OpenClaw so that:

- `ace/bin/guarded/` is placed before real binaries in the exec PATH.
- Bare shells such as `/bin/sh`, `/bin/bash`, and `/bin/zsh` are denied unless specifically approved.
- Absolute paths to real binaries such as `/usr/bin/git`, `/usr/bin/sqlite3`, `/usr/bin/curl`, and `/usr/bin/python3` are denied unless specifically approved.
- `/usr/bin/env` is denied unless specifically approved.
- Inline eval is restricted by OpenClaw config where available.

OpenClaw config setup, PATH ordering, host approvals, filesystem permissions, and ownership of these wrapper files are operator-driven and intentionally not changed in this slice.

## Covered wrappers

### `git`

Resolves the real binary from `/usr/bin/git`.

Classification:

- `git status`, `git diff`, `git log`, `git show`, `git rev-parse`, `git branch`, `git config` → read-only.
- `git add` → `git_stage`.
- `git commit` → `git_commit`.
- `git push` → `git_push`.
- `git reset`, `git revert`, `git rebase`, `git checkout`, `git switch`, `git merge`, `git cherry-pick`, `git tag`, and unknown write-like commands → `git_rewrite`.

### `sqlite3`

Resolves the real binary from `/usr/bin/sqlite3`.

Classification:

- Proven read-only query text beginning with `select`, `.schema`, `.tables`, or `.indexes`, without write tokens → read-only.
- DDL/DML/transaction/maintenance commands such as `insert`, `update`, `delete`, `create`, `drop`, `alter`, `pragma`, `vacuum`, `attach`, `detach`, `begin`, `commit`, `rollback` → `db_mutation`.
- Empty or unclassified SQLite invocation fails closed as `db_mutation`.

### `curl`

Resolves the real binary from `/usr/bin/curl`.

Classification:

- Telegram Bot API send endpoints and explicit POST-like invocations → `external_send`.
- Other URL fetches → read-only.

### `python3`

Resolves the real binary from `/usr/bin/python3`.

Classification:

- `-c` and `-m` inline/module execution → `test_side_effecting` unless specifically authorized.
- Commands that look like test execution (`unittest`, `pytest`, `ace.tests`, `/tests/`) → `test_side_effecting`.
- Other script invocations → read-only by default in this wrapper layer.

## Still bypassable without operator-owned controls

These wrappers do not stop:

- Direct OpenClaw filesystem tools (`write`, `edit`, `apply_patch`) unless tool-layer policy/plugin enforcement is also active.
- Direct invocation of absolute real binaries if OpenClaw exec allowlist permits them.
- Bare shell or `/usr/bin/env` execution if OpenClaw exec allowlist permits them.
- Running from a different clone/path that does not use this wrapper directory.
- OS-level users who can modify the wrapper files or authorization file.
- Network sends made through other tools (`message`, browser automation, custom plugins) unless those tools are independently gated.

The intended enterprise boundary is layered: durable authorization file + OpenClaw exec allowlist + wrapper PATH precedence + filesystem ownership/permissions + branch protection + CI.
