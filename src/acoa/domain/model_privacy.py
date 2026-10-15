"""Provider data scopes supplied by trusted adapters, never by model assertions."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.authorization import SENSITIVE_CATEGORIES, DataCategory, validate_scope
from acoa.domain.values import DomainError, require_identifier, require_text, require_timestamp


class DataSensitivity(StrEnum):
    UNKNOWN = "unknown"
    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


def validate_data_scope(sensitivity: DataSensitivity, categories: tuple[DataCategory, ...]) -> None:
    if not isinstance(sensitivity, DataSensitivity):
        raise DomainError("Data sensitivity must be an explicit classification.")
    validate_scope(categories, DataCategory)
    if sensitivity is DataSensitivity.PUBLIC and categories:
        raise DomainError("Public data must not include personal sharing categories.")
    if sensitivity in (DataSensitivity.PERSONAL, DataSensitivity.SENSITIVE) and not categories:
        raise DomainError("Nonpublic input requires explicit sharing categories.")
    if sensitivity is DataSensitivity.PERSONAL and set(categories) & SENSITIVE_CATEGORIES:
        raise DomainError("Sensitive categories must not be classified as ordinary personal data.")
    if sensitivity is DataSensitivity.SENSITIVE and not set(categories) & SENSITIVE_CATEGORIES:
        raise DomainError("Sensitive input must name the relevant sensitive sharing categories.")


@dataclass(frozen=True, slots=True)
class ProviderPermission:
    provider_id: UUID
    policy_version: str
    expires_at: datetime
    sensitivities: tuple[DataSensitivity, ...] = ()
    categories: tuple[DataCategory, ...] = ()
    enabled: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.provider_id)
        require_text(self.policy_version)
        require_timestamp(self.expires_at)
        validate_scope(self.sensitivities, DataSensitivity)
        validate_scope(self.categories, DataCategory)
        if DataSensitivity.UNKNOWN in self.sensitivities or not isinstance(self.enabled, bool):
            raise DomainError(
                "Provider scope cannot authorize unknown sensitivity or implicit enablement."
            )

    def covers(
        self, sensitivity: DataSensitivity, categories: tuple[DataCategory, ...], now: datetime
    ) -> bool:
        require_timestamp(now)
        validate_data_scope(sensitivity, categories)
        return (
            self.enabled
            and now < self.expires_at
            and sensitivity in self.sensitivities
            and set(categories) <= set(self.categories)
        )
