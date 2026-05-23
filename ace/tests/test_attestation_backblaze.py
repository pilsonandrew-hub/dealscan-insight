from __future__ import annotations

import logging
import traceback
import unittest
from typing import Any, Mapping

from ace.attestation.backblaze import (
    B2ApiError,
    B2AttestationClient,
    B2Authorization,
    B2Config,
    B2ConflictError,
    B2ConfigurationError,
    B2ObjectNotVisibleError,
    B2ObjectVersion,
    B2PostUploadVerificationError,
)


class FakeB2Transport:
    supports_conditional_upload = True

    def __init__(self) -> None:
        self.authorize_calls: list[tuple[str, str]] = []
        self.post_json_calls: list[tuple[str, Mapping[str, Any]]] = []
        self.upload_calls: list[tuple[str, bytes, bool]] = []
        self.objects: dict[str, bytes] = {}
        self.visible_after_reads: dict[str, int] = {}
        self.read_counts: dict[str, int] = {}
        self.list_pages: list[Mapping[str, Any]] = []
        self.version_pages: list[Mapping[str, Any]] = []
        self.read_override: bytes | None = None
        self.raise_with_secret_on_read = False

    def authorize(self, key_id: str, application_key: str) -> B2Authorization:
        self.authorize_calls.append((key_id, application_key))
        return B2Authorization(
            api_url="https://api.example.test",
            authorization_token="auth-token-secret",
            download_url="https://download.example.test",
            account_id="acct",
            allowed_bucket_id="bucket-id",
            allowed_bucket_name="ace-bucket",
        )

    def post_json(self, url: str, token: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.post_json_calls.append((url, dict(payload)))
        if url.endswith("/b2_get_upload_url"):
            return {"uploadUrl": "https://upload.example.test", "authorizationToken": "upload-token-secret"}
        if url.endswith("/b2_list_file_names"):
            return self.list_pages.pop(0) if self.list_pages else {"files": [], "nextFileName": None}
        if url.endswith("/b2_list_file_versions"):
            return self.version_pages.pop(0) if self.version_pages else {"files": [], "nextFileName": None, "nextFileId": None}
        raise AssertionError(f"unexpected post_json endpoint: {url}")

    def post_bytes(
        self,
        url: str,
        token: str,
        *,
        file_name: str,
        content: bytes,
        content_type: str,
        sha1: str,
        if_none_match: bool = False,
    ) -> Mapping[str, Any]:
        self.upload_calls.append((file_name, content, if_none_match))
        self.objects[file_name] = content
        return {"fileId": f"id-{len(self.upload_calls)}", "fileName": file_name, "contentSha1": sha1}

    def get_bytes(self, url: str, token: str | None = None) -> bytes:
        file_name = url.split("/file/ace-bucket/", 1)[1]
        self.read_counts[file_name] = self.read_counts.get(file_name, 0) + 1
        if self.raise_with_secret_on_read:
            raise AssertionError("transport leaked key-secret app-secret auth-token-secret")
        visible_after = self.visible_after_reads.get(file_name, 0)
        if self.read_counts[file_name] <= visible_after:
            raise B2ObjectNotVisibleError("B2 object is not visible yet")
        if self.read_override is not None:
            return self.read_override
        if file_name not in self.objects:
            raise B2ObjectNotVisibleError("B2 object is not visible")
        return self.objects[file_name]


class B2AttestationClientTests(unittest.TestCase):
    def _config(self) -> B2Config:
        return B2Config(
            key_id="key-secret",
            application_key="app-secret",
            bucket="ace-bucket",
            instance_id="andrew-prod",
        )

    def _client(self, transport: FakeB2Transport | None = None) -> tuple[B2AttestationClient, FakeB2Transport]:
        fake = transport or FakeB2Transport()
        return B2AttestationClient(self._config(), transport=fake), fake

    def test_config_reads_only_required_environment_variables(self) -> None:
        config = B2Config.from_env(
            {
                "ACE_B2_KEY_ID": " key ",
                "ACE_B2_APPLICATION_KEY": " app ",
                "ACE_B2_BUCKET": " bucket ",
                "ACE_B2_INSTANCE_ID": " instance ",
                "ACE_B2_OBJECT_PREFIX": " prefix/ ",
            }
        )

        self.assertEqual(config.key_id, "key")
        self.assertEqual(config.application_key, "app")
        self.assertEqual(config.bucket, "bucket")
        self.assertEqual(config.instance_id, "instance")
        self.assertEqual(config.object_prefix, "prefix/")

    def test_config_missing_env_fails_without_secret_values(self) -> None:
        with self.assertRaisesRegex(B2ConfigurationError, "ACE_B2_APPLICATION_KEY") as caught:
            B2Config.from_env({"ACE_B2_KEY_ID": "key", "ACE_B2_BUCKET": "bucket", "ACE_B2_INSTANCE_ID": "instance"})

        self.assertNotIn("key", str(caught.exception))

    def test_repr_redacts_credentials(self) -> None:
        config = self._config()
        client, _fake = self._client()

        self.assertNotIn("key-secret", repr(config))
        self.assertNotIn("app-secret", repr(config))
        self.assertNotIn("key-secret", repr(client))
        self.assertNotIn("app-secret", repr(client))

    def test_list_prefix_exhausts_pagination(self) -> None:
        client, fake = self._client()
        fake.list_pages = [
            {
                "files": [{"fileName": "prefix/a.json", "fileId": "id-a", "size": 3, "contentSha1": "sha-a"}],
                "nextFileName": "prefix/b.json",
            },
            {
                "files": [{"fileName": "prefix/b.json", "fileId": "id-b", "size": 4, "contentSha1": "sha-b"}],
                "nextFileName": None,
            },
        ]

        objects = client.list_prefix("prefix/")

        self.assertEqual([obj.file_name for obj in objects], ["prefix/a.json", "prefix/b.json"])
        list_calls = [payload for url, payload in fake.post_json_calls if url.endswith("/b2_list_file_names")]
        self.assertEqual(list_calls[0]["prefix"], "prefix/")
        self.assertEqual(list_calls[1]["startFileName"], "prefix/b.json")

    def test_list_prefix_rejects_invalid_pagination_token(self) -> None:
        client, fake = self._client()
        fake.list_pages = [{"files": [], "nextFileName": 123}]

        with self.assertRaisesRegex(B2ApiError, "invalid pagination token"):
            client.list_prefix("prefix/")

    def test_list_versions_exhausts_file_name_and_file_id_pagination(self) -> None:
        client, fake = self._client()
        fake.version_pages = [
            {
                "files": [{"fileName": "prefix/a.json", "fileId": "id-a1", "action": "upload", "uploadTimestamp": 1}],
                "nextFileName": "prefix/a.json",
                "nextFileId": "id-a0",
            },
            {
                "files": [{"fileName": "prefix/a.json", "fileId": "id-a0", "action": "hide", "uploadTimestamp": 2}],
                "nextFileName": None,
                "nextFileId": None,
            },
        ]

        versions = client.list_versions("prefix/")

        self.assertEqual([(v.file_name, v.file_id, v.action) for v in versions], [("prefix/a.json", "id-a1", "upload"), ("prefix/a.json", "id-a0", "hide")])
        version_calls = [payload for url, payload in fake.post_json_calls if url.endswith("/b2_list_file_versions")]
        self.assertEqual(version_calls[1]["startFileName"], "prefix/a.json")
        self.assertEqual(version_calls[1]["startFileId"], "id-a0")

    def test_list_versions_returns_all_visible_versions_including_earliest_locked(self) -> None:
        client, fake = self._client()
        fake.version_pages = [
            {
                "files": [
                    {"fileName": "prefix/a.json", "fileId": "id-new", "action": "upload", "uploadTimestamp": 300, "size": 3, "contentSha1": "sha-new"},
                    {"fileName": "prefix/a.json", "fileId": "id-mid", "action": "upload", "uploadTimestamp": 200, "size": 3, "contentSha1": "sha-mid"},
                ],
                "nextFileName": "prefix/a.json",
                "nextFileId": "id-old",
            },
            {
                "files": [
                    {"fileName": "prefix/a.json", "fileId": "id-old", "action": "upload", "uploadTimestamp": 100, "size": 3, "contentSha1": "sha-old"},
                ],
                "nextFileName": None,
                "nextFileId": None,
            },
        ]

        versions = client.list_versions("prefix/a.json")

        self.assertEqual([version.file_id for version in versions], ["id-new", "id-mid", "id-old"])
        self.assertEqual(
            versions[-1],
            B2ObjectVersion(
                file_name="prefix/a.json",
                file_id="id-old",
                action="upload",
                upload_timestamp=100,
                content_sha1="sha-old",
                size=3,
            ),
        )

    def test_upload_if_absent_uses_conditional_upload_and_strict_readback(self) -> None:
        client, fake = self._client()

        uploaded = client.upload_if_absent("prefix/one.json", b"{\"ok\":true}")

        self.assertEqual(uploaded.file_name, "prefix/one.json")
        self.assertEqual(fake.upload_calls, [("prefix/one.json", b"{\"ok\":true}", True)])

    def test_upload_if_absent_returns_existing_matching_object_without_reupload(self) -> None:
        client, fake = self._client()
        fake.objects["prefix/one.json"] = b"same"
        fake.version_pages = [
            {
                "files": [{"fileName": "prefix/one.json", "fileId": "id-existing", "action": "upload", "uploadTimestamp": 1}],
                "nextFileName": None,
                "nextFileId": None,
            }
        ]

        existing = client.upload_if_absent("prefix/one.json", b"same")

        self.assertEqual(existing.file_id, "id-existing")
        self.assertEqual(fake.upload_calls, [])

    def test_upload_if_absent_rejects_existing_conflicting_object(self) -> None:
        client, fake = self._client()
        fake.objects["prefix/one.json"] = b"old"
        fake.version_pages = [
            {
                "files": [{"fileName": "prefix/one.json", "fileId": "id-existing", "action": "upload", "uploadTimestamp": 1}],
                "nextFileName": None,
                "nextFileId": None,
            }
        ]

        with self.assertRaisesRegex(B2ConflictError, "different content"):
            client.upload_if_absent("prefix/one.json", b"new")

    def test_upload_if_absent_rejects_post_upload_readback_mismatch(self) -> None:
        client, fake = self._client()
        fake.read_override = b"corrupt"

        with self.assertRaisesRegex(B2PostUploadVerificationError, "readback mismatch"):
            client.upload_if_absent("prefix/one.json", b"expected")

    def test_upload_if_absent_rejects_post_upload_readback_truncation(self) -> None:
        client, fake = self._client()
        fake.read_override = b"expect"

        with self.assertRaisesRegex(B2PostUploadVerificationError, "readback mismatch"):
            client.upload_if_absent("prefix/one.json", b"expected")

    def test_upload_if_absent_retries_eventual_consistency_before_success(self) -> None:
        client, fake = self._client()
        fake.visible_after_reads["prefix/one.json"] = 2

        uploaded = client.upload_if_absent("prefix/one.json", b"expected")

        self.assertEqual(uploaded.file_name, "prefix/one.json")
        self.assertEqual(fake.read_counts["prefix/one.json"], 3)

    def test_upload_if_absent_fails_loudly_when_invisible_inside_bounded_window(self) -> None:
        client, fake = self._client()
        fake.visible_after_reads["prefix/one.json"] = 99

        with self.assertRaisesRegex(B2ObjectNotVisibleError, "bounded readback window"):
            client.upload_if_absent("prefix/one.json", b"expected")
        self.assertEqual(fake.read_counts["prefix/one.json"], 3)

    def test_error_messages_do_not_leak_credentials(self) -> None:
        client, fake = self._client()
        fake.list_pages = [{"files": "not-a-list", "nextFileName": None}]

        with self.assertRaises(B2ApiError) as caught:
            client.list_prefix("prefix/")

        message = str(caught.exception)
        self.assertNotIn("key-secret", message)
        self.assertNotIn("app-secret", message)
        self.assertNotIn("auth-token-secret", message)

    def test_no_credentials_leak_through_exception_attributes_tracebacks_logs_or_client_strings(self) -> None:
        client, fake = self._client()
        fake.raise_with_secret_on_read = True
        logger = logging.getLogger("ace.tests.attestation.backblaze")

        with self.assertLogs(logger, level="ERROR") as logs:
            try:
                client.upload_if_absent("prefix/one.json", b"expected")
            except Exception as exc:  # noqa: BLE001 - deliberately inspect all surfaces
                logger.exception("sanitized B2 attestation failure")
                surfaces = [
                    str(exc),
                    repr(exc),
                    repr(client),
                    str(client),
                    repr(client.config),
                    str(client.config),
                    traceback.format_exc(),
                    repr(getattr(exc, "__dict__", {})),
                    "\n".join(logs.output),
                ]
            else:  # pragma: no cover - defensive
                self.fail("expected upload to fail")

        combined = "\n".join(surfaces)
        self.assertNotIn("key-secret", combined)
        self.assertNotIn("app-secret", combined)
        self.assertNotIn("auth-token-secret", combined)


if __name__ == "__main__":
    unittest.main()
