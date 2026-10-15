"""Evidence-bound matching values; hard exclusions are never numerical preferences."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.authorization import validate_scope
from acoa.domain.goals import GoalCondition, GoalDimension, ProfileGoalReference
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


def validate_evidence(status: EvidenceStatus, evidence_ids: tuple[UUID, ...]) -> None:
    if not isinstance(status, EvidenceStatus):
        raise DomainError("Evidence status must be explicit.")
    validate_scope(evidence_ids, UUID)
    if status is EvidenceStatus.CONFIRMED and not evidence_ids:
        raise DomainError("Confirmed matching data requires evidence.")
    if status is EvidenceStatus.CONFLICTED and len(evidence_ids) < 2:
        raise DomainError("Conflicted matching data requires at least two evidence records.")


@dataclass(frozen=True, slots=True)
class OpportunityAttribute:
    dimension: GoalDimension
    values: tuple[str, ...] = field(repr=False)
    status: EvidenceStatus
    evidence_ids: tuple[UUID, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, GoalDimension):
            raise DomainError("Opportunity attribute dimension must be explicit.")
        if not isinstance(self.values, tuple) or any(
            not isinstance(item, str) for item in self.values
        ):
            raise DomainError("Opportunity values must be immutable text values.")
        for value in self.values:
            require_text(value)
        if len(set(self.values)) != len(self.values):
            raise DomainError("Opportunity values must not repeat.")
        validate_evidence(self.status, self.evidence_ids)
        if self.status is EvidenceStatus.CONFIRMED and not self.values:
            raise DomainError("Confirmed opportunity attributes require an explicit value.")
        if self.status is not EvidenceStatus.CONFIRMED and self.values:
            raise DomainError("Unknown or conflicted attributes must not assert a selected value.")


@dataclass(frozen=True, slots=True)
class OpportunitySnapshot:
    opportunity_id: UUID = field(repr=False)
    version: int
    content_sha256: str = field(repr=False)
    updated_at: datetime
    valid_until: datetime
    attributes: tuple[OpportunityAttribute, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.opportunity_id)
        require_version(self.version)
        require_sha256(self.content_sha256)
        require_timestamp(self.updated_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.updated_at:
            raise DomainError("Opportunity validity must follow its update.")
        if not isinstance(self.attributes, tuple) or any(
            not isinstance(item, OpportunityAttribute) for item in self.attributes
        ):
            raise DomainError("Opportunity attributes must be an immutable validated tuple.")
        if len({item.dimension for item in self.attributes}) != len(self.attributes):
            raise DomainError("An opportunity has one current attribute per dimension.")


class HardConstraintStatus(StrEnum):
    PASS = "pass"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HardConstraintResult:
    condition: GoalCondition
    status: HardConstraintStatus
    evidence_ids: tuple[UUID, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.condition, GoalCondition) or not isinstance(
            self.status, HardConstraintStatus
        ):
            raise DomainError("Hard-constraint results require explicit validated values.")
        validate_scope(self.evidence_ids, UUID)


class MatchCriterion(StrEnum):
    TARGET_ALIGNMENT = "target_alignment"
    OPPORTUNITY_VALUE = "opportunity_value"
    FRESHNESS = "freshness"
    COST_EFFICIENCY = "cost_efficiency"
    CERTAINTY = "certainty"


def require_unit_interval(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
        raise DomainError("A matching score must be a finite Decimal between zero and one.")


@dataclass(frozen=True, slots=True)
class CriterionSignal:
    criterion: MatchCriterion
    status: EvidenceStatus
    score: Decimal | None
    evidence_ids: tuple[UUID, ...] = field(default=(), repr=False)
    profile_fact_ids: tuple[UUID, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, MatchCriterion):
            raise DomainError("A matching criterion must be explicit.")
        validate_evidence(self.status, self.evidence_ids)
        validate_scope(self.profile_fact_ids, UUID)
        if self.status is EvidenceStatus.CONFIRMED:
            if self.score is None:
                raise DomainError("A confirmed criterion requires an explicit score.")
            require_unit_interval(self.score)
        elif self.score is not None:
            raise DomainError("Unknown or conflicted criteria must not carry a score.")


@dataclass(frozen=True, slots=True)
class CriterionWeight:
    criterion: MatchCriterion
    weight: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, MatchCriterion):
            raise DomainError("A criterion weight requires an explicit criterion.")
        if not isinstance(self.weight, Decimal) or not self.weight.is_finite() or self.weight <= 0:
            raise DomainError("A criterion weight must be a finite positive Decimal.")


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    policy_version: str
    weights: tuple[CriterionWeight, ...]
    required_criteria: tuple[MatchCriterion, ...]
    fit_threshold: Decimal
    low_priority_threshold: Decimal
    minimum_required_score: Decimal
    validity_seconds: int

    def __post_init__(self) -> None:
        require_text(self.policy_version)
        if (
            not isinstance(self.weights, tuple)
            or not self.weights
            or any(not isinstance(item, CriterionWeight) for item in self.weights)
        ):
            raise DomainError("Matching policy requires immutable criterion weights.")
        weighted = {item.criterion for item in self.weights}
        if len(weighted) != len(self.weights):
            raise DomainError("A matching policy must not repeat criterion weights.")
        if weighted != set(MatchCriterion):
            raise DomainError("Matching policy must explicitly weight every approved criterion.")
        validate_scope(self.required_criteria, MatchCriterion)
        if not self.required_criteria or not set(self.required_criteria) <= weighted:
            raise DomainError("Required criteria must be a nonempty subset of weighted criteria.")
        for value in (
            self.fit_threshold,
            self.low_priority_threshold,
            self.minimum_required_score,
        ):
            require_unit_interval(value)
        if self.low_priority_threshold >= self.fit_threshold:
            raise DomainError("Low-priority threshold must be below the fit threshold.")
        if (
            isinstance(self.validity_seconds, bool)
            or not isinstance(self.validity_seconds, int)
            or self.validity_seconds < 1
        ):
            raise DomainError("Matching validity must be a positive integer.")


class MatchClassification(StrEnum):
    FIT = "fit"
    RESEARCH_REQUIRED = "research_required"
    LOW_PRIORITY = "low_priority"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class MatchAssessment:
    assessment_id: UUID
    reference: ProfileGoalReference
    opportunity_id: UUID
    opportunity_version: int
    opportunity_sha256: str = field(repr=False)
    evaluated_at: datetime
    valid_until: datetime
    policy_version: str
    classification: MatchClassification
    hard_results: tuple[HardConstraintResult, ...]
    criterion_signals: tuple[CriterionSignal, ...]
    aggregate_numerator: int | None = None
    aggregate_denominator: int | None = None

    def __post_init__(self) -> None:
        require_identifier(self.assessment_id)
        if not isinstance(self.reference, ProfileGoalReference):
            raise DomainError("A match assessment requires profile/goal version binding.")
        require_identifier(self.opportunity_id)
        require_version(self.opportunity_version)
        require_sha256(self.opportunity_sha256)
        require_timestamp(self.evaluated_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.evaluated_at:
            raise DomainError("Match assessment validity must follow evaluation.")
        require_text(self.policy_version)
        if not isinstance(self.classification, MatchClassification):
            raise DomainError("A match classification must be explicit.")
        if not isinstance(self.hard_results, tuple) or any(
            not isinstance(item, HardConstraintResult) for item in self.hard_results
        ):
            raise DomainError("Hard results must be an immutable validated tuple.")
        if len({item.condition for item in self.hard_results}) != len(self.hard_results):
            raise DomainError("A hard condition must have exactly one assessment result.")
        if not isinstance(self.criterion_signals, tuple) or any(
            not isinstance(item, CriterionSignal) for item in self.criterion_signals
        ):
            raise DomainError("Criterion signals must be an immutable validated tuple.")
        if self.criterion_signals and {item.criterion for item in self.criterion_signals} != set(
            MatchCriterion
        ):
            raise DomainError("A scored assessment requires every approved criterion once.")
        score_present = (
            self.aggregate_numerator is not None or self.aggregate_denominator is not None
        )
        if score_present and (
            isinstance(self.aggregate_numerator, bool)
            or not isinstance(self.aggregate_numerator, int)
            or self.aggregate_numerator < 0
            or isinstance(self.aggregate_denominator, bool)
            or not isinstance(self.aggregate_denominator, int)
            or self.aggregate_denominator < 1
        ):
            raise DomainError("Aggregate matching score must be an exact nonnegative fraction.")
        if (
            self.aggregate_numerator is not None
            and self.aggregate_denominator is not None
            and self.aggregate_numerator > self.aggregate_denominator
        ):
            raise DomainError("Aggregate matching score must not exceed one.")
        hard_excluded = any(
            item.status is HardConstraintStatus.EXCLUDED for item in self.hard_results
        )
        hard_unknown = any(
            item.status is HardConstraintStatus.UNKNOWN for item in self.hard_results
        )
        if hard_excluded:
            if (
                self.classification is not MatchClassification.EXCLUDED
                or self.criterion_signals
                or score_present
            ):
                raise DomainError("Hard exclusion must stop before preference scoring.")
        elif hard_unknown:
            if (
                self.classification is not MatchClassification.RESEARCH_REQUIRED
                or self.criterion_signals
                or score_present
            ):
                raise DomainError("Unknown hard constraints require research before scoring.")
        elif self.classification is MatchClassification.EXCLUDED or not self.criterion_signals:
            raise DomainError("Passed hard constraints require a separate scored assessment.")
        elif self.classification is not MatchClassification.RESEARCH_REQUIRED and not score_present:
            raise DomainError("Fit and low-priority results require an exact aggregate score.")
