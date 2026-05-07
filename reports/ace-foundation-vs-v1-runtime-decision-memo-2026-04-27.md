# ACE Decision Memo — Stay Governed Foundation vs Become V1-Class Runtime

> **Canonical supporting authority artifact**
> Canonical status: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
> Read this memo as a supporting authority artifact together with `ace/README.md`, `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`, `reports/ace-enterprise-status-verdict-2026-05-05.md`, and `reports/ace-phase-truth-matrix-2026-05-05.md`.

Date: 2026-04-27
Status: decision memo

## Grounded baseline
- Main HEAD: `40d9805`
- `test_runtime_ownership`: 10 OK
- `test_resume_runtime`: 7 OK
- `test_resume_recovery_runtime`: 6 OK
- `test_owned_recovery_runtime`: 4 OK
- Full ACE suite: 374 OK

## Current honest state
ACE is a **Governed Foundation / Phase 0 continuity substrate**.
It is:
- local-only
- operator-invoked
- SQLite-backed
- proof-oriented
- bounded to landed seams

It is **not V1**.

## What has been proven
ACE has real bounded proofs across:
- decision/closed-loop seams
- action-runtime seams
- resume/recovery seams
- runtime-ownership seams
- one cross-seam owned-recovery lifecycle
- named interruption replay-healing proofs
- doctrine-level local runtime, authority, confidence, packaging, and local-only V1-within-boundary clarifications

## What has also been proven
Programs and narrow gate lanes repeatedly hit an honest limit:
- Program 1 runtime breadth: blocked on current seam family
- Program 2 operational authority: blocked on current authority surface
- Program 3 failure/recovery breadth: blocked on current bounded proof family
- broader combined runtime ownership + recovery breadth: blocked on the same current seam family

## The real decision
There are now only two honest paths.

# Option A — Keep ACE as a Governed Foundation

## Meaning
Treat ACE as a strong internal substrate with explicit bounded guarantees.
Do not keep chasing V1 through renamed prooflets.
Do not broaden claims beyond the current local-only/runtime-bounded truth.

## Benefits
- preserves truth and trust
- avoids fake maturity inflation
- keeps the system useful without pretending it is a broader runtime product
- prevents wasting cycles on seam-mining that no longer changes the real boundary

## Cost
- ACE remains below V1
- broader runtime/platform/product ambitions are deferred

## Best use case
Choose this if the real value is the current internal foundation and not a sellable/runtime-grade product right now.

# Option B — Deliberately Become a V1-Class Runtime Program

## Meaning
Admit that ACE must change class.
Stop pretending more tiny seam work will get it there.
Open a larger runtime program with new scope, new guarantees, and new acceptance criteria.

## What this would require
At minimum:
1. broader runtime class definition
2. broader ownership/recovery/failure breadth beyond current seam family
3. stronger operational authority model
4. stronger deployment/runtime reality model
5. explicit pass criteria for all hard V1 gates

## Benefits
- creates a real path to an honest V1
- aligns future work to actual missing substance rather than artifact churn

## Cost
- much larger scope
- likely new architecture/runtime expectations
- more expensive and slower
- higher risk of accidental platform inflation unless tightly governed

## Best use case
Choose this only if ACE truly needs to become a broader runtime product rather than remain a powerful local substrate.

## My recommendation
**Option A by default.**

Reason:
- current ACE is already meaningful and credible as a governed foundation
- current seam family has been mined honestly to its limit
- forcing V1 from this surface would likely create false claims before real runtime-class change exists

## When to choose Option B instead
Choose Option B only if you explicitly want to fund and tolerate a larger runtime-class change, not just “continue improving ACE.”

## Decision rule
Ask one question:

**Do we want ACE to remain a trustworthy bounded internal substrate, or do we want it to become a broader runtime product with new classes of guarantees?**

If the answer is:
- **bounded substrate** -> choose Option A and stop the V1 chase
- **broader runtime product** -> choose Option B and open a new runtime-class program deliberately

## Bottom line
ACE is not stuck.
It is at a fork.
The wrong move is pretending the fork does not exist.
The right move is choosing the class of system ACE is supposed to become.
