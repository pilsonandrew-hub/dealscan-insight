from __future__ import annotations


CANONICAL_STATES = ("TRIAGE", "APPROVED", "CLAIMED_DONE", "VERIFIED_DONE")
LEGACY_TOLERATED_STATES = ("ACTIVE",)
TERMINAL_STATES = ("VERIFIED_DONE", "DROPPED")

LEGAL_TRANSITIONS: dict[str, dict[str, str]] = {
    "TRIAGE": {
        "approve": "APPROVED",
        "block": "BLOCKED",
        "drop": "DROPPED",
    },
    "ACTIVE": {
        "approve": "APPROVED",
        "done": "CLAIMED_DONE",
        "block": "BLOCKED",
        "drop": "DROPPED",
    },
    "APPROVED": {
        "done": "CLAIMED_DONE",
        "block": "BLOCKED",
        "drop": "DROPPED",
    },
    "BLOCKED": {
        "resolve": "APPROVED",
        "drop": "DROPPED",
    },
    "CLAIMED_DONE": {
        "resolve": "VERIFIED_DONE",
        "block": "BLOCKED",
        "drop": "DROPPED",
    },
    "VERIFIED_DONE": {},
    "DROPPED": {},
}

OPEN_OBLIGATION_TERMINAL_STATUSES = {
    "complete",
    "closed",
    "done",
    "resolved",
    "satisfied",
}

VALID_CONTRADICTION_STATUSES = {
    "open",
    "resolved",
}

OPEN_CONTRADICTION_TERMINAL_STATUSES = {
    "resolved",
    "closed",
    "done",
    "satisfied",
}

VALID_NEW_CONTRADICTION_STATUSES = {
    "open",
}

VALID_CONFIDENCE_TIERS = (
    "hypothesis",
    "locally_validated_only",
    "live_improved_but_pending",
    "live_confirmed",
)

VALID_VERDICTS = (
    "pending",
    "pass",
    "fail",
)


class AceError(Exception):
    """Base class for ACE workflow failures."""


class UnknownStateError(AceError):
    """Raised when a state is not part of the explicit contract."""


class IllegalTransitionError(AceError):
    """Raised when a requested command is not legal from the current state."""


class CloseoutGateError(AceError):
    """Raised when CLAIMED_DONE cannot legally advance to VERIFIED_DONE."""


class InvalidContradictionStatusError(AceError):
    """Raised when a contradiction status is outside the explicit ACE contract."""


class InvalidNewContradictionStatusError(AceError):
    """Raised when a new contradiction is created in an illegal initial state."""


class InvalidConfidenceTierError(AceError):
    """Raised when a confidence tier is outside the explicit ACE contract."""


class InvalidVerdictError(AceError):
    """Raised when a verdict is outside the explicit ACE contract."""


def normalize_state(state: str) -> str:
    normalized = state.strip().upper()
    if normalized not in LEGAL_TRANSITIONS:
        raise UnknownStateError(f"unknown item state: {state}")
    return normalized


def normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    if not normalized:
        raise IllegalTransitionError("empty command is not allowed")
    return normalized


def next_state(current_state: str, action: str) -> str:
    normalized_state = normalize_state(current_state)
    normalized_action = normalize_action(action)
    transitions = LEGAL_TRANSITIONS[normalized_state]
    try:
        return transitions[normalized_action]
    except KeyError as exc:
        legal = ", ".join(sorted(transitions)) or "none"
        raise IllegalTransitionError(
            f"illegal transition: {normalized_state} --{normalized_action}--> ? (legal actions: {legal})"
        ) from exc


def is_legacy_tolerated_state(state: str) -> bool:
    return state.strip().upper() in LEGACY_TOLERATED_STATES


def normalize_contradiction_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in VALID_CONTRADICTION_STATUSES:
        legal = ", ".join(sorted(VALID_CONTRADICTION_STATUSES))
        raise InvalidContradictionStatusError(
            f"invalid contradiction status: {status} (legal statuses: {legal})"
        )
    return normalized


def normalize_new_contradiction_status(status: str) -> str:
    normalized = normalize_contradiction_status(status)
    if normalized not in VALID_NEW_CONTRADICTION_STATUSES:
        legal = ", ".join(sorted(VALID_NEW_CONTRADICTION_STATUSES))
        raise InvalidNewContradictionStatusError(
            f"invalid contradiction status: {status} (legal creation statuses: {legal})"
        )
    return normalized


def is_terminal_obligation_status(status: str | None) -> bool:
    return (status or "").strip().lower() in OPEN_OBLIGATION_TERMINAL_STATUSES


def is_terminal_contradiction_status(status: str | None) -> bool:
    return (status or "").strip().lower() in OPEN_CONTRADICTION_TERMINAL_STATUSES


def normalize_confidence_tier(tier: str) -> str:
    normalized = tier.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in VALID_CONFIDENCE_TIERS:
        legal = ", ".join(VALID_CONFIDENCE_TIERS)
        raise InvalidConfidenceTierError(
            f"invalid confidence tier: {tier} (legal tiers: {legal})"
        )
    return normalized


def normalize_verdict(verdict: str) -> str:
    normalized = verdict.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in VALID_VERDICTS:
        legal = ", ".join(VALID_VERDICTS)
        raise InvalidVerdictError(
            f"invalid verdict: {verdict} (legal verdicts: {legal})"
        )
    return normalized


def closeout_gate(
    evidence_count: int,
    open_obligation_count: int,
    open_contradiction_count: int = 0,
    verdict: str | None = None,
) -> tuple[bool, str | None, str | None]:
    if evidence_count <= 0:
        return False, "missing_evidence", "closeout requires at least one evidence record"
    if open_contradiction_count > 0:
        suffix = "s" if open_contradiction_count != 1 else ""
        return (
            False,
            "open_contradictions",
            f"closeout blocked by {open_contradiction_count} open contradiction{suffix}",
        )
    if open_obligation_count > 0:
        suffix = "s" if open_obligation_count != 1 else ""
        return (
            False,
            "open_obligations",
            f"closeout blocked by {open_obligation_count} open obligation{suffix}",
        )
    normalized_verdict = verdict.strip().lower() if verdict else None
    if normalized_verdict == "fail":
        return False, "verdict_fail", "closeout blocked: item verdict is fail"
    if normalized_verdict == "pending":
        return False, "verdict_pending", "closeout blocked: verdict is still pending"
    return True, None, None
