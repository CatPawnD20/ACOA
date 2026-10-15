"""Labeled matching evaluation values with exact quality and resource denominators."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.matching import MatchAssessment
from acoa.domain.model_calls import require_amount, require_currency
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class ExpectedMatchLabel(StrEnum):
    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"
    RESEARCH_REQUIRED = "research_required"


@dataclass(frozen=True, slots=True)
class LabeledOpportunity:
    example_id: UUID
    opportunity_id: UUID
    opportunity_version: int
    opportunity_sha256: str = field(repr=False)
    expected: ExpectedMatchLabel
    cohort: str
    label_evidence_id: UUID = field(repr=False)
    labeled_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.example_id)
        require_identifier(self.opportunity_id)
        require_version(self.opportunity_version)
        require_sha256(self.opportunity_sha256)
        if not isinstance(self.expected, ExpectedMatchLabel):
            raise DomainError("A labeled opportunity requires an explicit expected class.")
        require_text(self.cohort)
        if self.cohort == "all":
            raise DomainError("The aggregate cohort name is reserved.")
        require_identifier(self.label_evidence_id)
        require_timestamp(self.labeled_at)


@dataclass(frozen=True, slots=True)
class EvaluationUsage:
    stage: str
    model_calls: int
    input_tokens: int
    output_tokens: int
    actual_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        require_text(self.stage)
        for value in (self.model_calls, self.input_tokens, self.output_tokens):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DomainError("Evaluation usage counts must be nonnegative integers.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        if self.model_calls == 0 and (
            self.input_tokens != 0 or self.output_tokens != 0 or self.actual_cost != 0
        ):
            raise DomainError("T0 evaluation usage must not report model tokens or cost.")


@dataclass(frozen=True, slots=True)
class EvaluationStageMetrics:
    stage: str
    case_count: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    actual_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        require_text(self.stage)
        counts = (self.case_count, self.model_calls, self.input_tokens, self.output_tokens)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise DomainError("Stage metrics require nonnegative integer counts.")
        if self.case_count < 1:
            raise DomainError("Stage metrics require at least one evaluated case.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        if self.model_calls == 0 and (
            self.input_tokens != 0 or self.output_tokens != 0 or self.actual_cost != 0
        ):
            raise DomainError("A stage without model calls must not report model usage or cost.")


@dataclass(frozen=True, slots=True)
class MatchEvaluationCase:
    label: LabeledOpportunity
    assessment: MatchAssessment
    usage: EvaluationUsage

    def __post_init__(self) -> None:
        if not isinstance(self.label, LabeledOpportunity):
            raise DomainError("An evaluation case requires a validated label.")
        if not isinstance(self.assessment, MatchAssessment):
            raise DomainError("An evaluation case requires a validated assessment.")
        if not isinstance(self.usage, EvaluationUsage):
            raise DomainError("An evaluation case requires validated resource usage.")
        if (
            self.label.opportunity_id != self.assessment.opportunity_id
            or self.label.opportunity_version != self.assessment.opportunity_version
            or self.label.opportunity_sha256 != self.assessment.opportunity_sha256
        ):
            raise DomainError(
                "Evaluation label and assessment must target the same opportunity version."
            )


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    cohort: str
    sample_count: int
    qualified_count: int
    not_qualified_count: int
    research_expected_count: int
    predicted_fit_count: int
    predicted_research_count: int
    predicted_low_priority_count: int
    predicted_excluded_count: int
    recovered_qualified_count: int
    missed_qualified_count: int
    unresolved_qualified_count: int
    false_exclusion_count: int
    false_positive_count: int
    unsupported_decision_count: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    actual_cost: Decimal
    currency: str
    stages: tuple[EvaluationStageMetrics, ...]

    def __post_init__(self) -> None:
        require_text(self.cohort)
        counts = (
            self.sample_count,
            self.qualified_count,
            self.not_qualified_count,
            self.research_expected_count,
            self.predicted_fit_count,
            self.predicted_research_count,
            self.predicted_low_priority_count,
            self.predicted_excluded_count,
            self.recovered_qualified_count,
            self.missed_qualified_count,
            self.unresolved_qualified_count,
            self.false_exclusion_count,
            self.false_positive_count,
            self.unsupported_decision_count,
            self.model_calls,
            self.input_tokens,
            self.output_tokens,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise DomainError("Evaluation metrics require nonnegative integer counts.")
        if self.sample_count != (
            self.qualified_count + self.not_qualified_count + self.research_expected_count
        ):
            raise DomainError("Evaluation label counts must equal the sample count.")
        if self.sample_count != (
            self.predicted_fit_count
            + self.predicted_research_count
            + self.predicted_low_priority_count
            + self.predicted_excluded_count
        ):
            raise DomainError("Evaluation prediction counts must equal the sample count.")
        if (
            self.recovered_qualified_count
            + self.missed_qualified_count
            + (self.unresolved_qualified_count)
            != self.qualified_count
        ):
            raise DomainError("Qualified outcomes must partition labeled qualified cases.")
        if self.false_exclusion_count > self.missed_qualified_count:
            raise DomainError("False exclusions must be a subset of missed qualified cases.")
        if self.false_positive_count > self.not_qualified_count:
            raise DomainError("False positives cannot exceed labeled non-qualified cases.")
        if self.unsupported_decision_count > self.research_expected_count:
            raise DomainError("Unsupported decisions cannot exceed research-required cases.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        if self.model_calls == 0 and (
            self.input_tokens != 0 or self.output_tokens != 0 or self.actual_cost != 0
        ):
            raise DomainError("Metrics without model calls must not report model usage or cost.")
        if (
            not isinstance(self.stages, tuple)
            or not self.stages
            or any(not isinstance(item, EvaluationStageMetrics) for item in self.stages)
        ):
            raise DomainError("Evaluation metrics require immutable per-stage metrics.")
        if tuple(item.stage for item in self.stages) != tuple(
            sorted(item.stage for item in self.stages)
        ):
            raise DomainError("Evaluation stages must be unique and canonically ordered.")
        if len({item.stage for item in self.stages}) != len(self.stages):
            raise DomainError("Evaluation metrics must not repeat stages.")
        if sum(item.case_count for item in self.stages) != self.sample_count:
            raise DomainError("Per-stage case counts must cover the evaluation sample.")
        if (
            sum(item.model_calls for item in self.stages) != self.model_calls
            or sum(item.input_tokens for item in self.stages) != self.input_tokens
            or sum(item.output_tokens for item in self.stages) != self.output_tokens
            or sum((item.actual_cost for item in self.stages), start=Decimal(0)) != self.actual_cost
        ):
            raise DomainError("Per-stage resource totals must equal overall resource usage.")
        if any(item.currency != self.currency for item in self.stages):
            raise DomainError("Per-stage metrics must use the evaluation currency.")


@dataclass(frozen=True, slots=True)
class MatchEvaluationReport:
    run_id: UUID
    dataset_version: str
    dataset_sha256: str = field(repr=False)
    matching_policy_version: str
    label_period_start: datetime
    label_period_end: datetime
    evaluated_at: datetime
    overall: EvaluationMetrics
    cohorts: tuple[EvaluationMetrics, ...]

    def __post_init__(self) -> None:
        require_identifier(self.run_id)
        require_text(self.dataset_version)
        require_sha256(self.dataset_sha256)
        require_text(self.matching_policy_version)
        require_timestamp(self.label_period_start)
        require_timestamp(self.label_period_end)
        require_timestamp(self.evaluated_at)
        if self.label_period_end < self.label_period_start:
            raise DomainError("Evaluation label period must be ordered.")
        if self.evaluated_at < self.label_period_end:
            raise DomainError("Evaluation must not predate its latest label.")
        if not isinstance(self.overall, EvaluationMetrics):
            raise DomainError("An evaluation report requires overall metrics.")
        if self.overall.cohort != "all":
            raise DomainError("Overall evaluation metrics require the aggregate cohort name.")
        if not isinstance(self.cohorts, tuple) or any(
            not isinstance(item, EvaluationMetrics) for item in self.cohorts
        ):
            raise DomainError("Evaluation cohort metrics must be immutable.")
        if len({item.cohort for item in self.cohorts}) != len(self.cohorts):
            raise DomainError("An evaluation report must not repeat cohorts.")
        if any(item.cohort == "all" for item in self.cohorts):
            raise DomainError("Evaluation cohort slices must not use the aggregate name.")
        if tuple(item.cohort for item in self.cohorts) != tuple(
            sorted(item.cohort for item in self.cohorts)
        ):
            raise DomainError("Evaluation cohorts must use canonical ordering.")
        if sum(item.sample_count for item in self.cohorts) != self.overall.sample_count:
            raise DomainError("Evaluation cohorts must partition the overall sample.")
        if any(item.currency != self.overall.currency for item in self.cohorts):
            raise DomainError("Evaluation cohorts must use the report currency.")
        if _metric_rollup(self.cohorts) != _metric_rollup((self.overall,)):
            raise DomainError("Evaluation cohort totals must equal the overall metrics.")


@dataclass(frozen=True, slots=True)
class EvaluationGate:
    gate_version: str
    dataset_version: str
    dataset_sha256: str = field(repr=False)
    minimum_samples: int
    minimum_qualified: int
    minimum_not_qualified: int
    minimum_research_expected: int
    minimum_recall: Decimal
    maximum_false_exclusion_rate: Decimal
    maximum_false_positive_rate: Decimal
    maximum_unsupported_decision_rate: Decimal
    maximum_tokens_per_case: int
    maximum_cost_per_recovered_qualified: Decimal
    currency: str

    def __post_init__(self) -> None:
        require_text(self.gate_version)
        require_text(self.dataset_version)
        require_sha256(self.dataset_sha256)
        for count in (
            self.minimum_samples,
            self.minimum_qualified,
            self.minimum_not_qualified,
            self.minimum_research_expected,
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise DomainError("Evaluation gate counts must be positive integers.")
        if (
            isinstance(self.maximum_tokens_per_case, bool)
            or not isinstance(self.maximum_tokens_per_case, int)
            or self.maximum_tokens_per_case < 0
        ):
            raise DomainError("The token-per-case limit must be a nonnegative integer.")
        for rate in (
            self.minimum_recall,
            self.maximum_false_exclusion_rate,
            self.maximum_false_positive_rate,
            self.maximum_unsupported_decision_rate,
        ):
            if not isinstance(rate, Decimal) or not rate.is_finite() or not 0 <= rate <= 1:
                raise DomainError("Evaluation gate rates must be finite Decimals from zero to one.")
        require_amount(self.maximum_cost_per_recovered_qualified)
        require_currency(self.currency)


class EvaluationGateReason(StrEnum):
    PASSED = "passed"
    DATASET_MISMATCH = "dataset_mismatch"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    INSUFFICIENT_QUALIFIED = "insufficient_qualified"
    INSUFFICIENT_NOT_QUALIFIED = "insufficient_not_qualified"
    INSUFFICIENT_RESEARCH_EXPECTED = "insufficient_research_expected"
    RECALL_BELOW_LIMIT = "recall_below_limit"
    FALSE_EXCLUSION_ABOVE_LIMIT = "false_exclusion_above_limit"
    FALSE_POSITIVE_ABOVE_LIMIT = "false_positive_above_limit"
    UNSUPPORTED_DECISION_ABOVE_LIMIT = "unsupported_decision_above_limit"
    TOKENS_ABOVE_LIMIT = "tokens_above_limit"
    UNIT_COST_UNKNOWN = "unit_cost_unknown"
    UNIT_COST_ABOVE_LIMIT = "unit_cost_above_limit"
    CURRENCY_MISMATCH = "currency_mismatch"


@dataclass(frozen=True, slots=True)
class EvaluationGateResult:
    passed: bool
    reasons: tuple[EvaluationGateReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool) or not isinstance(self.reasons, tuple):
            raise DomainError("Evaluation gate result must be explicit and immutable.")
        if not self.reasons or len(set(self.reasons)) != len(self.reasons):
            raise DomainError("Evaluation gate reasons must be unique and nonempty.")
        if self.passed != (self.reasons == (EvaluationGateReason.PASSED,)):
            raise DomainError("Evaluation gate status must match its structured reasons.")


def _metric_rollup(metrics: tuple[EvaluationMetrics, ...]) -> tuple[int | Decimal, ...]:
    return tuple(
        sum((getattr(metric, field_name) for metric in metrics), start=Decimal(0))
        if field_name == "actual_cost"
        else sum(getattr(metric, field_name) for metric in metrics)
        for field_name in (
            "sample_count",
            "qualified_count",
            "not_qualified_count",
            "research_expected_count",
            "predicted_fit_count",
            "predicted_research_count",
            "predicted_low_priority_count",
            "predicted_excluded_count",
            "recovered_qualified_count",
            "missed_qualified_count",
            "unresolved_qualified_count",
            "false_exclusion_count",
            "false_positive_count",
            "unsupported_decision_count",
            "model_calls",
            "input_tokens",
            "output_tokens",
            "actual_cost",
        )
    )
