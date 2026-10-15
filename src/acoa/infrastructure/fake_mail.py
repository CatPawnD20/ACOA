"""Deterministic in-memory mail provider for offline workflows."""

from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.domain.mail import (
    DraftRequest,
    MailChange,
    MailCursorExpired,
    MailDelta,
    MailMessageRef,
    MailPage,
    ProviderDraft,
    require_provider_id,
)
from acoa.domain.values import DomainError


class FakeMailProvider:
    def __init__(
        self,
        messages: tuple[MailMessageRef, ...] = (),
        changes: tuple[MailChange, ...] = (),
        start_cursor: str = "fake-cursor-0",
        final_cursor: str = "fake-cursor-1",
    ) -> None:
        MailPage(messages, None)
        MailDelta(changes, final_cursor)
        require_provider_id(start_cursor)
        self.messages = messages
        self.changes = changes
        self.start_cursor = start_cursor
        self.final_cursor = final_cursor
        self.drafts: dict[UUID, tuple[DraftRequest, ProviderDraft]] = {}

    def list_messages(self, page_token: str | None, max_results: int) -> MailPage:
        if page_token is not None:
            raise DomainError("The fake mail provider has no additional page.")
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 500
        ):
            raise DomainError("Mail page size must be between one and 500.")
        return MailPage(self.messages[:max_results], None)

    def list_changes(self, cursor: str, page_token: str | None, max_results: int) -> MailDelta:
        require_provider_id(cursor)
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 500
        ):
            raise DomainError("Mail page size must be between one and 500.")
        if cursor == self.final_cursor:
            if page_token is not None:
                raise DomainError("A current fake cursor cannot continue an old page.")
            return MailDelta((), self.final_cursor)
        if cursor != self.start_cursor:
            raise MailCursorExpired("The fake mailbox cursor is unavailable.")
        offset = self._page_offset(page_token)
        page = self.changes[offset : offset + max_results]
        next_offset = offset + len(page)
        next_token = f"fake-page-{next_offset}" if next_offset < len(self.changes) else None
        return MailDelta(page, self.final_cursor, next_token)

    @staticmethod
    def _page_offset(page_token: str | None) -> int:
        if page_token is None:
            return 0
        prefix = "fake-page-"
        if not page_token.startswith(prefix) or not page_token.removeprefix(prefix).isdigit():
            raise DomainError("The fake mail page token is invalid.")
        return int(page_token.removeprefix(prefix))

    def create_draft(self, request: DraftRequest) -> ProviderDraft:
        if not isinstance(request, DraftRequest):
            raise DomainError("The fake mail provider requires a validated draft request.")
        prior = self.drafts.get(request.draft_id)
        if prior is not None:
            if prior[0] != request:
                raise DomainError("A draft identity must remain immutable.")
            return prior[1]
        value = str(uuid5(NAMESPACE_URL, f"acoa:fake-mail:{request.draft_id}"))
        result = ProviderDraft(
            request.draft_id, f"draft-{value}", f"message-{value}", f"thread-{value}"
        )
        self.drafts[request.draft_id] = (request, result)
        return result
