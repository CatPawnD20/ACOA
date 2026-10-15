"""Privacy classification and retention rules for application artifacts; EP-05.04."""

from dataclasses import dataclass
from enum import StrEnum

from acoa.domain.artifacts import ArtifactVersion
from acoa.domain.authorization import SENSITIVE_CATEGORIES, DataCategory, validate_scope
from acoa.domain.composition import DraftKind
from acoa.domain.values import DomainError


class ArtifactRetention(StrEnum):
    APPLICATION_HISTORY = "application_history"


@dataclass(frozen=True, slots=True)
class ArtifactLifecycle:
    artifact: ArtifactVersion
    data_categories: tuple[DataCategory, ...]
    retention: ArtifactRetention

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactVersion):
            raise DomainError("Artifact lifecycle requires an exact artifact version.")
        validate_scope(self.data_categories, DataCategory)
        if not self.data_categories or set(self.data_categories) & SENSITIVE_CATEGORIES:
            raise DomainError("Application artifacts require explicit nonsensitive categories.")
        if self.retention is not ArtifactRetention.APPLICATION_HISTORY:
            raise DomainError("Application artifacts cannot use temporary-data retention.")


def classify_artifact(artifact: ArtifactVersion) -> ArtifactLifecycle:
    material = {
        DraftKind.RESUME: DataCategory.CV,
        DraftKind.COVER_LETTER: DataCategory.COVER_LETTER,
        DraftKind.FORM_ANSWER: DataCategory.APPROVED_ANSWER,
    }[artifact.kind]
    return ArtifactLifecycle(
        artifact,
        (DataCategory.PROFESSIONAL_PROFILE, DataCategory.CONTACT_DETAILS, material),
        ArtifactRetention.APPLICATION_HISTORY,
    )
