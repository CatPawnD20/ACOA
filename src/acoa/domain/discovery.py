"""Authorized discovery values; source content remains untrusted observation data."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from acoa.domain.authorization import DataCategory, validate_scope
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)


class SourceKind(StrEnum):
    OFFICIAL_API = "official_api"
    SEARCH_API = "search_api"
    PUBLIC_HTTP = "public_http"


class SourceResourceKind(StrEnum):
    SOURCE_PAGE = "source_page"
    ORGANIZATION = "organization"
    OPPORTUNITY = "opportunity"


class SourceOperation(StrEnum):
    DISCOVER = "discover"
    FETCH = "fetch"


class SourceAccessStatus(StrEnum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    ACCESS_CHALLENGE = "access_challenge"
    INVALID_RESPONSE = "invalid_response"


def _require_bounded_text(value: object, maximum: int) -> None:
    require_text(value)
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("Discovery text exceeds its bounded contract.")


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    source_id: UUID = field(repr=False)
    policy_version: str
    name: str
    kind: SourceKind
    entrypoint_url: str = field(repr=False)
    allowed_hosts: tuple[str, ...]
    allowed_media_types: tuple[str, ...]
    allowed_data_categories: tuple[DataCategory, ...]
    terms_reference: str
    license_reference: str
    observed_at: datetime
    valid_until: datetime
    access_allowed: bool
    max_response_bytes: int
    max_redirects: int
    max_batch_results: int
    snapshot_ttl_seconds: int

    def __post_init__(self) -> None:
        require_identifier(self.source_id)
        for value in (
            self.policy_version,
            self.name,
            self.entrypoint_url,
            self.terms_reference,
            self.license_reference,
        ):
            _require_bounded_text(value, 4096)
        if not isinstance(self.kind, SourceKind):
            raise DomainError("A discovery source requires an explicit kind.")
        if not isinstance(self.allowed_hosts, tuple) or not self.allowed_hosts:
            raise DomainError("A source policy requires immutable allowed hosts.")
        for host in self.allowed_hosts:
            _require_bounded_text(host, 253)
            if host != host.lower() or host.endswith("."):
                raise DomainError("Allowed source hosts must use canonical lowercase form.")
        if len(set(self.allowed_hosts)) != len(self.allowed_hosts):
            raise DomainError("A source policy must not repeat allowed hosts.")
        if not isinstance(self.allowed_media_types, tuple) or not self.allowed_media_types:
            raise DomainError("A source policy requires immutable allowed media types.")
        for media_type in self.allowed_media_types:
            _require_bounded_text(media_type, 127)
            if media_type != media_type.lower() or "/" not in media_type or ";" in media_type:
                raise DomainError("Allowed media types must use canonical base types.")
        if len(set(self.allowed_media_types)) != len(self.allowed_media_types):
            raise DomainError("A source policy must not repeat media types.")
        validate_scope(self.allowed_data_categories, DataCategory)
        require_timestamp(self.observed_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.observed_at:
            raise DomainError("A source policy validity window must follow its observation.")
        if not isinstance(self.access_allowed, bool):
            raise DomainError("Source access permission must be explicit.")
        for bound in (
            self.max_response_bytes,
            self.max_batch_results,
            self.snapshot_ttl_seconds,
        ):
            if isinstance(bound, bool) or not isinstance(bound, int) or bound < 1:
                raise DomainError(
                    "Source size, batch and lifetime bounds must be positive integers."
                )
        if (
            isinstance(self.max_redirects, bool)
            or not isinstance(self.max_redirects, int)
            or self.max_redirects < 0
        ):
            raise DomainError("The source redirect bound must be a nonnegative integer.")


@dataclass(frozen=True, slots=True)
class SourceAccessPermit:
    decision_id: UUID = field(repr=False)
    source_id: UUID = field(repr=False)
    policy_version: str
    evaluated_at: datetime
    expires_at: datetime
    allowed: bool

    def __post_init__(self) -> None:
        require_identifier(self.decision_id)
        require_identifier(self.source_id)
        _require_bounded_text(self.policy_version, 255)
        require_timestamp(self.evaluated_at)
        require_timestamp(self.expires_at)
        if self.expires_at <= self.evaluated_at:
            raise DomainError("A source-access decision must have a future expiry.")
        if not isinstance(self.allowed, bool):
            raise DomainError("A source-access decision must be explicit.")


def source_access_is_current(
    policy: SourcePolicy, permit: SourceAccessPermit, now: datetime
) -> bool:
    """Require two exact current trusted bindings; structural values are not proof of origin."""
    require_timestamp(now)
    return (
        policy.access_allowed
        and policy.observed_at <= now < policy.valid_until
        and permit.allowed
        and permit.source_id == policy.source_id
        and permit.policy_version == policy.policy_version
        and permit.evaluated_at >= policy.observed_at
        and permit.evaluated_at <= now < permit.expires_at
    )


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    query_id: UUID = field(repr=False)
    text: str = field(repr=False)
    text_sha256: str
    data_categories: tuple[DataCategory, ...]
    requested_at: datetime
    max_results: int

    def __post_init__(self) -> None:
        require_identifier(self.query_id)
        _require_bounded_text(self.text, 4000)
        require_sha256(self.text_sha256)
        if self.text_sha256 != discovery_query_sha256(self.text):
            raise DomainError("A discovery query digest must bind its exact text.")
        validate_scope(self.data_categories, DataCategory)
        require_timestamp(self.requested_at)
        if (
            isinstance(self.max_results, bool)
            or not isinstance(self.max_results, int)
            or self.max_results < 1
        ):
            raise DomainError("A discovery query requires a positive result bound.")


def discovery_query_sha256(text: str) -> str:
    _require_bounded_text(text, 4000)
    return content_digest({"schema": "acoa-discovery-query/1", "text": text})


def canonical_resource_sha256(source_id: UUID, kind: SourceResourceKind, external_id: str) -> str:
    require_identifier(source_id)
    if not isinstance(kind, SourceResourceKind):
        raise DomainError("A discovered resource requires an explicit kind.")
    _require_bounded_text(external_id, 2048)
    return content_digest(
        {
            "schema": "acoa-source-resource/1",
            "source_id": str(source_id),
            "kind": kind.value,
            "external_id": external_id,
        }
    )


@dataclass(frozen=True, slots=True)
class DiscoveredResource:
    resource_id: UUID = field(repr=False)
    source_id: UUID = field(repr=False)
    kind: SourceResourceKind
    external_id: str = field(repr=False)
    canonical_sha256: str
    canonical_url: str = field(repr=False)
    discovered_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.resource_id)
        require_identifier(self.source_id)
        if not isinstance(self.kind, SourceResourceKind):
            raise DomainError("A discovered resource requires an explicit kind.")
        _require_bounded_text(self.external_id, 2048)
        require_sha256(self.canonical_sha256)
        if self.canonical_sha256 != canonical_resource_sha256(
            self.source_id, self.kind, self.external_id
        ):
            raise DomainError("A discovered resource identity must bind its stable source key.")
        _require_bounded_text(self.canonical_url, 4096)
        require_timestamp(self.discovered_at)


@dataclass(frozen=True, slots=True)
class SourceBatch:
    batch_id: UUID
    source_id: UUID = field(repr=False)
    source_policy_version: str
    query_sha256: str
    resources: tuple[DiscoveredResource, ...]
    observed_at: datetime
    access_evidence_sha256: str
    next_cursor: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.batch_id)
        require_identifier(self.source_id)
        _require_bounded_text(self.source_policy_version, 255)
        require_sha256(self.query_sha256)
        if not isinstance(self.resources, tuple) or any(
            not isinstance(item, DiscoveredResource) for item in self.resources
        ):
            raise DomainError("A discovery batch requires immutable validated resources.")
        if len({item.canonical_sha256 for item in self.resources}) != len(self.resources):
            raise DomainError("A discovery batch must not repeat canonical resources.")
        if any(item.source_id != self.source_id for item in self.resources):
            raise DomainError("Every discovered resource must belong to the batch source.")
        require_timestamp(self.observed_at)
        if any(item.discovered_at != self.observed_at for item in self.resources):
            raise DomainError("Every discovered resource must bind the batch observation time.")
        require_sha256(self.access_evidence_sha256)
        if self.next_cursor is not None:
            _require_bounded_text(self.next_cursor, 4096)


def source_batch_sha256(batch: SourceBatch) -> str:
    if not isinstance(batch, SourceBatch):
        raise DomainError("A validated discovery batch is required.")
    return content_digest(
        {
            "schema": "acoa-source-batch/1",
            "batch_id": str(batch.batch_id),
            "source_id": str(batch.source_id),
            "source_policy_version": batch.source_policy_version,
            "query_sha256": batch.query_sha256,
            "resources": [
                {
                    "resource_id": str(item.resource_id),
                    "canonical_sha256": item.canonical_sha256,
                    "canonical_url": item.canonical_url,
                    "discovered_at": item.discovered_at.astimezone(UTC).isoformat(),
                }
                for item in batch.resources
            ],
            "observed_at": batch.observed_at.astimezone(UTC).isoformat(),
            "access_evidence_sha256": batch.access_evidence_sha256,
            "next_cursor": batch.next_cursor,
        }
    )


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    snapshot_id: UUID
    resource: DiscoveredResource
    source_policy_version: str
    canonical_url: str = field(repr=False)
    observed_at: datetime
    valid_until: datetime
    content_sha256: str
    media_type: str
    byte_length: int
    access_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.snapshot_id)
        if not isinstance(self.resource, DiscoveredResource):
            raise DomainError("A source snapshot requires a canonical resource.")
        _require_bounded_text(self.source_policy_version, 255)
        _require_bounded_text(self.canonical_url, 4096)
        require_timestamp(self.observed_at)
        require_timestamp(self.valid_until)
        if self.observed_at < self.resource.discovered_at:
            raise DomainError("A source snapshot cannot predate resource discovery.")
        if self.valid_until <= self.observed_at:
            raise DomainError("A source snapshot validity window must follow observation.")
        require_sha256(self.content_sha256)
        _require_bounded_text(self.media_type, 127)
        if (
            self.media_type != self.media_type.lower()
            or "/" not in self.media_type
            or ";" in self.media_type
        ):
            raise DomainError("A source snapshot requires a canonical base media type.")
        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
            or self.byte_length < 0
        ):
            raise DomainError("A source snapshot byte length must be a nonnegative integer.")
        require_sha256(self.access_evidence_sha256)


def source_snapshot_sha256(snapshot: SourceSnapshot) -> str:
    if not isinstance(snapshot, SourceSnapshot):
        raise DomainError("A validated source snapshot is required.")
    return content_digest(
        {
            "schema": "acoa-source-snapshot/1",
            "snapshot_id": str(snapshot.snapshot_id),
            "resource_sha256": snapshot.resource.canonical_sha256,
            "source_policy_version": snapshot.source_policy_version,
            "canonical_url": snapshot.canonical_url,
            "observed_at": snapshot.observed_at.astimezone(UTC).isoformat(),
            "valid_until": snapshot.valid_until.astimezone(UTC).isoformat(),
            "content_sha256": snapshot.content_sha256,
            "media_type": snapshot.media_type,
            "byte_length": snapshot.byte_length,
            "access_evidence_sha256": snapshot.access_evidence_sha256,
        }
    )


@dataclass(frozen=True, slots=True)
class SourceObservation:
    observation_id: UUID
    source_id: UUID = field(repr=False)
    source_policy_version: str
    operation: SourceOperation
    target_sha256: str
    canonical_url: str = field(repr=False)
    status: SourceAccessStatus
    observed_at: datetime
    result_sha256: str | None = None
    access_evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.observation_id)
        require_identifier(self.source_id)
        _require_bounded_text(self.source_policy_version, 255)
        if not isinstance(self.operation, SourceOperation) or not isinstance(
            self.status, SourceAccessStatus
        ):
            raise DomainError("A source observation requires explicit operation and status.")
        require_sha256(self.target_sha256)
        _require_bounded_text(self.canonical_url, 4096)
        require_timestamp(self.observed_at)
        for digest in (self.result_sha256, self.access_evidence_sha256):
            if digest is not None:
                require_sha256(digest)
        if (self.status is SourceAccessStatus.SUCCEEDED) != (self.result_sha256 is not None):
            raise DomainError("Only successful source observations may bind a result.")
        if self.status is SourceAccessStatus.SUCCEEDED and self.access_evidence_sha256 is None:
            raise DomainError("A successful source observation requires access evidence.")


@dataclass(frozen=True, slots=True)
class UntrustedSourceDocument:
    snapshot: SourceSnapshot
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, SourceSnapshot) or not isinstance(self.content, bytes):
            raise DomainError("A fetched source document requires immutable bytes and metadata.")
        if len(self.content) != self.snapshot.byte_length:
            raise DomainError("Fetched source bytes must match snapshot length.")
        if content_digest_bytes(self.content) != self.snapshot.content_sha256:
            raise DomainError("Fetched source bytes must match the snapshot digest.")


def content_digest_bytes(content: bytes) -> str:
    if not isinstance(content, bytes):
        raise DomainError("Source content must be immutable bytes.")
    return sha256(content).hexdigest()
