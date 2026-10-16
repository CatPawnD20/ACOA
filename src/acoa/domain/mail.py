"""Provider-neutral mailbox and draft values; EP-06.01."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from acoa.domain.action_requests import PolicyRequest
from acoa.domain.authorization import ActionKind, Channel
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)

EMAIL_PATTERN = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,63}")
PROVIDER_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,99}")


class MailChangeKind(StrEnum):
    MESSAGE_ADDED = "message_added"


class MailSyncStatus(StrEnum):
    COMPLETED = "completed"
    FULL_SYNC_REQUIRED = "full_sync_required"


class MailDraftKind(StrEnum):
    INITIAL_APPLICATION = "initial_application"
    REPLY = "reply"
    FOLLOWUP = "followup"


class MailCursorExpired(DomainError):
    """The provider can no longer continue from the retained mailbox cursor."""


def require_email(value: object) -> str:
    require_text(value)
    if (
        not isinstance(value, str)
        or len(value) > 254
        or value != value.lower()
        or EMAIL_PATTERN.fullmatch(value) is None
    ):
        raise DomainError("A mail address must be a canonical lowercase address.")
    local_part, domain = value.rsplit("@", maxsplit=1)
    domain_labels = domain.split(".")
    if (
        len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in domain_labels
        )
    ):
        raise DomainError("A mail address must be a canonical lowercase address.")
    return value


def require_provider_id(value: object) -> str:
    require_text(value)
    if not isinstance(value, str) or len(value) > 512 or any(ord(char) < 33 for char in value):
        raise DomainError("A provider identifier is invalid.")
    return value


def require_provider_name(value: object) -> str:
    if not isinstance(value, str) or PROVIDER_NAME_PATTERN.fullmatch(value) is None:
        raise DomainError("A mail provider name must use canonical lowercase form.")
    return value


@dataclass(frozen=True, slots=True)
class MailMessageRef:
    provider_message_id: str
    provider_thread_id: str

    def __post_init__(self) -> None:
        require_provider_id(self.provider_message_id)
        require_provider_id(self.provider_thread_id)


@dataclass(frozen=True, slots=True)
class MailPage:
    messages: tuple[MailMessageRef, ...]
    next_page_token: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.messages, tuple) or any(
            not isinstance(item, MailMessageRef) for item in self.messages
        ):
            raise DomainError("A mail page requires immutable message references.")
        identities = tuple(item.provider_message_id for item in self.messages)
        if len(set(identities)) != len(identities):
            raise DomainError("A mail page cannot repeat a provider message.")
        if self.next_page_token is not None:
            require_provider_id(self.next_page_token)


@dataclass(frozen=True, slots=True)
class MailChange:
    provider_event_id: str
    message: MailMessageRef
    kind: MailChangeKind

    def __post_init__(self) -> None:
        require_provider_id(self.provider_event_id)
        if not isinstance(self.message, MailMessageRef) or not isinstance(
            self.kind, MailChangeKind
        ):
            raise DomainError("A mail change requires a validated message and kind.")


@dataclass(frozen=True, slots=True)
class MailDelta:
    changes: tuple[MailChange, ...]
    checkpoint_cursor: str = field(repr=False)
    next_page_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.changes, tuple) or any(
            not isinstance(item, MailChange) for item in self.changes
        ):
            raise DomainError("A mail delta requires immutable validated changes.")
        event_ids = tuple(item.provider_event_id for item in self.changes)
        if len(set(event_ids)) != len(event_ids):
            raise DomainError("A mail delta cannot repeat a provider event.")
        require_provider_id(self.checkpoint_cursor)
        if self.next_page_token is not None:
            require_provider_id(self.next_page_token)


@dataclass(frozen=True, slots=True)
class MailboxCheckpoint:
    account_id: UUID = field(repr=False)
    provider: str
    cursor: str = field(repr=False)
    revision: int
    updated_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.account_id)
        require_provider_name(self.provider)
        require_provider_id(self.cursor)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise DomainError("A mailbox checkpoint requires a positive revision.")
        require_timestamp(self.updated_at)


@dataclass(frozen=True, slots=True)
class MailSyncResult:
    sync_id: UUID
    account_id: UUID = field(repr=False)
    provider: str
    status: MailSyncStatus
    start_cursor: str | None = field(repr=False)
    final_cursor: str | None = field(repr=False)
    fetched_count: int
    inserted_count: int
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.sync_id)
        require_identifier(self.account_id)
        require_provider_name(self.provider)
        if not isinstance(self.status, MailSyncStatus):
            raise DomainError("A mail sync result requires an explicit provider and status.")
        for cursor in (self.start_cursor, self.final_cursor):
            if cursor is not None:
                require_provider_id(cursor)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (self.fetched_count, self.inserted_count)
        ):
            raise DomainError("Mail sync counts must be nonnegative integers.")
        if self.inserted_count > self.fetched_count:
            raise DomainError("A mail sync cannot insert more events than it fetched.")
        require_timestamp(self.started_at)
        require_timestamp(self.completed_at)
        if self.completed_at < self.started_at:
            raise DomainError("A mail sync cannot complete before it starts.")
        if self.status is MailSyncStatus.COMPLETED:
            if self.start_cursor is None or self.final_cursor is None:
                raise DomainError("A completed mail sync requires both cursors.")
        elif self.final_cursor is not None or self.fetched_count != 0 or self.inserted_count != 0:
            raise DomainError("A required full sync cannot claim reconciled changes.")


@dataclass(frozen=True, slots=True)
class DraftRequest:
    draft_id: UUID
    account_email: str = field(repr=False)
    recipients: tuple[str, ...] = field(repr=False)
    subject: str = field(repr=False)
    body: str = field(repr=False)
    body_sha256: str
    created_at: datetime
    provider_thread_id: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.draft_id)
        require_email(self.account_email)
        if not isinstance(self.recipients, tuple) or not self.recipients:
            raise DomainError("A mail draft requires immutable recipients.")
        for recipient in self.recipients:
            require_email(recipient)
        if len(set(self.recipients)) != len(self.recipients):
            raise DomainError("A mail draft cannot repeat a recipient.")
        for value in (self.subject, self.body):
            require_text(value)
        if len(self.subject) > 998 or len(self.body) > 200_000:
            raise DomainError("Mail draft content exceeds its bounded contract.")
        if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in self.body):
            raise DomainError("A mail draft body contains invalid plain text.")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.subject):
            raise DomainError("A mail draft subject contains invalid plain text.")
        require_sha256(self.body_sha256)
        if sha256(self.body.encode("utf-8")).hexdigest() != self.body_sha256:
            raise DomainError("A mail draft must bind its exact UTF-8 body.")
        require_timestamp(self.created_at)
        if self.provider_thread_id is not None:
            require_provider_id(self.provider_thread_id)


@dataclass(frozen=True, slots=True)
class ProviderDraft:
    draft_id: UUID
    provider_draft_id: str
    provider_message_id: str
    provider_thread_id: str

    def __post_init__(self) -> None:
        require_identifier(self.draft_id)
        for value in (
            self.provider_draft_id,
            self.provider_message_id,
            self.provider_thread_id,
        ):
            require_provider_id(value)


def draft_request_sha256(request: DraftRequest) -> str:
    """Bind policy to the exact account, recipients, subject, body and thread."""
    if not isinstance(request, DraftRequest):
        raise DomainError("A validated mail draft request is required.")
    value = "\x1f".join(
        (
            "acoa-mail-draft-content/1",
            str(request.draft_id),
            request.account_email,
            *request.recipients,
            request.subject,
            request.body,
            request.provider_thread_id or "",
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MailDraftRecord:
    """A prepared draft; this record is neither send authority nor sent evidence."""

    application_id: UUID
    account_id: UUID = field(repr=False)
    recipient_id: UUID = field(repr=False)
    kind: MailDraftKind
    request: DraftRequest = field(repr=False)
    policy_request: PolicyRequest = field(repr=False)
    source_message: MailMessageRef | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for identifier in (self.application_id, self.account_id, self.recipient_id):
            require_identifier(identifier)
        if not isinstance(self.kind, MailDraftKind) or not isinstance(self.request, DraftRequest):
            raise DomainError("A mail draft record requires validated draft values.")
        if not isinstance(self.policy_request, PolicyRequest):
            raise DomainError("A mail draft record requires an exact policy request.")
        if len(self.request.recipients) != 1:
            raise DomainError("A policy-bound mail draft requires exactly one recipient.")
        self._validate_policy_binding()
        self._validate_conversation_binding()

    @property
    def draft_id(self) -> UUID:
        return self.request.draft_id

    def _validate_policy_binding(self) -> None:
        expected_action = {
            MailDraftKind.INITIAL_APPLICATION: ActionKind.SUBMIT_INITIAL_APPLICATION,
            MailDraftKind.REPLY: ActionKind.DRAFT_REPLY,
            MailDraftKind.FOLLOWUP: ActionKind.DRAFT_FOLLOWUP,
        }[self.kind]
        policy = self.policy_request
        if (
            policy.request_id != self.request.draft_id
            or policy.action is not expected_action
            or policy.channel is not Channel.EMAIL
            or policy.account_id != self.account_id
            or policy.recipient_id != self.recipient_id
            or policy.content_sha256 != draft_request_sha256(self.request)
        ):
            raise DomainError("A mail draft must bind its exact policy action and content.")

    def _validate_conversation_binding(self) -> None:
        if self.kind is MailDraftKind.INITIAL_APPLICATION:
            if self.source_message is not None or self.request.provider_thread_id is not None:
                raise DomainError("An initial application draft cannot claim an existing thread.")
            return
        if (
            not isinstance(self.source_message, MailMessageRef)
            or self.request.provider_thread_id != self.source_message.provider_thread_id
        ):
            raise DomainError("A reply or follow-up draft requires its exact source thread.")


@dataclass(frozen=True, slots=True)
class MailDraftReceipt:
    """Proof of provider draft creation only; it never proves message sending."""

    provider: str
    draft: ProviderDraft
    recorded_at: datetime

    def __post_init__(self) -> None:
        require_provider_name(self.provider)
        if not isinstance(self.draft, ProviderDraft):
            raise DomainError("A mail draft receipt requires a validated provider draft.")
        require_timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class MailSentRecord:
    """A provider sent-record observation; acceptance does not prove delivery or reading."""

    source_ref: UUID
    attempt_id: UUID
    application_id: UUID
    draft_id: UUID
    provider_id: UUID
    provider: str
    message: MailMessageRef
    observed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (
            self.source_ref,
            self.attempt_id,
            self.application_id,
            self.draft_id,
            self.provider_id,
        ):
            require_identifier(identifier)
        require_provider_name(self.provider)
        if not isinstance(self.message, MailMessageRef):
            raise DomainError("A mail sent record requires validated provider identifiers.")
        require_timestamp(self.observed_at)


def mail_sent_record_sha256(record: MailSentRecord) -> str:
    if not isinstance(record, MailSentRecord):
        raise DomainError("A validated mail sent record is required.")
    value = "\x1f".join(
        (
            "acoa-mail-sent-record/1",
            str(record.source_ref),
            str(record.attempt_id),
            str(record.application_id),
            str(record.draft_id),
            str(record.provider_id),
            record.provider,
            record.message.provider_message_id,
            record.message.provider_thread_id,
            record.observed_at.astimezone(UTC).isoformat(),
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


def mail_change_sha256(account_id: UUID, provider: str, change: MailChange) -> str:
    require_identifier(account_id)
    require_provider_name(provider)
    if not isinstance(change, MailChange):
        raise DomainError("A validated mail change is required.")
    value = "\x1f".join(
        (
            "acoa-mail-change/1",
            str(account_id),
            provider,
            change.provider_event_id,
            change.message.provider_message_id,
            change.message.provider_thread_id,
            change.kind.value,
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


def mail_sync_result_sha256(result: MailSyncResult) -> str:
    if not isinstance(result, MailSyncResult):
        raise DomainError("A validated mail sync result is required.")
    value = "\x1f".join(
        (
            "acoa-mail-sync-result/1",
            str(result.sync_id),
            str(result.account_id),
            result.provider,
            result.status.value,
            result.start_cursor or "",
            result.final_cursor or "",
            str(result.fetched_count),
            str(result.inserted_count),
            result.started_at.astimezone(UTC).isoformat(),
            result.completed_at.astimezone(UTC).isoformat(),
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()
