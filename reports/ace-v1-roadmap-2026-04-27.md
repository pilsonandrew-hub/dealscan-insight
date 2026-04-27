# ACE V1 Roadmap — 2026-04-27

## Grounded starting point
- Main HEAD: `40d9805`
- `test_runtime_ownership`: 10 OK
- `test_resume_runtime`: 7 OK
- `test_resume_recovery_runtime`: 6 OK
- `test_owned_recovery_runtime`: 4 OK
- Full ACE suite: 374 OK

## Current honest label
ACE is a **Governed Foundation / Phase 0 continuity substrate**.
It is real, useful, and proof-backed in bounded local seams.
It is **not V1**.

## What “getting to V1” actually means
V1 is not “more tests” and not “more doctrine.”
V1 means all remaining hard gates move from partial/blocked to pass with evidence.

## The four programs that get ACE from foundation to V1

### Program 1 — Runtime Breadth
Goal: prove ACE handles more than a handful of narrow seam cases.

Must achieve:
- at least one more materially distinct cross-seam lifecycle beyond the current owned-recovery family, or
- a broader runtime breadth proof that is not just a renamed clone of existing seams
- broader ownership/recovery/failure breadth with explicit success/failure/replay contracts

Done when:
- Gate 2 is pass, not blocked
- breadth is real in code/tests, not just described in artifacts

### Program 2 — Operational Authority
Goal: define and prove what ACE may actually mutate/own operationally beyond today’s bounded local seam writes.

Must achieve:
- a final authority map for local mutation, write authority, and non-authority
- explicit proof or permanent exclusion for continuity-source writeback
- explicit proof or permanent exclusion for broader operational actions

Done when:
- Gate 3 is pass in the broader sense, not just Gate 3A doctrine-only

### Program 3 — Failure and Recovery Breadth
Goal: prove failure handling is broad enough to trust the system, not just a set of isolated seam cases.

Must achieve:
- broader failure classes than current bounded seam failures
- broader replay/recovery guarantees than the current named interruption proofs
- cross-seam failure behavior that is explicit, inspectable, and non-contradictory

Done when:
- Gate 4 is pass in substance, not only the current Gate 4A doctrine clarification

### Program 4 — Deployment / Runtime Reality
Goal: prove what ACE operationally is as a runnable system beyond local doctrine.

Must achieve one of two honest outcomes:
1. either ACE remains intentionally a local-only operator-invoked system and V1 is defined within that boundary, or
2. ACE deliberately becomes a stronger runtime/deployment model with real proofs to match

Must clarify:
- startup/shutdown truth
- packaging/handoff truth
- deployment/runtime truth
- what is not claimed

Done when:
- Gates 5, 7, and 8 are pass in their broader V1 sense, not only the doctrine-only sub-gates

## Required order
Do not attack everything at once.

### Step 1
Finish the **V1 gate map** and lock each gate to one program owner and one pass criterion.

### Step 2
Open **Program 1 — Runtime Breadth** first.
Reason: it is the biggest missing substance and drives the truth of later gates.

### Step 3
Open **Program 3 — Failure and Recovery Breadth** second.
Reason: broader breadth without broader failure truth would be fragile and misleading.

### Step 4
Open **Program 2 — Operational Authority** third.
Reason: authority claims should be made after breadth/failure truth is real enough to justify them.

### Step 5
Open **Program 4 — Deployment / Runtime Reality** fourth.
Reason: deployment packaging before breadth/authority/failure maturity would overstate the product.

## What to stop doing
To get to V1, stop spending cycles on:
- tiny renamed prooflets
- doctrine churn that does not change a gate outcome
- raising test counts without broadening proof class truth
- trying to sound more mature than the runtime really is

## What a clean weekly execution rhythm should look like
For each active V1 program:
1. one distinctness review
2. one implementation-proof spec
3. one isolated TDD lane
4. one main landing if proven
5. one governed truth update
6. one explicit gate status update: pass / partial / blocked

## Immediate next move
The next real move is:
### Open Program 1 — Runtime Breadth as a bounded execution track

First artifact to write next:
- `reports/ace-v1-program1-runtime-breadth-charter-2026-04-27.md`

First question to answer:
- what is the first materially broader lifecycle or proof family that survives distinctness review without collapsing into an existing seam clone?

## Bottom line
ACE gets to V1 by graduating from a set of bounded local proofs into a broader, explicitly governed runtime system — one gate at a time.
Right now the path is clear, but the work is still ahead.
