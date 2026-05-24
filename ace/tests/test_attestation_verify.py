from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from ace.attestation.backblaze import B2ApiError, B2Config, B2Object, B2ObjectNotVisibleError, B2ObjectVersion
from ace.attestation.sync import expected_attestation_objects
from ace.attestation.verify import verify_external_attestation, verify_external_attestation_with_client
from ace.storage import (
    CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
    append_cutover_genesis_event,
    append_event,
    bootstrap_db,
    compute_event_hash_from_mapping,
    connect,
)


class FakeAuditB2Client:
    def __init__(self, *, object_prefix: str = "ace-attest", instance_id: str = "andrew-prod") -> None:
        self.config = B2Config(
            key_id="redacted-key",
            application_key="redacted-app",
            bucket="ace-bucket",
            instance_id=instance_id,
            object_prefix=object_prefix,
        )
        self.objects: dict[str, bytes] = {}
        self.versions: dict[str, list[B2ObjectVersion]] = {}
        self.list_prefix_calls: list[str] = []
        self.fail_listing = False
        self.invisible_reads: set[str] = set()

    def list_prefix(self, prefix: str) -> list[B2Object]:
        self.list_prefix_calls.append(prefix)
        if self.fail_listing:
            raise B2ApiError("simulated pagination failure")
        return [
            B2Object(
                file_name=name,
                file_id=self.versions[name][0].file_id if self.versions.get(name) else f"id-{name}",
                size=self.versions[name][0].size if self.versions.get(name) else len(self.objects[name]),
                content_sha1=self.versions[name][0].content_sha1 if self.versions.get(name) else hashlib.sha1(self.objects[name]).hexdigest(),
            )
            for name in sorted(self.objects)
            if name.startswith(prefix)
        ]

    def list_versions(self, prefix: str) -> list[B2ObjectVersion]:
        versions: list[B2ObjectVersion] = []
        for name, name_versions in self.versions.items():
            if name.startswith(prefix):
                versions.extend(name_versions)
        return versions

    def read_object(self, file_name: str) -> bytes:
        if file_name in self.invisible_reads:
            raise B2ObjectNotVisibleError("simulated eventual consistency window")
        return self.objects[file_name]

    def upload_if_absent(self, file_name: str, content: bytes, *, content_type: str = "application/json") -> B2Object:
        raise AssertionError("audit verification must not write remote B2 objects")

    def seed_expected(self, db_path: Path) -> list:
        expected = expected_attestation_objects(
            db_path,
            instance_id=self.config.instance_id,
            object_prefix=self.config.object_prefix,
        )
        for index, item in enumerate(expected, start=1):
            self.objects[item.file_name] = item.body
            self.versions[item.file_name] = [
                B2ObjectVersion(
                    file_name=item.file_name,
                    file_id=f"id-{index}",
                    action="upload",
                    upload_timestamp=index,
                    content_sha1=hashlib.sha1(item.body).hexdigest(),
                    size=len(item.body),
                )
            ]
        return expected


class ExternalAttestationVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self._build_post_cutover_chain(post_events=2)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _build_post_cutover_chain(self, post_events: int = 2) -> None:
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_attestation_verify.py",
                session_id="v1.1-cutover:test",
            )
            for index in range(post_events):
                append_event(connection, event_type="item.post", payload={"index": index})
            connection.commit()

    def test_verify_external_attestation_happy_path(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)

        result = verify_external_attestation_with_client(client, self.db_path)

        self.assertTrue(result.ok)
        self.assertIn("external_attestation=ok", result.detail)
        self.assertIn(f"checked={len(expected)}", result.detail)
        self.assertGreaterEqual(len(client.list_prefix_calls), 1)

    def test_verify_external_attestation_fails_on_remote_extra(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        prefix = expected[0].file_name.rsplit("seq_", 1)[0]
        client.objects[prefix + "seq_999999999999__evt_extra.json"] = expected[0].body

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_remote_extra", detail)

    def test_verify_external_attestation_detects_local_truncation_with_rehash_as_remote_extra(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        truncated = expected[-1]
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DROP TRIGGER ace_events_no_delete")
            connection.execute("DELETE FROM events WHERE event_id = ?", (truncated.record.event_id,))
            connection.commit()

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_remote_extra", detail)

    def test_verify_external_attestation_fails_on_version_conflict(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        item = expected[0]
        client.versions[item.file_name].append(
            B2ObjectVersion(item.file_name, "id-conflict", "upload", 999, content_sha1="different", size=len(item.body) + 1)
        )

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_conflicting_version", detail)

    def test_verify_external_attestation_fails_on_pagination_failure(self) -> None:
        client = FakeAuditB2Client()
        client.seed_expected(self.db_path)
        client.fail_listing = True

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_listing_incomplete", detail)

    def test_verify_external_attestation_fails_on_instance_collision(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        prefix = expected[0].file_name.rsplit("seq_", 1)[0]
        client.objects[prefix + "seq_999999999998__evt_collision.json"] = expected[0].body.replace(b'"instance_id":"andrew-prod"', b'"instance_id":"other-prod"')

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_namespace_collision", detail)

    def test_verify_external_attestation_fails_on_missing_object(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        del client.objects[expected[0].file_name]

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_missing", detail)

    def test_verify_external_attestation_fails_on_partial_remote_listing_hash(self) -> None:
        client = FakeAuditB2Client()
        expected = client.seed_expected(self.db_path)
        client.versions[expected[0].file_name][0] = B2ObjectVersion(
            file_name=expected[0].file_name,
            file_id="id-hash-mismatch",
            action="upload",
            upload_timestamp=1,
            content_sha1="0" * 40,
            size=len(expected[0].body),
        )

        ok, detail = verify_external_attestation(self.db_path, client=client)

        self.assertFalse(ok)
        self.assertIn("external_attestation_mismatch", detail)


if __name__ == "__main__":
    unittest.main()
