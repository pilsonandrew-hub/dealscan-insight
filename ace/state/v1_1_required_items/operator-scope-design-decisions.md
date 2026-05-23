# Operator Scope Enforcement Design Decisions — ACE V1.1 Item 3

Status: Slice 5 decision record. This file records operator-approved design choices for ACE V1.1 Item 3 operator-scope enforcement.

Primary references:

- Design V2: `ace/state/v1_1_required_items/operator-scope-enforcement-design-v2.md`
- Design V2 commit: `d90fbbf` (`ace: revise concrete operator scope enforcement design`)
- Consultation artifact: `ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md`
- Consultation sources: Claude-style fallback recommendation, live Gemini recommendation, and DeepSeek-style recommendation recorded in the three-model consultation artifact.
- Durable operator anchor: `ace/state/v1_1_required_items/current-operator-instruction.md`

## Decision 1 — Strict deny-by-default

Choice made:

- ACE operator-scope enforcement uses strict deny-by-default for side-effecting actions.
- If an action class, path, command, destination, or scope file state is ambiguous, missing, expired, malformed, or outside the active authorization, the action is refused before the side effect.

Trade-off accepted:

- This will slow down some legitimate work and create more explicit approval/update steps.
- It may block useful actions during incomplete or stale authorization windows.
- It favors false negatives over accidental execution.

Rationale:

- The documented bypass pattern came from treating conversational intent as enough authority and proceeding through generic tool access.
- Strict deny-by-default is the cleanest way to make durable scope the authority instead of agent judgment.
- The three-model consultation converged on pessimistic conflict resolution: when active context and durable scope conflict, durable scope wins.

## Decision 2 — Scope-based bulk approval with narrow bounds

Choice made:

- Use scope-based bulk approval, not per-action approval for every single write.
- Each scope grant must be narrow: explicit mode, objective, allowed paths, allowed action classes, denied actions/paths, expiry, and operator reference.
- Commits for scoped work must reference the active operator scope via an `Operator-Scope` trailer where applicable.

Trade-off accepted:

- Scope-based approval is less granular than approving every individual action.
- A poorly written scope could still authorize too much.
- The operator must keep scope text precise, and the implementation must fail closed when scope is unclear.

Rationale:

- Per-action approval would create too much operational drag for normal engineering slices.
- Narrow bulk scopes preserve execution flow while still preventing unrelated implementation, external sends, credential access, DB mutation, and scope expansion.
- This matches the consultation recommendation to make “proposal only,” “investigation only,” and “implementation approved” machine-distinguishable.

## Decision 3 — Default expiries

Choice made:

Default expiry model:

- Investigation: no expiry, because it allows no side effects.
- Consultation: 1 hour.
- Implementation: 1 hour, renewable by operator scope update.
- External sends: 15 minutes and single-use unless explicitly stated otherwise.

Trade-off accepted:

- Short expiries can interrupt work and require renewal.
- Long-running implementation may need multiple operator refreshes.
- External-send flows become deliberately more ceremonial.

Rationale:

- The bypass incidents clustered around stale or over-broad conversational context.
- Expiry prevents an old permission from silently carrying forward into a different session, compaction state, or agent run.
- External sends have higher privacy and operator-trust risk, so their authorization window is intentionally shortest.

## Decision 4 — Side-effect class list approved as proposed

Choice made:

- The side-effect classes from Design V2 Section 5.4 are approved as-is for ACE V1.1 Item 3 enforcement.
- Covered classes include file writes/edits/deletes, git stage/commit/push/rewrite, DB mutation, external sends, credential reads, config changes, gateway restarts, subagent mutation, side-effecting tests, and cron mutation.

Trade-off accepted:

- The list is broader than a minimal ACE-only guard.
- Some actions that feel routine, such as tests or git operations, require explicit classification.
- Future action classes may need explicit additions instead of being assumed safe.

Rationale:

- The consultation identified the real failure mode as Javarious/OpenClaw tool-layer bypass, not only ACE-internal code paths.
- Broad classification is necessary because the bypasses used general tool capabilities: file edits, shell/git, direct state mutation, and implementation commits.
- Treating side effects as named classes gives hooks, wrappers, and ACE code paths a shared policy language.

## Decision 5 — Tiered denial behavior

Choice made:

Tiered denial behavior:

- Low-risk denial: block the specific action.
- Medium-risk denial: require plan revision before continuing.
- High-risk denial: pause the session for operator acknowledgement.

Trade-off accepted:

- The agent must stop more often on high-risk work.
- Medium-risk work gains an extra planning step.
- Some denials require operator attention even when the intended work is legitimate.

Rationale:

- Not all denied actions have the same risk. Reading an unapproved path is not equivalent to credential access, DB mutation, external sends, config changes, or history rewrite.
- The tiering keeps low-risk blocks lightweight while forcing explicit human review where harm or trust damage is highest.
- This matches the Design V2 goal: prevent repeated bypasses without turning every blocked action into identical noise.

## Final status of these decisions

These five decisions are operator-approved for ACE V1.1 Item 3. They are recorded here as the durable decision reference for the scope guard, ACE write-path integration, tracked hooks, guarded command wrappers, and any later operator-owned infrastructure controls.
