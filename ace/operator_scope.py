from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ACE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = ACE_DIR.parent
DEFAULT_AUTHORIZATION_PATH = ACE_DIR / "state" / "v1_1_required_items" / "authorization.json"
BLOCK_LOG_PATH = ACE_DIR / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"

READ_ONLY_ACTIONS = frozenset({"read", "status", "inspect", "diff", "log"})
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


class OperatorScopeError(Exception):
    """Base exception for operator scope policy errors."""


class OperatorScopeInvalid(OperatorScopeError):
    """Raised when the durable operator scope file is invalid."""


class OperatorScopeDenied(OperatorScopeError):
    """Raised when an action is outside the active operator scope."""


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    reason: str
    mode: str | None = None
    scope_hash: str | None = None


@dataclass(frozen=True)
class OperatorAction:
    action_class: str
    paths: tuple[str, ...] = ()
    command: str | None = None
    destination: str | None = None
    description: str | None = None

    def normalized_paths(self) -> tuple[str, ...]:
        return tuple(_normalize_repo_path(path) for path in self.paths)


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

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OperatorAuthorization":
        mode = _required_text(data, "mode")
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

        if not _is_expected_hash(data, scope_hash):
            raise OperatorScopeInvalid("scope_hash does not match authorization content")
        unknown_actions = set(allowed_actions) - ALL_ACTIONS
        unknown_actions.update(set(denied_actions) - ALL_ACTIONS)
        if unknown_actions:
            raise OperatorScopeInvalid("unknown action classes: " + ",".join(sorted(unknown_actions)))
        _parse_iso_timestamp(issued_at, field_name="issued_at")
        if expires_at is not None:
            _parse_iso_timestamp(expires_at, field_name="expires_at")

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
        )

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        return _parse_iso_timestamp(self.expires_at, field_name="expires_at") <= datetime.now(timezone.utc)

    def evaluate(self, action: OperatorAction) -> ScopeDecision:
        if self.expired:
            return ScopeDecision(False, "operator authorization expired", self.mode, self.scope_hash)
        if action.action_class not in ALL_ACTIONS:
            return ScopeDecision(False, f"unknown action class {action.action_class}", self.mode, self.scope_hash)
        if action.action_class in self.denied_actions:
            return ScopeDecision(False, f"action class {action.action_class} is explicitly denied", self.mode, self.scope_hash)
        paths = action.normalized_paths()
        for path in paths:
            if _matches_any(path, self.denied_paths):
                return ScopeDecision(False, f"path {path} is explicitly denied", self.mode, self.scope_hash)

        if action.action_class in READ_ONLY_ACTIONS:
            return ScopeDecision(True, "read-only action allowed", self.mode, self.scope_hash)

        if action.action_class not in self.allowed_actions:
            return ScopeDecision(False, f"action class {action.action_class} is not allowed", self.mode, self.scope_hash)
        if paths:
            disallowed = [path for path in paths if not _matches_any(path, self.allowed_paths)]
            if disallowed:
                return ScopeDecision(False, "paths not allowed: " + ",".join(disallowed), self.mode, self.scope_hash)
        if action.action_class == "external_send" and action.destination is None:
            return ScopeDecision(False, "external_send requires a destination", self.mode, self.scope_hash)
        if action.command is not None and self.allowed_commands:
            if action.command not in self.allowed_commands:
                return ScopeDecision(False, "command is not in allowed_commands", self.mode, self.scope_hash)
        if action.destination is not None:
            if action.destination not in self.allowed_external_destinations:
                return ScopeDecision(False, "external destination is not allowed", self.mode, self.scope_hash)
        return ScopeDecision(True, "action allowed by operator authorization", self.mode, self.scope_hash)


def load_authorization(path: Path | str = DEFAULT_AUTHORIZATION_PATH) -> OperatorAuthorization:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OperatorScopeInvalid(f"operator authorization file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OperatorScopeInvalid(f"operator authorization file is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise OperatorScopeInvalid("operator authorization root must be an object")
    return OperatorAuthorization.from_mapping(data)


def evaluate_action(
    action: OperatorAction,
    *,
    authorization_path: Path | str = DEFAULT_AUTHORIZATION_PATH,
) -> ScopeDecision:
    authorization = load_authorization(authorization_path)
    return authorization.evaluate(action)


def require_action(
    action: OperatorAction,
    *,
    authorization_path: Path | str = DEFAULT_AUTHORIZATION_PATH,
    block_log_path: Path | str = BLOCK_LOG_PATH,
) -> ScopeDecision:
    try:
        decision = evaluate_action(action, authorization_path=authorization_path)
    except OperatorScopeInvalid as exc:
        decision = ScopeDecision(False, str(exc))
    if not decision.allowed:
        append_block_log(action, decision, block_log_path=block_log_path)
        raise OperatorScopeDenied(decision.reason)
    return decision


def append_block_log(
    action: OperatorAction,
    decision: ScopeDecision,
    *,
    block_log_path: Path | str = BLOCK_LOG_PATH,
) -> None:
    path = Path(block_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "allowed": decision.allowed,
        "reason": decision.reason,
        "mode": decision.mode,
        "scope_hash": decision.scope_hash,
        "action_class": action.action_class,
        "paths": list(action.normalized_paths()),
        "command": action.command,
        "destination": action.destination,
        "description": action.description,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def compute_scope_hash(data: Mapping[str, Any]) -> str:
    material = {key: value for key, value in data.items() if key != "scope_hash"}
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_authorization_template(
    *,
    mode: str,
    approval_ref: str,
    issued_by: str,
    issued_at: str,
    expires_at: str | None,
    allowed_actions: Iterable[str] = (),
    allowed_paths: Iterable[str] = (),
    denied_actions: Iterable[str] = (),
    denied_paths: Iterable[str] = (),
    allowed_commands: Iterable[str] = (),
    allowed_external_destinations: Iterable[str] = (),
) -> str:
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
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    text = _optional_text(value, key)
    if text is None:
        raise OperatorScopeInvalid(f"{key} is required")
    return text


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OperatorScopeInvalid(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise OperatorScopeInvalid(f"{field_name} must not be empty")
    return normalized


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise OperatorScopeInvalid(f"{field_name} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise OperatorScopeInvalid(f"{field_name}[{index}] must be a non-empty string")
        result.append(item.strip())
    return tuple(result)


def _is_expected_hash(data: Mapping[str, Any], scope_hash: str) -> bool:
    return scope_hash == compute_scope_hash(data)


def _parse_iso_timestamp(value: str, *, field_name: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OperatorScopeInvalid(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise OperatorScopeInvalid(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_repo_path(path: str) -> str:
    candidate = Path(path)
    if candidate.parts and candidate.parts[0] == "..":
        raise OperatorScopeInvalid(f"path is outside workspace: {path}")
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(WORKSPACE_ROOT.resolve())
        except ValueError as exc:
            raise OperatorScopeInvalid(f"path is outside workspace: {path}") from exc
    normalized = candidate.as_posix().lstrip("./")
    if normalized == ".." or normalized.startswith("../"):
        raise OperatorScopeInvalid(f"path is outside workspace: {path}")
    return normalized or "."


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)
