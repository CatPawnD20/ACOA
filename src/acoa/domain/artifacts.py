"""Immutable application-artifact versions and portable storage objects; EP-05.03."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.composition import ComposedDraft, DraftKind
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


@dataclass(frozen=True, slots=True)
class ArtifactObject:
    storage_key: str
    content: bytes = field(repr=False)
    content_sha256: str
    media_type: str

    def __post_init__(self) -> None:
        require_text(self.storage_key)
        require_text(self.media_type)
        if not isinstance(self.content, bytes) or not self.content:
            raise DomainError("An artifact storage object requires nonempty immutable bytes.")
        require_sha256(self.content_sha256)
        if sha256(self.content).hexdigest() != self.content_sha256:
            raise DomainError("An artifact storage object must bind its exact bytes.")


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    artifact_id: UUID
    version: int
    application_id: UUID
    kind: DraftKind
    source_draft_id: UUID
    source_binding_sha256: str
    media_type: str
    content_sha256: str
    content_size: int
    storage_key: str
    created_at: datetime
    record_sha256: str

    def __post_init__(self) -> None:
        for identifier in (self.artifact_id, self.application_id, self.source_draft_id):
            require_identifier(identifier)
        require_version(self.version)
        if not isinstance(self.kind, DraftKind):
            raise DomainError("An artifact version requires an explicit draft kind.")
        require_sha256(self.source_binding_sha256)
        require_text(self.media_type)
        require_sha256(self.content_sha256)
        if isinstance(self.content_size, bool) or not isinstance(self.content_size, int):
            raise DomainError("An artifact content size must be an integer.")
        if self.content_size <= 0 or self.content_size > 10_000_000:
            raise DomainError("An artifact exceeds its bounded content-size contract.")
        if self.storage_key != artifact_storage_key(
            self.artifact_id, self.version, self.content_sha256
        ):
            raise DomainError("An artifact storage key must derive from its immutable identity.")
        require_timestamp(self.created_at)
        require_sha256(self.record_sha256)
        if self.record_sha256 != artifact_version_sha256(self):
            raise DomainError("An artifact version digest must bind its exact metadata.")


def artifact_storage_key(artifact_id: UUID, version: int, content_sha256: str) -> str:
    require_identifier(artifact_id)
    require_version(version)
    require_sha256(content_sha256)
    return f"artifacts/{artifact_id}/{version}/{content_sha256}"


def artifact_version_sha256(artifact: ArtifactVersion) -> str:
    return artifact_version_binding_sha256(
        artifact.artifact_id,
        artifact.version,
        artifact.application_id,
        artifact.kind,
        artifact.source_draft_id,
        artifact.source_binding_sha256,
        artifact.media_type,
        artifact.content_sha256,
        artifact.content_size,
        artifact.storage_key,
        artifact.created_at,
    )


def artifact_version_binding_sha256(
    artifact_id: UUID,
    version: int,
    application_id: UUID,
    kind: DraftKind,
    source_draft_id: UUID,
    source_binding_sha256: str,
    media_type: str,
    content_sha256: str,
    content_size: int,
    storage_key: str,
    created_at: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-artifact-version/1",
            "artifact_id": str(artifact_id),
            "version": version,
            "application_id": str(application_id),
            "kind": kind.value,
            "source_draft_id": str(source_draft_id),
            "source_binding_sha256": source_binding_sha256,
            "media_type": media_type,
            "content_sha256": content_sha256,
            "content_size": content_size,
            "storage_key": storage_key,
            "created_at": created_at.astimezone(UTC).isoformat(),
        }
    )


def artifact_from_draft(
    artifact_id: UUID, version: int, draft: ComposedDraft, created_at: datetime
) -> tuple[ArtifactVersion, ArtifactObject]:
    if not isinstance(draft, ComposedDraft):
        raise DomainError("An artifact version requires a validated composed draft.")
    require_timestamp(created_at)
    if created_at < draft.composed_at:
        raise DomainError("An artifact version cannot predate its source draft.")
    content = draft.content.encode("utf-8")
    key = artifact_storage_key(artifact_id, version, draft.content_sha256)
    digest = artifact_version_binding_sha256(
        artifact_id,
        version,
        draft.application_id,
        draft.kind,
        draft.draft_id,
        draft.binding_sha256,
        draft.media_type,
        draft.content_sha256,
        len(content),
        key,
        created_at,
    )
    version_record = ArtifactVersion(
        artifact_id,
        version,
        draft.application_id,
        draft.kind,
        draft.draft_id,
        draft.binding_sha256,
        draft.media_type,
        draft.content_sha256,
        len(content),
        key,
        created_at,
        digest,
    )
    return version_record, ArtifactObject(key, content, draft.content_sha256, draft.media_type)
