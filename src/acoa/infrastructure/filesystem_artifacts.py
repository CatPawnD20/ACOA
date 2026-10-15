"""Local immutable artifact storage rooted in one explicitly selected directory."""

import os
from hashlib import sha256
from pathlib import Path, PurePosixPath

from acoa.domain.artifacts import ArtifactObject
from acoa.infrastructure.postgres import DatabaseBoundaryError


class FilesystemArtifactStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, storage_key: str, *, create_parent: bool) -> Path:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or not key.parts or any(part in ("", ".", "..") for part in key.parts):
            raise DatabaseBoundaryError("Artifact storage key escapes its dedicated root.")
        candidate = self.root.joinpath(*key.parts)
        if create_parent:
            self.root.mkdir(parents=True, exist_ok=True)
            parent = self.root
            for part in key.parts[:-1]:
                parent = parent / part
                if parent.is_symlink():
                    raise DatabaseBoundaryError("Artifact storage path contains a link.")
                parent.mkdir(exist_ok=True)
        try:
            candidate.resolve(strict=False).relative_to(self.root)
        except ValueError:
            raise DatabaseBoundaryError(
                "Artifact storage key escapes its dedicated root."
            ) from None
        return candidate

    def write(self, artifact: ArtifactObject) -> None:
        if not isinstance(artifact, ArtifactObject):
            raise DatabaseBoundaryError("Storage requires a validated artifact object.")
        path = self._path(artifact.storage_key, create_parent=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if self.read(artifact.storage_key, artifact.media_type) != artifact:
                raise DatabaseBoundaryError(
                    "An artifact storage key is already immutable."
                ) from None
            return
        except OSError:
            raise DatabaseBoundaryError("Artifact storage write failed.") from None
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(artifact.content)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            path.unlink(missing_ok=True)
            raise DatabaseBoundaryError("Artifact storage write failed.") from None

    def read(self, storage_key: str, media_type: str) -> ArtifactObject:
        try:
            content = self._path(storage_key, create_parent=False).read_bytes()
            return ArtifactObject(storage_key, content, sha256(content).hexdigest(), media_type)
        except (OSError, ValueError):
            raise DatabaseBoundaryError("Artifact storage read failed.") from None
