"""Deterministic initial-mail adapter for offline acceptance and timeout exercises."""

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.application.executor import ProviderAcknowledgement
from acoa.application.policy import request_binding_sha256
from acoa.domain.actions import DispatchLimits, PreparedAction
from acoa.domain.authorization import ActionKind
from acoa.domain.mail import MailDraftKind, MailDraftRecord, MailMessageRef, MailSentRecord
from acoa.domain.values import DomainError, require_identifier


class FakeMailOutcome(StrEnum):
    ACCEPT = "accept"
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"
    TIMEOUT_BEFORE_ACCEPT = "timeout_before_accept"


class FakeInitialMailAdapter:
    """A counted fake provider; each configured attempt may be invoked only once."""

    def __init__(
        self,
        provider_id: UUID,
        drafts: Mapping[UUID, MailDraftRecord],
        outcomes: Mapping[UUID, FakeMailOutcome],
    ) -> None:
        require_identifier(provider_id)
        if set(drafts) != set(outcomes):
            raise DomainError("Fake mail attempts require one explicit outcome each.")
        if any(not isinstance(value, MailDraftRecord) for value in drafts.values()) or any(
            not isinstance(value, FakeMailOutcome) for value in outcomes.values()
        ):
            raise DomainError("Fake mail configuration requires validated drafts and outcomes.")
        self.provider_id = provider_id
        self.drafts = MappingProxyType(dict(drafts))
        self.outcomes = MappingProxyType(dict(outcomes))
        self.invocations: dict[UUID, int] = {}
        self.sent_records: dict[UUID, MailSentRecord] = {}

    def execute_once(
        self, prepared: PreparedAction, limits: DispatchLimits
    ) -> ProviderAcknowledgement | None:
        draft = self.drafts.get(prepared.attempt_id)
        if (
            draft is None
            or prepared.provider_id != self.provider_id
            or prepared.request.action is not ActionKind.SUBMIT_INITIAL_APPLICATION
            or draft.kind is not MailDraftKind.INITIAL_APPLICATION
            or draft.application_id != prepared.application_id
            or draft.policy_request != prepared.request
        ):
            raise DomainError("Fake initial mail requires the exact prepared draft.")
        self.invocations[prepared.attempt_id] = self.invocations.get(prepared.attempt_id, 0) + 1
        if self.invocations[prepared.attempt_id] != 1:
            raise DomainError("A fake initial mail attempt cannot be invoked twice.")
        outcome = self.outcomes[prepared.attempt_id]
        if outcome is FakeMailOutcome.TIMEOUT_BEFORE_ACCEPT:
            raise TimeoutError("Synthetic timeout before provider acceptance.")
        record = self._sent_record(prepared, draft, datetime.now(UTC))
        self.sent_records[prepared.attempt_id] = record
        if outcome is FakeMailOutcome.TIMEOUT_AFTER_ACCEPT:
            raise TimeoutError("Synthetic timeout after provider acceptance.")
        return ProviderAcknowledgement(
            prepared.attempt_id,
            request_binding_sha256(prepared.request),
            record.source_ref,
        )

    def find_sent_record(self, attempt_id: UUID) -> MailSentRecord | None:
        require_identifier(attempt_id)
        return self.sent_records.get(attempt_id)

    def _sent_record(
        self, prepared: PreparedAction, draft: MailDraftRecord, observed_at: datetime
    ) -> MailSentRecord:
        value = uuid5(NAMESPACE_URL, f"acoa:fake-sent:{prepared.attempt_id}")
        return MailSentRecord(
            value,
            prepared.attempt_id,
            prepared.application_id,
            draft.draft_id,
            self.provider_id,
            "fake_test_mailbox",
            MailMessageRef(f"sent-{value}", f"thread-{value}"),
            observed_at,
        )
