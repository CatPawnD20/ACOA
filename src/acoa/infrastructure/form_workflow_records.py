"""Immutable PostgreSQL records for unresolved questions and approved answers."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.form_workflow import ApprovedFormAnswer, FormQuestionRequest
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(value: FormQuestionRequest | ApprovedFormAnswer) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(prior: Sequence[object] | None, digest: str, payload: str) -> None:
    if prior is None or prior[0] != digest or prior[1] != json.loads(payload):
        raise DatabaseBoundaryError("A form workflow record must remain immutable.")


class FormWorkflowRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_question(self, request: FormQuestionRequest) -> None:
        if not isinstance(request, FormQuestionRequest):
            raise DatabaseBoundaryError("A validated form-question request is required.")
        eligible = self.connection.execute(
            text("""SELECT 1 FROM acoa.task_runs task
                JOIN acoa.opportunity_versions opportunity
                  ON opportunity.opportunity_id=:opportunity
                 AND opportunity.version=:opportunity_version
                WHERE task.task_id=:task AND task.kind='compose_artifact'
                  AND task.input_ref=:application
                  AND opportunity.content_sha256=:opportunity_hash
                  AND ((task.state='running' AND task.lease_until>clock_timestamp())
                       OR (task.state='waiting_user'
                           AND task.waiting_question_id=:question))"""),
            {
                "opportunity": request.opportunity_id,
                "opportunity_version": request.opportunity_version,
                "opportunity_hash": request.opportunity_sha256,
                "task": request.task_id,
                "application": request.application_id,
                "question": request.question.question_id,
            },
        ).scalar_one_or_none()
        if eligible is None:
            raise DatabaseBoundaryError(
                "A form question requires its exact active application-composition task."
            )
        payload, digest = _encoded(request)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.form_question_requests
                (question_id,application_id,task_id,opportunity_id,opportunity_version,
                 opportunity_sha256,prompt_sha256,required_fact_kind,requested_at,
                 request,record_sha256)
                VALUES (:question,:application,:task,:opportunity,:version,:opportunity_hash,
                    :prompt_hash,:fact_kind,:requested,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (question_id) DO NOTHING RETURNING question_id"""),
            {
                "question": request.question.question_id,
                "application": request.application_id,
                "task": request.task_id,
                "opportunity": request.opportunity_id,
                "version": request.opportunity_version,
                "opportunity_hash": request.opportunity_sha256,
                "prompt_hash": request.question.prompt_sha256,
                "fact_kind": request.question.required_fact_kind,
                "requested": request.requested_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT record_sha256,request FROM acoa.form_question_requests
                WHERE question_id=:question"""),
            {"question": request.question.question_id},
        ).one_or_none()
        _require_exact(prior, digest, payload)

    def record_answer(self, answer: ApprovedFormAnswer) -> None:
        if not isinstance(answer, ApprovedFormAnswer):
            raise DatabaseBoundaryError("A validated approved form answer is required.")
        payload, digest = _encoded(answer)
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:question AS text),0))"),
            {"question": answer.question_id},
        )
        request_exists = self.connection.execute(
            text("""SELECT 1 FROM acoa.form_question_requests
                WHERE question_id=:question AND application_id=:application
                  AND requested_at<=:approved"""),
            {
                "question": answer.question_id,
                "application": answer.application_id,
                "approved": answer.review.reviewed_at,
            },
        ).scalar_one_or_none()
        if request_exists is None:
            raise DatabaseBoundaryError("An approved answer requires its exact form question.")
        prior = self.connection.execute(
            text("""SELECT record_sha256,answer FROM acoa.approved_form_answers
                WHERE question_id=:question"""),
            {"question": answer.question_id},
        ).one_or_none()
        if prior is not None:
            _require_exact(prior, digest, payload)
            return
        self.connection.execute(
            text("""INSERT INTO acoa.approved_form_answers
                (answer_id,version,question_id,application_id,answer_sha256,approved_at,
                 answer,record_sha256)
                VALUES (:answer_id,:version,:question,:application,:answer_hash,:approved,
                    CAST(:payload AS jsonb),:digest)"""),
            {
                "answer_id": answer.answer_id,
                "version": answer.version,
                "question": answer.question_id,
                "application": answer.application_id,
                "answer_hash": answer.answer_sha256,
                "approved": answer.review.reviewed_at,
                "payload": payload,
                "digest": digest,
            },
        )
