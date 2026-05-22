from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

ACE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = ACE_DIR.parent
DEFAULT_AUTHORIZATION_PATH = ACE_DIR / "state" / "v1_1_required_items" / "authorization.json"
DEFAULT_BLOCK_LOG_PATH = ACE_DIR / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"

READ_ONLY_ACTIONS = frozenset({"read", "inspect", "status", "diff", "log"})
SIDE_EFFECT_ACTIONS = frozenset(
    {
        "file_write",
        "file_edit",
        "file_delete",
        "git_stage",
        "git_commit",
        "git_push",
        "git_rewrite",
        "db_mutation",
        "external_send",
        "credential_read",
        "config_change",
        "gateway_restart",
        "subagent_mutating",
        "test_side_effecting",
        "cron_mutation",
    }
)
ALL_ACTIONS = READ_ONLY_ACTIONS | SIDE_EFFECT_ACTIONS

APPROVED_MODES = frozenset(
    {
        "investigation_only",
        "consultation_only",
        "proposal_only",
        "implementation_approved",
        "breach_disclosure_only",
        "external_send_approved",
    }
)

HIGH_RISK_ACTIONS = frozenset(
    {
        "db_mutation",
        "external_send",
        "credential_read",
        "config_change",
        "gateway_restart",
        "git_rewrite",
        "cron_mutation",
    }
)
MEDIUM_RISK_ACTIONS = frozenset(
    {"git_stage", "git_commit", "git_push", "file_write", "file_edit", "file_delete", "test_side_effecting", "subagent_mutating"}
)


class ScopeDecisionType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ScopeGuardError(Exception):
    """Base error for operator-scope guard failures."""


class ScopeAuthorizationInvalid(ScopeGuardError):
    """Raised when the durable authorization file is invalid."""


@dataclass(frozen=True)
class ScopeAction:
    action_class: str
    paths: tuple[str, ...] = ()
    command: str | None = None
    destination: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ScopeDecision:
    decision: ScopeDecisionType
    reason: str
    severity: str
    mode: str | None = None
    scope_hash: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is ScopeDecisionType.ALLOW


@dataclass(frozen=True)
class OperatorAuthorization:
    mode: str
    approval_ref: str
    issued_by: str
    issued_at: str
    expires_at: str | None
    allowed_actions: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    denied_actions: tuple[str, ...]
    denied_paths: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    allowed_external_destinations: tuple[str, ...]
    scope_hash: str
    raw: Mapping[str, Any]
    workspace_root: Path = WORKSPACE_ROOT

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        workspace_root: Path = WORKSPACE_ROOT,
    ) -> "OperatorAuthorization":
        mode = _required_text(data, "mode")
        if mode not in APPROVED_MODES:
            raise ScopeAuthorizationInvalid(f"unknown mode: {mode}")

        approval_ref = _required_text(data, "approval_ref")
        issued_by = _required_text(data, "issued_by")
        issued_at = _required_text(data, "issued_at")
        expires_at = _optional_text(data.get("expires_at"), "expires_at")
        allowed_actions = _string_tuple(data.get("allowed_actions", ()), "allowed_actions")
        allowed_paths = _string_tuple(data.get("allowed_paths", ()), "allowed_paths")
        denied_actions = _string_tuple(data.get("denied_actions", ()), "denied_actions")
        denied_paths = _string_tuple(data.get("denied_paths", ()), "denied_paths")
        allowed_commands = _string_tuple(data.get("allowed_commands", ()), "allowed_commands")
        allowed_external_destinations = _string_tuple(
            data.get("allowed_external_destinations", ()), "allowed_external_destinations"
        )
        scope_hash = _required_text(data, "scope_hash")

        unknown_actions = (set(allowed_actions) | set(denied_actions)) - ALL_ACTIONS
        if unknown_actions:
            raise ScopeAuthorizationInvalid("unknown action classes: " + ",".join(sorted(unknown_actions)))
        for field_name, patterns in (("allowed_paths", allowed_paths), ("denied_paths", denied_paths)):
            for pattern in patterns:
                _validate_path_pattern(pattern, field_name=field_name, workspace_root=workspace_root)
        _parse_timestamp(issued_at, field_name="issued_at")
        if expires_at is not None:
            _parse_timestamp(expires_at, field_name="expires_at")
        if not _hash_matches(data, scope_hash):
            raise ScopeAuthorizationInvalid("scope_hash does not match authorization content")

        return cls(
            mode=mode,
            approval_ref=approval_ref,
            issued_by=issued_by,
            issued_at=issued_at,
            expires_at=expires_at,
            allowed_actions=allowed_actions,
            allowed_paths=allowed_paths,
            denied_actions=denied_actions,
            denied_paths=denied_paths,
            allowed_commands=allowed_commands,
            allowed_external_destinations=allowed_external_destinations,
            scope_hash=scope_hash,
            raw=dict(data),
            workspace_root=workspace_root,
        )

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        return _parse_timestamp(self.expires_at, field_name="expires_at") <= datetime.now(timezone.utc)

    def evaluate(self, action: ScopeAction) -> ScopeDecision:
        severity = _severity_for_action(action.action_class)
        if self.expired:
            return ScopeDecision(
                ScopeDecisionType.REQUIRE_APPROVAL,
                "operator authorization expired",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.action_class not in ALL_ACTIONS:
            return ScopeDecision(
                ScopeDecisionType.BLOCK,
                f"unknown action class: {action.action_class}",
                "medium",
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.action_class in self.denied_actions:
            return ScopeDecision(
                _denial_decision(action.action_class),
                f"action class denied: {action.action_class}",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.action_class in READ_ONLY_ACTIONS:
            return ScopeDecision(
                ScopeDecisionType.ALLOW,
                "read-only action allowed",
                "low",
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.action_class not in self.allowed_actions:
            return ScopeDecision(
                _denial_decision(action.action_class),
                f"action class not allowed: {action.action_class}",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        denied_path = _first_matching_path(action.paths, self.denied_paths, workspace_root=self.workspace_root)
        if denied_path is not None:
            return ScopeDecision(
                _denial_decision(action.action_class),
                f"path denied: {denied_path}",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.paths and not _all_paths_match(action.paths, self.allowed_paths, workspace_root=self.workspace_root):
            return ScopeDecision(
                _denial_decision(action.action_class),
                "path outside allowed scope",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        if action.action_class == "external_send":
            if not action.destination:
                return ScopeDecision(
                    ScopeDecisionType.REQUIRE_APPROVAL,
                    "external send requires named destination",
                    "high",
                    mode=self.mode,
                    scope_hash=self.scope_hash,
                )
            if action.destination not in self.allowed_external_destinations:
                return ScopeDecision(
                    ScopeDecisionType.REQUIRE_APPROVAL,
                    "external destination not allowed",
                    "high",
                    mode=self.mode,
                    scope_hash=self.scope_hash,
                )
        if action.command and self.allowed_commands and action.command not in self.allowed_commands:
            return ScopeDecision(
                _denial_decision(action.action_class),
                "command not allowed",
                severity,
                mode=self.mode,
                scope_hash=self.scope_hash,
            )
        return ScopeDecision(
            ScopeDecisionType.ALLOW,
            "action allowed by operator authorization",
            severity,
            mode=self.mode,
            scope_hash=self.scope_hash,
        )


class ScopeGuard:
    def __init__(
        self,
        authorization_path: Path | str = DEFAULT_AUTHORIZATION_PATH,
        block_log_path: Path | str = DEFAULT_BLOCK_LOG_PATH,
        workspace_root: Path | str = WORKSPACE_ROOT,
    ) -> None:
        self.authorization_path = Path(authorization_path)
        self.block_log_path = Path(block_log_path)
        self.workspace_root = Path(workspace_root).resolve()

    def load(self) -> OperatorAuthorization:
        if not self.authorization_path.exists():
            raise ScopeAuthorizationInvalid(f"authorization file missing: {self.authorization_path}")
        with self.authorization_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ScopeAuthorizationInvalid("authorization file must contain a JSON object")
        return OperatorAuthorization.from_mapping(data, workspace_root=self.workspace_root)

    def authorize(self, action: ScopeAction, *, log_block: bool = True) -> ScopeDecision:
        authorization = self.load()
        decision = authorization.evaluate(action)
        if decision.decision is not ScopeDecisionType.ALLOW and log_block:
            self.log_block(action, decision)
        return decision

    def log_block(self, action: ScopeAction, decision: ScopeDecision) -> None:
        self.block_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "decision": decision.decision.value,
            "reason": decision.reason,
            "severity": decision.severity,
            "mode": decision.mode,
            "scope_hash": decision.scope_hash,
            "action_class": action.action_class,
            "paths": list(action.paths),
            "command": action.command,
            "destination": action.destination,
            "description": action.description,
        }
        with self.block_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def authorize_scope_action(
    action_class: str,
    *,
    paths: Sequence[str] = (),
    command: str | None = None,
    destination: str | None = None,
    description: str | None = None,
    guard: ScopeGuard | None = None,
) -> ScopeDecision:
    active_guard = guard or ScopeGuard()
    return active_guard.authorize(
        ScopeAction(
            action_class,
            paths=tuple(paths),
            command=command,
            destination=destination,
            description=description,
        )
    )


def require_scope_action(
    action_class: str,
    *,
    paths: Sequence[str] = (),
    command: str | None = None,
    destination: str | None = None,
    description: str | None = None,
    guard: ScopeGuard | None = None,
) -> ScopeDecision:
    decision = authorize_scope_action(
        action_class,
        paths=paths,
        command=command,
        destination=destination,
        description=description,
        guard=guard,
    )
    if not decision.allowed:
        raise ScopeGuardError(f"{decision.decision.value}: {decision.reason}")
    return decision


def render_authorization(
    *,
    mode: str,
    approval_ref: str,
    issued_by: str,
    issued_at: str,
    expires_at: str | None,
    allowed_actions: Sequence[str] = (),
    allowed_paths: Sequence[str] = (),
    denied_actions: Sequence[str] = (),
    denied_paths: Sequence[str] = (),
    allowed_commands: Sequence[str] = (),
    allowed_external_destinations: Sequence[str] = (),
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "mode": mode,
        "approval_ref": approval_ref,
        "issued_by": issued_by,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "allowed_actions": list(allowed_actions),
        "allowed_paths": list(allowed_paths),
        "denied_actions": list(denied_actions),
        "denied_paths": list(denied_paths),
        "allowed_commands": list(allowed_commands),
        "allowed_external_destinations": list(allowed_external_destinations),
    }
    data["scope_hash"] = compute_scope_hash(data)
    return data


def compute_scope_hash(data: Mapping[str, Any]) -> str:
    canonical = dict(data)
    canonical.pop("scope_hash", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_matches(data: Mapping[str, Any], expected_hash: str) -> bool:
    return compute_scope_hash(data) == expected_hash


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    return _coerce_text(value, key, required=True)


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _coerce_text(value, field_name, required=False)


def _coerce_text(value: Any, field_name: str, *, required: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        if required:
            raise ScopeAuthorizationInvalid(f"{field_name} is required")
        raise ScopeAuthorizationInvalid(f"{field_name} must be text")
    return value


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ScopeAuthorizationInvalid(f"{field_name} must be a list")
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise ScopeAuthorizationInvalid(f"{field_name} entries must be non-empty text")
        result.append(entry)
    return tuple(result)


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ScopeAuthorizationInvalid(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ScopeAuthorizationInvalid(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _validate_path_pattern(pattern: str, *, field_name: str, workspace_root: Path = WORKSPACE_ROOT) -> None:
    normalized = _normalize_workspace_path(pattern, workspace_root=workspace_root)
    if normalized.startswith("../") or normalized == ".." or Path(pattern).is_absolute():
        raise ScopeAuthorizationInvalid(f"{field_name} entry outside workspace: {pattern}")


def _normalize_workspace_path(path: str, *, workspace_root: Path = WORKSPACE_ROOT) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(workspace_root).as_posix()
        except ValueError as exc:
            raise ScopeAuthorizationInvalid(f"path outside workspace: {path}") from exc
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                raise ScopeAuthorizationInvalid(f"path outside workspace: {path}")
        else:
            parts.append(part)
    return "/".join(parts)


def _first_matching_path(
    paths: Sequence[str],
    patterns: Sequence[str],
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> str | None:
    for path in paths:
        normalized = _normalize_workspace_path(path, workspace_root=workspace_root)
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns):
            return normalized
    return None


def _all_paths_match(
    paths: Sequence[str],
    patterns: Sequence[str],
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> bool:
    if not patterns:
        return False
    for path in paths:
        normalized = _normalize_workspace_path(path, workspace_root=workspace_root)
        if not any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns):
            return False
    return True


def _severity_for_action(action_class: str) -> str:
    if action_class in HIGH_RISK_ACTIONS:
        return "high"
    if action_class in MEDIUM_RISK_ACTIONS:
        return "medium"
    return "low"


def _denial_decision(action_class: str) -> ScopeDecisionType:
    if action_class in HIGH_RISK_ACTIONS:
        return ScopeDecisionType.REQUIRE_APPROVAL
    return ScopeDecisionType.BLOCK
