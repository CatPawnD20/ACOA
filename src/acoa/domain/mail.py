"""Provider-neutral mailbox and draft values; EP-06.01."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)

EMAIL_PATTERN = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,63}")


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


def _provider_id(value: object) -> str:
    require_text(value)
    if not isinstance(value, str) or len(value) > 512 or any(ord(char) < 33 for char in value):
        raise DomainError("A provider identifier is invalid.")
    return value


@dataclass(frozen=True, slots=True)
class MailMessageRef:
    provider_message_id: str
    provider_thread_id: str

    def __post_init__(self) -> None:
        _provider_id(self.provider_message_id)
        _provider_id(self.provider_thread_id)


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
            _provider_id(self.next_page_token)


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
            _provider_id(self.provider_thread_id)


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
            _provider_id(value)
