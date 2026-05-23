from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol


class B2AttestationError(RuntimeError):
    """Base class for sanitized Backblaze attestation errors."""


class B2ConfigurationError(B2AttestationError):
    """Raised when required B2 configuration is absent or invalid."""


class B2ApiError(B2AttestationError):
    """Raised when B2 returns an error or malformed response."""


class B2ConflictError(B2AttestationError):
    """Raised when a remote object already exists with different content."""


class B2PostUploadVerificationError(B2AttestationError):
    """Raised when strict post-upload readback does not match expected bytes."""


@dataclass(frozen=True)
class B2Config:
    key_id: str
    application_key: str
    bucket: str
    instance_id: str
    object_prefix: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "B2Config":
        values = os.environ if env is None else env
        return cls(
            key_id=_required_env(values, "ACE_B2_KEY_ID"),
            application_key=_required_env(values, "ACE_B2_APPLICATION_KEY"),
            bucket=_required_env(values, "ACE_B2_BUCKET"),
            instance_id=_required_env(values, "ACE_B2_INSTANCE_ID"),
            object_prefix=values.get("ACE_B2_OBJECT_PREFIX", "").strip(),
        )

    def __repr__(self) -> str:
        return (
            "B2Config(key_id=<redacted>, application_key=<redacted>, "
            f"bucket={self.bucket!r}, instance_id={self.instance_id!r}, object_prefix={self.object_prefix!r})"
        )


def _required_env(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise B2ConfigurationError(f"missing required environment variable: {name}")
    return value.strip()


@dataclass(frozen=True)
class B2Object:
    file_name: str
    file_id: str | None
    size: int | None = None
    content_sha1: str | None = None


@dataclass(frozen=True)
class B2ObjectVersion:
    file_name: str
    file_id: str
    action: str
    upload_timestamp: int | None
    content_sha1: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class B2Authorization:
    api_url: str
    authorization_token: str
    download_url: str
    account_id: str
    allowed_bucket_id: str | None = None
    allowed_bucket_name: str | None = None


@dataclass(frozen=True)
class B2UploadUrl:
    upload_url: str
    authorization_token: str


class B2Transport(Protocol):
    supports_conditional_upload: bool

    def authorize(self, key_id: str, application_key: str) -> B2Authorization: ...

    def post_json(self, url: str, token: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

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
    ) -> Mapping[str, Any]: ...

    def get_bytes(self, url: str, token: str | None = None) -> bytes: ...


class UrllibB2Transport:
    supports_conditional_upload = False

    def authorize(self, key_id: str, application_key: str) -> B2Authorization:
        credentials = base64.b64encode(f"{key_id}:{application_key}".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            headers={"Authorization": f"Basic {credentials}"},
            method="GET",
        )
        response = self._json_request(request)
        allowed = response.get("allowed") if isinstance(response.get("allowed"), dict) else {}
        return B2Authorization(
            api_url=_required_response_text(response, "apiUrl"),
            authorization_token=_required_response_text(response, "authorizationToken"),
            download_url=_required_response_text(response, "downloadUrl"),
            account_id=_required_response_text(response, "accountId"),
            allowed_bucket_id=allowed.get("bucketId"),
            allowed_bucket_name=allowed.get("bucketName"),
        )

    def post_json(self, url: str, token: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            headers={"Authorization": token, "Content-Type": "application/json"},
            method="POST",
        )
        return self._json_request(request)

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
        headers = {
            "Authorization": token,
            "X-Bz-File-Name": urllib.parse.quote(file_name, safe="/"),
            "Content-Type": content_type,
            "Content-Length": str(len(content)),
            "X-Bz-Content-Sha1": sha1,
        }
        if if_none_match and self.supports_conditional_upload:
            headers["If-None-Match"] = "*"
        request = urllib.request.Request(url, data=content, headers=headers, method="POST")
        return self._json_request(request)

    def get_bytes(self, url: str, token: str | None = None) -> bytes:
        headers = {"Authorization": token} if token else {}
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise B2ApiError(f"B2 HTTP error during read: status={exc.code}") from None
        except urllib.error.URLError as exc:
            raise B2ApiError(f"B2 network error during read: reason={type(exc.reason).__name__}") from None

    def _json_request(self, request: urllib.request.Request) -> Mapping[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise B2ApiError(f"B2 HTTP error: status={exc.code}") from None
        except urllib.error.URLError as exc:
            raise B2ApiError(f"B2 network error: reason={type(exc.reason).__name__}") from None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise B2ApiError("B2 response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise B2ApiError("B2 response JSON was not an object")
        return parsed


class B2AttestationClient:
    def __init__(self, config: B2Config, *, transport: B2Transport | None = None) -> None:
        self.config = config
        self._transport = transport or UrllibB2Transport()
        self._authorization: B2Authorization | None = None
        self._bucket_id: str | None = None

    def __repr__(self) -> str:
        return f"B2AttestationClient(config={self.config!r}, authorized={self._authorization is not None})"

    @property
    def authorization(self) -> B2Authorization:
        if self._authorization is None:
            self._authorization = self._transport.authorize(self.config.key_id, self.config.application_key)
        return self._authorization

    def bucket_id(self) -> str:
        if self._bucket_id is None:
            authorization = self.authorization
            if authorization.allowed_bucket_id and authorization.allowed_bucket_name in {None, self.config.bucket}:
                self._bucket_id = authorization.allowed_bucket_id
            else:
                response = self._post_json(
                    "b2_list_buckets",
                    {"accountId": authorization.account_id, "bucketName": self.config.bucket},
                )
                buckets = response.get("buckets")
                if not isinstance(buckets, list) or not buckets:
                    raise B2ConfigurationError("configured B2 bucket was not found")
                bucket = buckets[0]
                if not isinstance(bucket, dict) or not isinstance(bucket.get("bucketId"), str):
                    raise B2ApiError("B2 list buckets response missing bucketId")
                self._bucket_id = bucket["bucketId"]
        return self._bucket_id

    def list_prefix(self, prefix: str) -> list[B2Object]:
        objects: list[B2Object] = []
        next_file_name: str | None = None
        while True:
            payload: dict[str, Any] = {
                "bucketId": self.bucket_id(),
                "prefix": prefix,
                "maxFileCount": 1000,
            }
            if next_file_name is not None:
                payload["startFileName"] = next_file_name
            response = self._post_json("b2_list_file_names", payload)
            files = response.get("files")
            if not isinstance(files, list):
                raise B2ApiError("B2 list file names response missing files list")
            for file_entry in files:
                if not isinstance(file_entry, dict):
                    raise B2ApiError("B2 list file names response contained malformed file entry")
                objects.append(
                    B2Object(
                        file_name=_required_response_text(file_entry, "fileName"),
                        file_id=file_entry.get("fileId"),
                        size=file_entry.get("size") if isinstance(file_entry.get("size"), int) else None,
                        content_sha1=file_entry.get("contentSha1") if isinstance(file_entry.get("contentSha1"), str) else None,
                    )
                )
            next_file_name = response.get("nextFileName")
            if next_file_name is None:
                break
            if not isinstance(next_file_name, str) or not next_file_name:
                raise B2ApiError("B2 list file names returned invalid pagination token")
        return objects

    def list_versions(self, prefix: str) -> list[B2ObjectVersion]:
        versions: list[B2ObjectVersion] = []
        next_file_name: str | None = None
        next_file_id: str | None = None
        while True:
            payload: dict[str, Any] = {
                "bucketId": self.bucket_id(),
                "prefix": prefix,
                "maxFileCount": 1000,
            }
            if next_file_name is not None:
                payload["startFileName"] = next_file_name
            if next_file_id is not None:
                payload["startFileId"] = next_file_id
            response = self._post_json("b2_list_file_versions", payload)
            files = response.get("files")
            if not isinstance(files, list):
                raise B2ApiError("B2 list file versions response missing files list")
            for file_entry in files:
                if not isinstance(file_entry, dict):
                    raise B2ApiError("B2 list file versions response contained malformed file entry")
                versions.append(
                    B2ObjectVersion(
                        file_name=_required_response_text(file_entry, "fileName"),
                        file_id=_required_response_text(file_entry, "fileId"),
                        action=_required_response_text(file_entry, "action"),
                        upload_timestamp=file_entry.get("uploadTimestamp") if isinstance(file_entry.get("uploadTimestamp"), int) else None,
                        content_sha1=file_entry.get("contentSha1") if isinstance(file_entry.get("contentSha1"), str) else None,
                        size=file_entry.get("size") if isinstance(file_entry.get("size"), int) else None,
                    )
                )
            next_file_name = response.get("nextFileName")
            next_file_id = response.get("nextFileId")
            if next_file_name is None and next_file_id is None:
                break
            if not isinstance(next_file_name, str) or not next_file_name or not isinstance(next_file_id, str) or not next_file_id:
                raise B2ApiError("B2 list file versions returned invalid pagination token")
        return versions

    def read_object(self, file_name: str) -> bytes:
        authorization = self.authorization
        encoded = urllib.parse.quote(file_name, safe="/")
        bucket = urllib.parse.quote(self.config.bucket, safe="")
        return self._transport.get_bytes(f"{authorization.download_url}/file/{bucket}/{encoded}", authorization.authorization_token)

    def upload_if_absent(self, file_name: str, content: bytes, *, content_type: str = "application/json") -> B2Object:
        expected_sha1 = hashlib.sha1(content).hexdigest()
        existing = self.list_versions(file_name)
        matching_existing = [version for version in existing if version.file_name == file_name and version.action == "upload"]
        if matching_existing:
            remote = self.read_object(file_name)
            if remote != content:
                raise B2ConflictError("B2 object already exists with different content")
            return B2Object(file_name=file_name, file_id=matching_existing[0].file_id, size=len(remote), content_sha1=hashlib.sha1(remote).hexdigest())

        upload_url = self._upload_url()
        response = self._transport.post_bytes(
            upload_url.upload_url,
            upload_url.authorization_token,
            file_name=file_name,
            content=content,
            content_type=content_type,
            sha1=expected_sha1,
            if_none_match=self._transport.supports_conditional_upload,
        )
        file_id = _required_response_text(response, "fileId")
        returned_name = _required_response_text(response, "fileName")
        if returned_name != file_name:
            raise B2ApiError("B2 upload response fileName mismatch")
        readback = self.read_object(file_name)
        if readback != content:
            raise B2PostUploadVerificationError("B2 post-upload readback mismatch")
        return B2Object(file_name=file_name, file_id=file_id, size=len(readback), content_sha1=hashlib.sha1(readback).hexdigest())

    def _upload_url(self) -> B2UploadUrl:
        response = self._post_json("b2_get_upload_url", {"bucketId": self.bucket_id()})
        return B2UploadUrl(
            upload_url=_required_response_text(response, "uploadUrl"),
            authorization_token=_required_response_text(response, "authorizationToken"),
        )

    def _post_json(self, endpoint: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        authorization = self.authorization
        return self._transport.post_json(
            f"{authorization.api_url}/b2api/v2/{endpoint}",
            authorization.authorization_token,
            payload,
        )


def _required_response_text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise B2ApiError(f"B2 response missing required field: {key}")
    return value
