"""Operational health, error-budget and response values for EP-10.03."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


class DependencyKind(StrEnum):
    DATABASE = "database"
    ARTIFACT_STORE = "artifact_store"
    MAIL_PROVIDER = "mail_provider"
    MODEL_PROVIDER = "model_provider"
    SOURCE_PROVIDER = "source_provider"
    BROWSER_WORKER = "browser_worker"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    SYSTEMIC_RISK = "systemic_risk"


class OperationalResponse(StrEnum):
    CONTINUE = "continue"
    ALERT = "alert"
    ISOLATE_DEPENDENCY = "isolate_dependency"
    ENTER_SAFE_MODE = "enter_safe_mode"


@dataclass(frozen=True, slots=True)
class ErrorBudgetPolicy:
    maximum_failures: int
    window_seconds: int

    def __post_init__(self) -> None:
        require_version(self.maximum_failures)
        require_version(self.window_seconds)


@dataclass(frozen=True, slots=True)
class HealthObservation:
    observation_id: UUID
    dependency: DependencyKind
    state: HealthState
    evidence_sha256: str
    observed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.observation_id)
        if not isinstance(self.dependency, DependencyKind) or not isinstance(
            self.state, HealthState
        ):
            raise DomainError("Health observations require explicit dependency and state values.")
        require_sha256(self.evidence_sha256)
        require_timestamp(self.observed_at)


@dataclass(frozen=True, slots=True)
class OperationalAssessment:
    assessment_id: UUID
    dependency: DependencyKind
    observation_ids: tuple[UUID, ...]
    response: OperationalResponse
    failure_count: int
    maximum_failures: int
    window_seconds: int
    assessed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.assessment_id)
        if not isinstance(self.dependency, DependencyKind) or not isinstance(
            self.response, OperationalResponse
        ):
            raise DomainError("Operational assessments require explicit typed decisions.")
        if not self.observation_ids or len(set(self.observation_ids)) != len(self.observation_ids):
            raise DomainError("Operational assessments require unique health observations.")
        for identifier in self.observation_ids:
            require_identifier(identifier)
        if (
            isinstance(self.failure_count, bool)
            or not isinstance(self.failure_count, int)
            or self.failure_count < 0
        ):
            raise DomainError("Operational failure count must be a nonnegative integer.")
        require_version(self.maximum_failures)
        require_version(self.window_seconds)
        require_timestamp(self.assessed_at)


def assess_dependency_health(
    assessment_id: UUID,
    observations: tuple[HealthObservation, ...],
    policy: ErrorBudgetPolicy,
    now: datetime,
) -> OperationalAssessment:
    """Choose a bounded response for one dependency without inventing global failure."""
    require_identifier(assessment_id)
    require_timestamp(now)
    if (
        not isinstance(policy, ErrorBudgetPolicy)
        or not observations
        or any(not isinstance(item, HealthObservation) for item in observations)
    ):
        raise DomainError("Health assessment requires observations and an explicit policy.")
    dependency = observations[0].dependency
    if any(item.dependency is not dependency for item in observations):
        raise DomainError("One health assessment cannot combine different dependencies.")
    ordered = tuple(
        sorted(observations, key=lambda item: (item.observed_at, item.observation_id.int))
    )
    if len({item.observation_id for item in ordered}) != len(ordered):
        raise DomainError("Health observations cannot be repeated.")
    window_start = now - timedelta(seconds=policy.window_seconds)
    if any(item.observed_at < window_start or item.observed_at > now for item in ordered):
        raise DomainError("Health observations must fit the configured assessment window.")
    failures = sum(item.state is not HealthState.HEALTHY for item in ordered)
    latest = ordered[-1]
    if any(item.state is HealthState.SYSTEMIC_RISK for item in ordered):
        response = OperationalResponse.ENTER_SAFE_MODE
    elif latest.state is HealthState.UNAVAILABLE or failures >= policy.maximum_failures:
        response = OperationalResponse.ISOLATE_DEPENDENCY
    elif latest.state is HealthState.DEGRADED:
        response = OperationalResponse.ALERT
    else:
        response = OperationalResponse.CONTINUE
    return OperationalAssessment(
        assessment_id,
        dependency,
        tuple(item.observation_id for item in ordered),
        response,
        failures,
        policy.maximum_failures,
        policy.window_seconds,
        now,
    )
