"""Validated dashboard control values and authority transformations; EP-07.02."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from acoa.config import ApplicationLimits, BudgetLimits, OutreachLimits


@dataclass(frozen=True, slots=True)
class DashboardControlCommand:
    request_id: UUID
    actor_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, UUID):
            raise ValueError("Dashboard controls require a request identifier.")
        if (
            not isinstance(self.actor_sha256, str)
            or len(self.actor_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.actor_sha256)
        ):
            raise ValueError("Dashboard controls require an authenticated actor digest.")


@dataclass(frozen=True, slots=True)
class DashboardLimitValues:
    applications_per_day: int | None
    applications_per_week: int | None
    outreach_per_company: int | None
    outreach_per_contact: int | None
    currency: str | None
    currency_per_day: Decimal | None
    currency_per_month: Decimal | None
    tokens_per_task: int | None
    seconds_per_task: int | None

    def __post_init__(self) -> None:
        ApplicationLimits(self.applications_per_day, self.applications_per_week)
        OutreachLimits(self.outreach_per_company, self.outreach_per_contact)
        BudgetLimits(
            self.currency,
            self.currency_per_day,
            self.currency_per_month,
            self.tokens_per_task,
            self.seconds_per_task,
        )


@dataclass(frozen=True, slots=True)
class DashboardControlResult:
    action: str
    state: str
    task_id: UUID | None = None
    authority_revision: int | None = None
