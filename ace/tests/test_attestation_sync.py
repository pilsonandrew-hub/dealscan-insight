from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from ace.attestation.backblaze import B2ApiError, B2Config, B2ConflictError, B2Object, B2ObjectNotVisibleError, B2ObjectVersion
from ace.attestation.sync import (
    AttestationLocalChainError,
    AttestationRemoteSetMismatchError,
    AttestationRemoteVersionError,
    derive_attestation_prefix,
    expected_attestation_objects,
    sync_attestation_records,
)
from ace.storage import CUTOVER_EXECUTE_AUTHORIZATION_TOKEN, append_cutover_genesis_event, append_event, bootstrap_db, connect


class FakeSyncB2Client:
    def __init__(self, *, object_prefix: str = "ace-attest") -> None:
        self.config = B2Config(
            key_id="redacted-key",
            application_key="redacted-app",
            bucket="ace-bucket",
            instance_id="andrew-prod",
            object_prefix=object_prefix,
        )
        self.objects: dict[str, bytes] = {}
        self.versions: dict[str, list[B2ObjectVersion]] = {}
        self.upload_calls: list[str] = []
        self.list_prefix_calls: list[str] = []
        self.fail_upload = False
        self.invisible_after_upload: set[str] = set()
        self.conflict_on_upload: set[str] = set()
        self.read_override: dict[str, bytes] = {}
        self.version_503_once: set[str] = set()

    def list_prefix(self, prefix: str) -> list[B2Object]:
        self.list_prefix_calls.append(prefix)
        return [
            B2Object(file_name=name, file_id=self.versions[name][0].file_id if self.versions.get(name) else f"id-{name}")
            for name in sorted(self.objects)
            if name.startswith(prefix)
        ]

    def list_versions(self, prefix: str) -> list[B2ObjectVersion]:
        if prefix in self.version_503_once:
            self.version_503_once.remove(prefix)
            raise B2ApiError("B2 HTTP error: status=503")
        versions: list[B2ObjectVersion] = []
        for name, name_versions in self.versions.items():
            if name.startswith(prefix):
                versions.extend(name_versions)
        return versions

    def upload_if_absent(self, file_name: str, content: bytes, *, content_type: str = "application/json") -> B2Object:
        self.upload_calls.append(file_name)
        if self.fail_upload:
            raise B2ObjectNotVisibleError("simulated B2 unreachable")
        if file_name in self.conflict_on_upload:
            raise B2ConflictError("simulated conflicting upload")
        if file_name in self.objects and self.objects[file_name] != content:
            raise B2ConflictError("existing object differs")
        if file_name not in self.objects:
            self.objects[file_name] = content
            self.versions[file_name] = [
                B2ObjectVersion(
                    file_name=file_name,
                    file_id=f"id-{len(self.versions) + 1}",
                    action="upload",
                    upload_timestamp=1000 + len(self.versions),
                    content_sha1="sha",
                    size=len(content),
                )
            ]
        if file_name in self.invisible_after_upload:
            raise B2ObjectNotVisibleError("not visible after upload")
        return B2Object(file_name=file_name, file_id=self.versions[file_name][0].file_id, size=len(content), content_sha1="sha")

    def read_object(self, file_name: str) -> bytes:
        if file_name in self.read_override:
            return self.read_override[file_name]
        if file_name not in self.objects:
            raise B2ObjectNotVisibleError("missing")
        return self.objects[file_name]


class AttestationSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

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
                source="ace/tests/test_attestation_sync.py",
                session_id="v1.1-cutover:test",
            )
            for index in range(post_events):
                append_event(connection, event_type="item.post", payload={"index": index})
            connection.commit()

    def _expected(self) -> list:
        return expected_attestation_objects(self.db_path, instance_id="andrew-prod", object_prefix="ace-attest")

    def test_expected_attestation_objects_scan_local_post_cutover_events_hash_only(self) -> None:
        self._build_post_cutover_chain(post_events=2)

        objects = self._expected()

        self.assertEqual([item.record.event_sequence for item in objects], [1, 2, 3])
        self.assertEqual(len({item.file_name for item in objects}), 3)
        self.assertTrue(all(item.file_name.startswith("ace-attest/ace-v1.1-post-cutover/andrew-prod/cutover_evt_") for item in objects))
        self.assertTrue(all(b"payload_json" not in item.body for item in objects))

    def test_sync_happy_path_uploads_missing_objects_and_verifies_exact_set(self) -> None:
        self._build_post_cutover_chain(post_events=2)
        client = FakeSyncB2Client()

        result = sync_attestation_records(client, self.db_path)

        self.assertEqual(result.expected_count, 3)
        self.assertEqual(result.uploaded_count, 3)
        self.assertEqual(result.existing_count, 0)
        self.assertEqual(set(client.objects), {item.file_name for item in self._expected()})
        self.assertGreaterEqual(len(client.list_prefix_calls), 2)

    def test_sync_emits_bounded_progress_for_large_remote_verification(self) -> None:
        self._build_post_cutover_chain(post_events=3)
        client = FakeSyncB2Client()
        messages: list[str] = []

        result = sync_attestation_records(
            client,
            self.db_path,
            progress_callback=messages.append,
            progress_every=2,
        )

        self.assertEqual(result.expected_count, 4)
        self.assertTrue(messages[0].startswith("sync_start expected=4"))
        self.assertIn("remote_initial count=0", messages)
        self.assertIn("object_pass_complete checked=4 uploaded=4 existing=0", messages)
        self.assertIn("remote_final_list_start", messages)
        self.assertIn("remote_final count=4", messages)
        self.assertIn("final_verify_complete checked=4", messages)
        self.assertTrue(any(message.startswith("object_progress checked=2/4") for message in messages))
        self.assertTrue(any(message.startswith("final_verify_progress checked=2/4") for message in messages))

    def test_sync_rejects_invalid_progress_interval(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()

        with self.assertRaisesRegex(ValueError, "progress_every"):
            sync_attestation_records(client, self.db_path, progress_every=0)

    def test_sync_is_idempotent_and_retries_without_duplicate_uploads(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()

        first = sync_attestation_records(client, self.db_path)
        client.upload_calls.clear()
        second = sync_attestation_records(client, self.db_path)

        self.assertEqual(first.uploaded_count, 2)
        self.assertEqual(second.uploaded_count, 0)
        self.assertEqual(second.existing_count, 2)
        self.assertEqual(client.upload_calls, [])

    def test_sync_does_not_read_existing_object_bodies_before_missing_uploads(self) -> None:
        self._build_post_cutover_chain(post_events=2)
        client = FakeSyncB2Client()
        existing, missing = self._expected()[:2]
        client.objects[existing.file_name] = existing.body
        client.versions[existing.file_name] = [
            B2ObjectVersion(existing.file_name, "id-existing", "upload", 1, content_sha1="sha", size=len(existing.body))
        ]
        client.read_override[existing.file_name] = b"stale-body-that-audit-must-catch-later"

        with self.assertRaisesRegex(AttestationRemoteVersionError, "body mismatch"):
            sync_attestation_records(client, self.db_path)

        self.assertIn(missing.file_name, client.upload_calls)
        self.assertIn(missing.file_name, client.objects)

    def test_sync_retries_transient_b2_503_during_version_verification(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()
        first = self._expected()[0]
        client.objects[first.file_name] = first.body
        client.versions[first.file_name] = [
            B2ObjectVersion(first.file_name, "id-existing", "upload", 1, content_sha1="sha", size=len(first.body))
        ]
        client.version_503_once.add(first.file_name)

        result = sync_attestation_records(client, self.db_path)

        self.assertEqual(result.uploaded_count, 1)
        self.assertEqual(result.existing_count, 1)

    def test_sync_rejects_remote_extra_objects_before_upload(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()
        expected = self._expected()
        prefix = expected[0].file_name.rsplit("seq_", 1)[0]
        client.objects[prefix + "seq_999999999999__evt_extra.json"] = b"{}\n"

        with self.assertRaisesRegex(AttestationRemoteSetMismatchError, "unexpected objects"):
            sync_attestation_records(client, self.db_path)

        self.assertEqual(client.upload_calls, [])

    def test_sync_propagates_b2_unreachable_without_local_state_change(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()
        client.fail_upload = True

        with self.assertRaises(B2ObjectNotVisibleError):
            sync_attestation_records(client, self.db_path)

        self.assertEqual(client.objects, {})

    def test_sync_rejects_conflicting_versions(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()
        item = self._expected()[0]
        client.objects[item.file_name] = item.body
        client.versions[item.file_name] = [
            B2ObjectVersion(item.file_name, "id-old", "upload", 1, content_sha1="old", size=len(item.body)),
            B2ObjectVersion(item.file_name, "id-new", "upload", 2, content_sha1="new", size=len(item.body) + 1),
        ]

        with self.assertRaisesRegex(AttestationRemoteVersionError, "conflicting later version"):
            sync_attestation_records(client, self.db_path)

    def test_sync_rejects_partial_upload_readback_mismatch(self) -> None:
        self._build_post_cutover_chain(post_events=1)
        client = FakeSyncB2Client()
        item = self._expected()[0]
        client.objects[item.file_name] = item.body
        client.versions[item.file_name] = [B2ObjectVersion(item.file_name, "id-1", "upload", 1, content_sha1="sha", size=len(item.body))]
        client.read_override[item.file_name] = b"partial"

        with self.assertRaisesRegex(AttestationRemoteVersionError, "body mismatch"):
            sync_attestation_records(client, self.db_path)

    def test_sync_rejects_namespace_collision(self) -> None:
        with self.assertRaisesRegex(Exception, "namespace"):
            derive_attestation_prefix(object_prefix="safe", instance_id="../other", cutover_event_id="evt_cutover")

    def test_sync_rejects_non_attestable_local_chain(self) -> None:
        with self.assertRaises(AttestationLocalChainError):
            expected_attestation_objects(self.db_path, instance_id="andrew-prod", object_prefix="ace-attest")


if __name__ == "__main__":
    unittest.main()
