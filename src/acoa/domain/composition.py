"""Evidence-bound local application drafts; F-07/P-05/P-06/P-18."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class DraftKind(StrEnum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    FORM_ANSWER = "form_answer"


class UnresolvedFormQuestion(DomainError):
    """A form question has no single verified answer in the bound profile."""


@dataclass(frozen=True, slots=True)
class ProfileFactBinding:
    fact_id: UUID
    version: int
    content_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.fact_id)
        require_version(self.version)
        require_sha256(self.content_sha256)


@dataclass(frozen=True, slots=True)
class FormQuestion:
    question_id: UUID
    prompt: str = field(repr=False)
    prompt_sha256: str
    required_fact_kind: str

    def __post_init__(self) -> None:
        require_identifier(self.question_id)
        _require_bounded_text(self.prompt, 4000)
        require_sha256(self.prompt_sha256)
        validate_composition_fact_kind(self.required_fact_kind)
        if self.prompt_sha256 != form_question_sha256(self.prompt):
            raise DomainError("A form question digest must bind its exact prompt.")


@dataclass(frozen=True, slots=True)
class ComposedDraft:
    draft_id: UUID
    kind: DraftKind
    application_id: UUID
    profile_variant_id: UUID
    profile_variant_version: int
    profile_variant_sha256: str
    opportunity_id: UUID
    opportunity_version: int
    opportunity_sha256: str
    fact_bindings: tuple[ProfileFactBinding, ...]
    question_id: UUID | None
    prompt_sha256: str | None
    media_type: str
    content: str = field(repr=False)
    content_sha256: str
    binding_sha256: str
    composed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (
            self.draft_id,
            self.application_id,
            self.profile_variant_id,
            self.opportunity_id,
        ):
            require_identifier(identifier)
        require_version(self.profile_variant_version)
        require_version(self.opportunity_version)
        require_sha256(self.profile_variant_sha256)
        require_sha256(self.opportunity_sha256)
        require_sha256(self.content_sha256)
        require_sha256(self.binding_sha256)
        require_timestamp(self.composed_at)
        if not isinstance(self.kind, DraftKind):
            raise DomainError("A composed draft requires an explicit material kind.")
        if not isinstance(self.fact_bindings, tuple) or not self.fact_bindings:
            raise DomainError("A composed draft requires immutable verified fact bindings.")
        if any(not isinstance(item, ProfileFactBinding) for item in self.fact_bindings):
            raise DomainError("A composed draft contains an invalid fact binding.")
        identities = tuple((item.fact_id, item.version) for item in self.fact_bindings)
        if len(set(identities)) != len(identities):
            raise DomainError("A composed draft cannot repeat a profile fact version.")
        if self.kind is DraftKind.FORM_ANSWER:
            if self.question_id is None or self.prompt_sha256 is None:
                raise DomainError("A form answer must bind its exact question.")
            require_identifier(self.question_id)
            require_sha256(self.prompt_sha256)
        elif self.question_id is not None or self.prompt_sha256 is not None:
            raise DomainError("Only a form answer may bind a form question.")
        if self.media_type != "text/plain; charset=utf-8":
            raise DomainError("EP-05.01 drafts require canonical UTF-8 plain text.")
        _require_bounded_text(self.content, 200_000)
        if any(
            (ord(character) < 32 and character not in "\n\t") or ord(character) == 127
            for character in self.content
        ):
            raise DomainError("A composed draft contains an invalid plain-text character.")
        if self.content_sha256 != sha256(self.content.encode("utf-8")).hexdigest():
            raise DomainError("A draft content digest must bind its exact UTF-8 bytes.")
        if self.binding_sha256 != composition_draft_binding_sha256(self):
            raise DomainError("A draft digest must bind its exact content and source versions.")


def _require_bounded_text(value: object, maximum: int) -> None:
    require_text(value)
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("Composition text exceeds its bounded contract.")


def validate_composition_fact_kind(value: object) -> None:
    _require_bounded_text(value, 100)
    if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_]*", value) is None:
        raise DomainError("A composition fact kind must use a canonical identifier.")


def form_question_sha256(prompt: str) -> str:
    _require_bounded_text(prompt, 4000)
    return content_digest({"schema": "acoa-form-question/1", "prompt": prompt})


def composition_draft_binding_sha256(draft: ComposedDraft) -> str:
    return composition_binding_sha256(
        draft.draft_id,
        draft.kind,
        draft.application_id,
        draft.profile_variant_id,
        draft.profile_variant_version,
        draft.profile_variant_sha256,
        draft.opportunity_id,
        draft.opportunity_version,
        draft.opportunity_sha256,
        draft.fact_bindings,
        draft.question_id,
        draft.prompt_sha256,
        draft.media_type,
        draft.content_sha256,
        draft.composed_at,
    )


def composition_binding_sha256(
    draft_id: UUID,
    kind: DraftKind,
    application_id: UUID,
    profile_variant_id: UUID,
    profile_variant_version: int,
    profile_variant_sha256: str,
    opportunity_id: UUID,
    opportunity_version: int,
    opportunity_sha256: str,
    fact_bindings: tuple[ProfileFactBinding, ...],
    question_id: UUID | None,
    prompt_sha256: str | None,
    media_type: str,
    content_sha256: str,
    composed_at: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-composed-draft/1",
            "draft_id": str(draft_id),
            "kind": kind.value,
            "application_id": str(application_id),
            "profile_variant_id": str(profile_variant_id),
            "profile_variant_version": profile_variant_version,
            "profile_variant_sha256": profile_variant_sha256,
            "opportunity_id": str(opportunity_id),
            "opportunity_version": opportunity_version,
            "opportunity_sha256": opportunity_sha256,
            "fact_bindings": [
                {
                    "fact_id": str(item.fact_id),
                    "version": item.version,
                    "content_sha256": item.content_sha256,
                }
                for item in fact_bindings
            ],
            "question_id": str(question_id) if question_id is not None else None,
            "prompt_sha256": prompt_sha256,
            "media_type": media_type,
            "content_sha256": content_sha256,
            "composed_at": composed_at.astimezone(UTC).isoformat(),
        }
    )
