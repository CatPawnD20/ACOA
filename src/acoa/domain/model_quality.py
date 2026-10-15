"""Deterministic quality receipts from trusted validators, never model self-ratings."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from acoa.domain.model_calls import StructuredModelOutput
from acoa.domain.values import DomainError, require_sha256, require_text


def require_quality(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
        raise DomainError("Quality must be a finite Decimal between zero and one.")


class QualityCheck(StrEnum):
    STRUCTURE = "structure"
    GROUNDING = "grounding"
    TASK_RELEVANCE = "task_relevance"
    INSTRUCTION_ISOLATION = "instruction_isolation"


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    check: QualityCheck
    status: CheckStatus

    def __post_init__(self) -> None:
        if not isinstance(self.check, QualityCheck) or not isinstance(self.status, CheckStatus):
            raise DomainError("Quality checks require explicit kind and status.")


@dataclass(frozen=True, slots=True)
class QualityReport:
    output_sha256: str
    evaluator_version: str
    request_sha256: str
    score: Decimal | None = None
    checks: tuple[CheckOutcome, ...] = ()
    requires_user: bool = False

    def __post_init__(self) -> None:
        require_sha256(self.output_sha256)
        require_sha256(self.request_sha256)
        require_text(self.evaluator_version)
        if self.score is not None:
            require_quality(self.score)
        if not isinstance(self.checks, tuple) or any(
            not isinstance(item, CheckOutcome) for item in self.checks
        ):
            raise DomainError("Quality reports require immutable structured check outcomes.")
        if len({item.check for item in self.checks}) != len(self.checks):
            raise DomainError("A quality check must have exactly one reported status.")
        if not isinstance(self.requires_user, bool):
            raise DomainError("A human-decision requirement must be explicit.")


def output_content_sha256(output: StructuredModelOutput) -> str:
    return sha256(output.output_json.encode("utf-8")).hexdigest()


def quality_passes(
    report: QualityReport, output_sha256: str, request_sha256: str, target: Decimal
) -> bool:
    require_sha256(output_sha256)
    require_sha256(request_sha256)
    require_quality(target)
    facts = {item.check: item.status for item in report.checks}
    return (
        not report.requires_user
        and report.output_sha256 == output_sha256
        and report.request_sha256 == request_sha256
        and report.score is not None
        and report.score >= target
        and all(facts.get(check) is CheckStatus.PASS for check in QualityCheck)
    )
