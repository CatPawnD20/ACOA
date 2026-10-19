"""EP-00.02 configuration validation; E-02.01, P-04/P-10/P-17, ADR-006/011."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import cast
from uuid import UUID


class ConfigurationError(ValueError):
    """Invalid configuration, reported without disclosing supplied values."""


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a boolean.")
    return value


def _count(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{name} must be a nonnegative integer or unset.")
    return value


def _amount(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ConfigurationError(f"{name} must be a finite nonnegative decimal or unset.")
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0:
        raise ConfigurationError(f"{name} must be a finite nonnegative decimal or unset.")
    return amount


def _currency(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 3
        or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in value)
    ):
        raise ConfigurationError("budget.currency must be a three-letter uppercase label or unset.")
    return value


def _validate_items(items: object, name: str) -> None:
    if not isinstance(items, tuple) or any(
        not isinstance(item, str) or not item or item != item.strip() for item in items
    ):
        raise ConfigurationError(f"{name} must contain nonempty strings without outer whitespace.")


@dataclass(frozen=True, slots=True)
class ApplicationLimits:
    max_per_day: int | None = None
    max_per_week: int | None = None

    def __post_init__(self) -> None:
        _count(self.max_per_day, "applications.max_per_day")
        _count(self.max_per_week, "applications.max_per_week")


@dataclass(frozen=True, slots=True)
class OutreachLimits:
    per_company_limit: int | None = None
    per_contact_limit: int | None = None

    def __post_init__(self) -> None:
        _count(self.per_company_limit, "outreach.per_company_limit")
        _count(self.per_contact_limit, "outreach.per_contact_limit")


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    currency: str | None = None
    max_currency_per_day: Decimal | None = None
    max_currency_per_month: Decimal | None = None
    max_tokens_per_task: int | None = None
    max_time_per_task: int | None = None
    paid_services_enabled: bool = True
    progress_stall_timeout: int | None = None

    def __post_init__(self) -> None:
        _currency(self.currency)
        for name in ("max_currency_per_day", "max_currency_per_month"):
            object.__setattr__(self, name, _amount(getattr(self, name), f"budget.{name}"))
        _count(self.max_tokens_per_task, "budget.max_tokens_per_task")
        _count(self.max_time_per_task, "budget.max_time_per_task")
        _boolean(self.paid_services_enabled, "budget.paid_services_enabled")
        _count(self.progress_stall_timeout, "budget.progress_stall_timeout")


@dataclass(frozen=True, slots=True)
class AuthorizationReference:
    grant_id: UUID | None = field(default=None, repr=False)
    limit_policy_id: UUID | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("grant_id", self.grant_id),
            ("limit_policy_id", self.limit_policy_id),
        ):
            if value is not None and not isinstance(value, UUID):
                raise ConfigurationError(f"authorization.{name} must be a UUID or unset.")


@dataclass(frozen=True, slots=True)
class AccountSettings:
    authorized_emails: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _validate_items(self.authorized_emails, "accounts.authorized_emails")


@dataclass(frozen=True, slots=True)
class PrivacySettings:
    allowed_data_categories: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _validate_items(self.allowed_data_categories, "privacy.allowed_data_categories")


@dataclass(frozen=True, slots=True)
class Settings:
    dry_run: bool = True
    external_actions_enabled: bool = False
    applications: ApplicationLimits = field(default_factory=ApplicationLimits)
    outreach: OutreachLimits = field(default_factory=OutreachLimits)
    budget: BudgetLimits = field(default_factory=BudgetLimits)
    authorization: AuthorizationReference = field(default_factory=AuthorizationReference)
    accounts: AccountSettings = field(default_factory=AccountSettings)
    privacy: PrivacySettings = field(default_factory=PrivacySettings)

    def __post_init__(self) -> None:
        _boolean(self.dry_run, "dry_run")
        _boolean(self.external_actions_enabled, "external_actions_enabled")
        for name, model in (
            ("applications", ApplicationLimits),
            ("outreach", OutreachLimits),
            ("budget", BudgetLimits),
            ("authorization", AuthorizationReference),
            ("accounts", AccountSettings),
            ("privacy", PrivacySettings),
        ):
            if not isinstance(getattr(self, name), model):
                raise ConfigurationError(f"{name} must be a validated configuration section.")


@dataclass(frozen=True, slots=True)
class ConfigurationReadiness:
    """Configuration completeness only; never a Policy Gate authorization decision."""

    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


def _known_fields(data: Mapping[str, object], allowed: tuple[str, ...], name: str) -> None:
    if any(key not in allowed for key in data):
        raise ConfigurationError(f"Unknown fields in {name}.")


def _section(
    data: Mapping[str, object], name: str, allowed: tuple[str, ...]
) -> Mapping[str, object]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a table.")
    section = cast(Mapping[str, object], value)
    _known_fields(section, allowed, name)
    return section


def _parse_applications(data: Mapping[str, object]) -> ApplicationLimits:
    section = _section(data, "applications", ("max_per_day", "max_per_week"))
    return ApplicationLimits(
        max_per_day=_count(section.get("max_per_day"), "applications.max_per_day"),
        max_per_week=_count(section.get("max_per_week"), "applications.max_per_week"),
    )


def _parse_outreach(data: Mapping[str, object]) -> OutreachLimits:
    section = _section(data, "outreach", ("per_company_limit", "per_contact_limit"))
    return OutreachLimits(
        per_company_limit=_count(section.get("per_company_limit"), "outreach.per_company_limit"),
        per_contact_limit=_count(section.get("per_contact_limit"), "outreach.per_contact_limit"),
    )


def _parse_budget(data: Mapping[str, object]) -> BudgetLimits:
    section = _section(
        data,
        "budget",
        (
            "currency",
            "max_currency_per_day",
            "max_currency_per_month",
            "max_tokens_per_task",
            "max_time_per_task",
            "paid_services_enabled",
            "progress_stall_timeout",
        ),
    )
    return BudgetLimits(
        currency=_currency(section.get("currency")),
        max_currency_per_day=_amount(
            section.get("max_currency_per_day"), "budget.max_currency_per_day"
        ),
        max_currency_per_month=_amount(
            section.get("max_currency_per_month"), "budget.max_currency_per_month"
        ),
        max_tokens_per_task=_count(
            section.get("max_tokens_per_task"), "budget.max_tokens_per_task"
        ),
        max_time_per_task=_count(section.get("max_time_per_task"), "budget.max_time_per_task"),
        paid_services_enabled=_boolean(
            section.get("paid_services_enabled", True), "budget.paid_services_enabled"
        ),
        progress_stall_timeout=_count(
            section.get("progress_stall_timeout"), "budget.progress_stall_timeout"
        ),
    )


def _parse_authorization(data: Mapping[str, object]) -> AuthorizationReference:
    section = _section(data, "authorization", ("grant_id", "limit_policy_id"))

    def reference(name: str) -> UUID | None:
        value = section.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigurationError(f"authorization.{name} must be a UUID string or unset.")
        try:
            return UUID(value)
        except ValueError:
            raise ConfigurationError(
                f"authorization.{name} must be a UUID string or unset."
            ) from None

    return AuthorizationReference(
        grant_id=reference("grant_id"),
        limit_policy_id=reference("limit_policy_id"),
    )


def _parse_items(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{name} must be an array of strings.")
    items = tuple(value)
    _validate_items(items, name)
    return cast(tuple[str, ...], items)


def _parse_accounts(data: Mapping[str, object]) -> AccountSettings:
    section = _section(data, "accounts", ("authorized_emails",))
    return AccountSettings(
        authorized_emails=_parse_items(
            section.get("authorized_emails", []), "accounts.authorized_emails"
        )
    )


def _parse_privacy(data: Mapping[str, object]) -> PrivacySettings:
    section = _section(data, "privacy", ("allowed_data_categories",))
    return PrivacySettings(
        allowed_data_categories=_parse_items(
            section.get("allowed_data_categories", []), "privacy.allowed_data_categories"
        )
    )


def settings_from_mapping(data: Mapping[str, object]) -> Settings:
    """Validate a configuration mapping without file, environment, or provider access."""
    _known_fields(
        data,
        (
            "dry_run",
            "external_actions_enabled",
            "applications",
            "outreach",
            "budget",
            "authorization",
            "accounts",
            "privacy",
        ),
        "configuration",
    )
    return Settings(
        dry_run=_boolean(data.get("dry_run", True), "dry_run"),
        external_actions_enabled=_boolean(
            data.get("external_actions_enabled", False), "external_actions_enabled"
        ),
        applications=_parse_applications(data),
        outreach=_parse_outreach(data),
        budget=_parse_budget(data),
        authorization=_parse_authorization(data),
        accounts=_parse_accounts(data),
        privacy=_parse_privacy(data),
    )


def load_settings(path: Path) -> Settings:
    """Load only the explicitly supplied TOML file; errors never echo file contents."""
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream, parse_float=Decimal)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, DecimalException):
        raise ConfigurationError("Unable to load configuration TOML.") from None
    return settings_from_mapping(data)


def _mode_blockers(settings: Settings) -> tuple[str, ...]:
    blockers = []
    if settings.dry_run:
        blockers.append("dry_run_enabled")
    if not settings.external_actions_enabled:
        blockers.append("external_actions_disabled")
    return tuple(blockers)


def _limit_blockers(settings: Settings) -> tuple[str, ...]:
    blockers = []
    for name, count_value in (
        ("applications.max_per_day", settings.applications.max_per_day),
        ("applications.max_per_week", settings.applications.max_per_week),
        ("outreach.per_company_limit", settings.outreach.per_company_limit),
        ("outreach.per_contact_limit", settings.outreach.per_contact_limit),
        ("budget.max_tokens_per_task", settings.budget.max_tokens_per_task),
        ("budget.max_time_per_task", settings.budget.max_time_per_task),
    ):
        if count_value is None or count_value == 0:
            blockers.append(name)
    for name, money_value in (
        ("budget.max_currency_per_day", settings.budget.max_currency_per_day),
        ("budget.max_currency_per_month", settings.budget.max_currency_per_month),
    ):
        if settings.budget.paid_services_enabled:
            if money_value is None or money_value == 0:
                blockers.append(name)
        elif money_value is None or money_value != 0:
            blockers.append(name)
    if settings.budget.currency is None:
        blockers.append("budget.currency")
    stall_timeout = settings.budget.progress_stall_timeout
    if stall_timeout is not None and stall_timeout == 0:
        blockers.append("budget.progress_stall_timeout")
    if (
        stall_timeout is not None
        and settings.budget.max_time_per_task is not None
        and stall_timeout > settings.budget.max_time_per_task
    ):
        blockers.append("budget.progress_stall_timeout_above_task_limit")
    return tuple(blockers)


def _permission_configuration_blockers(settings: Settings) -> tuple[str, ...]:
    blockers = []
    for name, value in (
        ("authorization.grant_id", settings.authorization.grant_id),
        ("accounts.authorized_emails", settings.accounts.authorized_emails),
        ("privacy.allowed_data_categories", settings.privacy.allowed_data_categories),
    ):
        if not value:
            blockers.append(name)
    return tuple(blockers)


def external_action_readiness(settings: Settings) -> ConfigurationReadiness:
    """Check completeness; real actions still require a resolved grant and Policy Gate."""
    return ConfigurationReadiness(
        blockers=(
            _mode_blockers(settings)
            + _limit_blockers(settings)
            + _permission_configuration_blockers(settings)
        )
    )
