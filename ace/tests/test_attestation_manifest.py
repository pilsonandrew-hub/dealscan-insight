from __future__ import annotations

import json
import unittest

from ace.attestation.manifest import (
    ATTESTATION_CHAIN_ID,
    ATTESTATION_SCHEMA_VERSION,
    MANIFEST_GENERATOR_VERSION,
    AttestationRecord,
    AttestationSchemaError,
    attestation_record_from_event_row,
    canonical_attestation_json,
    parse_attestation_record,
)


class AttestationManifestTests(unittest.TestCase):
    def _event_row(self) -> dict[str, object]:
        return {
            "event_sequence": 2,
            "event_id": "evt_post_cutover",
            "event_hash": "a" * 64,
            "previous_event_hash": "b" * 64,
            "created_at": "2026-05-23T00:00:00Z",
            "payload_json": '{"private":"not mirrored"}',
        }

    def test_record_from_event_row_contains_hash_only_schema_fields(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        )

        self.assertEqual(record.schema_version, ATTESTATION_SCHEMA_VERSION)
        self.assertEqual(record.chain_id, ATTESTATION_CHAIN_ID)
        self.assertEqual(record.instance_id, "andrew-prod")
        self.assertEqual(record.cutover_event_id, "evt_cutover")
        self.assertEqual(record.event_sequence, 2)
        self.assertEqual(record.event_id, "evt_post_cutover")
        self.assertEqual(record.event_hash, "a" * 64)
        self.assertEqual(record.previous_event_hash, "b" * 64)
        self.assertEqual(record.created_at, "2026-05-23T00:00:00Z")
        self.assertEqual(record.manifest_generator_version, MANIFEST_GENERATOR_VERSION)
        self.assertNotIn("payload_json", record.to_mapping())

    def test_canonical_serialization_is_deterministic_and_sorted(self) -> None:
        record = AttestationRecord(
            schema_version=ATTESTATION_SCHEMA_VERSION,
            chain_id=ATTESTATION_CHAIN_ID,
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
            event_sequence=1,
            event_id="evt_one",
            event_hash="a" * 64,
            previous_event_hash=None,
            created_at="2026-05-23T00:00:00Z",
            manifest_generator_version=MANIFEST_GENERATOR_VERSION,
        )

        first = canonical_attestation_json(record)
        second = canonical_attestation_json(dict(reversed(list(record.to_mapping().items()))))

        self.assertEqual(first, second)
        self.assertEqual(first, record.to_canonical_json())
        self.assertFalse(" " in first)
        self.assertEqual(json.loads(first), record.to_mapping())

    def test_parse_round_trips_valid_record(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        )

        parsed = parse_attestation_record(
            record.to_canonical_json(),
            expected_instance_id="andrew-prod",
            expected_cutover_event_id="evt_cutover",
        )

        self.assertEqual(parsed, record)

    def test_parse_rejects_schema_version_mismatch(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        ).to_mapping()
        record["schema_version"] = "ace-b2-attestation-v2"

        with self.assertRaisesRegex(AttestationSchemaError, "unsupported schema_version"):
            parse_attestation_record(
                json.dumps(record, sort_keys=True, separators=(",", ":")),
                expected_instance_id="andrew-prod",
                expected_cutover_event_id="evt_cutover",
            )

    def test_parse_rejects_manifest_generator_version_mismatch(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        ).to_mapping()
        record["manifest_generator_version"] = "future-generator"

        with self.assertRaisesRegex(AttestationSchemaError, "unsupported manifest_generator_version"):
            parse_attestation_record(
                json.dumps(record, sort_keys=True, separators=(",", ":")),
                expected_instance_id="andrew-prod",
                expected_cutover_event_id="evt_cutover",
            )

    def test_parse_rejects_namespace_mismatch(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        )

        with self.assertRaisesRegex(AttestationSchemaError, "instance_id mismatch"):
            parse_attestation_record(
                record.to_canonical_json(),
                expected_instance_id="other-instance",
                expected_cutover_event_id="evt_cutover",
            )

    def test_record_rejects_invalid_event_sequence(self) -> None:
        row = self._event_row()
        row["event_sequence"] = 0

        with self.assertRaisesRegex(AttestationSchemaError, "event_sequence"):
            attestation_record_from_event_row(
                row,
                instance_id="andrew-prod",
                cutover_event_id="evt_cutover",
            )

    def test_parse_rejects_extra_fields_for_forward_compatibility(self) -> None:
        record = attestation_record_from_event_row(
            self._event_row(),
            instance_id="andrew-prod",
            cutover_event_id="evt_cutover",
        ).to_mapping()
        record["future_field"] = "not silently accepted"

        with self.assertRaisesRegex(AttestationSchemaError, "unsupported fields"):
            parse_attestation_record(
                json.dumps(record, sort_keys=True, separators=(",", ":")),
                expected_instance_id="andrew-prod",
                expected_cutover_event_id="evt_cutover",
            )


if __name__ == "__main__":
    unittest.main()
