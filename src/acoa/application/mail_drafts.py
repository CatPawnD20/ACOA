"""Prepare durable mail drafts without granting or performing message sending."""

from typing import Protocol

from acoa.application.policy import GateDecision, GateResult, ReasonCode, evaluate_policy
from acoa.application.policy_inputs import CommunicationPurpose, PolicyContext
from acoa.domain.authorization import PermissionMode
from acoa.domain.mail import MailDraftKind, MailDraftRecord
from acoa.domain.values import DomainError


class MailDraftWriter(Protocol):
    def record_draft(self, draft: MailDraftRecord) -> None: ...


def prepare_initial_application_draft(draft: MailDraftRecord, writer: MailDraftWriter) -> None:
    """Persist local initial-application content for a later fresh send preflight."""
    if draft.kind is not MailDraftKind.INITIAL_APPLICATION:
        raise DomainError("Initial application preparation requires an initial draft.")
    writer.record_draft(draft)


def prepare_user_sent_draft(
    draft: MailDraftRecord, context: PolicyContext, writer: MailDraftWriter
) -> GateResult:
    """Allow reply/follow-up composition only; the application has no send transition."""
    if draft.kind not in (MailDraftKind.REPLY, MailDraftKind.FOLLOWUP):
        raise DomainError("User-sent preparation requires a reply or follow-up draft.")
    expected_purpose = {
        MailDraftKind.REPLY: CommunicationPurpose.EMPLOYER_REPLY,
        MailDraftKind.FOLLOWUP: CommunicationPurpose.FOLLOWUP,
    }[draft.kind]
    if context.purpose is not expected_purpose:
        raise DomainError("Mail draft kind does not match the trusted communication purpose.")
    result = evaluate_policy(draft.policy_request, context)
    if (
        result.decision is not GateDecision.ALLOW
        or result.mode is not PermissionMode.AUTO_ALLOWED
        or result.reason_codes != (ReasonCode.DRAFT_ONLY,)
    ):
        raise DomainError("Policy Gate did not authorize draft-only preparation.")
    writer.record_draft(draft)
    return result
