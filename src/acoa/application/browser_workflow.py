"""Deterministic browser workflow boundary; Playwright adapters implement this port."""

from datetime import datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from acoa.domain.artifacts import ArtifactObject, ArtifactVersion
from acoa.domain.browser import (
    BrowserCapability,
    BrowserField,
    BrowserFieldKind,
    BrowserFieldPurpose,
    BrowserFieldValue,
    BrowserHandoff,
    BrowserHandoffReason,
    BrowserPageObservation,
    BrowserPermit,
    BrowserUploadReceipt,
    page_origin,
)
from acoa.domain.composition import DraftKind
from acoa.domain.values import DomainError, require_timestamp


class BrowserAdapter(Protocol):
    """A Playwright-backed implementation may observe, draft and upload, but not submit."""

    def inspect(self, permit: BrowserPermit, url: str) -> BrowserPageObservation: ...

    def fill_draft(
        self,
        permit: BrowserPermit,
        observation: BrowserPageObservation,
        values: tuple[BrowserFieldValue, ...],
    ) -> BrowserPageObservation: ...

    def upload_document(
        self,
        permit: BrowserPermit,
        observation: BrowserPageObservation,
        field: BrowserField,
        artifact: ArtifactObject,
    ) -> BrowserUploadReceipt: ...


class BrowserArtifactReader(Protocol):
    def read(self, storage_key: str, media_type: str) -> ArtifactObject: ...


def _require_permit(
    permit: BrowserPermit,
    capability: BrowserCapability,
    now: datetime,
) -> None:
    require_timestamp(now)
    if not isinstance(permit, BrowserPermit) or capability not in permit.capabilities:
        raise DomainError("Browser operation is outside the explicit task capability.")
    if now >= permit.expires_at:
        raise DomainError("Browser authority has expired.")


def _require_observation(permit: BrowserPermit, observation: BrowserPageObservation) -> None:
    if not isinstance(observation, BrowserPageObservation):
        raise DomainError("Browser work requires a validated page observation.")
    if (
        observation.permit_id != permit.permit_id
        or page_origin(observation.url) != permit.allowed_origin
        or observation.observed_at >= permit.expires_at
    ):
        raise DomainError("Browser observation is outside the current task authority.")


def inspect_form(
    adapter: BrowserAdapter,
    permit: BrowserPermit,
    url: str,
    now: datetime,
) -> BrowserPageObservation:
    _require_permit(permit, BrowserCapability.VISIT, now)
    _require_permit(permit, BrowserCapability.READ_PAGE, now)
    if page_origin(url) != permit.allowed_origin:
        raise DomainError("Browser navigation cannot leave the permitted origin.")
    observation = adapter.inspect(permit, url)
    _require_observation(permit, observation)
    return observation


def handoff_for_form(
    observation: BrowserPageObservation,
    available_purposes: tuple[BrowserFieldPurpose, ...],
) -> BrowserHandoff | None:
    if not isinstance(observation, BrowserPageObservation):
        raise DomainError("Form assessment requires a validated browser observation.")
    if not isinstance(available_purposes, tuple) or any(
        not isinstance(item, BrowserFieldPurpose) for item in available_purposes
    ):
        raise DomainError("Available form values require explicit purposes.")
    if len(set(available_purposes)) != len(available_purposes):
        raise DomainError("Available form purposes cannot repeat.")
    if observation.obstacles:
        return BrowserHandoff(
            BrowserHandoffReason.ACCESS_CHALLENGE,
            observation.observation_id,
            obstacles=observation.obstacles,
        )
    unknown = tuple(
        field.field_id
        for field in observation.fields
        if field.required
        and field.purpose in (BrowserFieldPurpose.UNKNOWN, BrowserFieldPurpose.OTHER)
    )
    if unknown:
        return BrowserHandoff(
            BrowserHandoffReason.UNKNOWN_REQUIRED_FIELD,
            observation.observation_id,
            field_ids=unknown,
        )
    missing = tuple(
        field.field_id
        for field in observation.fields
        if field.required and field.purpose not in available_purposes
    )
    if missing:
        return BrowserHandoff(
            BrowserHandoffReason.REQUIRED_VALUE_MISSING,
            observation.observation_id,
            field_ids=missing,
        )
    return None


def fill_form_draft(
    adapter: BrowserAdapter,
    permit: BrowserPermit,
    observation: BrowserPageObservation,
    values: tuple[BrowserFieldValue, ...],
    now: datetime,
) -> BrowserPageObservation:
    _require_permit(permit, BrowserCapability.FILL_DRAFT, now)
    _require_observation(permit, observation)
    if observation.obstacles:
        raise DomainError("Access challenges require user handoff, never automated filling.")
    fields = {field.field_id: field for field in observation.fields}
    if (
        not isinstance(values, tuple)
        or not values
        or any(not isinstance(value, BrowserFieldValue) for value in values)
        or len({value.field_id for value in values}) != len(values)
    ):
        raise DomainError("Browser draft values must be nonempty and target unique fields.")
    for value in values:
        field = fields.get(value.field_id)
        if field is None or field.purpose != value.purpose:
            raise DomainError("A browser value does not match the observed field purpose.")
        if field.kind is BrowserFieldKind.FILE or field.purpose in (
            BrowserFieldPurpose.UNKNOWN,
            BrowserFieldPurpose.OTHER,
        ):
            raise DomainError("This observed field requires another verified workflow.")
        if sha256(value.value.encode()).hexdigest() != value.value_sha256:
            raise DomainError("A browser value digest does not match its exact content.")
    updated = adapter.fill_draft(permit, observation, values)
    _require_observation(permit, updated)
    if updated.observed_at < observation.observed_at:
        raise DomainError("Browser draft observation cannot predate its source page.")
    return updated


def upload_verified_resume(
    adapter: BrowserAdapter,
    permit: BrowserPermit,
    observation: BrowserPageObservation,
    field_id: UUID,
    artifact: ArtifactVersion,
    storage: BrowserArtifactReader,
    now: datetime,
) -> BrowserUploadReceipt:
    _require_permit(permit, BrowserCapability.UPLOAD_DOCUMENT, now)
    _require_observation(permit, observation)
    if observation.obstacles:
        raise DomainError("Access challenges require user handoff, never document upload.")
    if not isinstance(artifact, ArtifactVersion):
        raise DomainError("Browser upload requires a validated artifact version.")
    stored = storage.read(artifact.storage_key, artifact.media_type)
    if (
        not isinstance(stored, ArtifactObject)
        or artifact.kind is not DraftKind.RESUME
        or artifact.application_id != permit.application_id
        or stored.storage_key != artifact.storage_key
        or stored.media_type != artifact.media_type
        or stored.content_sha256 != artifact.content_sha256
        or len(stored.content) != artifact.content_size
    ):
        raise DomainError("Browser upload requires the exact verified resume artifact.")
    field = next((item for item in observation.fields if item.field_id == field_id), None)
    if (
        field is None
        or field.kind is not BrowserFieldKind.FILE
        or field.purpose is not BrowserFieldPurpose.RESUME_UPLOAD
    ):
        raise DomainError("Resume upload requires the exact observed resume field.")
    if not field.accepted_media_types or artifact.media_type not in field.accepted_media_types:
        raise DomainError("Resume media type is not accepted by the observed field.")
    receipt = adapter.upload_document(permit, observation, field, stored)
    if (
        not isinstance(receipt, BrowserUploadReceipt)
        or receipt.observation_id != observation.observation_id
        or receipt.field_id != field.field_id
        or receipt.artifact_id != artifact.artifact_id
        or receipt.artifact_version != artifact.version
        or receipt.content_sha256 != artifact.content_sha256
        or not observation.observed_at <= receipt.uploaded_at < permit.expires_at
    ):
        raise DomainError("Browser upload receipt does not bind the verified operation.")
    return receipt
