"""Pre-activation configuration readiness with no activation side effect; EP-10.04."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from acoa.config import Settings
from acoa.domain.authorization import (
    AuthorizationGrant,
    Channel,
    DataCategory,
    grant_is_active,
    validate_scope,
)
from acoa.domain.goals import UserGoals, goals_content_sha256
from acoa.domain.profile import ProfileVariant, variant_content_sha256, variant_is_usable
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


class ReadinessState(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_PILOT = "ready_for_pilot"


@dataclass(frozen=True, slots=True)
class ChannelConfiguration:
    binding_id: UUID = field(repr=False)
    channel: Channel
    account_id: UUID = field(repr=False)
    terms_evidence_sha256: str = field(repr=False)
    verified_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        require_identifier(self.binding_id)
        require_identifier(self.account_id)
        if not isinstance(self.channel, Channel):
            raise DomainError("A channel configuration requires an explicit channel.")
        require_sha256(self.terms_evidence_sha256)
        require_timestamp(self.verified_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.verified_at:
            raise DomainError("Channel terms validity must follow verification.")


def channel_configuration_sha256(configuration: ChannelConfiguration) -> str:
    return content_digest(
        {
            "binding_id": str(configuration.binding_id),
            "channel": configuration.channel.value,
            "account_id": str(configuration.account_id),
            "terms_evidence_sha256": configuration.terms_evidence_sha256,
            "verified_at": configuration.verified_at.astimezone(UTC).isoformat(),
            "valid_until": configuration.valid_until.astimezone(UTC).isoformat(),
        }
    )


@dataclass(frozen=True, slots=True)
class ActivationReadinessAssessment:
    assessment_id: UUID
    authority_revision: int
    profile_variant_id: UUID | None = field(repr=False)
    profile_variant_version: int | None
    profile_sha256: str | None = field(repr=False)
    goals_id: UUID | None = field(repr=False)
    goals_version: int | None
    goals_sha256: str | None = field(repr=False)
    channel_configuration_sha256s: tuple[str, ...] = field(repr=False)
    blockers: tuple[str, ...]
    assessed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.assessment_id)
        if (
            isinstance(self.authority_revision, bool)
            or not isinstance(self.authority_revision, int)
            or self.authority_revision < 0
        ):
            raise DomainError("Authority revision must be a nonnegative integer.")
        profile_values = (
            self.profile_variant_id,
            self.profile_variant_version,
            self.profile_sha256,
        )
        goals_values = (self.goals_id, self.goals_version, self.goals_sha256)
        if any(value is None for value in profile_values) != all(
            value is None for value in profile_values
        ):
            raise DomainError("Profile readiness evidence must be complete or absent.")
        if any(value is None for value in goals_values) != all(
            value is None for value in goals_values
        ):
            raise DomainError("Goal readiness evidence must be complete or absent.")
        if self.profile_variant_id is not None:
            require_identifier(self.profile_variant_id)
            require_version(self.profile_variant_version)
            require_sha256(self.profile_sha256)
        if self.goals_id is not None:
            require_identifier(self.goals_id)
            require_version(self.goals_version)
            require_sha256(self.goals_sha256)
        if any(not isinstance(item, str) or not item for item in self.blockers):
            raise DomainError("Readiness blockers must be explicit codes.")
        if tuple(sorted(set(self.blockers))) != self.blockers:
            raise DomainError("Readiness blockers must be unique and ordered.")
        if any(not isinstance(item, str) for item in self.channel_configuration_sha256s):
            raise DomainError("Channel readiness evidence must use content digests.")
        for digest in self.channel_configuration_sha256s:
            require_sha256(digest)
        if tuple(sorted(set(self.channel_configuration_sha256s))) != (
            self.channel_configuration_sha256s
        ):
            raise DomainError("Channel readiness evidence must be unique and ordered.")
        require_timestamp(self.assessed_at)

    @property
    def state(self) -> ReadinessState:
        return ReadinessState.BLOCKED if self.blockers else ReadinessState.READY_FOR_PILOT


def _limit_blockers(settings: Settings) -> set[str]:
    values = (
        ("applications.max_per_day", settings.applications.max_per_day),
        ("applications.max_per_week", settings.applications.max_per_week),
        ("outreach.per_company_limit", settings.outreach.per_company_limit),
        ("outreach.per_contact_limit", settings.outreach.per_contact_limit),
        ("budget.max_tokens_per_task", settings.budget.max_tokens_per_task),
        ("budget.max_time_per_task", settings.budget.max_time_per_task),
    )
    blockers = {name for name, count_value in values if count_value is None or count_value == 0}
    for name, money_value in (
        ("budget.max_currency_per_day", settings.budget.max_currency_per_day),
        ("budget.max_currency_per_month", settings.budget.max_currency_per_month),
    ):
        if settings.budget.paid_services_enabled:
            if money_value is None or money_value == 0:
                blockers.add(name)
        elif money_value is None or money_value != 0:
            blockers.add(name)
    if settings.budget.currency is None:
        blockers.add("budget.currency")
    stall_timeout = settings.budget.progress_stall_timeout
    if stall_timeout is not None and stall_timeout == 0:
        blockers.add("budget.progress_stall_timeout")
    if (
        stall_timeout is not None
        and settings.budget.max_time_per_task is not None
        and stall_timeout > settings.budget.max_time_per_task
    ):
        blockers.add("budget.progress_stall_timeout_above_task_limit")
    if (
        settings.applications.max_per_day is not None
        and settings.applications.max_per_week is not None
        and settings.applications.max_per_week < settings.applications.max_per_day
    ):
        blockers.add("applications.weekly_below_daily")
    if (
        settings.budget.max_currency_per_day is not None
        and settings.budget.max_currency_per_month is not None
        and settings.budget.max_currency_per_month < settings.budget.max_currency_per_day
    ):
        blockers.add("budget.monthly_below_daily")
    return blockers


def _profile_goal_blockers(
    profile: ProfileVariant | None, goals: UserGoals | None, now: datetime
) -> set[str]:
    blockers: set[str] = set()
    if profile is None:
        blockers.add("profile.missing")
    elif not variant_is_usable(profile, now):
        blockers.add("profile.not_current_approved")
    if goals is None:
        blockers.add("goals.missing")
    else:
        if goals.updated_at > now:
            blockers.add("goals.future_dated")
        if not goals.hard_constraints and not goals.soft_preferences:
            blockers.add("goals.empty")
    return blockers


def _authority_blockers(
    settings: Settings,
    grant: AuthorizationGrant | None,
    paused: bool,
    now: datetime,
) -> set[str]:
    blockers = _limit_blockers(settings)
    if paused:
        blockers.add("authority.paused")
    if not settings.dry_run:
        blockers.add("safety.dry_run_must_remain_enabled")
    if settings.external_actions_enabled:
        blockers.add("safety.external_actions_must_remain_disabled")
    if grant is None:
        blockers.add("authorization.grant_missing")
        return blockers
    if not grant_is_active(grant, now):
        blockers.add("authorization.grant_inactive")
    if settings.authorization.grant_id != grant.grant_id:
        blockers.add("authorization.grant_reference_mismatch")
    if settings.authorization.limit_policy_id != grant.limit_policy_id:
        blockers.add("authorization.limit_policy_reference_mismatch")
    if len(set(settings.accounts.authorized_emails)) != len(settings.accounts.authorized_emails):
        blockers.add("channels.duplicate_authorized_email")
    if len(set(settings.privacy.allowed_data_categories)) != len(
        settings.privacy.allowed_data_categories
    ):
        blockers.add("privacy.duplicate_data_category")
    try:
        allowed_categories = {
            DataCategory(value) for value in settings.privacy.allowed_data_categories
        }
    except ValueError:
        blockers.add("privacy.unknown_data_category")
    else:
        if not set(grant.data_categories) <= allowed_categories:
            blockers.add("privacy.grant_scope_not_allowed")
    if Channel.EMAIL in grant.channels and not settings.accounts.authorized_emails:
        blockers.add("channels.authorized_email_missing")
    return blockers


def _channel_blockers(
    grant: AuthorizationGrant | None,
    configurations: tuple[ChannelConfiguration, ...],
    now: datetime,
) -> set[str]:
    validate_scope(configurations, ChannelConfiguration)
    pairs = {(item.channel, item.account_id) for item in configurations}
    if len(pairs) != len(configurations):
        raise DomainError("A channel/account configuration may appear only once.")
    if grant is None:
        return set()
    blockers: set[str] = set()
    grant_channels = set(grant.channels)
    grant_accounts = set(grant.account_ids)
    if any(item.channel not in grant_channels for item in configurations):
        blockers.add("channels.outside_grant")
    if any(item.account_id not in grant_accounts for item in configurations):
        blockers.add("channels.account_outside_grant")
    current = tuple(item for item in configurations if item.verified_at <= now < item.valid_until)
    if not grant_channels <= {item.channel for item in current}:
        blockers.add("channels.required_channel_missing")
    if not grant_accounts <= {item.account_id for item in current}:
        blockers.add("channels.required_account_missing")
    return blockers


def assess_activation_readiness(
    assessment_id: UUID,
    authority_revision: int,
    settings: Settings,
    grant: AuthorizationGrant | None,
    paused: bool,
    profile: ProfileVariant | None,
    goals: UserGoals | None,
    channel_configurations: tuple[ChannelConfiguration, ...],
    now: datetime,
) -> ActivationReadinessAssessment:
    """Prove configuration completeness while keeping all external actions disabled."""
    require_identifier(assessment_id)
    require_timestamp(now)
    if not isinstance(settings, Settings) or not isinstance(paused, bool):
        raise DomainError("Readiness requires current validated authority settings.")
    if grant is not None and not isinstance(grant, AuthorizationGrant):
        raise DomainError("Readiness authority grant must be validated or absent.")
    if profile is not None and not isinstance(profile, ProfileVariant):
        raise DomainError("Readiness profile must be a validated variant or absent.")
    if goals is not None and not isinstance(goals, UserGoals):
        raise DomainError("Readiness goals must be validated or absent.")
    blockers = (
        _profile_goal_blockers(profile, goals, now)
        | _authority_blockers(settings, grant, paused, now)
        | _channel_blockers(grant, channel_configurations, now)
    )
    return ActivationReadinessAssessment(
        assessment_id=assessment_id,
        authority_revision=authority_revision,
        profile_variant_id=profile.variant_id if profile else None,
        profile_variant_version=profile.version if profile else None,
        profile_sha256=variant_content_sha256(profile) if profile else None,
        goals_id=goals.goals_id if goals else None,
        goals_version=goals.version if goals else None,
        goals_sha256=goals_content_sha256(goals) if goals else None,
        channel_configuration_sha256s=tuple(
            sorted(channel_configuration_sha256(item) for item in channel_configurations)
        ),
        blockers=tuple(sorted(blockers)),
        assessed_at=now,
    )
