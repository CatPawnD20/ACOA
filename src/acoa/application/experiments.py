"""Fail-closed experiment checkpoint assessment and rollback decisions; EP-09.01."""

from dataclasses import dataclass
from enum import StrEnum

from acoa.domain.experiments import ExperimentCheckpoint, ExperimentState, StrategyExperiment
from acoa.domain.values import DomainError


class ExperimentDecisionKind(StrEnum):
    CONTINUE = "continue"
    READY_FOR_COMPARISON = "ready_for_comparison"
    ROLLBACK = "rollback"


class ExperimentDecisionReason(StrEnum):
    WITHIN_LIMITS = "within_limits"
    MINIMUM_SAMPLE_REACHED = "minimum_sample_reached"
    BINDING_CHANGED = "binding_changed"
    EXPIRED = "expired"
    CASE_LIMIT_EXCEEDED = "case_limit_exceeded"
    EXTERNAL_IMPACT_EXCEEDED = "external_impact_exceeded"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    METRIC_BELOW_ROLLBACK_FLOOR = "metric_below_rollback_floor"


@dataclass(frozen=True, slots=True)
class ExperimentDecision:
    kind: ExperimentDecisionKind
    reasons: tuple[ExperimentDecisionReason, ...]
    restore_strategy_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExperimentDecisionKind):
            raise DomainError("An experiment decision requires an explicit kind.")
        if (
            not isinstance(self.reasons, tuple)
            or not self.reasons
            or len(set(self.reasons)) != len(self.reasons)
        ):
            raise DomainError("Experiment decision reasons must be unique and nonempty.")
        if (self.kind is ExperimentDecisionKind.ROLLBACK) != (
            self.restore_strategy_version is not None
        ):
            raise DomainError("Only rollback decisions restore a prior strategy version.")


def assess_experiment_checkpoint(
    experiment: StrategyExperiment,
    checkpoint: ExperimentCheckpoint,
) -> ExperimentDecision:
    """Stop on any invariant/limit breach; comparison and promotion remain separate."""
    if not isinstance(experiment, StrategyExperiment) or not isinstance(
        checkpoint, ExperimentCheckpoint
    ):
        raise DomainError("Experiment assessment requires validated plan and checkpoint values.")
    if checkpoint.experiment_id != experiment.experiment_id:
        raise DomainError("An experiment checkpoint targets another plan.")
    if checkpoint.observed_at < experiment.created_at:
        raise DomainError("An experiment checkpoint cannot predate its plan.")
    if checkpoint.state is not ExperimentState.RUNNING:
        raise DomainError("Only a running checkpoint can be assessed.")
    reasons: list[ExperimentDecisionReason] = []
    if (
        checkpoint.goals_sha256 != experiment.goals_sha256
        or checkpoint.authorization_sha256 != experiment.authorization_sha256
        or checkpoint.hard_constraints_sha256 != experiment.hard_constraints_sha256
    ):
        reasons.append(ExperimentDecisionReason.BINDING_CHANGED)
    if checkpoint.observed_at >= experiment.expires_at:
        reasons.append(ExperimentDecisionReason.EXPIRED)
    if checkpoint.completed_cases > experiment.maximum_cases:
        reasons.append(ExperimentDecisionReason.CASE_LIMIT_EXCEEDED)
    if checkpoint.external_impact > experiment.maximum_external_impact:
        reasons.append(ExperimentDecisionReason.EXTERNAL_IMPACT_EXCEEDED)
    if (
        checkpoint.currency != experiment.currency
        or checkpoint.actual_cost > experiment.maximum_cost
    ):
        reasons.append(ExperimentDecisionReason.COST_LIMIT_EXCEEDED)
    if (
        checkpoint.metric_denominator >= experiment.minimum_samples
        and checkpoint.metric_numerator < experiment.rollback_floor * checkpoint.metric_denominator
    ):
        reasons.append(ExperimentDecisionReason.METRIC_BELOW_ROLLBACK_FLOOR)
    if reasons:
        return ExperimentDecision(
            ExperimentDecisionKind.ROLLBACK,
            tuple(reasons),
            experiment.baseline_strategy_version,
        )
    if checkpoint.completed_cases >= experiment.minimum_samples:
        return ExperimentDecision(
            ExperimentDecisionKind.READY_FOR_COMPARISON,
            (ExperimentDecisionReason.MINIMUM_SAMPLE_REACHED,),
        )
    return ExperimentDecision(
        ExperimentDecisionKind.CONTINUE,
        (ExperimentDecisionReason.WITHIN_LIMITS,),
    )
