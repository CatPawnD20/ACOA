"""Immutable PostgreSQL records for prepared mail and provider draft receipts."""

import json
from dataclasses import asdict
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.mail import (
    MailDraftReceipt,
    MailDraftRecord,
    ProviderDraft,
    draft_request_sha256,
    require_provider_name,
)
from acoa.domain.values import require_identifier
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(value: MailDraftRecord | MailDraftReceipt) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(prior: tuple[object, object] | None, digest: str, payload: str) -> None:
    if prior is None or prior[0] != digest or prior[1] != json.loads(payload):
        raise DatabaseBoundaryError("A mail draft record must remain immutable.")


class MailDraftRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_draft(self, draft: MailDraftRecord) -> None:
        if not isinstance(draft, MailDraftRecord):
            raise DatabaseBoundaryError("A validated mail draft record is required.")
        application_open = self.connection.execute(
            text("""SELECT 1 FROM acoa.applications
                WHERE application_id=:application AND state='open'"""),
            {"application": draft.application_id},
        ).scalar_one_or_none()
        if application_open is None:
            raise DatabaseBoundaryError("A mail draft requires an open application.")
        payload, digest = _encoded(draft)
        source = draft.source_message
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mail_drafts
                (draft_id,application_id,account_id,recipient_id,kind,policy_action,
                 content_sha256,provider_thread_id,source_message_id,prepared_at,
                 draft,record_sha256)
                VALUES (:draft,:application,:account,:recipient,:kind,:action,:content,
                    :thread,:source_message,:prepared,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (draft_id) DO NOTHING RETURNING draft_id"""),
            {
                "draft": draft.draft_id,
                "application": draft.application_id,
                "account": draft.account_id,
                "recipient": draft.recipient_id,
                "kind": draft.kind.value,
                "action": draft.policy_request.action.value,
                "content": draft_request_sha256(draft.request),
                "thread": draft.request.provider_thread_id,
                "source_message": None if source is None else source.provider_message_id,
                "prepared": draft.request.created_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("SELECT record_sha256,draft FROM acoa.mail_drafts WHERE draft_id=:draft"),
            {"draft": draft.draft_id},
        ).one_or_none()
        _require_exact(prior, digest, payload)

    def load_provider_draft(self, draft_id: UUID, provider: str) -> ProviderDraft | None:
        require_identifier(draft_id)
        require_provider_name(provider)
        row = self.connection.execute(
            text("""SELECT provider_draft_id,provider_message_id,provider_thread_id
                FROM acoa.mail_provider_draft_receipts
                WHERE draft_id=:draft AND provider=:provider"""),
            {"draft": draft_id, "provider": provider},
        ).one_or_none()
        if row is None:
            return None
        return ProviderDraft(draft_id, cast(str, row[0]), cast(str, row[1]), cast(str, row[2]))

    def record_provider_draft(self, receipt: MailDraftReceipt) -> None:
        if not isinstance(receipt, MailDraftReceipt):
            raise DatabaseBoundaryError("A validated provider draft receipt is required.")
        payload, digest = _encoded(receipt)
        provider_draft = receipt.draft
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.mail_provider_draft_receipts
                (draft_id,provider,provider_draft_id,provider_message_id,provider_thread_id,
                 recorded_at,receipt,record_sha256)
                VALUES (:draft,:provider,:provider_draft,:provider_message,:provider_thread,
                    :recorded,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (draft_id) DO NOTHING RETURNING draft_id"""),
            {
                "draft": provider_draft.draft_id,
                "provider": receipt.provider,
                "provider_draft": provider_draft.provider_draft_id,
                "provider_message": provider_draft.provider_message_id,
                "provider_thread": provider_draft.provider_thread_id,
                "recorded": receipt.recorded_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT record_sha256,receipt
                FROM acoa.mail_provider_draft_receipts WHERE draft_id=:draft"""),
            {"draft": provider_draft.draft_id},
        ).one_or_none()
        _require_exact(prior, digest, payload)
