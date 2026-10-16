"""Optional model-guided field interpretation without browser action authority; EP-08.05."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from acoa.domain.browser import (
    BrowserField,
    BrowserFieldKind,
    BrowserFieldPurpose,
    BrowserPageObservation,
)
from acoa.domain.model_calls import StructuredModelOutput
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)

BROWSER_GUIDANCE_SCHEMA = "acoa-browser-guidance/1"


class BrowserInterpretationMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    AI_GUIDED = "ai_guided"
    USER_HANDOFF = "user_handoff"


@dataclass(frozen=True, slots=True)
class BrowserGuidancePolicy:
    policy_version: str
    enabled: bool
    expires_at: datetime
    minimum_confidence: Decimal

    def __post_init__(self) -> None:
        require_text(self.policy_version)
        require_timestamp(self.expires_at)
        if not isinstance(self.enabled, bool):
            raise DomainError("Browser guidance enablement must be explicit.")
        if (
            not isinstance(self.minimum_confidence, Decimal)
            or not self.minimum_confidence.is_finite()
            or not Decimal("0") <= self.minimum_confidence <= Decimal("1")
        ):
            raise DomainError("Browser guidance confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class BrowserFieldSuggestion:
    """Advisory classification only; it is not an observed field or fill instruction."""

    model_call_id: UUID = field(repr=False)
    observation_id: UUID = field(repr=False)
    page_sha256: str = field(repr=False)
    field_id: UUID = field(repr=False)
    purpose: BrowserFieldPurpose
    confidence: Decimal

    def __post_init__(self) -> None:
        for identifier in (self.model_call_id, self.observation_id, self.field_id):
            require_identifier(identifier)
        require_sha256(self.page_sha256)
        if self.purpose in (
            BrowserFieldPurpose.UNKNOWN,
            BrowserFieldPurpose.OTHER,
            BrowserFieldPurpose.RESUME_UPLOAD,
        ):
            raise DomainError("AI guidance cannot authorize unknown or document fields.")
        if (
            not isinstance(self.confidence, Decimal)
            or not self.confidence.is_finite()
            or not Decimal("0") <= self.confidence <= Decimal("1")
        ):
            raise DomainError("Field suggestion confidence must be between zero and one.")


def select_browser_interpretation(
    observation: BrowserPageObservation,
    deterministic_adequate: bool,
    policy: BrowserGuidancePolicy,
    now: datetime,
) -> BrowserInterpretationMethod:
    """Prefer deterministic inspection; challenges and unavailable guidance require handoff."""
    require_timestamp(now)
    if not isinstance(observation, BrowserPageObservation) or not isinstance(
        deterministic_adequate, bool
    ):
        raise DomainError("Browser interpretation requires validated inputs.")
    if not isinstance(policy, BrowserGuidancePolicy):
        raise DomainError("Browser interpretation requires an explicit guidance policy.")
    if observation.obstacles:
        return BrowserInterpretationMethod.USER_HANDOFF
    unresolved = _unresolved_text_fields(observation)
    if deterministic_adequate or not unresolved:
        return BrowserInterpretationMethod.DETERMINISTIC
    if policy.enabled and now < policy.expires_at:
        return BrowserInterpretationMethod.AI_GUIDED
    return BrowserInterpretationMethod.USER_HANDOFF


def parse_browser_guidance(
    output: StructuredModelOutput,
    observation: BrowserPageObservation,
    policy: BrowserGuidancePolicy,
    now: datetime,
) -> tuple[BrowserFieldSuggestion, ...]:
    """Validate advisory gateway output; never mutate the observation or invoke a browser."""
    require_timestamp(now)
    if not isinstance(output, StructuredModelOutput) or not isinstance(
        observation, BrowserPageObservation
    ):
        raise DomainError("Browser guidance requires exact model and observation records.")
    if (
        not isinstance(policy, BrowserGuidancePolicy)
        or not policy.enabled
        or now >= policy.expires_at
        or output.output_schema_version != BROWSER_GUIDANCE_SCHEMA
    ):
        raise DomainError("Browser guidance is not currently enabled for this output schema.")
    payload = _object_payload(output.output_json)
    if set(payload) != {"schema", "observation_id", "page_sha256", "suggestions"}:
        raise DomainError("Browser guidance output contains unsupported fields.")
    if (
        payload["schema"] != BROWSER_GUIDANCE_SCHEMA
        or payload["observation_id"] != str(observation.observation_id)
        or payload["page_sha256"] != observation.page_sha256
        or not isinstance(payload["suggestions"], list)
    ):
        raise DomainError("Browser guidance output targets another page observation.")
    unresolved = {field.field_id for field in _unresolved_text_fields(observation)}
    suggestions = tuple(
        _parse_suggestion(output.call_id, observation, value, unresolved)
        for value in payload["suggestions"]
    )
    if not suggestions or len({item.field_id for item in suggestions}) != len(suggestions):
        raise DomainError("Browser guidance must contain unique nonempty field suggestions.")
    if any(item.confidence < policy.minimum_confidence for item in suggestions):
        raise DomainError("Browser guidance did not meet the configured confidence floor.")
    return suggestions


def _unresolved_text_fields(
    observation: BrowserPageObservation,
) -> tuple[BrowserField, ...]:
    return tuple(
        field
        for field in observation.fields
        if field.required
        and field.kind is not BrowserFieldKind.FILE
        and field.purpose in (BrowserFieldPurpose.UNKNOWN, BrowserFieldPurpose.OTHER)
    )


def _object_payload(output_json: str) -> dict[str, object]:
    try:
        value = json.loads(output_json)
    except (TypeError, ValueError):
        raise DomainError("Browser guidance output must be a JSON object.") from None
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise DomainError("Browser guidance output must be a JSON object.")
    return value


def _parse_suggestion(
    call_id: UUID,
    observation: BrowserPageObservation,
    value: object,
    unresolved: set[UUID],
) -> BrowserFieldSuggestion:
    if not isinstance(value, dict) or set(value) != {"field_id", "purpose", "confidence"}:
        raise DomainError("A browser field suggestion has an invalid shape.")
    if not all(isinstance(value[key], str) for key in value):
        raise DomainError("A browser field suggestion must contain text values.")
    try:
        field_id = UUID(value["field_id"])
        purpose = BrowserFieldPurpose(value["purpose"])
        confidence = Decimal(value["confidence"])
    except (ValueError, TypeError, InvalidOperation):
        raise DomainError("A browser field suggestion contains an invalid value.") from None
    if field_id not in unresolved:
        raise DomainError("AI guidance can target only an unresolved observed text field.")
    return BrowserFieldSuggestion(
        call_id,
        observation.observation_id,
        observation.page_sha256,
        field_id,
        purpose,
        confidence,
    )
