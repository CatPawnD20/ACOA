"""Evidence-bound reply classifications and notification summaries; EP-06.05."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from acoa.domain.mail import require_provider_id, require_provider_name
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
)


class MailReplyKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INFORMATION_REQUEST = "information_request"
    INTERVIEW_REQUEST = "interview_request"
    AUTOMATIC_REPLY = "automatic_reply"
    AMBIGUOUS = "ambiguous"
    OPT_OUT = "opt_out"


IMMEDIATE_REPLY_KINDS = frozenset(
    (
        MailReplyKind.POSITIVE,
        MailReplyKind.INFORMATION_REQUEST,
        MailReplyKind.INTERVIEW_REQUEST,
        MailReplyKind.AMBIGUOUS,
        MailReplyKind.OPT_OUT,
    )
)


@dataclass(frozen=True, slots=True)
class MailReplyClassification:
    classification_id: UUID
    application_id: UUID
    account_id: UUID = field(repr=False)
    provider: str
    provider_event_id: str = field(repr=False)
    provider_message_id: str = field(repr=False)
    provider_thread_id: str = field(repr=False)
    kind: MailReplyKind
    message_snapshot_sha256: str = field(repr=False)
    relation_evidence_id: UUID = field(repr=False)
    classified_at: datetime

    def __post_init__(self) -> None:
        for identifier in (
            self.classification_id,
            self.application_id,
            self.account_id,
            self.relation_evidence_id,
        ):
            require_identifier(identifier)
        require_provider_name(self.provider)
        for value in (
            self.provider_event_id,
            self.provider_message_id,
            self.provider_thread_id,
        ):
            require_provider_id(value)
        if not isinstance(self.kind, MailReplyKind):
            raise DomainError("A mail reply classification requires an explicit kind.")
        require_sha256(self.message_snapshot_sha256)
        require_timestamp(self.classified_at)


def mail_notification_dedupe_key(classification: MailReplyClassification) -> str:
    if not isinstance(classification, MailReplyClassification):
        raise DomainError("A validated reply classification is required.")
    value = "\x1f".join(
        (
            "acoa-important-mail-notification/1",
            str(classification.account_id),
            classification.provider,
            classification.provider_event_id,
        )
    )
    return sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MailDailyDigest:
    digest_id: UUID
    window_start: datetime
    window_end: datetime
    created_at: datetime
    incoming_count: int
    classified_count: int
    immediate_count: int
    reply_draft_count: int
    followup_draft_count: int

    def __post_init__(self) -> None:
        require_identifier(self.digest_id)
        for value in (self.window_start, self.window_end, self.created_at):
            require_timestamp(value)
        if self.window_end <= self.window_start or self.created_at < self.window_end:
            raise DomainError("A daily digest requires a closed, ordered reporting window.")
        for count in (
            self.incoming_count,
            self.classified_count,
            self.immediate_count,
            self.reply_draft_count,
            self.followup_draft_count,
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DomainError("Daily digest counts must be nonnegative integers.")
