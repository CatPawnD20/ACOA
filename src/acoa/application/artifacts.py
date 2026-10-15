"""Persist verified draft bytes before registering immutable artifact metadata."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from acoa.domain.artifacts import ArtifactObject, ArtifactVersion, artifact_from_draft
from acoa.domain.composition import ComposedDraft
from acoa.domain.values import DomainError


class PortableArtifactStorage(Protocol):
    def write(self, artifact: ArtifactObject) -> None: ...

    def read(self, storage_key: str) -> ArtifactObject: ...


class ArtifactRecords(Protocol):
    def record(self, artifact: ArtifactVersion) -> None: ...


def persist_draft_artifact(
    artifact_id: UUID,
    version: int,
    draft: ComposedDraft,
    storage: PortableArtifactStorage,
    records: ArtifactRecords,
    now: datetime,
) -> ArtifactVersion:
    """Write and verify immutable bytes before exposing their metadata for later actions."""
    artifact, storage_object = artifact_from_draft(artifact_id, version, draft, now)
    storage.write(storage_object)
    persisted = storage.read(artifact.storage_key)
    if persisted != storage_object:
        raise DomainError("Artifact storage verification did not return the exact written bytes.")
    records.record(artifact)
    return artifact
