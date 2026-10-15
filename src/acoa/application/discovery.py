"""Fail-closed discovery orchestration over resolver-pinned source transports."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from acoa.domain.discovery import (
    DiscoveredResource,
    DiscoveryQuery,
    SourceAccessPermit,
    SourceAccessStatus,
    SourceBatch,
    SourceObservation,
    SourceOperation,
    SourcePolicy,
    SourceResourceKind,
    SourceSnapshot,
    UntrustedSourceDocument,
    canonical_resource_sha256,
    content_digest_bytes,
    source_access_is_current,
    source_batch_sha256,
    source_snapshot_sha256,
)
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_timestamp


@dataclass(frozen=True, slots=True)
class ResolvedEndpoint:
    """A URL and the public addresses a transport must pin for one request."""

    url: str
    host: str
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransportResource:
    kind: SourceResourceKind
    external_id: str = field(repr=False)
    url: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class TransportDiscoveryResponse:
    status: SourceAccessStatus
    resources: tuple[TransportResource, ...] = ()
    next_cursor: str | None = field(default=None, repr=False)
    redirect_url: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class TransportFetchResponse:
    status: SourceAccessStatus
    body: bytes | None = field(default=None, repr=False)
    media_type: str | None = None
    declared_length: int | None = None
    redirect_url: str | None = field(default=None, repr=False)


class EndpointResolver(Protocol):
    def resolve(self, host: str, port: int) -> tuple[str, ...]: ...


class SourceTransport(Protocol):
    """Trusted implementation must connect only to endpoint.addresses and disable redirects."""

    def discover(
        self,
        endpoint: ResolvedEndpoint,
        query: DiscoveryQuery,
        cursor: str | None,
    ) -> TransportDiscoveryResponse: ...

    def fetch(
        self, endpoint: ResolvedEndpoint, resource: DiscoveredResource
    ) -> TransportFetchResponse: ...


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    observation: SourceObservation
    batch: SourceBatch | None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, SourceObservation):
            raise DomainError("A discovery result requires a source observation.")
        if self.observation.operation is not SourceOperation.DISCOVER:
            raise DomainError("A discovery result requires a discovery observation.")
        succeeded = self.observation.status is SourceAccessStatus.SUCCEEDED
        if succeeded != isinstance(self.batch, SourceBatch):
            raise DomainError("A successful discovery observation requires its batch.")
        if self.batch is not None and self.observation.result_sha256 != source_batch_sha256(
            self.batch
        ):
            raise DomainError("A discovery observation must bind its exact batch.")


@dataclass(frozen=True, slots=True)
class FetchResult:
    observation: SourceObservation
    document: UntrustedSourceDocument | None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, SourceObservation):
            raise DomainError("A fetch result requires a source observation.")
        if self.observation.operation is not SourceOperation.FETCH:
            raise DomainError("A fetch result requires a fetch observation.")
        succeeded = self.observation.status is SourceAccessStatus.SUCCEEDED
        if succeeded != isinstance(self.document, UntrustedSourceDocument):
            raise DomainError("A successful fetch observation requires its untrusted document.")
        if self.document is not None and self.observation.result_sha256 != source_snapshot_sha256(
            self.document.snapshot
        ):
            raise DomainError("A fetch observation must bind its exact snapshot.")


class DiscoveryService:
    """Apply source, data, DNS, redirect and content bounds around one transport."""

    def __init__(
        self,
        policy: SourcePolicy,
        permit: SourceAccessPermit,
        resolver: EndpointResolver,
        transport: SourceTransport,
        identifier_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if not isinstance(policy, SourcePolicy) or not isinstance(permit, SourceAccessPermit):
            raise DomainError("Discovery requires validated source policy and access decision.")
        self.policy = policy
        self.permit = permit
        self.resolver = resolver
        self.transport = transport
        self.identifier_factory = identifier_factory

    def discover(self, query: DiscoveryQuery, cursor: str | None, now: datetime) -> DiscoveryResult:
        self._require_access(now)
        if not isinstance(query, DiscoveryQuery):
            raise DomainError("Discovery requires a validated bounded query.")
        if query.requested_at > now:
            raise DomainError("A discovery query must not be future-dated.")
        if query.max_results > self.policy.max_batch_results:
            raise DomainError("The query result bound exceeds source policy.")
        if not set(query.data_categories) <= set(self.policy.allowed_data_categories):
            raise DomainError("The source policy does not allow every shared query data category.")
        if cursor is not None and (not isinstance(cursor, str) or not cursor or len(cursor) > 4096):
            raise DomainError("A discovery cursor must be bounded nonempty text.")
        endpoint, failure = self._resolve_or_status(self.policy.entrypoint_url)
        if failure is not None:
            return self._failed_discovery(query, failure, (), now)
        assert endpoint is not None
        hops: list[ResolvedEndpoint] = []
        for redirect_count in range(self.policy.max_redirects + 1):
            hops.append(endpoint)
            try:
                response = self.transport.discover(endpoint, query, cursor)
            except TimeoutError:
                return self._failed_discovery(query, SourceAccessStatus.TIMEOUT, tuple(hops), now)
            except OSError:
                return self._failed_discovery(
                    query, SourceAccessStatus.UNAVAILABLE, tuple(hops), now
                )
            if not isinstance(response, TransportDiscoveryResponse):
                raise DomainError("A source transport returned an invalid discovery response.")
            if response.redirect_url is not None and (
                response.resources or response.next_cursor is not None
            ):
                return self._failed_discovery(
                    query, SourceAccessStatus.INVALID_RESPONSE, tuple(hops), now
                )
            redirect = self._redirect(response.redirect_url, response.status)
            if redirect is None:
                return self._build_discovery_result(query, response, tuple(hops), now)
            if redirect_count == self.policy.max_redirects:
                return self._failed_discovery(query, SourceAccessStatus.BLOCKED, tuple(hops), now)
            endpoint, failure = self._resolve_or_status(redirect)
            if failure is not None:
                return self._failed_discovery(query, failure, tuple(hops), now)
            assert endpoint is not None
        return self._failed_discovery(query, SourceAccessStatus.BLOCKED, tuple(hops), now)

    def fetch(self, resource: DiscoveredResource, now: datetime) -> FetchResult:
        self._require_access(now)
        self._require_resource(resource)
        endpoint, failure = self._resolve_or_status(resource.canonical_url)
        if failure is not None:
            return self._failed_fetch(resource, failure, (), now)
        assert endpoint is not None
        hops: list[ResolvedEndpoint] = []
        for redirect_count in range(self.policy.max_redirects + 1):
            hops.append(endpoint)
            try:
                response = self.transport.fetch(endpoint, resource)
            except TimeoutError:
                return self._failed_fetch(resource, SourceAccessStatus.TIMEOUT, tuple(hops), now)
            except OSError:
                return self._failed_fetch(
                    resource, SourceAccessStatus.UNAVAILABLE, tuple(hops), now
                )
            if not isinstance(response, TransportFetchResponse):
                raise DomainError("A source transport returned an invalid fetch response.")
            if response.redirect_url is not None and (
                response.body is not None
                or response.media_type is not None
                or response.declared_length is not None
            ):
                return self._failed_fetch(
                    resource, SourceAccessStatus.INVALID_RESPONSE, tuple(hops), now
                )
            redirect = self._redirect(response.redirect_url, response.status)
            if redirect is None:
                return self._build_fetch_result(resource, response, tuple(hops), now)
            if redirect_count == self.policy.max_redirects:
                return self._failed_fetch(resource, SourceAccessStatus.BLOCKED, tuple(hops), now)
            endpoint, failure = self._resolve_or_status(redirect)
            if failure is not None:
                return self._failed_fetch(resource, failure, tuple(hops), now)
            assert endpoint is not None
        return self._failed_fetch(resource, SourceAccessStatus.BLOCKED, tuple(hops), now)

    def _require_access(self, now: datetime) -> None:
        require_timestamp(now)
        if not source_access_is_current(self.policy, self.permit, now):
            raise DomainError("Source access policy or decision is absent, stale or denied.")

    def _require_resource(self, resource: DiscoveredResource) -> None:
        if (
            not isinstance(resource, DiscoveredResource)
            or resource.source_id != self.policy.source_id
        ):
            raise DomainError("A fetch resource must belong to the configured source.")
        self._canonical_url(resource.canonical_url)

    def _resolve(self, url: str) -> ResolvedEndpoint:
        canonical, parsed = self._canonical_url(url)
        host = parsed.hostname
        if host is None:
            raise DomainError("A source URL requires a host.")
        addresses = self.resolver.resolve(host, 443)
        if not isinstance(addresses, tuple) or not addresses:
            raise DomainError("Source DNS resolution must return immutable addresses.")
        canonical_addresses = tuple(sorted(set(addresses)))
        if len(canonical_addresses) != len(addresses):
            raise DomainError("Source DNS resolution must not repeat addresses.")
        for address in canonical_addresses:
            try:
                resolved = ip_address(address)
            except ValueError as error:
                raise DomainError("Source DNS resolution returned an invalid address.") from error
            if not resolved.is_global:
                raise DomainError("Source access resolved to a non-public address.")
        return ResolvedEndpoint(canonical, host, canonical_addresses)

    def _resolve_or_status(
        self, url: str
    ) -> tuple[ResolvedEndpoint | None, SourceAccessStatus | None]:
        try:
            return self._resolve(url), None
        except TimeoutError:
            return None, SourceAccessStatus.TIMEOUT
        except OSError:
            return None, SourceAccessStatus.UNAVAILABLE

    def _canonical_url(self, url: str) -> tuple[str, SplitResult]:
        if not isinstance(url, str) or not url or url != url.strip() or len(url) > 4096:
            raise DomainError("A source URL must be bounded canonical text.")
        if any(ord(character) < 32 or character == "\\" for character in url):
            raise DomainError("A source URL contains a prohibited character.")
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as error:
            raise DomainError("A source URL is malformed.") from error
        if (
            parsed.scheme != "https"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.query
            or port not in (None, 443)
        ):
            raise DomainError(
                "Source URLs require HTTPS without credentials, query data or fragments."
            )
        try:
            canonical_host = host.encode("idna").decode("ascii").lower().rstrip(".")
            ip_address(canonical_host)
        except UnicodeError as error:
            raise DomainError("A source URL host is malformed.") from error
        except ValueError:
            pass
        else:
            raise DomainError("Source URLs must not use direct IP literals.")
        if canonical_host not in self.policy.allowed_hosts:
            raise DomainError("A source URL host is outside the explicit allowlist.")
        netloc = canonical_host
        path = parsed.path or "/"
        canonical = urlunsplit(("https", netloc, path, "", ""))
        return canonical, urlsplit(canonical)

    @staticmethod
    def _redirect(redirect_url: str | None, status: object) -> str | None:
        if redirect_url is None:
            return None
        if status is not SourceAccessStatus.SUCCEEDED:
            raise DomainError("A source redirect cannot also report a failed access status.")
        if not isinstance(redirect_url, str) or not redirect_url:
            raise DomainError("A source redirect requires a bounded URL.")
        return redirect_url

    def _build_discovery_result(
        self,
        query: DiscoveryQuery,
        response: TransportDiscoveryResponse,
        hops: tuple[ResolvedEndpoint, ...],
        now: datetime,
    ) -> DiscoveryResult:
        self._require_status(response.status)
        evidence = access_evidence_sha256(self.policy, self.permit, hops)
        if not isinstance(response.resources, tuple):
            return self._failed_discovery(query, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        if response.status is not SourceAccessStatus.SUCCEEDED and (
            response.resources or response.next_cursor is not None
        ):
            return self._failed_discovery(query, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        if response.status is not SourceAccessStatus.SUCCEEDED:
            return self._failed_discovery(query, response.status, hops, now)
        if len(response.resources) > query.max_results:
            return self._failed_discovery(query, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        resources = tuple(self._resource_from_transport(item, now) for item in response.resources)
        if len({item.canonical_sha256 for item in resources}) != len(resources):
            return self._failed_discovery(query, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        batch = SourceBatch(
            batch_id=self.identifier_factory(),
            source_id=self.policy.source_id,
            source_policy_version=self.policy.policy_version,
            query_sha256=query.text_sha256,
            resources=resources,
            observed_at=now,
            access_evidence_sha256=evidence,
            next_cursor=response.next_cursor,
        )
        observation = self._observation(
            SourceOperation.DISCOVER,
            query.text_sha256,
            hops[0].url,
            SourceAccessStatus.SUCCEEDED,
            now,
            source_batch_sha256(batch),
            evidence,
        )
        return DiscoveryResult(observation, batch)

    def _resource_from_transport(
        self, item: TransportResource, observed_at: datetime
    ) -> DiscoveredResource:
        if not isinstance(item, TransportResource) or not isinstance(item.kind, SourceResourceKind):
            raise DomainError("A source returned an invalid resource shape.")
        canonical_url, _ = self._canonical_url(item.url)
        canonical = canonical_resource_sha256(self.policy.source_id, item.kind, item.external_id)
        return DiscoveredResource(
            resource_id=uuid5(NAMESPACE_URL, f"acoa:{canonical}"),
            source_id=self.policy.source_id,
            kind=item.kind,
            external_id=item.external_id,
            canonical_sha256=canonical,
            canonical_url=canonical_url,
            discovered_at=observed_at,
        )

    def _build_fetch_result(
        self,
        resource: DiscoveredResource,
        response: TransportFetchResponse,
        hops: tuple[ResolvedEndpoint, ...],
        now: datetime,
    ) -> FetchResult:
        self._require_status(response.status)
        evidence = access_evidence_sha256(self.policy, self.permit, hops)
        if response.status is not SourceAccessStatus.SUCCEEDED and (
            response.body is not None
            or response.media_type is not None
            or response.declared_length is not None
        ):
            return self._failed_fetch(resource, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        if response.status is not SourceAccessStatus.SUCCEEDED:
            return self._failed_fetch(resource, response.status, hops, now)
        content = self._validated_content(response)
        if content is None:
            return self._failed_fetch(resource, SourceAccessStatus.INVALID_RESPONSE, hops, now)
        body, media_type = content
        snapshot = self._snapshot(resource, hops[-1].url, body, media_type, evidence, now)
        document = UntrustedSourceDocument(snapshot, body)
        observation = self._observation(
            SourceOperation.FETCH,
            resource.canonical_sha256,
            resource.canonical_url,
            SourceAccessStatus.SUCCEEDED,
            now,
            source_snapshot_sha256(snapshot),
            evidence,
        )
        return FetchResult(observation, document)

    def _validated_content(self, response: TransportFetchResponse) -> tuple[bytes, str] | None:
        if not isinstance(response.body, bytes) or not isinstance(response.media_type, str):
            return None
        media_type = response.media_type.split(";", 1)[0].strip().lower()
        if media_type not in self.policy.allowed_media_types:
            return None
        length = len(response.body)
        if length > self.policy.max_response_bytes:
            return None
        if response.declared_length is not None and (
            isinstance(response.declared_length, bool)
            or not isinstance(response.declared_length, int)
            or response.declared_length < 0
            or response.declared_length > self.policy.max_response_bytes
            or response.declared_length != length
        ):
            return None
        return response.body, media_type

    def _snapshot(
        self,
        resource: DiscoveredResource,
        canonical_url: str,
        body: bytes,
        media_type: str,
        evidence_sha256: str,
        now: datetime,
    ) -> SourceSnapshot:
        valid_until = min(
            now + timedelta(seconds=self.policy.snapshot_ttl_seconds),
            self.policy.valid_until,
            self.permit.expires_at,
        )
        return SourceSnapshot(
            snapshot_id=self.identifier_factory(),
            resource=resource,
            source_policy_version=self.policy.policy_version,
            canonical_url=canonical_url,
            observed_at=now,
            valid_until=valid_until,
            content_sha256=content_digest_bytes(body),
            media_type=media_type,
            byte_length=len(body),
            access_evidence_sha256=evidence_sha256,
        )

    def _failed_discovery(
        self,
        query: DiscoveryQuery,
        status: SourceAccessStatus,
        hops: tuple[ResolvedEndpoint, ...],
        now: datetime,
    ) -> DiscoveryResult:
        return DiscoveryResult(
            self._observation(
                SourceOperation.DISCOVER,
                query.text_sha256,
                hops[0].url if hops else self.policy.entrypoint_url,
                status,
                now,
                None,
                access_evidence_sha256(self.policy, self.permit, hops),
            ),
            None,
        )

    def _failed_fetch(
        self,
        resource: DiscoveredResource,
        status: SourceAccessStatus,
        hops: tuple[ResolvedEndpoint, ...],
        now: datetime,
    ) -> FetchResult:
        return FetchResult(
            self._observation(
                SourceOperation.FETCH,
                resource.canonical_sha256,
                resource.canonical_url,
                status,
                now,
                None,
                access_evidence_sha256(self.policy, self.permit, hops),
            ),
            None,
        )

    def _observation(
        self,
        operation: SourceOperation,
        target_sha256: str,
        canonical_url: str,
        status: SourceAccessStatus,
        observed_at: datetime,
        result_sha256: str | None,
        evidence_sha256: str | None,
    ) -> SourceObservation:
        return SourceObservation(
            self.identifier_factory(),
            self.policy.source_id,
            self.policy.policy_version,
            operation,
            target_sha256,
            canonical_url,
            status,
            observed_at,
            result_sha256,
            evidence_sha256,
        )

    @staticmethod
    def _require_status(status: object) -> None:
        if not isinstance(status, SourceAccessStatus):
            raise DomainError("A source transport returned an invalid access status.")


def access_evidence_sha256(
    policy: SourcePolicy,
    permit: SourceAccessPermit,
    hops: tuple[ResolvedEndpoint, ...],
) -> str:
    if not isinstance(policy, SourcePolicy) or not isinstance(permit, SourceAccessPermit):
        raise DomainError("Source access evidence requires policy and decision bindings.")
    if not isinstance(hops, tuple) or any(not isinstance(hop, ResolvedEndpoint) for hop in hops):
        raise DomainError("Source access evidence requires immutable resolved endpoints.")
    return content_digest(
        {
            "schema": "acoa-source-access/1",
            "source_id": str(policy.source_id),
            "source_policy_version": policy.policy_version,
            "access_decision_id": str(permit.decision_id),
            "decision_evaluated_at": permit.evaluated_at.astimezone(UTC).isoformat(),
            "decision_expires_at": permit.expires_at.astimezone(UTC).isoformat(),
            "hops": [
                {"url": hop.url, "host": hop.host, "addresses": list(hop.addresses)} for hop in hops
            ],
        }
    )
