"""Atomic PostgreSQL reply classification, notification dedupe and daily digest."""

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.mail_notifications import (
    IMMEDIATE_REPLY_KINDS,
    MailDailyDigest,
    MailReplyClassification,
    mail_notification_dedupe_key,
)
from acoa.domain.values import require_timestamp
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _payload(value: MailReplyClassification | MailDailyDigest) -> tuple[str, str]:
    encoded = encode_record(asdict(value))
    return encoded, sha256(encoded.encode()).hexdigest()


class MailNotificationRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_classification(self, classification: MailReplyClassification) -> bool:
        """Persist classification and at most one immediate item in the same transaction."""
        if not isinstance(classification, MailReplyClassification):
            raise DatabaseBoundaryError("A validated mail reply classification is required.")
        self._require_sent_thread_relation(classification)
        payload, digest = _payload(classification)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mail_reply_classifications
                (classification_id,application_id,account_id,provider,provider_event_id,
                 provider_message_id,provider_thread_id,kind,message_snapshot_sha256,
                 relation_evidence_id,classified_at,classification,record_sha256)
                VALUES (:classification,:application,:account,:provider,:event,:message,
                    :thread,:kind,:snapshot,:relation,:classified,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (account_id,provider,provider_event_id) DO NOTHING
                RETURNING classification_id"""),
            {
                "classification": classification.classification_id,
                "application": classification.application_id,
                "account": classification.account_id,
                "provider": classification.provider,
                "event": classification.provider_event_id,
                "message": classification.provider_message_id,
                "thread": classification.provider_thread_id,
                "kind": classification.kind.value,
                "snapshot": classification.message_snapshot_sha256,
                "relation": classification.relation_evidence_id,
                "classified": classification.classified_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is None:
            self._require_existing_classification(classification, payload, digest)
        if classification.kind not in IMMEDIATE_REPLY_KINDS:
            return False
        dedupe_key = mail_notification_dedupe_key(classification)
        notification_id = uuid4()
        created = self.connection.execute(
            text("""INSERT INTO acoa.notification_items
                (notification_id,kind,urgency,dedupe_key,application_id,classification_id,
                 state,created_at)
                VALUES (:notification,'important_reply','immediate',:dedupe,:application,
                    :classification,'pending',:created)
                ON CONFLICT (dedupe_key) DO NOTHING RETURNING notification_id"""),
            {
                "notification": notification_id,
                "dedupe": dedupe_key,
                "application": classification.application_id,
                "classification": classification.classification_id,
                "created": classification.classified_at,
            },
        ).scalar_one_or_none()
        return created is not None

    def _require_sent_thread_relation(self, classification: MailReplyClassification) -> None:
        related: bool = self.connection.execute(
            text("""SELECT EXISTS (
                SELECT 1 FROM acoa.mailbox_events event
                JOIN acoa.mail_sent_records sent
                  ON sent.provider=event.provider
                 AND sent.provider_thread_id=event.provider_thread_id
                JOIN acoa.mail_drafts draft ON draft.draft_id=sent.draft_id
                WHERE event.account_id=:account AND event.provider=:provider
                  AND event.provider_event_id=:event
                  AND event.provider_message_id=:message
                  AND event.provider_thread_id=:thread
                  AND sent.application_id=:application
                  AND draft.account_id=:account
                  AND sent.observed_at<=event.recorded_at
                  AND event.recorded_at<=:classified
                )"""),
            {
                "account": classification.account_id,
                "provider": classification.provider,
                "event": classification.provider_event_id,
                "message": classification.provider_message_id,
                "thread": classification.provider_thread_id,
                "application": classification.application_id,
                "classified": classification.classified_at,
            },
        ).scalar_one()
        if not related:
            raise DatabaseBoundaryError(
                "A reply classification requires its exact sent-thread mailbox event."
            )

    def _require_existing_classification(
        self, classification: MailReplyClassification, payload: str, digest: str
    ) -> None:
        prior = self.connection.execute(
            text("""SELECT classification_id,record_sha256,classification
                FROM acoa.mail_reply_classifications
                WHERE account_id=:account AND provider=:provider AND provider_event_id=:event"""),
            {
                "account": classification.account_id,
                "provider": classification.provider,
                "event": classification.provider_event_id,
            },
        ).one_or_none()
        if (
            prior is None
            or prior[0] != classification.classification_id
            or prior[1] != digest
            or prior[2] != json.loads(payload)
        ):
            raise DatabaseBoundaryError("A mail event classification must remain immutable.")

    def record_daily_digest(
        self, window_start: datetime, window_end: datetime, created_at: datetime
    ) -> MailDailyDigest:
        for value in (window_start, window_end, created_at):
            require_timestamp(value)
        counts = self.connection.execute(
            text("""SELECT
                (SELECT count(*) FROM acoa.mailbox_events
                    WHERE recorded_at>=:start AND recorded_at<:end),
                (SELECT count(*) FROM acoa.mail_reply_classifications
                    WHERE classified_at>=:start AND classified_at<:end),
                (SELECT count(*) FROM acoa.notification_items
                    WHERE urgency='immediate' AND created_at>=:start AND created_at<:end),
                (SELECT count(*) FROM acoa.mail_drafts
                    WHERE kind='reply' AND prepared_at>=:start AND prepared_at<:end),
                (SELECT count(*) FROM acoa.mail_drafts
                    WHERE kind='followup' AND prepared_at>=:start AND prepared_at<:end)"""),
            {"start": window_start, "end": window_end},
        ).one()
        digest = MailDailyDigest(
            uuid4(),
            window_start,
            window_end,
            created_at,
            cast(int, counts[0]),
            cast(int, counts[1]),
            cast(int, counts[2]),
            cast(int, counts[3]),
            cast(int, counts[4]),
        )
        payload, record_hash = _payload(digest)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mail_daily_digests
                (digest_id,window_start,window_end,created_at,incoming_count,
                 classified_count,immediate_count,reply_draft_count,
                 followup_draft_count,digest,record_sha256)
                VALUES (:digest,:start,:end,:created,:incoming,:classified,:immediate,
                    :reply_drafts,:followup_drafts,CAST(:payload AS jsonb),:record_hash)
                ON CONFLICT (window_start,window_end) DO NOTHING RETURNING digest_id"""),
            {
                "digest": digest.digest_id,
                "start": digest.window_start,
                "end": digest.window_end,
                "created": digest.created_at,
                "incoming": digest.incoming_count,
                "classified": digest.classified_count,
                "immediate": digest.immediate_count,
                "reply_drafts": digest.reply_draft_count,
                "followup_drafts": digest.followup_draft_count,
                "payload": payload,
                "record_hash": record_hash,
            },
        ).scalar_one_or_none()
        if inserted is None:
            raise DatabaseBoundaryError("A closed daily digest window can be recorded only once.")
        return digest
