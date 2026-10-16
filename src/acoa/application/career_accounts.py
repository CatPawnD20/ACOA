"""Central-executor adapter for authorized career-account creation; EP-08.03."""

from collections.abc import Callable
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID, uuid4

from acoa.application.executor import ProviderAcknowledgement
from acoa.application.policy import request_binding_sha256
from acoa.domain.actions import DispatchLimits, PreparedAction, career_account_semantic_key
from acoa.domain.authorization import ActionKind, Channel
from acoa.domain.career_accounts import (
    AccountCredential,
    CareerAccountEvent,
    CareerAccountMaterial,
    CareerAccountPlan,
    CareerAccountProviderResult,
    CareerAccountResultKind,
    career_account_plan_sha256,
    login_identifier_sha256,
)
from acoa.domain.values import DomainError


class CareerAccountPlanReader(Protocol):
    def read_plan(self, plan_id: UUID) -> CareerAccountPlan: ...


class CareerAccountMaterialReader(Protocol):
    def read_material(self, plan_id: UUID) -> CareerAccountMaterial: ...


class CareerAccountSecretStore(Protocol):
    """Atomically retain one new credential; never return or log its secret value."""

    def create(self, credential: AccountCredential) -> None: ...


class CareerAccountEventWriter(Protocol):
    def append(self, event: CareerAccountEvent) -> None: ...


class CareerAccountProvider(Protocol):
    def create_once(
        self,
        plan: CareerAccountPlan,
        credential: AccountCredential,
        limits: DispatchLimits,
    ) -> CareerAccountProviderResult: ...


def generate_account_credential(
    login_identifier: str,
    identifier_factory: Callable[[], UUID] = uuid4,
    password_factory: Callable[[int], str] = token_urlsafe,
) -> AccountCredential:
    return AccountCredential(identifier_factory(), login_identifier, password_factory(32))


class CareerAccountInteractionAdapter:
    """Trusted adapter registered only with the central ExternalActionExecutor."""

    def __init__(
        self,
        plans: CareerAccountPlanReader,
        materials: CareerAccountMaterialReader,
        secrets: CareerAccountSecretStore,
        events: CareerAccountEventWriter,
        provider: CareerAccountProvider,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        identifier_factory: Callable[[], UUID] = uuid4,
        password_factory: Callable[[int], str] = token_urlsafe,
    ) -> None:
        self.plans = plans
        self.materials = materials
        self.secrets = secrets
        self.events = events
        self.provider = provider
        self.clock = clock
        self.identifier_factory = identifier_factory
        self.password_factory = password_factory

    def execute_once(
        self, prepared: PreparedAction, limits: DispatchLimits
    ) -> ProviderAcknowledgement | None:
        plan, material = self._load_exact_material(prepared)
        credential = generate_account_credential(
            material.login_identifier,
            self.identifier_factory,
            self.password_factory,
        )
        self.secrets.create(credential)
        try:
            result = self.provider.create_once(plan, credential, limits)
        except Exception:
            result = CareerAccountProviderResult(CareerAccountResultKind.UNCONFIRMED)
        if not isinstance(result, CareerAccountProviderResult):
            result = CareerAccountProviderResult(CareerAccountResultKind.UNCONFIRMED)
        event = CareerAccountEvent(
            self.identifier_factory(),
            plan.plan_id,
            prepared.attempt_id,
            credential.secret_ref_id,
            result,
            self.clock(),
        )
        self.events.append(event)
        if result.kind is not CareerAccountResultKind.CREATED:
            return None
        return ProviderAcknowledgement(
            prepared.attempt_id,
            request_binding_sha256(prepared.request),
            event.event_id,
        )

    def _load_exact_material(
        self, prepared: PreparedAction
    ) -> tuple[CareerAccountPlan, CareerAccountMaterial]:
        request = prepared.request
        if (
            request.action is not ActionKind.CREATE_CAREER_ACCOUNT
            or request.channel is not Channel.WEB
            or request.account_id is None
        ):
            raise DomainError("A career-account adapter requires an exact web account request.")
        plan = self.plans.read_plan(prepared.plan_id)
        material = self.materials.read_material(prepared.plan_id)
        if (
            plan.plan_id != prepared.plan_id
            or plan.application_id != prepared.application_id
            or plan.account_id != request.account_id
            or plan.provider_id != prepared.provider_id
            or tuple(plan.data_categories) != tuple(request.data_categories)
            or career_account_plan_sha256(plan) != request.content_sha256
            or material.plan_id != plan.plan_id
            or login_identifier_sha256(material.login_identifier) != plan.login_sha256
            or prepared.semantic_key
            != career_account_semantic_key(plan.account_id, plan.provider_id)
            or self.clock() >= plan.expires_at
        ):
            raise DomainError("Career-account material does not match the prepared action.")
        return plan, material
