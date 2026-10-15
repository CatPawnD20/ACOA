"""Deterministic labeled matching metrics and explicit release-gate comparisons."""

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from uuid import UUID

from acoa.application.decision_records import serialize_snapshot_value
from acoa.domain.evaluation import (
    EvaluationGate,
    EvaluationGateReason,
    EvaluationGateResult,
    EvaluationMetrics,
    EvaluationStageMetrics,
    ExpectedMatchLabel,
    MatchEvaluationCase,
    MatchEvaluationReport,
)
from acoa.domain.matching import MatchClassification
from acoa.domain.values import DomainError, require_identifier, require_text, require_timestamp


def dataset_sha256(cases: tuple[MatchEvaluationCase, ...]) -> str:
    """Fingerprint the ordered label set without including candidate predictions."""
    _require_case_set(cases)
    labels = [
        asdict(case.label) for case in sorted(cases, key=lambda item: item.label.example_id.int)
    ]
    encoded = json.dumps(
        {"schema": "acoa-match-evaluation-labels/1", "labels": labels},
        default=serialize_snapshot_value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def metrics_for(cohort: str, cases: tuple[MatchEvaluationCase, ...]) -> EvaluationMetrics:
    """Compute quality and resource counts with explicit denominators."""
    require_text(cohort)
    _require_case_set(cases)
    if cohort != "all" and any(case.label.cohort != cohort for case in cases):
        raise DomainError("A cohort metric slice must contain only its declared cohort.")
    currencies = {case.usage.currency for case in cases}
    if len(currencies) != 1:
        raise DomainError("Evaluation costs require one explicit currency; no FX is inferred.")
    qualified = tuple(case for case in cases if case.label.expected is ExpectedMatchLabel.QUALIFIED)
    not_qualified = tuple(
        case for case in cases if case.label.expected is ExpectedMatchLabel.NOT_QUALIFIED
    )
    research = tuple(
        case for case in cases if case.label.expected is ExpectedMatchLabel.RESEARCH_REQUIRED
    )
    missed_qualified = tuple(
        case
        for case in qualified
        if _classification(case) in (MatchClassification.EXCLUDED, MatchClassification.LOW_PRIORITY)
    )
    decisive = (
        MatchClassification.FIT,
        MatchClassification.LOW_PRIORITY,
        MatchClassification.EXCLUDED,
    )
    stages = tuple(
        _metrics_for_stage(stage, cases) for stage in sorted({case.usage.stage for case in cases})
    )
    return EvaluationMetrics(
        cohort=cohort,
        sample_count=len(cases),
        qualified_count=len(qualified),
        not_qualified_count=len(not_qualified),
        research_expected_count=len(research),
        predicted_fit_count=sum(_classification(case) is MatchClassification.FIT for case in cases),
        predicted_research_count=sum(
            _classification(case) is MatchClassification.RESEARCH_REQUIRED for case in cases
        ),
        predicted_low_priority_count=sum(
            _classification(case) is MatchClassification.LOW_PRIORITY for case in cases
        ),
        predicted_excluded_count=sum(
            _classification(case) is MatchClassification.EXCLUDED for case in cases
        ),
        recovered_qualified_count=sum(
            _classification(case) is MatchClassification.FIT for case in qualified
        ),
        missed_qualified_count=len(missed_qualified),
        unresolved_qualified_count=sum(
            _classification(case) is MatchClassification.RESEARCH_REQUIRED for case in qualified
        ),
        false_exclusion_count=sum(
            _classification(case) is MatchClassification.EXCLUDED for case in qualified
        ),
        false_positive_count=sum(
            _classification(case) is MatchClassification.FIT for case in not_qualified
        ),
        unsupported_decision_count=sum(_classification(case) in decisive for case in research),
        model_calls=sum(case.usage.model_calls for case in cases),
        input_tokens=sum(case.usage.input_tokens for case in cases),
        output_tokens=sum(case.usage.output_tokens for case in cases),
        actual_cost=sum((case.usage.actual_cost for case in cases), start=Decimal(0)),
        currency=next(iter(currencies)),
        stages=stages,
    )


def _classification(case: MatchEvaluationCase) -> MatchClassification:
    return case.assessment.classification


def _require_case_set(cases: tuple[MatchEvaluationCase, ...]) -> None:
    if (
        not isinstance(cases, tuple)
        or not cases
        or any(not isinstance(case, MatchEvaluationCase) for case in cases)
    ):
        raise DomainError("Evaluation requires a nonempty immutable labeled case set.")
    if len({case.label.example_id for case in cases}) != len(cases):
        raise DomainError("Evaluation examples must have unique identities.")
    if len({case.assessment.assessment_id for case in cases}) != len(cases):
        raise DomainError("Evaluation cases must have unique assessment identities.")


def _metrics_for_stage(
    stage: str, cases: tuple[MatchEvaluationCase, ...]
) -> EvaluationStageMetrics:
    stage_cases = tuple(case for case in cases if case.usage.stage == stage)
    return EvaluationStageMetrics(
        stage=stage,
        case_count=len(stage_cases),
        model_calls=sum(case.usage.model_calls for case in stage_cases),
        input_tokens=sum(case.usage.input_tokens for case in stage_cases),
        output_tokens=sum(case.usage.output_tokens for case in stage_cases),
        actual_cost=sum((case.usage.actual_cost for case in stage_cases), start=Decimal(0)),
        currency=stage_cases[0].usage.currency,
    )


def evaluate_labeled_matches(
    run_id: UUID,
    dataset_version: str,
    matching_policy_version: str,
    cases: tuple[MatchEvaluationCase, ...],
    evaluated_at: datetime,
) -> MatchEvaluationReport:
    """Evaluate one matching policy against one immutable labeled dataset."""
    require_identifier(run_id)
    require_text(dataset_version)
    require_text(matching_policy_version)
    require_timestamp(evaluated_at)
    _require_case_set(cases)
    if any(case.assessment.policy_version != matching_policy_version for case in cases):
        raise DomainError("Evaluation cases must use the declared matching policy version.")
    overall = metrics_for("all", cases)
    cohort_names = sorted({case.label.cohort for case in cases})
    cohorts = tuple(
        metrics_for(name, tuple(case for case in cases if case.label.cohort == name))
        for name in cohort_names
    )
    return MatchEvaluationReport(
        run_id=run_id,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256(cases),
        matching_policy_version=matching_policy_version,
        label_period_start=min(case.label.labeled_at for case in cases),
        label_period_end=max(case.label.labeled_at for case in cases),
        evaluated_at=evaluated_at,
        overall=overall,
        cohorts=cohorts,
    )


def rate_exceeds(numerator: int, denominator: int, limit: Decimal) -> bool:
    if denominator == 0:
        return False
    return Fraction(numerator, denominator) > Fraction(limit)


def rate_below(numerator: int, denominator: int, limit: Decimal) -> bool:
    if denominator == 0:
        return True
    return Fraction(numerator, denominator) < Fraction(limit)


def evaluate_release_gate(
    report: MatchEvaluationReport, gate: EvaluationGate
) -> EvaluationGateResult:
    """Apply explicit exact quality and resource limits to a bound report."""
    if not isinstance(report, MatchEvaluationReport) or not isinstance(gate, EvaluationGate):
        raise DomainError("Release evaluation requires a validated report and gate.")
    metrics = report.overall
    reasons: list[EvaluationGateReason] = []
    if (
        report.dataset_version != gate.dataset_version
        or report.dataset_sha256 != gate.dataset_sha256
    ):
        reasons.append(EvaluationGateReason.DATASET_MISMATCH)
    if metrics.sample_count < gate.minimum_samples:
        reasons.append(EvaluationGateReason.INSUFFICIENT_SAMPLES)
    if metrics.qualified_count < gate.minimum_qualified:
        reasons.append(EvaluationGateReason.INSUFFICIENT_QUALIFIED)
    if metrics.not_qualified_count < gate.minimum_not_qualified:
        reasons.append(EvaluationGateReason.INSUFFICIENT_NOT_QUALIFIED)
    if metrics.research_expected_count < gate.minimum_research_expected:
        reasons.append(EvaluationGateReason.INSUFFICIENT_RESEARCH_EXPECTED)
    if rate_below(metrics.recovered_qualified_count, metrics.qualified_count, gate.minimum_recall):
        reasons.append(EvaluationGateReason.RECALL_BELOW_LIMIT)
    if rate_exceeds(
        metrics.false_exclusion_count,
        metrics.qualified_count,
        gate.maximum_false_exclusion_rate,
    ):
        reasons.append(EvaluationGateReason.FALSE_EXCLUSION_ABOVE_LIMIT)
    if rate_exceeds(
        metrics.false_positive_count,
        metrics.not_qualified_count,
        gate.maximum_false_positive_rate,
    ):
        reasons.append(EvaluationGateReason.FALSE_POSITIVE_ABOVE_LIMIT)
    if rate_exceeds(
        metrics.unsupported_decision_count,
        metrics.research_expected_count,
        gate.maximum_unsupported_decision_rate,
    ):
        reasons.append(EvaluationGateReason.UNSUPPORTED_DECISION_ABOVE_LIMIT)
    if any(
        stage.input_tokens + stage.output_tokens > gate.maximum_tokens_per_case * stage.case_count
        for stage in metrics.stages
    ):
        reasons.append(EvaluationGateReason.TOKENS_ABOVE_LIMIT)
    if metrics.currency != gate.currency:
        reasons.append(EvaluationGateReason.CURRENCY_MISMATCH)
    elif metrics.recovered_qualified_count == 0:
        reasons.append(EvaluationGateReason.UNIT_COST_UNKNOWN)
    elif metrics.actual_cost > (
        gate.maximum_cost_per_recovered_qualified * metrics.recovered_qualified_count
    ):
        reasons.append(EvaluationGateReason.UNIT_COST_ABOVE_LIMIT)
    if not reasons:
        return EvaluationGateResult(True, (EvaluationGateReason.PASSED,))
    return EvaluationGateResult(False, tuple(reasons))
