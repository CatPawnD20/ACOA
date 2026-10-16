"""Bounded strategy experiment plans and checkpoints; EP-09.01."""

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


class ExperimentMode(StrEnum):
    REPLAY = "replay"
    LIMITED_REAL = "limited_real"


class ExperimentState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    READY_FOR_COMPARISON = "ready_for_comparison"
    STOPPED = "stopped"
    ROLLED_BACK = "rolled_back"
    PROMOTED = "promoted"


REAL_EXPERIMENT_ROLLOUT_ENABLED = False


@dataclass(frozen=True, slots=True)
class StrategyExperiment:
    experiment_id: UUID
    task_id: UUID
    hypothesis: str
    cohort: str
    success_metric: str
    baseline_strategy_version: str
    candidate_strategy_version: str
    mode: ExperimentMode
    minimum_samples: int
    maximum_cases: int
    maximum_external_impact: int
    maximum_cost: Decimal
    currency: str
    rollback_floor: Decimal
    goals_sha256: str = field(repr=False)
    authorization_sha256: str = field(repr=False)
    hard_constraints_sha256: str = field(repr=False)
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.experiment_id, self.task_id):
            require_identifier(identifier)
        for value in (
            self.hypothesis,
            self.cohort,
            self.success_metric,
            self.baseline_strategy_version,
            self.candidate_strategy_version,
        ):
            require_text(value)
        if self.baseline_strategy_version == self.candidate_strategy_version:
            raise DomainError("An experiment candidate must differ from its baseline.")
        if not isinstance(self.mode, ExperimentMode):
            raise DomainError("An experiment requires an explicit execution mode.")
        if self.mode is ExperimentMode.LIMITED_REAL and not REAL_EXPERIMENT_ROLLOUT_ENABLED:
            raise DomainError("Real experiment rollout is not configured.")
        for count in (self.minimum_samples, self.maximum_cases):
            require_version(count)
        if (
            isinstance(self.maximum_external_impact, bool)
            or not isinstance(self.maximum_external_impact, int)
            or self.maximum_external_impact < 0
            or self.maximum_external_impact > self.maximum_cases
        ):
            raise DomainError("External impact must be a bounded subset of experiment cases.")
        if self.minimum_samples > self.maximum_cases:
            raise DomainError("Minimum samples cannot exceed the experiment case limit.")
        if self.mode is ExperimentMode.REPLAY and self.maximum_external_impact != 0:
            raise DomainError("Replay experiments cannot permit external effects.")
        require_amount(self.maximum_cost)
        require_currency(self.currency)
        if (
            not isinstance(self.rollback_floor, Decimal)
            or not self.rollback_floor.is_finite()
            or not Decimal("0") <= self.rollback_floor <= Decimal("1")
        ):
            raise DomainError("The rollback floor must be between zero and one.")
        for digest in (
            self.goals_sha256,
            self.authorization_sha256,
            self.hard_constraints_sha256,
        ):
            require_sha256(digest)
        require_timestamp(self.created_at)
        require_timestamp(self.expires_at)
        if self.expires_at <= self.created_at:
            raise DomainError("Experiment expiry must follow creation.")


@dataclass(frozen=True, slots=True)
class ExperimentCheckpoint:
    checkpoint_id: UUID
    experiment_id: UUID
    sequence: int
    state: ExperimentState
    completed_cases: int
    external_impact: int
    metric_numerator: int
    metric_denominator: int
    actual_cost: Decimal
    currency: str
    goals_sha256: str = field(repr=False)
    authorization_sha256: str = field(repr=False)
    hard_constraints_sha256: str = field(repr=False)
    observed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.checkpoint_id, self.experiment_id):
            require_identifier(identifier)
        require_version(self.sequence)
        if not isinstance(self.state, ExperimentState):
            raise DomainError("An experiment checkpoint requires an explicit state.")
        for count in (
            self.completed_cases,
            self.external_impact,
            self.metric_numerator,
            self.metric_denominator,
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DomainError("Experiment checkpoint counts must be nonnegative integers.")
        if self.metric_numerator > self.metric_denominator:
            raise DomainError("Experiment metric numerator cannot exceed its denominator.")
        if (
            self.metric_denominator > self.completed_cases
            or self.external_impact > self.completed_cases
        ):
            raise DomainError("Experiment measurements cannot exceed completed cases.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        for digest in (
            self.goals_sha256,
            self.authorization_sha256,
            self.hard_constraints_sha256,
        ):
            require_sha256(digest)
        require_timestamp(self.observed_at)
