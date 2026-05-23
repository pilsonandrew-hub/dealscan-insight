from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

ATTESTATION_SCHEMA_VERSION = "ace-b2-attestation-v1"
ATTESTATION_CHAIN_ID = "ace-v1.1-post-cutover"
MANIFEST_GENERATOR_VERSION = "ace-attestation-manifest-v1"

_ATTESTATION_FIELDS = (
    "schema_version",
    "chain_id",
    "instance_id",
    "cutover_event_id",
    "event_sequence",
    "event_id",
    "event_hash",
    "previous_event_hash",
    "created_at",
    "manifest_generator_version",
)


class AttestationSchemaError(ValueError):
    """Raised when an attestation record does not match the V1.1 schema."""


@dataclass(frozen=True)
class AttestationRecord:
    schema_version: str
    chain_id: str
    instance_id: str
    cutover_event_id: str
    event_sequence: int
    event_id: str
    event_hash: str
    previous_event_hash: str | None
    created_at: str
    manifest_generator_version: str

    def to_mapping(self) -> dict[str, Any]:
        """Return the exact canonical field set for remote attestation."""

        return {field: getattr(self, field) for field in _ATTESTATION_FIELDS}

    def to_canonical_json(self) -> str:
        return canonical_attestation_json(self)


def canonical_attestation_json(record: AttestationRecord | Mapping[str, Any]) -> str:
    """Serialize one attestation record with deterministic JSON output."""

    mapping = record.to_mapping() if isinstance(record, AttestationRecord) else _canonical_mapping(record)
    return json.dumps(mapping, sort_keys=True, separators=(",", ":"))


def attestation_record_from_event_row(
    row: Mapping[str, Any],
    *,
    instance_id: str,
    cutover_event_id: str,
) -> AttestationRecord:
    """Build a hash-only V1.1 attestation record from a post-cutover event row."""

    _require_text(instance_id, "instance_id")
    _require_text(cutover_event_id, "cutover_event_id")
    event_sequence = _require_positive_int(row.get("event_sequence"), "event_sequence")
    return AttestationRecord(
        schema_version=ATTESTATION_SCHEMA_VERSION,
        chain_id=ATTESTATION_CHAIN_ID,
        instance_id=instance_id,
        cutover_event_id=cutover_event_id,
        event_sequence=event_sequence,
        event_id=_require_text(row.get("event_id"), "event_id"),
        event_hash=_require_text(row.get("event_hash"), "event_hash"),
        previous_event_hash=_optional_text(row.get("previous_event_hash"), "previous_event_hash"),
        created_at=_require_text(row.get("created_at"), "created_at"),
        manifest_generator_version=MANIFEST_GENERATOR_VERSION,
    )


def parse_attestation_record(
    raw_json: str,
    *,
    expected_instance_id: str,
    expected_cutover_event_id: str,
) -> AttestationRecord:
    """Parse and validate a remote attestation record.

    Unknown or missing schema versions fail closed. This intentionally supports no
    forward-compatibility auto-upgrade: a new schema requires an explicit design
    and migration rather than silent comparison under V1.1 rules.
    """

    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise AttestationSchemaError("attestation record JSON is malformed") from exc
    if not isinstance(value, dict):
        raise AttestationSchemaError("attestation record must be a JSON object")
    mapping = _canonical_mapping(value)
    _validate_expected(mapping, expected_instance_id=expected_instance_id, expected_cutover_event_id=expected_cutover_event_id)
    return AttestationRecord(**mapping)


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(value)
    expected = set(_ATTESTATION_FIELDS)
    missing = expected - keys
    extra = keys - expected
    if missing:
        raise AttestationSchemaError(f"attestation record missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise AttestationSchemaError(f"attestation record has unsupported fields: {', '.join(sorted(extra))}")
    mapping = {field: value[field] for field in _ATTESTATION_FIELDS}
    mapping["schema_version"] = _require_exact(mapping["schema_version"], ATTESTATION_SCHEMA_VERSION, "schema_version")
    mapping["chain_id"] = _require_exact(mapping["chain_id"], ATTESTATION_CHAIN_ID, "chain_id")
    mapping["manifest_generator_version"] = _require_exact(
        mapping["manifest_generator_version"],
        MANIFEST_GENERATOR_VERSION,
        "manifest_generator_version",
    )
    mapping["instance_id"] = _require_text(mapping["instance_id"], "instance_id")
    mapping["cutover_event_id"] = _require_text(mapping["cutover_event_id"], "cutover_event_id")
    mapping["event_sequence"] = _require_positive_int(mapping["event_sequence"], "event_sequence")
    mapping["event_id"] = _require_text(mapping["event_id"], "event_id")
    mapping["event_hash"] = _require_text(mapping["event_hash"], "event_hash")
    mapping["previous_event_hash"] = _optional_text(mapping["previous_event_hash"], "previous_event_hash")
    mapping["created_at"] = _require_text(mapping["created_at"], "created_at")
    return mapping


def _validate_expected(mapping: Mapping[str, Any], *, expected_instance_id: str, expected_cutover_event_id: str) -> None:
    if mapping["instance_id"] != expected_instance_id:
        raise AttestationSchemaError("attestation record instance_id mismatch")
    if mapping["cutover_event_id"] != expected_cutover_event_id:
        raise AttestationSchemaError("attestation record cutover_event_id mismatch")


def _require_exact(value: Any, expected: str, field_name: str) -> str:
    if value != expected:
        raise AttestationSchemaError(f"unsupported {field_name}: {value!r}")
    return expected


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AttestationSchemaError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AttestationSchemaError(f"{field_name} must be a positive integer")
    return value
