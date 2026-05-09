from __future__ import annotations

import unittest

from ace.workflow import (
    CloseoutGateError,
    IllegalTransitionError,
    InvalidConfidenceTierError,
    InvalidContradictionStatusError,
    InvalidNewContradictionStatusError,
    InvalidVerdictError,
    UnknownStateError,
    closeout_gate,
    is_legacy_tolerated_state,
    is_terminal_contradiction_status,
    is_terminal_obligation_status,
    next_state,
    normalize_action,
    normalize_confidence_tier,
    normalize_contradiction_status,
    normalize_new_contradiction_status,
    normalize_state,
    normalize_verdict,
)


class WorkflowContractTests(unittest.TestCase):
    def test_normalize_state_trims_and_uppercases(self) -> None:
        self.assertEqual(normalize_state(" triage "), "TRIAGE")
        self.assertEqual(normalize_state("approved"), "APPROVED")
        self.assertEqual(normalize_state(" active "), "ACTIVE")

    def test_normalize_state_rejects_unknown_state(self) -> None:
        with self.assertRaises(UnknownStateError):
            normalize_state("unknown")

    def test_normalize_action_trims_and_lowercases(self) -> None:
        self.assertEqual(normalize_action(" APPROVE "), "approve")
        self.assertEqual(normalize_action("Resolve"), "resolve")

    def test_normalize_action_rejects_empty_command(self) -> None:
        with self.assertRaises(IllegalTransitionError):
            normalize_action("   ")

    def test_next_state_allows_canonical_legal_transitions(self) -> None:
        self.assertEqual(next_state("TRIAGE", "approve"), "APPROVED")
        self.assertEqual(next_state("APPROVED", "done"), "CLAIMED_DONE")
        self.assertEqual(next_state("CLAIMED_DONE", "resolve"), "VERIFIED_DONE")
        self.assertEqual(next_state("BLOCKED", "resolve"), "APPROVED")
        self.assertEqual(next_state("ACTIVE", "done"), "CLAIMED_DONE")

    def test_next_state_rejects_illegal_transition_with_legal_actions_listed(self) -> None:
        with self.assertRaisesRegex(
            IllegalTransitionError,
            r"illegal transition: TRIAGE --resolve--> \? \(legal actions: approve, block, drop\)",
        ):
            next_state("TRIAGE", "resolve")

    def test_next_state_rejects_terminal_state_actions_with_none_legal(self) -> None:
        with self.assertRaisesRegex(
            IllegalTransitionError,
            r"illegal transition: VERIFIED_DONE --drop--> \? \(legal actions: none\)",
        ):
            next_state("VERIFIED_DONE", "drop")

    def test_legacy_tolerated_state_detection(self) -> None:
        self.assertTrue(is_legacy_tolerated_state(" active "))
        self.assertFalse(is_legacy_tolerated_state("TRIAGE"))

    def test_normalize_contradiction_status_accepts_open_and_resolved(self) -> None:
        self.assertEqual(normalize_contradiction_status(" OPEN "), "open")
        self.assertEqual(normalize_contradiction_status("resolved"), "resolved")

    def test_normalize_contradiction_status_rejects_invalid_values(self) -> None:
        with self.assertRaises(InvalidContradictionStatusError):
            normalize_contradiction_status("dismissed")

    def test_normalize_new_contradiction_status_only_allows_open(self) -> None:
        self.assertEqual(normalize_new_contradiction_status("open"), "open")
        with self.assertRaises(InvalidNewContradictionStatusError):
            normalize_new_contradiction_status("resolved")

    def test_normalize_confidence_tier_accepts_canonical_values_and_aliases(self) -> None:
        self.assertEqual(normalize_confidence_tier("hypothesis"), "hypothesis")
        self.assertEqual(normalize_confidence_tier("locally validated only"), "locally_validated_only")
        self.assertEqual(normalize_confidence_tier("live-improved-but-pending"), "live_improved_but_pending")
        self.assertEqual(normalize_confidence_tier(" LIVE CONFIRMED "), "live_confirmed")

    def test_normalize_confidence_tier_rejects_invalid_values(self) -> None:
        with self.assertRaises(InvalidConfidenceTierError):
            normalize_confidence_tier("probably_true")

    def test_normalize_verdict_accepts_canonical_values_and_aliases(self) -> None:
        self.assertEqual(normalize_verdict("pass"), "pass")
        self.assertEqual(normalize_verdict(" FAIL "), "fail")
        self.assertEqual(normalize_verdict("pending"), "pending")

    def test_normalize_verdict_rejects_invalid_values(self) -> None:
        with self.assertRaises(InvalidVerdictError):
            normalize_verdict("live_confirmed")

    def test_terminal_obligation_status_helper(self) -> None:
        self.assertTrue(is_terminal_obligation_status(" Resolved "))
        self.assertTrue(is_terminal_obligation_status("done"))
        self.assertFalse(is_terminal_obligation_status("pending"))
        self.assertFalse(is_terminal_obligation_status(None))

    def test_terminal_contradiction_status_helper(self) -> None:
        self.assertTrue(is_terminal_contradiction_status(" satisfied "))
        self.assertTrue(is_terminal_contradiction_status("closed"))
        self.assertFalse(is_terminal_contradiction_status("open"))
        self.assertFalse(is_terminal_contradiction_status(None))

    def test_closeout_gate_blocks_missing_evidence_first(self) -> None:
        allowed, code, detail = closeout_gate(
            evidence_count=0,
            open_obligation_count=5,
            open_contradiction_count=7,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "missing_evidence")
        self.assertEqual(detail, "closeout requires at least one evidence record")

    def test_closeout_gate_blocks_open_contradictions_before_obligations(self) -> None:
        allowed, code, detail = closeout_gate(
            evidence_count=1,
            open_obligation_count=5,
            open_contradiction_count=2,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "open_contradictions")
        self.assertEqual(detail, "closeout blocked by 2 open contradictions")

    def test_closeout_gate_blocks_open_obligations_when_other_gates_clear(self) -> None:
        allowed, code, detail = closeout_gate(
            evidence_count=3,
            open_obligation_count=1,
            open_contradiction_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "open_obligations")
        self.assertEqual(detail, "closeout blocked by 1 open obligation")

    def test_closeout_gate_passes_when_requirements_are_met(self) -> None:
        allowed, code, detail = closeout_gate(
            evidence_count=2,
            open_obligation_count=0,
            open_contradiction_count=0,
        )
        self.assertTrue(allowed)
        self.assertIsNone(code)
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
