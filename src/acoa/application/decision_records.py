"""EP-01.04 structured preflight traces; E-07, P-11/P-17, ADR-006/007/014."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from acoa.application.policy import (
    POLICY_VERSION,
    GateDecision,
    GateResult,
    ReasonCode,
    evaluate_policy,
    request_binding_sha256,
)
from acoa.application.policy_inputs import PolicyContext, PolicyRequest
from acoa.domain.authorization import PermissionMode
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)


def serialize_snapshot_value(value: object) -> str:
    """Encode validated domain scalar types without reading files or credentials."""
    if isinstance(value, datetime):
        require_timestamp(value)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    raise DomainError("Policy snapshots contain an unsupported scalar type.")


def context_fingerprint(context: PolicyContext) -> str:
    """Hash the complete trusted snapshot; do not persist or log its private payload."""
    payload = {"schema": "acoa-policy-context/1", "context": asdict(context)}
    encoded = json.dumps(
        payload,
        default=serialize_snapshot_value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """Audit data, never an authenticated receipt or executor capability."""

    decision_id: UUID
    evaluated_at: datetime
    snapshot_at: datetime
    request_sha256: str = field(repr=False)
    context_sha256: str = field(repr=False)
    decision: GateDecision
    mode: PermissionMode
    reason_codes: tuple[ReasonCode, ...]
    policy_version: str

    def __post_init__(self) -> None:
        require_identifier(self.decision_id)
        require_timestamp(self.evaluated_at)
        require_timestamp(self.snapshot_at)
        require_sha256(self.request_sha256)
        require_sha256(self.context_sha256)
        require_text(self.policy_version)
        if not isinstance(self.decision, GateDecision) or not isinstance(self.mode, PermissionMode):
            raise DomainError("Decision records require explicit decision and permission values.")
        if (
            not isinstance(self.reason_codes, tuple)
            or not self.reason_codes
            or any(not isinstance(reason, ReasonCode) for reason in self.reason_codes)
            or len(set(self.reason_codes)) != len(self.reason_codes)
        ):
            raise DomainError("Decision records require unique structured reason codes.")


def evaluate_and_record(
    decision_id: UUID, request: PolicyRequest, context: PolicyContext
) -> DecisionRecord:
    """Evaluate once and bind a caller-supplied audit ID to the exact evaluated inputs."""
    result = evaluate_policy(request, context)
    return DecisionRecord(
        decision_id=decision_id,
        evaluated_at=context.now,
        snapshot_at=context.snapshot_at,
        request_sha256=request_binding_sha256(request),
        context_sha256=context_fingerprint(context),
        decision=result.decision,
        mode=result.mode,
        reason_codes=result.reason_codes,
        policy_version=result.policy_version,
    )


def record_matches_evaluation(
    record: DecisionRecord, request: PolicyRequest, context: PolicyContext
) -> bool:
    """Require fresh evaluation on any changed input; this does not reserve or execute."""
    if (
        record.policy_version != POLICY_VERSION
        or record.request_sha256 != request_binding_sha256(request)
        or record.context_sha256 != context_fingerprint(context)
        or record.evaluated_at != context.now
        or record.snapshot_at != context.snapshot_at
    ):
        return False
    return evaluate_policy(request, context) == GateResult(
        record.decision, record.mode, record.reason_codes, record.policy_version
    )


def decision_record_json(record: DecisionRecord) -> str:
    """Export structured codes and opaque hashes without profile, recipient or account data."""
    return json.dumps(
        asdict(record),
        default=serialize_snapshot_value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
