"""Bounded route -> gateway -> trusted quality check; T0 never invokes the gateway."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from time import monotonic_ns
from typing import Protocol
from uuid import UUID, uuid5

from acoa.application.decision_records import serialize_snapshot_value
from acoa.application.model_gateway import ModelGateway
from acoa.application.model_router import RouteDecision, select_route
from acoa.domain.model_calls import (
    ModelCallRequest,
    ModelCallState,
    StructuredModelOutput,
    model_request_sha256,
    validate_output_object,
)
from acoa.domain.model_quality import QualityReport, output_content_sha256, quality_passes
from acoa.domain.model_routing import ModelOption, RoutingPolicy, RoutingStrategy, RoutingTask
from acoa.domain.values import DomainError, require_identifier, require_text

NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True, slots=True)
class ModelRunInput:
    route_id: UUID
    task_id: UUID
    lease_owner: UUID = field(repr=False)
    lease_token: UUID = field(repr=False)
    prompt_version: str
    output_schema_version: str
    prompt: str = field(repr=False)

    def __post_init__(self) -> None:
        for identifier in (self.route_id, self.task_id, self.lease_owner, self.lease_token):
            require_identifier(identifier)
        for version in (self.prompt_version, self.output_schema_version):
            require_text(version)
        if not isinstance(self.prompt, str):
            raise DomainError("Workflow input must be explicit text.")


@dataclass(frozen=True, slots=True)
class ModelWorkflowResult:
    strategy: RoutingStrategy
    reason: str
    output: StructuredModelOutput | None = None
    deterministic_json: str | None = field(default=None, repr=False)


class QualityEvaluator(Protocol):
    evaluator_version: str

    def assess(self, request: ModelCallRequest, output: StructuredModelOutput) -> QualityReport: ...


class RoutingAuditStore(Protocol):
    def route(self, run: ModelRunInput, input_sha256: str, decision: RouteDecision) -> bool: ...
    def quality(
        self, call_id: UUID, policy_version: str, report: QualityReport, passed: bool
    ) -> None: ...


def routing_input_sha256(
    run: ModelRunInput,
    task: RoutingTask,
    policy: RoutingPolicy,
    catalog: tuple[ModelOption, ...],
) -> str:
    payload = {
        "run": asdict(run),
        "task": asdict(task),
        "policy": asdict(policy),
        "catalog": [asdict(item) for item in catalog],
    }
    encoded = json.dumps(
        payload, default=serialize_snapshot_value, sort_keys=True, separators=(",", ":")
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def assess_output(
    evaluator: QualityEvaluator, request: ModelCallRequest, output: StructuredModelOutput
) -> QualityReport:
    try:
        report = evaluator.assess(request, output)
        if (
            isinstance(report, QualityReport)
            and report.evaluator_version == evaluator.evaluator_version
            and report.output_sha256 == output_content_sha256(output)
            and report.request_sha256 == model_request_sha256(request)
        ):
            return report
    except Exception:
        pass
    return QualityReport(
        output_content_sha256(output),
        evaluator.evaluator_version,
        model_request_sha256(request),
        requires_user=True,
    )


def deterministic_result(handler: Callable[[], str] | None) -> ModelWorkflowResult:
    if handler is None:
        return ModelWorkflowResult(RoutingStrategy.DEFER, "deterministic_handler_missing")
    try:
        payload = handler()
        validate_output_object(payload)
    except Exception:
        return ModelWorkflowResult(RoutingStrategy.DEFER, "deterministic_handler_failed")
    return ModelWorkflowResult(
        RoutingStrategy.DETERMINISTIC, "t0_completed", deterministic_json=payload
    )


def stage_request(
    run: ModelRunInput,
    task: RoutingTask,
    policy: RoutingPolicy,
    option: ModelOption,
    index: int,
    timeout: int,
) -> ModelCallRequest:
    if task.required_input_tokens is None:
        raise DomainError("Model workflow input bound is missing.")
    call_id = uuid5(
        run.route_id, f"{policy.policy_version}:{index}:{option.provider_id}:{option.model_alias}"
    )
    return ModelCallRequest(
        call_id,
        run.task_id,
        run.lease_owner,
        run.lease_token,
        option.provider_id,
        option.model_alias,
        run.prompt_version,
        run.output_schema_version,
        run.prompt,
        task.required_input_tokens,
        option.output_token_limit,
        timeout,
        option.max_cost,
        option.currency,
        routing_policy_version=policy.policy_version,
        data_sensitivity=task.sensitivity,
        data_categories=task.categories,
        route_id=run.route_id,
    )


class ModelWorkflow:
    def __init__(self, gateway: ModelGateway, audit: RoutingAuditStore) -> None:
        self.gateway = gateway
        self.audit = audit

    def run(
        self,
        run: ModelRunInput,
        task: RoutingTask,
        policy: RoutingPolicy,
        catalog: tuple[ModelOption, ...],
        evaluator: QualityEvaluator | None = None,
        deterministic: Callable[[], str] | None = None,
    ) -> ModelWorkflowResult:
        decision = select_route(task, policy, catalog, datetime.now(UTC))
        if not self.audit.route(run, routing_input_sha256(run, task, policy, catalog), decision):
            return ModelWorkflowResult(RoutingStrategy.DEFER, "task_paused_or_lease_not_current")
        if decision.strategy is RoutingStrategy.DETERMINISTIC:
            return deterministic_result(deterministic)
        if decision.strategy is not RoutingStrategy.MODEL:
            return ModelWorkflowResult(decision.strategy, decision.decision_reason)
        if evaluator is None:
            return ModelWorkflowResult(RoutingStrategy.DEFER, "quality_evaluator_missing")
        require_text(evaluator.evaluator_version)
        return self._run_stages(run, task, policy, decision.choices, evaluator)

    def _run_stages(
        self,
        run: ModelRunInput,
        task: RoutingTask,
        policy: RoutingPolicy,
        choices: tuple[ModelOption, ...],
        evaluator: QualityEvaluator,
    ) -> ModelWorkflowResult:
        if task.latency_budget is None or task.required_quality is None:
            raise DomainError("Model workflow resource/quality bounds are unresolved.")
        deadline_ns = monotonic_ns() + task.latency_budget * NANOSECONDS_PER_SECOND
        for index, option in enumerate(choices):
            if datetime.now(UTC) >= option.expires_at:
                return ModelWorkflowResult(RoutingStrategy.DEFER, "model_estimate_expired")
            remaining = (deadline_ns - monotonic_ns()) // NANOSECONDS_PER_SECOND
            if remaining < 1:
                return ModelWorkflowResult(RoutingStrategy.DEFER, "latency_budget_exhausted")
            request = stage_request(
                run, task, policy, option, index, min(option.timeout_seconds, remaining)
            )
            outcome = self._checked_stage(
                request, evaluator, task.required_quality, policy.policy_version
            )
            if outcome is not None:
                return outcome
        return ModelWorkflowResult(RoutingStrategy.HUMAN, "bounded_quality_attempts_exhausted")

    def _checked_stage(
        self,
        request: ModelCallRequest,
        evaluator: QualityEvaluator,
        target: Decimal,
        policy_version: str,
    ) -> ModelWorkflowResult | None:
        """Return no result only when a known quality failure permits bounded fallback."""
        result = self.gateway.complete(request)
        if result.state is not ModelCallState.SUCCEEDED or result.output is None:
            return ModelWorkflowResult(
                RoutingStrategy.DEFER, result.reason or "gateway_did_not_complete"
            )
        report = assess_output(evaluator, request, result.output)
        passed = quality_passes(
            report, output_content_sha256(result.output), model_request_sha256(request), target
        )
        self.audit.quality(request.call_id, policy_version, report, passed)
        if report.requires_user or report.score is None:
            return ModelWorkflowResult(RoutingStrategy.HUMAN, "quality_requires_user")
        if passed:
            return ModelWorkflowResult(RoutingStrategy.MODEL, "quality_gate_passed", result.output)
        return None
