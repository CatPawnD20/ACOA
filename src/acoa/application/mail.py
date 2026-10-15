"""Provider-neutral mail operations that cannot send a message."""

from typing import Protocol

from acoa.domain.mail import DraftRequest, MailDelta, MailPage, ProviderDraft


class MailChangeProvider(Protocol):
    def list_changes(self, cursor: str, page_token: str | None, max_results: int) -> MailDelta: ...


class MailProvider(MailChangeProvider, Protocol):
    def list_messages(self, page_token: str | None, max_results: int) -> MailPage: ...

    def create_draft(self, request: DraftRequest) -> ProviderDraft: ...
