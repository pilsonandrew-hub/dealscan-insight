from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ace.storage import DB_PATH

from .backblaze import B2ApiError, B2AttestationError, B2Config, B2ConfigurationError, B2ObjectNotVisibleError
from .sync import (
    AttestationClient,
    AttestationLocalChainError,
    AttestationObject,
    AttestationRemoteSetMismatchError,
    AttestationRemoteVersionError,
    _common_prefix,
    _verify_remote_versions,
    expected_attestation_objects,
)


EXTERNAL_ATTESTATION_NOT_CONFIGURED = "external_attestation_not_configured"


class AttestationClientFactory(Protocol):
    def __call__(self) -> AttestationClient: ...


@dataclass(frozen=True)
class ExternalAttestationCheckResult:
    ok: bool
    detail: str


def verify_external_attestation(
    db_path: Path | str = DB_PATH,
    *,
    client: AttestationClient | None = None,
    client_factory: AttestationClientFactory | None = None,
) -> tuple[bool, str | None]:
    """Verify local post-cutover chain truth against the external B2 attestation set.

    This is intentionally read-only with respect to both local ACE state and remote
    B2 state. Missing remote objects are audit failures, not an implicit sync.
    """

    try:
        resolved_client = client if client is not None else _client_from_factory(client_factory)
    except B2ConfigurationError as exc:
        return False, f"{EXTERNAL_ATTESTATION_NOT_CONFIGURED}: {exc}"

    try:
        result = verify_external_attestation_with_client(resolved_client, db_path)
    except AttestationLocalChainError as exc:
        return False, f"external_attestation_local_chain_invalid: {exc}"
    except AttestationRemoteSetMismatchError as exc:
        return False, str(exc)
    except AttestationRemoteVersionError as exc:
        return False, str(exc)
    except B2ObjectNotVisibleError as exc:
        return False, f"external_attestation_eventual_consistency_pending: {exc}"
    except B2ConfigurationError as exc:
        return False, f"external_attestation_auth_failed: {exc}"
    except (B2ApiError, B2AttestationError) as exc:
        return False, f"external_attestation_remote_unreachable: {exc}"
    return result.ok, result.detail


def verify_external_attestation_with_client(
    client: AttestationClient,
    db_path: Path | str = DB_PATH,
) -> ExternalAttestationCheckResult:
    """Read-only exact-set external attestation verification using an injected client."""

    instance_id = getattr(client.config, "instance_id")
    object_prefix = getattr(client.config, "object_prefix", "")
    expected = expected_attestation_objects(db_path, instance_id=instance_id, object_prefix=object_prefix)
    if not expected:
        raise AttestationLocalChainError("no post-cutover events available for attestation")
    expected_by_name = {item.file_name: item for item in expected}
    prefix = _common_prefix(expected_by_name)

    remote_names = _list_remote_names_for_audit(client, prefix)
    expected_names = set(expected_by_name)
    missing = sorted(expected_names - remote_names)
    if missing:
        item = expected_by_name[missing[0]]
        raise AttestationRemoteSetMismatchError(
            f"external_attestation_missing event_sequence={item.record.event_sequence} event_id={item.record.event_id}"
        )
    extra = sorted(remote_names - expected_names)
    if extra:
        detail = _classify_remote_extra(client, extra[0], expected[0])
        raise AttestationRemoteSetMismatchError(detail)

    remote_by_name = {obj.file_name: obj for obj in client.list_prefix(prefix)}
    versions_by_name = _list_remote_versions_for_audit(client, prefix)
    for item in expected_by_name.values():
        try:
            _verify_remote_listing_object(remote_by_name[item.file_name], item)
            _verify_remote_versions_from_list(versions_by_name.get(item.file_name, []), item)
        except AttestationRemoteVersionError as exc:
            raise AttestationRemoteVersionError(_classify_remote_version_error(str(exc), item)) from exc

    return ExternalAttestationCheckResult(
        ok=True,
        detail=(
            "external_attestation=ok backend=b2 "
            f"checked={len(expected_by_name)} missing=0 extra=0 mismatched=0 conflicting_versions=0 "
            f"cutover_event_id={expected[0].record.cutover_event_id} instance_id={instance_id}"
        ),
    )


def _client_from_factory(client_factory: AttestationClientFactory | None) -> AttestationClient:
    if client_factory is not None:
        return client_factory()
    from .backblaze import B2AttestationClient

    return B2AttestationClient(B2Config.from_env())


def _list_remote_names_for_audit(client: AttestationClient, prefix: str) -> set[str]:
    try:
        return {obj.file_name for obj in client.list_prefix(prefix)}
    except B2ApiError as exc:
        raise AttestationRemoteSetMismatchError(f"external_attestation_listing_incomplete: {exc}") from exc


def _list_remote_versions_for_audit(client: AttestationClient, prefix: str):
    try:
        versions_by_name: dict[str, list[object]] = {}
        for version in client.list_versions(prefix):
            versions_by_name.setdefault(version.file_name, []).append(version)
        return versions_by_name
    except B2ApiError as exc:
        raise AttestationRemoteVersionError(f"external_attestation_version_listing_incomplete: {exc}") from exc


def _verify_remote_listing_object(remote: object, item: AttestationObject) -> None:
    size = getattr(remote, "size", None)
    if size is not None and size != len(item.body):
        raise AttestationRemoteVersionError(f"remote object listing size mismatch: {item.file_name}")
    content_sha1 = getattr(remote, "content_sha1", None)
    if content_sha1 is not None and content_sha1 != hashlib.sha1(item.body).hexdigest():
        raise AttestationRemoteVersionError(f"remote object listing content hash mismatch: {item.file_name}")


def _verify_remote_versions_from_list(versions: list[object], item: AttestationObject) -> None:
    upload_versions = [version for version in versions if getattr(version, "file_name", None) == item.file_name and getattr(version, "action", None) == "upload"]
    if not upload_versions:
        raise AttestationRemoteVersionError(f"remote object has no visible upload version: {item.file_name}")
    earliest = min(upload_versions, key=lambda version: version.upload_timestamp if version.upload_timestamp is not None else -1)
    if len(upload_versions) > 1:
        for version in upload_versions:
            if version.file_id == earliest.file_id:
                continue
            if version.content_sha1 is not None and version.content_sha1 != earliest.content_sha1:
                raise AttestationRemoteVersionError(f"remote object has conflicting later version: {item.file_name}")
            if version.size is not None and earliest.size is not None and version.size != earliest.size:
                raise AttestationRemoteVersionError(f"remote object has conflicting later version: {item.file_name}")


def _classify_remote_extra(client: AttestationClient, file_name: str, reference: AttestationObject) -> str:
    try:
        body = client.read_object(file_name)
    except B2AttestationError:
        return f"external_attestation_remote_extra file_name={file_name}"
    try:
        from .manifest import parse_attestation_record

        parse_attestation_record(
            body.decode("utf-8").strip(),
            expected_instance_id=reference.record.instance_id,
            expected_cutover_event_id=reference.record.cutover_event_id,
        )
    except Exception:  # noqa: BLE001 - malformed/colliding remote body is namespace collision evidence.
        return f"external_attestation_namespace_collision file_name={file_name}"
    return f"external_attestation_remote_extra file_name={file_name}"


def _classify_remote_version_error(message: str, item: AttestationObject) -> str:
    if "schema mismatch" in message or "record mismatch" in message:
        return f"external_attestation_mismatch event_sequence={item.record.event_sequence} event_id={item.record.event_id}"
    if "body mismatch" in message:
        return f"external_attestation_mismatch event_sequence={item.record.event_sequence} event_id={item.record.event_id}"
    if "conflicting later version" in message:
        return f"external_attestation_conflicting_version event_sequence={item.record.event_sequence} event_id={item.record.event_id}"
    if "no visible upload version" in message:
        return f"external_attestation_version_visibility_unverified event_sequence={item.record.event_sequence} event_id={item.record.event_id}"
    return f"external_attestation_mismatch event_sequence={item.record.event_sequence} event_id={item.record.event_id}: {message}"
