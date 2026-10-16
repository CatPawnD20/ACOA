"""Privacy-limited dashboard view models; EP-07.01."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DashboardQuery:
    search: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.search is not None and (
            not self.search or self.search != self.search.strip() or len(self.search) > 100
        ):
            raise ValueError("Dashboard search must be a trimmed value of at most 100 characters.")
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or not 1 <= self.limit <= 200
        ):
            raise ValueError("Dashboard result limit must be between 1 and 200.")


@dataclass(frozen=True, slots=True)
class DashboardApplication:
    application_id: UUID
    company_id: UUID
    company_label: str
    kind: str
    state: str
    submission_state: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardCompany:
    company_id: UUID
    label: str
    application_count: int
    open_application_count: int


@dataclass(frozen=True, slots=True)
class DashboardTask:
    task_id: UUID
    kind: str
    state: str
    attempt_count: int
    next_run_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardWaitingItem:
    task_id: UUID
    task_kind: str
    question_id: UUID
    waiting_since: datetime


@dataclass(frozen=True, slots=True)
class DashboardCost:
    currency: str
    consumed: Decimal
    reserved: Decimal
    unsettled_count: int


@dataclass(frozen=True, slots=True)
class DashboardPerformance:
    application_count: int
    open_application_count: int
    task_count: int
    completed_task_count: int
    failed_task_count: int
    waiting_user_count: int
    model_call_count: int
    consumed_tokens: int
    consumed_seconds: Decimal
    verified_action_count: int
    unconfirmed_action_count: int


@dataclass(frozen=True, slots=True)
class DashboardAuthority:
    revision: int
    paused: bool
    dry_run: bool
    external_actions_enabled: bool
    applications_per_day: int | None
    applications_per_week: int | None
    outreach_per_company: int | None
    outreach_per_contact: int | None
    currency: str | None
    currency_per_day: Decimal | None
    currency_per_month: Decimal | None
    tokens_per_task: int | None
    seconds_per_task: int | None


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    generated_at: datetime
    authority: DashboardAuthority
    applications: tuple[DashboardApplication, ...]
    companies: tuple[DashboardCompany, ...]
    tasks: tuple[DashboardTask, ...]
    waiting_items: tuple[DashboardWaitingItem, ...]
    costs: tuple[DashboardCost, ...]
    performance: DashboardPerformance
