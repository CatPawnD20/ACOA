"""Hard constraints first, then exact evidence-bound multi-criteria classification."""

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from uuid import UUID

from acoa.application.decision_records import serialize_snapshot_value
from acoa.domain.goals import (
    ConditionOperator,
    GoalCondition,
    ProfileGoalReference,
    UserGoals,
    reference_is_current,
)
from acoa.domain.matching import (
    CriterionSignal,
    EvidenceStatus,
    HardConstraintResult,
    HardConstraintStatus,
    MatchAssessment,
    MatchClassification,
    MatchCriterion,
    MatchingPolicy,
    OpportunityAttribute,
    OpportunitySnapshot,
)
from acoa.domain.profile import ProfileVariant, VerificationStatus, variant_is_usable
from acoa.domain.values import DomainError, require_identifier, require_timestamp


def evaluate_hard_condition(
    condition: GoalCondition, attribute: OpportunityAttribute | None
) -> HardConstraintResult:
    if attribute is None or attribute.status is not EvidenceStatus.CONFIRMED:
        evidence = attribute.evidence_ids if attribute else ()
        return HardConstraintResult(condition, HardConstraintStatus.UNKNOWN, evidence)
    overlap = bool(set(condition.values) & set(attribute.values))
    excluded = (condition.operator is ConditionOperator.REQUIRE and not overlap) or (
        condition.operator is ConditionOperator.EXCLUDE and overlap
    )
    status = HardConstraintStatus.EXCLUDED if excluded else HardConstraintStatus.PASS
    return HardConstraintResult(condition, status, attribute.evidence_ids)


def evaluate_hard_constraints(
    goals: UserGoals, opportunity: OpportunitySnapshot
) -> tuple[HardConstraintResult, ...]:
    attributes = {item.dimension: item for item in opportunity.attributes}
    return tuple(
        evaluate_hard_condition(condition, attributes.get(condition.dimension))
        for condition in goals.hard_constraints
    )


def hard_classification(
    results: tuple[HardConstraintResult, ...],
) -> MatchClassification | None:
    if any(item.status is HardConstraintStatus.EXCLUDED for item in results):
        return MatchClassification.EXCLUDED
    if any(item.status is HardConstraintStatus.UNKNOWN for item in results):
        return MatchClassification.RESEARCH_REQUIRED
    return None


def validate_assessment_inputs(
    assessment_id: UUID,
    variant: ProfileVariant,
    goals: UserGoals,
    opportunity: OpportunitySnapshot,
    now: datetime,
) -> None:
    require_identifier(assessment_id)
    require_timestamp(now)
    if not isinstance(variant, ProfileVariant) or not isinstance(goals, UserGoals):
        raise DomainError("Matching requires validated profile and goal inputs.")
    if not isinstance(opportunity, OpportunitySnapshot):
        raise DomainError("Matching requires a validated opportunity snapshot.")
    if not variant_is_usable(variant, now) or goals.updated_at > now:
        raise DomainError("Matching requires current approved profile and goal versions.")
    if opportunity.updated_at > now or now >= opportunity.valid_until:
        raise DomainError("Matching requires a current opportunity snapshot.")


def validate_criterion_signals(
    signals: tuple[CriterionSignal, ...], policy: MatchingPolicy, variant: ProfileVariant
) -> dict[MatchCriterion, CriterionSignal]:
    if not isinstance(signals, tuple) or any(
        not isinstance(item, CriterionSignal) for item in signals
    ):
        raise DomainError("Matching signals must be an immutable validated tuple.")
    by_criterion = {item.criterion: item for item in signals}
    if len(by_criterion) != len(signals) or set(by_criterion) != {
        item.criterion for item in policy.weights
    }:
        raise DomainError("Matching requires exactly one signal per configured criterion.")
    verified_fact_ids = {
        fact.fact_id for fact in variant.facts if fact.status is VerificationStatus.VERIFIED
    }
    if any(not set(item.profile_fact_ids) <= verified_fact_ids for item in signals):
        raise DomainError(
            "Matching signals may reference only verified facts in the bound profile."
        )
    return by_criterion


def exact_weighted_score(
    signals: dict[MatchCriterion, CriterionSignal], policy: MatchingPolicy
) -> Fraction:
    numerator = Fraction(0)
    denominator = Fraction(0)
    for weighted in policy.weights:
        signal = signals[weighted.criterion]
        if signal.status is EvidenceStatus.CONFIRMED:
            assert signal.score is not None
            weight = Fraction(weighted.weight)
            numerator += Fraction(signal.score) * weight
            denominator += weight
    if denominator == 0:
        raise DomainError("A match score requires at least one confirmed weighted criterion.")
    return numerator / denominator


def score_classification(
    signals: dict[MatchCriterion, CriterionSignal], policy: MatchingPolicy, score: Fraction
) -> MatchClassification:
    required = tuple(signals[item] for item in policy.required_criteria)
    minimum = Fraction(policy.minimum_required_score)
    if any(item.score is None or Fraction(item.score) < minimum for item in required):
        return MatchClassification.LOW_PRIORITY
    if score >= Fraction(policy.fit_threshold):
        return MatchClassification.FIT
    if score <= Fraction(policy.low_priority_threshold):
        return MatchClassification.LOW_PRIORITY
    return MatchClassification.RESEARCH_REQUIRED


def assessment_deadline(
    variant: ProfileVariant,
    opportunity: OpportunitySnapshot,
    policy: MatchingPolicy,
    now: datetime,
) -> datetime:
    deadlines = [now + timedelta(seconds=policy.validity_seconds), opportunity.valid_until]
    if variant.valid_until is not None:
        deadlines.append(variant.valid_until)
    return min(deadlines)


def assess_match(
    assessment_id: UUID,
    variant: ProfileVariant,
    goals: UserGoals,
    opportunity: OpportunitySnapshot,
    signals: tuple[CriterionSignal, ...],
    policy: MatchingPolicy,
    now: datetime,
) -> MatchAssessment:
    """Return before scoring on exclusion/unknown hard rules; preferences cannot override them."""
    validate_assessment_inputs(assessment_id, variant, goals, opportunity, now)
    if not isinstance(policy, MatchingPolicy):
        raise DomainError("Matching requires an explicit validated policy.")
    reference = ProfileGoalReference(
        variant.variant_id, variant.version, goals.goals_id, goals.version
    )
    hard_results = evaluate_hard_constraints(goals, opportunity)
    classification = hard_classification(hard_results)
    deadline = assessment_deadline(variant, opportunity, policy, now)
    if classification is not None:
        return MatchAssessment(
            assessment_id,
            reference,
            opportunity.opportunity_id,
            opportunity.version,
            opportunity.content_sha256,
            now,
            deadline,
            policy.policy_version,
            classification,
            hard_results,
            (),
        )
    validated = validate_criterion_signals(signals, policy, variant)
    required = tuple(validated[item] for item in policy.required_criteria)
    if any(item.status is EvidenceStatus.CONFLICTED for item in validated.values()) or any(
        item.status is not EvidenceStatus.CONFIRMED for item in required
    ):
        return MatchAssessment(
            assessment_id,
            reference,
            opportunity.opportunity_id,
            opportunity.version,
            opportunity.content_sha256,
            now,
            deadline,
            policy.policy_version,
            MatchClassification.RESEARCH_REQUIRED,
            hard_results,
            signals,
        )
    score = exact_weighted_score(validated, policy)
    classification = score_classification(validated, policy, score)
    return MatchAssessment(
        assessment_id,
        reference,
        opportunity.opportunity_id,
        opportunity.version,
        opportunity.content_sha256,
        now,
        deadline,
        policy.policy_version,
        classification,
        hard_results,
        signals,
        score.numerator,
        score.denominator,
    )


def assessment_binding_sha256(assessment: MatchAssessment) -> str:
    payload = {"schema": "acoa-match-assessment/1", "assessment": asdict(assessment)}
    encoded = json.dumps(
        payload,
        default=serialize_snapshot_value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def assessment_is_current(
    assessment: MatchAssessment,
    variant: ProfileVariant,
    goals: UserGoals,
    opportunity: OpportunitySnapshot,
    policy: MatchingPolicy,
    now: datetime,
) -> bool:
    require_timestamp(now)
    return (
        now < assessment.valid_until
        and assessment.policy_version == policy.policy_version
        and assessment.opportunity_id == opportunity.opportunity_id
        and assessment.opportunity_version == opportunity.version
        and assessment.opportunity_sha256 == opportunity.content_sha256
        and opportunity.updated_at <= now < opportunity.valid_until
        and reference_is_current(assessment.reference, variant, goals, now)
    )
