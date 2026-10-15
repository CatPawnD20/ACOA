"""Gmail API mapping with injected authenticated transport and exact OAuth scopes."""

from base64 import urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol, cast

from acoa.domain.mail import (
    DraftRequest,
    MailChange,
    MailChangeKind,
    MailCursorExpired,
    MailDelta,
    MailMessageRef,
    MailPage,
    ProviderDraft,
    require_provider_id,
)
from acoa.domain.values import DomainError

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_REQUIRED_SCOPES = frozenset((GMAIL_READONLY_SCOPE, GMAIL_COMPOSE_SCOPE))


class GmailTransportError(RuntimeError):
    """Redacted HTTP failure raised by an authenticated Gmail transport."""

    def __init__(self, status_code: int) -> None:
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            raise DomainError("A Gmail transport status must be an integer.")
        self.status_code = status_code
        super().__init__(f"Gmail transport failed with HTTP status {status_code}.")


class GmailTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        body: Mapping[str, object] | None,
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class GmailOAuthScope:
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scopes, tuple) or set(self.scopes) != GMAIL_REQUIRED_SCOPES:
            raise DomainError("Gmail requires exactly readonly and compose OAuth scopes.")
        if len(self.scopes) != len(GMAIL_REQUIRED_SCOPES):
            raise DomainError("Gmail OAuth scopes cannot repeat.")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DomainError(f"Gmail returned an invalid {name}.")
    return value


def _history_changes(raw_history: object) -> tuple[MailChange, ...]:
    if not isinstance(raw_history, list):
        raise DomainError("Gmail returned an invalid history page.")
    changes: list[MailChange] = []
    for raw_record in raw_history:
        if not isinstance(raw_record, Mapping):
            raise DomainError("Gmail returned an invalid history record.")
        history_id = _text(raw_record.get("id"), "history ID")
        additions = raw_record.get("messagesAdded", [])
        if not isinstance(additions, list):
            raise DomainError("Gmail returned invalid added-message history.")
        for addition in additions:
            if not isinstance(addition, Mapping):
                raise DomainError("Gmail returned an invalid added-message record.")
            message = addition.get("message")
            if not isinstance(message, Mapping):
                raise DomainError("Gmail returned invalid added-message metadata.")
            message_ref = MailMessageRef(
                _text(message.get("id"), "message ID"),
                _text(message.get("threadId"), "thread ID"),
            )
            changes.append(
                MailChange(
                    f"{history_id}:message_added:{message_ref.provider_message_id}",
                    message_ref,
                    MailChangeKind.MESSAGE_ADDED,
                )
            )
    return tuple(changes)


class GmailMailProvider:
    def __init__(self, scope: GmailOAuthScope, transport: GmailTransport) -> None:
        if not isinstance(scope, GmailOAuthScope):
            raise DomainError("Gmail requires validated OAuth scope declarations.")
        self.transport = transport

    def list_messages(self, page_token: str | None, max_results: int) -> MailPage:
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 500
        ):
            raise DomainError("Mail page size must be between one and 500.")
        query = {"maxResults": str(max_results), "includeSpamTrash": "false"}
        if page_token is not None:
            query["pageToken"] = page_token
        response = self.transport.request("GET", "/gmail/v1/users/me/messages", query, None)
        raw_messages = response.get("messages", [])
        if not isinstance(raw_messages, list):
            raise DomainError("Gmail returned an invalid message page.")
        messages = tuple(
            MailMessageRef(
                _text(item.get("id"), "message ID"), _text(item.get("threadId"), "thread ID")
            )
            for item in raw_messages
            if isinstance(item, Mapping)
        )
        if len(messages) != len(raw_messages):
            raise DomainError("Gmail returned an invalid message reference.")
        token = response.get("nextPageToken")
        return MailPage(messages, cast(str | None, token))

    def list_changes(self, cursor: str, page_token: str | None, max_results: int) -> MailDelta:
        require_provider_id(cursor)
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 500
        ):
            raise DomainError("Mail page size must be between one and 500.")
        query = {
            "startHistoryId": cursor,
            "maxResults": str(max_results),
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
        }
        if page_token is not None:
            require_provider_id(page_token)
            query["pageToken"] = page_token
        try:
            response = self.transport.request("GET", "/gmail/v1/users/me/history", query, None)
        except GmailTransportError as error:
            if error.status_code == 404:
                raise MailCursorExpired("The Gmail history cursor requires a full sync.") from None
            raise
        return MailDelta(
            _history_changes(response.get("history", [])),
            _text(response.get("historyId"), "mailbox history ID"),
            cast(str | None, response.get("nextPageToken")),
        )

    def create_draft(self, request: DraftRequest) -> ProviderDraft:
        if not isinstance(request, DraftRequest):
            raise DomainError("Gmail requires a validated draft request.")
        message = EmailMessage()
        message["From"] = request.account_email
        message["To"] = ", ".join(request.recipients)
        message["Subject"] = request.subject
        message.set_content(request.body)
        payload: dict[str, object] = {
            "raw": urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
        }
        if request.provider_thread_id is not None:
            payload["threadId"] = request.provider_thread_id
        response = self.transport.request(
            "POST", "/gmail/v1/users/me/drafts", {}, {"message": payload}
        )
        provider_message = response.get("message")
        if not isinstance(provider_message, Mapping):
            raise DomainError("Gmail returned an invalid draft message.")
        return ProviderDraft(
            request.draft_id,
            _text(response.get("id"), "draft ID"),
            _text(provider_message.get("id"), "message ID"),
            _text(provider_message.get("threadId"), "thread ID"),
        )
