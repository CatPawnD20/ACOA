"""Isolate an unresolved form question to its exact application-composition task."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from acoa.domain.composition import FormQuestion
from acoa.domain.form_workflow import (
    ApprovedFormAnswer,
    FormQuestionRequest,
    form_question_request_binding_sha256,
)
from acoa.domain.research import Opportunity, evidence_is_current
from acoa.domain.tasks import TaskKind, TaskSnapshot, TaskState
from acoa.domain.values import DomainError, require_identifier, require_timestamp


class FormWorkflowRecords(Protocol):
    def record_question(self, request: FormQuestionRequest) -> None: ...

    def record_answer(self, answer: ApprovedFormAnswer) -> None: ...


class UserWaitQueue(Protocol):
    def wait_for_user(
        self, task_id: UUID, owner: UUID, token: UUID, question_id: UUID
    ) -> TaskSnapshot: ...

    def resume(
        self, task_id: UUID, question_id: UUID, answer_evidence_id: UUID
    ) -> TaskSnapshot: ...


def wait_for_form_answer(
    task: TaskSnapshot,
    application_id: UUID,
    opportunity: Opportunity,
    question: FormQuestion,
    records: FormWorkflowRecords,
    queue: UserWaitQueue,
    now: datetime,
) -> FormQuestionRequest:
    require_identifier(application_id)
    require_timestamp(now)
    if not isinstance(task, TaskSnapshot) or task.state is not TaskState.RUNNING:
        raise DomainError("A form question can pause only its running composition task.")
    if task.spec.kind is not TaskKind.COMPOSE_ARTIFACT or task.spec.input_ref != application_id:
        raise DomainError("A form question must bind the exact application-composition task.")
    if task.lease_owner is None or task.lease_token is None:
        raise DomainError("A running composition task requires its fenced lease.")
    if task.lease_until is None or task.lease_until <= now:
        raise DomainError("A form question cannot use an expired task lease.")
    if (
        not isinstance(opportunity, Opportunity)
        or not evidence_is_current(opportunity.publication_evidence, now)
        or not isinstance(question, FormQuestion)
    ):
        raise DomainError("Form handoff requires exact opportunity and question inputs.")
    request = _question_request(task, application_id, opportunity, question, now)
    records.record_question(request)
    queue.wait_for_user(task.spec.task_id, task.lease_owner, task.lease_token, question.question_id)
    return request


def resume_with_approved_answer(
    request: FormQuestionRequest,
    answer: ApprovedFormAnswer,
    records: FormWorkflowRecords,
    queue: UserWaitQueue,
) -> TaskSnapshot:
    if not isinstance(request, FormQuestionRequest) or not isinstance(answer, ApprovedFormAnswer):
        raise DomainError("Form resume requires exact request and approved-answer records.")
    if (
        answer.question_id != request.question.question_id
        or answer.application_id != request.application_id
        or answer.review.reviewed_at < request.requested_at
    ):
        raise DomainError("An approved answer targets another or older form question.")
    records.record_answer(answer)
    return queue.resume(request.task_id, request.question.question_id, answer.answer_id)


def _question_request(
    task: TaskSnapshot,
    application_id: UUID,
    opportunity: Opportunity,
    question: FormQuestion,
    now: datetime,
) -> FormQuestionRequest:
    digest = form_question_request_binding_sha256(
        question,
        application_id,
        task.spec.task_id,
        opportunity.opportunity_id,
        opportunity.version,
        opportunity.content_sha256,
        now,
    )
    return FormQuestionRequest(
        question,
        application_id,
        task.spec.task_id,
        opportunity.opportunity_id,
        opportunity.version,
        opportunity.content_sha256,
        now,
        digest,
    )
