# A.C.E. V2.3 Drift Dimensions Evidence — 2026-05-13

## Verdict

PASS for the bounded V2.3 drift-dimensions inspection slice.

This is not a V1/V2/V3 platform promotion. It proves only that A.C.E. now exposes the approved V2.3 drift dimensions through a governed inspection surface with tests.

## Source truth

- Source HEAD at verification refresh: `084ca43` (`ace: keep drift on inspect surface`)
- Implementation commits in this V2.3 drift surface:
  - `9cf0bd5` — `ace: add drift dimension inspection`
  - `3185926` — `ace: align drift dimensions with v2.3`
  - `d2eeccf` — `ace: clean drift test naming`
  - `8152440` — `ace: add v2.3 drift evidence`
  - `fc7a59f` — `ace: document drift inspection surface`
  - `084ca43` — `ace: keep drift on inspect surface`
- Implemented source and evidence files:
  - `ace/drift.py`
  - `ace/ace.py`
  - `ace/README.md`
  - `ace/tests/test_drift.py`
  - `ace/tests/test_cli.py`
  - `ace/reports/ace-v2-3-drift-dimensions-evidence-2026-05-13.md`

## Approved dimensions

The implemented inspection surface uses the approved V2.3 names:

1. `loop_depth`
2. `decision_drift`
3. `claim_drift`

A stale source-truth mismatch was corrected: the implementation no longer exposes the earlier intermediate names `decision_distribution` or `state_churn` as active drift dimensions.

## Inspection surface

Command surface:

```bash
python3 -m ace.ace inspect <item_id> --drift-window <positive-int>
```

Acceptance behavior:

- `ace inspect` prints item detail, bounded event history, and drift dimensions.
- `ace show` remains the lower-noise item detail surface and does not print drift dimensions.
- `--drift-window` belongs to `inspect` and must be greater than zero.
- Drift dimensions are computed from repository item events returned in chronological order.

## Dimension behavior

### loop_depth

Detects repeated blocked closeout attempts without state advancement. This is a loop-control dimension, intended to flag churn where work keeps trying the same closure path without progressing.

### decision_drift

Computes decision distribution drift from closeout results and verdict events using Jensen-Shannon distance against the pass-oriented baseline. This is intentionally bounded and transparent; it does not claim statistical maturity beyond the available event window.

### claim_drift

Flags unsupported pass claims: pass verdicts or passed closeouts without prior evidence in the sampled event window. Evidence-backed pass claims clear the dimension.

## Gates required for this slice

Required before calling this slice pass:

1. Focused drift tests pass.
2. CLI inspect tests pass.
3. Full ACE suite passes under warnings-as-errors.
4. Live event hash chain verifies.
5. Git source status is clean except intentionally committed evidence/report changes before commit.

## Explicit non-claims

This slice does not prove:

- raw live Telegram polling acceptance,
- sleep/network-blip resilience,
- broad runtime fabric,
- worker/scheduler control-plane ownership,
- production daemon/service semantics,
- A.C.E. V1/V2/V3 closure.

Those remain separate gates.
