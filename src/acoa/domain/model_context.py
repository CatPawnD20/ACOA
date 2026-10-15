"""Minimal model context contracts; external content always remains untrusted data."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.authorization import DataCategory
from acoa.domain.model_privacy import DataSensitivity, validate_data_scope
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)

CONTEXT_SCHEMA = "acoa-model-context/1"


@dataclass(frozen=True, slots=True)
class ProfileFieldSelection:
    """A requested field from an already approved profile snapshot."""

    fact_id: UUID = field(repr=False)
    sensitivity: DataSensitivity
    categories: tuple[DataCategory, ...]

    def __post_init__(self) -> None:
        require_identifier(self.fact_id)
        if self.sensitivity not in (DataSensitivity.PERSONAL, DataSensitivity.SENSITIVE):
            raise DomainError("Profile context must be explicitly personal or sensitive.")
        validate_data_scope(self.sensitivity, self.categories)


@dataclass(frozen=True, slots=True)
class UntrustedContextSource:
    """Versioned external text; its content can never become an instruction or permission."""

    source_id: UUID = field(repr=False)
    version: int
    content: str = field(repr=False)
    content_sha256: str = field(repr=False)
    observed_at: datetime
    valid_until: datetime
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    categories: tuple[DataCategory, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.source_id)
        require_version(self.version)
        if not isinstance(self.content, str) or not self.content:
            raise DomainError("External context content must be explicit nonempty text.")
        require_sha256(self.content_sha256)
        if sha256(self.content.encode("utf-8")).hexdigest() != self.content_sha256:
            raise DomainError("External context content does not match its evidence digest.")
        require_timestamp(self.observed_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.observed_at:
            raise DomainError("External context validity must follow its observation.")
        validate_data_scope(self.sensitivity, self.categories)


@dataclass(frozen=True, slots=True)
class PackedModelContext:
    """Private provider payload plus non-content bindings used by routing and cache keys."""

    context_json: str = field(repr=False)
    context_sha256: str = field(repr=False)
    sensitivity: DataSensitivity
    categories: tuple[DataCategory, ...]
    component_sha256s: tuple[str, ...] = field(repr=False)
    valid_until: datetime | None

    def __post_init__(self) -> None:
        require_sha256(self.context_sha256)
        if sha256(self.context_json.encode("utf-8")).hexdigest() != self.context_sha256:
            raise DomainError("Packed context does not match its digest.")
        validate_data_scope(self.sensitivity, self.categories)
        validate_context_payload(self.context_json, self.sensitivity, self.categories)
        if not isinstance(self.component_sha256s, tuple) or any(
            not isinstance(item, str) for item in self.component_sha256s
        ):
            raise DomainError("Packed context requires immutable component digests.")
        for digest in self.component_sha256s:
            require_sha256(digest)
        if self.valid_until is not None:
            require_timestamp(self.valid_until)


def validate_context_payload(
    context_json: str,
    sensitivity: DataSensitivity,
    categories: tuple[DataCategory, ...],
) -> None:
    """Reject extra instruction-like fields and classification mismatches at the gateway."""
    try:
        payload = json.loads(context_json)
    except (TypeError, ValueError):
        raise DomainError("Packed context must be valid JSON.") from None
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "schema",
            "data_scope",
            "verified_profile_data",
            "untrusted_external_data",
        }
        or payload.get("schema") != CONTEXT_SCHEMA
    ):
        raise DomainError("Packed context must use the approved context schema.")
    expected_scope = {
        "sensitivity": sensitivity.value,
        "categories": [item.value for item in categories],
    }
    if payload["data_scope"] != expected_scope:
        raise DomainError("Packed context classification does not match its payload.")
    profile = payload["verified_profile_data"]
    external = payload["untrusted_external_data"]
    if not isinstance(profile, list) or any(
        not isinstance(item, dict)
        or set(item) != {"kind", "value"}
        or not all(isinstance(value, str) for value in item.values())
        for item in profile
    ):
        raise DomainError("Packed profile context has an invalid structure.")
    for item in profile:
        require_text(item["kind"])
        require_text(item["value"])
    if not isinstance(external, list) or any(
        not isinstance(item, dict)
        or set(item) != {"label", "observed_at", "content"}
        or not all(isinstance(value, str) for value in item.values())
        for item in external
    ):
        raise DomainError("Packed external context has an invalid structure.")
    for index, item in enumerate(external, start=1):
        if item["label"] != f"external_data_{index}" or not item["content"]:
            raise DomainError("Packed external context has invalid labels or empty content.")
        try:
            observed_at = datetime.fromisoformat(item["observed_at"])
        except ValueError:
            raise DomainError("Packed external observation time is invalid.") from None
        require_timestamp(observed_at)


def require_current_context(context: PackedModelContext, now: datetime) -> None:
    require_timestamp(now)
    if context.valid_until is not None and now >= context.valid_until:
        raise DomainError("Model context is stale and must be rebuilt from current evidence.")


def utc_text(value: datetime) -> str:
    require_timestamp(value)
    return value.astimezone(UTC).isoformat()
