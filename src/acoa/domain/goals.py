"""EP-01.01 user goals and immutable hard/soft conditions; F-01.02/03/06; P-03."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.profile import ProfileVariant, variant_is_usable
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_text,
    require_timestamp,
    require_version,
)


class GoalDimension(StrEnum):
    ROLE = "role"
    INDUSTRY = "industry"
    SENIORITY = "seniority"
    LOCATION = "location"
    WORK_MODEL = "work_model"
    COMPENSATION = "compensation"
    LANGUAGE = "language"
    EMPLOYMENT_TYPE = "employment_type"


class ConditionOperator(StrEnum):
    REQUIRE = "require"
    EXCLUDE = "exclude"


@dataclass(frozen=True, slots=True)
class GoalCondition:
    dimension: GoalDimension
    operator: ConditionOperator
    values: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, GoalDimension):
            raise DomainError("A goal dimension must be explicit.")
        if not isinstance(self.operator, ConditionOperator):
            raise DomainError("A goal operator must be explicit.")
        if not isinstance(self.values, tuple) or not self.values:
            raise DomainError("Goal values must be a nonempty immutable tuple.")
        for value in self.values:
            require_text(value)
        if len(set(self.values)) != len(self.values):
            raise DomainError("A goal condition must not repeat a value.")


def validate_condition_set(conditions: tuple[GoalCondition, ...]) -> None:
    """Reject ambiguous repeated condition axes and mutable collections."""
    if not isinstance(conditions, tuple) or any(
        not isinstance(condition, GoalCondition) for condition in conditions
    ):
        raise DomainError("Goal conditions must be an immutable tuple.")
    keys = {(condition.dimension, condition.operator) for condition in conditions}
    if len(keys) != len(conditions):
        raise DomainError("Combine values for each goal dimension/operator into one condition.")


def validate_hard_conditions(conditions: tuple[GoalCondition, ...]) -> None:
    """Reject a required set completely excluded by the user's own hard rules."""
    validate_condition_set(conditions)
    required = {
        condition.dimension: set(condition.values)
        for condition in conditions
        if condition.operator is ConditionOperator.REQUIRE
    }
    for condition in conditions:
        if condition.operator is ConditionOperator.EXCLUDE:
            allowed = required.get(condition.dimension)
            if allowed is not None and allowed <= set(condition.values):
                raise DomainError("Hard conditions exclude every required value.")


@dataclass(frozen=True, slots=True)
class UserGoals:
    goals_id: UUID = field(repr=False)
    updated_at: datetime
    version: int = 1
    hard_constraints: tuple[GoalCondition, ...] = field(default=(), repr=False)
    soft_preferences: tuple[GoalCondition, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.goals_id)
        require_timestamp(self.updated_at)
        require_version(self.version)
        validate_hard_conditions(self.hard_constraints)
        validate_condition_set(self.soft_preferences)


def revise_goals(
    goals: UserGoals,
    hard_constraints: tuple[GoalCondition, ...],
    soft_preferences: tuple[GoalCondition, ...],
    updated_at: datetime,
) -> UserGoals:
    """Create a new immutable target version without mutating dependent old references."""
    require_timestamp(updated_at)
    if updated_at < goals.updated_at:
        raise DomainError("A goals correction must not be backdated.")
    return replace(
        goals,
        version=goals.version + 1,
        updated_at=updated_at,
        hard_constraints=hard_constraints,
        soft_preferences=soft_preferences,
    )


@dataclass(frozen=True, slots=True)
class ProfileGoalReference:
    """Version dependency held by a later assessment/draft, never its private contents."""

    variant_id: UUID = field(repr=False)
    variant_version: int
    goals_id: UUID = field(repr=False)
    goals_version: int

    def __post_init__(self) -> None:
        require_identifier(self.variant_id)
        require_identifier(self.goals_id)
        require_version(self.variant_version)
        require_version(self.goals_version)


def reference_is_current(
    reference: ProfileGoalReference, variant: ProfileVariant, goals: UserGoals, now: datetime
) -> bool:
    """Identify stale or inactive inputs before a dependent assessment/draft is reused."""
    return (
        variant_is_usable(variant, now)
        and goals.updated_at <= now
        and reference.variant_id == variant.variant_id
        and reference.variant_version == variant.version
        and reference.goals_id == goals.goals_id
        and reference.goals_version == goals.version
    )
