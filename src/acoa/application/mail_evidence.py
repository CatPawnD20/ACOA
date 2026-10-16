"""Convert trusted mail sent-record observations into submission evidence."""

from datetime import datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.actions import PreparedAction, prepared_binding_sha256
from acoa.domain.mail import MailSentRecord, mail_sent_record_sha256
from acoa.domain.submission_evidence import EvidenceSource, SubmissionClaim, SubmissionEvidence
from acoa.domain.values import DomainError, require_identifier, require_timestamp


def build_mail_submission_evidence(
    evidence_id: UUID,
    prepared: PreparedAction,
    search_ref: UUID,
    observed_at: datetime,
    sent_record: MailSentRecord | None,
) -> SubmissionEvidence:
    """Report acceptance only from an exact sent record; an empty lookup stays unknown."""
    require_identifier(evidence_id)
    require_identifier(search_ref)
    require_timestamp(observed_at)
    if not isinstance(prepared, PreparedAction):
        raise DomainError("Mail evidence requires an exact prepared action.")
    if sent_record is None:
        snapshot = sha256(
            f"acoa-mail-inconclusive/1\x1f{prepared.attempt_id}\x1f{search_ref}\x1f"
            f"{observed_at.isoformat()}".encode()
        ).hexdigest()
        return SubmissionEvidence(
            evidence_id,
            prepared.attempt_id,
            prepared.provider_id,
            prepared_binding_sha256(prepared),
            search_ref,
            snapshot,
            observed_at,
            SubmissionClaim.UNKNOWN,
            EvidenceSource.INCONCLUSIVE_LOOKUP,
            True,
        )
    if (
        sent_record.attempt_id != prepared.attempt_id
        or sent_record.application_id != prepared.application_id
        or sent_record.provider_id != prepared.provider_id
        or sent_record.observed_at != observed_at
    ):
        raise DomainError("A mail sent record does not match the prepared action.")
    return SubmissionEvidence(
        evidence_id,
        prepared.attempt_id,
        prepared.provider_id,
        prepared_binding_sha256(prepared),
        sent_record.source_ref,
        mail_sent_record_sha256(sent_record),
        observed_at,
        SubmissionClaim.PROVIDER_ACCEPTED,
        EvidenceSource.SENT_RECORD,
        True,
    )
