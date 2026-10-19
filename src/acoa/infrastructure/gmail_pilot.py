"""Single-attempt Gmail live-pilot adapter and read-only reconciliation."""

from base64 import urlsafe_b64encode
from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.application.executor import ProviderAcknowledgement
from acoa.application.policy import request_binding_sha256
from acoa.domain.actions import DispatchLimits, PreparedAction
from acoa.domain.authorization import ActionKind, Channel
from acoa.domain.mail import (
    MailDraftKind,
    MailDraftRecord,
    MailMessageRef,
    MailSentRecord,
    draft_request_sha256,
    require_email,
    require_provider_id,
)
from acoa.domain.pilot import ControlledMailTarget
from acoa.domain.values import DomainError, require_identifier, require_timestamp
from acoa.infrastructure.gmail import GmailOAuthScope


class BoundedGmailTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        body: Mapping[str, object] | None,
        *,
        timeout_seconds: int,
    ) -> Mapping[str, object]: ...


def _provider_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise DomainError(f"Gmail returned an invalid {name}.")
    return require_provider_id(value)


def _authenticated_account_email(
    transport: BoundedGmailTransport, *, timeout_seconds: int
) -> str:
    profile = transport.request(
        "GET",
        "/gmail/v1/users/me/profile",
        {},
        None,
        timeout_seconds=timeout_seconds,
    )
    value = profile.get("emailAddress")
    if not isinstance(value, str):
        raise DomainError("Gmail returned an invalid authenticated account identity.")
    return require_email(value.casefold())


def pilot_message_id(attempt_id: UUID) -> str:
    require_identifier(attempt_id)
    return f"<{attempt_id}@pilot.acoa.invalid>"


def _raw_message(record: MailDraftRecord, attempt_id: UUID) -> str:
    request = record.request
    message = EmailMessage()
    message["From"] = request.account_email
    message["To"] = request.recipients[0]
    message["Subject"] = request.subject
    message["Message-ID"] = pilot_message_id(attempt_id)
    message["X-ACOA-Attempt-ID"] = str(attempt_id)
    message.set_content(request.body)
    return urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _validate_pilot_binding(
    prepared: PreparedAction,
    provider_id: UUID,
    draft: MailDraftRecord,
    target: ControlledMailTarget,
    now: datetime,
    *,
    require_current_target: bool = True,
) -> None:
    request = prepared.request
    if (
        prepared.provider_id != provider_id
        or request.action is not ActionKind.SUBMIT_INITIAL_APPLICATION
        or request.channel is not Channel.EMAIL
        or draft.kind is not MailDraftKind.INITIAL_APPLICATION
        or draft.policy_request != request
        or draft.application_id != prepared.application_id
        or draft.draft_id != request.request_id
        or request.content_sha256 != draft_request_sha256(draft.request)
        or request.account_id != target.account_id
        or request.recipient_id != target.recipient_id
        or draft.account_id != target.account_id
        or draft.recipient_id != target.recipient_id
        or draft.request.account_email != target.sender_email
        or draft.request.recipients != (target.recipient_email,)
        or target.sender_email.casefold() != target.recipient_email.casefold()
    ):
        raise DomainError("The live pilot does not match its exact initial-mail authorization.")
    if require_current_target and not target.is_current(now):
        raise DomainError("The controlled pilot target authorization is not current.")


class GmailInitialApplicationPilot:
    """Permit exactly one initial mail material through the central Executor boundary."""

    def __init__(
        self,
        scope: GmailOAuthScope,
        transport: BoundedGmailTransport,
        provider_id: UUID,
        draft: MailDraftRecord,
        target: ControlledMailTarget,
    ) -> None:
        if not isinstance(scope, GmailOAuthScope):
            raise DomainError("The Gmail pilot requires validated OAuth scopes.")
        require_identifier(provider_id)
        if not isinstance(draft, MailDraftRecord) or not isinstance(target, ControlledMailTarget):
            raise DomainError("The Gmail pilot requires validated material and target records.")
        self.transport = transport
        self.provider_id = provider_id
        self.draft = draft
        self.target = target
        self._invoked = False

    def execute_once(
        self, prepared: PreparedAction, limits: DispatchLimits
    ) -> ProviderAcknowledgement:
        now = datetime.now(UTC)
        _validate_pilot_binding(prepared, self.provider_id, self.draft, self.target, now)
        if self._invoked:
            raise DomainError("A Gmail pilot adapter instance cannot dispatch twice.")
        authenticated_email = _authenticated_account_email(
            self.transport,
            timeout_seconds=min(limits.timeout_seconds, 30),
        )
        if authenticated_email.casefold() != self.draft.request.account_email.casefold():
            raise DomainError("The authenticated Gmail account differs from the approved sender.")
        self._invoked = True
        response = self.transport.request(
            "POST",
            "/gmail/v1/users/me/messages/send",
            {},
            {"raw": _raw_message(self.draft, prepared.attempt_id)},
            timeout_seconds=limits.timeout_seconds,
        )
        message_id = _provider_text(response.get("id"), "message ID")
        _provider_text(response.get("threadId"), "thread ID")
        return ProviderAcknowledgement(
            prepared.attempt_id,
            request_binding_sha256(prepared.request),
            uuid5(NAMESPACE_URL, f"gmail-message:{message_id}"),
        )

    def find_sent_record(
        self,
        prepared: PreparedAction,
        observed_at: datetime,
        *,
        timeout_seconds: int,
    ) -> MailSentRecord | None:
        """Search Sent by the attempt Message-ID; this path cannot submit a message."""
        require_timestamp(observed_at)
        _validate_pilot_binding(
            prepared,
            self.provider_id,
            self.draft,
            self.target,
            observed_at,
            require_current_target=False,
        )
        response = self.transport.request(
            "GET",
            "/gmail/v1/users/me/messages",
            {
                "q": f"in:sent rfc822msgid:{pilot_message_id(prepared.attempt_id)}",
                "maxResults": "1",
            },
            None,
            timeout_seconds=timeout_seconds,
        )
        raw_messages = response.get("messages", [])
        if not isinstance(raw_messages, list):
            raise DomainError("Gmail returned an invalid sent-message search result.")
        if not raw_messages:
            return None
        first = raw_messages[0]
        if not isinstance(first, Mapping):
            raise DomainError("Gmail returned an invalid sent-message reference.")
        message_id = _provider_text(first.get("id"), "message ID")
        thread_id = _provider_text(first.get("threadId"), "thread ID")
        return MailSentRecord(
            source_ref=uuid5(NAMESPACE_URL, f"gmail-sent-record:{message_id}"),
            attempt_id=prepared.attempt_id,
            application_id=prepared.application_id,
            draft_id=self.draft.draft_id,
            provider_id=self.provider_id,
            provider="gmail",
            message=MailMessageRef(message_id, thread_id),
            observed_at=observed_at,
        )
