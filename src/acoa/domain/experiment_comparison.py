"""Fixed-cohort strategy comparison and reversible selection values; EP-09.02."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.model_calls import require_amount, require_currency
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


@dataclass(frozen=True, slots=True)
class ExperimentVariantMetrics:
    strategy_version: str
    dataset_version: str
    dataset_sha256: str = field(repr=False)
    cohort: str
    sample_count: int
    success_count: int
    unauthorized_action_count: int
    duplicate_external_action_count: int
    actual_cost: Decimal
    currency: str
    measured_at: datetime

    def __post_init__(self) -> None:
        for value in (self.strategy_version, self.dataset_version, self.cohort):
            require_text(value)
        require_sha256(self.dataset_sha256)
        require_version(self.sample_count)
        for count in (
            self.success_count,
            self.unauthorized_action_count,
            self.duplicate_external_action_count,
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DomainError("Experiment comparison counts must be nonnegative integers.")
        if self.success_count > self.sample_count:
            raise DomainError("Experiment successes cannot exceed the sample count.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        require_timestamp(self.measured_at)


@dataclass(frozen=True, slots=True)
class StrategyComparison:
    comparison_id: UUID
    experiment_id: UUID
    gate_version: str
    minimum_absolute_improvement: Decimal
    baseline: ExperimentVariantMetrics
    candidate: ExperimentVariantMetrics
    compared_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.comparison_id, self.experiment_id):
            require_identifier(identifier)
        require_text(self.gate_version)
        if (
            not isinstance(self.minimum_absolute_improvement, Decimal)
            or not self.minimum_absolute_improvement.is_finite()
            or not Decimal("0") < self.minimum_absolute_improvement <= Decimal("1")
        ):
            raise DomainError("Comparison improvement must be a positive Decimal at most one.")
        if not isinstance(self.baseline, ExperimentVariantMetrics) or not isinstance(
            self.candidate, ExperimentVariantMetrics
        ):
            raise DomainError("A comparison requires validated baseline and candidate metrics.")
        require_timestamp(self.compared_at)
        if self.compared_at < max(self.baseline.measured_at, self.candidate.measured_at):
            raise DomainError("A comparison cannot predate its metrics.")


class StrategySelectionKind(StrEnum):
    PROMOTE_CANDIDATE = "promote_candidate"
    KEEP_BASELINE = "keep_baseline"
    ROLLBACK_BASELINE = "rollback_baseline"


class StrategySelectionReason(StrEnum):
    CANDIDATE_IMPROVED = "candidate_improved"
    FIXED_SCOPE_MISMATCH = "fixed_scope_mismatch"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    UNAUTHORIZED_ACTION_REGRESSION = "unauthorized_action_regression"
    DUPLICATE_ACTION_REGRESSION = "duplicate_action_regression"
    IMPROVEMENT_BELOW_GATE = "improvement_below_gate"


@dataclass(frozen=True, slots=True)
class StrategySelection:
    selection_id: UUID
    comparison_id: UUID
    experiment_id: UUID
    kind: StrategySelectionKind
    reasons: tuple[StrategySelectionReason, ...]
    selected_strategy_version: str
    restore_strategy_version: str
    selected_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.selection_id, self.comparison_id, self.experiment_id):
            require_identifier(identifier)
        if not isinstance(self.kind, StrategySelectionKind):
            raise DomainError("A strategy selection requires an explicit kind.")
        if (
            not isinstance(self.reasons, tuple)
            or not self.reasons
            or len(set(self.reasons)) != len(self.reasons)
        ):
            raise DomainError("Strategy selection reasons must be unique and nonempty.")
        require_text(self.selected_strategy_version)
        require_text(self.restore_strategy_version)
        require_timestamp(self.selected_at)
