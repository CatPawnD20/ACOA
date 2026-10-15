"""Select only required approved facts and isolate external text as untrusted data."""

import json
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from acoa.domain.authorization import DataCategory
from acoa.domain.model_context import (
    CONTEXT_SCHEMA,
    PackedModelContext,
    ProfileFieldSelection,
    UntrustedContextSource,
    utc_text,
)
from acoa.domain.model_privacy import DataSensitivity, validate_data_scope
from acoa.domain.profile import (
    ProfileFact,
    ProfileVariant,
    fact_content_sha256,
    variant_content_sha256,
    variant_is_usable,
)
from acoa.domain.values import DomainError, require_timestamp


def aggregate_scope(
    scopes: tuple[tuple[DataSensitivity, tuple[DataCategory, ...]], ...],
) -> tuple[DataSensitivity, tuple[DataCategory, ...]]:
    if not scopes:
        return DataSensitivity.PUBLIC, ()
    if any(sensitivity is DataSensitivity.UNKNOWN for sensitivity, _ in scopes):
        raise DomainError("Unknown data sensitivity cannot enter model context.")
    categories = tuple(
        sorted(
            {category for _, values in scopes for category in values}, key=lambda item: item.value
        )
    )
    if any(sensitivity is DataSensitivity.SENSITIVE for sensitivity, _ in scopes):
        sensitivity = DataSensitivity.SENSITIVE
    elif any(sensitivity is DataSensitivity.PERSONAL for sensitivity, _ in scopes):
        sensitivity = DataSensitivity.PERSONAL
    else:
        sensitivity = DataSensitivity.PUBLIC
    validate_data_scope(sensitivity, categories)
    return sensitivity, categories


def select_profile_facts(
    variant: ProfileVariant | None,
    selections: tuple[ProfileFieldSelection, ...],
    now: datetime,
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...], datetime | None]:
    if not isinstance(selections, tuple) or any(
        not isinstance(item, ProfileFieldSelection) for item in selections
    ):
        raise DomainError("Profile selections must be an immutable validated tuple.")
    if not selections:
        return (), (), None
    if variant is None or not variant_is_usable(variant, now):
        raise DomainError("Selected profile context requires a current approved profile variant.")
    if len({item.fact_id for item in selections}) != len(selections):
        raise DomainError("A profile field can be selected only once.")
    facts: dict[UUID, ProfileFact] = {fact.fact_id: fact for fact in variant.facts}
    records: list[dict[str, object]] = []
    digests: list[str] = []
    for selection in sorted(selections, key=lambda item: item.fact_id.int):
        fact = facts.get(selection.fact_id)
        if fact is None:
            raise DomainError("A requested profile fact is absent from the approved snapshot.")
        records.append({"kind": fact.kind, "value": fact.value})
        digests.append(fact_content_sha256(fact))
    return tuple(records), (variant_content_sha256(variant), *digests), variant.valid_until


def select_external_sources(
    sources: tuple[UntrustedContextSource, ...], now: datetime
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...], datetime | None]:
    if not isinstance(sources, tuple) or any(
        not isinstance(item, UntrustedContextSource) for item in sources
    ):
        raise DomainError("External context sources must be an immutable validated tuple.")
    if len({item.source_id for item in sources}) != len(sources):
        raise DomainError("An external source can be selected only once.")
    records: list[dict[str, object]] = []
    deadlines: list[datetime] = []
    selected_sources = tuple(sorted(sources, key=lambda item: item.source_id.int))
    for source in selected_sources:
        if source.observed_at > now or now >= source.valid_until:
            raise DomainError("External context must be observed and current at packing time.")
        records.append(
            {
                "label": f"external_data_{len(records) + 1}",
                "observed_at": utc_text(source.observed_at),
                "content": source.content,
            }
        )
        deadlines.append(source.valid_until)
    valid_until = min(deadlines) if deadlines else None
    digests = tuple(
        sha256(
            json.dumps(
                {
                    "source_id": str(item.source_id),
                    "version": item.version,
                    "content_sha256": item.content_sha256,
                    "observed_at": utc_text(item.observed_at),
                    "valid_until": utc_text(item.valid_until),
                    "sensitivity": item.sensitivity.value,
                    "categories": [category.value for category in item.categories],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for item in selected_sources
    )
    return tuple(records), digests, valid_until


def pack_model_context(
    variant: ProfileVariant | None,
    profile_fields: tuple[ProfileFieldSelection, ...],
    external_sources: tuple[UntrustedContextSource, ...],
    now: datetime,
    max_utf8_bytes: int,
) -> PackedModelContext:
    """Build a bounded payload; never truncate evidence or reinterpret source instructions."""
    require_timestamp(now)
    if (
        isinstance(max_utf8_bytes, bool)
        or not isinstance(max_utf8_bytes, int)
        or max_utf8_bytes < 1
    ):
        raise DomainError("Context byte limit must be a positive integer.")
    profile, profile_hashes, profile_deadline = select_profile_facts(variant, profile_fields, now)
    external, external_hashes, source_deadline = select_external_sources(external_sources, now)
    scopes = tuple((item.sensitivity, item.categories) for item in profile_fields) + tuple(
        (item.sensitivity, item.categories) for item in external_sources
    )
    sensitivity, categories = aggregate_scope(scopes)
    payload = {
        "schema": CONTEXT_SCHEMA,
        "data_scope": {
            "sensitivity": sensitivity.value,
            "categories": [item.value for item in categories],
        },
        "verified_profile_data": profile,
        "untrusted_external_data": external,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(encoded.encode("utf-8")) > max_utf8_bytes:
        raise DomainError("Selected model context exceeds its explicit byte limit.")
    deadlines = tuple(item for item in (profile_deadline, source_deadline) if item is not None)
    return PackedModelContext(
        encoded,
        sha256(encoded.encode("utf-8")).hexdigest(),
        sensitivity,
        categories,
        profile_hashes + external_hashes,
        min(deadlines) if deadlines else None,
    )
