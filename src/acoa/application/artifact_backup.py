"""Hash-verified logical artifact backup and restore without credentials."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from acoa.application.artifacts import PortableArtifactStorage
from acoa.domain.artifacts import ArtifactObject, ArtifactVersion
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_sha256, require_timestamp


@dataclass(frozen=True, slots=True)
class ArtifactBackup:
    artifacts: tuple[ArtifactVersion, ...]
    objects: tuple[ArtifactObject, ...] = field(repr=False)
    created_at: datetime
    backup_sha256: str

    def __post_init__(self) -> None:
        require_timestamp(self.created_at)
        require_sha256(self.backup_sha256)
        if (
            not isinstance(self.artifacts, tuple)
            or not isinstance(self.objects, tuple)
            or not self.artifacts
            or len(self.artifacts) != len(self.objects)
            or any(not isinstance(item, ArtifactVersion) for item in self.artifacts)
            or any(not isinstance(item, ArtifactObject) for item in self.objects)
        ):
            raise DomainError("An artifact backup requires matching metadata and objects.")
        identities = tuple((item.artifact_id, item.version) for item in self.artifacts)
        if len(set(identities)) != len(identities):
            raise DomainError("An artifact backup cannot repeat a version.")
        _verify_pairs(self.artifacts, self.objects)
        if self.backup_sha256 != _backup_digest(self.artifacts, self.created_at):
            raise DomainError("An artifact backup manifest digest is invalid.")


def _verify_pairs(
    artifacts: tuple[ArtifactVersion, ...], objects: tuple[ArtifactObject, ...]
) -> None:
    for artifact, stored in zip(artifacts, objects, strict=True):
        if (
            stored.storage_key != artifact.storage_key
            or stored.content_sha256 != artifact.content_sha256
            or len(stored.content) != artifact.content_size
            or stored.media_type != artifact.media_type
        ):
            raise DomainError("Backup content does not match its artifact metadata.")


def _backup_digest(artifacts: tuple[ArtifactVersion, ...], created_at: datetime) -> str:
    return content_digest(
        {
            "schema": "acoa-artifact-backup/1",
            "artifacts": [item.record_sha256 for item in artifacts],
            "created_at": created_at.astimezone(UTC).isoformat(),
        }
    )


def create_artifact_backup(
    artifacts: tuple[ArtifactVersion, ...], storage: PortableArtifactStorage, now: datetime
) -> ArtifactBackup:
    require_timestamp(now)
    if (
        not isinstance(artifacts, tuple)
        or not artifacts
        or any(not isinstance(item, ArtifactVersion) for item in artifacts)
    ):
        raise DomainError("Backup creation requires immutable artifact versions.")
    if len({(item.artifact_id, item.version) for item in artifacts}) != len(artifacts):
        raise DomainError("An artifact backup cannot repeat a version.")
    objects = tuple(storage.read(item.storage_key, item.media_type) for item in artifacts)
    return ArtifactBackup(artifacts, objects, now, _backup_digest(artifacts, now))


def restore_artifact_backup(backup: ArtifactBackup, storage: PortableArtifactStorage) -> None:
    if not isinstance(backup, ArtifactBackup):
        raise DomainError("Restore requires a validated artifact backup.")
    for artifact, stored in zip(backup.artifacts, backup.objects, strict=True):
        storage.write(stored)
        if storage.read(artifact.storage_key, artifact.media_type) != stored:
            raise DomainError("Restored artifact verification failed.")
