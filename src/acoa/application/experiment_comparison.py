"""Deterministic same-scope comparison with critical regression veto; EP-09.02."""

from fractions import Fraction
from uuid import UUID

from acoa.domain.experiment_comparison import (
    StrategyComparison,
    StrategySelection,
    StrategySelectionKind,
    StrategySelectionReason,
)
from acoa.domain.experiments import StrategyExperiment
from acoa.domain.values import DomainError, require_identifier


def select_strategy(
    selection_id: UUID,
    experiment: StrategyExperiment,
    comparison: StrategyComparison,
) -> StrategySelection:
    """Critical regressions veto promotion; all decisions retain a rollback target."""
    require_identifier(selection_id)
    if not isinstance(experiment, StrategyExperiment) or not isinstance(
        comparison, StrategyComparison
    ):
        raise DomainError("Strategy selection requires validated experiment comparison inputs.")
    if comparison.experiment_id != experiment.experiment_id:
        raise DomainError("A strategy comparison targets another experiment.")
    baseline, candidate = comparison.baseline, comparison.candidate
    if (
        baseline.strategy_version != experiment.baseline_strategy_version
        or candidate.strategy_version != experiment.candidate_strategy_version
    ):
        raise DomainError("Comparison variants do not match the experiment plan.")
    reasons: list[StrategySelectionReason] = []
    fixed_scope = (
        baseline.dataset_version == candidate.dataset_version
        and baseline.dataset_sha256 == candidate.dataset_sha256
        and baseline.cohort == candidate.cohort == experiment.cohort
        and baseline.sample_count == candidate.sample_count
        and baseline.currency == candidate.currency == experiment.currency
    )
    if not fixed_scope:
        reasons.append(StrategySelectionReason.FIXED_SCOPE_MISMATCH)
    if min(baseline.sample_count, candidate.sample_count) < experiment.minimum_samples:
        reasons.append(StrategySelectionReason.INSUFFICIENT_SAMPLES)
    if candidate.unauthorized_action_count > baseline.unauthorized_action_count:
        reasons.append(StrategySelectionReason.UNAUTHORIZED_ACTION_REGRESSION)
    if candidate.duplicate_external_action_count > baseline.duplicate_external_action_count:
        reasons.append(StrategySelectionReason.DUPLICATE_ACTION_REGRESSION)
    if reasons:
        return _selection(
            selection_id,
            comparison,
            StrategySelectionKind.ROLLBACK_BASELINE,
            tuple(reasons),
            experiment.baseline_strategy_version,
            experiment.baseline_strategy_version,
        )
    improvement = Fraction(candidate.success_count, candidate.sample_count) - Fraction(
        baseline.success_count, baseline.sample_count
    )
    if improvement < Fraction(comparison.minimum_absolute_improvement):
        return _selection(
            selection_id,
            comparison,
            StrategySelectionKind.KEEP_BASELINE,
            (StrategySelectionReason.IMPROVEMENT_BELOW_GATE,),
            experiment.baseline_strategy_version,
            experiment.baseline_strategy_version,
        )
    return _selection(
        selection_id,
        comparison,
        StrategySelectionKind.PROMOTE_CANDIDATE,
        (StrategySelectionReason.CANDIDATE_IMPROVED,),
        experiment.candidate_strategy_version,
        experiment.baseline_strategy_version,
    )


def _selection(
    selection_id: UUID,
    comparison: StrategyComparison,
    kind: StrategySelectionKind,
    reasons: tuple[StrategySelectionReason, ...],
    selected: str,
    restore: str,
) -> StrategySelection:
    return StrategySelection(
        selection_id,
        comparison.comparison_id,
        comparison.experiment_id,
        kind,
        reasons,
        selected,
        restore,
        comparison.compared_at,
    )
