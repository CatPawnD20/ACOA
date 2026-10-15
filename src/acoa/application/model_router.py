"""EP-03.02 pure T0-first model selection; routing never authorizes external actions."""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from acoa.domain.authorization import validate_scope
from acoa.domain.model_privacy import DataSensitivity
from acoa.domain.model_routing import (
    ModelOption,
    ProcessingTier,
    RoutingPolicy,
    RoutingStrategy,
    RoutingTask,
)
from acoa.domain.values import DomainError, require_timestamp


@dataclass(frozen=True, slots=True)
class RouteDecision:
    strategy: RoutingStrategy
    routing_policy_version: str
    decision_reason: str
    choices: tuple[ModelOption, ...] = ()
    quality_checks: tuple[str, ...] = ()
    minimum_tier: ProcessingTier | None = None
    required_quality: Decimal | None = None

    @property
    def model_alias(self) -> str | None:
        return self.choices[0].model_alias if self.choices else None


def unknown_routing_input(task: RoutingTask, policy: RoutingPolicy) -> str | None:
    if task.risk is None or task.uncertainty is None or task.complexity is None:
        return "task_assessment_unknown"
    if task.required_quality is None:
        return "quality_target_unknown"
    if policy.max_escalations is None:
        return "escalation_limit_unknown"
    if task.sensitivity is DataSensitivity.UNKNOWN:
        return "data_scope_unknown"
    if any(
        value is None
        for value in (
            task.latency_budget,
            task.remaining_tokens,
            task.remaining_currency,
            task.currency,
            task.required_input_tokens,
        )
    ):
        return "resource_budget_unknown"
    if task.required_input_tokens == 0:
        return "input_token_bound_unknown"
    return None


def eligible_model(
    option: ModelOption,
    task: RoutingTask,
    policy: RoutingPolicy,
    minimum_tier: ProcessingTier,
    now: datetime,
) -> bool:
    if (
        option.tier < minimum_tier
        or option.expires_at <= now
        or task.required_quality is None
        or option.estimated_quality < task.required_quality
        or task.required_input_tokens is None
        or task.required_input_tokens > option.input_token_limit
        or task.remaining_tokens is None
        or task.required_input_tokens + option.output_token_limit > task.remaining_tokens
        or task.latency_budget is None
        or option.timeout_seconds > task.latency_budget
        or task.remaining_currency is None
        or option.max_cost > task.remaining_currency
        or option.currency != task.currency
    ):
        return False
    return any(
        permission.provider_id == option.provider_id
        and permission.policy_version == policy.policy_version
        and permission.covers(task.sensitivity, task.categories, now)
        for permission in policy.permissions
    )


def select_route(
    task: RoutingTask,
    policy: RoutingPolicy,
    catalog: tuple[ModelOption, ...],
    now: datetime,
) -> RouteDecision:
    """Human decisions dominate T0; sufficient deterministic work never spends model tokens."""
    require_timestamp(now)
    if task.requires_user_decision:
        return RouteDecision(
            RoutingStrategy.HUMAN, policy.policy_version, "human_decision_required"
        )
    if task.deterministic_adequate:
        return RouteDecision(RoutingStrategy.DETERMINISTIC, policy.policy_version, "t0_sufficient")
    validate_scope(catalog, ModelOption)
    if len({(option.provider_id, option.model_alias) for option in catalog}) != len(catalog):
        raise DomainError("A catalog must contain one current option per provider/model alias.")
    unknown = unknown_routing_input(task, policy)
    if unknown is not None:
        return RouteDecision(RoutingStrategy.DEFER, policy.policy_version, unknown)
    assert task.risk is not None and task.uncertainty is not None and task.complexity is not None
    minimum = ProcessingTier(max(task.risk.value, task.uncertainty.value, task.complexity.value))
    candidates = sorted(
        (item for item in catalog if eligible_model(item, task, policy, minimum, now)),
        key=lambda item: (
            item.tier.value,
            item.max_cost,
            item.timeout_seconds,
            item.model_alias,
            item.provider_id.int,
        ),
    )
    if not candidates:
        return RouteDecision(
            RoutingStrategy.DEFER, policy.policy_version, "no_authorized_model_within_limits"
        )
    assert policy.max_escalations is not None
    choices = tuple(candidates[: policy.max_escalations + 1])
    return RouteDecision(
        RoutingStrategy.MODEL,
        policy.policy_version,
        "bounded_model_plan",
        choices,
        ("structure", "grounding", "task_relevance", "instruction_isolation"),
        minimum,
        task.required_quality,
    )


def route_decision_json(decision: RouteDecision) -> str:
    primary = decision.choices[0] if decision.choices else None
    return json.dumps(
        {
            "strategy": decision.strategy.value,
            "model_alias": decision.model_alias,
            "reasoning_tier": primary.tier.name
            if primary
            else (
                ProcessingTier.T0.name
                if decision.strategy is RoutingStrategy.DETERMINISTIC
                else None
            ),
            "max_output_tokens": primary.output_token_limit if primary else None,
            "timeout": primary.timeout_seconds if primary else None,
            "quality_checks": decision.quality_checks,
            "minimum_tier": decision.minimum_tier.name if decision.minimum_tier else None,
            "required_quality": str(decision.required_quality)
            if decision.required_quality is not None
            else None,
            "fallback_chain": [
                {
                    "provider_id": str(item.provider_id),
                    "model_alias": item.model_alias,
                    "reasoning_tier": item.tier.name,
                }
                for item in decision.choices[1:]
            ],
            "routing_policy_version": decision.routing_policy_version,
            "estimated_cost": str(primary.max_cost)
            if primary
            else (str(Decimal(0)) if decision.strategy is RoutingStrategy.DETERMINISTIC else None),
            "decision_reason": decision.decision_reason,
            "currency": primary.currency if primary else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
