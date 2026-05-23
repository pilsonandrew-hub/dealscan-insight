"""ACE external attestation core primitives."""

from .manifest import (
    ATTESTATION_CHAIN_ID,
    ATTESTATION_SCHEMA_VERSION,
    MANIFEST_GENERATOR_VERSION,
    AttestationRecord,
    AttestationSchemaError,
    attestation_record_from_event_row,
    canonical_attestation_json,
    parse_attestation_record,
)

__all__ = [
    "ATTESTATION_CHAIN_ID",
    "ATTESTATION_SCHEMA_VERSION",
    "MANIFEST_GENERATOR_VERSION",
    "AttestationRecord",
    "AttestationSchemaError",
    "attestation_record_from_event_row",
    "canonical_attestation_json",
    "parse_attestation_record",
]
