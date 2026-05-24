from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from ace.storage import CUTOVER_EVENT_TYPE, DB_PATH, connect_readonly, post_cutover_event_hash_chain

from .backblaze import B2AttestationClient, B2ConflictError, B2ObjectVersion
from .manifest import (
    ATTESTATION_CHAIN_ID,
    AttestationRecord,
    AttestationSchemaError,
    attestation_record_from_event_row,
    parse_attestation_record,
)


class AttestationSyncError(RuntimeError):
    """Base class for V1.1 external attestation sync failures."""


class AttestationNamespaceError(AttestationSyncError):
    """Raised when local/remote namespace configuration is inconsistent."""


class AttestationRemoteSetMismatchError(AttestationSyncError):
    """Raised when remote prefix objects are not exactly the expected set."""


class AttestationRemoteVersionError(AttestationSyncError):
    """Raised when remote object versions violate V1.1 policy."""


class AttestationLocalChainError(AttestationSyncError):
    """Raised when local post-cutover chain is not safe to attest."""


class AttestationClient(Protocol):
    config: object

    def list_prefix(self, prefix: str): ...

    def list_versions(self, prefix: str) -> list[B2ObjectVersion]: ...

    def upload_if_absent(self, file_name: str, content: bytes, *, content_type: str = "application/json"): ...

    def read_object(self, file_name: str) -> bytes: ...


@dataclass(frozen=True)
class AttestationObject:
    file_name: str
    record: AttestationRecord
    body: bytes


@dataclass(frozen=True)
class AttestationSyncResult:
    expected_count: int
    uploaded_count: int
    existing_count: int
    prefix: str
    cutover_event_id: str


def derive_attestation_prefix(*, object_prefix: str, instance_id: str, cutover_event_id: str) -> str:
    _require_namespace_component(instance_id, "instance_id")
    _require_namespace_component(cutover_event_id, "cutover_event_id")
    base = object_prefix.strip("/")
    parts = [part for part in (base, ATTESTATION_CHAIN_ID, instance_id, f"cutover_{cutover_event_id}") if part]
    return "/".join(parts) + "/"


def attestation_object_name(prefix: str, record: AttestationRecord) -> str:
    sequence = f"{record.event_sequence:012d}"
    return f"{prefix}seq_{sequence}__{record.event_id}.json"


def expected_attestation_objects(
    db_path: Path | str = DB_PATH,
    *,
    instance_id: str,
    object_prefix: str = "",
) -> list[AttestationObject]:
    """Derive all expected post-cutover attestation objects from local DB truth."""

    ok, detail = post_cutover_event_hash_chain(db_path)
    if not ok:
        raise AttestationLocalChainError(f"post-cutover chain is not attestable: {detail}")

    with connect_readonly(db_path) as connection:
        cutovers = connection.execute(
            """
            SELECT id, event_id
            FROM events
            WHERE event_type = ?
              AND event_sequence = 1
              AND previous_event_hash IS NULL
            ORDER BY id ASC
            """,
            (CUTOVER_EVENT_TYPE,),
        ).fetchall()
        if len(cutovers) != 1:
            raise AttestationLocalChainError("cutover boundary missing or ambiguous")
        cutover = cutovers[0]
        rows = connection.execute(
            """
            SELECT id, event_id, event_hash, previous_event_hash, event_sequence, created_at
            FROM events
            WHERE id >= ?
            ORDER BY event_sequence ASC, id ASC
            """,
            (cutover["id"],),
        ).fetchall()

    prefix = derive_attestation_prefix(
        object_prefix=object_prefix,
        instance_id=instance_id,
        cutover_event_id=cutover["event_id"],
    )
    objects: list[AttestationObject] = []
    for row in rows:
        record = attestation_record_from_event_row(dict(row), instance_id=instance_id, cutover_event_id=cutover["event_id"])
        body = (record.to_canonical_json() + "\n").encode("utf-8")
        objects.append(AttestationObject(file_name=attestation_object_name(prefix, record), record=record, body=body))
    return objects


def sync_attestation_records(
    client: B2AttestationClient,
    db_path: Path | str = DB_PATH,
    *,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> AttestationSyncResult:
    """Synchronize local post-cutover hashes to B2 using the approved V1.1 sequence.

    The sequence is intentionally full-scan and idempotent:
    1. derive all local expected records from readonly post-cutover chain truth;
    2. list the entire remote prefix;
    3. fail on remote extras before upload;
    4. verify versions for existing objects;
    5. upload missing objects with client-level conflict/readback protection;
    6. re-list the prefix;
    7. require exact set equality;
    8. verify every expected object's earliest upload version and body.
    """

    if progress_every <= 0:
        raise ValueError("progress_every must be positive")

    instance_id = getattr(client.config, "instance_id")
    object_prefix = getattr(client.config, "object_prefix", "")
    expected = expected_attestation_objects(db_path, instance_id=instance_id, object_prefix=object_prefix)
    if not expected:
        raise AttestationLocalChainError("no post-cutover events available for attestation")
    expected_by_name = {item.file_name: item for item in expected}
    prefix = _common_prefix(expected_by_name)

    _emit_progress(progress_callback, f"sync_start expected={len(expected_by_name)} prefix={prefix}")

    initial_remote_names = _list_remote_names(client, prefix)
    _assert_no_remote_extras(initial_remote_names, set(expected_by_name))
    _emit_progress(progress_callback, f"remote_initial count={len(initial_remote_names)}")

    uploaded = 0
    existing = 0
    for index, (file_name, item) in enumerate(expected_by_name.items(), start=1):
        _emit_periodic_progress(
            progress_callback,
            index,
            progress_every,
            f"object_progress checked={index - 1}/{len(expected_by_name)} uploaded={uploaded} "
            f"existing={existing} event_sequence={item.record.event_sequence}",
        )
        if file_name in initial_remote_names:
            _verify_remote_object(client, item)
            existing += 1
            _emit_periodic_progress(
                progress_callback,
                index,
                progress_every,
                f"object_progress checked={index}/{len(expected_by_name)} uploaded={uploaded} "
                f"existing={existing} event_sequence={item.record.event_sequence}",
            )
            continue
        try:
            client.upload_if_absent(file_name, item.body)
        except B2ConflictError as exc:
            raise AttestationRemoteVersionError(f"conflicting remote object during upload: {file_name}") from exc
        uploaded += 1
        _verify_remote_object(client, item)
        _emit_periodic_progress(
            progress_callback,
            index,
            progress_every,
            f"object_progress checked={index}/{len(expected_by_name)} uploaded={uploaded} "
            f"existing={existing} event_sequence={item.record.event_sequence}",
        )

    _emit_progress(
        progress_callback,
        f"object_pass_complete checked={len(expected_by_name)} uploaded={uploaded} existing={existing}",
    )
    _emit_progress(progress_callback, "remote_final_list_start")
    final_remote_names = _list_remote_names(client, prefix)
    if final_remote_names != set(expected_by_name):
        missing = sorted(set(expected_by_name) - final_remote_names)
        extra = sorted(final_remote_names - set(expected_by_name))
        raise AttestationRemoteSetMismatchError(
            f"remote attestation set mismatch after sync: missing={missing[:3]} extra={extra[:3]}"
        )

    _emit_progress(progress_callback, f"remote_final count={len(final_remote_names)}")

    for index, item in enumerate(expected_by_name.values(), start=1):
        _emit_periodic_progress(
            progress_callback,
            index,
            progress_every,
            f"final_verify_progress checked={index - 1}/{len(expected_by_name)} "
            f"event_sequence={item.record.event_sequence}",
        )
        _verify_remote_object(client, item)
        _emit_periodic_progress(
            progress_callback,
            index,
            progress_every,
            f"final_verify_progress checked={index}/{len(expected_by_name)} "
            f"event_sequence={item.record.event_sequence}",
        )

    _emit_progress(progress_callback, f"final_verify_complete checked={len(expected_by_name)}")

    return AttestationSyncResult(
        expected_count=len(expected_by_name),
        uploaded_count=uploaded,
        existing_count=existing,
        prefix=prefix,
        cutover_event_id=expected[0].record.cutover_event_id,
    )


def _verify_remote_object(client: AttestationClient, item: AttestationObject) -> None:
    versions = [version for version in client.list_versions(item.file_name) if version.file_name == item.file_name]
    upload_versions = [version for version in versions if version.action == "upload"]
    if not upload_versions:
        raise AttestationRemoteVersionError(f"remote object has no visible upload version: {item.file_name}")
    earliest = min(upload_versions, key=lambda version: version.upload_timestamp if version.upload_timestamp is not None else -1)
    remote_body = client.read_object(item.file_name)
    if remote_body != item.body:
        raise AttestationRemoteVersionError(f"remote object body mismatch: {item.file_name}")
    try:
        parsed = parse_attestation_record(
            remote_body.decode("utf-8").strip(),
            expected_instance_id=item.record.instance_id,
            expected_cutover_event_id=item.record.cutover_event_id,
        )
    except (UnicodeDecodeError, AttestationSchemaError) as exc:
        raise AttestationRemoteVersionError(f"remote object schema mismatch: {item.file_name}") from exc
    if parsed != item.record:
        raise AttestationRemoteVersionError(f"remote object record mismatch: {item.file_name}")
    if len(upload_versions) > 1:
        for version in upload_versions:
            if version.file_id == earliest.file_id:
                continue
            if version.content_sha1 is not None and version.content_sha1 != earliest.content_sha1:
                raise AttestationRemoteVersionError(f"remote object has conflicting later version: {item.file_name}")
            if version.size is not None and earliest.size is not None and version.size != earliest.size:
                raise AttestationRemoteVersionError(f"remote object has conflicting later version: {item.file_name}")


def _list_remote_names(client: AttestationClient, prefix: str) -> set[str]:
    return {obj.file_name for obj in client.list_prefix(prefix)}


def _assert_no_remote_extras(remote_names: set[str], expected_names: set[str]) -> None:
    extras = sorted(remote_names - expected_names)
    if extras:
        raise AttestationRemoteSetMismatchError(f"remote attestation prefix contains unexpected objects: {extras[:3]}")


def _emit_progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _emit_periodic_progress(
    progress_callback: Callable[[str], None] | None,
    index: int,
    progress_every: int,
    message: str,
) -> None:
    if index == 1 or index % progress_every == 0:
        _emit_progress(progress_callback, message)


def _common_prefix(expected_by_name: Mapping[str, AttestationObject]) -> str:
    first = next(iter(expected_by_name.values()))
    marker = f"seq_{first.record.event_sequence:012d}__{first.record.event_id}.json"
    return first.file_name.removesuffix(marker)


def _require_namespace_component(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AttestationNamespaceError(f"{field_name} must be a non-empty string")
    if any(part in value for part in ("..", "//", "\\")) or value.startswith("/") or value.endswith("/"):
        raise AttestationNamespaceError(f"{field_name} is not safe for B2 attestation namespace")
