"""Deterministic in-memory mail provider for offline workflows."""

from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.domain.mail import DraftRequest, MailMessageRef, MailPage, ProviderDraft
from acoa.domain.values import DomainError


class FakeMailProvider:
    def __init__(self, messages: tuple[MailMessageRef, ...] = ()) -> None:
        self.messages = messages
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
