"""Durable unknown-form-question handoff and approved answer evidence; EP-05.02."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.composition import FormQuestion
from acoa.domain.reviews import ReviewDecision, UserReview, content_digest, validate_review_target
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


@dataclass(frozen=True, slots=True)
class FormQuestionRequest:
    question: FormQuestion
    application_id: UUID
    task_id: UUID
    opportunity_id: UUID
    opportunity_version: int
    opportunity_sha256: str
    requested_at: datetime
    request_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.question, FormQuestion):
            raise DomainError("A form-question request requires a validated question.")
        for identifier in (self.application_id, self.task_id, self.opportunity_id):
            require_identifier(identifier)
        require_version(self.opportunity_version)
        require_sha256(self.opportunity_sha256)
        require_timestamp(self.requested_at)
        require_sha256(self.request_sha256)
        if self.request_sha256 != form_question_request_sha256(self):
            raise DomainError("A form-question request must bind its exact task and application.")


@dataclass(frozen=True, slots=True)
class ApprovedFormAnswer:
    answer_id: UUID
    version: int
    question_id: UUID
    application_id: UUID
    answer: str = field(repr=False)
    answer_sha256: str
    proposed_at: datetime
    review: UserReview = field(repr=False)

    def __post_init__(self) -> None:
        for identifier in (self.answer_id, self.question_id, self.application_id):
            require_identifier(identifier)
        require_version(self.version)
        _require_answer(self.answer)
        require_sha256(self.answer_sha256)
        require_timestamp(self.proposed_at)
        if self.answer_sha256 != sha256(self.answer.encode("utf-8")).hexdigest():
            raise DomainError("An approved form answer must bind its exact UTF-8 bytes.")
        if not isinstance(self.review, UserReview):
            raise DomainError("A form answer requires an exact user review.")
        validate_review_target(
            self.review,
            self.answer_id,
            self.version,
            self.proposed_at,
            form_answer_proposal_sha256(self),
        )
        if self.review.decision is not ReviewDecision.APPROVE:
            raise DomainError("A rejected form answer cannot resume application work.")


def _require_answer(value: object) -> None:
    require_text(value)
    if not isinstance(value, str) or len(value) > 4000:
        raise DomainError("A form answer exceeds its bounded contract.")
    if any(
        (ord(character) < 32 and character not in "\n\t") or ord(character) == 127
        for character in value
    ):
        raise DomainError("A form answer contains an invalid plain-text character.")


def form_question_request_sha256(request: FormQuestionRequest) -> str:
    return form_question_request_binding_sha256(
        request.question,
        request.application_id,
        request.task_id,
        request.opportunity_id,
        request.opportunity_version,
        request.opportunity_sha256,
        request.requested_at,
    )


def form_question_request_binding_sha256(
    question: FormQuestion,
    application_id: UUID,
    task_id: UUID,
    opportunity_id: UUID,
    opportunity_version: int,
    opportunity_sha256: str,
    requested_at: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-form-question-request/1",
            "question_id": str(question.question_id),
            "prompt_sha256": question.prompt_sha256,
            "required_fact_kind": question.required_fact_kind,
            "application_id": str(application_id),
            "task_id": str(task_id),
            "opportunity_id": str(opportunity_id),
            "opportunity_version": opportunity_version,
            "opportunity_sha256": opportunity_sha256,
            "requested_at": requested_at.astimezone(UTC).isoformat(),
        }
    )


def form_answer_proposal_sha256(answer: ApprovedFormAnswer) -> str:
    return form_answer_proposal_binding_sha256(
        answer.answer_id,
        answer.version,
        answer.question_id,
        answer.application_id,
        answer.answer_sha256,
        answer.proposed_at,
    )


def form_answer_proposal_binding_sha256(
    answer_id: UUID,
    version: int,
    question_id: UUID,
    application_id: UUID,
    answer_sha256: str,
    proposed_at: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-form-answer-proposal/1",
            "answer_id": str(answer_id),
            "version": version,
            "question_id": str(question_id),
            "application_id": str(application_id),
            "answer_sha256": answer_sha256,
            "proposed_at": proposed_at.astimezone(UTC).isoformat(),
        }
    )
