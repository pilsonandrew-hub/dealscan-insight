# ACE operator-scope Git hooks

Status: Slice 3 tracked hook sources. Activation is operator-owned.

These hooks are local workflow guards for the current clone. They are **not** security boundaries.

## Activation

The operator activates them once per clone:

```sh
sh ace/hooks/install.sh
```

The installer sets:

```sh
git config core.hooksPath ace/hooks
```

Running the installer on the live workspace and verifying hook activation are operator-owned tasks, not agent-owned tasks.

## Hooks

- `pre-commit` — reads `ace/state/v1_1_required_items/authorization.json`, validates hash/mode/expiry through `ace.scope_guard`, inspects staged paths, and refuses unauthorized commits before the commit is created.
- `commit-msg` — requires an `Operator-Scope:` trailer on commits governed by this scope and appends a refusal record when missing.
- `pre-push` — inspects outgoing protected paths and refuses unauthorized pushes before refs are updated remotely.
- `pre-rebase` — treats rebases as `git_rewrite` and refuses unless explicitly authorized.
- `post-checkout` — validates the authorization file after checkout and warns if invalid; it does not block checkout because post-checkout runs after the fact.

Refusals append JSONL evidence to:

```text
ace/state/v1_1_required_items/operator-scope-block-log.jsonl
```

## Honest limitation

These hooks are bypassable via:

- `--no-verify`
- alternate clones
- direct `.git/hooks` or `core.hooksPath` override
- direct object/ref manipulation outside normal Git commands

That is expected. Hooks are workflow guards, not enforcement-grade security boundaries.

The security boundary comes from Slice 4 command wrappers plus operator-owned filesystem permissions, credential separation, and branch protection.
