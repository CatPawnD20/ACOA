"""Immutable PostgreSQL relationship between initial-mail sent records and attempts."""

import json
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.mail import MailSentRecord, mail_sent_record_sha256
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class MailSentRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(self, record: MailSentRecord) -> None:
        if not isinstance(record, MailSentRecord):
            raise DatabaseBoundaryError("A validated mail sent record is required.")
        relationship = self.connection.execute(
            text("""SELECT 1 FROM acoa.mail_drafts draft
                JOIN acoa.external_action_attempts attempt
                  ON attempt.application_id=draft.application_id
                WHERE draft.draft_id=:draft AND draft.application_id=:application
                  AND draft.kind='initial_application'
                  AND attempt.attempt_id=:attempt
                  AND attempt.request_id=draft.draft_id
                  AND attempt.prepared->>'provider_id'=CAST(:provider_id AS text)
                  AND attempt.execution_started_at<=:observed
                  AND attempt.state IN ('reconciling','unconfirmed','verified')"""),
            {
                "draft": record.draft_id,
                "application": record.application_id,
                "attempt": record.attempt_id,
                "provider_id": record.provider_id,
                "observed": record.observed_at,
            },
        ).scalar_one_or_none()
        if relationship is None:
            raise DatabaseBoundaryError("A mail sent record requires its dispatched application.")
        payload = encode_record(asdict(record))
        digest = sha256(payload.encode()).hexdigest()
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mail_sent_records
                (source_ref,attempt_id,application_id,draft_id,provider_id,provider,
                 provider_message_id,provider_thread_id,observed_at,snapshot_sha256,
                 record,record_sha256)
                VALUES (:source,:attempt,:application,:draft,:provider_id,:provider,
                    :message,:thread,:observed,:snapshot,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (source_ref) DO NOTHING RETURNING source_ref"""),
            {
                "source": record.source_ref,
                "attempt": record.attempt_id,
                "application": record.application_id,
                "draft": record.draft_id,
                "provider_id": record.provider_id,
                "provider": record.provider,
                "message": record.message.provider_message_id,
                "thread": record.message.provider_thread_id,
                "observed": record.observed_at,
                "snapshot": mail_sent_record_sha256(record),
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("SELECT record_sha256,record FROM acoa.mail_sent_records WHERE source_ref=:ref"),
            {"ref": record.source_ref},
        ).one_or_none()
        if prior is None or prior[0] != digest or prior[1] != json.loads(payload):
            raise DatabaseBoundaryError("A mail sent record must remain immutable.")
