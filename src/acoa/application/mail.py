"""Provider-neutral mail operations that cannot send a message."""

from typing import Protocol

from acoa.domain.mail import DraftRequest, MailPage, ProviderDraft


class MailProvider(Protocol):
    def list_messages(self, page_token: str | None, max_results: int) -> MailPage: ...

    def create_draft(self, request: DraftRequest) -> ProviderDraft: ...
